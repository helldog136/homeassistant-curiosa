"""Fonctions pures : texte, cle, code, adresse."""

from __future__ import annotations

import pytest

from custom_components.curiosa.sanitize import (
    AddressError,
    clean_text,
    clean_viewer,
    normalize_code,
    normalize_key,
    parse_site_address,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Bonjour tout le monde", "Bonjour tout le monde"),
        ("<speak>Salut<break time='5s'/> toi</speak>", "Salut toi"),
        ("&lt;speak&gt;caché&lt;/speak&gt;", "caché"),
        ("va sur https://evil.example/x?y=1 vite", "va sur vite"),
        ("www.evil.com et evil.tv/abc", "et"),
        ("a\x00b\x07c​d‮e", "abcde"),
        ("ligne1\nligne2\t\tfin", "ligne1 ligne2 fin"),
        ("aaaaaaaaaa bbbbb", "aaaa bbbb"),
        ("ｆｕｌｌｗｉｄｔｈ", "fullwidth"),
        ("   ", ""),
    ],
)
def test_clean_text(raw: str, expected: str) -> None:
    assert clean_text(raw) == expected


def test_clean_text_not_a_string() -> None:
    assert clean_text(None) == ""
    assert clean_text(42) == ""


def test_clean_text_length_limit() -> None:
    assert len(clean_text("ab " * 500)) <= 300
    assert len(clean_text("x" * 1000, 50)) == 4  # repetitions reduites


def test_no_markup_survives() -> None:
    out = clean_text("<<script>>alert(1)<</script>> <speak>")
    assert "<" not in out
    assert ">" not in out


def test_clean_viewer_short() -> None:
    assert len(clean_viewer("<b>" + "z" * 100)) <= 25


def test_normalize_key() -> None:
    assert normalize_key("Lumieres:Rouge") == "lumieres:rouge"
    assert normalize_key("tts:lire") == "tts:lire"
    for bad in ("", ":x", "-x", "a b", "é", "x" * 41, None, 3, "a/b", "scene.rouge"):
        assert normalize_key(bad) is None
    assert normalize_key("x" * 40) == "x" * 40


def test_normalize_code() -> None:
    assert normalize_code("abcd-2345") == "ABCD2345"
    assert normalize_code(" abcd 2345 ") == "ABCD2345"
    for bad in ("", "ABC", "ABCD23456", "ABCD234!", None):
        assert normalize_code(bad) is None


def test_address_https_ok() -> None:
    addr = parse_site_address("https://mon-site.com")
    assert addr.base_url == "https://mon-site.com/m/home-assistant"
    assert addr.host == "mon-site.com"
    assert parse_site_address("mon-site.com/").base_url.startswith("https://mon-site.com/m/")


def test_address_keeps_explicit_path() -> None:
    addr = parse_site_address("https://mon-site.com/m/ha-maison/")
    assert addr.base_url == "https://mon-site.com/m/ha-maison"


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("http://mon-site.com", "https_required"),
        ("ftp://mon-site.com", "invalid_address"),
        ("https://user:pw@mon-site.com", "invalid_address"),
        ("https://mon-site.com/?a=1", "invalid_address"),
        ("", "invalid_address"),
        ("https://", "invalid_address"),
        ("https://localhost", "private_address"),
        ("https://192.168.1.20", "private_address"),
        ("https://10.0.0.5:8443", "private_address"),
        ("https://[::1]", "private_address"),
        ("https://box.local", "private_address"),
        ("http://192.168.1.20", "private_address"),
    ],
)
def test_address_refused(raw: str, code: str) -> None:
    with pytest.raises(AddressError) as err:
        parse_site_address(raw)
    assert err.value.code == code


def test_address_developer_mode() -> None:
    addr = parse_site_address("http://127.0.0.1:8080", developer=True)
    assert addr.base_url == "http://127.0.0.1:8080/m/home-assistant"
    assert parse_site_address("https://localhost", developer=True).host == "localhost"
    # http reste refuse pour un site public, meme en mode developpeur
    with pytest.raises(AddressError) as err:
        parse_site_address("http://mon-site.com", developer=True)
    assert err.value.code == "https_required"


def test_ancienne_forme_avec_ha_final_est_acceptee():
    addr = parse_site_address("https://mon-site.com/m/ha-maison/ha")
    assert addr.base_url == "https://mon-site.com/m/ha-maison"
