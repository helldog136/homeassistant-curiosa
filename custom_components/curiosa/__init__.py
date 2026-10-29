"""Integration Curiosa : relie les recompenses du stream a la maison, en local."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .api import CuriosaApi
from .const import CONF_DEVELOPER, CONF_TOKEN, CONF_URL, DOMAIN
from .coordinator import CuriosaConfigEntry, CuriosaCoordinator
from .sanitize import AddressError, parse_site_address

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]


def _store(hass: HomeAssistant, entry: CuriosaConfigEntry) -> Store[dict[str, bool]]:
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
    local_enabled = bool(saved.get("enabled", True)) if isinstance(saved, dict) else True

    api = CuriosaApi(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN])
    coordinator = CuriosaCoordinator(hass, entry, api, store, local_enabled)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CuriosaConfigEntry) -> bool:
    """Arrete l'integration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: CuriosaConfigEntry) -> None:
    """Efface l'etat de l'interrupteur local."""
    await _store(hass, entry).async_remove()
