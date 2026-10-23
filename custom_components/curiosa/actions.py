"""Execution locale des actions : uniquement les scenes/scripts lies et le TTS choisi."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .api import Action
from .const import (
    BINDABLE_DOMAINS,
    CODE_ERROR,
    CODE_EXPIRED,
    CODE_OK,
    CODE_UNMAPPED,
    EXPIRY_TOLERANCE_SECONDS,
    KEY_RE,
    MAX_ACTION_LIFETIME_SECONDS,
    OPT_BINDINGS,
    OPT_ENTITY,
    OPT_KEY,
    OPT_TTS_ENGINE,
    OPT_TTS_LANGUAGE,
    OPT_TTS_PLAYER,
    OPT_TTS_SAY_VIEWER,
    OPT_TTS_VOLUME,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_IGNORED,
    TEXT_MAX_LENGTH,
    TTS_KEY_PREFIX,
    TTS_TIMEOUT_SECONDS,
)
from .sanitize import clean_text, clean_viewer

_LOGGER = logging.getLogger(__name__)

Result = tuple[str, str]  # (status, code) : listes fermees


def status_for(code: str) -> str:
    """Etat de l'accuse pour un code."""
    if code == CODE_OK:
        return STATUS_DONE
    if code == CODE_ERROR:
        return STATUS_FAILED
    return STATUS_IGNORED


def result_for(code: str) -> Result:
    """Couple (etat, code) pour un code."""
    return status_for(code), code


def is_expired(action: Action, now: datetime) -> bool:
    """Vrai si l'action est perimee.

    ``now`` est l'heure du site (serverTime + temps ecoule depuis la reponse),
    donc l'horloge de Home Assistant n'intervient pas. La tolerance couvre
    seulement la latence du reseau. Une action sans date, ou avec une duree
    de vie anormalement longue, est traitee avec la limite de securite.
    """
    tolerance = timedelta(seconds=EXPIRY_TOLERANCE_SECONDS)
    limits = []
    if action.expires_at is not None:
        limits.append(action.expires_at)
    if action.issued_at is not None:
        limits.append(action.issued_at + timedelta(seconds=MAX_ACTION_LIFETIME_SECONDS))
    if not limits:
        return True  # pas de date d'expiration : on ne joue pas
    return now > min(limits) + tolerance


def find_binding(options: Mapping[str, Any], key: str) -> str | None:
    """Entite liee a une cle, ou None."""
    for line in options.get(OPT_BINDINGS, []):
        if line.get(OPT_KEY) == key:
            entity_id = line.get(OPT_ENTITY)
            if isinstance(entity_id, str) and entity_id.split(".", 1)[0] in BINDABLE_DOMAINS:
                return entity_id
    return None


async def execute_action(
    hass: HomeAssistant,
    options: Mapping[str, Any],
    action: Action,
) -> Result:
    """Execute une action deja validee (active, non expiree, non repetee)."""
    key = action.key
    if not KEY_RE.fullmatch(key):
        return result_for(CODE_UNMAPPED)
    if key.startswith(TTS_KEY_PREFIX):
        return await _speak(hass, options, action)
    entity_id = find_binding(options, key)
    if entity_id is None:
        return result_for(CODE_UNMAPPED)
    domain = entity_id.split(".", 1)[0]
    if hass.states.get(entity_id) is None:
        _LOGGER.warning("Linked %s no longer exists", domain)
        return result_for(CODE_ERROR)
    try:
        await hass.services.async_call(domain, "turn_on", {"entity_id": entity_id}, blocking=True)
    except (HomeAssistantError, ValueError):
        _LOGGER.exception("Could not run the linked %s", domain)
        return result_for(CODE_ERROR)
    return result_for(CODE_OK)


def build_message(options: Mapping[str, Any], action: Action) -> str:
    """Texte final a lire : re-nettoye, avec le pseudo si l'option est active."""
    text = clean_text(action.text, TEXT_MAX_LENGTH)
    if text and options.get(OPT_TTS_SAY_VIEWER):
        viewer = clean_viewer(action.viewer)
        if viewer:
            text = clean_text(f"{viewer} : {text}", TEXT_MAX_LENGTH)
    return text


async def _speak(
    hass: HomeAssistant,
    options: Mapping[str, Any],
    action: Action,
) -> Result:
    player = options.get(OPT_TTS_PLAYER)
    engine = options.get(OPT_TTS_ENGINE)
    if not player or not engine:
        return result_for(CODE_UNMAPPED)
    if not str(player).startswith("media_player.") or not str(engine).startswith("tts."):
        return result_for(CODE_ERROR)
    message = build_message(options, action)
    if not message:
        return result_for(CODE_ERROR)
    if hass.states.get(player) is None or not hass.services.has_service("tts", "speak"):
        return result_for(CODE_ERROR)

    data: dict[str, Any] = {
        "entity_id": engine,
        "media_player_entity_id": player,
        "message": message,
        "cache": False,
    }
    if options.get(OPT_TTS_LANGUAGE):
        data["language"] = options[OPT_TTS_LANGUAGE]
    try:
        async with asyncio.timeout(TTS_TIMEOUT_SECONDS):
            volume = options.get(OPT_TTS_VOLUME)
            if volume is not None:
                # Seul autre appel possible : le volume du lecteur choisi.
                await hass.services.async_call(
                    "media_player",
                    "volume_set",
                    {"entity_id": player, "volume_level": min(max(float(volume), 0), 100) / 100},
                    blocking=True,
                )
            await hass.services.async_call("tts", "speak", data, blocking=True)
    except (HomeAssistantError, ValueError, TimeoutError):
        _LOGGER.exception("Could not speak the message")
        return result_for(CODE_ERROR)
    return result_for(CODE_OK)


__all__ = [
    "CODE_EXPIRED",
    "build_message",
    "execute_action",
    "find_binding",
    "is_expired",
    "result_for",
    "status_for",
]
