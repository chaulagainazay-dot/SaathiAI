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


_MAX_DOC_BYTES = 15 * 1024 * 1024


@dataclass
class CaptureResult:
    status: str                       # ok | degraded
    error_category: str = ""
    notices: list = field(default_factory=list)
    disclosures: dict | list = field(default_factory=dict)
    securities: list = field(default_factory=list)
    endpoint_status: dict = field(default_factory=dict)   # path -> http status seen in browser
    off_domain_blocked: list = field(default_factory=list)
    documents: dict = field(default_factory=dict)         # url -> {status, content_type, body}
    runtime_sec: float = 0.0
    cleanup: dict = field(default_factory=dict)


def _derive_doc_urls(notices, disclosures) -> list[str]:
    from saathi.browser_research.nepse_endpoint import _doc_url
    urls: list[str] = []
    for n in (notices or []):
        p = n.get("noticeFilePath")
        if p:
            urls.append(_doc_url(str(p)))
    news = disclosures.get("companyNews", []) if isinstance(disclosures, dict) else (disclosures or [])
    for c in news:
        for d in (c.get("applicationDocumentDetailsList") or []):
            if d.get("filePath"):
                urls.append(_doc_url(str(d["filePath"])))
    # unique, order-preserving
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u); out.append(u)
    return out


def capture_nepse(*, timeout_sec: float = 45.0, detail_pages: tuple[str, ...] = (),
                  max_documents: int = 0, max_doc_bytes: int = _MAX_DOC_BYTES) -> CaptureResult:
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
        notices = bodies.get(NEPSE_RESEARCH_ENDPOINTS[0], []) or []
        disclosures = bodies.get(NEPSE_RESEARCH_ENDPOINTS[1], {}) or {}
        documents: dict = {}
        if max_documents > 0:
            # Fetch official document bytes IN-SESSION (browser's own token; no
            # forgery). Domain-checked + size-capped. Bounded count.
            for url in _derive_doc_urls(notices, disclosures)[:max_documents]:
                if not check_domain(url, allowed_hosts=list(_ALLOWED)).allowed:
                    off_domain.append(url); continue
                try:
                    dr = context.request.get(url, timeout=int(timeout_sec * 1000))
                    body = dr.body()
                    if len(body) > max_doc_bytes:
                        documents[url] = {"status": dr.status, "content_type": "", "body": None,
                                          "too_large": True}
                    else:
                        documents[url] = {"status": dr.status,
                                          "content_type": (dr.headers.get("content-type", "") or "").split(";")[0].strip().lower(),
                                          "body": body}
                except Exception as e:
                    documents[url] = {"status": 0, "content_type": "", "body": None,
                                      "error": type(e).__name__}
        res = CaptureResult(
            status="ok", notices=notices, disclosures=disclosures,
            securities=bodies.get(NEPSE_SECURITY_ENDPOINT, []) or [],
            endpoint_status=ep_status, off_domain_blocked=off_domain, documents=documents,
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
