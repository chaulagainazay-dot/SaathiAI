"""Storage Telegram alert tests (SES-019A Part 7) — AP-12.

The sender is injected (a list append), so no real Telegram call is made.
Verifies message formatting and that alerts fire end-to-end when the Disk
Watchdog publishes through the bus.
"""
from saathi.events import EventBus
from saathi.storage import StorageDB, DiskWatchdog, DiskUsage
from saathi.storage.alerts import (
    StorageAlerts, format_warning, format_render_blocked,
)


def test_warning_message_has_key_fields():
    msg = format_warning({
        "disk_pct": 0.918, "recoverable_bytes": 18.4e9,
        "cleanup_scheduled": "02:00", "active_jobs": 7,
    })
    assert "⚠️ Storage Warning" in msg
    assert "91.8%" in msg
    assert "Rendering Paused" in msg
    assert "18.4 GB" in msg
    assert "Cleanup Scheduled: 02:00" in msg
    assert "Current Jobs: 7" in msg
    assert "/cleanup" in msg and "/status" in msg and "/override" in msg


def test_render_blocked_message():
    msg = format_render_blocked({
        "required_bytes": 29e9, "free_bytes": 22e9, "shortfall_bytes": 7e9,
    })
    assert "29.0 GB" in msg and "22.0 GB" in msg and "7.0 GB" in msg


def test_alerts_fire_from_watchdog_via_bus(tmp_path):
    sent: list[str] = []
    bus = EventBus()
    StorageAlerts(send=sent.append).register(bus)

    db = StorageDB(str(tmp_path / "s.db"))
    wd = DiskWatchdog(
        db,
        usage_reader=lambda: DiskUsage(total=100, used=92, free=8),  # 92% → warning
        publish=bus.publish_sync,
    )
    wd.check()
    assert any("Storage Warning" in m for m in sent)


def test_critical_alert(tmp_path):
    sent: list[str] = []
    bus = EventBus()
    StorageAlerts(send=sent.append).register(bus)

    db = StorageDB(str(tmp_path / "s.db"))
    wd = DiskWatchdog(
        db,
        usage_reader=lambda: DiskUsage(total=100, used=97, free=3),  # 97% → critical
        publish=bus.publish_sync,
    )
    wd.check()
    assert any("CRITICAL" in m for m in sent)
