"""Constantes de l'integration Curiosa."""

from __future__ import annotations

import re

DOMAIN = "curiosa"
VERSION = "0.1.0"

# Donnees de l'entree de configuration
CONF_URL = "url"
CONF_TOKEN = "token"
CONF_CODE = "code"
CONF_DEVELOPER = "developer_mode"
CONF_INSTANCE = "instance"
CONF_POLL_SECONDS = "poll_seconds"

# Options (la liaison)
OPT_BINDINGS = "bindings"
OPT_KEY = "key"
OPT_ENTITY = "entity_id"
OPT_TTS_PLAYER = "tts_player"
OPT_TTS_ENGINE = "tts_engine"
OPT_TTS_LANGUAGE = "tts_language"
OPT_TTS_VOLUME = "tts_volume"
OPT_TTS_SAY_VIEWER = "tts_say_viewer"
OPT_REMOVE = "remove"

BINDABLE_DOMAINS = ("scene", "script")
TTS_KEY_PREFIX = "tts:"
MAX_BINDINGS = 100

# Cle d'action : meme regle que cote Curiosa
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9:_-]{0,39}$")
CODE_RE = re.compile(r"^[A-Z0-9]{8}$")
ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")

# Nom envoye a l'appairage : fixe, jamais le nom de la maison
DEVICE_NAME = "Home Assistant"
DEFAULT_INSTANCE = "home-assistant"

# Interrogation
DEFAULT_POLL_SECONDS = 3
MIN_POLL_SECONDS = 2
MAX_BACKOFF_SECONDS = 60
MAX_RETRY_AFTER_SECONDS = 300
OFF_POLL_SECONDS = 30
PULL_LIMIT = 10
REQUEST_TIMEOUT = 10
MAX_RESPONSE_BYTES = 65536

# Securite
TEXT_MAX_LENGTH = 300
VIEWER_MAX_LENGTH = 25
DEDUP_MAX = 200
EXPIRY_TOLERANCE_SECONDS = 5
MAX_ACTION_LIFETIME_SECONDS = 300
TTS_TIMEOUT_SECONDS = 30

# Etats de l'accuse (listes fermees)
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_IGNORED = "ignored"
CODE_OK = "ok"
CODE_UNMAPPED = "unmapped"
CODE_DISABLED = "disabled"
CODE_EXPIRED = "expired"
CODE_ERROR = "error"

# Etats affiches par le capteur de connexion
STATE_READY = "ready"
STATE_WAITING_STREAM = "waiting_stream"
STATE_PAUSED_SITE = "paused_site"
STATE_PAUSED_HERE = "paused_here"
STATE_PROBLEM = "problem"
CONNECTION_STATES = [
    STATE_READY,
    STATE_WAITING_STREAM,
    STATE_PAUSED_SITE,
    STATE_PAUSED_HERE,
    STATE_PROBLEM,
]
