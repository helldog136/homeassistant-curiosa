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
