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

    def _page(self, pw, headless=True, session=None):
        browser = getattr(pw, self._engine).launch(headless=headless)
        storage = (session.storage_state or None) if session is not None else None
        context = browser.new_context(storage_state=storage)
        return browser, context, context.new_page()

    def open(self, url: str, *, timeout: int = 30, session=None) -> Page:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser, context, page = self._page(pw, session=session)
            try:
                resp = page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
                html = page.content()
                if session is not None:
                    session.storage_state = context.storage_state()   # persist login
                from .http_tier import html_to_text
                return Page(url=page.url, status=(resp.status if resp else 200),
                            html=html, text=html_to_text(html), title=page.title(),
                            tier=Tier.PLAYWRIGHT)
            finally:
                browser.close()

    def screenshot(self, url: str, *, timeout: int = 30, full_page: bool = True) -> bytes:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser, _ctx, page = self._page(pw)
            try:
                page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
                return page.screenshot(full_page=full_page)
            finally:
                browser.close()

    def pdf(self, url: str, *, timeout: int = 30) -> bytes:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser, _ctx, page = self._page(pw)  # PDF requires headless chromium
            try:
                page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
                return page.pdf()
            finally:
                browser.close()

    def query(self, url: str, selector: str, *, timeout: int = 30) -> list[str]:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser, _ctx, page = self._page(pw)
            try:
                page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
                # Many data tables are filled by AJAX after DOMContentLoaded, so a
                # query that runs immediately sees an empty tbody and reports "no
                # rows" rather than "not ready yet". Wait for the selector itself,
                # but never fail on it: a page that genuinely has no match must
                # still return an empty list rather than raising.
                try:
                    page.wait_for_selector(selector, timeout=min(timeout, 15) * 1000)
                except Exception:
                    pass
                return [el.inner_text() for el in page.query_selector_all(selector)]
            finally:
                browser.close()
