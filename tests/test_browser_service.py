"""Browser Service (Phase 1.2) — escalation, capability routing, and the real
HTTP tier driven by an injected transport (no network, no real browser)."""
import httpx
import pytest

from saathi.browser import BrowserService, Tier, BrowserError
from saathi.browser.base import BrowserTier
from saathi.browser.types import Capabilities, Page
from saathi.browser.http_tier import HttpTier, html_to_text


# ── fakes ────────────────────────────────────────────────────────────────
class FakeTier(BrowserTier):
    def __init__(self, name, tier, caps, *, avail=True, page=None, boom=False):
        self.name, self.tier, self._caps = name, tier, caps
        self._avail, self._page, self._boom = avail, page, boom
        self.opened = 0

    def capabilities(self): return self._caps
    def available(self): return self._avail

    def open(self, url, *, timeout=30):
        self.opened += 1
        if self._boom:
            raise RuntimeError("tier crashed")
        return self._page or Page(url=url, status=200, text="ok", tier=self.tier)

    def screenshot(self, url, *, timeout=30, full_page=True):
        if not self._caps.screenshot:
            raise NotImplementedError
        return b"PNGDATA"

    def query(self, url, selector, *, timeout=30):
        if not self._caps.dom_query:
            raise NotImplementedError
        return [f"{selector}:node"]


def _caps(**kw): return Capabilities(**kw)


# ── escalation ───────────────────────────────────────────────────────────
def test_escalates_past_blocked_http_to_playwright():
    blocked = Page(url="u", status=403, blocked=True, tier=Tier.HTTP)
    http = FakeTier("http", Tier.HTTP, _caps(fetch=True), page=blocked)
    pw = FakeTier("playwright", Tier.PLAYWRIGHT, _caps(fetch=True, render_js=True))
    svc = BrowserService(tiers=[pw, http])          # unsorted input
    page = svc.open("http://x")
    assert page.ok and page.tier == Tier.PLAYWRIGHT
    assert http.opened == 1 and pw.opened == 1      # tried http first, then escalated


def test_evade_starts_at_camofox_only():
    http = FakeTier("http", Tier.HTTP, _caps(fetch=True))
    cam = FakeTier("camofox", Tier.CAMOFOX, _caps(fetch=True, evade=True))
    svc = BrowserService(tiers=[http, cam])
    svc.open("http://x", evade=True)
    assert http.opened == 0 and cam.opened == 1     # HTTP tier skipped entirely


def test_all_blocked_returns_best_effort_page():
    b1 = Page(url="u", status=403, blocked=True, tier=Tier.HTTP)
    b2 = Page(url="u", status=429, blocked=True, tier=Tier.PLAYWRIGHT)
    svc = BrowserService(tiers=[
        FakeTier("http", Tier.HTTP, _caps(fetch=True), page=b1),
        FakeTier("playwright", Tier.PLAYWRIGHT, _caps(fetch=True), page=b2),
    ])
    page = svc.open("http://x")
    assert page.blocked and page.tier == Tier.PLAYWRIGHT   # strongest attempt returned


def test_crashing_tier_is_skipped():
    ok = Page(url="u", status=200, text="hi", tier=Tier.PLAYWRIGHT)
    svc = BrowserService(tiers=[
        FakeTier("http", Tier.HTTP, _caps(fetch=True), boom=True),
        FakeTier("playwright", Tier.PLAYWRIGHT, _caps(fetch=True), page=ok),
    ])
    assert svc.open("http://x").ok


def test_no_fetch_tier_raises():
    svc = BrowserService(tiers=[FakeTier("http", Tier.HTTP, _caps(fetch=True), avail=False)])
    with pytest.raises(BrowserError):
        svc.open("http://x")


# ── capability routing ───────────────────────────────────────────────────
def test_screenshot_skips_incapable_tier():
    http = FakeTier("http", Tier.HTTP, _caps(fetch=True))               # no screenshot
    pw = FakeTier("playwright", Tier.PLAYWRIGHT, _caps(fetch=True, screenshot=True))
    svc = BrowserService(tiers=[http, pw])
    assert svc.screenshot("http://x") == b"PNGDATA"


def test_screenshot_without_capable_tier_raises():
    svc = BrowserService(tiers=[FakeTier("http", Tier.HTTP, _caps(fetch=True))])
    with pytest.raises(BrowserError):
        svc.screenshot("http://x")


def test_extract_with_selector_uses_dom_tier():
    http = FakeTier("http", Tier.HTTP, _caps(fetch=True))
    pw = FakeTier("playwright", Tier.PLAYWRIGHT, _caps(fetch=True, dom_query=True))
    svc = BrowserService(tiers=[http, pw])
    assert svc.extract("http://x", "h1.title") == ["h1.title:node"]


def test_tiers_status_reports_availability():
    svc = BrowserService(tiers=[
        FakeTier("http", Tier.HTTP, _caps(fetch=True), avail=True),
        FakeTier("camofox", Tier.CAMOFOX, _caps(fetch=True), avail=False),
    ])
    assert svc.tiers_status() == {"http": True, "camofox": False}


# ── monitoring ───────────────────────────────────────────────────────────
def test_monitor_detects_change():
    page = Page(url="u", status=200, text="v1", tier=Tier.HTTP)
    svc = BrowserService(tiers=[FakeTier("http", Tier.HTTP, _caps(fetch=True), page=page)])
    first = svc.monitor("http://x")
    assert first["first_seen"] and first["changed"] is False
    same = svc.monitor("http://x", first["digest"])
    assert same["changed"] is False                    # identical content
    changed = svc.monitor("http://x", "different-digest")
    assert changed["changed"] is True


# ── real HTTP tier via injected transport (no network) ───────────────────
def test_http_tier_parses_and_flags_block():
    def handler(request):
        if "blocked" in request.url.path:
            return httpx.Response(403, text="<h1>Attention Required</h1>")
        return httpx.Response(200, text="<html><head><title>Hi</title></head>"
                                        "<body><script>x()</script><p>Hello  world</p></body></html>")
    tier = HttpTier(transport=httpx.MockTransport(handler))
    good = tier.open("http://site/ok")
    assert good.ok and good.title == "Hi" and "Hello world" in good.text
    assert "x()" not in good.text                      # script stripped
    blocked = tier.open("http://site/blocked")
    assert blocked.blocked and blocked.status == 403


def test_html_to_text_strips_markup():
    assert html_to_text("<b>a</b> &amp; <i>b</i>") == "a & b"
