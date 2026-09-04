"""D13 — the containment auditor and ``lsof`` must agree, and an isolated boot
must write nothing outside its root.

The previous audit hook compared ``sqlite3.connect``'s argument against ``str``.
Production passes a ``pathlib.Path``, so the ledger reported a clean run while
``lsof`` showed four read-write descriptors on the worktree's legacy database.
Test 26 pins the representation bug itself; test 27 pins the agreement between
the two instruments, which is what makes either trustworthy.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys

import pytest

from saathi.runtime_paths import REPO_ROOT

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from support.containment_audit import (  # noqa: E402
    UNCLASSIFIED,
    ContainmentAudit,
    normalize_target,
    parse_sqlite_target,
)

PERSONAL_ROOT = pathlib.Path.home() / ".saathi"
WORKTREE_ENV = REPO_ROOT / ".env"


# ── 26: every path representation is seen ───────────────────────────────────
def test_normalizer_accepts_every_path_representation(tmp_path):
    target = tmp_path / "x.db"
    expected = os.path.realpath(target)
    assert normalize_target(str(target)) == expected
    assert normalize_target(pathlib.Path(target)) == expected
    assert normalize_target(str(target).encode()) == expected
    assert normalize_target(None) is None
    assert normalize_target(":memory:") is None


def test_relative_and_symlinked_targets_resolve_to_the_real_file(tmp_path, monkeypatch):
    real = tmp_path / "real.db"
    real.write_text("")
    link = tmp_path / "link.db"
    link.symlink_to(real)
    assert normalize_target(link) == os.path.realpath(real)

    monkeypatch.chdir(tmp_path)
    assert normalize_target("real.db") == os.path.realpath(real)


def test_sqlite_uri_read_only_mode_is_recorded_as_a_read(tmp_path):
    db = tmp_path / "x.db"
    path, write = parse_sqlite_target(f"file:{db}?mode=ro")
    assert path == os.path.realpath(db)
    assert write is False
    _, rw = parse_sqlite_target(f"file:{db}?mode=rwc")
    assert rw is True


def test_audit_hook_catches_path_based_sqlite_connect(tmp_path):
    """The exact bug: a Path argument must not be dropped."""
    child = r'''
import json, pathlib, sqlite3, sys, os
sys.path.insert(0, %(tests)r)
from support.containment_audit import ContainmentAudit
audit = ContainmentAudit({"iso": %(root)r}, allowed_write_zones={"iso"}).install()

db = pathlib.Path(%(db)r)
db.parent.mkdir(parents=True, exist_ok=True)
sqlite3.connect(db).close()                       # PathLike
sqlite3.connect(str(db)).close()                  # str
sqlite3.connect(str(db).encode()).close()         # bytes
sqlite3.connect("file:" + str(db) + "?mode=ro", uri=True).close()   # URI, read-only

seen = [r for r in audit.records if r["event"] == "sqlite3.connect"]
print("@@R@@" + json.dumps({
    "paths": sorted({r["path"] for r in seen}),
    "count": len(seen),
    "writes": sum(1 for r in seen if r["write"]),
    "reads": sum(1 for r in seen if not r["write"]),
}))
''' % {
        "tests": str(pathlib.Path(__file__).resolve().parent),
        "root": str(tmp_path),
        "db": str(tmp_path / "data" / "legacy.db"),
    }
    result = _run(child, dict(os.environ))
    assert result["count"] == 4, "one representation was dropped"
    assert result["paths"] == [os.path.realpath(tmp_path / "data" / "legacy.db")]
    assert result["writes"] == 3 and result["reads"] == 1


def test_unclassifiable_writable_target_fails_closed(tmp_path):
    audit = ContainmentAudit({"iso": str(tmp_path)}, allowed_write_zones={"iso"})
    audit.record("sqlite3.connect", "/somewhere/else/legacy.db", True)
    audit.record("sqlite3.connect", os.path.realpath(tmp_path / "ok.db"), True)
    violations = audit.violations()
    assert [v["path"] for v in violations] == ["/somewhere/else/legacy.db"]
    assert violations[0]["zone"] == UNCLASSIFIED


def test_ddl_without_inserts_still_registers_as_a_write(tmp_path):
    audit = ContainmentAudit({"iso": str(tmp_path)}, allowed_write_zones={"iso"})
    audit.install()
    db = tmp_path / "ddl.db"
    conn = sqlite3.connect(db)
    conn.executescript("CREATE TABLE IF NOT EXISTS t(x)")
    conn.close()
    assert os.path.realpath(db) in audit.write_paths()


# ── 27: the ledger and lsof agree ───────────────────────────────────────────
_HOLD_CHILD = r'''
import json, pathlib, sqlite3, sys, os
sys.path.insert(0, %(tests)r)
from support.containment_audit import ContainmentAudit
audit = ContainmentAudit({"iso": %(root)r}, allowed_write_zones={"iso"}).install()

db = pathlib.Path(%(db)r)
db.parent.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(db)                 # PathLike, deliberately
conn.executescript("CREATE TABLE IF NOT EXISTS probe(x)")
conn.execute("INSERT INTO probe(x) VALUES(1)")
conn.commit()

print("@@LEDGER@@" + json.dumps({"writes": audit.write_paths()}), flush=True)
sys.stdin.readline()          # hold the descriptor open for lsof
'''


def test_ledger_and_lsof_agree_on_a_disposable_legacy_mutation(tmp_path):
    if shutil.which("lsof") is None:
        pytest.skip("lsof unavailable")
    db = tmp_path / "data" / "saathi.db"
    source = _HOLD_CHILD % {
        "tests": str(pathlib.Path(__file__).resolve().parent),
        "root": str(tmp_path),
        "db": str(db),
    }
    proc = subprocess.Popen(
        [sys.executable, "-c", source], cwd=REPO_ROOT, env=dict(os.environ),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        line = proc.stdout.readline()
        assert line.startswith("@@LEDGER@@"), line
        ledger = json.loads(line[len("@@LEDGER@@"):])

        lsof = subprocess.run(
            ["lsof", "-p", str(proc.pid), "-nP"], capture_output=True, text=True, timeout=60,
        ).stdout
        held = {
            parts[-1] for parts in (l.split() for l in lsof.splitlines()[1:])
            if len(parts) > 5 and parts[4] == "REG" and parts[3].rstrip("rwu").isdigit()
            and parts[-1].endswith("saathi.db")
        }
    finally:
        proc.stdin.write("\n")
        proc.stdin.flush()
        proc.wait(timeout=30)

    real = os.path.realpath(db)
    assert real in ledger["writes"], "the ledger missed the mutation"
    assert {os.path.realpath(p) for p in held} == {real}, "lsof disagrees with the ledger"


# ── 28-32: a clean isolated boot ────────────────────────────────────────────
_BOOT_CHILD = r'''
import json, os, pathlib, sys
sys.path.insert(0, %(tests)r)
from support.containment_audit import UNCLASSIFIED as UNCLASSIFIED_ZONE, ContainmentAudit

ROOT = os.environ["SAATHI_STATE_ROOT"]
HOME = os.path.expanduser("~")
audit = ContainmentAudit({
    "isolated":  ROOT,
    "personal":  os.path.join(HOME, ".saathi"),
    "personal_checkout": os.path.join(HOME, "SaathiAI"),
    "worktree":  %(repo)r,
    "tmp":       "/private/tmp",
    "var_tmp":   "/private/var/folders",
    "system":    "/opt/homebrew",
    "python":    os.path.dirname(os.__file__),
    # The interpreter's own libraries. `python` above is only the stdlib
    # (Homebrew Cellar); third-party packages live in the virtualenv, and this
    # developer's virtualenv sits inside $HOME/SaathiAI. Longest-prefix
    # classification therefore filed every `import` of a third-party library --
    # 1682 of them, all under .venv -- as a read of personal state, and the
    # containment assertion failed on library imports rather than on any access
    # to operator data. Naming the environment makes the detector truthful; it
    # does not widen what counts as personal. ~/.saathi remains forbidden, and
    # this zone is deliberately the venv prefix only, not $HOME/SaathiAI.
    "python_env": sys.prefix,
}, allowed_write_zones={"isolated", "tmp", "var_tmp"}).install()

import saathi.server as server
from fastapi.testclient import TestClient

with TestClient(server.app) as client:
    status = client.get("/api/v1/health").status_code

def _paths(zone, events):
    return sorted({r["path"] for r in audit.records
                   if r["write"] and r["path"] and r["zone"] == zone and r["event"] in events})

FILE_EVENTS = {"open", "sqlite3.connect", "os.rename", "os.remove"}
DIR_EVENTS = {"os.mkdir"}
OUTSIDE = ("personal", "personal_checkout", "worktree", UNCLASSIFIED_ZONE)

print("@@R@@" + json.dumps({
    "health": status,
    "writes_isolated":   audit.write_paths("isolated"),
    # File-level writes are the containment question D13 answers. Directory
    # creation is tracked separately because four unrelated modules mkdir at
    # import time; see D14_IMPORT_TIME_MKDIR in the test module.
    "file_writes_outside": sorted({p for z in OUTSIDE for p in _paths(z, FILE_EVENTS)}),
    "dir_writes_outside":  sorted({p for z in OUTSIDE for p in _paths(z, DIR_EVENTS)}),
    "reads_personal":    audit.reads_in("personal") + audit.reads_in("personal_checkout"),
    "legacy_db_targets": sorted({r["path"] for r in audit.records
                                 if r["path"] and r["path"].endswith("saathi.db")}),
    "worktree_env_opened": any(
        r["path"] == os.path.realpath(%(env)r) for r in audit.records
    ),
}))
'''


def _run(source: str, env: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", source], cwd=REPO_ROOT, env=env,
        capture_output=True, text=True, timeout=900,
    )
    assert proc.returncode == 0, f"child failed:\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}"
    marker = [l for l in proc.stdout.splitlines() if l.startswith("@@R@@")]
    assert marker, f"no result:\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}"
    return json.loads(marker[-1][len("@@R@@"):])


def _oracle() -> dict[str, str]:
    """Size+mtime for the stores this repair must leave alone, plus the pinned model."""
    targets = [
        REPO_ROOT / "data" / "saathi.db",
        REPO_ROOT / "data" / "baadar.db",
        REPO_ROOT / "data" / "projects.json",
        REPO_ROOT / "storage" / "storage.db",
        WORKTREE_ENV,
        PERSONAL_ROOT / "stt-models" / "whisper-cpp" / "ggml-base.bin",
    ]
    out = {}
    for path in targets:
        if path.exists():
            stat = path.stat()
            out[str(path)] = f"{stat.st_size}:{int(stat.st_mtime)}"
    return out


@pytest.fixture(scope="module")
def isolated_boot(tmp_path_factory):
    root = tmp_path_factory.mktemp("d13-boot") / "state"
    env = dict(os.environ)
    env.update({
        "SAATHI_STATE_ROOT": str(root),
        "SAATHI_PLATFORM_DB": str(root / "platform" / "platform.db"),
        "SAATHI_VOICE_ARTIFACT_DIR": str(root / "voice-artifacts"),
        "SAATHI_RUNTIME_STATE_DIR": str(root / "runtime"),
        "SAATHI_LOAD_DOTENV": "false",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    env.pop("SAATHI_LEGACY_DB", None)
    env.pop("SAATHI_DOTENV_PATH", None)

    before = _oracle()
    result = _run(
        _BOOT_CHILD % {
            "tests": str(pathlib.Path(__file__).resolve().parent),
            "repo": str(REPO_ROOT),
            "env": str(WORKTREE_ENV),
        },
        env,
    )
    result["oracle_before"] = before
    result["oracle_after"] = _oracle()
    result["root"] = str(root)
    return result


def test_isolated_boot_reaches_health(isolated_boot):
    # 401/403 would mean an auth gate, not a containment problem; a 5xx would.
    assert isolated_boot["health"] in (200, 401, 403)


# Four modules create a directory while being imported. None of them is a
# legacy-database or dotenv consumer, so none is in D13's scope — but the
# repaired auditor is the reason they are visible at all, and one of them
# reaches into the operator's personal checkout. They are enumerated here, with
# the line that does it, so the set cannot grow unnoticed and so that nothing
# about them reads as "allowed". Tracked as D14.
D14_IMPORT_TIME_MKDIR = {
    "<repo>/data/files":        "saathi/server.py:2501",
    "<repo>/data/quote_cards":  "saathi/tools/quote_maker.py:26",
    "<repo>/videos_output":     "saathi/tools/hyperframes.py:26",
    "~/SaathiAI/data/growth":   "saathi/tools/growth_engine.py:19",
    "<repo>/data/linkedin":     "saathi/tools/linkedin_post.py:36",
}


def _logical(path: str) -> str:
    path = path.replace(str(pathlib.Path(REPO_ROOT).resolve()), "<repo>")
    return path.replace(str(pathlib.Path.home()), "~")


def test_isolated_boot_opens_no_personal_file(isolated_boot):
    """No personal file is read or written. Directory creation is D14, below."""
    assert isolated_boot["reads_personal"] == []
    personal_files = [p for p in isolated_boot["file_writes_outside"] if "/.saathi/" in p]
    assert personal_files == []


# ── negative control: the detector must still catch a real violation ────────
def test_the_detector_still_catches_a_read_of_personal_state(tmp_path):
    """Green must mean contained, not that the instrument stopped working.

    Phase 15 added a ``python_env`` zone so library imports stop being filed as
    personal reads. That is only safe if a genuine personal read is still
    caught, so this drives one deliberately -- against a fixture inside a fake
    personal root, never the operator's real ``~/.saathi``.
    """
    fake_home = tmp_path / "home"
    personal = fake_home / ".saathi"
    personal.mkdir(parents=True)
    secret = personal / "accounts.db"
    secret.write_text("fixture")

    child = r'''
import json, os, sys
sys.path.insert(0, %(tests)r)
from support.containment_audit import ContainmentAudit
audit = ContainmentAudit({
    "personal": %(personal)r,
    "python_env": sys.prefix,
}, allowed_write_zones=set()).install()

# The violation: read a file inside the personal zone.
open(%(secret)r, "rb").close()
# And a benign library import, which must NOT be counted as personal.
import json as _j

print("@@N@@" + json.dumps({
    "personal_reads": audit.reads_in("personal"),
}))
''' % {
        "tests": str(pathlib.Path(__file__).resolve().parent),
        "personal": str(personal),
        "secret": str(secret),
    }

    proc = subprocess.run([sys.executable, "-c", child], cwd=REPO_ROOT,
                          env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    line = next(l for l in proc.stdout.splitlines() if l.startswith("@@N@@"))
    reads = json.loads(line[len("@@N@@"):])["personal_reads"]

    assert reads, "the detector failed to record a real personal read"
    assert any(os.path.realpath(str(secret)) == r for r in reads)


def test_the_python_env_zone_does_not_cover_the_checkout(tmp_path):
    """The new zone is the virtualenv prefix, not $HOME/SaathiAI.

    If it ever widened to the checkout it would hide real personal reads, which
    is exactly the failure mode this milestone was called to prevent.
    """
    import sys as _sys

    venv = os.path.realpath(_sys.prefix)
    checkout = os.path.realpath(os.path.join(os.path.expanduser("~"), "SaathiAI"))
    assert venv != checkout
    assert venv.startswith(checkout + os.sep) or not venv.startswith(checkout), (
        "the venv may live inside the checkout, but the zone must be the venv")

    # A file directly in the checkout is not inside the venv zone.
    from support.containment_audit import classify
    zones = {"personal_checkout": checkout, "python_env": venv}
    assert classify(os.path.join(checkout, "data", "growth"), zones) == "personal_checkout"
    assert classify(os.path.join(venv, "lib", "x.py"), zones) == "python_env"


def test_isolated_boot_writes_no_file_outside_the_root(isolated_boot):
    assert isolated_boot["file_writes_outside"] == []


def test_the_legacy_database_is_only_ever_the_isolated_one(isolated_boot):
    """D13 itself: every saathi.db the boot touches lives under the root."""
    root = os.path.realpath(isolated_boot["root"])
    assert all(p.startswith(root) for p in isolated_boot["legacy_db_targets"]), (
        isolated_boot["legacy_db_targets"]
    )


def test_import_time_directory_creation_has_not_grown(isolated_boot):
    """D14 fence: these are known escapes, not permitted ones. A new entry here
    is a new containment defect and must fail rather than accumulate."""
    seen = {_logical(p) for p in isolated_boot["dir_writes_outside"]}
    assert seen <= set(D14_IMPORT_TIME_MKDIR), (
        f"new import-time directory escape: {sorted(seen - set(D14_IMPORT_TIME_MKDIR))}"
    )


def test_isolated_boot_opens_no_worktree_dotenv(isolated_boot):
    assert isolated_boot["worktree_env_opened"] is False


def test_every_isolated_boot_write_is_inside_the_root(isolated_boot):
    root = os.path.realpath(isolated_boot["root"])
    assert isolated_boot["writes_isolated"], "the boot wrote nothing at all — check the probe"
    assert all(p.startswith(root) for p in isolated_boot["writes_isolated"])


def test_oracles_are_unchanged_by_an_isolated_boot(isolated_boot):
    assert isolated_boot["oracle_before"] == isolated_boot["oracle_after"]
