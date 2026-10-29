"""Capteurs : etat de la connexion et derniere action (cle seulement)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONNECTION_STATES,
    STATE_PAUSED_HERE,
    STATE_PAUSED_SITE,
    STATE_PROBLEM,
    STATE_READY,
    STATE_WAITING_STREAM,
)
from .coordinator import CuriosaConfigEntry, CuriosaCoordinator
from .entity import CuriosaEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CuriosaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Ajoute les capteurs."""
    coordinator = entry.runtime_data
    async_add_entities([CuriosaConnectionSensor(coordinator), CuriosaLastActionSensor(coordinator)])


def connection_state(coordinator: CuriosaCoordinator) -> str:
    """Etat resume de la liaison."""
    if not coordinator.last_update_success or coordinator.data is None:
        return STATE_PROBLEM
    if not coordinator.local_enabled:
        return STATE_PAUSED_HERE
    if not coordinator.data.site_enabled:
        return STATE_PAUSED_SITE
    if not coordinator.data.live:
        return STATE_WAITING_STREAM
    return STATE_READY


class CuriosaConnectionSensor(CuriosaEntity, SensorEntity):
    """Etat de la connexion avec Curiosa."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = CONNECTION_STATES

    def __init__(self, coordinator: CuriosaCoordinator) -> None:
        super().__init__(coordinator, "connection")

    @property
    def available(self) -> bool:
        """Toujours visible : c'est justement ce capteur qui dit s'il y a un souci."""
        return True

    @property
    def native_value(self) -> str:
        """Etat courant."""
        return connection_state(self.coordinator)


class CuriosaLastActionSensor(CuriosaEntity, SensorEntity):
    """Cle de la derniere action recue (pas de pseudo, pas de texte)."""

    def __init__(self, coordinator: CuriosaCoordinator) -> None:
        super().__init__(coordinator, "last_action")

    @property
    def available(self) -> bool:
        """Visible meme pendant une erreur : on garde la derniere cle."""
        return True

    @property
    def native_value(self) -> str | None:
        """Cle de l'action."""
        last = self.coordinator.last_action
        return last.key if last else None

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Resultat sous forme de codes fermes."""
        last = self.coordinator.last_action
        if last is None:
            return None
        attrs = {"status": last.status, "code": last.code}
        if last.test:
            attrs["test"] = "true"
        return attrs
