"""Browser-as-connector — the Browser Service exposed through the same contract.

Proves the infrastructure symmetry: a *service* can also be a *driver*. AI Studio
can `registry.execute(capability="fetch", url=...)` and get the same escalation
(HTTP→Playwright→Camofox) it would via `browser.open`, with uniform diagnostics
and events. No SDK — it wraps SaathiAI's own Browser Service.
"""
from __future__ import annotations

from ..base import Connector, Health, Status, ConnectorError
from ..manifest import Manifest

_CAPS = frozenset({"fetch", "extract", "search", "screenshot", "monitor"})


class BrowserConnector(Connector):
    id = "browser"

    def __init__(self, service=None):
        self._service = service     # inject a BrowserService in tests

    def _svc(self):
        if self._service is None:
            from saathi.browser import browser
            self._service = browser
        return self._service

    def manifest(self) -> Manifest:
        return Manifest(
            id=self.id, display_name="Browser", category="web", version=1,
            capabilities=_CAPS, permissions=frozenset({"outbound"}),
            requires_auth=False, cost=0.0, latency="medium", reliability=0.95,
            health_checks=frozenset({"tiers"}))

    def authenticate(self) -> bool:
        return True

    def health(self) -> Health:
        try:
            tiers = self._svc().tiers_status()
            live = [n for n, ok in tiers.items() if ok]
            if not live:
                return Health(Status.DOWN, "no browser tier available")
            status = Status.OK if "http" in live else Status.DEGRADED
            return Health(status, "tiers: " + ", ".join(live), {"tiers": tiers})
        except Exception as e:
            return Health(Status.DOWN, str(e))

    def execute(self, capability: str, **payload):
        self._require(capability)
        svc = self._svc()
        if capability == "fetch":
            return svc.open(payload["url"], evade=payload.get("evade", False),
                            session=payload.get("session"))
        if capability == "extract":
            return svc.extract(payload["url"], payload.get("selector"))
        if capability == "search":
            return svc.search(payload["query"], limit=payload.get("limit", 10))
        if capability == "screenshot":
            return svc.screenshot(payload["url"], full_page=payload.get("full_page", True))
        if capability == "monitor":
            return svc.monitor(payload["url"], payload.get("previous_digest"))
        raise ConnectorError(capability)  # unreachable
