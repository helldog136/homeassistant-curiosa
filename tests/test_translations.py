"""Traductions completes et identiques en structure (FR = EN)."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent / "custom_components" / "curiosa"


def load(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def paths(node, prefix=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from paths(value, f"{prefix}/{key}")
    else:
        yield prefix, node


def test_fr_en_same_keys_and_no_empty_text() -> None:
    en = dict(paths(load("translations/en.json")))
    fr = dict(paths(load("translations/fr.json")))
    assert set(en) == set(fr)
    assert all(isinstance(v, str) and v.strip() for v in fr.values())
    assert load("strings.json") == load("translations/en.json")


def test_placeholders_match() -> None:
    en = dict(paths(load("translations/en.json")))
    fr = dict(paths(load("translations/fr.json")))
    for key, text in en.items():
        assert set(re.findall(r"{(\w+)}", text)) == set(re.findall(r"{(\w+)}", fr[key])), key


def test_every_error_used_in_code_is_translated() -> None:
    source = "".join(
        (ROOT / name).read_text(encoding="utf-8")
        for name in ("config_flow.py", "sanitize.py", "api.py")
    )
    used = set(
        re.findall(
            r'"((?:invalid|https|private|code|too|not|cannot|reserved|duplicate|engine)_\w+|unknown)"',
            source,
        )
    )
    en = load("translations/en.json")
    known = set(en["config"]["error"]) | set(en["options"]["error"])
    missing = {u for u in used if u not in known and u not in {"invalid_code_format"}}
    assert not missing, missing


def test_no_jargon_for_the_user() -> None:
    text = (
        json.dumps(load("translations/fr.json")).lower()
        + json.dumps(load("translations/en.json")).lower()
    )
    for word in ("webhook", "eventsub", "token", "jeton", "oauth", "payload", "api "):
        assert word not in text, word


def test_every_options_step_and_menu_entry_is_translated() -> None:
    source = (ROOT / "config_flow.py").read_text(encoding="utf-8")
    steps = set(
        re.findall(r"async def async_step_(\w+)", source.split("class CuriosaOptionsFlow")[1])
    )
    for lang in ("en", "fr"):
        options = load(f"translations/{lang}.json")["options"]["step"]
        assert steps <= set(options), (lang, steps - set(options))
        menu = set(options["init"]["menu_options"])
        assert {"bindings", "add_binding", "remove_binding", "tts"} == menu


def test_issues_are_translated_like_the_code_uses_them() -> None:
    source = (ROOT / "coordinator.py").read_text(encoding="utf-8")
    keys = set(re.findall(r'"(unmapped_\w+)"', source))
    assert keys == {"unmapped_action", "unmapped_voice"}
    for lang in ("en", "fr"):
        issues = load(f"translations/{lang}.json")["issues"]
        assert keys <= set(issues)
        for key in keys:
            assert issues[key]["title"].strip()
        fix = issues["unmapped_action"]["fix_flow"]
        assert "init" in fix["step"] and {"invalid_target", "too_many"} <= set(fix["error"])
        assert "not_ready" in fix["abort"]


def test_flow_placeholders_are_provided() -> None:
    """Chaque {nom} des ecrans de liaison est fourni par le code (sinon texte brut)."""
    source = (ROOT / "config_flow.py").read_text(encoding="utf-8") + (
        ROOT / "repairs.py"
    ).read_text(encoding="utf-8")
    provided = {"site", "action", "state"}
    for name in provided:
        assert f'"{name}"' in source
    for lang in ("en", "fr"):
        data = load(f"translations/{lang}.json")
        text = json.dumps([data["options"]["step"], data["issues"]])
        assert set(re.findall(r"{(\w+)}", text)) <= provided | {"example"}


def test_texts_for_emma_use_plain_words() -> None:
    """Pas de jargon sur les nouveaux ecrans (le mot « entite » reste cote developpeur)."""
    for lang, banned in (("fr", ("entité", "binding", "slug", "clé")), ("en", ("entity", "slug"))):
        data = load(f"translations/{lang}.json")
        values = [v for _, v in paths({"s": data["options"]["step"], "i": data["issues"]})]
        text = " ".join(values).lower()
        for word in banned:
            assert word not in text, (lang, word)
