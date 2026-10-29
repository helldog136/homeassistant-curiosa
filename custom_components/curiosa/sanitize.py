"""Fonctions pures : nettoyage du texte, cles, adresse du site.

Aucune dependance a Home Assistant : tout est facile a tester.
"""

from __future__ import annotations

import html
import ipaddress
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

from .const import (
    CODE_RE,
    DEFAULT_INSTANCE,
    KEY_RE,
    TEXT_MAX_LENGTH,
    VIEWER_MAX_LENGTH,
)

_TAG_RE = re.compile(r"<[^<>]{0,500}>")
_URL_RE = re.compile(
    r"(?i)(?:\b(?:https?|ftp|file)://\S*|\bwww\.\S*|"
    r"\b[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|be|fr|io|tv|gg|me|ly|co|app|dev|xyz|info|eu|"
    r"ru|cn|tk|ml|ga|cf|gq|top|site|online|link|live)\b(?:/\S*)?)"
)
_REPEAT_RE = re.compile(r"(.)\1{4,}", re.DOTALL)
_SPACES_RE = re.compile(r"\s+")
_DROPPED_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Cn"}
_SPACE_CATEGORIES = {"Zl", "Zp", "Zs"}


def normalize_key(raw: object) -> str | None:
    """Renvoie la cle en minuscules si elle est valide, sinon None."""
    if not isinstance(raw, str):
        return None
    key = raw.strip().lower()
    return key if KEY_RE.fullmatch(key) else None


def normalize_code(raw: object) -> str | None:
    """Renvoie le code d'appairage (8 caracteres) ou None."""
    if not isinstance(raw, str):
        return None
    code = re.sub(r"[\s-]", "", raw).upper()
    return code if CODE_RE.fullmatch(code) else None


def clean_text(raw: object, max_length: int = TEXT_MAX_LENGTH) -> str:
    """Nettoie un texte avant de le lire a voix haute.

    Retire : caracteres de controle, balisage (HTML/SSML), adresses web,
    repetitions excessives. Coupe a ``max_length`` caracteres.
    """
    if not isinstance(raw, str):
        return ""
    # Un texte "echappe" (&lt;speak&gt;) ne doit pas revenir en balisage.
    text = raw
    for _ in range(2):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    text = unicodedata.normalize("NFKC", text)
    out: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        if char in "\t\n\r\v\f" or category in _SPACE_CATEGORIES:
            out.append(" ")
        elif category in _DROPPED_CATEGORIES:
            continue
        else:
            out.append(char)
    text = "".join(out)
    text = _TAG_RE.sub(" ", text)
    text = text.replace("<", " ").replace(">", " ")
    text = _URL_RE.sub(" ", text)
    text = _REPEAT_RE.sub(lambda m: m.group(1) * 4, text)
    text = _SPACES_RE.sub(" ", text).strip()
    if len(text) > max_length:
        text = text[:max_length].rstrip()
    return text


def clean_viewer(raw: object) -> str:
    """Nettoie un pseudo (court, sans balisage)."""
    return clean_text(raw, VIEWER_MAX_LENGTH)


class AddressError(ValueError):
    """Adresse refusee ; ``code`` est une cle de traduction."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SiteAddress:
    """Adresse de base de l'API Curiosa (sans barre finale)."""

    base_url: str
    host: str


_PRIVATE_SUFFIXES = (".local", ".lan", ".internal", ".home.arpa", ".localhost", ".home")


def is_private_host(host: str) -> bool:
    """Vrai pour localhost, une adresse privee ou un nom de reseau local."""
    host = host.strip("[]").lower()
    if host == "localhost" or host.endswith(_PRIVATE_SUFFIXES):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host  # nom sans point : reseau local
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified
    )


def parse_site_address(raw: object, developer: bool = False) -> SiteAddress:
    """Valide l'adresse saisie et renvoie l'adresse de base de l'API.

    - sans schema : https:// est ajoute ;
    - http:// et les adresses locales ne passent qu'en mode developpeur ;
    - si l'adresse ne contient pas /m/<instance>, on ajoute l'adresse par defaut
      (un /ha final, ancienne forme, est retire).
    """
    if not isinstance(raw, str) or not raw.strip():
        raise AddressError("invalid_address")
    value = raw.strip()
    if "://" not in value:
        value = f"https://{value}"
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as err:
        raise AddressError("invalid_address") from err
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        raise AddressError("invalid_address")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise AddressError("invalid_address")
    private = is_private_host(host)
    if private and not developer:
        raise AddressError("private_address")
    if parts.scheme == "http" and not (developer and private):
        raise AddressError("https_required")

    path = parts.path.rstrip("/")
    if re.fullmatch(r"(?:/[A-Za-z0-9._~-]+)*/m/[A-Za-z0-9._-]+/ha", path):
        path = path[: -len("/ha")]
    if re.fullmatch(r"(?:/[A-Za-z0-9._~-]+)*/m/[A-Za-z0-9._-]+", path):
        api_path = path
    elif re.fullmatch(r"(?:/[A-Za-z0-9._~-]+)*", path):
        api_path = f"{path}/m/{DEFAULT_INSTANCE}"
    else:
        raise AddressError("invalid_address")
    netloc = f"[{host}]" if ":" in host else host
    if port:
        netloc = f"{netloc}:{port}"
    return SiteAddress(base_url=f"{parts.scheme}://{netloc}{api_path}", host=host)


def site_root(base_url: str) -> str:
    """Adresse du site (sans /m/<instance>), pour l'afficher et ouvrir le site."""
    parts = urlsplit(base_url)
    path = re.sub(r"/m/[^/]+/?$", "", parts.path).rstrip("/")
    return f"{parts.scheme}://{parts.netloc}{path}"


def connector_page_url(base_url: str) -> str:
    """Page du Connecteur Home Assistant dans l'administration du site (adresse stable)."""
    return f"{site_root(base_url)}/admin/modules/home-assistant"
