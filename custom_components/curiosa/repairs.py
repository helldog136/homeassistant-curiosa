"""Reparation « une action n'a pas de script relie » : on choisit le script sur place."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .bindings import is_bindable, with_binding
from .const import BINDABLE_DOMAINS, DOMAIN, KEY_RE, MAX_BINDINGS, OPT_BINDINGS, OPT_ENTITY
from .coordinator import CuriosaConfigEntry


class LinkActionRepairFlow(RepairsFlow):
    """Une seule question : quel script ou quelle scene pour cette action ?"""

    def __init__(self, entry_id: str, key: str) -> None:
        self._entry_id = entry_id
        self._key = key

    def _entry(self) -> CuriosaConfigEntry | None:
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            return None
        return entry

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> FlowResult:
        """Choix du script ou de la scene."""
        entry = self._entry()
        if entry is None:
            return self.async_abort(reason="not_ready")
        coordinator = entry.runtime_data
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_id = user_input.get(OPT_ENTITY)
            if not is_bindable(entity_id):
                errors[OPT_ENTITY] = "invalid_target"
            elif len(entry.options.get(OPT_BINDINGS, [])) >= MAX_BINDINGS:
                errors["base"] = "too_many"
            else:
                self.hass.config_entries.async_update_entry(
                    entry, options=with_binding(entry.options, self._key, entity_id)
                )
                coordinator.async_sync_issues()
                return self.async_create_entry(data={})
        schema = vol.Schema(
            {
                vol.Required(OPT_ENTITY): EntitySelector(
                    EntitySelectorConfig(domain=list(BINDABLE_DOMAINS))
                )
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={"action": coordinator.label_for(self._key)},
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Cree la reparation (donnees controlees : on les revalide)."""
    info: dict[str, Any] = data or {}
    entry_id = info.get("entry_id")
    key = info.get("key")
    if (
        not isinstance(entry_id, str)
        or not isinstance(key, str)
        or not KEY_RE.fullmatch(key)
        or hass.config_entries.async_get_entry(entry_id) is None
        or hass.config_entries.async_get_entry(entry_id).domain != DOMAIN
    ):
        raise ValueError("unknown issue")
    return LinkActionRepairFlow(entry_id, key)
