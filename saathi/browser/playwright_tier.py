"""Playwright tier — real browser: renders JS, screenshots, PDF, DOM query.

Guarded import: `available()` is False (service skips this tier) unless
Playwright is installed. Never a hard dependency of the platform.
"""
from __future__ import annotations

from .base import BrowserTier
from .types import Capabilities, Page, Tier


class PlaywrightTier(BrowserTier):
    name = "playwright"
    tier = Tier.PLAYWRIGHT
    _engine = "chromium"

    def capabilities(self) -> Capabilities:
        return Capabilities(fetch=True, render_js=True, screenshot=True, pdf=True,
                            dom_query=True,
                            labels=frozenset({"fetch", "render", "screenshot", "pdf", "dom"}))

    def available(self) -> bool:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
            return True
        except Exception:
            return False

    def _page(self, pw, headless=True):
        browser = getattr(pw, self._engine).launch(headless=headless)
        return browser, browser.new_page()

    def open(self, url: str, *, timeout: int = 30) -> Page:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser, page = self._page(pw)
            try:
                resp = page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
                html = page.content()
                from .http_tier import html_to_text
                return Page(url=page.url, status=(resp.status if resp else 200),
                            html=html, text=html_to_text(html), title=page.title(),
                            tier=Tier.PLAYWRIGHT)
            finally:
                browser.close()

    def screenshot(self, url: str, *, timeout: int = 30, full_page: bool = True) -> bytes:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser, page = self._page(pw)
            try:
                page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
                return page.screenshot(full_page=full_page)
            finally:
                browser.close()

    def pdf(self, url: str, *, timeout: int = 30) -> bytes:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser, page = self._page(pw)  # PDF requires headless chromium
            try:
                page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
                return page.pdf()
            finally:
                browser.close()

    def query(self, url: str, selector: str, *, timeout: int = 30) -> list[str]:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser, page = self._page(pw)
            try:
                page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
                return [el.inner_text() for el in page.query_selector_all(selector)]
            finally:
                browser.close()
