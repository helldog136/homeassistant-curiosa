"""Coordinateur : interroge Curiosa, execute, accuse reception."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .actions import Result, execute_action, is_expired, result_for
from .api import (
    Action,
    CuriosaApi,
    CuriosaAuthError,
    CuriosaConnectionError,
    CuriosaError,
    CuriosaHttpError,
)
from .const import (
    CODE_DISABLED,
    CODE_EXPIRED,
    CONF_POLL_SECONDS,
    DEDUP_MAX,
    DEFAULT_POLL_SECONDS,
    DOMAIN,
    KEY_RE,
    MAX_BACKOFF_SECONDS,
    MAX_RETRY_AFTER_SECONDS,
    MIN_POLL_SECONDS,
    OFF_POLL_SECONDS,
    PULL_LIMIT,
)

_LOGGER = logging.getLogger(__name__)

type CuriosaConfigEntry = ConfigEntry[CuriosaCoordinator]


@dataclass(frozen=True)
class LastAction:
    """Derniere action : la CLE seulement (jamais de pseudo ni de texte)."""

    key: str
    status: str
    code: str
    test: bool = False


@dataclass(frozen=True)
class CuriosaData:
    """Ce que le site a dit lors de la derniere interrogation."""

    site_enabled: bool
    live: bool
    last_action: LastAction | None = None


class CuriosaCoordinator(DataUpdateCoordinator[CuriosaData]):
    """Interrogation reguliere de Curiosa.

    Rythme : ``pollSeconds`` (3 s par defaut, 2 s minimum). En cas d'erreur le
    delai double jusqu'a 60 s, et ``Retry-After`` est respecte.

    Quand l'interrupteur local est coupe, on continue d'interroger, mais
    rarement (30 s) : on n'execute rien et on acquitte ``ignored/disabled``
    ce qui arrive, pour que le site rembourse vite plutot que d'attendre
    l'expiration, et pour que Curiosa voie que Home Assistant est la.
    """

    config_entry: CuriosaConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CuriosaConfigEntry,
        api: CuriosaApi,
        store: Store[dict[str, bool]],
        local_enabled: bool,
    ) -> None:
        poll = entry.data.get(CONF_POLL_SECONDS, DEFAULT_POLL_SECONDS)
        self._poll = max(MIN_POLL_SECONDS, int(poll))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=self._poll),
        )
        self.api = api
        self._store = store
        self.local_enabled = local_enabled
        self.last_action: LastAction | None = None
        self._cursor: int | None = None
        self._failures = 0
        self._seen: OrderedDict[str, Result] = OrderedDict()
        self._server_ref: tuple[datetime, float] | None = None
        self.set_interval()

    # --- horloge du site -------------------------------------------------
    def site_now(self) -> datetime:
        """Heure du site : serverTime + temps ecoule (repli : horloge locale)."""
        if self._server_ref is None:
            return datetime.now(UTC)
        server_time, mono = self._server_ref
        return server_time + timedelta(seconds=time.monotonic() - mono)

    # --- rythme -----------------------------------------------------------
    @property
    def base_interval(self) -> int:
        """Delai normal entre deux interrogations."""
        return self._poll if self.local_enabled else OFF_POLL_SECONDS

    def set_interval(self, retry_after: int | None = None) -> None:
        """Calcule le prochain delai (repli exponentiel apres erreur)."""
        if self._failures == 0:
            delay = self.base_interval
        else:
            delay = min(MAX_BACKOFF_SECONDS, self.base_interval * 2**self._failures)
        if retry_after:
            delay = max(delay, min(retry_after, MAX_RETRY_AFTER_SECONDS))
        self.update_interval = timedelta(seconds=delay)

    async def async_set_local_enabled(self, enabled: bool) -> None:
        """Interrupteur local : conserve sur disque, effet immediat."""
        self.local_enabled = enabled
        await self._store.async_save({"enabled": enabled})
        self.set_interval()
        self.async_update_listeners()
        if enabled:
            await self.async_request_refresh()

    # --- interrogation ----------------------------------------------------
    async def _async_update_data(self) -> CuriosaData:
        try:
            result = await self.api.pull(self._cursor)
        except CuriosaAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="reauth_needed"
            ) from err
        except CuriosaHttpError as err:
            self._failures += 1
            self.set_interval(err.retry_after)
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="site_error",
                translation_placeholders={"status": str(err.status)},
            ) from err
        except CuriosaConnectionError as err:
            self._failures += 1
            self.set_interval()
            raise UpdateFailed(translation_domain=DOMAIN, translation_key="cannot_reach") from err

        self._failures = 0
        if result.server_time is not None:
            self._server_ref = (result.server_time, time.monotonic())
        if result.cursor is not None:
            self._cursor = result.cursor

        for action in result.actions[:PULL_LIMIT]:
            await self._handle(action)

        self.set_interval()
        return CuriosaData(result.enabled, result.live, self.last_action)

    async def _handle(self, action: Action) -> None:
        """Traite une action : doublon, coupe-circuit, expiration, execution, accuse."""
        known = self._seen.get(action.id)
        if known is not None:
            # Deja traitee (l'accuse a peut-etre ete perdu) : on le renvoie, sans rejouer.
            await self._ack(action.id, known)
            return

        if not self.local_enabled:
            outcome = result_for(CODE_DISABLED)
        elif is_expired(action, self.site_now()):
            outcome = result_for(CODE_EXPIRED)
        else:
            outcome = await execute_action(self.hass, self.config_entry.options, action)

        if action.test:
            _LOGGER.info("Test action from Curiosa: %s", outcome[1])
        self._seen[action.id] = outcome
        while len(self._seen) > DEDUP_MAX:
            self._seen.popitem(last=False)
        key = action.key if KEY_RE.fullmatch(action.key) else "invalid"
        self.last_action = LastAction(key, outcome[0], outcome[1], action.test)
        await self._ack(action.id, outcome)

    async def _ack(self, action_id: str, outcome: Result) -> None:
        try:
            await self.api.ack(action_id, outcome[0], outcome[1])
        except CuriosaAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="reauth_needed"
            ) from err
        except CuriosaError as err:
            # Le site renverra l'action ; on renverra le meme accuse sans rien rejouer.
            _LOGGER.debug("Acknowledgement not delivered (%s)", type(err).__name__)
