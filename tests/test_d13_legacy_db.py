"""D13 — the legacy database honours canonical state isolation, and no module
opens it while being imported.

Before this repair a backend booted with an isolated ``SAATHI_STATE_ROOT`` still
held four read-write descriptors on ``<repo>/data/saathi.db``, because
``config.DB_PATH`` was a module constant evaluated at import time and four
modules connected to it during import. These tests pin both halves: where the
path resolves, and when the connection is made.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import threading

import pytest

from saathi.runtime_paths import REPO_ROOT, StateRootError, legacy_db_path

HISTORICAL = REPO_ROOT / "data" / "saathi.db"

# The modules that used to connect during import.
LAZY_MODULES = ("saathi.selfimprove", "saathi.nepali", "saathi.tools.notes", "saathi.tools.english")


@pytest.fixture
def clean_env(monkeypatch):
    for var in ("SAATHI_STATE_ROOT", "SAATHI_LEGACY_DB"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


# ── resolution (1-7) ────────────────────────────────────────────────────────
def test_unset_configuration_keeps_historical_repo_path(clean_env):
    assert legacy_db_path() == HISTORICAL


def test_state_root_redirects_under_the_root(clean_env, tmp_path):
    clean_env.setenv("SAATHI_STATE_ROOT", str(tmp_path))
    assert legacy_db_path() == tmp_path / "data" / "saathi.db"


def test_explicit_env_wins_over_state_root(clean_env, tmp_path):
    clean_env.setenv("SAATHI_STATE_ROOT", str(tmp_path / "root"))
    clean_env.setenv("SAATHI_LEGACY_DB", str(tmp_path / "elsewhere" / "legacy.db"))
    assert legacy_db_path() == tmp_path / "elsewhere" / "legacy.db"


def test_explicit_argument_wins_over_everything(clean_env, tmp_path):
    clean_env.setenv("SAATHI_STATE_ROOT", str(tmp_path / "root"))
    clean_env.setenv("SAATHI_LEGACY_DB", str(tmp_path / "env.db"))
    assert legacy_db_path(tmp_path / "arg.db") == tmp_path / "arg.db"


@pytest.mark.parametrize("relative", ["data/saathi.db", "./x.db", "../x.db"])
def test_relative_override_is_rejected(clean_env, relative):
    clean_env.setenv("SAATHI_LEGACY_DB", relative)
    with pytest.raises(StateRootError):
        legacy_db_path()


def test_relative_explicit_argument_is_rejected(clean_env):
    with pytest.raises(StateRootError):
        legacy_db_path("data/saathi.db")


def test_readers_and_writers_resolve_identically(clean_env, tmp_path):
    """``config.DB_PATH`` and the accessor must never disagree."""
    clean_env.setenv("SAATHI_STATE_ROOT", str(tmp_path))
    from saathi import config

    assert pathlib.Path(config.DB_PATH) == legacy_db_path()


def test_no_fallback_to_repository_when_state_root_is_set(clean_env, tmp_path):
    clean_env.setenv("SAATHI_STATE_ROOT", str(tmp_path))
    resolved = legacy_db_path()
    assert resolved != HISTORICAL
    assert str(resolved).startswith(str(tmp_path))


def test_resolver_creates_nothing(clean_env, tmp_path):
    root = tmp_path / "never-created"
    clean_env.setenv("SAATHI_STATE_ROOT", str(root))
    resolved = legacy_db_path()
    assert not resolved.exists()
    assert not resolved.parent.exists()
    assert not root.exists()


# ── lazy consumers (8-15) ───────────────────────────────────────────────────
# Runs in a child so the audit hook sees the imports themselves.
_IMPORT_CHILD = r'''
import json, os, sys
opened = []
def _hook(event, args):
    try:
        if event == "sqlite3.connect":
            p = args[0]
            opened.append(os.fspath(p) if not isinstance(p, str) else p)
        elif event == "open":
            flags = args[2] or 0
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
                p = args[0]
                opened.append(os.fspath(p) if not isinstance(p, str) else p)
    except Exception:
        pass
sys.addaudithook(_hook)

import importlib
for name in %(modules)r:
    importlib.import_module(name)

db = %(db)r
print("@@R@@" + json.dumps({
    "touched_db": [str(p) for p in opened if str(p).endswith("saathi.db")],
    "db_exists": os.path.exists(db),
}))
'''


def _run_child(source: str, env: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", source], cwd=REPO_ROOT, env=env,
        capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, f"child failed:\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}"
    marker = [l for l in proc.stdout.splitlines() if l.startswith("@@R@@")]
    assert marker, f"no result:\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}"
    return json.loads(marker[-1][len("@@R@@"):])


def _child_env(root: pathlib.Path) -> dict:
    env = dict(os.environ)
    env.update({
        "SAATHI_STATE_ROOT": str(root),
        "SAATHI_LOAD_DOTENV": "false",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    env.pop("SAATHI_LEGACY_DB", None)
    return env


@pytest.mark.parametrize("module", LAZY_MODULES)
def test_importing_a_consumer_opens_no_database(tmp_path, module):
    """Import must not connect, and must not run DDL — which means the file
    must not exist afterwards, since DDL is what would create it."""
    root = tmp_path / "state"
    db = root / "data" / "saathi.db"
    result = _run_child(
        _IMPORT_CHILD % {"modules": (module,), "db": str(db)}, _child_env(root)
    )
    assert result["touched_db"] == []
    assert result["db_exists"] is False


def test_importing_all_consumers_together_opens_no_database(tmp_path):
    root = tmp_path / "state"
    db = root / "data" / "saathi.db"
    result = _run_child(
        _IMPORT_CHILD % {"modules": LAZY_MODULES, "db": str(db)}, _child_env(root)
    )
    assert result["touched_db"] == []
    assert result["db_exists"] is False


_FIRST_USE_CHILD = r'''
import json, os, sys
opened = []
def _hook(event, args):
    if event == "sqlite3.connect":
        p = args[0]
        opened.append(os.fspath(p) if not isinstance(p, str) else p)
sys.addaudithook(_hook)

from saathi.tools import notes, english
import saathi.nepali as nepali
import saathi.selfimprove as selfimprove

notes.remember_fact("d13 probe", "test")
english.log_mistake("teh", "the")
nepali.apply_corrections("satie")
selfimprove.record_feedback("praise", "d13")

print("@@R@@" + json.dumps({"connected": sorted({str(p) for p in opened})}))
'''


def test_first_use_opens_only_the_configured_isolated_database(tmp_path):
    root = tmp_path / "state"
    result = _run_child(_FIRST_USE_CHILD, _child_env(root))
    expected = str(root / "data" / "saathi.db")
    assert result["connected"], "nothing connected — the probe did not exercise the stores"
    assert all(p == expected for p in result["connected"]), result["connected"]
    assert (root / "data" / "saathi.db").exists()


def test_four_consumers_share_one_configured_path(tmp_path):
    """Every consumer must land on the same file — a reader and a writer that
    disagree is the drift this repair exists to stop."""
    result = _run_child(_FIRST_USE_CHILD, _child_env(tmp_path / "state"))
    assert len(set(result["connected"])) == 1


def test_switching_roots_does_not_reuse_the_cached_instance(monkeypatch, tmp_path):
    from saathi import legacy_store

    legacy_store.reset_legacy_stores()
    monkeypatch.delenv("SAATHI_LEGACY_DB", raising=False)
    monkeypatch.setenv("SAATHI_STATE_ROOT", str(tmp_path / "a"))
    first = legacy_store.legacy_memory()
    monkeypatch.setenv("SAATHI_STATE_ROOT", str(tmp_path / "b"))
    second = legacy_store.legacy_memory()

    assert first is not second
    assert first.db_path != second.db_path
    assert second.db_path == tmp_path / "b" / "data" / "saathi.db"
    legacy_store.reset_legacy_stores()


def test_concurrent_first_use_builds_one_instance(monkeypatch, tmp_path):
    from saathi import legacy_store

    legacy_store.reset_legacy_stores()
    monkeypatch.delenv("SAATHI_LEGACY_DB", raising=False)
    monkeypatch.setenv("SAATHI_STATE_ROOT", str(tmp_path))

    seen: list = []
    barrier = threading.Barrier(8)

    def grab():
        barrier.wait()
        seen.append(legacy_store.legacy_memory())

    threads = [threading.Thread(target=grab) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(seen) == 8
    assert len({id(m) for m in seen}) == 1
    legacy_store.reset_legacy_stores()


def test_reset_closes_connections(monkeypatch, tmp_path):
    from saathi import legacy_store

    legacy_store.reset_legacy_stores()
    monkeypatch.delenv("SAATHI_LEGACY_DB", raising=False)
    monkeypatch.setenv("SAATHI_STATE_ROOT", str(tmp_path))
    memory = legacy_store.legacy_memory()
    conn = legacy_store.legacy_connection("probe", "CREATE TABLE IF NOT EXISTS t(x)")
    memory.save_fact("still open")

    legacy_store.reset_legacy_stores()

    import sqlite3
    with pytest.raises(sqlite3.ProgrammingError):
        memory.db.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_tool_outputs_remain_compatible(monkeypatch, tmp_path):
    """Delayed initialisation only — the tools return what they always did."""
    from saathi import legacy_store

    legacy_store.reset_legacy_stores()
    monkeypatch.delenv("SAATHI_LEGACY_DB", raising=False)
    monkeypatch.setenv("SAATHI_STATE_ROOT", str(tmp_path))

    from saathi.tools import english, notes

    assert notes.remember_fact("ajay likes tea") == {"remembered": "ajay likes tea"}
    added = notes.manage_tasks("add", title="ship d13")
    assert added["added"]["title"] == "ship d13"
    assert any(t["title"] == "ship d13" for t in notes.manage_tasks("list")["open_tasks"])
    assert english.log_mistake("teh", "the") == {"logged": True}
    assert english.progress()["top_mistakes"][0]["mistake"] == "teh"

    legacy_store.reset_legacy_stores()
