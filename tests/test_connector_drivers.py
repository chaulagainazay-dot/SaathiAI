"""Phase 1.3 drivers — Filesystem, n8n, Browser-as-connector, YouTube + manifest."""
import httpx
import pytest

from saathi.infrastructure.connectors import (
    Manifest, Status, AuthRequired, install_defaults, ConnectorRegistry,
    FilesystemConnector, N8nConnector, BrowserConnector, YouTubeConnector,
)


# ── Manifest ────────────────────────────────────────────────────────────────
def test_manifest_from_nested_dict():
    m = Manifest.from_dict({
        "id": "telegram", "display_name": "Telegram", "category": "messaging",
        "supports": ["send_text", "send_video"], "permissions": ["outbound", "inbound"],
        "requires_auth": True, "rate_limits": {"requests_per_second": 30},
        "cost": {"per_request": 0}, "priority": {"reliability": 0.99, "latency": "low"},
        "health_checks": ["token", "api"],
    })
    assert m.id == "telegram" and m.category == "messaging"
    assert m.supports("send_video") and "inbound" in m.permissions
    assert m.reliability == 0.99 and m.latency_rank == 1
    assert m.rate_limits["requests_per_second"] == 30
    assert m.as_dict()["priority"]["reliability"] == 0.99


# ── Filesystem ──────────────────────────────────────────────────────────────
def test_filesystem_write_read_checksum_move_list(tmp_path):
    fs = FilesystemConnector(root=str(tmp_path))
    fs.execute("write", path="a/b.txt", content="hello")
    assert fs.execute("read", path="a/b.txt") == "hello"
    digest = fs.execute("checksum", path="a/b.txt")
    assert len(digest) == 64
    assert fs.execute("list", path="a") == ["b.txt"]
    fs.execute("move", src="a/b.txt", dest="c/d.txt")
    assert fs.execute("read", path="c/d.txt") == "hello"
    watch = fs.execute("watch", path="c/d.txt")
    assert watch["exists"] and watch["size"] == 5


def test_filesystem_sandbox_blocks_escape(tmp_path):
    fs = FilesystemConnector(root=str(tmp_path))
    with pytest.raises(Exception):
        fs.execute("read", path="../../etc/passwd")


def test_filesystem_needs_no_auth(tmp_path):
    fs = FilesystemConnector(root=str(tmp_path))
    assert fs.authenticate() and fs.manifest().requires_auth is False
    assert fs.health().status is Status.OK


# ── n8n ─────────────────────────────────────────────────────────────────────
def test_n8n_auth_and_trigger():
    def handler(req):
        if req.url.path.startswith("/webhook/"):
            return httpx.Response(200, json={"executed": True})
        return httpx.Response(200)
    n8n = N8nConnector(base_url="https://n8n.test", transport=httpx.MockTransport(handler))
    assert n8n.authenticate()
    out = n8n.execute("trigger_workflow", path="daily-content", data={"topic": "ielts"})
    assert out == {"executed": True}


def test_n8n_missing_base_is_auth_required():
    assert N8nConnector(base_url="").health().status is Status.AUTH_REQUIRED


# ── Browser-as-connector ────────────────────────────────────────────────────
class FakeBrowser:
    def tiers_status(self): return {"http": True, "playwright": False, "camofox": False}
    def open(self, url, **kw): return {"url": url, "opened": True}
    def search(self, query, **kw): return [{"title": query}]


def test_browser_connector_wraps_service():
    bc = BrowserConnector(service=FakeBrowser())
    assert bc.authenticate()
    assert bc.health().status is Status.OK
    assert bc.execute("fetch", url="http://x")["opened"] is True
    assert bc.execute("search", query="ielts")[0]["title"] == "ielts"


def test_browser_connector_down_when_no_tiers():
    class Dead:
        def tiers_status(self): return {"http": False}
    assert BrowserConnector(service=Dead()).health().status is Status.DOWN


# ── YouTube ─────────────────────────────────────────────────────────────────
def test_youtube_search_read_path():
    def handler(req):
        assert req.url.path.endswith("/search")
        return httpx.Response(200, json={"items": [{"id": {"videoId": "abc"}}]})
    yt = YouTubeConnector(api_key="AIza-x", transport=httpx.MockTransport(handler))
    assert yt.execute("search", query="ielts tips")["items"][0]["id"]["videoId"] == "abc"


def test_youtube_upload_requires_oauth():
    yt = YouTubeConnector(api_key="AIza-x")           # no oauth token
    with pytest.raises(AuthRequired):
        yt.execute("upload_video", title="x", file="y.mp4")


# ── defaults + richer diagnostics ───────────────────────────────────────────
def test_install_defaults_registers_all_six():
    reg = install_defaults(ConnectorRegistry())
    ids = {c.id for c in reg.all()}
    assert ids == {"telegram", "github", "n8n", "browser", "youtube", "filesystem"}


def test_diagnostics_dict_is_first_class(tmp_path):
    diag = FilesystemConnector(root=str(tmp_path)).diagnostics()
    for key in ("healthy", "latency_ms", "authenticated", "last_success",
                "last_error", "capabilities", "category", "display_name"):
        assert key in diag
    assert diag["healthy"] is True and diag["authenticated"] is True
