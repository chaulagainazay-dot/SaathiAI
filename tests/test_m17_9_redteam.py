"""M17.9 red-team probes — deterministic adversarial tests against the run ledger.

Each probe encodes a specific attack the ledger must defeat: duplicate claim,
stale writer, terminal resurrection, cross-user cancel, run-ID substitution,
PID reuse, process-group substitution, idempotency collision, forged heartbeat,
forged recovery, migration record injection, malformed legacy JSONL, DB path
traversal, symlink DB substitution, cancellation/completion race, recovery of a
live process, secret injection, unbounded transition history, and lock DoS.
"""
import json
import os

import pytest

from saathi.application_harness import run_ledger as L
from saathi.application_harness import ledger_migration as Mg


def _led(tmp_path):
    return L.RunLedger(tmp_path / "ledger.db")


def _running(led, rid="r", owner="ajay", pid=None):
    led.create_run(rid, owner=owner, harness_id="h")
    led.claim(rid, pid=pid if pid is not None else os.getpid())
    led.mark_running(rid, pid=pid if pid is not None else os.getpid())
    return rid


# 1. duplicate run claim ─────────────────────────────────────────────────────
def test_probe_duplicate_claim(tmp_path):
    led = _led(tmp_path)
    led.create_run("r", owner="ajay")
    assert [led.claim("r", pid=1), led.claim("r", pid=2), led.claim("r", pid=3)] \
        == [True, False, False]


# 2. stale writer ────────────────────────────────────────────────────────────
def test_probe_stale_writer(tmp_path):
    led = _led(tmp_path)
    _running(led, "r")
    ver = led.inspect("r")["state_version"]
    led.record_heartbeat("r")                    # (no version bump) — still fine
    # attacker replays an old version number
    with pytest.raises(L.LedgerConcurrencyError):
        led._transition("r", L.SUCCEEDED, expected_version=ver - 1, terminal_at=1)


# 3. terminal-state resurrection ─────────────────────────────────────────────
def test_probe_terminal_resurrection(tmp_path):
    led = _led(tmp_path)
    _running(led, "r"); led.complete("r", state=L.FAILED)
    for tgt in (L.RUNNING, L.STARTING, L.QUEUED, L.SUCCEEDED):
        with pytest.raises(L.LedgerTransitionError):
            led._transition("r", tgt)
    assert led.latest_state("r") == L.FAILED


# 4. cross-user cancel ───────────────────────────────────────────────────────
def test_probe_cross_user_cancel(tmp_path):
    led = _led(tmp_path)
    _running(led, "r", owner="ajay")
    assert led.request_cancellation("r", requester="attacker")["cancelled"] is False
    assert led.latest_state("r") == L.RUNNING


# 5. run-ID substitution ─────────────────────────────────────────────────────
def test_probe_run_id_substitution(tmp_path):
    led = _led(tmp_path)
    _running(led, "victim", owner="ajay")
    # attacker guesses/forges a different id — no run, no side effect
    assert led.request_cancellation("../victim", requester="ajay")["reason"] == "unknown_run"
    assert led.reconcile_run("no-such-run")["reason"] == "unknown_run"
    assert led.inspect("victim; DROP TABLE run;--") is None
    assert led.latest_state("victim") == L.RUNNING


# 6. PID reuse cannot resurrect a terminal run ───────────────────────────────
def test_probe_pid_reuse_no_resurrection(tmp_path):
    led = _led(tmp_path)
    _running(led, "r", pid=os.getpid())
    led.complete("r", state=L.SUCCEEDED)
    # even though this PID is very much alive (reused), a terminal run stays put
    assert led.reconcile_run("r", is_alive=lambda p: True)["reason"] == "already_terminal"
    assert led.latest_state("r") == L.SUCCEEDED


# 7. process-group substitution — the ledger never signals a process ─────────
def test_probe_no_process_control_in_ledger(tmp_path):
    src = (L.__file__)
    text = open(src).read()
    # the ledger is state-only: it must not kill/signal any process group. All
    # process control stays in the adapter/gateway. Fail closed if that changes.
    for forbidden in ("killpg", "SIGKILL", "SIGTERM", "subprocess.", "proc.kill"):
        assert forbidden not in text, f"ledger must not do process control: {forbidden}"
    # the ONLY permitted os.kill is the signal-0 liveness existence check
    for line in text.splitlines():
        if "os.kill(" in line:
            assert "0)" in line, f"non-liveness os.kill in ledger: {line.strip()}"


# 8. idempotency collision ───────────────────────────────────────────────────
def test_probe_idempotency_collision(tmp_path):
    led = _led(tmp_path)
    first = led.create_run("r1", owner="ajay", idempotency_key="dup")
    dup = led.create_run("r2", owner="ajay", idempotency_key="dup")
    assert first["created"] and not dup["created"]
    assert led.inspect("r2") is None
    assert led.health()["idempotency_collisions"] == 0


# 9. forged heartbeat on a dead run ──────────────────────────────────────────
def test_probe_forged_heartbeat(tmp_path):
    led = _led(tmp_path)
    _running(led, "r"); led.complete("r", state=L.CRASH_RECOVERED)
    assert led.record_heartbeat("r") is False    # terminal run cannot heartbeat


# 10. forged recovery cannot overwrite a live run ────────────────────────────
def test_probe_forged_recovery_on_live_run(tmp_path):
    led = _led(tmp_path)
    _running(led, "r", pid=os.getpid())
    assert led.reconcile_run("r", is_alive=lambda p: True)["reconciled"] is False
    led.mark_recovery("r", evidence="attacker note")     # annotate only
    assert led.latest_state("r") == L.RUNNING            # state unchanged


# 11. migration record injection ─────────────────────────────────────────────
def test_probe_migration_record_injection(tmp_path):
    led = _led(tmp_path)
    p = tmp_path / "journal.jsonl"
    p.write_text("\n".join([
        json.dumps({"run_id": "good", "event": "start", "state": "running",
                    "owner": "ajay", "pid": 999999999, "ts": 1.0}),
        json.dumps({"run_id": "good", "event": "end", "state": "success", "ts": 2.0}),
        json.dumps({"run_id": "evil", "event": "start", "state": "PWNED", "ts": 3.0}),
        json.dumps({"run_id": "ctl\x00inject", "event": "start", "state": "running", "ts": 4.0}),
    ]) + "\n")
    res = Mg.migrate_jsonl(p, led, is_alive=lambda pid: False)
    assert "good" in res["imported"]
    assert "evil" not in res["imported"]          # unknown state rejected
    assert led.inspect("evil") is None
    assert led.inspect("ctl\x00inject") is None    # control-char id rejected


# 12. malformed legacy JSONL ─────────────────────────────────────────────────
def test_probe_malformed_jsonl(tmp_path):
    p = tmp_path / "journal.jsonl"
    p.write_text('{"broken":\nnot-json\n[]\n{"run_id":"x","event":"start","state":"running","ts":1}\n')
    recs, bad = Mg._read_legacy(p)
    assert bad >= 2 and [r["run_id"] for r in recs] == ["x"]


# 13. DB path traversal (NUL) ────────────────────────────────────────────────
def test_probe_db_path_nul(tmp_path):
    with pytest.raises(L.LedgerSecurityError):
        L.RunLedger(str(tmp_path / "x\x00.db"))


# 14. symlink DB substitution ────────────────────────────────────────────────
def test_probe_symlink_db_substitution(tmp_path):
    real = tmp_path / "real.db"
    real.write_text("")
    link = tmp_path / "ledger.db"
    os.symlink(real, link)
    with pytest.raises(L.LedgerSecurityError):
        L.RunLedger(link)


# 15. cancellation/completion race — see concurrency suite (multi-process) ────
def test_probe_cancel_then_complete_single_outcome(tmp_path):
    led = _led(tmp_path)
    _running(led, "r", owner="ajay")
    led.request_cancellation("r", requester="ajay")
    led.complete("r", state=L.CANCELLED)
    # a second completion attempt is rejected — no double terminal
    with pytest.raises(L.LedgerTransitionError):
        led.complete("r", state=L.FAILED)
    assert led.latest_state("r") == L.CANCELLED


# 16. recovery of a still-live process ───────────────────────────────────────
def test_probe_recovery_of_live_process(tmp_path):
    led = _led(tmp_path)
    _running(led, "r", pid=os.getpid())
    assert led.reconcile_stale(is_alive=lambda p: True)["recovered"] == []
    assert led.latest_state("r") == L.RUNNING


# 17. secret injection into run metadata ─────────────────────────────────────
def test_probe_secret_injection(tmp_path):
    led = _led(tmp_path)
    for meta in ({"password": "hunter2"}, {"nested": {"token": "x"}},
                 {"note": "AKIA" + "A" * 16}):
        with pytest.raises(L.LedgerSecurityError):
            led.create_run("r_" + str(id(meta)), owner="ajay", metadata=meta)


# 18. unbounded transition history ───────────────────────────────────────────
def test_probe_unbounded_history_capped(tmp_path):
    led = _led(tmp_path)
    assert led.transitions("nope", limit=10**9) == []
    _running(led, "r")
    assert len(led.transitions("r", limit=10**9)) <= L._TRANSITION_HISTORY_CAP


# 19. ledger lock DoS — busy_timeout bounds the wait ─────────────────────────
def test_probe_lock_dos_has_busy_timeout(tmp_path):
    led = _led(tmp_path)
    with led._conn() as c:
        bt = c.execute("PRAGMA busy_timeout").fetchone()[0]
    assert bt >= 1000                            # bounded wait, never infinite
