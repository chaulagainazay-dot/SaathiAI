"""HumanTier — the Human Browser Driver as a Browser Service escalation tier.

Opt-in: not in the default tier list (it needs a queue + signing secret). Add it
to a BrowserService when you want `open()` to escalate all the way to your real
Chrome profile after HTTP/Playwright/Camofox fail or are blocked.

    from saathi.browser import BrowserService
    from saathi.browser.http_tier import HttpTier
    from saathi.infrastructure.human_browser import HumanBrowserProxy
    from saathi.infrastructure.human_browser.browser_tier import HumanTier
    svc = BrowserService(tiers=[HttpTier(), HumanTier(HumanBrowserProxy(queue))])
"""
from __future__ import annotations

from saathi.browser.base import BrowserTier
from saathi.browser.types import Capabilities, Page, Tier


class HumanTier(BrowserTier):
    name = "human"
    tier = Tier.HUMAN

    def __init__(self, proxy, *, profile: str = ""):
        self._proxy = proxy
        self._profile = profile

    def capabilities(self) -> Capabilities:
        return Capabilities(fetch=True, render_js=True, screenshot=True, evade=True,
                            dom_query=False,
                            labels=frozenset({"fetch", "render", "screenshot", "human"}))

    def available(self) -> bool:
        return bool(self._proxy) and self._proxy.available()

    def open(self, url: str, *, timeout: int = 60, session=None) -> Page:
        data = self._proxy.execute("open", profile=self._profile, url=url)
        return Page(url=data.get("url", url), status=200, title=data.get("title", ""),
                    tier=Tier.HUMAN)

    def screenshot(self, url: str, *, timeout: int = 60, full_page: bool = True) -> bytes:
        import base64
        self._proxy.execute("open", profile=self._profile, url=url)
        shot = self._proxy.execute("screenshot", profile=self._profile)
        return base64.b64decode(shot.get("screenshot_b64", "")) if shot.get("screenshot_b64") else b""
