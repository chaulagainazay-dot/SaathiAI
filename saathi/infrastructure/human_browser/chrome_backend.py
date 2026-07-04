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
                 channel: str = "chrome", cdp_url: str | None = None):
        self._profiles = profiles or ProfileStore()
        self._headless = headless
        self._channel = channel
        # cdp_url attaches to a Chrome YOU launched (no automation flags → no
        # Google sign-in block, reuses your real logged-in session).
        import os as _os
        self._cdp_url = cdp_url if cdp_url is not None else _os.getenv("CHROME_CDP_URL")

    def available(self) -> bool:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
            return True
        except Exception:
            return False

    def _context(self, pw, profile: str):
        if self._cdp_url:
            browser = pw.chromium.connect_over_cdp(self._cdp_url)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            ctx._saathi_attached = True   # marker: don't close the user's browser
            return ctx
        user_dir = str(self._profiles.ensure(profile))
        return pw.chromium.launch_persistent_context(
            user_dir, headless=self._headless, channel=self._channel)

    def execute(self, capability: str, *, profile: str = "", **payload) -> dict:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            ctx = self._context(pw, profile)
            # attached (CDP): open a fresh tab so we never hijack the user's tabs
            page = ctx.new_page() if getattr(ctx, "_saathi_attached", False) else (
                ctx.pages[0] if ctx.pages else ctx.new_page())
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
                if capability in ("publish_video", "publish_post"):
                    from .primitives import BrowserPrimitives
                    from .workflows import WORKFLOWS
                    from .vision_verifier import default_verifier
                    from .selector_registry import default_registry as _selreg
                    _default_wf = "youtube_upload" if capability == "publish_video" else "linkedin_post"
                    wf_cls = WORKFLOWS.get(payload.get("workflow") or _default_wf)
                    if wf_cls is None:
                        return {"error": f"unknown workflow {payload.get('workflow')!r}"}
                    reg = _selreg()
                    for _m in ("youtube", "linkedin", "tiktok"):    # seed all known page objects
                        try:
                            __import__(f"saathi.infrastructure.human_browser.pages.{_m}",
                                       fromlist=[_m]).seed(reg)
                        except Exception:
                            pass
                    prims = BrowserPrimitives(page)
                    verifier = None if payload.get("no_vision") else default_verifier()
                    content = {k: v for k, v in payload.items() if k not in ("workflow", "no_vision")}
                    return wf_cls().run(prims, verifier=verifier, registry=reg, **content)
                if capability == "close":
                    return {"closed": True}
                return {"error": f"unknown capability {capability}"}
            finally:
                if not getattr(ctx, "_saathi_attached", False):
                    ctx.close()          # never close a Chrome the user launched (CDP attach)
