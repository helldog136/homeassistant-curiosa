"""Capteurs binaires : connecte, stream en direct."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Ajoute les capteurs binaires."""
    coordinator = entry.runtime_data
    async_add_entities([CuriosaConnectedSensor(coordinator), CuriosaLiveSensor(coordinator)])


class CuriosaConnectedSensor(CuriosaEntity, BinarySensorEntity):
    """Vrai quand Curiosa repond."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: CuriosaCoordinator) -> None:
        super().__init__(coordinator, "connected")

    @property
    def available(self) -> bool:
        """Toujours visible."""
        return True

    @property
    def is_on(self) -> bool:
        """Dernier appel reussi."""
        return self.coordinator.last_update_success


class CuriosaLiveSensor(CuriosaEntity, BinarySensorEntity):
    """Vrai quand le site dit que le stream est en direct."""

    def __init__(self, coordinator: CuriosaCoordinator) -> None:
        super().__init__(coordinator, "live")

    @property
    def is_on(self) -> bool | None:
        """Etat annonce par le site."""
        data = self.coordinator.data
        return data.live if data else None
