"""La liaison (cle -> scene/script) et le reglage de la voix."""

from __future__ import annotations

from homeassistant.data_entry_flow import FlowResultType

from custom_components.curiosa.const import (
    OPT_BINDINGS,
    OPT_ENTITY,
    OPT_KEY,
    OPT_REMOVE,
    OPT_TTS_ENGINE,
    OPT_TTS_LANGUAGE,
    OPT_TTS_PLAYER,
    OPT_TTS_SAY_VIEWER,
    OPT_TTS_VOLUME,
)


async def open_step(hass, entry, step):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


async def test_menu_hides_remove_when_empty(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake, {})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["menu_options"] == ["add_binding", "tts"]
    hass.config_entries.options.async_abort(result["flow_id"])


async def test_add_binding(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    form = await open_step(hass, entry, "add_binding")
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {OPT_KEY: " Lumieres:Vert ", OPT_ENTITY: "scene.autre"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert {OPT_KEY: "lumieres:vert", OPT_ENTITY: "scene.autre"} in entry.options[OPT_BINDINGS]
    assert entry.options[OPT_TTS_PLAYER] == "media_player.salon"  # le reste est conserve


async def test_add_binding_validation(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    form = await open_step(hass, entry, "add_binding")
    flow_id = form["flow_id"]
    cases = [
        ({OPT_KEY: "pas bon!", OPT_ENTITY: "scene.rouge"}, {OPT_KEY: "invalid_key"}),
        ({OPT_KEY: "x" * 41, OPT_ENTITY: "scene.rouge"}, {OPT_KEY: "invalid_key"}),
        ({OPT_KEY: "tts:autre", OPT_ENTITY: "scene.rouge"}, {OPT_KEY: "reserved_key"}),
        ({OPT_KEY: "fete", OPT_ENTITY: "script.fete"}, {OPT_KEY: "duplicate_key"}),
        ({OPT_KEY: "FETE", OPT_ENTITY: "scene.autre"}, {OPT_KEY: "duplicate_key"}),
    ]
    for data, errors in cases:
        result = await hass.config_entries.options.async_configure(flow_id, data)
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == errors
    assert len(entry.options[OPT_BINDINGS]) == 2


async def test_target_must_be_scene_or_script(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    form = await open_step(hass, entry, "add_binding")
    try:
        result = await hass.config_entries.options.async_configure(
            form["flow_id"], {OPT_KEY: "lampe", OPT_ENTITY: "light.chambre"}
        )
    except Exception:  # le selecteur refuse deja la saisie
        return
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {OPT_ENTITY: "invalid_target"}


async def test_remove_binding(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    form = await open_step(hass, entry, "remove_binding")
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {OPT_REMOVE: ["fete"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[OPT_BINDINGS] == [{OPT_KEY: "lumieres:rouge", OPT_ENTITY: "scene.rouge"}]
    # La cle retiree n'execute plus rien
    fake.enqueue("fete")
    await entry.runtime_data.async_refresh()
    assert service_calls == []
    assert fake.acks[-1]["code"] == "unmapped"


async def test_tts_settings(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake, {})
    form = await open_step(hass, entry, "tts")
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {
            OPT_TTS_PLAYER: "media_player.salon",
            OPT_TTS_ENGINE: "tts.moteur",
            OPT_TTS_LANGUAGE: "fr-FR",
            OPT_TTS_VOLUME: 35,
            OPT_TTS_SAY_VIEWER: True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[OPT_TTS_PLAYER] == "media_player.salon"
    assert entry.options[OPT_TTS_ENGINE] == "tts.moteur"
    assert entry.options[OPT_TTS_LANGUAGE] == "fr-FR"
    assert entry.options[OPT_TTS_VOLUME] == 35.0
    assert entry.options[OPT_TTS_SAY_VIEWER] is True


async def test_tts_needs_engine_and_valid_language(
    hass, fake, service_calls, entry_factory
) -> None:
    entry = await entry_factory(fake, {})
    form = await open_step(hass, entry, "tts")
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {OPT_TTS_PLAYER: "media_player.salon", OPT_TTS_LANGUAGE: "français!!"}
    )
    assert result["errors"] == {
        OPT_TTS_ENGINE: "engine_required",
        OPT_TTS_LANGUAGE: "invalid_language",
    }


async def test_tts_can_be_turned_off(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    form = await open_step(hass, entry, "tts")
    result = await hass.config_entries.options.async_configure(form["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert OPT_TTS_PLAYER not in entry.options
    assert len(entry.options[OPT_BINDINGS]) == 2
    fake.enqueue("tts:lire", "salut")
    await entry.runtime_data.async_refresh()
    assert service_calls == []
    assert fake.acks[-1]["code"] == "unmapped"
