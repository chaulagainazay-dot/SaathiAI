"""n8n connector — orchestration (everything already flows through n8n).

Triggers n8n webhooks. `N8N_WEBHOOK_BASE` sets the instance base URL.
Transport injectable for tests.
"""
from __future__ import annotations

import os

from ..base import Connector, Health, Status, ConnectorError
from ..manifest import Manifest

_CAPS = frozenset({"trigger_workflow", "execute_webhook"})


class N8nConnector(Connector):
    id = "n8n"

    def __init__(self, base_url: str | None = None, transport=None):
        self._base = (base_url if base_url is not None
                      else os.getenv("N8N_WEBHOOK_BASE", "")).rstrip("/")
        self._transport = transport

    def manifest(self) -> Manifest:
        return Manifest(
            id=self.id, display_name="n8n", category="orchestration", version=1,
            capabilities=_CAPS, permissions=frozenset({"outbound", "webhook"}),
            requires_auth=True, cost=0.0, latency="medium", reliability=0.97,
            health_checks=frozenset({"base_url", "api"}))

    def authenticate(self) -> bool:
        return bool(self._base) and not self._base.startswith("YOUR")

    def _client(self, timeout=30):
        import httpx
        return httpx.Client(timeout=timeout, transport=self._transport, base_url=self._base)

    def health(self) -> Health:
        if not self.authenticate():
            return Health(Status.AUTH_REQUIRED, "N8N_WEBHOOK_BASE missing")
        try:
            with self._client(timeout=5) as c:
                r = c.get("/healthz")
            return Health(Status.OK if r.status_code < 500 else Status.DOWN,
                          f"HTTP {r.status_code}")
        except Exception as e:
            return Health(Status.DOWN, str(e))

    def execute(self, capability: str, **payload):
        self._require(capability)
        path = payload.pop("path", None) or payload.pop("webhook", None)
        if not path:
            raise ConnectorError("n8n needs a 'path' (the webhook path)")
        with self._client() as c:
            r = c.post(f"/webhook/{path.lstrip('/')}", json=payload.get("data", payload))
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return {"status": r.status_code, "text": r.text}
