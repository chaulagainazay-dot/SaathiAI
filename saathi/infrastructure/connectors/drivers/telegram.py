"""Telegram connector — reference driver (the platform already uses Telegram).

Wraps the Bot API over httpx; no department imports it directly. Transport is
injectable for tests (httpx.MockTransport), so no network in CI.
"""
from __future__ import annotations

import os

from ..base import Connector, Health, Status, ConnectorError, RateLimited
from ..manifest import Manifest

_CAPS = frozenset({"send_text", "send_photo", "send_document", "send_video", "get_updates"})
_METHOD = {"send_text": ("sendMessage", "text"), "send_photo": ("sendPhoto", "photo"),
           "send_document": ("sendDocument", "document"), "send_video": ("sendVideo", "video")}


class TelegramConnector(Connector):
    id = "telegram"

    def __init__(self, token: str | None = None, chat_id: str | None = None, transport=None):
        self._token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "")
        self._transport = transport

    def manifest(self) -> Manifest:
        return Manifest(
            id=self.id, display_name="Telegram", category="messaging", version=1,
            capabilities=_CAPS, permissions=frozenset({"outbound", "inbound", "webhook"}),
            requires_auth=True, cost=0.0, latency="low", reliability=0.99,
            rate_limits={"requests_per_second": 30}, health_checks=frozenset({"token", "api"}))

    def authenticate(self) -> bool:
        return bool(self._token) and not self._token.startswith("YOUR")

    def _client(self, timeout=15):
        import httpx
        return httpx.Client(timeout=timeout, transport=self._transport,
                            base_url=f"https://api.telegram.org/bot{self._token}")

    def health(self) -> Health:
        if not self.authenticate():
            return Health(Status.AUTH_REQUIRED, "TELEGRAM_BOT_TOKEN missing")
        try:
            with self._client() as c:
                r = c.get("/getMe")
            if r.status_code == 429:
                return Health(Status.DEGRADED, "rate limited")
            if r.status_code == 401:
                return Health(Status.AUTH_REQUIRED, "token rejected")
            r.raise_for_status()
            name = r.json().get("result", {}).get("username", "")
            return Health(Status.OK, f"@{name}" if name else "ok")
        except Exception as e:
            return Health(Status.DOWN, str(e))

    def execute(self, capability: str, **payload):
        self._require(capability)
        if capability == "get_updates":                 # inbound polling (no chat_id)
            with self._client(timeout=payload.get("timeout", 60) + 10) as c:
                r = c.get("/getUpdates", params={k: v for k, v in payload.items() if v is not None})
            if r.status_code == 429:
                raise RateLimited("telegram 429")
            r.raise_for_status()
            return r.json()
        method, arg = _METHOD[capability]
        chat_id = payload.pop("chat_id", None) or self._chat
        if not chat_id:
            raise ConnectorError("no chat_id (pass chat_id= or set TELEGRAM_CHAT_ID)")
        file_path = payload.pop("file_path", None)      # multipart upload of a local file
        with self._client(timeout=120 if file_path else 15) as c:
            if file_path:
                from pathlib import Path
                p = Path(file_path).expanduser()
                data = {"chat_id": chat_id, **{k: v for k, v in payload.items() if v is not None}}
                with open(p, "rb") as f:
                    r = c.post(f"/{method}", data=data, files={arg: (p.name, f, "application/octet-stream")})
            else:
                r = c.post(f"/{method}", json={"chat_id": chat_id, **payload})
        if r.status_code == 429:
            raise RateLimited("telegram 429")
        r.raise_for_status()
        return r.json()
