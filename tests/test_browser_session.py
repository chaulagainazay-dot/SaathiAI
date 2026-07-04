"""Browser Session Manager (Phase 1.2.5) — persistence + cookie threading."""
import httpx
import pytest

from saathi.browser import BrowserService, SessionManager, SessionState, Tier
from saathi.browser.http_tier import HttpTier
from saathi.browser.session import to_httpx_cookies, capture_httpx_cookies


def test_save_load_list_delete(tmp_path):
    sm = SessionManager(root=tmp_path)
    assert sm.list() == [] and not sm.exists("youtube")
    sm.save(SessionState(name="youtube", cookies=[{"name": "SID", "value": "abc",
                                                   "domain": "youtube.com", "path": "/"}]))
    assert sm.exists("youtube") and sm.list() == ["youtube"]
    loaded = sm.load("youtube")
    assert loaded.cookies[0]["value"] == "abc" and loaded.updated_at > 0
    assert sm.delete("youtube") and sm.list() == []


def test_load_missing_returns_empty_named_session(tmp_path):
    sm = SessionManager(root=tmp_path)
    s = sm.load("fresh")
    assert s.name == "fresh" and s.cookies == [] and s.storage_state == {}


def test_corrupt_session_file_starts_clean(tmp_path):
    sm = SessionManager(root=tmp_path)
    sm.root.mkdir(parents=True, exist_ok=True)
    (tmp_path / "broken.json").write_text("{ not json")
    s = sm.load("broken")            # must not raise
    assert s.name == "broken" and s.cookies == []


def test_name_is_sanitized_for_filesystem(tmp_path):
    sm = SessionManager(root=tmp_path)
    sm.save(SessionState(name="../evil/../x"))
    # nothing escapes the root
    assert all(p.parent == tmp_path for p in tmp_path.rglob("*.json"))


def test_httpx_cookie_bridge_roundtrip():
    state = SessionState(name="s", cookies=[{"name": "A", "value": "1",
                                             "domain": "ex.com", "path": "/"}])
    jar = to_httpx_cookies(state)
    assert jar.get("A", domain="ex.com") == "1"


def test_http_tier_sends_and_captures_cookies():
    seen = {}

    def handler(request: httpx.Request):
        seen["cookie"] = request.headers.get("cookie", "")
        return httpx.Response(200, headers={"set-cookie": "NEW=xyz; Path=/"},
                              text="<title>ok</title>")

    tier = HttpTier(transport=httpx.MockTransport(handler))
    state = SessionState(name="s", cookies=[{"name": "OLD", "value": "1",
                                             "domain": "site.test", "path": "/"}])
    tier.open("http://site.test/", session=state)
    assert "OLD=1" in seen["cookie"]                       # sent existing cookie
    assert any(c["name"] == "NEW" and c["value"] == "xyz"  # captured Set-Cookie
               for c in state.cookies)


def test_service_open_persists_named_session(tmp_path):
    def handler(request):
        return httpx.Response(200, headers={"set-cookie": "TOKEN=t1; Path=/"},
                              text="<title>hi</title>")
    tier = HttpTier(transport=httpx.MockTransport(handler))
    sm = SessionManager(root=tmp_path)
    svc = BrowserService(tiers=[tier], sessions=sm)
    page = svc.open("http://site.test/", session="acct")
    assert page.ok
    # session was created + persisted with the captured cookie
    reloaded = sm.load("acct")
    assert any(c["name"] == "TOKEN" for c in reloaded.cookies)


def test_open_without_session_passes_none(tmp_path):
    def handler(request):
        return httpx.Response(200, text="<title>x</title>")
    tier = HttpTier(transport=httpx.MockTransport(handler))
    svc = BrowserService(tiers=[tier], sessions=SessionManager(root=tmp_path))
    svc.open("http://x/")
    assert svc.sessions.list() == []      # no session file written
