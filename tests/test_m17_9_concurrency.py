"""M17.9 multi-PROCESS concurrency proofs (not threads).

Real OS processes contend on the same SQLite ledger file: concurrent claim,
concurrent cancel, completion/cancel race, many heartbeat writers, recovery while
another process is alive, and database-lock handling under load. Uses the 'spawn'
start method so workers are genuine separate interpreters, exercising WAL +
BEGIN IMMEDIATE + busy_timeout — the real cross-process path, not in-process locks.
"""
import multiprocessing as mp
import os
import time

import pytest

from saathi.application_harness import run_ledger as L

POSIX = os.name == "posix"
pytestmark = pytest.mark.skipif(not POSIX, reason="POSIX multi-process control")
CTX = mp.get_context("spawn")


# ── module-level workers (must be importable for spawn) ──────────────────────
def _w_claim(db_path, run_id, q, barrier):
    barrier.wait()                              # race the claim simultaneously
    led = L.RunLedger(db_path)
    q.put(led.claim(run_id, pid=os.getpid()))


def _w_cancel(db_path, run_id, requester, q, barrier):
    barrier.wait()
    led = L.RunLedger(db_path)
    try:
        q.put(bool(led.request_cancellation(run_id, requester=requester)["cancelled"]))
    except Exception as e:                      # must never crash under contention
        q.put(f"ERR:{e}")


def _w_complete(db_path, run_id, q, barrier):
    barrier.wait()
    led = L.RunLedger(db_path)
    try:
        led.complete(run_id, state=L.SUCCEEDED)
        q.put("completed")
    except L.LedgerError as e:
        q.put(f"lost:{e.code}")


def _w_heartbeat(db_path, run_id, n, q):
    led = L.RunLedger(db_path)
    ok = 0
    for _ in range(n):
        try:
            if led.record_heartbeat(run_id):
                ok += 1
        except Exception as e:
            q.put(f"ERR:{e}"); return
    q.put(ok)


def _w_full_run(db_path, idx, q):
    """Independent run through the whole lifecycle — many at once stress locks."""
    led = L.RunLedger(db_path)
    rid = f"run-{idx}"
    try:
        led.create_run(rid, owner=f"u{idx}")
        led.claim(rid, pid=os.getpid())
        led.mark_running(rid)
        led.record_heartbeat(rid)
        led.complete(rid, state=L.SUCCEEDED)
        q.put(led.latest_state(rid))
    except Exception as e:
        q.put(f"ERR:{e}")


def _drain(q, n, timeout=30):
    out = []
    end = time.time() + timeout
    while len(out) < n and time.time() < end:
        try:
            out.append(q.get(timeout=timeout))
        except Exception:
            break
    return out


# ── concurrent claim: exactly one winner ────────────────────────────────────
def test_concurrent_claim_exactly_one_winner(tmp_path):
    db = str(tmp_path / "ledger.db")
    led = L.RunLedger(db)
    led.create_run("r", owner="ajay")
    n = 8
    q = CTX.Queue()
    barrier = CTX.Barrier(n)
    procs = [CTX.Process(target=_w_claim, args=(db, "r", q, barrier)) for _ in range(n)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(30)
    results = _drain(q, n)
    assert results.count(True) == 1, f"expected 1 claimant, got {results}"
    assert led.latest_state("r") == L.STARTING


# ── concurrent cancel: all safe, converge on one state ──────────────────────
def test_concurrent_cancel_all_safe(tmp_path):
    db = str(tmp_path / "ledger.db")
    led = L.RunLedger(db)
    led.create_run("r", owner="ajay"); led.claim("r", pid=os.getpid())
    led.mark_running("r")
    n = 6
    q = CTX.Queue()
    barrier = CTX.Barrier(n)
    procs = [CTX.Process(target=_w_cancel, args=(db, "r", "ajay", q, barrier))
             for _ in range(n)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(30)
    results = _drain(q, n)
    assert all(r is True for r in results), f"cancel not all-safe: {results}"
    assert led.latest_state("r") == L.CANCEL_REQ


# ── completion / cancel race resolves deterministically ─────────────────────
def test_completion_cancel_race_is_deterministic(tmp_path):
    db = str(tmp_path / "ledger.db")
    led = L.RunLedger(db)
    led.create_run("r", owner="ajay"); led.claim("r", pid=os.getpid())
    led.mark_running("r")
    q = CTX.Queue()
    barrier = CTX.Barrier(2)
    a = CTX.Process(target=_w_complete, args=(db, "r", q, barrier))
    b = CTX.Process(target=_w_cancel, args=(db, "r", "ajay", q, barrier))
    a.start(); b.start(); a.join(30); b.join(30)
    _drain(q, 2)
    final = led.latest_state("r")
    # Either completion won (succeeded) or cancel won the running slot then the
    # process still finished (cancellation_requested→succeeded is legal). Both
    # orderings converge on a single, legal terminal/near-terminal state.
    assert final in (L.SUCCEEDED, L.CANCEL_REQ)
    # exactly one 'succeeded' terminal transition at most — no double completion
    succ = [t for t in led.transitions("r") if t["to_state"] == L.SUCCEEDED]
    assert len(succ) <= 1
    assert led.health()["integrity"] == "ok"


# ── many heartbeat writers, no lock error, state unchanged ──────────────────
def test_multiple_heartbeat_writers(tmp_path):
    db = str(tmp_path / "ledger.db")
    led = L.RunLedger(db)
    led.create_run("r", owner="ajay"); led.claim("r", pid=os.getpid())
    led.mark_running("r")
    n = 5
    q = CTX.Queue()
    procs = [CTX.Process(target=_w_heartbeat, args=(db, "r", 20, q)) for _ in range(n)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(30)
    results = _drain(q, n)
    assert all(isinstance(r, int) for r in results), f"heartbeat error: {results}"
    assert sum(results) > 0
    assert led.latest_state("r") == L.RUNNING     # heartbeats never change state


# ── recovery must not overwrite a still-live process (cross-process) ────────
def test_recovery_skips_live_then_recovers_dead(tmp_path):
    import subprocess
    db = str(tmp_path / "ledger.db")
    led = L.RunLedger(db)
    child = subprocess.Popen(["/bin/sleep", "30"])
    led.create_run("r", owner="ajay")
    led.claim("r", pid=child.pid); led.mark_running("r", pid=child.pid)
    # while the child lives, reconcile is a no-op
    assert led.reconcile_run("r")["reconciled"] is False
    assert led.latest_state("r") == L.RUNNING
    child.kill(); child.wait()
    for _ in range(100):
        if led.reconcile_run("r").get("reconciled"):
            break
        time.sleep(0.02)
    assert led.latest_state("r") == L.CRASH_RECOVERED


# ── database-lock handling under heavy concurrent writers ───────────────────
def test_db_lock_handling_under_load(tmp_path):
    db = str(tmp_path / "ledger.db")
    L.RunLedger(db)                              # init schema
    n = 12
    q = CTX.Queue()
    procs = [CTX.Process(target=_w_full_run, args=(db, i, q)) for i in range(n)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(40)
    results = _drain(q, n)
    assert results.count(L.SUCCEEDED) == n, f"lock contention lost runs: {results}"
    assert L.RunLedger(db).health()["integrity"] == "ok"
