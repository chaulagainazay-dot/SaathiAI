"""M17.9 LIVE lifecycle + integration — real processes through the ONE adapter,
with a SQLite ledger as the durable journal. Proves: transactional lifecycle,
process cancellation, crash reconciliation, restart persistence, orphan-free
cleanup, and no terminal-state resurrection — end to end, no mocks.
"""
import os
import time

import pytest

from saathi.application_harness import run_ledger as L
from saathi.application_harness.adapter import ApplicationHarnessAdapter
from saathi.application_harness.models import HarnessDefinition, HarnessActionIntent, TrustStatus
from saathi.application_harness.task_control import HarnessTaskController

POSIX = os.name == "posix"
pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(not POSIX, reason="POSIX process control only"),
]
HAS_SLEEP = os.path.exists("/bin/sleep")
HAS_SH = os.path.exists("/bin/sh")


def _defn():
    return HarnessDefinition(harness_id="tasktest", display_name="Task Test",
                             application_name="tasktest", version="system",
                             source_type="local", trust_status=TrustStatus.APPROVED.value)


def _intent(user="ajay"):
    return HarnessActionIntent(user_id=user, session_id="s", harness_id="tasktest",
                               operation_id="run")


def _alive(pid):
    try:
        os.kill(pid, 0); return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


# ── adapter writes ledger state on a real successful run ────────────────────
@pytest.mark.skipif(not HAS_SH, reason="/bin/sh absent")
def test_adapter_ledgers_success(tmp_path):
    led = L.RunLedger(tmp_path / "ledger.db")
    adapter = ApplicationHarnessAdapter()
    res = adapter.run(defn=_defn(), intent=_intent(), argv=["/bin/sh", "-c", "exit 0"],
                      work_dir=str(tmp_path), file_roots=[str(tmp_path)], timeout=5,
                      run_id="ok1", journal=led)
    assert res.status == "success"
    assert led.latest_state("ok1") == L.SUCCEEDED
    # full transactional trail: queued→starting→running→succeeded
    assert [t["to_state"] for t in led.transitions("ok1")] == \
        [L.QUEUED, L.STARTING, L.RUNNING, L.SUCCEEDED]


# ── controller claims + launches a real long run, then cancels it ───────────
@pytest.mark.skipif(not HAS_SLEEP, reason="/bin/sleep absent")
def test_controller_live_cancel_ledgered_orphan_free(tmp_path):
    led = L.RunLedger(tmp_path / "ledger.db")
    ctl = HarnessTaskController(journal=led)
    h = ctl.launch(run_id="c1", defn=_defn(), intent=_intent(),
                   argv=["/bin/sleep", "30"], work_dir=str(tmp_path),
                   file_roots=[str(tmp_path)], owner="ajay", timeout=60)
    pid = None
    for _ in range(200):
        act = led.list_active()
        if act and act[0].get("pid"):
            pid = act[0]["pid"]; break
        time.sleep(0.02)
    assert pid and _alive(pid)
    assert led.latest_state("c1") == L.RUNNING
    assert ctl.cancel("c1", requester="ajay")["cancelled"] is True
    res = h.join(timeout=5)
    assert res is not None and res.status == "cancelled"
    for _ in range(100):
        if not _alive(pid):
            break
        time.sleep(0.02)
    assert not _alive(pid)                        # orphan-free
    assert led.latest_state("c1") == L.CANCELLED
    # went through cancellation_requested (state machine honoured)
    states = [t["to_state"] for t in led.transitions("c1")]
    assert L.CANCEL_REQ in states and states[-1] == L.CANCELLED


# ── live timeout is ledgered as timed_out ───────────────────────────────────
@pytest.mark.skipif(not HAS_SLEEP, reason="/bin/sleep absent")
def test_live_timeout_ledgered(tmp_path):
    led = L.RunLedger(tmp_path / "ledger.db")
    adapter = ApplicationHarnessAdapter()
    res = adapter.run(defn=_defn(), intent=_intent(), argv=["/bin/sleep", "30"],
                      work_dir=str(tmp_path), file_roots=[str(tmp_path)], timeout=0.5,
                      run_id="t1", journal=led)
    assert res.status == "timeout"
    assert led.latest_state("t1") == L.TIMED_OUT


# ── crash reconciliation on a real killed process ───────────────────────────
@pytest.mark.skipif(not HAS_SLEEP, reason="/bin/sleep absent")
def test_live_crash_reconciled(tmp_path):
    import subprocess
    led = L.RunLedger(tmp_path / "ledger.db")
    child = subprocess.Popen(["/bin/sleep", "30"])
    led.create_run("k1", owner="ajay")
    led.claim("k1", pid=child.pid); led.mark_running("k1", pid=child.pid)
    child.kill(); child.wait()
    out = led.reconcile_stale(is_alive=_alive)
    assert "k1" in out["recovered"]
    assert led.latest_state("k1") == L.CRASH_RECOVERED
    # recovery is idempotent — a second sweep does nothing
    assert led.reconcile_stale(is_alive=_alive)["recovered"] == []


# ── restart persistence: a fresh ledger on the same DB sees prior state ─────
@pytest.mark.skipif(not HAS_SH, reason="/bin/sh absent")
def test_restart_persistence(tmp_path):
    db = tmp_path / "ledger.db"
    led = L.RunLedger(db)
    adapter = ApplicationHarnessAdapter()
    adapter.run(defn=_defn(), intent=_intent(), argv=["/bin/sh", "-c", "exit 0"],
                work_dir=str(tmp_path), file_roots=[str(tmp_path)], timeout=5,
                run_id="p1", journal=led)
    # simulate a controller restart — brand new ledger object, same file
    led2 = L.RunLedger(db)
    assert led2.latest_state("p1") == L.SUCCEEDED
    assert led2.health()["integrity"] == "ok"


# ── backup + isolated restore preserves the ledger ─────────────────────────
def test_backup_and_isolated_restore_preserves_ledger(tmp_path):
    import shutil
    db = tmp_path / "ledger.db"
    led = L.RunLedger(db)
    led.create_run("b1", owner="ajay"); led.claim("b1", pid=os.getpid())
    led.mark_running("b1"); led.complete("b1", state=L.SUCCEEDED)
    led.create_run("b2", owner="bob")
    assert led.health()["integrity"] == "ok"
    # backup (checkpoint WAL first so the single-file copy is complete)
    with led._conn() as c:
        c.execute("PRAGMA wal_checkpoint(FULL)")
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    shutil.copy2(db, backup_dir / "ledger.db")
    # destroy the original, restore into a fresh ISOLATED location
    shutil.rmtree(str(tmp_path / "ledger.db"), ignore_errors=True)
    db.unlink()
    restore_dir = tmp_path / "restore"
    restore_dir.mkdir()
    restored = restore_dir / "ledger.db"
    shutil.copy2(backup_dir / "ledger.db", restored)
    led2 = L.RunLedger(restored)
    assert led2.health()["integrity"] == "ok"
    assert led2.latest_state("b1") == L.SUCCEEDED     # terminal result preserved
    assert led2.latest_state("b2") == L.QUEUED
    # transition history survived the round-trip
    assert [t["to_state"] for t in led2.transitions("b1")] == \
        [L.QUEUED, L.STARTING, L.RUNNING, L.SUCCEEDED]


# ── a terminal run is never resurrected by a late adapter callback ──────────
def test_no_terminal_resurrection_from_late_callback(tmp_path):
    led = L.RunLedger(tmp_path / "ledger.db")
    led.create_run("r", owner="ajay"); led.claim("r", pid=os.getpid())
    led.mark_running("r"); led.complete("r", state=L.SUCCEEDED)
    # a stale/duplicate adapter end-callback must be swallowed, not resurrect
    led.record_end("r", "failed", 1)
    led.record_start("r", harness_id="h", owner="ajay", pid=os.getpid(), pgid=None)
    assert led.latest_state("r") == L.SUCCEEDED
