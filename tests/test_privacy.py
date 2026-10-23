"""Rien de la maison ne part ; diagnostics et entites sans secret ni texte."""

from __future__ import annotations

import json

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from custom_components.curiosa.const import KEY_RE

from .fake_curiosa import TOKEN


async def run_scenario(hass, fake, entry) -> None:
    fake.enqueue("lumieres:rouge")
    fake.enqueue("tts:lire", "Salut Emma", viewer="Zoé")
    fake.enqueue("inconnue")
    fake.enqueue("fete", ttl=1, age=100)
    await entry.runtime_data.async_refresh()
    await entry.runtime_data.async_set_local_enabled(False)
    fake.enqueue("fete")
    await entry.runtime_data.async_refresh()
    fake.pull_status = 503
    await entry.runtime_data.async_refresh()


async def test_requests_contain_no_house_data(hass, fake, service_calls, entry_factory) -> None:
    hass.config.location_name = "Maison secrete de Emma"
    entry = await entry_factory(fake)
    await run_scenario(hass, fake, entry)
    assert len(fake.requests) >= 6

    allowed_ack = {"id", "status", "code"}
    for request in fake.requests:
        assert set(request["query"]) <= {"cursor", "limit"}
        assert set(request["headers"]) <= {
            "Accept",
            "Accept-Encoding",
            "Authorization",
            "Host",
            "User-Agent",
            "Content-Length",
            "Content-Type",
        }
        assert request["headers"]["Authorization"] == f"Bearer {TOKEN}"
        if request["path"].endswith("/ack"):
            body = request["body"]
            assert set(body) == allowed_ack
            assert body["status"] in {"done", "failed", "ignored"}
            assert body["code"] in {"ok", "unmapped", "disabled", "expired", "error"}
        elif request["path"].endswith("/pull"):
            assert request["body"] is None
        blob = json.dumps(request, ensure_ascii=False).lower()
        for forbidden in (
            "scene.",
            "script.",
            "media_player",
            "light.",
            "tts.moteur",
            "secrete",
            "emma",
            "salon",
            "latitude",
            "zoé",
            "salut",
        ):
            assert forbidden not in blob, forbidden


async def test_pair_request_has_no_house_data(hass, fake) -> None:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from custom_components.curiosa.api import CuriosaApi

    hass.config.location_name = "Maison secrete"
    api = CuriosaApi(async_get_clientsession(hass), fake.api_url)
    await api.pair("ABCD2345", "Home Assistant")
    assert fake.requests[0]["body"] == {"code": "ABCD2345", "name": "Home Assistant"}
    assert fake.requests[0]["query"] == {}


async def test_diagnostics_have_no_secret(
    hass, hass_client, fake, service_calls, entry_factory
) -> None:
    entry = await entry_factory(fake)
    await run_scenario(hass, fake, entry)
    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    blob = json.dumps(diag)
    assert TOKEN not in blob
    assert "127.0.0.1" not in blob
    assert str(fake.url.rsplit(":", 1)[1]) not in blob
    assert "scene.rouge" not in blob  # seulement le type (scene/script)
    assert "Salut" not in blob
    assert "Zoé" not in blob
    assert diag["bindings"][0] == {"key": "lumieres:rouge", "target_domain": "scene"}
    assert diag["tts_configured"] is True


async def test_entities_never_hold_viewer_or_text(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    await run_scenario(hass, fake, entry)
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(entities) == 5
    for item in entities:
        state = hass.states.get(item.entity_id)
        blob = json.dumps([state.state, dict(state.attributes)], ensure_ascii=False)
        for forbidden in ("Salut", "Emma", "Zoé", TOKEN, "127.0.0.1"):
            assert forbidden not in blob, (item.entity_id, forbidden)
    last = hass.states.get(
        registry.async_get_entity_id("sensor", "curiosa", f"{entry.entry_id}_last_action")
    )
    assert KEY_RE.fullmatch(last.state)
    assert last.state == "fete"
    assert set(last.attributes) - {"friendly_name", "icon"} == {"status", "code"}
