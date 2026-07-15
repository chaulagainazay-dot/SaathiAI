"""Browser-as-connector — Browser Service through the governed boundary.

M17.24: side-effecting capabilities (fetch/extract/screenshot) enter
GovernedBrowser → ExecutionGateway. Diagnostics (health/tiers) remain direct.
"""
from __future__ import annotations

from ..base import Connector, Health, Status, ConnectorError
from ..manifest import Manifest

_CAPS = frozenset({"fetch", "extract", "search", "screenshot", "monitor"})


class BrowserConnector(Connector):
    id = "browser"

    def __init__(self, service=None, *, actor: str = "connector:browser"):
        self._service = service     # inject a BrowserService in tests
        self._injected = service is not None
        self._actor = actor

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
        actor = payload.get("actor") or self._actor
        # Injected harness services keep direct path; production singleton is governed
        svc = self._svc()
        allow_direct = bool(getattr(svc, "allow_direct", self._injected))

        if capability == "search":
            return svc.search(payload["query"], limit=payload.get("limit", 10))

        if capability == "monitor":
            return svc.monitor(payload["url"], payload.get("previous_digest"))

        # Side-effecting: prefer GovernedBrowser unless test harness
        if not allow_direct:
            from saathi.browser.governed import default_governed_browser
            action_map = {
                "fetch": "navigate",
                "extract": "extract",
                "screenshot": "screenshot",
            }
            action = action_map.get(capability, capability)
            rec = default_governed_browser().execute(
                action=action,
                url=payload.get("url", ""),
                selector=payload.get("selector") or "",
                actor=actor,
                request_source="connector",
                mission_id=payload.get("mission_id") or "connector_browser",
                mission_run_id=payload.get("mission_run_id") or "connector-browser",
                session_id=payload.get("session") or "default",
                environment=payload.get("environment") or "dev",
            )
            if rec.status != "succeeded":
                raise ConnectorError(
                    f"governed browser {capability} failed: "
                    f"{rec.failure_category or rec.status}: {rec.result_summary}"
                )
            return {
                "status": rec.status,
                "execution_id": rec.execution_id,
                "summary": rec.result_summary,
                "governed": True,
            }

        if capability == "fetch":
            return svc.open(payload["url"], evade=payload.get("evade", False),
                            session=payload.get("session"))
        if capability == "extract":
            return svc.extract(payload["url"], payload.get("selector"))
        if capability == "screenshot":
            return svc.screenshot(payload["url"], full_page=payload.get("full_page", True))
        raise ConnectorError(capability)  # unreachable
