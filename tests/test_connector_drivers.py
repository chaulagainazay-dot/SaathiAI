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
        # base already carries the webhook segment; workflow appended directly
        assert req.url.path == "/webhook/daily-content"
        return httpx.Response(200, headers={"content-type": "application/json"},
                              json={"executed": True})
    n8n = N8nConnector(base_url="https://n8n.test/webhook",
                       transport=httpx.MockTransport(handler))
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
def test_youtube_search_forwards_params():
    def handler(req):
        assert req.url.path.endswith("/search")
        assert req.url.params.get("q") == "ielts tips"       # caller's params forwarded
        assert req.url.params.get("order") == "viewCount"
        assert req.url.params.get("key") == "AIza-x"
        return httpx.Response(200, json={"items": [{"id": {"videoId": "abc"}}]})
    yt = YouTubeConnector(api_key="AIza-x", transport=httpx.MockTransport(handler))
    out = yt.execute("search", q="ielts tips", part="snippet", order="viewCount", type="video")
    assert out["items"][0]["id"]["videoId"] == "abc"


def test_youtube_upload_requires_oauth():
    yt = YouTubeConnector(api_key="AIza-x")           # no oauth token
    with pytest.raises(AuthRequired):
        yt.execute("upload_video", title="x", file="y.mp4")


def test_youtube_list_comments_path():
    def handler(req):
        assert req.url.path.endswith("/commentThreads")
        assert req.url.params.get("videoId") == "vid1"
        return httpx.Response(200, json={"items": []})
    yt = YouTubeConnector(api_key="AIza-x", transport=httpx.MockTransport(handler))
    assert yt.execute("list_comments", videoId="vid1", part="snippet")["items"] == []


def test_youtube_reads_alternate_env_key(monkeypatch):
    monkeypatch.delenv("YT_API_KEY", raising=False)
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-alt")
    assert YouTubeConnector().authenticate()          # falls back to YOUTUBE_API_KEY


# ── new driver capabilities added during the caller migration ───────────────
def test_telegram_get_updates():
    from saathi.infrastructure.connectors import TelegramConnector
    def handler(req):
        assert req.url.path.endswith("/getUpdates")
        return httpx.Response(200, json={"result": [{"update_id": 5}]})
    tg = TelegramConnector(token="1:a", chat_id="9", transport=httpx.MockTransport(handler))
    assert tg.execute("get_updates", offset=None, timeout=50)["result"][0]["update_id"] == 5


def test_telegram_send_video_multipart(tmp_path):
    from saathi.infrastructure.connectors import TelegramConnector
    vid = tmp_path / "clip.mp4"; vid.write_bytes(b"\x00\x01video")
    seen = {}
    def handler(req):
        seen["path"] = req.url.path
        seen["multipart"] = req.headers.get("content-type", "").startswith("multipart/")
        return httpx.Response(200, json={"ok": True})
    tg = TelegramConnector(token="1:a", chat_id="9", transport=httpx.MockTransport(handler))
    tg.execute("send_video", caption="hi", file_path=str(vid))
    assert seen["path"].endswith("/sendVideo") and seen["multipart"]


def test_github_actions_capabilities():
    calls = []
    def handler(req):
        calls.append(req.url.path)
        if req.url.path.endswith("/runs") and "workflows" in req.url.path:
            return httpx.Response(200, json={"workflow_runs": [{"id": 42}]})
        return httpx.Response(200, json={"jobs": [{"name": "build"}]})
    from saathi.infrastructure.connectors import GitHubConnector
    gh = GitHubConnector(token="ghp_x", transport=httpx.MockTransport(handler))
    runs = gh.execute("list_workflow_runs", repo_full="ajay/pielts", workflow="deploy.yml")
    assert runs["workflow_runs"][0]["id"] == 42
    jobs = gh.execute("list_run_jobs", repo_full="ajay/pielts", run_id=42)
    assert jobs["jobs"][0]["name"] == "build"


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
