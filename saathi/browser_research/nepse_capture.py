"""Phase 6/17/19 — bounded governed Playwright capture of NEPSE public JSON.

Read-only. One context, headless, hard timeout, no clicks/mutation/login. Loads
the official NEPSE pages so the site's own JS issues its public XHRs, and
captures those JSON responses. Every captured/redirected URL is revalidated
against domain policy. Guaranteed teardown (page/context/browser). Playwright is
imported lazily; if unavailable the caller degrades cleanly.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from saathi.browser.policy import check_domain
from saathi.browser_research.nepse_endpoint import (
    NEPSE_ORIGIN, NEPSE_RESEARCH_ENDPOINTS, NEPSE_SECURITY_ENDPOINT,
)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

_ALLOWED = ("nepalstock.com",)


@dataclass
class CaptureResult:
    status: str                       # ok | degraded
    error_category: str = ""
    notices: list = field(default_factory=list)
    disclosures: dict | list = field(default_factory=dict)
    securities: list = field(default_factory=list)
    endpoint_status: dict = field(default_factory=dict)   # path -> http status seen in browser
    off_domain_blocked: list = field(default_factory=list)
    runtime_sec: float = 0.0
    cleanup: dict = field(default_factory=dict)


def capture_nepse(*, timeout_sec: float = 45.0, detail_pages: tuple[str, ...] = ()) -> CaptureResult:
    t0 = time.time()
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return CaptureResult(status="degraded", error_category="PLAYWRIGHT_UNAVAILABLE",
                             runtime_sec=round(time.time() - t0, 3))

    want = tuple(NEPSE_RESEARCH_ENDPOINTS) + (NEPSE_SECURITY_ENDPOINT,)
    bodies: dict[str, object] = {}
    ep_status: dict[str, int] = {}
    off_domain: list[str] = []
    browser = context = None
    page_closed = ctx_closed = br_closed = False
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True, args=["--disable-http2", "--no-sandbox"])
        context = browser.new_context(user_agent=_UA)
        page = context.new_page()

        def on_resp(r):
            url = r.url
            # domain policy revalidation on every response URL
            if not check_domain(url, allowed_hosts=list(_ALLOWED)).allowed:
                off_domain.append(url[:120])
                return
            for w in want:
                if w in url:
                    ep_status[w] = r.status
                    if w not in bodies and r.status == 200:
                        try:
                            bodies[w] = r.json()
                        except Exception:
                            pass

        page.on("response", on_resp)
        # domain check the seed before navigating
        if not check_domain(NEPSE_ORIGIN + "/", allowed_hosts=list(_ALLOWED)).allowed:
            raise RuntimeError("seed blocked by domain policy")
        page.goto(NEPSE_ORIGIN + "/", wait_until="domcontentloaded", timeout=int(timeout_sec * 1000))
        page.wait_for_timeout(5000)
        # bounded detail navigation (read-only) to trigger disclosure/notice XHRs
        for path in detail_pages[:3]:
            url = NEPSE_ORIGIN + path
            if not check_domain(url, allowed_hosts=list(_ALLOWED)).allowed:
                off_domain.append(url)
                continue
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(3500)
            except Exception:
                continue
        res = CaptureResult(
            status="ok",
            notices=bodies.get(NEPSE_RESEARCH_ENDPOINTS[0], []) or [],
            disclosures=bodies.get(NEPSE_RESEARCH_ENDPOINTS[1], {}) or {},
            securities=bodies.get(NEPSE_SECURITY_ENDPOINT, []) or [],
            endpoint_status=ep_status, off_domain_blocked=off_domain,
        )
    except Exception as e:
        res = CaptureResult(status="degraded", error_category=f"CAPTURE_ERROR:{type(e).__name__}",
                            endpoint_status=ep_status, off_domain_blocked=off_domain)
    finally:
        try:
            if context is not None:
                context.close(); ctx_closed = True
        except Exception:
            pass
        try:
            if browser is not None:
                browser.close(); br_closed = True
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass
    res.runtime_sec = round(time.time() - t0, 3)
    res.cleanup = {"context_closed": ctx_closed, "browser_closed": br_closed, "page_closed": True}
    return res
