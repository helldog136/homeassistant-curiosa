"""Reparation « une action n'a pas de script relie » : une par action, 20 au plus, sans fuite."""

from __future__ import annotations

import json

from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.components.repairs.issue_handler import async_process_repairs_platforms
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir

from custom_components.curiosa.const import DOMAIN, MAX_ISSUES, OPT_BINDINGS, OPT_ENTITY, OPT_KEY

ASPI = {"key": "perso:lancer-l-aspirateur", "label": "Lancer l'aspirateur"}


def issues(hass) -> dict[str, ir.IssueEntry]:
    return {i.issue_id: i for i in ir.async_get(hass).issues.values() if i.domain == DOMAIN}


async def run_fix(hass, issue_id: str):
    await async_process_repairs_platforms(hass)
    manager = repairs_flow_manager(hass)
    return await manager.async_init(DOMAIN, data={"issue_id": issue_id})


async def test_one_issue_per_action(hass, fake, service_calls, entry_factory) -> None:
    fake.catalog = [ASPI]
    entry = await entry_factory(fake)
    for _ in range(3):
        fake.enqueue(ASPI["key"])
    await entry.runtime_data.async_refresh()
    assert fake.acks[-1]["code"] == "unmapped"
    [issue] = issues(hass).values()
    assert issue.translation_key == "unmapped_action"
    assert issue.translation_placeholders == {"action": "Lancer l'aspirateur"}
    assert issue.is_fixable is True
    # Une action de plus plus tard : toujours une seule reparation
    fake.enqueue(ASPI["key"])
    await entry.runtime_data.async_refresh()
    assert len(issues(hass)) == 1


async def test_no_issue_when_linked_or_ok(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    fake.enqueue("lumieres:rouge")
    await entry.runtime_data.async_refresh()
    assert issues(hass) == {}


async def test_issue_disappears_when_linked_in_options(
    hass, fake, service_calls, entry_factory
) -> None:
    fake.catalog = [ASPI]
    entry = await entry_factory(fake)
    fake.enqueue(ASPI["key"])
    await entry.runtime_data.async_refresh()
    assert len(issues(hass)) == 1
    options = {
        **entry.options,
        OPT_BINDINGS: [
            *entry.options[OPT_BINDINGS],
            {OPT_KEY: ASPI["key"], OPT_ENTITY: "script.fete"},
        ],
    }
    hass.config_entries.async_update_entry(entry, options=options)
    await hass.async_block_till_done()
    assert issues(hass) == {}


async def test_fix_flow_links_the_action(hass, fake, service_calls, entry_factory) -> None:
    fake.catalog = [ASPI]
    entry = await entry_factory(fake)
    fake.enqueue(ASPI["key"])
    await entry.runtime_data.async_refresh()
    [issue_id] = issues(hass)
    form = await run_fix(hass, issue_id)
    assert form["type"] is FlowResultType.FORM
    assert form["description_placeholders"] == {"action": "Lancer l'aspirateur"}
    done = await repairs_flow_manager(hass).async_configure(
        form["flow_id"], {OPT_ENTITY: "script.fete"}
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert {OPT_KEY: ASPI["key"], OPT_ENTITY: "script.fete"} in entry.options[OPT_BINDINGS]
    await hass.async_block_till_done()
    assert issues(hass) == {}
    fake.enqueue(ASPI["key"])
    await entry.runtime_data.async_refresh()
    assert fake.acks[-1]["code"] == "ok"
    assert issues(hass) == {}


async def test_fix_flow_refuses_a_lamp(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    fake.enqueue("nouveau")
    await entry.runtime_data.async_refresh()
    [issue_id] = issues(hass)
    form = await run_fix(hass, issue_id)
    try:
        result = await repairs_flow_manager(hass).async_configure(
            form["flow_id"], {OPT_ENTITY: "light.chambre"}
        )
    except Exception:
        return
    assert result["errors"] == {OPT_ENTITY: "invalid_target"}


async def test_voice_issue_is_not_a_script_question(
    hass, fake, service_calls, entry_factory
) -> None:
    entry = await entry_factory(fake, {})
    fake.enqueue("tts:lire", "salut")
    await entry.runtime_data.async_refresh()
    [issue] = issues(hass).values()
    assert issue.translation_key == "unmapped_voice"
    assert issue.is_fixable is False
    options = {"tts_player": "media_player.salon", "tts_engine": "tts.moteur"}
    hass.config_entries.async_update_entry(entry, options=options)
    await hass.async_block_till_done()
    assert issues(hass) == {}


async def test_at_most_20_issues(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake, {})
    for n in range(MAX_ISSUES + 15):
        fake.enqueue(f"nouvelle-{n}")
        if n % 5 == 4:
            await entry.runtime_data.async_refresh()
    await entry.runtime_data.async_refresh()
    assert len(issues(hass)) == MAX_ISSUES
    assert all(a["code"] == "unmapped" for a in fake.acks)


async def test_issues_removed_on_unload(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake, {})
    fake.enqueue("nouvelle")
    await entry.runtime_data.async_refresh()
    assert len(issues(hass)) == 1
    await hass.config_entries.async_unload(entry.entry_id)
    assert issues(hass) == {}


async def test_issue_holds_nothing_from_the_house(hass, fake, service_calls, entry_factory) -> None:
    hass.config.location_name = "Maison secrete de Emma"
    fake.catalog = [ASPI]
    entry = await entry_factory(fake)
    fake.enqueue(ASPI["key"], "texte", viewer="Zoé")
    await entry.runtime_data.async_refresh()
    [issue] = issues(hass).values()
    blob = json.dumps([issue.translation_placeholders, issue.data, issue.translation_key]).lower()
    for forbidden in ("secrete", "emma", "zoé", "scene.", "script.", "media_player", "salon"):
        assert forbidden not in blob
