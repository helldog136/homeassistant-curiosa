"""Client HTTP du contrat Curiosa : pair, pull, ack.

Ce client n'envoie JAMAIS de donnees de la maison : seulement le code
d'appairage, le jeton, un curseur et un accuse a code ferme.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import aiohttp

from .const import (
    CODE_RE,
    DEFAULT_POLL_SECONDS,
    ID_RE,
    MAX_RESPONSE_BYTES,
    MAX_RETRY_AFTER_SECONDS,
    MIN_POLL_SECONDS,
    PULL_LIMIT,
    REQUEST_TIMEOUT,
    VERSION,
)


class CuriosaError(Exception):
    """Erreur de base."""


class CuriosaConnectionError(CuriosaError):
    """Site injoignable, reponse illisible ou trop lente."""


class CuriosaAuthError(CuriosaError):
    """401 : jeton inconnu ou revoque."""


class CuriosaHttpError(CuriosaError):
    """Reponse HTTP d'erreur (404, 429, 5xx...)."""

    def __init__(self, status: int, retry_after: int | None = None) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status
        self.retry_after = retry_after


class CuriosaPairError(CuriosaError):
    """Appairage refuse ; ``reason`` : invalid_code | code_expired | too_many | not_found."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class PairResult:
    """Reponse de l'appairage."""

    token: str
    instance: str
    poll_seconds: int


@dataclass(frozen=True)
class Action:
    """Une action recue de Curiosa."""

    id: str
    key: str
    text: str
    viewer: str
    issued_at: datetime | None
    expires_at: datetime | None
    test: bool = False


@dataclass(frozen=True)
class PullResult:
    """Reponse de l'interrogation."""

    enabled: bool
    live: bool
    server_time: datetime | None
    cursor: int | None
    actions: list[Action] = field(default_factory=list)


def parse_time(value: object) -> datetime | None:
    """Lit une date ISO ; sans fuseau on suppose UTC."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _retry_after(response: aiohttp.ClientResponse) -> int | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        seconds = int(value.strip())
    except ValueError:
        return None
    return max(1, min(seconds, MAX_RETRY_AFTER_SECONDS))


def parse_pull(payload: dict[str, Any]) -> PullResult:
    """Valide la reponse de ``pull`` ; ignore ce qui n'a pas la bonne forme."""
    actions: list[Action] = []
    raw_actions = payload.get("actions")
    if isinstance(raw_actions, list):
        for item in raw_actions[:PULL_LIMIT]:
            if not isinstance(item, dict):
                continue
            action_id = item.get("id")
            if not isinstance(action_id, str) or not ID_RE.fullmatch(action_id):
                continue  # sans identifiant valide on ne peut meme pas accuser
            key = item.get("key")
            text = item.get("text")
            viewer = item.get("viewer")
            actions.append(
                Action(
                    id=action_id,
                    key=key if isinstance(key, str) else "",
                    text=text if isinstance(text, str) else "",
                    viewer=viewer if isinstance(viewer, str) else "",
                    issued_at=parse_time(item.get("issuedAt")),
                    expires_at=parse_time(item.get("expiresAt")),
                    test=item.get("test") is True,
                )
            )
    cursor = payload.get("cursor")
    return PullResult(
        enabled=payload.get("enabled") is True,
        live=payload.get("live") is True,
        server_time=parse_time(payload.get("serverTime")),
        cursor=cursor if isinstance(cursor, int) and not isinstance(cursor, bool) else None,
        actions=actions,
    )


class CuriosaApi:
    """Client du contrat HTTP public de Curiosa."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        token: str | None = None,
    ) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._token = token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> tuple[int, Any, aiohttp.ClientResponse]:
        headers = {"Accept": "application/json", "User-Agent": f"HomeAssistant-Curiosa/{VERSION}"}
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            async with self._session.request(
                method,
                f"{self._base}/{path}",
                params=params,
                json=body,
                headers=headers,
                allow_redirects=False,  # le jeton ne doit jamais suivre une redirection
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                raw = await response.content.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise CuriosaConnectionError("response too large")
                data: Any = None
                if raw:
                    try:
                        data = json.loads(raw)
                    except (ValueError, UnicodeDecodeError):
                        data = None
                return response.status, data, response
        except (TimeoutError, aiohttp.ClientError) as err:
            raise CuriosaConnectionError(type(err).__name__) from err

    async def pair(self, code: str, name: str) -> PairResult:
        """Echange le code a usage unique contre un jeton."""
        if not CODE_RE.fullmatch(code):
            raise CuriosaPairError("invalid_code")
        status, data, response = await self._request(
            "POST", "pair", body={"code": code, "name": name}, auth=False
        )
        if status == 200 and isinstance(data, dict):
            token = data.get("token")
            instance = data.get("instance")
            poll = data.get("pollSeconds")
            if not isinstance(token, str) or len(token) < 16 or not isinstance(instance, str):
                raise CuriosaConnectionError("bad pair response")
            if not isinstance(poll, int) or isinstance(poll, bool):
                poll = DEFAULT_POLL_SECONDS
            return PairResult(token, instance, max(MIN_POLL_SECONDS, min(poll, 60)))
        detail = ""
        if isinstance(data, dict):
            detail = " ".join(
                str(data.get(k, "")) for k in ("error", "code", "reason") if data.get(k)
            ).lower()
        if status == 429 or "too_many" in detail or "rate" in detail:
            raise CuriosaPairError("too_many")
        if status == 410 or "expir" in detail:
            raise CuriosaPairError("code_expired")
        if status == 404:
            raise CuriosaPairError("not_found")
        if status in (400, 401, 403, 422):
            raise CuriosaPairError("invalid_code")
        raise CuriosaHttpError(status, _retry_after(response))

    async def pull(self, cursor: int | None) -> PullResult:
        """Demande les actions en attente."""
        params: dict[str, Any] = {"limit": PULL_LIMIT}
        if cursor is not None:
            params["cursor"] = cursor
        status, data, response = await self._request("GET", "pull", params=params)
        if status == 401:
            raise CuriosaAuthError
        if status != 200:
            raise CuriosaHttpError(status, _retry_after(response))
        if not isinstance(data, dict):
            raise CuriosaConnectionError("bad pull response")
        return parse_pull(data)

    async def ack(self, action_id: str, status_value: str, code: str) -> None:
        """Envoie l'accuse : un identifiant, un etat et un code de la liste fermee."""
        status, _data, response = await self._request(
            "POST", "ack", body={"id": action_id, "status": status_value, "code": code}
        )
        if status == 401:
            raise CuriosaAuthError
        if status >= 500 or status == 429:
            raise CuriosaHttpError(status, _retry_after(response))
        # 200/204/404/409 : rien d'autre a faire (deja acquittee, expiree...)
