"""Mission Control event-first tests (AP-13) — the dashboard state is updated
by Event Fabric events, never by polling. Also proves the end-to-end path:
Disk Watchdog → Event Fabric → Mission Control → (snapshot the dashboard reads).
"""
from saathi.events import EventBus, STORAGE_EVENTS
from saathi.mission_control import MissionControlState
from saathi.storage import StorageDB, DiskWatchdog, DiskUsage


def test_snapshot_updates_from_storage_events():
    bus = EventBus()
    mc = MissionControlState()
    mc.register(bus)

    bus.publish_sync("storage_warning", {"disk_pct": 0.91})
    snap = mc.snapshot()
    assert snap["storage"]["disk_pct"] == 0.91
    assert snap["storage"]["rendering_paused"] is True
    assert snap["storage"]["emergency"] is False

    bus.publish_sync("storage_critical", {"disk_pct": 0.97})
    assert mc.snapshot()["storage"]["emergency"] is True


def test_render_and_cleanup_counters():
    bus = EventBus()
    mc = MissionControlState()
    mc.register(bus)

    bus.publish_sync(STORAGE_EVENTS["render_allowed"], {})
    bus.publish_sync(STORAGE_EVENTS["render_allowed"], {})
    bus.publish_sync(STORAGE_EVENTS["render_blocked"], {})
    bus.publish_sync(STORAGE_EVENTS["cleanup_finished"], {"kind": "nightly", "bytes_freed": 5_000_000})

    s = mc.snapshot()["storage"]
    assert s["renders_allowed"] == 2
    assert s["renders_blocked"] == 1
    assert s["last_cleanup_kind"] == "nightly"
    assert s["last_cleanup_freed_bytes"] == 5_000_000


def test_recent_events_and_counts():
    bus = EventBus()
    mc = MissionControlState()
    mc.register(bus)
    for _ in range(3):
        bus.publish_sync("storage_warning", {"disk_pct": 0.9})
    snap = mc.snapshot()
    assert snap["event_counts"]["storage_warning"] == 3
    assert snap["recent_events"][0]["name"] == "storage_warning"


def test_end_to_end_watchdog_to_mission_control(tmp_path):
    """The whole event-first path with no direct calls between subsystems."""
    bus = EventBus()
    mc = MissionControlState()
    mc.register(bus)

    db = StorageDB(str(tmp_path / "s.db"))
    wd = DiskWatchdog(
        db,
        usage_reader=lambda: DiskUsage(total=100, used=96, free=4),  # 96% → critical
        publish=bus.publish_sync,
    )
    wd.check()

    snap = mc.snapshot()
    assert snap["storage"]["emergency"] is True
    assert snap["storage"]["rendering_paused"] is True
