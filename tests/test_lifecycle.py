"""Lifecycle Engine tests (SES-019A Parts 1 & 6) — AP-12.

The load-bearing guarantee under test: PERMANENT files are never deleted,
even when nested inside a job directory full of disposable output
(SES-019A AC-004). Also covers the archive upload-gate, manifest-missing
skip, and freed-bytes accounting. Operates entirely in a temp dir.
"""
import json
from pathlib import Path

import pytest

from saathi.storage import LifecycleEngine, LifecycleClass


@pytest.fixture
def engine():
    return LifecycleEngine()


def _write(p: Path, content: str = "x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# --- the cardinal guard --------------------------------------------------
def test_permanent_is_never_deletable(engine, tmp_path):
    f = _write(tmp_path / "saathi.db", "important")
    res = engine.delete(f, LifecycleClass.PERMANENT)
    assert res.deleted is False
    assert "permanent" in res.reason
    assert f.exists()   # still there


def test_archive_requires_verified_upload(engine, tmp_path):
    f = _write(tmp_path / "final.mp4")
    # not verified → refused
    assert engine.delete(f, LifecycleClass.ARCHIVE, upload_verified=False).deleted is False
    assert f.exists()
    # verified → allowed
    res = engine.delete(f, LifecycleClass.ARCHIVE, upload_verified=True)
    assert res.deleted is True
    assert not f.exists()


def test_disposable_and_temporary_delete_freely(engine, tmp_path):
    for cls in (LifecycleClass.DISPOSABLE, LifecycleClass.TEMPORARY, LifecycleClass.WORKING):
        f = _write(tmp_path / f"{cls.value}.tmp", "data")
        res = engine.delete(f, cls)
        assert res.deleted is True, cls
        assert res.freed_bytes == 4


def test_cleanup_job_never_touches_permanent_nested_in_temp(engine, tmp_path):
    """AC-004: a permanent-class file living inside a job's temp tree survives."""
    job = tmp_path / "jobs" / "2026-07-02_001"
    _write(job / "frames" / "f001.png", "frame")           # temporary
    _write(job / "cache" / "c.bin", "cache")               # disposable
    _write(job / "output" / "final.mp4", "video")          # archive
    _write(job / "output" / "metadata.json", "{}")         # permanent
    (job / "manifest.json").write_text(json.dumps({
        "job_id": "2026-07-02_001",
        "upload_verified": True,
        "files": {
            "frames/":              {"class": "temporary"},
            "cache/":               {"class": "disposable"},
            "output/final.mp4":     {"class": "archive"},
            "output/metadata.json": {"class": "permanent"},
        },
    }))

    result = engine.cleanup_job(job)

    assert result.ok
    assert not (job / "frames").exists()
    assert not (job / "cache").exists()
    assert not (job / "output" / "final.mp4").exists()      # archive, verified → gone
    assert (job / "output" / "metadata.json").exists()      # PERMANENT → survives
    assert result.freed_bytes > 0


def test_cleanup_job_skips_when_manifest_missing(engine, tmp_path):
    job = tmp_path / "jobs" / "no_manifest"
    _write(job / "frames" / "f.png", "frame")
    result = engine.cleanup_job(job)
    assert result.ok is False
    assert "missing" in result.skipped_reason
    assert (job / "frames" / "f.png").exists()   # nothing guessed at / deleted


def test_cleanup_job_skips_on_corrupt_manifest(engine, tmp_path):
    job = tmp_path / "jobs" / "bad_manifest"
    _write(job / "frames" / "f.png", "frame")
    (job / "manifest.json").write_text("{ this is not json")
    result = engine.cleanup_job(job)
    assert result.ok is False
    assert "unreadable" in result.skipped_reason
    assert (job / "frames" / "f.png").exists()
