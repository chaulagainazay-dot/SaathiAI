"""publish_video — API→Human ranked fallback + Human-mode connector."""
import pytest

from saathi.infrastructure.connectors import (
    ConnectorRegistry, Connector, ConnectorMetadata, Health, Status,
    ConnectorEvent, AuthRequired, HumanPublishConnector,
)


class FakeConn(Connector):
    def __init__(self, cid, caps, reliability, *, fail=None):
        self.id, self._caps, self._rel, self._fail = cid, frozenset(caps), reliability, fail
    def manifest(self):
        return ConnectorMetadata(id=self.id, capabilities=self._caps, requires_auth=False,
                                 reliability=self._rel)
    def authenticate(self): return True
    def health(self): return Health(Status.OK)
    def execute(self, capability, **payload):
        self._require(capability)
        if self._fail:
            raise self._fail("mode unavailable")
        return {"by": self.id, **payload}


class Bus:
    def __init__(self): self.events = []
    def publish_sync(self, n, p): self.events.append((n, p))


def test_ranked_orders_api_before_human():
    reg = ConnectorRegistry()
    reg.register(FakeConn("human", ["publish_video"], 0.75))
    reg.register(FakeConn("api", ["publish_video"], 0.96))
    assert [c.id for c in reg.ranked("publish_video")] == ["api", "human"]


def test_execute_falls_through_api_to_human():
    bus = Bus()
    reg = ConnectorRegistry(bus=bus)
    reg.register(FakeConn("youtube_api", ["publish_video"], 0.96, fail=AuthRequired))  # no OAuth
    reg.register(FakeConn("human_publish", ["publish_video"], 0.75))                   # logged-in Chrome
    out = reg.execute(capability="publish_video", path="clip.mp4")
    assert out["by"] == "human_publish" and out["path"] == "clip.mp4"
    names = [e[0] for e in bus.events]
    assert ConnectorEvent.AUTH_REQUIRED.value in names        # API tried + failed
    assert ConnectorEvent.DEGRADED.value in names             # fell back
    assert ConnectorEvent.EXECUTED.value in names             # human succeeded


def test_execute_raises_when_all_modes_fail():
    reg = ConnectorRegistry()
    reg.register(FakeConn("api", ["publish_video"], 0.96, fail=AuthRequired))
    reg.register(FakeConn("human", ["publish_video"], 0.75, fail=RuntimeError))
    with pytest.raises(Exception):
        reg.execute(capability="publish_video")


# ── Human-mode connector ─────────────────────────────────────────────────────
class FakeProxy:
    def __init__(self, ok=True): self._ok = ok
    def available(self): return self._ok
    def execute(self, capability, *, profile="", **payload):
        return {"published": capability, "profile": profile, **payload}


def test_human_publish_gated_on_secret(monkeypatch):
    monkeypatch.delenv("HUMAN_BROWSER_SECRET", raising=False)
    c = HumanPublishConnector(proxy=FakeProxy())
    assert c.authenticate() is False and c.health().status is Status.AUTH_REQUIRED


def test_human_publish_routes_to_proxy(monkeypatch):
    monkeypatch.setenv("HUMAN_BROWSER_SECRET", "s3cr3t")
    c = HumanPublishConnector(proxy=FakeProxy())
    assert c.authenticate() is True
    r = c.execute("publish_video", path="clip.mp4", title="Mr Yeti", profile="ajay/youtube")
    assert r["published"] == "publish_video" and r["profile"] == "ajay/youtube" and r["title"] == "Mr Yeti"


def test_human_publish_default_profile(monkeypatch):
    monkeypatch.setenv("HUMAN_BROWSER_SECRET", "s3cr3t")
    c = HumanPublishConnector(proxy=FakeProxy(), default_profile="ajay/youtube")
    r = c.execute("publish_video", path="x.mp4")
    assert r["profile"] == "ajay/youtube"
