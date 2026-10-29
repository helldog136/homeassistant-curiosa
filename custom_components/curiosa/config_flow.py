"""Assistant d'installation (appairage) et reglages (la liaison)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .api import (
    CatalogItem,
    CuriosaApi,
    CuriosaConnectionError,
    CuriosaError,
    CuriosaHttpError,
    CuriosaPairError,
)
from .bindings import binding_lines, is_bindable, linked_entity, with_binding
from .const import (
    BINDABLE_DOMAINS,
    CONF_CODE,
    CONF_DEVELOPER,
    CONF_INSTANCE,
    CONF_POLL_SECONDS,
    CONF_TOKEN,
    CONF_URL,
    DEVICE_NAME,
    DOMAIN,
    KEY_RE,
    MAX_BINDINGS,
    OPT_ACTION,
    OPT_BINDINGS,
    OPT_ENTITY,
    OPT_KEY,
    OPT_REMOVE,
    OPT_TTS_ENGINE,
    OPT_TTS_LANGUAGE,
    OPT_TTS_PLAYER,
    OPT_TTS_SAY_VIEWER,
    OPT_TTS_VOLUME,
    TTS_KEY_PREFIX,
)
from .coordinator import CuriosaConfigEntry, async_stored_catalog
from .sanitize import AddressError, normalize_code, parse_site_address, site_root

_LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}([-_][A-Za-z0-9]{2,8})?$")


class CuriosaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Appairage avec le code a 8 caracteres affiche dans l'admin de Curiosa."""

    VERSION = 1

    async def _pair(self, base_url: str, code: str, errors: dict[str, str]) -> Any:
        """Appelle ``pair`` ; remplit ``errors`` en cas d'echec."""
        api = CuriosaApi(async_get_clientsession(self.hass), base_url)
        try:
            return await api.pair(code, DEVICE_NAME)
        except CuriosaPairError as err:
            errors[CONF_CODE if err.reason != "not_found" else CONF_URL] = err.reason
        except (CuriosaConnectionError, CuriosaHttpError):
            errors["base"] = "cannot_connect"
        except CuriosaError:
            errors["base"] = "unknown"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Etape 1 : adresse du site + code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            developer = bool(user_input.get(CONF_DEVELOPER, False))
            address = None
            try:
                address = parse_site_address(user_input.get(CONF_URL), developer)
            except AddressError as err:
                errors[CONF_URL] = err.code
            code = normalize_code(user_input.get(CONF_CODE))
            if code is None:
                errors[CONF_CODE] = "invalid_code_format"
            if address is not None and not errors:
                await self.async_set_unique_id(address.base_url)
                self._abort_if_unique_id_configured()
                result = await self._pair(address.base_url, code or "", errors)
                if result is not None:
                    return self.async_create_entry(
                        title=address.host,
                        data={
                            CONF_URL: address.base_url,
                            CONF_TOKEN: result.token,
                            CONF_INSTANCE: result.instance,
                            CONF_POLL_SECONDS: result.poll_seconds,
                            CONF_DEVELOPER: developer,
                        },
                    )
        schema = vol.Schema(
            {
                vol.Required(CONF_URL): TextSelector(),
                vol.Required(CONF_CODE): TextSelector(),
                vol.Optional(CONF_DEVELOPER, default=False): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
            description_placeholders={"example": self._example_address()},
        )

    def _example_address(self) -> str:
        """Exemple d'adresse dans la langue de l'utilisateur (pas d'URL dans les textes)."""
        if str(self.hass.config.language).startswith("fr"):
            return "https://mon-site.com"
        return "https://my-site.com"

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Le site a refuse le jeton (401) : il faut un nouveau code."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Nouveau code, meme site."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            code = normalize_code(user_input.get(CONF_CODE))
            if code is None:
                errors[CONF_CODE] = "invalid_code_format"
            else:
                result = await self._pair(entry.data[CONF_URL], code, errors)
                if result is not None:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={
                            CONF_TOKEN: result.token,
                            CONF_INSTANCE: result.instance,
                            CONF_POLL_SECONDS: result.poll_seconds,
                        },
                    )
        host = entry.title
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_CODE): TextSelector()}),
            description_placeholders={"host": host},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: CuriosaConfigEntry) -> CuriosaOptionsFlow:
        """Reglages : la liaison et la voix."""
        return CuriosaOptionsFlow()


_TEXTS: dict[str, dict[str, str]] = {
    "fr": {
        "linked": "reliée à {entity}",
        "free": "pas encore reliée",
        "voice_ready": "voix réglée",
        "voice_missing": "voix pas encore réglée (voir « Voix »)",
        "old": "ancienne liaison",
    },
    "en": {
        "linked": "linked to {entity}",
        "free": "not linked yet",
        "voice_ready": "voice set up",
        "voice_missing": 'voice not set up yet (see "Voice")',
        "old": "old link",
    },
}


class CuriosaOptionsFlow(OptionsFlow):
    """Liaison « action -> script ou scene » (par son nom) et reglage de la voix."""

    config_entry: CuriosaConfigEntry

    def __init__(self) -> None:
        self._catalog: list[CatalogItem] = []
        self._key = ""

    # --- aides --------------------------------------------------------------
    def _text(self, name: str, **values: str) -> str:
        language = "fr" if str(self.hass.config.language).startswith("fr") else "en"
        return _TEXTS[language][name].format(**values)

    async def _load_catalog(self) -> None:
        entry = self.config_entry
        if entry.state is ConfigEntryState.LOADED:
            self._catalog = list(entry.runtime_data.catalog)
        else:
            self._catalog = await async_stored_catalog(self.hass, entry.entry_id)

    def _site(self) -> str:
        return site_root(self.config_entry.data[CONF_URL])

    def _label(self, key: str) -> str:
        return next((item.label for item in self._catalog if item.key == key), key)

    def _state(self, key: str) -> str:
        """Etat d'une action en mots simples."""
        options = self.config_entry.options
        if key.startswith(TTS_KEY_PREFIX):
            ready = options.get(OPT_TTS_PLAYER) and options.get(OPT_TTS_ENGINE)
            return self._text("voice_ready" if ready else "voice_missing")
        entity_id = linked_entity(options, key)
        if entity_id is None:
            return self._text("free")
        return self._text("linked", entity=entity_id)

    def _simple_screens(self) -> bool:
        """Vrai si on montre la liste par noms (le site a envoye son catalogue)."""
        return bool(self._catalog)

    def _manual_visible(self) -> bool:
        """Saisie a la main : mode avance, ou site sans catalogue (ancien site)."""
        return self.show_advanced_options or not self._catalog

    # --- menu ----------------------------------------------------------------
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        """Menu."""
        await self._load_catalog()
        lines = binding_lines(self.config_entry.options)
        menu = []
        if self._catalog or lines:
            menu.append("bindings")
        if self._manual_visible():
            menu.append("add_binding")
            if lines:
                menu.append("remove_binding")
        menu.append("tts")
        return self.async_show_menu(
            step_id="init",
            menu_options=menu,
            description_placeholders={"site": self._site()},
        )

    # --- la liste des actions, par leur nom ----------------------------------------
    async def async_step_bindings(self, user_input: dict[str, Any] | None = None) -> Any:
        """Liste des actions avec leur etat ; on en choisit une pour la relier."""
        if not self._catalog:
            await self._load_catalog()
        if user_input is not None:
            key = user_input.get(OPT_ACTION)
            if not key:
                return self.async_create_entry(data=dict(self.config_entry.options))
            if key.startswith(TTS_KEY_PREFIX):
                return await self.async_step_tts()
            self._key = key
            return await self.async_step_link()
        known = [item.key for item in self._catalog]
        old = sorted(
            line[OPT_KEY]
            for line in binding_lines(self.config_entry.options)
            if line[OPT_KEY] not in known
        )
        choices = [
            SelectOptionDict(value=item.key, label=f"{item.label} : {self._state(item.key)}")
            for item in self._catalog
        ] + [
            SelectOptionDict(value=key, label=f"{key} ({self._text('old')}) : {self._state(key)}")
            for key in old
        ]
        schema = vol.Schema(
            {
                vol.Optional(OPT_ACTION): SelectSelector(
                    SelectSelectorConfig(options=choices, mode=SelectSelectorMode.LIST)
                )
            }
        )
        return self.async_show_form(
            step_id="bindings",
            data_schema=schema,
            description_placeholders={"site": self._site()},
        )

    async def async_step_link(self, user_input: dict[str, Any] | None = None) -> Any:
        """Choisit le script ou la scene d'une action (vide = ne plus la relier)."""
        errors: dict[str, str] = {}
        options = self.config_entry.options
        if user_input is not None:
            entity_id = user_input.get(OPT_ENTITY) or None
            if entity_id is not None and not is_bindable(entity_id):
                errors[OPT_ENTITY] = "invalid_target"
            elif (
                entity_id is not None
                and linked_entity(options, self._key) is None
                and len(binding_lines(options)) >= MAX_BINDINGS
            ):
                errors["base"] = "too_many"
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=with_binding(options, self._key, entity_id)
                )
                return await self.async_step_bindings()
        schema = vol.Schema(
            {
                vol.Optional(OPT_ENTITY): EntitySelector(
                    EntitySelectorConfig(domain=list(BINDABLE_DOMAINS))
                )
            }
        )
        suggested = user_input or {OPT_ENTITY: linked_entity(options, self._key)}
        return self.async_show_form(
            step_id="link",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
            description_placeholders={
                "action": self._label(self._key),
                "state": self._state(self._key),
            },
        )

    # --- avance : a la main, comme avant --------------------------------------------
    async def async_step_add_binding(self, user_input: dict[str, Any] | None = None) -> Any:
        """Ajoute une ligne (mot d'action tape a la main)."""
        errors: dict[str, str] = {}
        lines = binding_lines(self.config_entry.options)
        if user_input is not None:
            key = str(user_input.get(OPT_KEY, "")).strip().lower()
            entity_id = str(user_input.get(OPT_ENTITY, ""))
            if not KEY_RE.fullmatch(key):
                errors[OPT_KEY] = "invalid_key"
            elif key.startswith(TTS_KEY_PREFIX):
                errors[OPT_KEY] = "reserved_key"
            elif any(line[OPT_KEY] == key for line in lines):
                errors[OPT_KEY] = "duplicate_key"
            elif not is_bindable(entity_id):
                errors[OPT_ENTITY] = "invalid_target"
            elif len(lines) >= MAX_BINDINGS:
                errors["base"] = "too_many"
            if not errors:
                lines.append({OPT_KEY: key, OPT_ENTITY: entity_id})
                return self.async_create_entry(
                    data={**self.config_entry.options, OPT_BINDINGS: lines}
                )
        schema = vol.Schema(
            {
                vol.Required(OPT_KEY): TextSelector(),
                vol.Required(OPT_ENTITY): EntitySelector(
                    EntitySelectorConfig(domain=list(BINDABLE_DOMAINS))
                ),
            }
        )
        return self.async_show_form(
            step_id="add_binding",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_remove_binding(self, user_input: dict[str, Any] | None = None) -> Any:
        """Supprime une ou plusieurs lignes."""
        lines = binding_lines(self.config_entry.options)
        if user_input is not None:
            gone = set(user_input.get(OPT_REMOVE, []))
            kept = [line for line in lines if line[OPT_KEY] not in gone]
            return self.async_create_entry(data={**self.config_entry.options, OPT_BINDINGS: kept})
        choices = [
            SelectOptionDict(value=x[OPT_KEY], label=f"{x[OPT_KEY]} -> {x[OPT_ENTITY]}")
            for x in lines
        ]
        schema = vol.Schema(
            {
                vol.Required(OPT_REMOVE): SelectSelector(
                    SelectSelectorConfig(
                        options=choices, multiple=True, mode=SelectSelectorMode.LIST
                    )
                )
            }
        )
        return self.async_show_form(step_id="remove_binding", data_schema=schema)

    async def async_step_tts(self, user_input: dict[str, Any] | None = None) -> Any:
        """Voix : lecteur, moteur, langue, volume."""
        errors: dict[str, str] = {}
        if user_input is not None:
            language = str(user_input.get(OPT_TTS_LANGUAGE, "")).strip()
            if user_input.get(OPT_TTS_PLAYER) and not user_input.get(OPT_TTS_ENGINE):
                errors[OPT_TTS_ENGINE] = "engine_required"
            if language and not _LANGUAGE_RE.fullmatch(language):
                errors[OPT_TTS_LANGUAGE] = "invalid_language"
            if not errors:
                options = {
                    k: v for k, v in self.config_entry.options.items() if not k.startswith("tts_")
                }
                if user_input.get(OPT_TTS_PLAYER):
                    options[OPT_TTS_PLAYER] = user_input[OPT_TTS_PLAYER]
                    options[OPT_TTS_ENGINE] = user_input[OPT_TTS_ENGINE]
                    if language:
                        options[OPT_TTS_LANGUAGE] = language
                    if user_input.get(OPT_TTS_VOLUME) is not None:
                        options[OPT_TTS_VOLUME] = float(user_input[OPT_TTS_VOLUME])
                    options[OPT_TTS_SAY_VIEWER] = bool(user_input.get(OPT_TTS_SAY_VIEWER))
                return self.async_create_entry(data=options)
        schema = vol.Schema(
            {
                vol.Optional(OPT_TTS_PLAYER): EntitySelector(
                    EntitySelectorConfig(domain="media_player")
                ),
                vol.Optional(OPT_TTS_ENGINE): EntitySelector(EntitySelectorConfig(domain="tts")),
                vol.Optional(OPT_TTS_LANGUAGE): TextSelector(),
                vol.Optional(OPT_TTS_VOLUME): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=100,
                        step=1,
                        unit_of_measurement="%",
                        mode=NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Optional(OPT_TTS_SAY_VIEWER, default=False): BooleanSelector(),
            }
        )
        suggested = user_input or dict(self.config_entry.options)
        return self.async_show_form(
            step_id="tts",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
        )
