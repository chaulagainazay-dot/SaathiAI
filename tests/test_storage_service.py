"""Storage Service integration test (SES-019A) — the whole capability wired
together on one Event Fabric, end-to-end, no threads/real Telegram.

Proves: a watchdog tick flows through the bus to both Mission Control and
the injected Telegram sender, and the 95% emergency hook triggers a real
cleanup pass.
"""
import json

from saathi.events import EventBus
from saathi.storage.service import StorageService
from saathi.storage import watchdog as wd_mod


def test_service_wires_watchdog_to_dashboard_and_telegram(tmp_path, monkeypatch):
    sent = []
    bus = EventBus()
    svc = StorageService(tmp_path, bus=bus, telegram_send=sent.append)

    # Force the watchdog to see a 96% disk (critical) regardless of real disk.
    monkeypatch.setattr(svc.watchdog, "_read",
                        lambda: wd_mod.DiskUsage(total=100, used=96, free=4))
    svc.tick()

    # Mission Control updated via the fabric...
    snap = svc.snapshot()
    assert snap["storage"]["emergency"] is True
    assert snap["storage"]["rendering_paused"] is True
    # ...and a Telegram alert was formatted + sent.
    assert any("CRITICAL" in m for m in sent)


def test_emergency_hook_runs_real_cleanup(tmp_path, monkeypatch):
    bus = EventBus()
    svc = StorageService(tmp_path, bus=bus)

    # Stage a completed job with deletable frames.
    job = tmp_path / "temp" / "jobs" / "j1"
    (job / "frames").mkdir(parents=True)
    (job / "frames" / "f.png").write_text("frame")
    (job / "manifest.json").write_text(json.dumps({
        "job_id": "j1", "upload_verified": True,
        "files": {"frames/": {"class": "temporary"}},
    }))

    monkeypatch.setattr(svc.watchdog, "_read",
                        lambda: wd_mod.DiskUsage(total=100, used=96, free=4))
    svc.tick()   # 96% → emergency → _emergency_cleanup → cleanup.nightly()

    assert not (job / "frames").exists()   # cleanup actually ran
    assert svc.db.recent_cleanup_runs()    # audit row written
