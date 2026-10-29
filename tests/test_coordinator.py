"""Interrogation : rythme, repli, erreurs, jeton refuse, interrupteurs."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.curiosa.const import MAX_BACKOFF_SECONDS


def seconds(entry) -> float:
    return entry.runtime_data.update_interval.total_seconds()


def state_of(hass: HomeAssistant, entry, domain: str, key: str) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(domain, "curiosa", f"{entry.entry_id}_{key}")
    assert entity_id
    return hass.states.get(entity_id).state


async def test_normal_rhythm_and_query(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    assert seconds(entry) == 3
    first = fake.requests[0]
    assert first["method"] == "GET"
    assert first["query"] == {"limit": "10"}  # pas de curseur au demarrage
    assert first["headers"]["Authorization"].startswith("Bearer ")
    await entry.runtime_data.async_refresh()
    assert fake.requests[-1]["query"] == {"limit": "10", "cursor": "1"}  # curseur du site renvoye


async def test_exponential_backoff_to_60_and_reset(
    hass, fake, service_calls, entry_factory
) -> None:
    entry = await entry_factory(fake)
    fake.pull_status = 503
    seen = []
    for _ in range(7):
        await entry.runtime_data.async_refresh()
        seen.append(seconds(entry))
    assert seen == [6, 12, 24, 48, 60, 60, 60]
    assert max(seen) == MAX_BACKOFF_SECONDS
    assert state_of(hass, entry, "sensor", "connection") == "problem"
    assert state_of(hass, entry, "binary_sensor", "connected") == "off"
    fake.pull_status = None
    await entry.runtime_data.async_refresh()
    assert seconds(entry) == 3
    assert state_of(hass, entry, "sensor", "connection") == "ready"
    assert state_of(hass, entry, "binary_sensor", "connected") == "on"


async def test_429_respects_retry_after(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    fake.pull_status = 429
    fake.retry_after = "20"
    await entry.runtime_data.async_refresh()
    assert seconds(entry) == 20
    fake.retry_after = "9999"
    await entry.runtime_data.async_refresh()
    assert seconds(entry) == 300  # borne de securite
    fake.retry_after = "soon"  # valeur illisible : repli normal
    await entry.runtime_data.async_refresh()
    assert seconds(entry) == 24  # 3 echecs de suite : 3 x 2^3


async def test_unreachable_site_backs_off(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    await fake.stop()
    await entry.runtime_data.async_refresh()
    assert entry.runtime_data.last_update_success is False
    assert seconds(entry) == 6


async def test_401_starts_reauth_and_stops_polling(
    hass, fake, service_calls, entry_factory
) -> None:
    entry = await entry_factory(fake)
    fake.valid_token = "other-token"
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler("curiosa")
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]
    count = len(fake.requests)
    assert entry.runtime_data.last_update_success is False
    # le coordinateur ne reprogramme plus d'appel : pas de boucle
    assert entry.runtime_data._unsub_refresh is None
    assert len(fake.requests) == count


async def test_401_at_setup_asks_for_pairing(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake, token="revoked-token")
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler("curiosa")
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_server_disabled_runs_nothing(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    fake.enabled = False
    fake.enqueue("lumieres:rouge")
    await entry.runtime_data.async_refresh()
    assert service_calls == []
    assert fake.acks == []
    assert state_of(hass, entry, "sensor", "connection") == "paused_site"
    fake.enabled = True
    fake.live = False
    await entry.runtime_data.async_refresh()
    assert state_of(hass, entry, "sensor", "connection") == "waiting_stream"
    assert state_of(hass, entry, "binary_sensor", "live") == "off"
    fake.live = True
    await entry.runtime_data.async_refresh()
    assert state_of(hass, entry, "sensor", "connection") == "ready"


async def test_local_off_state_and_backoff_base(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    await entry.runtime_data.async_set_local_enabled(False)
    assert state_of(hass, entry, "sensor", "connection") == "paused_here"
    fake.pull_status = 503
    await entry.runtime_data.async_refresh()
    assert seconds(entry) == 60  # 30 s x 2, plafonne a 60 s
    await hass.async_block_till_done()


async def test_scheduled_refresh_uses_interval(hass, fake, service_calls, entry_factory) -> None:
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    await entry_factory(fake)
    before = len(fake.requests)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=5))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(fake.requests) > before
