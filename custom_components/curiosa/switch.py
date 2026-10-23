"""Interrupteur local : le coupe-circuit cote Home Assistant."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import CuriosaConfigEntry, CuriosaCoordinator
from .entity import CuriosaEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CuriosaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Ajoute l'interrupteur."""
    async_add_entities([CuriosaEnabledSwitch(entry.runtime_data)])


class CuriosaEnabledSwitch(CuriosaEntity, SwitchEntity):
    """Coupe, ici, tout ce que Curiosa pourrait lancer."""

    def __init__(self, coordinator: CuriosaCoordinator) -> None:
        super().__init__(coordinator, "enabled")

    @property
    def available(self) -> bool:
        """Toujours utilisable, meme si le site ne repond pas."""
        return True

    @property
    def is_on(self) -> bool:
        """Vrai si Curiosa peut lancer des actions."""
        return self.coordinator.local_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Reactive."""
        await self.coordinator.async_set_local_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Coupe : plus rien n'est execute."""
        await self.coordinator.async_set_local_enabled(False)
