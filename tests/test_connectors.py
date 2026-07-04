"""Connector Registry (Phase 1.3) — framework + Telegram/GitHub reference drivers."""
import httpx
import pytest

from saathi.infrastructure.connectors import (
    ConnectorRegistry, Connector, ConnectorMetadata, Health, Status,
    ConnectorEvent, AuthRequired, RateLimited, CapabilityUnsupported,
    TelegramConnector, GitHubConnector, diagnostics,
)


# ── a controllable fake connector ───────────────────────────────────────────
class FakeConnector(Connector):
    def __init__(self, cid, caps, *, status=Status.OK, reliability=0.9, cost=0.0,
                 latency="low", auth=True):
        self.id = cid
        self._caps, self._status, self._rel = frozenset(caps), status, reliability
        self._cost, self._lat, self._auth = cost, latency, auth
        self.calls = []

    def manifest(self):
        return ConnectorMetadata(id=self.id, capabilities=self._caps, requires_auth=True,
                                 cost=self._cost, latency=self._lat, reliability=self._rel)

    def authenticate(self): return self._auth
    def health(self): return Health(self._status)

    def execute(self, capability, **payload):
        self._require(capability)
        self.calls.append((capability, payload))
        return {"ok": self.id}


class FakeBus:
    def __init__(self): self.events = []
    def publish_sync(self, name, payload): self.events.append((name, payload))


# ── registry basics ─────────────────────────────────────────────────────────
def test_register_get_by_capability():
    reg = ConnectorRegistry()
    a = reg.register(FakeConnector("a", ["send_text"]))
    reg.register(FakeConnector("b", ["send_video"]))
    assert reg.get("a") is a
    assert [c.id for c in reg.by_capability("send_text")] == ["a"]
    with pytest.raises(Exception):
        reg.get("nope")


def test_best_prefers_ok_then_reliability_then_cost():
    reg = ConnectorRegistry()
    reg.register(FakeConnector("cheap_degraded", ["gen"], status=Status.DEGRADED, cost=0))
    reg.register(FakeConnector("reliable", ["gen"], status=Status.OK, reliability=0.99, cost=5))
    reg.register(FakeConnector("less_reliable", ["gen"], status=Status.OK, reliability=0.8, cost=0))
    # OK beats DEGRADED; among OK, higher reliability wins even at higher cost
    assert reg.best("gen").id == "reliable"


def test_best_skips_unauthenticated_and_down():
    reg = ConnectorRegistry()
    reg.register(FakeConnector("noauth", ["gen"], auth=False))
    reg.register(FakeConnector("down", ["gen"], status=Status.DOWN))
    assert reg.best("gen") is None


def test_execute_routes_to_best_and_emits_connected():
    bus = FakeBus()
    reg = ConnectorRegistry(bus=bus)
    reg.register(FakeConnector("winner", ["send_text"], reliability=0.99))
    out = reg.execute(capability="send_text", text="hi")
    assert out == {"ok": "winner"}
    assert (ConnectorEvent.EXECUTED.value, {"connector": "winner", "capability": "send_text"}) in bus.events


def test_execute_explicit_connector_id():
    reg = ConnectorRegistry()
    reg.register(FakeConnector("a", ["x"], reliability=0.99))
    b = reg.register(FakeConnector("b", ["x"], reliability=0.5))
    reg.execute(capability="x", connector_id="b")
    assert b.calls and b.calls[0][0] == "x"


def test_unsupported_capability_raises():
    c = FakeConnector("a", ["x"])
    with pytest.raises(CapabilityUnsupported):
        c.execute("y")


def test_health_all_emits_on_transition_only():
    bus = FakeBus()
    reg = ConnectorRegistry(bus=bus)
    reg.register(FakeConnector("c", ["x"], status=Status.DEGRADED))
    reg.health_all(); reg.health_all()            # same status twice
    degraded = [e for e in bus.events if e[0] == ConnectorEvent.DEGRADED.value]
    assert len(degraded) == 1                      # only the first (transition) emits


# ── Telegram reference connector ─────────────────────────────────────────────
def _telegram(handler, **kw):
    return TelegramConnector(token="123:abc", chat_id="999",
                             transport=httpx.MockTransport(handler), **kw)


def test_telegram_auth_and_health():
    def h(req): return httpx.Response(200, json={"result": {"username": "pieltsbot"}})
    tg = _telegram(h)
    assert tg.authenticate()
    health = tg.health()
    assert health.status is Status.OK and "pieltsbot" in health.detail


def test_telegram_missing_token_is_auth_required():
    tg = TelegramConnector(token="", chat_id="1")
    assert tg.authenticate() is False
    assert tg.health().status is Status.AUTH_REQUIRED


def test_telegram_send_text_and_rate_limit():
    sent = {}
    def h(req):
        if req.url.path.endswith("/sendMessage"):
            import json; sent.update(json.loads(req.content))
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(200, json={"result": {}})
    tg = _telegram(h)
    tg.execute("send_text", text="hello")
    assert sent == {"chat_id": "999", "text": "hello"}

    def h429(req): return httpx.Response(429, json={"ok": False})
    with pytest.raises(RateLimited):
        _telegram(h429).execute("send_text", text="x")


# ── GitHub reference connector ───────────────────────────────────────────────
def test_github_health_reports_quota():
    def h(req):
        return httpx.Response(200, json={"resources": {"core": {"remaining": 4000, "limit": 5000}}})
    gh = GitHubConnector(token="ghp_x", transport=httpx.MockTransport(h))
    health = gh.health()
    assert health.status is Status.OK and health.metrics["quota_pct"] == 20  # 20% used → healthy

    def h_low(req):
        return httpx.Response(200, json={"resources": {"core": {"remaining": 100, "limit": 5000}}})
    degraded = GitHubConnector(token="ghp_x", transport=httpx.MockTransport(h_low)).health()
    assert degraded.status is Status.DEGRADED and degraded.metrics["quota_pct"] == 98  # near-exhausted


def test_github_create_issue():
    def h(req):
        assert req.method == "POST" and req.url.path == "/repos/ajay/pielts/issues"
        return httpx.Response(201, json={"number": 7})
    gh = GitHubConnector(token="ghp_x", transport=httpx.MockTransport(h))
    assert gh.execute("create_issue", owner="ajay", repo="pielts", title="bug")["number"] == 7


# ── diagnostics ──────────────────────────────────────────────────────────────
def test_diagnostics_snapshot_has_all_sections():
    reg = ConnectorRegistry()
    reg.register(FakeConnector("telegram", ["send_text"], status=Status.OK))
    snap = diagnostics.snapshot(reg)
    assert set(snap) == {"model_router", "browser", "connectors"}
    assert snap["connectors"][0]["id"] == "telegram" and snap["connectors"][0]["light"] == "🟢"
    assert all("light" in row for row in snap["model_router"])
