"""Base commune des entites Curiosa."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_URL, DOMAIN
from .coordinator import CuriosaCoordinator
from .sanitize import connector_page_url


class CuriosaEntity(CoordinatorEntity[CuriosaCoordinator]):
    """Entite rattachee a l'appareil Curiosa."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CuriosaCoordinator, name_key: str) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_translation_key = name_key
        self._attr_unique_id = f"{entry_id}_{name_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Curiosa",
            manufacturer="Helldog136",
            entry_type=DeviceEntryType.SERVICE,
            # Bouton « Visiter » : ouvre le site de la personne.
            configuration_url=connector_page_url(coordinator.config_entry.data[CONF_URL]),
        )
