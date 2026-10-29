"""Integration Curiosa : relie les recompenses du stream a la maison, en local."""

from __future__ import annotations

from typing import Any

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import CuriosaApi, parse_catalog
from .const import (
    CONF_DEVELOPER,
    CONF_TOKEN,
    CONF_URL,
    DOMAIN,
    STORE_CATALOG,
    STORE_ENABLED,
)
from .coordinator import CuriosaConfigEntry, CuriosaCoordinator
from .sanitize import AddressError, parse_site_address

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]


def _store(hass: HomeAssistant, entry: CuriosaConfigEntry) -> Store[dict[str, Any]]:
    return Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")


async def async_setup_entry(hass: HomeAssistant, entry: CuriosaConfigEntry) -> bool:
    """Demarre l'integration."""
    # Defense en profondeur : on revalide l'adresse (https obligatoire).
    try:
        parse_site_address(entry.data[CONF_URL], bool(entry.data.get(CONF_DEVELOPER)))
    except AddressError as err:
        raise ConfigEntryError(translation_domain=DOMAIN, translation_key="bad_address") from err

    store = _store(hass, entry)
    saved = await store.async_load()
    local_enabled = bool(saved.get(STORE_ENABLED, True)) if isinstance(saved, dict) else True
    # Fichier de la 0.1.0 : pas de catalogue, tout le reste inchange.
    catalog = parse_catalog(saved.get(STORE_CATALOG)) if isinstance(saved, dict) else None

    api = CuriosaApi(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN])
    coordinator = CuriosaCoordinator(hass, entry, api, store, local_enabled, catalog)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    # Une liaison posee ou retiree ferme (ou rouvre) la reparation correspondante.
    entry.async_on_unload(entry.add_update_listener(_options_changed))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _options_changed(hass: HomeAssistant, entry: CuriosaConfigEntry) -> None:
    entry.runtime_data.async_sync_issues()


async def async_unload_entry(hass: HomeAssistant, entry: CuriosaConfigEntry) -> bool:
    """Arrete l'integration."""
    entry.runtime_data.async_clear_issues()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: CuriosaConfigEntry) -> None:
    """Efface l'etat de l'interrupteur local."""
    await _store(hass, entry).async_remove()
