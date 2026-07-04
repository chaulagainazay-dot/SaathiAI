"""Telegram connector — reference driver (the platform already uses Telegram).

Wraps the Bot API over httpx; no department imports it directly. Transport is
injectable for tests (httpx.MockTransport), so no network in CI.
"""
from __future__ import annotations

import os

from .base import (
    Connector, ConnectorMetadata, Health, Status, ConnectorError, RateLimited,
)

_CAPS = frozenset({"send_text", "send_photo", "send_document", "send_video"})
_METHOD = {"send_text": ("sendMessage", "text"), "send_photo": ("sendPhoto", "photo"),
           "send_document": ("sendDocument", "document"), "send_video": ("sendVideo", "video")}


class TelegramConnector(Connector):
    id = "telegram"

    def __init__(self, token: str | None = None, chat_id: str | None = None, transport=None):
        self._token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "")
        self._transport = transport

    def metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            id=self.id, capabilities=_CAPS, permissions=frozenset({"outbound", "webhook"}),
            requires_auth=True, cost=0.0, latency="low", reliability=0.99,
            rate_limits="30/sec")

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
        method, arg = _METHOD[capability]
        chat_id = payload.pop("chat_id", None) or self._chat
        if not chat_id:
            raise ConnectorError("no chat_id (pass chat_id= or set TELEGRAM_CHAT_ID)")
        body = {"chat_id": chat_id, **payload}
        with self._client() as c:
            r = c.post(f"/{method}", json=body)
        if r.status_code == 429:
            raise RateLimited("telegram 429")
        r.raise_for_status()
        return r.json()
