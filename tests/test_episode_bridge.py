"""Event → Episode bridge (M5.1 sprint, Audit 4)."""
from saathi.events import EventBus
from saathi import episode_bridge


def test_infra_events_become_episodes():
    bus = EventBus()
    recorded = []
    episode_bridge.install(bus, record_episode=lambda **kw: recorded.append(kw) or 1)

    bus.publish_sync("conversation.completed", {"session": "web:1", "intent": "chat"})
    bus.publish_sync("connector.executed", {"connector": "telegram", "capability": "send_text"})
    bus.publish_sync("browser.finished", {"url": "http://x", "ok": True, "tier": "HTTP"})

    intents = {r["intent"] for r in recorded}
    assert intents == {"conversation", "connector_execute", "browser_fetch"}
    assert all(r["agent"] == "infrastructure" for r in recorded)


def test_failed_fetch_records_failure_outcome():
    bus = EventBus()
    recorded = []
    episode_bridge.install(bus, record_episode=lambda **kw: recorded.append(kw) or 1)
    bus.publish_sync("browser.finished", {"url": "http://x", "ok": False, "error": "boom"})
    assert recorded[0]["outcome"] == "failure"


def test_uninstall_stops_recording():
    bus = EventBus()
    recorded = []
    off = episode_bridge.install(bus, record_episode=lambda **kw: recorded.append(kw) or 1)
    off()
    bus.publish_sync("connector.executed", {"connector": "github"})
    assert recorded == []


def test_broken_recorder_never_breaks_publish():
    bus = EventBus()
    def boom(**kw):
        raise RuntimeError("recorder down")
    episode_bridge.install(bus, record_episode=boom)
    # must not raise
    report = bus.publish_sync("conversation.completed", {"session": "x"})
    assert report is not None
