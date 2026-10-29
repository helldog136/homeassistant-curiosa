"""Diagnostics : sans jeton, sans adresse complete, sans nom d'entite."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_DEVELOPER,
    OPT_BINDINGS,
    OPT_ENTITY,
    OPT_KEY,
    OPT_TTS_ENGINE,
    OPT_TTS_PLAYER,
    VERSION,
)
from .coordinator import CuriosaConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CuriosaConfigEntry
) -> dict[str, Any]:
    """Renvoie un resume sur, partageable tel quel."""
    coordinator = entry.runtime_data
    data = coordinator.data
    bindings = entry.options.get(OPT_BINDINGS, [])
    return {
        "version": VERSION,
        "developer_mode": bool(entry.data.get(CONF_DEVELOPER)),
        "address": "https://<masquee>",
        "token": "<masque>",
        "local_switch_on": coordinator.local_enabled,
        "last_update_success": coordinator.last_update_success,
        "site_enabled": data.site_enabled if data else None,
        "live": data.live if data else None,
        "poll_seconds_now": coordinator.update_interval.total_seconds()
        if coordinator.update_interval
        else None,
        "bindings": [
            {
                "key": line.get(OPT_KEY),
                "target_domain": str(line.get(OPT_ENTITY, "")).split(".", 1)[0],
            }
            for line in bindings
        ],
        "tts_configured": bool(
            entry.options.get(OPT_TTS_PLAYER) and entry.options.get(OPT_TTS_ENGINE)
        ),
        "last_action": (
            {"key": coordinator.last_action.key, "code": coordinator.last_action.code}
            if coordinator.last_action
            else None
        ),
    }
