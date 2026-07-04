"""Automation Center backend — flight recorder, health score, status, publish-records."""
import time

from saathi.infrastructure.human_browser import RunStore, automation, publish
from saathi.infrastructure.human_browser.queue import InMemoryQueue


def test_run_store_record_get_list(tmp_path):
    store = RunStore(db_path=str(tmp_path / "runs.db"))
    rid = store.record(workflow="youtube_upload", profile="ajay/youtube", capability="publish_video",
                       title="Ep1", ok=True, video_url="https://youtu.be/x", duration_ms=41000,
                       timeline=[{"action": "goto"}, {"action": "publish"}])
    got = store.get(rid)
    assert got["ok"] is True and got["video_url"] == "https://youtu.be/x"
    assert got["timeline"][-1]["action"] == "publish"
    assert store.list()[0]["id"] == rid


def test_stats_success_rate_and_last_success(tmp_path):
    store = RunStore(db_path=str(tmp_path / "runs.db"))
    store.record(capability="publish_video", ok=True, duration_ms=30000)
    store.record(capability="publish_video", ok=True, duration_ms=50000)
    store.record(capability="publish_video", ok=False, error="selector not found")
    s = store.stats(window_hours=24)
    assert s["runs"] == 3 and s["successes"] == 2 and s["failures"] == 1
    assert round(s["success_rate"], 2) == 0.67 and s["avg_duration_ms"] == 40000
    assert s["last_success"] is not None


def test_status_health_blends_reliability_and_readiness(tmp_path, monkeypatch):
    store = RunStore(db_path=str(tmp_path / "runs.db"))
    store.record(ok=True, duration_ms=37000)
    q = InMemoryQueue(); q.claim()                       # simulate a fresh agent poll
    monkeypatch.setenv("HUMAN_BROWSER_SECRET", "s")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")         # vision ready
    snap = automation.status(queue=q, store=store)
    assert snap["components"]["agent"]["online"] is True
    assert snap["components"]["vision"]["ready"] is True
    assert snap["components"]["queue"]["ready"] is True
    assert snap["health"]["overall"] == 100              # 100% success + all ready
    assert snap["recent_runs"]


def test_status_marks_agent_offline_when_stale(tmp_path, monkeypatch):
    store = RunStore(db_path=str(tmp_path / "runs.db"))
    q = InMemoryQueue()
    q._last_claim = time.time() - 300                    # last poll 5 min ago
    monkeypatch.delenv("HUMAN_BROWSER_SECRET", raising=False)
    snap = automation.status(queue=q, store=store)
    assert snap["components"]["agent"]["online"] is False


class FakeReg:
    def __init__(self, result=None, err=None): self._r, self._e = result, err
    def execute(self, *, capability, **p):
        if self._e: raise self._e
        return self._r


def test_publish_records_success_and_failure(tmp_path):
    store = RunStore(db_path=str(tmp_path / "runs.db"))
    publish(FakeReg(result={"video_url": "https://youtu.be/x", "timeline": [{"action": "publish"}]}),
            store=store, title="Ep1", profile="ajay/youtube")
    try:
        publish(FakeReg(err=RuntimeError("all modes down")), store=store, title="Ep2")
    except RuntimeError:
        pass
    runs = store.list()
    assert len(runs) == 2
    assert any(r["ok"] and r["title"] == "Ep1" for r in runs)
    assert any((not r["ok"]) and r["title"] == "Ep2" for r in runs)
