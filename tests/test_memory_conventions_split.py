"""Curated conventions.md vs runtime learned_conventions.* separation."""
from __future__ import annotations

import json
from pathlib import Path

from saathi import config
from saathi.agent import _load_memory
from saathi import scheduler


def test_learned_paths_live_under_data_memory():
    assert config.LEARNED_MEMORY_DIR == config.ROOT / "data" / "memory"
    assert config.LEARNED_CONVENTIONS_MD.name == "learned_conventions.md"
    assert config.LEARNED_CONVENTIONS_JSONL.name == "learned_conventions.jsonl"
    assert "data" in config.LEARNED_CONVENTIONS_MD.parts
    # curated baseline is NOT under data/
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


def test_memory_reflector_writes_learned_not_curated(tmp_path, monkeypatch):
    curated = tmp_path / "conventions.md"
    curated.write_text("# Conventions\n\n## Language rules\n- stay English\n", encoding="utf-8")
    learned_dir = tmp_path / "data" / "memory"
    learned_md = learned_dir / "learned_conventions.md"
    learned_jl = learned_dir / "learned_conventions.jsonl"
    monkeypatch.setattr(config, "LEARNED_MEMORY_DIR", learned_dir)
    monkeypatch.setattr(config, "LEARNED_CONVENTIONS_MD", learned_md)
    monkeypatch.setattr(config, "LEARNED_CONVENTIONS_JSONL", learned_jl)

    # Point scheduler memory_dir at tmp so it doesn't touch real files for integrations
    real_memory = Path(scheduler.__file__).parent / "memory"
    # reflector uses saathi/memory for dir setup but writes learned via config paths

    class _FakeAgent:
        def complete(self, *a, **k):
            return "* Prefer verified voice before privileged actions\n* Keep posts English-only"

    # fake feedback rows via sqlite path - simpler: patch the feedback query block by
    # injecting recent_feedback through a full mock of the try body.
    # Instead call the write path by patching SaathiAgent + sqlite to return feedback.
    monkeypatch.setattr("saathi.agent.SaathiAgent", _FakeAgent)

    import sqlite3
    db = tmp_path / "fb.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE feedback (kind TEXT, detail TEXT, ts REAL)")
    conn.execute(
        "INSERT INTO feedback VALUES (?,?,?)",
        ("note", "Ajay wants speaker verification before shell", 1.0),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(config, "DB_PATH", db)

    before = curated.read_text(encoding="utf-8")
    scheduler.memory_reflector()
    after = curated.read_text(encoding="utf-8")
    assert after == before  # curated baseline untouched
    assert learned_md.exists()
    text = learned_md.read_text(encoding="utf-8")
    assert "Auto-learned" in text
    assert "verified voice" in text.lower() or "speaker" in text.lower() or "Prefer" in text
    assert learned_jl.exists()
    row = json.loads(learned_jl.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["source"] == "memory_reflector"
    assert "notes" in row
