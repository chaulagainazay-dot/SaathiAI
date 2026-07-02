"""Cleanup Engine tests (SES-019A Part 9) — AP-12.

Verifies the Cleanup Engine executes only Lifecycle-authorized deletions,
supports dry-run, detects orphans and failed jobs, protects PERMANENT files,
writes an audit row, and emits storage.cleanup.* / storage.lifecycle.* events.
All against a temp storage tree with an injected clock + event bus.
"""
import json
from pathlib import Path

from saathi.storage import StorageDB, LifecycleEngine, CleanupEngine
from saathi.events import EventBus, WILDCARD


def _job(root: Path, name: str, *, verified=True, mtime=None, manifest=True):
    d = root / "temp" / "jobs" / name
    (d / "frames").mkdir(parents=True, exist_ok=True)
    (d / "frames" / "f.png").write_text("frame")
    (d / "output").mkdir(parents=True, exist_ok=True)
    (d / "output" / "metadata.json").write_text("{}")   # permanent
    if manifest:
        m = d / "manifest.json"
        m.write_text(json.dumps({
            "job_id": name,
            "upload_verified": verified,
            "files": {
                "frames/": {"class": "temporary"},
                "output/metadata.json": {"class": "permanent"},
            },
        }))
        if mtime is not None:
            import os
            os.utime(m, (mtime, mtime))
    return d


def _engine(tmp_path, now=1_000_000.0, publish=None, dry_run=False):
    db = StorageDB(str(tmp_path / "s.db"))
    lifecycle = LifecycleEngine()
    eng = CleanupEngine(tmp_path, lifecycle, db, now=lambda: now, publish=publish, dry_run=dry_run)
    return eng, db


def test_nightly_deletes_temporary_keeps_permanent(tmp_path):
    _job(tmp_path, "j1")
    eng, db = _engine(tmp_path)
    run = eng.nightly()
    assert run.ok
    assert run.files_deleted == 1        # frames/
    assert run.files_protected == 1      # metadata.json (permanent)
    assert not (tmp_path / "temp/jobs/j1/frames").exists()
    assert (tmp_path / "temp/jobs/j1/output/metadata.json").exists()
    # audit row written
    runs = db.recent_cleanup_runs()
    assert runs and runs[0]["run_kind"] == "nightly"
    assert runs[0]["files_deleted"] == 1


def test_dry_run_deletes_nothing_but_reports(tmp_path):
    _job(tmp_path, "j1")
    eng, db = _engine(tmp_path, dry_run=True)
    run = eng.nightly()
    assert run.dry_run is True
    assert run.files_deleted == 0        # nothing actually deleted
    assert run.bytes_freed == 0
    assert (tmp_path / "temp/jobs/j1/frames").exists()   # still there
    assert db.recent_cleanup_runs()[0]["dry_run"] == 1


def test_orphan_detection_never_deletes(tmp_path):
    _job(tmp_path, "orphan", manifest=False)   # no manifest.json
    eng, _ = _engine(tmp_path)
    orphans = eng.find_orphans()
    assert len(orphans) == 1
    run = eng.nightly()
    # orphan surfaced, not deleted
    assert any("orphan" in o for o in run.orphans)
    assert (tmp_path / "temp/jobs/orphan/frames/f.png").exists()


def test_failed_job_cleanup_respects_age(tmp_path):
    now = 1_000_000.0
    _job(tmp_path, "old", mtime=now - 48 * 3600)   # 48h old → failed
    _job(tmp_path, "fresh", mtime=now - 1 * 3600)  # 1h old → keep
    eng, _ = _engine(tmp_path, now=now)
    failed = eng.find_failed_jobs()
    names = [p.name for p in failed]
    assert "old" in names and "fresh" not in names
    run = eng.hourly()
    assert run.jobs_scanned == 1                    # only the old one


def test_events_emitted(tmp_path):
    bus = EventBus()
    seen = []
    bus.subscribe(WILDCARD, lambda e: seen.append(e.name))
    _job(tmp_path, "j1")
    eng, _ = _engine(tmp_path, publish=bus.publish_sync)
    eng.nightly()
    assert "storage.cleanup.started" in seen
    assert "storage.cleanup.finished" in seen
    assert "storage.lifecycle.deleted" in seen
    assert "storage.lifecycle.protected" in seen


def test_cleanup_never_decides_uses_lifecycle_authorization(tmp_path):
    """Archive file with unverified upload must NOT be deleted — the Lifecycle
    Engine refuses, and the Cleanup Engine obeys."""
    d = tmp_path / "temp" / "jobs" / "j2"
    (d / "output").mkdir(parents=True)
    (d / "output" / "final.mp4").write_text("video")
    (d / "manifest.json").write_text(json.dumps({
        "job_id": "j2",
        "upload_verified": False,               # not yet in the cloud
        "files": {"output/final.mp4": {"class": "archive"}},
    }))
    eng, _ = _engine(tmp_path)
    run = eng.nightly()
    assert run.files_deleted == 0
    assert (d / "output" / "final.mp4").exists()   # protected until verified
