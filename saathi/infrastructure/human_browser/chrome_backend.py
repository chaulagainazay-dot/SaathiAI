"""ChromeBackend — the real HumanBrowser, Mac-side (guarded).

Drives a persistent Chrome profile via Playwright so the session is the one you
logged into by hand. Guarded import: `available()` is False unless Playwright is
installed, so importing this on the VM (where it must never run) is harmless.
"""
from __future__ import annotations

import base64

from .driver import HumanBrowser
from .profiles import ProfileStore


class ChromeBackend(HumanBrowser):
    def __init__(self, profiles: ProfileStore | None = None, *, headless: bool = False,
                 channel: str = "chrome"):
        self._profiles = profiles or ProfileStore()
        self._headless = headless
        self._channel = channel

    def available(self) -> bool:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
            return True
        except Exception:
            return False

    def _context(self, pw, profile: str):
        user_dir = str(self._profiles.ensure(profile))
        return pw.chromium.launch_persistent_context(
            user_dir, headless=self._headless, channel=self._channel)

    def execute(self, capability: str, *, profile: str = "", **payload) -> dict:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            ctx = self._context(pw, profile)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                if capability in ("open", "login"):
                    page.goto(payload["url"] if "url" in payload else payload.get("service", "about:blank"),
                              wait_until="domcontentloaded")
                    return {"url": page.url, "title": page.title()}
                if capability == "click":
                    page.click(payload["selector"]); return {"clicked": payload["selector"]}
                if capability == "type":
                    page.fill(payload["selector"], payload["text"]); return {"typed": True}
                if capability == "upload":
                    page.set_input_files(payload.get("selector", "input[type=file]"), payload["path"])
                    return {"uploaded": payload["path"]}
                if capability == "screenshot":
                    png = page.screenshot()
                    return {"screenshot_b64": base64.b64encode(png).decode()}
                if capability == "wait":
                    page.wait_for_timeout(int(payload.get("ms", 1000))); return {"waited": True}
                if capability == "publish_video":
                    # scripted UI flow lives here (per service); left to the operator to script
                    return {"status": "publish flow not scripted yet", "profile": profile}
                if capability == "close":
                    return {"closed": True}
                return {"error": f"unknown capability {capability}"}
            finally:
                ctx.close()
