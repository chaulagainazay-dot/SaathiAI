"""Camofox tier — anti-detect browser for bot-walled / challenge pages.

Top of the escalation chain: only reached when HTTP flags a block and Playwright
also fails or is unavailable. Camofox (a hardened Firefox via the `camoufox`
Playwright driver) presents a realistic fingerprint. Guarded import — never a
hard dependency; `available()` is False unless `camoufox` is installed.

Idea reused (not vendored) from jo-inc/camofox-browser; wrapped behind the same
BrowserTier contract so the rest of SaathiAI stays unaware of it.
"""
from __future__ import annotations

from .base import BrowserTier
from .types import Capabilities, Page, Tier


class CamofoxTier(BrowserTier):
    name = "camofox"
    tier = Tier.CAMOFOX

    def __init__(self, *, humanize: bool = True, headless: bool = True):
        self._humanize = humanize
        self._headless = headless

    def capabilities(self) -> Capabilities:
        return Capabilities(fetch=True, render_js=True, screenshot=True, pdf=False,
                            evade=True, dom_query=True,
                            labels=frozenset({"fetch", "render", "screenshot", "dom", "evade"}))

    def available(self) -> bool:
        try:
            from camoufox.sync_api import Camoufox  # noqa: F401
            return True
        except Exception:
            return False

    def _browser(self):
        from camoufox.sync_api import Camoufox
        return Camoufox(headless=self._headless, humanize=self._humanize)

    def open(self, url: str, *, timeout: int = 30, session=None) -> Page:
        with self._browser() as browser:
            storage = (session.storage_state or None) if session is not None else None
            context = browser.new_context(storage_state=storage)
            page = context.new_page()
            resp = page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            html = page.content()
            if session is not None:
                session.storage_state = context.storage_state()
            from .http_tier import html_to_text, _looks_blocked
            return Page(url=page.url, status=(resp.status if resp else 200),
                        html=html, text=html_to_text(html), title=page.title(),
                        tier=Tier.CAMOFOX, blocked=_looks_blocked(resp.status if resp else 200, html))

    def screenshot(self, url: str, *, timeout: int = 30, full_page: bool = True) -> bytes:
        with self._browser() as browser:
            page = browser.new_page()
            page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
            return page.screenshot(full_page=full_page)

    def query(self, url: str, selector: str, *, timeout: int = 30) -> list[str]:
        with self._browser() as browser:
            page = browser.new_page()
            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            return [el.inner_text() for el in page.query_selector_all(selector)]
