"""Storage Intelligence tests (SES-019A) — unit + failure-recovery, AP-12.

Drives the Disk Watchdog with a fake usage reader so no real disk is touched.
Verifies the escalation ladder, edge-triggered alerts, resume, event
persistence, and the predictive safe-to-render gate.
"""
import os
import tempfile

from saathi.storage import StorageDB, DiskWatchdog, DiskUsage, WatchdogLevel


def _mk(free_frac: float, total: int = 100) -> DiskUsage:
    free = int(total * free_frac)
    return DiskUsage(total=total, used=total - free, free=free)


def _db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return StorageDB(path)


def test_levels_map_to_thresholds():
    wd = DiskWatchdog(_db())
    assert wd.level_for(0.50) is WatchdogLevel.OK
    assert wd.level_for(0.80) is WatchdogLevel.NOTIFY
    assert wd.level_for(0.90) is WatchdogLevel.PAUSE
    assert wd.level_for(0.95) is WatchdogLevel.EMERGENCY
    assert wd.level_for(0.99) is WatchdogLevel.EMERGENCY


def test_pause_fires_once_and_records_event():
    usage = {"u": _mk(free_frac=0.05)}  # 95% used → but test the 90% path first
    usage["u"] = _mk(free_frac=0.08)     # 92% used → PAUSE
    calls = {"pause": 0, "alerts": []}
    db = _db()
    wd = DiskWatchdog(
        db,
        usage_reader=lambda: usage["u"],
        on_alert=lambda m: calls["alerts"].append(m),
        on_pause=lambda: calls.__setitem__("pause", calls["pause"] + 1),
    )
    assert wd.check() is WatchdogLevel.PAUSE
    assert wd.check() is WatchdogLevel.PAUSE   # still paused, no re-fire
    assert calls["pause"] == 1                  # edge-triggered, fired once
    assert wd.rendering_paused is True
    events = [e["event_type"] for e in db.recent_watchdog_events()]
    assert events.count("pause") == 1


def test_emergency_triggers_cleanup_and_pause():
    calls = {"emergency": 0, "pause": 0}
    db = _db()
    wd = DiskWatchdog(
        db,
        usage_reader=lambda: _mk(free_frac=0.02),  # 98% used
        on_pause=lambda: calls.__setitem__("pause", calls["pause"] + 1),
        on_emergency=lambda: calls.__setitem__("emergency", calls["emergency"] + 1),
    )
    assert wd.check() is WatchdogLevel.EMERGENCY
    assert wd.emergency_active is True
    assert wd.rendering_paused is True
    assert calls["emergency"] == 1
    assert calls["pause"] == 1


def test_resume_fires_when_space_recovers():
    state = {"u": _mk(free_frac=0.08)}  # start paused (92% used)
    calls = {"resume": 0}
    db = _db()
    wd = DiskWatchdog(
        db,
        usage_reader=lambda: state["u"],
        on_resume=lambda: calls.__setitem__("resume", calls["resume"] + 1),
    )
    wd.check()
    assert wd.rendering_paused is True
    state["u"] = _mk(free_frac=0.50)   # cleanup freed space → 50% used
    assert wd.check() is WatchdogLevel.OK
    assert wd.rendering_paused is False
    assert calls["resume"] == 1
    assert any(e["event_type"] == "resume" for e in db.recent_watchdog_events())


def test_safe_to_render_gate():
    db = _db()
    wd = DiskWatchdog(db, usage_reader=lambda: _mk(free_frac=0.50, total=100))
    # 50 free, 90% line is at 90 used → room for 40 before hitting pause line
    assert wd.safe_to_render(30) is True
    assert wd.safe_to_render(45) is False


def test_peak_tracking():
    state = {"u": _mk(free_frac=0.15)}  # 85% used → notify
    db = _db()
    wd = DiskWatchdog(db, usage_reader=lambda: state["u"])
    wd.check()
    state["u"] = _mk(free_frac=0.05)    # 95% → emergency
    wd.check()
    assert db.peak_disk_pct_since(0) >= 0.95
