"""Petit serveur HTTP de test qui parle le contrat de Curiosa (pair / pull / ack)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from aiohttp import web
from aiohttp.test_utils import TestServer

PREFIX = "/m/home-assistant"
GOOD_CODE = "ABCD2345"
EXPIRED_CODE = "OLDOLD22"
LIMITED_CODE = "SPAMSPAM"
TOKEN = "t" * 43


def iso(moment: datetime) -> str:
    """Date ISO UTC avec Z."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class FakeCuriosa:
    """Etat et journal d'un faux site Curiosa."""

    def __init__(self) -> None:
        self.enabled = True
        self.live = True
        self.cursor = 0
        self.queue: list[dict[str, Any]] = []
        self.requests: list[dict[str, Any]] = []
        self.acks: list[dict[str, Any]] = []
        self.pull_status: int | None = None
        self.retry_after: str | None = None
        self.ack_status = 200
        self.server_time_offset = timedelta(0)
        self.valid_token = TOKEN
        self.url = ""
        self._server: TestServer | None = None

    # --- scenario ----------------------------------------------------------
    def enqueue(
        self,
        key: str,
        text: str = "",
        viewer: str = "",
        *,
        action_id: str | None = None,
        ttl: float = 60,
        age: float = 0,
    ) -> str:
        """Met une action en attente ; ``age`` = depuis combien de secondes elle existe."""
        now = datetime.now(UTC) + self.server_time_offset
        issued = now - timedelta(seconds=age)
        action_id = action_id or uuid.uuid4().hex[:12]
        self.queue.append(
            {
                "id": action_id,
                "key": key,
                "text": text,
                "viewer": viewer,
                "issuedAt": iso(issued),
                "expiresAt": iso(issued + timedelta(seconds=ttl)),
            }
        )
        return action_id

    # --- HTTP --------------------------------------------------------------
    async def _log(self, request: web.Request) -> Any:
        body = None
        if request.can_read_body:
            body = await request.json()
        self.requests.append(
            {
                "method": request.method,
                "path": request.path,
                "query": dict(request.query),
                "body": body,
                "headers": dict(request.headers),
                "raw_url": str(request.rel_url),
            }
        )
        return body

    async def pair(self, request: web.Request) -> web.Response:
        body = await self._log(request)
        code = (body or {}).get("code")
        if code == GOOD_CODE:
            return web.json_response(
                {"token": TOKEN, "instance": "home-assistant", "pollSeconds": 3}
            )
        if code == EXPIRED_CODE:
            return web.json_response({"error": "expired"}, status=410)
        if code == LIMITED_CODE:
            return web.json_response({"error": "rate"}, status=429, headers={"Retry-After": "30"})
        return web.json_response({"error": "invalid"}, status=403)

    def _authorized(self, request: web.Request) -> bool:
        return request.headers.get("Authorization") == f"Bearer {self.valid_token}"

    async def pull(self, request: web.Request) -> web.Response:
        await self._log(request)
        if not self._authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        if self.pull_status is not None:
            headers = {"Retry-After": self.retry_after} if self.retry_after else {}
            return web.json_response({"error": "x"}, status=self.pull_status, headers=headers)
        now = datetime.now(UTC) + self.server_time_offset
        actions = list(self.queue) if self.enabled and self.live else []
        self.cursor += 1
        return web.json_response(
            {
                "enabled": self.enabled,
                "live": self.live,
                "serverTime": iso(now),
                "cursor": self.cursor,
                "actions": actions[:10],
            }
        )

    async def ack(self, request: web.Request) -> web.Response:
        body = await self._log(request)
        if not self._authorized(request):
            return web.json_response({"error": "unauthorized"}, status=401)
        if self.ack_status != 200:
            return web.json_response({"error": "x"}, status=self.ack_status)
        self.acks.append(body)
        self.queue = [a for a in self.queue if a["id"] != body.get("id")]
        return web.json_response({"ok": True})

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_post(f"{PREFIX}/pair", self.pair)
        app.router.add_get(f"{PREFIX}/pull", self.pull)
        app.router.add_post(f"{PREFIX}/ack", self.ack)
        return app

    async def start(self) -> None:
        self._server = TestServer(self.app())
        await self._server.start_server()
        self.url = f"http://127.0.0.1:{self._server.port}"

    async def stop(self) -> None:
        if self._server:
            await self._server.close()

    @property
    def api_url(self) -> str:
        return f"{self.url}{PREFIX}"
