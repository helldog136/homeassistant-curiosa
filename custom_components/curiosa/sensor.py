"""Capteurs : etat de la connexion, derniere action (cle seulement), informations des modules."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import InfoItem
from .const import (
    CONNECTION_STATES,
    INFO_KEY_RE,
    INFO_MAX_ITEMS,
    INFO_UNIQUE_PREFIX,
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

    # Un capteur par information, cree des que la cle apparait. Au demarrage on retrouve
    # aussi, par le registre, celles deja connues, pour qu'elles ne disparaissent pas.
    # 20 capteurs d'information au plus par entree (les cles du moment passent d'abord).
    known: set[str] = set()
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_{INFO_UNIQUE_PREFIX}"
    remembered: dict[str, str | None] = {}
    for item in er.async_entries_for_config_entry(registry, entry.entry_id):
        unique_id = item.unique_id or ""
        key = unique_id[len(prefix) :]
        if item.domain == "sensor" and unique_id.startswith(prefix) and INFO_KEY_RE.fullmatch(key):
            remembered[key] = item.original_name

    @callback
    def add_new_info() -> None:
        data = coordinator.data
        new: list[CuriosaInfoSensor] = []
        for info in data.info if data else ():
            if info.key not in known and len(known) < INFO_MAX_ITEMS:
                known.add(info.key)
                new.append(CuriosaInfoSensor(coordinator, info.key, info.label))
        if new:
            async_add_entities(new)

    add_new_info()
    restored: list[CuriosaInfoSensor] = []
    for key, label in remembered.items():
        if key not in known and len(known) < INFO_MAX_ITEMS:
            known.add(key)
            restored.append(CuriosaInfoSensor(coordinator, key, label or key))
    if restored:
        async_add_entities(restored)
    entry.async_on_unload(coordinator.async_add_listener(add_new_info))


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


class CuriosaInfoSensor(CuriosaEntity, SensorEntity):
    """Une petite information fournie par un module du site (lecture seule)."""

    def __init__(self, coordinator: CuriosaCoordinator, key: str, label: str) -> None:
        super().__init__(coordinator, f"{INFO_UNIQUE_PREFIX}{key}")
        self.info_key = key
        # Le nom vient du libelle du site, pas d'une traduction.
        self._attr_translation_key = None
        self._attr_name = label

    @property
    def _item(self) -> InfoItem | None:
        data = self.coordinator.data
        if data is None:
            return None
        return next((item for item in data.info if item.key == self.info_key), None)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Le libelle peut changer d'une interrogation a l'autre."""
        item = self._item
        if item is not None:
            self._attr_name = item.label
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Indisponible si la derniere interrogation a echoue ou si la cle a disparu."""
        return super().available and self._item is not None

    @property
    def native_value(self) -> str | int | float | None:
        """Valeur du module ; un booleen devient 'true' ou 'false'."""
        item = self._item
        if item is None or item.value is None:
            return None
        if isinstance(item.value, bool):
            return "true" if item.value else "false"
        return item.value

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Unite, seulement pour un nombre."""
        item = self._item
        if item is None or isinstance(item.value, bool | str):
            return None
        return item.unit
