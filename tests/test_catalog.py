"""Catalogue des actions : lecture stricte, memoire, magasin, jamais renvoye au site."""

from __future__ import annotations

import json

from custom_components.curiosa.api import CatalogItem, parse_catalog, parse_pull

ASPI = {"key": "perso:lancer-l-aspirateur", "label": "Lancer l'aspirateur"}
ROUGE = {"key": "lumieres:rouge", "label": "Lumières : rouge"}


def test_valid_catalog() -> None:
    assert parse_catalog([ASPI, ROUGE]) == [
        CatalogItem("perso:lancer-l-aspirateur", "Lancer l'aspirateur"),
        CatalogItem("lumieres:rouge", "Lumières : rouge"),
    ]
    assert parse_catalog([]) == []


def test_absent_or_wrong_shape_is_none() -> None:
    assert parse_pull({"enabled": True}).catalog is None  # ancien site
    for bad in ("x", 3, {"a": 1}, None, True):
        assert parse_catalog(bad) is None


def test_label_is_cleaned_and_bounded() -> None:
    [item] = parse_catalog([{"key": "a", "label": "x" * 200}]) or []
    assert len(item.label) <= 60
    [item] = parse_catalog([{"key": "a", "label": "<b>Allume</b> https://evil.example/x ‮ tout"}])
    assert "<" not in item.label
    assert "evil" not in item.label
    assert "‮" not in item.label
    [item] = parse_catalog([{"key": "a", "label": "   "}])
    assert item.label == "a"  # libelle vide : on montre la cle


def test_invalid_entries_are_skipped() -> None:
    raw = [
        ASPI,
        "texte",
        None,
        {"key": "Majuscule", "label": "Non"},
        {"key": " espace", "label": "Non"},
        {"key": "-debut", "label": "Non"},
        {"key": "a" * 41, "label": "Non"},
        {"key": "ok:ok", "label": 5},
        {"key": 5, "label": "Non"},
        {"label": "Sans cle"},
        {"key": "bon", "label": "Bon"},
        {"key": "bon", "label": "Doublon"},
    ]
    assert [i.key for i in parse_catalog(raw) or []] == ["perso:lancer-l-aspirateur", "bon"]


def test_hard_limit_of_50() -> None:
    raw = [{"key": f"k{n}", "label": f"Action {n}"} for n in range(80)]
    assert len(parse_catalog(raw) or []) == 50


async def test_coordinator_keeps_and_stores_catalog(
    hass, fake, service_calls, entry_factory, hass_storage
) -> None:
    fake.catalog = [ASPI, ROUGE]
    entry = await entry_factory(fake)
    coordinator = entry.runtime_data
    assert [i.key for i in coordinator.catalog] == ["perso:lancer-l-aspirateur", "lumieres:rouge"]
    assert coordinator.label_for("lumieres:rouge") == "Lumières : rouge"
    assert coordinator.label_for("inconnue") == "inconnue"
    stored = hass_storage[f"curiosa.{entry.entry_id}"]["data"]
    assert stored["catalog"] == [ASPI, ROUGE]
    assert stored["enabled"] is True


async def test_old_site_without_catalog_still_works(
    hass, fake, service_calls, entry_factory, hass_storage
) -> None:
    entry = await entry_factory(fake)
    assert entry.runtime_data.catalog == []
    fake.enqueue("lumieres:rouge")
    await entry.runtime_data.async_refresh()
    assert fake.acks[-1]["code"] == "ok"
    assert "catalog" not in hass_storage.get(f"curiosa.{entry.entry_id}", {}).get("data", {})


async def test_catalog_follows_the_site(hass, fake, service_calls, entry_factory) -> None:
    fake.catalog = [ASPI]
    entry = await entry_factory(fake)
    fake.catalog = [ROUGE]
    await entry.runtime_data.async_refresh()
    assert [i.key for i in entry.runtime_data.catalog] == ["lumieres:rouge"]
    fake.catalog = None  # le site est revenu a une ancienne version
    await entry.runtime_data.async_refresh()
    assert entry.runtime_data.catalog == []


async def test_catalog_is_never_sent_back(hass, fake, service_calls, entry_factory) -> None:
    fake.catalog = [ASPI, ROUGE]
    entry = await entry_factory(fake)
    fake.enqueue("inconnue")
    fake.enqueue("tts:lire", "salut", viewer="Zoé")
    await entry.runtime_data.async_refresh()
    await entry.runtime_data.async_set_local_enabled(False)
    await entry.runtime_data.async_refresh()
    sent = [json.dumps([r["body"], r["query"], r["headers"]]).lower() for r in fake.requests]
    assert any("ack" in r["path"] for r in fake.requests)
    for blob in sent:
        assert "aspirateur" not in blob
        assert "perso:" not in blob
        assert "catalog" not in blob
        assert "lumières" not in blob
    for r in fake.requests:
        if r["path"].endswith("/ack"):
            assert set(r["body"]) == {"id", "status", "code"}
