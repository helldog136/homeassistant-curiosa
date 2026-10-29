"""Les liaisons « action -> script ou scene » : lecture et modification des options.

Le format est celui de la version 0.1.0 (liste de ``{key, entity_id}``) : rien a migrer,
les liaisons existantes continuent de marcher telles quelles.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .const import BINDABLE_DOMAINS, OPT_BINDINGS, OPT_ENTITY, OPT_KEY


def binding_lines(options: Mapping[str, Any]) -> list[dict[str, str]]:
    """Liaisons valides (copie) ; une ligne abimee est ignoree."""
    raw = options.get(OPT_BINDINGS, [])
    if not isinstance(raw, list):
        return []
    return [
        {OPT_KEY: line[OPT_KEY], OPT_ENTITY: line[OPT_ENTITY]}
        for line in raw
        if isinstance(line, Mapping)
        and isinstance(line.get(OPT_KEY), str)
        and isinstance(line.get(OPT_ENTITY), str)
    ]


def is_bindable(entity_id: object) -> bool:
    """Vrai pour un script ou une scene."""
    return isinstance(entity_id, str) and entity_id.split(".", 1)[0] in BINDABLE_DOMAINS


def linked_entity(options: Mapping[str, Any], key: str) -> str | None:
    """Script ou scene relie a une action, ou None."""
    for line in binding_lines(options):
        if line[OPT_KEY] == key and is_bindable(line[OPT_ENTITY]):
            return line[OPT_ENTITY]
    return None


def with_binding(options: Mapping[str, Any], key: str, entity_id: str | None) -> dict[str, Any]:
    """Options avec la liaison de ``key`` posee (ou retiree si ``entity_id`` est None)."""
    lines = [line for line in binding_lines(options) if line[OPT_KEY] != key]
    if entity_id:
        lines.append({OPT_KEY: key, OPT_ENTITY: entity_id})
    return {**options, OPT_BINDINGS: lines}
