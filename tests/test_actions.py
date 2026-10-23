"""Liaison, execution, TTS, interrupteur local, doublons, expiration."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.curiosa.const import (
    DEDUP_MAX,
    OPT_BINDINGS,
    OPT_ENTITY,
    OPT_KEY,
    OPT_TTS_ENGINE,
    OPT_TTS_LANGUAGE,
    OPT_TTS_PLAYER,
    OPT_TTS_SAY_VIEWER,
    OPT_TTS_VOLUME,
)

from .conftest import make_entry, setup_entry
from .fake_curiosa import FakeCuriosa


async def refresh(entry: Any) -> None:
    await entry.runtime_data.async_refresh()


def acks(fake: FakeCuriosa) -> list[tuple[str, str, str]]:
    return [(a["id"], a["status"], a["code"]) for a in fake.acks]


def calls_to(service_calls: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(c["domain"], c["service"]) for c in service_calls]


async def test_bound_scene_and_script(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    a = fake.enqueue("lumieres:rouge")
    b = fake.enqueue("fete")
    await refresh(entry)
    assert [(c["domain"], c["service"], c["data"]["entity_id"]) for c in service_calls] == [
        ("scene", "turn_on", "scene.rouge"),
        ("script", "turn_on", "script.fete"),
    ]
    assert acks(fake) == [(a, "done", "ok"), (b, "done", "ok")]


async def test_unmapped_key_is_acked_ignored(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    a = fake.enqueue("lumieres:bleu")
    await refresh(entry)
    assert service_calls == []
    assert acks(fake) == [(a, "ignored", "unmapped")]


async def test_only_linked_entities_are_called(hass, fake, service_calls, entry_factory) -> None:
    """Meme une ligne trafiquee vers une lumiere ne declenche rien."""
    options = {
        OPT_BINDINGS: [
            {OPT_KEY: "evil", OPT_ENTITY: "light.chambre"},
            {OPT_KEY: "evil2", OPT_ENTITY: "homeassistant.restart"},
            {OPT_KEY: "ok", OPT_ENTITY: "scene.rouge"},
        ]
    }
    entry = await entry_factory(fake, options)
    for key in ("evil", "evil2", "light.chambre", "scene.autre", "../x", "UPPER", ""):
        fake.enqueue(key)
    await refresh(entry)
    assert service_calls == []
    assert {c for (_, _, c) in acks(fake)} == {"unmapped"}
    fake.enqueue("ok")
    await refresh(entry)
    assert calls_to(service_calls) == [("scene", "turn_on")]
    assert service_calls[0]["data"] == {"entity_id": "scene.rouge"}


async def test_missing_entity_gives_error_code(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    hass.states.async_remove("scene.rouge")
    a = fake.enqueue("lumieres:rouge")
    await refresh(entry)
    assert service_calls == []
    assert acks(fake) == [(a, "failed", "error")]


async def test_tts_cleaned_single_service(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    a = fake.enqueue(
        "tts:lire", "<speak>Coucou</speak> https://evil.example/x\x00 <break time='9s'/> les amis"
    )
    await refresh(entry)
    assert calls_to(service_calls) == [("tts", "speak")]
    assert service_calls[0]["data"] == {
        "entity_id": "tts.moteur",
        "media_player_entity_id": "media_player.salon",
        "message": "Coucou les amis",
        "cache": False,
    }
    assert acks(fake) == [(a, "done", "ok")]


async def test_tts_length_cap_and_language_volume_viewer(
    hass, fake, service_calls, entry_factory
) -> None:
    options = {
        OPT_BINDINGS: [],
        OPT_TTS_PLAYER: "media_player.salon",
        OPT_TTS_ENGINE: "tts.moteur",
        OPT_TTS_LANGUAGE: "fr-FR",
        OPT_TTS_VOLUME: 40.0,
        OPT_TTS_SAY_VIEWER: True,
    }
    entry = await entry_factory(fake, options)
    fake.enqueue("tts:lire", "mot " * 200, viewer="<b>Zoé</b>")
    await refresh(entry)
    # Seuls deux appels possibles : le volume du lecteur choisi, puis la voix.
    assert calls_to(service_calls) == [("media_player", "volume_set"), ("tts", "speak")]
    assert service_calls[0]["data"] == {"entity_id": "media_player.salon", "volume_level": 0.4}
    speak = service_calls[1]["data"]
    assert speak["language"] == "fr-FR"
    assert len(speak["message"]) <= 300
    assert speak["message"].startswith("Zoé : mot mot")


async def test_tts_not_configured_is_unmapped(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake, {OPT_BINDINGS: []})
    a = fake.enqueue("tts:lire", "salut")
    await refresh(entry)
    assert service_calls == []
    assert acks(fake) == [(a, "ignored", "unmapped")]


async def test_tts_empty_after_cleaning_is_error(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    a = fake.enqueue("tts:lire", "<speak></speak> https://x.example")
    b = fake.enqueue("tts:lire", "")
    await refresh(entry)
    assert service_calls == []
    assert acks(fake) == [(a, "failed", "error"), (b, "failed", "error")]


async def test_text_never_reaches_other_keys(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    fake.enqueue("lumieres:rouge", "dis quelque chose", viewer="x")
    await refresh(entry)
    assert calls_to(service_calls) == [("scene", "turn_on")]
    assert service_calls[0]["data"] == {"entity_id": "scene.rouge"}


async def test_local_switch_off_ignores_everything(
    hass: HomeAssistant, fake, service_calls, entry_factory, hass_storage
) -> None:
    entry = await entry_factory(fake)
    registry = er.async_get(hass)
    switch_id = registry.async_get_entity_id("switch", "curiosa", f"{entry.entry_id}_enabled")
    assert switch_id
    assert hass.states.get(switch_id).state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch_id}, blocking=True)
    assert hass.states.get(switch_id).state == "off"
    assert hass_storage[f"curiosa.{entry.entry_id}"]["data"] == {"enabled": False}
    service_calls.clear()

    a = fake.enqueue("lumieres:rouge")
    b = fake.enqueue("tts:lire", "salut")
    await refresh(entry)
    assert service_calls == []
    assert acks(fake) == [(a, "ignored", "disabled"), (b, "ignored", "disabled")]
    # Rare mais pas muet : une interrogation toutes les 30 s.
    assert entry.runtime_data.update_interval == timedelta(seconds=30)

    await hass.services.async_call("switch", "turn_on", {"entity_id": switch_id}, blocking=True)
    assert entry.runtime_data.local_enabled is True
    assert entry.runtime_data.update_interval == timedelta(seconds=3)


async def test_local_switch_state_survives_restart(
    hass, fake, service_calls, entry_factory, hass_storage
) -> None:
    entry = make_entry(fake)
    hass_storage[f"curiosa.{entry.entry_id}"] = {
        "version": 1,
        "key": f"curiosa.{entry.entry_id}",
        "data": {"enabled": False},
    }
    fake.enqueue("lumieres:rouge")
    await setup_entry(hass, entry)  # la premiere interrogation a lieu deja coupee
    assert service_calls == []
    assert acks(fake)[0][1:] == ("ignored", "disabled")
    await hass.config_entries.async_unload(entry.entry_id)


async def test_duplicate_ids_run_once(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    fake.enqueue("lumieres:rouge", action_id="same-1")
    await refresh(entry)
    # Le site renvoie la meme action (accuse perdu) : on re-accuse, sans rejouer.
    fake.queue.append(
        {
            **{"id": "same-1", "key": "lumieres:rouge", "text": "", "viewer": ""},
            "issuedAt": None,
            "expiresAt": None,
        }
    )
    await refresh(entry)
    assert calls_to(service_calls) == [("scene", "turn_on")]
    assert [a[0] for a in acks(fake)] == ["same-1", "same-1"]


async def test_lost_ack_is_resent_without_rerun(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    fake.ack_status = 503
    fake.enqueue("fete", action_id="lost-1")
    await refresh(entry)
    assert len(service_calls) == 1
    assert entry.runtime_data.last_update_success is True
    fake.ack_status = 200
    await refresh(entry)
    assert len(service_calls) == 1
    assert acks(fake) == [("lost-1", "done", "ok")]


async def test_dedup_memory_is_bounded(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    coordinator = entry.runtime_data
    for i in range(DEDUP_MAX + 30):
        fake.enqueue("lumieres:rouge", action_id=f"id-{i}")
        if i % 10 == 9:
            await refresh(entry)
    await refresh(entry)
    assert len(coordinator._seen) == DEDUP_MAX
    assert "id-0" not in coordinator._seen


async def test_expired_action_is_not_run(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    a = fake.enqueue("lumieres:rouge", ttl=60, age=120)
    await refresh(entry)
    assert service_calls == []
    assert acks(fake) == [(a, "ignored", "expired")]


async def test_expiry_tolerance_five_seconds(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    ok = fake.enqueue("lumieres:rouge", ttl=60, age=63)  # perimee depuis 3 s : toleree
    late = fake.enqueue("fete", ttl=60, age=70)  # perimee depuis 10 s : refusee
    await refresh(entry)
    assert acks(fake) == [(ok, "done", "ok"), (late, "ignored", "expired")]


async def test_expiry_uses_site_clock_not_local(hass, fake, service_calls, entry_factory) -> None:
    """Horloge du site en avance de 1 h : la duree de vie reste jugee cote site."""
    fake.server_time_offset = timedelta(hours=1)
    entry = await entry_factory(fake)
    ok = fake.enqueue("lumieres:rouge", ttl=60, age=1)
    old = fake.enqueue("fete", ttl=60, age=90)
    await refresh(entry)
    assert acks(fake) == [(ok, "done", "ok"), (old, "ignored", "expired")]


async def test_action_without_dates_or_too_long_lived_is_not_run(
    hass, fake, service_calls, entry_factory
) -> None:
    entry = await entry_factory(fake)
    fake.queue.append({"id": "nodate", "key": "fete", "text": "", "viewer": ""})
    fake.enqueue("lumieres:rouge", ttl=86400, age=1000)  # emise il y a 1000 s, ttl absurde
    await refresh(entry)
    assert service_calls == []
    assert {c for (_, _, c) in acks(fake)} == {"expired"}


async def test_test_action_runs_normally_and_is_marked(hass, fake, service_calls, entry_factory):
    entry = await entry_factory(fake)
    a = fake.enqueue("lumieres:rouge")
    fake.queue[-1]["test"] = True
    await refresh(entry)
    assert calls_to(service_calls) == [("scene", "turn_on")]  # execute pour de vrai
    assert acks(fake) == [(a, "done", "ok")]  # accuse inchange
    assert set(fake.acks[0]) == {"id", "status", "code"}
    last = entry.runtime_data.last_action
    assert last.test is True
    state = hass.states.get("sensor.curiosa_last_action")
    assert state.attributes["test"] == "true"
    fake.enqueue("fete")
    await refresh(entry)
    assert "test" not in hass.states.get("sensor.curiosa_last_action").attributes
