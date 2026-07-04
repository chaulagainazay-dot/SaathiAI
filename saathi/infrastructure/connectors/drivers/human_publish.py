"""Human-mode publishing — the last-resort `publish_video` provider.

Advertises `publish_video` at low reliability so the registry only routes here
when the API (and any headless-browser) mode is unavailable. Execution goes
through the signed job queue to the Mac Agent, which drives your real,
logged-in Chrome. No credentials on the VM.
"""
from __future__ import annotations

import os

from ..base import Connector, Health, Status, AuthRequired
from ..manifest import Manifest

_CAPS = frozenset({"publish_video", "publish_photo"})


class HumanPublishConnector(Connector):
    id = "human_publish"

    def __init__(self, proxy=None, *, default_profile: str = "ajay/youtube"):
        self._proxy = proxy
        self._default_profile = default_profile

    def _p(self):
        if self._proxy is None:
            from saathi.infrastructure.human_browser import HumanBrowserProxy, default_queue
            self._proxy = HumanBrowserProxy(default_queue)
        return self._proxy

    def manifest(self) -> Manifest:
        return Manifest(
            id=self.id, display_name="Human Browser (publish)", category="media", version=1,
            capabilities=_CAPS, permissions=frozenset({"outbound"}),
            requires_auth=True, cost=0.0, latency="high", reliability=0.75,
            health_checks=frozenset({"queue", "secret"}))

    def authenticate(self) -> bool:
        # usable only if we can sign+enqueue jobs (needs HUMAN_BROWSER_SECRET + queue)
        return bool(os.getenv("HUMAN_BROWSER_SECRET")) and self._p().available()

    def health(self) -> Health:
        if not self.authenticate():
            return Health(Status.AUTH_REQUIRED, "HUMAN_BROWSER_SECRET not set / no queue")
        return Health(Status.OK, "signed-job queue ready")

    def execute(self, capability: str, **payload):
        self._require(capability)
        profile = payload.pop("profile", None) or self._default_profile
        return self._p().execute(capability, profile=profile, **payload)
