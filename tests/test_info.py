"""Informations des modules : lecture stricte, capteurs dynamiques, jamais renvoyees au site."""

from __future__ import annotations

import json
import math

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.curiosa.api import InfoItem, parse_info, parse_pull

SPONSOR = {
    "key": "sponsor-ticker.sponsors",
    "label": "Sponsor à l'écran",
    "value": "Camille Shop",
    "unit": None,
}
VIEWERS = {"key": "stats.viewers", "label": "Viewers", "value": 42, "unit": "viewers"}
ENTITY = "sensor.curiosa_sponsor_a_l_ecran"


def info_entities(hass, entry) -> list[er.RegistryEntry]:
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_info_"
    return [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if (e.unique_id or "").startswith(prefix)
    ]


async def refresh(hass, entry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


# --- lecture stricte -------------------------------------------------------------


def test_valid_info() -> None:
    assert parse_info([SPONSOR, VIEWERS]) == [
        InfoItem("sponsor-ticker.sponsors", "Sponsor à l'écran", "Camille Shop", None),
        InfoItem("stats.viewers", "Viewers", 42, "viewers"),
    ]
    assert parse_info([]) == []


def test_absent_or_wrong_shape_is_none() -> None:
    assert parse_pull({"enabled": True}).info is None  # ancien site
    assert parse_pull({"enabled": True, "info": []}).info == []
    for bad in ("x", 3, {"a": 1}, None, True, 1.5):
        assert parse_info(bad) is None
        assert parse_pull({"info": bad}).info is None


def test_invalid_keys_are_skipped() -> None:
    raw = [
        "texte",
        ["liste"],
        {"label": "Sans cle", "value": "x"},
        {"key": 5, "value": "x"},
        {"key": None, "value": "x"},
        {"key": "Majuscule", "value": "x"},
        {"key": " espace", "value": "x"},
        {"key": "espace ", "value": "x"},
        {"key": "fin\n", "value": "x"},
        {"key": "-debut", "value": "x"},
        {"key": ".debut", "value": "x"},
        {"key": "_debut", "value": "x"},
        {"key": "", "value": "x"},
        {"key": "a b", "value": "x"},
        {"key": "a/b", "value": "x"},
        {"key": "é", "value": "x"},
        {"key": "a" * 61, "value": "x"},
        {"key": "a" * 60, "value": "long"},
        {"key": "a", "value": "bon"},
        {"key": "0.x_y:z-w", "value": "bon aussi"},
    ]
    assert len(raw) == 20  # au-dela, tout est ignore (voir test_hard_limit_of_20)
    assert [i.key for i in parse_info(raw) or []] == ["a" * 60, "a", "0.x_y:z-w"]


def test_duplicates_first_wins() -> None:
    raw = [
        {"key": "a", "label": "Premier", "value": "1"},
        {"key": "a", "label": "Second", "value": "2"},
        {"key": "b", "value": "3"},
    ]
    assert parse_info(raw) == [InfoItem("a", "Premier", "1", None), InfoItem("b", "b", "3", None)]


def test_hard_limit_of_20() -> None:
    raw = [{"key": f"k{n}", "label": f"Info {n}", "value": n} for n in range(25)]
    items = parse_info(raw) or []
    assert len(items) == 20
    assert items[-1].key == "k19"


def test_values() -> None:
    def value(raw: object) -> object:
        [item] = parse_info([{"key": "a", "value": raw}]) or []
        return item.value

    assert value("texte") == "texte"
    assert value(7) == 7
    assert value(-3.5) == -3.5
    assert value(0) == 0
    assert value(999_999_999_999) == 999_999_999_999
    assert value(True) is True
    assert value(False) is False
    assert value(None) is None
    for bad in ({"a": 1}, ["x"], [], {}, "", "   ", "<b></b>", 1e12, -1e12, 10**15, math.inf):
        assert value(bad) is None, bad
    [missing] = parse_info([{"key": "a"}]) or []
    assert missing.value is None


def test_nan_and_infinity_in_json_are_dropped() -> None:
    payload = json.loads('{"info": [{"key": "a", "value": NaN}, {"key": "b", "value": Infinity}]}')
    assert [i.value for i in parse_pull(payload).info or []] == [None, None]


def test_text_is_cleaned_and_bounded() -> None:
    [item] = parse_info([{"key": "a", "label": "x" * 200, "value": "y" * 500}]) or []
    assert len(item.label) <= 60
    assert isinstance(item.value, str)
    assert len(item.value) <= 120
    [item] = (
        parse_info(
            [
                {
                    "key": "a",
                    "label": "<b>Titre</b>‮ https://evil.example/x \x00fin",
                    "value": "A\x00B\x07C <script>x</script> http://evil.example/p ​Z",
                }
            ]
        )
        or []
    )
    assert isinstance(item.value, str)
    for text in (item.label, item.value):
        assert "<" not in text
        assert "evil" not in text
        assert "‮" not in text
        assert "​" not in text
        assert "\x00" not in text
        assert "\x07" not in text
    assert item.label.startswith("Titre")
    assert "ABC" in item.value


def test_label_falls_back_to_key() -> None:
    for label in (None, "", "   ", 5, {"a": 1}, ["x"], "<b></b>"):
        [item] = parse_info([{"key": "a.b", "label": label, "value": 1}]) or []
        assert item.label == "a.b", label


def test_unit_only_for_numbers() -> None:
    def parse(value: object, unit: object) -> InfoItem:
        [item] = parse_info([{"key": "a", "value": value, "unit": unit}]) or []
        return item

    assert parse(21.5, "°C").unit == "°C"
    assert parse(0, "kg").unit == "kg"
    assert parse("texte", "kg").unit is None
    assert parse(True, "kg").unit is None
    assert parse(None, "kg").unit is None
    assert parse(5, None).unit is None
    assert parse(5, "").unit is None
    assert parse(5, 12).unit is None
    assert parse(5, {"a": 1}).unit is None
    assert len(parse(5, "u" * 50).unit or "") <= 12
    assert "<" not in (parse(5, "<b>kg</b> http://evil.example").unit or "")
    assert parse(5, "\x00‮").unit is None  # que du cache : plus rien


# --- capteurs --------------------------------------------------------------------


async def test_entity_created_on_first_appearance(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)
    assert info_entities(hass, entry) == []
    fake.info = [SPONSOR]
    await refresh(hass, entry)
    [item] = info_entities(hass, entry)
    assert item.unique_id == f"{entry.entry_id}_info_sponsor-ticker.sponsors"
    assert item.entity_id == ENTITY
    state = hass.states.get(ENTITY)
    assert state.state == "Camille Shop"
    assert state.attributes["friendly_name"] == "Curiosa Sponsor à l'écran"
    # meme appareil que les autres entites
    registry = er.async_get(hass)
    devices = {e.device_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    assert len(devices) == 1
    # une seconde interrogation ne recree rien
    await refresh(hass, entry)
    assert len(info_entities(hass, entry)) == 1


async def test_entity_present_at_startup(hass, fake, service_calls, entry_factory) -> None:
    fake.info = [SPONSOR, VIEWERS]
    entry = await entry_factory(fake)
    assert len(info_entities(hass, entry)) == 2
    assert hass.states.get(ENTITY).state == "Camille Shop"


async def test_value_updates_and_label_refreshes(hass, fake, service_calls, entry_factory) -> None:
    fake.info = [SPONSOR]
    entry = await entry_factory(fake)
    fake.info = [{**SPONSOR, "value": "Autre Boutique", "label": "Sponsor actuel"}]
    await refresh(hass, entry)
    state = hass.states.get(ENTITY)
    assert state.state == "Autre Boutique"
    assert state.attributes["friendly_name"] == "Curiosa Sponsor actuel"
    assert len(info_entities(hass, entry)) == 1


async def test_none_value_is_unknown_not_unavailable(
    hass, fake, service_calls, entry_factory
) -> None:
    fake.info = [{**SPONSOR, "value": None}]
    entry = await entry_factory(fake)
    assert hass.states.get(ENTITY).state == STATE_UNKNOWN
    fake.info = [SPONSOR]
    await refresh(hass, entry)
    assert hass.states.get(ENTITY).state == "Camille Shop"
    fake.info = [{"key": SPONSOR["key"], "label": SPONSOR["label"]}]  # valeur absente
    await refresh(hass, entry)
    assert hass.states.get(ENTITY).state == STATE_UNKNOWN


async def test_key_disappearing_is_unavailable(hass, fake, service_calls, entry_factory) -> None:
    fake.info = [SPONSOR, VIEWERS]
    entry = await entry_factory(fake)
    fake.info = [VIEWERS]
    await refresh(hass, entry)
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.curiosa_viewers").state == "42"
    fake.info = [SPONSOR, VIEWERS]  # il revient : meme entite, pas de doublon
    await refresh(hass, entry)
    assert hass.states.get(ENTITY).state == "Camille Shop"
    assert len(info_entities(hass, entry)) == 2


async def test_failed_update_is_unavailable_then_recovers(
    hass, fake, service_calls, entry_factory
) -> None:
    fake.info = [SPONSOR]
    entry = await entry_factory(fake)
    fake.pull_status = 503
    await refresh(hass, entry)
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE
    fake.pull_status = None
    await refresh(hass, entry)
    assert hass.states.get(ENTITY).state == "Camille Shop"


async def test_old_site_without_info(hass, fake, service_calls, entry_factory) -> None:
    entry = await entry_factory(fake)  # le faux site n'envoie pas "info"
    assert entry.runtime_data.data.info == ()
    assert info_entities(hass, entry) == []
    fake.enqueue("lumieres:rouge")
    await refresh(hass, entry)  # le reste marche comme avant
    assert fake.acks[-1]["code"] == "ok"
    assert entry.runtime_data.last_update_success is True
    fake.info = "n'importe quoi"  # champ de mauvaise forme : traite comme un ancien site
    await refresh(hass, entry)
    assert entry.runtime_data.last_update_success is True
    assert entry.runtime_data.data.info == ()
    assert info_entities(hass, entry) == []


async def test_site_back_to_old_version_makes_entities_unavailable(
    hass, fake, service_calls, entry_factory
) -> None:
    fake.info = [SPONSOR]
    entry = await entry_factory(fake)
    fake.info = None
    await refresh(hass, entry)
    assert entry.runtime_data.data.info == ()
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE


async def test_recreated_after_restart_from_registry(
    hass, fake, service_calls, entry_factory
) -> None:
    fake.info = [SPONSOR, VIEWERS]
    entry = await entry_factory(fake)
    assert hass.states.get(ENTITY).state == "Camille Shop"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    # Au redemarrage le site ne dit rien pour l'instant : les entites reviennent quand meme.
    fake.info = []
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert len(info_entities(hass, entry)) == 2
    state = hass.states.get(ENTITY)
    assert state.state == STATE_UNAVAILABLE
    assert state.attributes["friendly_name"] == "Curiosa Sponsor à l'écran"  # nom du registre
    # La cle revient : l'entite reprend sa valeur, sans doublon.
    fake.info = [SPONSOR]
    await refresh(hass, entry)
    assert hass.states.get(ENTITY).state == "Camille Shop"
    assert len(info_entities(hass, entry)) == 2


async def test_restart_with_old_site_keeps_entities(
    hass, fake, service_calls, entry_factory
) -> None:
    fake.info = [SPONSOR]
    entry = await entry_factory(fake)
    assert await hass.config_entries.async_unload(entry.entry_id)
    fake.info = None  # le site n'envoie plus le champ
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert len(info_entities(hass, entry)) == 1
    assert hass.states.get(ENTITY).state == STATE_UNAVAILABLE


async def test_registry_of_another_entry_or_bad_key_is_ignored(
    hass, fake, service_calls, entry_factory
) -> None:
    registry = er.async_get(hass)
    other = MockConfigEntry(domain="curiosa", title="autre", entry_id="other-entry")
    other.add_to_hass(hass)
    registry.async_get_or_create(
        "sensor", "curiosa", "other-entry_info_autre.cle", config_entry=other
    )
    entry = await entry_factory(fake)
    registry.async_get_or_create(
        "sensor", "curiosa", f"{entry.entry_id}_info_MAUVAISE CLE", config_entry=entry
    )
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.async_entity_ids("sensor") == [
        "sensor.curiosa_connection",
        "sensor.curiosa_last_action",
    ]


async def test_never_more_than_20_entities(hass, fake, service_calls, entry_factory) -> None:
    fake.info = [{"key": f"k{n}", "label": f"Info {n}", "value": n} for n in range(25)]
    entry = await entry_factory(fake)
    assert len(info_entities(hass, entry)) == 20
    # Des cles qui changent sans cesse ne font pas grossir la liste au-dela de 20.
    fake.info = [{"key": f"autre{n}", "label": f"Autre {n}", "value": n} for n in range(20)]
    await refresh(hass, entry)
    assert len(info_entities(hass, entry)) == 20


async def test_unit_and_value_types(hass, fake, service_calls, entry_factory) -> None:
    fake.info = [
        {"key": "temp", "label": "Temp", "value": 21.5, "unit": "°C"},
        {"key": "count", "label": "Count", "value": 7},
        {"key": "flag", "label": "Flag", "value": True, "unit": "x"},
        {"key": "off", "label": "Off", "value": False},
        {"key": "txt", "label": "Txt", "value": "salut", "unit": "kg"},
    ]
    await entry_factory(fake)
    temp = hass.states.get("sensor.curiosa_temp")
    assert temp.state == "21.5"
    assert temp.attributes["unit_of_measurement"] == "°C"
    count = hass.states.get("sensor.curiosa_count")
    assert count.state == "7"
    assert "unit_of_measurement" not in count.attributes
    assert hass.states.get("sensor.curiosa_flag").state == "true"
    assert hass.states.get("sensor.curiosa_off").state == "false"
    assert hass.states.get("sensor.curiosa_txt").state == "salut"
    for name in ("flag", "off", "txt"):
        assert "unit_of_measurement" not in hass.states.get(f"sensor.curiosa_{name}").attributes


async def test_other_entities_unchanged(hass, fake, service_calls, entry_factory) -> None:
    fake.info = [SPONSOR]
    entry = await entry_factory(fake)
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", "curiosa", f"{entry.entry_id}_connection")
    assert registry.async_get_entity_id("sensor", "curiosa", f"{entry.entry_id}_last_action")
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 6
