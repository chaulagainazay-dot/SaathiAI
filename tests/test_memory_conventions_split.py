"""Curated conventions.md vs runtime learned_conventions.* separation (M17.18.1)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from saathi import config
from saathi.agent import _load_memory
from saathi import scheduler


class _FakeAgent:
    def complete(self, *a, **k):
        return (
            "* Prefer verified voice before privileged actions\n"
            "* Keep posts English-only\n"
            "* Confirm shell scope before running"
        )


def _seed_feedback_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE feedback (kind TEXT, detail TEXT, ts REAL)")
    conn.execute(
        "INSERT INTO feedback VALUES (?,?,?)",
        ("note", "Ajay wants speaker verification before shell", 1.0),
    )
    conn.commit()
    conn.close()


def _patch_reflector_targets(monkeypatch, tmp_path: Path):
    learned_dir = tmp_path / "data" / "memory"
    learned_md = learned_dir / "learned_conventions.md"
    learned_jl = learned_dir / "learned_conventions.jsonl"
    db = tmp_path / "fb.db"
    _seed_feedback_db(db)
    monkeypatch.setattr(config, "LEARNED_MEMORY_DIR", learned_dir)
    monkeypatch.setattr(config, "LEARNED_CONVENTIONS_MD", learned_md)
    monkeypatch.setattr(config, "LEARNED_CONVENTIONS_JSONL", learned_jl)
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr("saathi.agent.SaathiAgent", _FakeAgent)
    return learned_dir, learned_md, learned_jl


def test_learned_paths_live_under_data_memory():
    assert config.LEARNED_MEMORY_DIR == config.ROOT / "data" / "memory"
    assert config.LEARNED_CONVENTIONS_MD.name == "learned_conventions.md"
    assert config.LEARNED_CONVENTIONS_JSONL.name == "learned_conventions.jsonl"
    assert "data" in config.LEARNED_CONVENTIONS_MD.parts
    curated = Path(config.ROOT) / "saathi" / "memory" / "conventions.md"
    assert curated.exists()
    assert "data" not in curated.parts


def test_load_memory_includes_curated_and_learned(tmp_path, monkeypatch):
    learned = tmp_path / "learned_conventions.md"
    learned.write_text("## Auto-learned 2099-01-01\n* prefer tea\n", encoding="utf-8")
    monkeypatch.setattr(config, "LEARNED_CONVENTIONS_MD", learned)
    block = _load_memory()
    assert "conventions.md" in block
    assert "learned_conventions.md" in block
    assert "prefer tea" in block


def test_load_memory_missing_learned_files_is_safe(tmp_path, monkeypatch):
    """Learned-memory files missing: load curated only, no exception."""
    missing = tmp_path / "does-not-exist" / "learned_conventions.md"
    assert not missing.exists()
    monkeypatch.setattr(config, "LEARNED_CONVENTIONS_MD", missing)
    block = _load_memory()
    assert "conventions.md" in block or "decisions.md" in block
    assert "learned_conventions.md" not in block
    assert isinstance(block, str)


def test_load_memory_prefers_recent_when_over_context_limit(tmp_path, monkeypatch):
    """When learned file exceeds 400 chars, the recent (tail) slice is selected."""
    old_marker = "OLD_CONVENTION_MARKER_SHOULD_NOT_APPEAR_IN_CONTEXT"
    new_marker = "NEW_CONVENTION_MARKER_MUST_APPEAR_IN_CONTEXT"
    # Build a file where old content fills well past 400 chars; recent is at the end.
    body = (
        f"## Auto-learned 2099-01-01\n* {old_marker}\n"
        + ("* filler line about historical preference\n" * 40)
        + f"\n## Auto-learned 2099-12-31\n* {new_marker}\n"
    )
    assert len(body) > 400
    learned = tmp_path / "learned_conventions.md"
    learned.write_text(body, encoding="utf-8")
    monkeypatch.setattr(config, "LEARNED_CONVENTIONS_MD", learned)
    block = _load_memory()
    assert "learned_conventions.md" in block
    assert new_marker in block
    assert old_marker not in block


def test_memory_reflector_writes_learned_not_curated(tmp_path, monkeypatch):
    curated = tmp_path / "conventions.md"
    curated.write_text("# Conventions\n\n## Language rules\n- stay English\n", encoding="utf-8")
    _, learned_md, learned_jl = _patch_reflector_targets(monkeypatch, tmp_path)

    before = curated.read_text(encoding="utf-8")
    scheduler.memory_reflector()
    after = curated.read_text(encoding="utf-8")
    assert after == before
    assert learned_md.exists()
    text = learned_md.read_text(encoding="utf-8")
    assert "Auto-learned" in text
    assert "verified voice" in text.lower() or "speaker" in text.lower() or "Prefer" in text
    assert learned_jl.exists()
    row = json.loads(learned_jl.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["source"] == "memory_reflector"
    assert "notes" in row


def test_memory_reflector_dedupes_same_date(tmp_path, monkeypatch):
    """Second reflection on the same calendar day must not duplicate dated content."""
    _, learned_md, learned_jl = _patch_reflector_targets(monkeypatch, tmp_path)
    scheduler.memory_reflector()
    scheduler.memory_reflector()

    text = learned_md.read_text(encoding="utf-8")
    ts = datetime.now().strftime("%Y-%m-%d")
    heading = f"## Auto-learned {ts}"
    assert text.count(heading) == 1

    lines = [ln for ln in learned_jl.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["date"] == ts


def test_learned_convention_paths_are_gitignored():
    """Generated learned-convention files under data/memory/ are ignored by Git."""
    root = Path(config.ROOT)
    for rel in (
        "data/memory/learned_conventions.md",
        "data/memory/learned_conventions.jsonl",
    ):
        proc = subprocess.run(
            ["git", "check-ignore", "-v", rel],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"{rel} not ignored: {proc.stdout!r}{proc.stderr!r}"
        assert "data/" in proc.stdout or ".gitignore" in proc.stdout


def test_saathi_agent_state_is_gitignored():
    root = Path(config.ROOT)
    proc = subprocess.run(
        ["git", "check-ignore", "-v", ".saathi-agent-state/example.log"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert ".saathi-agent-state" in proc.stdout


def test_reflector_does_not_modify_real_curated_conventions(tmp_path, monkeypatch):
    """Runtime reflection must not modify saathi/memory/conventions.md."""
    curated = Path(config.ROOT) / "saathi" / "memory" / "conventions.md"
    assert curated.exists()
    before = curated.read_bytes()
    digest_before = hashlib.sha256(before).hexdigest()

    _patch_reflector_targets(monkeypatch, tmp_path)
    scheduler.memory_reflector()

    after = curated.read_bytes()
    assert hashlib.sha256(after).hexdigest() == digest_before
    assert after == before


def test_reflector_does_not_dirty_storage_db(tmp_path, monkeypatch):
    """Runtime reflection must not touch storage/storage.db (uses config.DB_PATH only)."""
    storage_db = Path(config.ROOT) / "storage" / "storage.db"
    if storage_db.exists():
        before = storage_db.read_bytes()
        mtime_before = storage_db.stat().st_mtime_ns
    else:
        before = None
        mtime_before = None

    _, learned_md, _ = _patch_reflector_targets(monkeypatch, tmp_path)
    # Ensure feedback DB is NOT storage/storage.db
    assert Path(config.DB_PATH) != storage_db
    scheduler.memory_reflector()
    assert learned_md.exists()

    if before is not None:
        assert storage_db.read_bytes() == before
        assert storage_db.stat().st_mtime_ns == mtime_before
    else:
        assert not storage_db.exists()
