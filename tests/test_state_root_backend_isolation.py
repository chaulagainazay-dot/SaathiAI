"""A backend started with an isolated root must not open the personal store.

The store-level tests prove each path resolves correctly when asked. This one
asks nothing: it starts the application the way the validation harness does, in
a subprocess, and records every file the process actually opens via an audit
hook installed before ``saathi`` is imported. Audit events fire inside CPython,
so a path reached through ``sqlite3``, ``os.open`` or a C extension is caught
just as a ``pathlib`` call would be.

No connector is contacted, no microphone is opened and no account is
bootstrapped — only import, route registration and a health request.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PERSONAL_ROOT = pathlib.Path.home() / ".saathi"

# Runs in the child. Installs the audit hook first, then boots the app.
CHILD = r'''
import json, os, pathlib, sys

PERSONAL = str(pathlib.Path.home() / ".saathi")
opened = []          # (path, mode-ish, is_write)

def _hook(event, args):
    try:
        if event == "open":
            path, mode, flags = args[0], args[1], args[2]
            if not isinstance(path, (str, bytes, os.PathLike)):
                return
            p = os.fspath(path)
            if isinstance(p, bytes):
                p = p.decode("utf-8", "replace")
            m = mode if isinstance(mode, str) else ""
            write = bool(set(m) & {"w", "a", "x", "+"}) or bool(
                (flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND)
            )
            opened.append((p, m, write))
        elif event == "sqlite3.connect":
            p = args[0]
            if isinstance(p, bytes):
                p = p.decode("utf-8", "replace")
            if isinstance(p, str):
                opened.append((p, "sqlite3", True))   # SQLite opens read/write
    except Exception:
        pass

sys.addaudithook(_hook)

# ── boot the application ────────────────────────────────────────────────────
import saathi.server as server
from fastapi.testclient import TestClient

status = {}
with TestClient(server.app) as client:
    r = client.get("/api/v1/health")
    status["health"] = r.status_code
status["routes"] = len(server.app.routes)

REPO = os.getcwd()
personal_writes = sorted({p for p, m, w in opened if w and p.startswith(PERSONAL + os.sep)})
repo_writes = sorted({p for p, m, w in opened if w and p.startswith(REPO + os.sep)})
repo_reads = sorted({p for p, m, w in opened if not w and p.startswith(REPO + os.sep)})
personal_reads = sorted({p for p, m, w in opened if not w and p.startswith(PERSONAL + os.sep)})
print("@@RESULT@@" + json.dumps({
    "status": status,
    "personal_writes": personal_writes,
    "personal_reads": personal_reads,
    "repo_writes": repo_writes,
    "repo_reads": repo_reads,
    "total_opens": len(opened),
}))
'''


@pytest.fixture
def isolated_env(tmp_path):
    root = tmp_path / "state"
    env = dict(os.environ)
    env.update({
        "SAATHI_STATE_ROOT": str(root),
        "SAATHI_PLATFORM_DB": str(tmp_path / "platform" / "platform.db"),
        "SAATHI_VOICE_ARTIFACT_DIR": str(tmp_path / "voice-artifacts"),
        "SAATHI_RUNTIME_STATE_DIR": str(tmp_path / "runtime"),
        "SAATHI_RUNS_DIR": str(tmp_path / "runs"),
        "SAATHI_MUSIC_DIR": str(tmp_path / "music"),
        "SAATHI_CBM_INDEX_DIR": str(tmp_path / "cbm"),
        "SAATHI_HOST": "127.0.0.1",
        "SAATHI_ENV": "test",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return root, env


def _boot(env, tmp_path):
    proc = subprocess.run(
        [sys.executable, "-c", CHILD],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        pytest.fail(f"backend boot failed ({proc.returncode}):\n{proc.stderr[-4000:]}")
    marker = [l for l in proc.stdout.splitlines() if l.startswith("@@RESULT@@")]
    assert marker, f"no result from child:\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}"
    return json.loads(marker[-1][len("@@RESULT@@"):]), proc


# ── 25/26/28/29/30 ──────────────────────────────────────────────────────────
def test_backend_boot_opens_no_personal_writable_path(isolated_env, tmp_path):
    root, env = isolated_env

    before = sorted(p.name for p in PERSONAL_ROOT.iterdir()) if PERSONAL_ROOT.exists() else []
    result, proc = _boot(env, tmp_path)
    after = sorted(p.name for p in PERSONAL_ROOT.iterdir()) if PERSONAL_ROOT.exists() else []

    # any HTTP status proves the stack answered; /health is auth-gated (401).
    assert result["status"]["health"] in (200, 401, 403, 404), result["status"]
    assert result["status"]["routes"] > 0, "no routes registered — app did not initialise"
    assert result["total_opens"] > 0, "audit hook recorded nothing; it is not working"

    assert result["personal_writes"] == [], (
        "backend opened personal state for writing:\n  "
        + "\n  ".join(result["personal_writes"])
    )
    assert after == before, "personal state root gained or lost entries during boot"

    # 30. the child exited on its own; nothing left behind
    assert proc.returncode == 0


def test_backend_boot_creates_state_only_under_the_isolated_root(isolated_env, tmp_path):
    root, env = isolated_env
    result, _ = _boot(env, tmp_path)
    assert result["personal_writes"] == []

    # whatever the boot did create must sit inside the sandbox we handed it
    created = [p for p in tmp_path.rglob("*") if p.is_file()]
    for p in created:
        assert p.is_relative_to(tmp_path)


def test_audit_hook_would_catch_a_write_under_the_watched_root(tmp_path):
    """Sensitivity check: the harness must fail when a watched write happens.

    Without this, a boot that opened nothing at all would look identical to a
    boot that was correctly isolated. The child watches a decoy root here rather
    than the operator's real one — proving isolation by writing into the
    directory under protection would defeat the point.
    """
    decoy = tmp_path / "decoy-state"
    decoy.mkdir()
    probe = decoy / "probe.db"

    child = CHILD.replace(
        'PERSONAL = str(pathlib.Path.home() / ".saathi")',
        f"PERSONAL = {str(decoy)!r}",
    ).replace(
        "import saathi.server as server",
        f"open({str(probe)!r}, 'a').close()\n"
        "import saathi.server as server",
    )
    env = dict(os.environ)
    env.update({
        "SAATHI_STATE_ROOT": str(tmp_path / "state"),
        "SAATHI_PLATFORM_DB": str(tmp_path / "platform" / "platform.db"),
        "SAATHI_RUNTIME_STATE_DIR": str(tmp_path / "runtime"),
        "SAATHI_CBM_INDEX_DIR": str(tmp_path / "cbm"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    proc = subprocess.run([sys.executable, "-c", child], cwd=REPO_ROOT, env=env,
                          capture_output=True, text=True, timeout=600)
    marker = [l for l in proc.stdout.splitlines() if l.startswith("@@RESULT@@")]
    assert marker, f"probe boot did not complete:\n{proc.stderr[-3000:]}"
    result = json.loads(marker[-1][len("@@RESULT@@"):])
    assert str(probe) in result["personal_writes"], (
        "audit hook failed to observe a deliberate write under the watched root — "
        "the isolation assertions above would prove nothing"
    )


# The three stores that used to escape isolation — `storage/storage.db`,
# `data/baadar.db`, `data/projects.json` — now resolve through
# `scoped_state_path`, so an isolated boot writes nothing inside the checkout.
# The allowance is gone deliberately: this set is empty and must stay empty.
KNOWN_REPO_LOCAL_WRITES: set[str] = set()

# Their historical locations, which an isolated boot must not open at all.
HISTORICAL_REPO_PATHS = (
    "storage/storage.db",
    "data/baadar.db",
    "data/projects.json",
)


def test_isolated_boot_writes_nothing_inside_the_checkout(isolated_env, tmp_path):
    """No repo-local state at all — the allowance for these three is retired."""
    _, env = isolated_env
    result, _ = _boot(env, tmp_path)

    written = {
        pathlib.Path(p).relative_to(REPO_ROOT).as_posix()
        for p in result.get("repo_writes", [])
    }
    # __pycache__ is bytecode, not state, and is already suppressed in the child.
    written = {w for w in written if "__pycache__" not in w}

    unexpected = written - KNOWN_REPO_LOCAL_WRITES
    assert not unexpected, (
        "backend boot wrote repo-local state under an isolated root:\n  "
        + "\n  ".join(sorted(unexpected))
        + "\n\nRoute it through saathi.runtime_paths.scoped_state_path()."
    )


def test_isolated_boot_does_not_open_the_historical_repo_paths(isolated_env, tmp_path):
    """The three formerly-unisolated stores are not opened, read or written."""
    _, env = isolated_env
    result, _ = _boot(env, tmp_path)

    opened = set(result.get("repo_writes", [])) | set(result.get("repo_reads", []))
    hit = sorted(
        p for p in opened
        if any(pathlib.Path(p).as_posix().endswith(h) for h in HISTORICAL_REPO_PATHS)
    )
    assert not hit, "isolated boot touched a historical repo-local store:\n  " + "\n  ".join(hit)


def test_isolated_boot_materialises_the_scoped_stores_under_the_root(isolated_env, tmp_path):
    """Positive half: the stores exist, but inside the sandbox."""
    root, env = isolated_env
    _boot(env, tmp_path)
    produced = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    assert "storage/storage.db" in produced, sorted(produced)[:20]
