"""M17.8 long-running harness task control — LIVE cancellation, timeout kill with
orphan-free process-group cleanup, resource-limit enforcement, and a durable run
journal with boot-time crash reconciliation. Real processes, real signals.
"""
import os
import time

import pytest

from saathi.application_harness.adapter import ApplicationHarnessAdapter
from saathi.application_harness.limits import ResourceLimits
from saathi.application_harness.models import HarnessDefinition, HarnessActionIntent, TrustStatus
from saathi.application_harness.run_journal import RunJournal
from saathi.application_harness.task_control import HarnessTaskController, CancelToken

POSIX = os.name == "posix"
skip_win = pytest.mark.skipif(not POSIX, reason="POSIX process control only")
HAS_SLEEP = os.path.exists("/bin/sleep")
HAS_SH = os.path.exists("/bin/sh")


def _trusted_defn():
    return HarnessDefinition(harness_id="tasktest", display_name="Task Test",
                             application_name="tasktest", version="system",
                             source_type="local",
                             trust_status=TrustStatus.APPROVED.value)


def _intent(user="ajay"):
    return HarnessActionIntent(user_id=user, session_id="s", harness_id="tasktest",
                               operation_id="run")


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


# ── LIVE cancellation of a real long-running process ────────────────────────
@skip_win
@pytest.mark.skipif(not HAS_SLEEP, reason="/bin/sleep absent")
def test_live_cancel_kills_process_orphan_free(tmp_path):
    journal = RunJournal(tmp_path / "j.jsonl")
    ctl = HarnessTaskController(journal=journal)
    h = ctl.launch(run_id="r1", defn=_trusted_defn(), intent=_intent(),
                   argv=["/bin/sleep", "30"], work_dir=str(tmp_path),
                   file_roots=[str(tmp_path)], owner="ajay", timeout=60)
    # wait until the child is actually running and recorded
    pid = None
    for _ in range(200):
        act = journal.active_runs()
        if act:
            pid = act[0]["pid"]; break
        time.sleep(0.02)
    assert pid is not None and _pid_alive(pid)
    assert ctl.cancel("r1", requester="ajay")["cancelled"] is True
    res = h.join(timeout=5)
    assert res is not None and res.status == "cancelled"
    assert res.error_code == "HARNESS_CANCELLED"
    # orphan-free: the process group is gone
    for _ in range(100):
        if not _pid_alive(pid):
            break
        time.sleep(0.02)
    assert not _pid_alive(pid)
    assert journal.latest_state("r1") == "cancelled"
    assert "r1" not in ctl.active_ids()


# ── LIVE timeout kill of a real hung process ────────────────────────────────
@skip_win
@pytest.mark.skipif(not HAS_SLEEP, reason="/bin/sleep absent")
def test_live_timeout_kills_and_journals(tmp_path):
    journal = RunJournal(tmp_path / "j.jsonl")
    adapter = ApplicationHarnessAdapter()
    res = adapter.run(defn=_trusted_defn(), intent=_intent(),
                      argv=["/bin/sleep", "30"], work_dir=str(tmp_path),
                      file_roots=[str(tmp_path)], timeout=0.5,
                      run_id="t1", journal=journal)
    assert res.status == "timeout" and res.error_code == "HARNESS_TIMEOUT"
    assert journal.latest_state("t1") == "timeout"


# ── LIVE resource-limit enforcement: RLIMIT_FSIZE stops a runaway writer ─────
@skip_win
@pytest.mark.skipif(not HAS_SH, reason="/bin/sh absent")
def test_live_fsize_limit_stops_runaway_output(tmp_path):
    adapter = ApplicationHarnessAdapter()
    lim = ResourceLimits(file_size_mb=1)   # 1 MB hard cap
    out = tmp_path / "out.bin"
    res = adapter.run(defn=_trusted_defn(), intent=_intent(),
                      argv=["/bin/sh", "-c",
                            "dd if=/dev/zero of=out.bin bs=1048576 count=20 2>/dev/null"],
                      work_dir=str(tmp_path), file_roots=[str(tmp_path)],
                      timeout=30, limits=lim)
    # the OS kills the writer (SIGXFSZ) before it can exceed the cap
    assert res.status != "success"
    if out.exists():
        assert out.stat().st_size <= 2 * 1024 * 1024   # capped near the 1 MB limit


# ── crash reconciliation: an interrupted 'running' record becomes recovered ──
def test_reconcile_marks_dead_running_as_crash_recovered(tmp_path):
    journal = RunJournal(tmp_path / "j.jsonl")
    journal.record_start("c1", harness_id="tasktest", owner="ajay",
                         pid=999999999, pgid=999999999)   # a PID that is not alive
    assert journal.latest_state("c1") == "running"
    recovered = journal.reconcile(is_alive=lambda pid: False)
    assert recovered == ["c1"]
    assert journal.latest_state("c1") == "crash_recovered"
    # a still-alive run is left untouched
    journal.record_start("c2", harness_id="tasktest", owner="ajay",
                         pid=os.getpid(), pgid=os.getpid())
    assert journal.reconcile(is_alive=lambda pid: True) == []
    assert journal.latest_state("c2") == "running"


# ── ownership: no cross-user launch or cancel ───────────────────────────────
@skip_win
@pytest.mark.skipif(not HAS_SLEEP, reason="/bin/sleep absent")
def test_cross_user_launch_and_cancel_blocked(tmp_path):
    ctl = HarnessTaskController(journal=RunJournal(tmp_path / "j.jsonl"))
    # victim owns the run; attacker intent -> blocked, never spawned
    h = ctl.launch(run_id="x1", defn=_trusted_defn(), intent=_intent("attacker"),
                   argv=["/bin/sleep", "1"], work_dir=str(tmp_path),
                   file_roots=[str(tmp_path)], owner="victim", timeout=5)
    assert h.join(timeout=1).status == "blocked"
    assert "ownership" in h.join().error_code
    # a real run owned by ajay cannot be cancelled by someone else
    h2 = ctl.launch(run_id="x2", defn=_trusted_defn(), intent=_intent("ajay"),
                    argv=["/bin/sleep", "2"], work_dir=str(tmp_path),
                    file_roots=[str(tmp_path)], owner="ajay", timeout=5)
    assert ctl.cancel("x2", requester="mallory")["cancelled"] is False
    ctl.cancel("x2", requester="ajay")
    h2.join(timeout=5)


# ── success path still journals a terminal record ───────────────────────────
@skip_win
@pytest.mark.skipif(not HAS_SH, reason="/bin/sh absent")
def test_success_run_journaled(tmp_path):
    journal = RunJournal(tmp_path / "j.jsonl")
    ctl = HarnessTaskController(journal=journal)
    h = ctl.launch(run_id="s1", defn=_trusted_defn(), intent=_intent(),
                   argv=["/bin/sh", "-c", "exit 0"], work_dir=str(tmp_path),
                   file_roots=[str(tmp_path)], owner="ajay", timeout=5)
    res = h.join(timeout=5)
    assert res.status == "success"
    assert journal.latest_state("s1") == "success"


# ── backward-compat: adapter without task-control params is unchanged ────────
@skip_win
@pytest.mark.skipif(not HAS_SH, reason="/bin/sh absent")
def test_adapter_default_off_unchanged(tmp_path):
    adapter = ApplicationHarnessAdapter()
    res = adapter.run(defn=_trusted_defn(), intent=_intent(),
                      argv=["/bin/sh", "-c", "echo hi"], work_dir=str(tmp_path),
                      file_roots=[str(tmp_path)], timeout=5)
    assert res.status == "success" and res.stdout.strip() == "hi"


def test_cancel_token_semantics():
    t = CancelToken()
    assert not t.is_cancelled()
    t.cancel()
    assert t.is_cancelled()
