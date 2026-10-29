"""Fixtures communes."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_socket
from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.curiosa.const import (
    CONF_DEVELOPER,
    CONF_INSTANCE,
    CONF_POLL_SECONDS,
    CONF_TOKEN,
    CONF_URL,
    DOMAIN,
    OPT_BINDINGS,
    OPT_ENTITY,
    OPT_KEY,
    OPT_TTS_ENGINE,
    OPT_TTS_PLAYER,
)

from .fake_curiosa import TOKEN, FakeCuriosa


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Active les integrations du dossier custom_components."""


@pytest.fixture
async def fake(socket_enabled: None) -> AsyncGenerator[FakeCuriosa]:
    """Faux site Curiosa sur 127.0.0.1."""
    pytest_socket.socket_allow_hosts(["127.0.0.1"], allow_unix_socket=True)
    site = FakeCuriosa()
    await site.start()
    yield site
    await site.stop()


@pytest.fixture
def service_calls(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Enregistre TOUS les appels de service + simule ceux dont on a besoin."""
    calls: list[dict[str, Any]] = []

    @callback
    def record(event: Event) -> None:
        calls.append(
            {
                "domain": event.data["domain"],
                "service": event.data["service"],
                "data": dict(event.data.get("service_data", {})),
            }
        )

    hass.bus.async_listen(EVENT_CALL_SERVICE, record)

    async def noop(call: ServiceCall) -> None:
        return None

    for domain, service in (
        ("scene", "turn_on"),
        ("script", "turn_on"),
        ("tts", "speak"),
        ("media_player", "volume_set"),
        ("light", "turn_on"),
        ("homeassistant", "restart"),
    ):
        hass.services.async_register(domain, service, noop)
    for entity_id in (
        "scene.rouge",
        "script.fete",
        "media_player.salon",
        "tts.moteur",
        "light.chambre",
        "scene.autre",
    ):
        hass.states.async_set(entity_id, "on")
    return calls


def make_entry(
    fake: FakeCuriosa, options: dict[str, Any] | None = None, token: str = TOKEN
) -> MockConfigEntry:
    """Entree deja appairee, en mode test (http://127.0.0.1)."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="127.0.0.1",
        unique_id=fake.api_url,
        data={
            CONF_URL: fake.api_url,
            CONF_TOKEN: token,
            CONF_INSTANCE: "home-assistant",
            CONF_POLL_SECONDS: 3,
            CONF_DEVELOPER: True,
        },
        options=options
        if options is not None
        else {
            OPT_BINDINGS: [
                {OPT_KEY: "lumieres:rouge", OPT_ENTITY: "scene.rouge"},
                {OPT_KEY: "fete", OPT_ENTITY: "script.fete"},
            ],
            OPT_TTS_PLAYER: "media_player.salon",
            OPT_TTS_ENGINE: "tts.moteur",
        },
    )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Installe l'entree."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
async def entry_factory(hass: HomeAssistant) -> AsyncGenerator[Any]:
    """Fabrique et nettoie les entrees (arrete les minuteurs)."""
    created: list[MockConfigEntry] = []

    async def factory(
        fake: FakeCuriosa, options: dict[str, Any] | None = None, token: str = TOKEN
    ) -> MockConfigEntry:
        entry = make_entry(fake, options, token)
        created.append(entry)
        await setup_entry(hass, entry)
        return entry

    yield factory
    for entry in created:
        if entry.state.recoverable or entry.state.name == "LOADED":
            await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
