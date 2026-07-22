"""M17.5 second live application harness — SQLite (real DB through the gateway)."""
import os
import shutil
import sqlite3 as pysq
import tempfile

import pytest

from saathi.application_harness.pilots import sqlite_harness as SQ
from saathi.application_harness import service as SVC, registry
from saathi.application_harness.models import HarnessActionIntent

HAS_SQLITE = SQ.available()["available"]
skip_no = pytest.mark.skipif(not HAS_SQLITE, reason="sqlite3 absent")


def _seed_db(ws):
    db = os.path.join(ws, "pilot.db")
    c = pysq.connect(db)
    c.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
    c.execute("INSERT INTO t(v) VALUES('a'),('b')")
    c.commit(); c.close()
    return db


# ── platform now has TWO live apps (when host binaries are present) ─────────
def test_two_live_applications_registered():
    """Multi-app registration is environment-honest: only available binaries
    are executable. Missing ffmpeg on Linux CI is not a product regression."""
    from saathi.application_harness.pilots import ffmpeg as F
    execs = {h.harness_id for h in registry.all_harnesses() if h.executable()}
    if HAS_SQLITE:
        assert "sqlite" in execs
    if F.available()["available"]:
        assert "ffmpeg" in execs
    # when both host tools exist, the platform must expose both
    if HAS_SQLITE and F.available()["available"]:
        assert "ffmpeg" in execs and "sqlite" in execs
    assert len(execs) >= 1  # at least one live pilot on any supported host


# ── SQL validation (injection / dot-command / attach defense) ───────────────
@pytest.mark.parametrize("bad", [
    ".tables", ".shell rm -rf /", ".import x t", "ATTACH DATABASE '/etc/x' AS y",
    "SELECT 1; DROP TABLE t", "PRAGMA writable_schema=1", "VACUUM",
    "SELECT load_extension('x')",
])
def test_forbidden_sql_rejected(bad):
    ok, _ = SQ.validate_sql(bad)
    assert not ok


def test_good_sql_and_identifier():
    assert SQ.validate_sql("SELECT count(*) FROM t")[0]
    assert SQ.valid_identifier("pilot_tbl")
    assert not SQ.valid_identifier("t; DROP TABLE t")


# ── live: schema / query / mutation through the gateway + independent verify ─
@skip_no
def test_live_inspect_schema_verified():
    ws = tempfile.mkdtemp(); db = _seed_db(ws)
    defn = SQ.definition(); op = {o.operation_id: o for o in SQ.operations()}["inspect_schema"]
    i = HarnessActionIntent(user_id="ajay", session_id="s", harness_id="sqlite",
                            operation_id="inspect_schema")
    r = SVC.run_harness_action(defn=defn, op=op, intent=i,
                               argv=SQ.build_schema_argv(db_path=db), work_dir=ws,
                               file_roots=[ws], owner="ajay", verify_target=db,
                               verify_kind="sqlite_db")
    assert r["status"] == "success"
    assert r["verification"]["integrity"] == "ok" and r["verification"]["tables"] >= 1
    shutil.rmtree(ws, ignore_errors=True)


@skip_no
def test_live_safe_mutation_verified():
    ws = tempfile.mkdtemp(); db = _seed_db(ws)
    defn = SQ.definition(); op = {o.operation_id: o for o in SQ.operations()}["safe_mutation"]
    i = HarnessActionIntent(user_id="ajay", session_id="s", harness_id="sqlite",
                            operation_id="safe_mutation")
    r = SVC.run_harness_action(defn=defn, op=op, intent=i,
                               argv=SQ.build_mutation_argv(db_path=db, table="pilot_tbl"),
                               work_dir=ws, file_roots=[ws], owner="ajay",
                               verify_target=db, verify_kind="sqlite_db")
    assert r["status"] == "success" and r["verification"]["verified"] is True
    # mutation actually happened + DB still integral
    con = pysq.connect(db)
    assert con.execute("SELECT count(*) FROM pilot_tbl").fetchone()[0] >= 1
    con.close()
    shutil.rmtree(ws, ignore_errors=True)


@skip_no
def test_live_query_readonly_cannot_write():
    """A read op uses -readonly; a write attempted via it fails (DB unchanged)."""
    ws = tempfile.mkdtemp(); db = _seed_db(ws)
    defn = SQ.definition(); op = {o.operation_id: o for o in SQ.operations()}["query_readonly"]
    i = HarnessActionIntent(user_id="ajay", session_id="s", harness_id="sqlite",
                            operation_id="query_readonly")
    # even if a write SQL reached the CLI, -readonly blocks it at the engine
    r = SVC.run_harness_action(defn=defn, op=op, intent=i,
                               argv=SQ.build_query_argv(db_path=db, sql="INSERT INTO t(v) VALUES('x')"),
                               work_dir=ws, file_roots=[ws], owner="ajay",
                               verify_target=db, verify_kind="sqlite_db")
    con = pysq.connect(db)
    assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 2   # unchanged
    con.close()
    shutil.rmtree(ws, ignore_errors=True)


@skip_no
def test_cross_user_blocked():
    ws = tempfile.mkdtemp(); db = _seed_db(ws)
    defn = SQ.definition(); op = {o.operation_id: o for o in SQ.operations()}["inspect_schema"]
    i = HarnessActionIntent(user_id="victim", session_id="s", harness_id="sqlite",
                            operation_id="inspect_schema")
    r = SVC.run_harness_action(defn=defn, op=op, intent=i,
                               argv=SQ.build_schema_argv(db_path=db), work_dir=ws,
                               file_roots=[ws], owner="attacker")
    assert r["status"] == "blocked" and "ownership" in r["error_code"]
    shutil.rmtree(ws, ignore_errors=True)
