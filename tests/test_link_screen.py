"""Ecran « Tes actions » : liste par noms, etat, choix d'un script, migration, avance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr

from custom_components.curiosa.const import (
    DOMAIN,
    OPT_ACTION,
    OPT_BINDINGS,
    OPT_ENTITY,
    OPT_KEY,
)

ASPI = {"key": "perso:lancer-l-aspirateur", "label": "Lancer l'aspirateur"}
ROUGE = {"key": "lumieres:rouge", "label": "Lumières : rouge"}
VOIX = {"key": "tts:lire", "label": "Lire le message à voix haute"}


async def open_menu(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    return result


async def go(hass, flow_id, step):
    return await hass.config_entries.options.async_configure(flow_id, {"next_step_id": step})


def choices(form) -> dict[str, str]:
    """valeur -> libelle du selecteur d'actions."""
    for marker, validator in form["data_schema"].schema.items():
        if marker == OPT_ACTION:
            return {o["value"]: o["label"] for o in validator.config["options"]}
    raise AssertionError("pas de liste d'actions")


@pytest.fixture
def lang_fr(hass) -> None:
    hass.config.language = "fr"


async def test_list_shows_names_and_state(
    hass, fake, service_calls, entry_factory, lang_fr
) -> None:
    fake.catalog = [ASPI, ROUGE, VOIX]
    entry = await entry_factory(fake)
    menu = await open_menu(hass, entry)
    assert menu["menu_options"] == ["bindings", "tts"]  # pas de saisie a la main en mode simple
    assert menu["description_placeholders"]["site"] == fake.url
    form = await go(hass, menu["flow_id"], "bindings")
    assert form["type"] is FlowResultType.FORM
    assert form["description_placeholders"]["site"] == fake.url
    assert choices(form) == {
        "perso:lancer-l-aspirateur": "Lancer l'aspirateur : pas encore reliée",
        "lumieres:rouge": "Lumières : rouge : reliée à scene.rouge",
        "tts:lire": "Lire le message à voix haute : voix réglée",
        "fete": "fete (ancienne liaison) : reliée à script.fete",
    }
    hass.config_entries.options.async_abort(menu["flow_id"])


async def test_state_in_english_and_voice_missing(hass, fake, service_calls, entry_factory) -> None:
    hass.config.language = "en"
    fake.catalog = [ASPI, VOIX]
    entry = await entry_factory(fake, {})
    menu = await open_menu(hass, entry)
    form = await go(hass, menu["flow_id"], "bindings")
    assert choices(form) == {
        "perso:lancer-l-aspirateur": "Lancer l'aspirateur : not linked yet",
        "tts:lire": 'Lire le message à voix haute : voice not set up yet (see "Voice")',
    }
    hass.config_entries.options.async_abort(menu["flow_id"])


async def test_link_an_action_by_name(hass, fake, service_calls, entry_factory, lang_fr) -> None:
    fake.catalog = [ASPI, ROUGE]
    entry = await entry_factory(fake)
    menu = await open_menu(hass, entry)
    flow_id = menu["flow_id"]
    await go(hass, flow_id, "bindings")
    link = await hass.config_entries.options.async_configure(
        flow_id, {OPT_ACTION: "perso:lancer-l-aspirateur"}
    )
    assert link["step_id"] == "link"
    assert link["description_placeholders"] == {
        "action": "Lancer l'aspirateur",
        "state": "pas encore reliée",
    }
    back = await hass.config_entries.options.async_configure(flow_id, {OPT_ENTITY: "script.fete"})
    assert back["step_id"] == "bindings"  # retour a la liste
    assert choices(back)["perso:lancer-l-aspirateur"].endswith("reliée à script.fete")
    assert {OPT_KEY: "perso:lancer-l-aspirateur", OPT_ENTITY: "script.fete"} in entry.options[
        OPT_BINDINGS
    ]
    done = await hass.config_entries.options.async_configure(flow_id, {})
    assert done["type"] is FlowResultType.CREATE_ENTRY
    # Et l'action marche pour de vrai
    fake.enqueue("perso:lancer-l-aspirateur")
    await entry.runtime_data.async_refresh()
    assert fake.acks[-1]["code"] == "ok"
    assert service_calls[-1]["domain"] == "script"


async def test_empty_choice_unlinks(hass, fake, service_calls, entry_factory) -> None:
    fake.catalog = [ROUGE]
    entry = await entry_factory(fake)
    menu = await open_menu(hass, entry)
    flow_id = menu["flow_id"]
    await go(hass, flow_id, "bindings")
    await hass.config_entries.options.async_configure(flow_id, {OPT_ACTION: "lumieres:rouge"})
    back = await hass.config_entries.options.async_configure(flow_id, {})
    assert back["step_id"] == "bindings"
    assert all(line[OPT_KEY] != "lumieres:rouge" for line in entry.options[OPT_BINDINGS])
    hass.config_entries.options.async_abort(flow_id)


async def test_selector_is_limited_to_script_and_scene(
    hass, fake, service_calls, entry_factory
) -> None:
    fake.catalog = [ASPI]
    entry = await entry_factory(fake)
    menu = await open_menu(hass, entry)
    flow_id = menu["flow_id"]
    await go(hass, flow_id, "bindings")
    link = await hass.config_entries.options.async_configure(
        flow_id, {OPT_ACTION: "perso:lancer-l-aspirateur"}
    )
    [(_, validator)] = list(link["data_schema"].schema.items())
    assert validator.config["domain"] == ["scene", "script"]
    with pytest.raises(Exception):  # noqa: B017 - le selecteur refuse une lampe
        await hass.config_entries.options.async_configure(flow_id, {OPT_ENTITY: "light.chambre"})
    assert len(entry.options[OPT_BINDINGS]) == 2
    hass.config_entries.options.async_abort(flow_id)


async def test_voice_action_goes_to_voice_screen(hass, fake, service_calls, entry_factory) -> None:
    fake.catalog = [VOIX]
    entry = await entry_factory(fake)
    menu = await open_menu(hass, entry)
    flow_id = menu["flow_id"]
    await go(hass, flow_id, "bindings")
    form = await hass.config_entries.options.async_configure(flow_id, {OPT_ACTION: "tts:lire"})
    assert form["step_id"] == "tts"
    hass.config_entries.options.async_abort(flow_id)


async def test_advanced_hand_entry_only_in_advanced_mode_or_old_site(
    hass, fake, service_calls, entry_factory
) -> None:
    fake.catalog = [ASPI]
    entry = await entry_factory(fake)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "add_binding" not in result["menu_options"]
    hass.config_entries.options.async_abort(result["flow_id"])
    result = await hass.config_entries.options.async_init(
        entry.entry_id, context={"show_advanced_options": True}
    )
    assert result["menu_options"] == ["bindings", "add_binding", "remove_binding", "tts"]
    form = await go(hass, result["flow_id"], "add_binding")
    done = await hass.config_entries.options.async_configure(
        form["flow_id"], {OPT_KEY: "Mon:Mot", OPT_ENTITY: "scene.autre"}
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert {OPT_KEY: "mon:mot", OPT_ENTITY: "scene.autre"} in entry.options[OPT_BINDINGS]


async def test_old_site_keeps_the_manual_screens(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)  # pas de catalogue
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["menu_options"] == ["bindings", "add_binding", "remove_binding", "tts"]
    form = await go(hass, result["flow_id"], "bindings")
    # Les liaisons existantes restent visibles et modifiables par leur mot d'action
    assert set(choices(form)) == {"lumieres:rouge", "fete"}
    hass.config_entries.options.async_abort(result["flow_id"])


async def test_orphan_links_stay_visible(hass, fake, service_calls, entry_factory, lang_fr) -> None:
    fake.catalog = [ASPI]
    entry = await entry_factory(fake)
    menu = await open_menu(hass, entry)
    form = await go(hass, menu["flow_id"], "bindings")
    assert choices(form)["fete"] == "fete (ancienne liaison) : reliée à script.fete"
    hass.config_entries.options.async_abort(menu["flow_id"])


async def test_works_from_store_when_site_is_down(
    hass, fake, service_calls, entry_factory, hass_storage
) -> None:
    """Apres redemarrage, sans reponse du site, le catalogue garde sur disque sert."""
    fake.catalog = [ASPI, ROUGE]
    entry = await entry_factory(fake)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    form = await go(hass, result["flow_id"], "bindings")
    assert set(choices(form)) == {"perso:lancer-l-aspirateur", "lumieres:rouge", "fete"}
    hass.config_entries.options.async_abort(result["flow_id"])


# --- migration depuis la 0.1.0 --------------------------------------------------------


async def test_migration_from_0_1_0_storage(
    hass, fake, service_calls, entry_factory, hass_storage
) -> None:
    """Magasin et options exactement comme en 0.1.0 : rien ne se perd, rien a faire."""
    from .conftest import make_entry, setup_entry

    entry = make_entry(fake)  # options 0.1.0 : liste de {key, entity_id}
    hass_storage[f"curiosa.{entry.entry_id}"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"curiosa.{entry.entry_id}",
        "data": {"enabled": False},  # fichier 0.1.0 : pas de catalogue
    }
    fake.catalog = [ASPI, ROUGE]
    await setup_entry(hass, entry)
    try:
        coordinator = entry.runtime_data
        assert coordinator.local_enabled is False  # l'interrupteur est conserve
        assert entry.options[OPT_BINDINGS] == [
            {OPT_KEY: "lumieres:rouge", OPT_ENTITY: "scene.rouge"},
            {OPT_KEY: "fete", OPT_ENTITY: "script.fete"},
        ]
        # Les anciennes liaisons apparaissent avec le nom du catalogue
        menu = await open_menu(hass, entry)
        form = await go(hass, menu["flow_id"], "bindings")
        assert choices(form)["lumieres:rouge"].endswith("scene.rouge")
        assert choices(form)["fete"].endswith("script.fete")
        hass.config_entries.options.async_abort(menu["flow_id"])
        # Le fichier garde l'interrupteur et gagne le catalogue
        saved = hass_storage[f"curiosa.{entry.entry_id}"]["data"]
        assert saved["enabled"] is False
        assert [x["key"] for x in saved["catalog"]] == [ASPI["key"], ROUGE["key"]]
        await coordinator.async_set_local_enabled(True)
        fake.enqueue("lumieres:rouge")
        await coordinator.async_refresh()
        assert fake.acks[-1]["code"] == "ok"
    finally:
        await hass.config_entries.async_unload(entry.entry_id)


# --- bouton « Visiter » ---------------------------------------------------------------


async def test_device_has_visit_link_to_the_connector_page(
    hass, fake, service_calls, entry_factory
) -> None:
    entry = await entry_factory(fake)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    assert device.configuration_url == f"{fake.url}/admin/modules/home-assistant"


def test_site_root_strips_instance() -> None:
    from custom_components.curiosa.sanitize import site_root

    assert site_root("https://mon-site.com/m/home-assistant") == "https://mon-site.com"
    assert (
        site_root("https://mon-site.com/sous/dossier/m/ha1") == "https://mon-site.com/sous/dossier"
    )
    assert site_root("http://127.0.0.1:8123/m/x") == "http://127.0.0.1:8123"


def test_no_url_in_translations() -> None:
    root = Path(__file__).parent.parent / "custom_components" / "curiosa"
    for name in ("strings.json", "translations/fr.json", "translations/en.json"):
        data = json.loads((root / name).read_text(encoding="utf-8"))
        # Nouveaux ecrans : le site s'affiche par un champ de texte, jamais ecrit en dur.
        text = json.dumps([data["options"]["step"], data["issues"]])
        assert "http://" not in text and "https://" not in text, name


def test_connector_page_url_points_to_module_page() -> None:
    from custom_components.curiosa.sanitize import connector_page_url

    assert (
        connector_page_url("https://mon-site.com/m/home-assistant")
        == "https://mon-site.com/admin/modules/home-assistant"
    )
    assert (
        connector_page_url("https://mon-site.com/sous/dossier/m/ha1")
        == "https://mon-site.com/sous/dossier/admin/modules/home-assistant"
    )
