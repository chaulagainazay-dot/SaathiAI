"""M17.9 run-ledger unit tests — schema, transition graph, compare-and-set,
idempotency, heartbeat classification, retention, sanitization, legacy parsing,
migration, read model, health. Pure ledger logic (no live processes here).
"""
import json
import os

import pytest

from saathi.application_harness import run_ledger as L
from saathi.application_harness import ledger_migration as Mg


def _led(tmp_path):
    return L.RunLedger(tmp_path / "ledger.db")


def _running(led, rid="r", owner="ajay", pid=None):
    led.create_run(rid, owner=owner, harness_id="h", operation_id="op")
    led.claim(rid, pid=pid if pid is not None else os.getpid())
    led.mark_running(rid, pid=pid if pid is not None else os.getpid())
    return rid


# ── schema / creation ───────────────────────────────────────────────────────
def test_create_run_starts_queued(tmp_path):
    led = _led(tmp_path)
    assert led.create_run("r", owner="ajay")["created"] is True
    assert led.latest_state("r") == L.QUEUED
    row = led.inspect("r")
    assert row["state_version"] == 0 and row["origin"] == "ledger"


def test_create_requires_owner(tmp_path):
    led = _led(tmp_path)
    with pytest.raises(L.LedgerSecurityError):
        led.create_run("r", owner="")


def test_duplicate_run_id_rejected(tmp_path):
    led = _led(tmp_path)
    led.create_run("r", owner="ajay")
    with pytest.raises(L.LedgerError):
        led.create_run("r", owner="ajay")


# ── transition graph ────────────────────────────────────────────────────────
def test_valid_lifecycle(tmp_path):
    led = _led(tmp_path)
    led.create_run("r", owner="ajay")
    assert led.claim("r", pid=os.getpid()) is True
    assert led.mark_running("r")["state"] == L.RUNNING
    assert led.complete("r", state=L.SUCCEEDED)["state"] == L.SUCCEEDED


def test_illegal_edge_fails_closed(tmp_path):
    led = _led(tmp_path)
    led.create_run("r", owner="ajay")
    # queued -> running is not a legal edge (must go through starting)
    with pytest.raises(L.LedgerTransitionError):
        led._transition("r", L.RUNNING)


def test_terminal_state_is_immutable(tmp_path):
    led = _led(tmp_path)
    _running(led, "r")
    led.complete("r", state=L.SUCCEEDED)
    with pytest.raises(L.LedgerTransitionError):
        led._transition("r", L.RUNNING)          # no resurrection
    with pytest.raises(L.LedgerTransitionError):
        led._transition("r", L.FAILED, terminal_at=1)


def test_terminal_same_state_is_idempotent_noop(tmp_path):
    led = _led(tmp_path)
    _running(led, "r")
    led.complete("r", state=L.SUCCEEDED)
    assert led.complete("r", state=L.SUCCEEDED)["noop"] is True


def test_complete_rejects_non_terminal(tmp_path):
    led = _led(tmp_path)
    _running(led, "r")
    with pytest.raises(L.LedgerTransitionError):
        led.complete("r", state=L.RUNNING)


# ── compare-and-set / stale writer ──────────────────────────────────────────
def test_second_claim_loses(tmp_path):
    led = _led(tmp_path)
    led.create_run("r", owner="ajay")
    assert led.claim("r", pid=os.getpid()) is True
    assert led.claim("r", pid=123) is False      # only one claimant


def test_stale_version_rejected(tmp_path):
    led = _led(tmp_path)
    _running(led, "r")
    with pytest.raises(L.LedgerConcurrencyError):
        led._transition("r", L.SUCCEEDED, expected_version=99, terminal_at=1)


def test_cas_current_version_succeeds(tmp_path):
    led = _led(tmp_path)
    _running(led, "r")
    ver = led.inspect("r")["state_version"]
    res = led._transition("r", L.SUCCEEDED, expected_version=ver, terminal_at=1)
    assert res["ok"] and res["version"] == ver + 1


# ── ownership ───────────────────────────────────────────────────────────────
def test_cross_user_cancel_denied(tmp_path):
    led = _led(tmp_path)
    _running(led, "r", owner="ajay")
    res = led.request_cancellation("r", requester="mallory")
    assert res["cancelled"] is False and "ownership" in res["reason"]
    assert led.latest_state("r") == L.RUNNING    # untouched


def test_owner_cancel_then_duplicate_is_safe(tmp_path):
    led = _led(tmp_path)
    _running(led, "r", owner="ajay")
    assert led.request_cancellation("r", requester="ajay")["cancelled"] is True
    # duplicate cancellation is idempotent, not an error
    assert led.request_cancellation("r", requester="ajay")["cancelled"] is True
    assert led.latest_state("r") == L.CANCEL_REQ


# ── idempotency ─────────────────────────────────────────────────────────────
def test_idempotency_key_prevents_duplicate_run(tmp_path):
    led = _led(tmp_path)
    a = led.create_run("r1", owner="ajay", idempotency_key="K")
    b = led.create_run("r2", owner="ajay", idempotency_key="K")
    assert a["created"] is True and b["created"] is False
    assert b["run_id"] == "r1"                   # points at the first run
    assert led.inspect("r2") is None             # no second row


# ── heartbeat classification ────────────────────────────────────────────────
def test_heartbeat_updates_only_active_runs(tmp_path):
    led = _led(tmp_path)
    _running(led, "r")
    assert led.record_heartbeat("r") is True
    led.complete("r", state=L.SUCCEEDED)
    assert led.record_heartbeat("r") is False    # dead run can't forge heartbeat


def test_classify_active_vs_stale_vs_missing(tmp_path):
    led = _led(tmp_path)
    _running(led, "r", pid=os.getpid())
    row = led.inspect("r")
    assert led.classify(row, now=row["heartbeat_at"] + 1, is_alive=lambda p: True) == "active"
    assert led.classify(row, now=row["heartbeat_at"] + 999,
                        is_alive=lambda p: True) == "heartbeat_stale"
    assert led.classify(row, is_alive=lambda p: False) == "process_missing"


def test_classify_single_missed_heartbeat_is_not_failure(tmp_path):
    led = _led(tmp_path)
    _running(led, "r", pid=os.getpid())
    row = led.inspect("r")
    # just past nothing — a fresh run is active, never auto-failed
    assert led.classify(row, now=row["heartbeat_at"] + 5, stale_sec=30,
                        is_alive=lambda p: True) == "active"


def test_classify_cancellation_stuck(tmp_path):
    led = _led(tmp_path)
    _running(led, "r", owner="ajay", pid=os.getpid())
    led.request_cancellation("r", requester="ajay")
    row = led.inspect("r")
    assert led.classify(row, now=row["cancel_requested_at"] + 999,
                        is_alive=lambda p: True) == "cancellation_stuck"


# ── recovery ────────────────────────────────────────────────────────────────
def test_reconcile_dead_pid_once_and_idempotent(tmp_path):
    led = _led(tmp_path)
    _running(led, "r", pid=999999999)
    r1 = led.reconcile_run("r", is_alive=lambda p: False)
    assert r1["reconciled"] is True
    assert led.latest_state("r") == L.CRASH_RECOVERED
    r2 = led.reconcile_run("r", is_alive=lambda p: False)   # idempotent
    assert r2["reconciled"] is False and r2["reason"] == "already_terminal"


def test_reconcile_never_overwrites_live_process(tmp_path):
    led = _led(tmp_path)
    _running(led, "r", pid=os.getpid())
    r = led.reconcile_run("r", is_alive=lambda p: True)
    assert r["reconciled"] is False and r["reason"] == "process_alive"
    assert led.latest_state("r") == L.RUNNING


def test_reconcile_stale_recovers_and_reports_attention(tmp_path):
    led = _led(tmp_path)
    _running(led, "dead", pid=999999999)
    _running(led, "alive", pid=os.getpid())
    out = led.reconcile_stale(is_alive=lambda p: p == os.getpid())
    assert out["recovered"] == ["dead"]
    assert led.latest_state("alive") == L.RUNNING


def test_mark_recovery_records_evidence_without_rerun(tmp_path):
    led = _led(tmp_path)
    _running(led, "r"); led.complete("r", state=L.CRASH_RECOVERED)
    out = led.mark_recovery("r", evidence="verified no partial write")
    assert out["ok"] and led.inspect("r")["recovery_status"] == "recovered"
    assert led.latest_state("r") == L.CRASH_RECOVERED     # state unchanged


# ── retention / transition history ──────────────────────────────────────────
def test_cleanup_removes_old_terminal_only(tmp_path):
    led = _led(tmp_path)
    _running(led, "old"); led.complete("old", state=L.SUCCEEDED)
    _running(led, "live")
    # force old terminal_at far in the past
    with led._conn() as c:
        c.execute("UPDATE run SET terminal_at=1 WHERE run_id='old'")
    out = led.cleanup(retention_sec=10, now=1000)
    assert out["deleted"] == 1 and led.inspect("old") is None
    assert led.latest_state("live") == L.RUNNING


def test_transition_history_is_bounded(tmp_path):
    led = _led(tmp_path)
    _running(led, "r")
    hist = led.transitions("r", limit=10_000)
    assert len(hist) <= L._TRANSITION_HISTORY_CAP
    assert [h["to_state"] for h in hist][:3] == [L.QUEUED, L.STARTING, L.RUNNING]


# ── sanitization ────────────────────────────────────────────────────────────
def test_secret_metadata_rejected(tmp_path):
    led = _led(tmp_path)
    with pytest.raises(L.LedgerSecurityError):
        led.create_run("r", owner="ajay", metadata={"api_key": "x"})
    with pytest.raises(L.LedgerSecurityError):
        led.create_run("r2", owner="ajay", metadata={"note": "sk-" + "a" * 20})


def test_control_char_field_rejected(tmp_path):
    led = _led(tmp_path)
    with pytest.raises(L.LedgerSecurityError):
        led.create_run("r", owner="ajay\x00root")


# ── legacy parsing / migration ──────────────────────────────────────────────
def _write_legacy(p):
    p.write_text("\n".join([
        json.dumps({"run_id": "a", "event": "start", "state": "running",
                    "owner": "ajay", "harness_id": "sleep", "pid": 999999999, "ts": 1000.0}),
        json.dumps({"run_id": "a", "event": "end", "state": "success",
                    "exit_code": 0, "ts": 1001.0}),
        json.dumps({"run_id": "b", "event": "start", "state": "running",
                    "owner": "x", "pid": 999999999, "ts": 1002.0}),
        "TORN {not json",
        json.dumps(["not", "a", "dict"]),
    ]) + "\n")


def test_legacy_malformed_records_rejected_safely(tmp_path):
    p = tmp_path / "journal.jsonl"
    _write_legacy(p)
    recs, bad = Mg._read_legacy(p)
    assert bad == 2 and {r["run_id"] for r in recs} == {"a", "b"}


def test_migration_preserves_provenance_and_backs_up(tmp_path):
    led = _led(tmp_path)
    p = tmp_path / "journal.jsonl"
    _write_legacy(p)
    res = Mg.migrate_jsonl(p, led, is_alive=lambda pid: False)
    assert res["backup"] and os.path.exists(res["backup"])
    assert p.exists()                            # legacy left untouched
    assert led.latest_state("a") == L.SUCCEEDED
    assert led.latest_state("b") == L.CRASH_RECOVERED   # dead 'running' -> crash
    assert led.inspect("a")["origin"] == "migrated_jsonl"
    assert led.inspect("a")["created_at"] == 1000.0     # timestamp preserved


def test_migration_is_idempotent_and_reversible(tmp_path):
    led = _led(tmp_path)
    p = tmp_path / "journal.jsonl"
    _write_legacy(p)
    Mg.migrate_jsonl(p, led, is_alive=lambda pid: False)
    again = Mg.migrate_jsonl(p, led, is_alive=lambda pid: False)
    assert again["imported"] == []              # nothing new
    back = Mg.rollback(led)
    assert back["rolled_back"] == 2 and led.inspect("a") is None


def test_migration_never_overwrites_live_ledger_run(tmp_path):
    led = _led(tmp_path)
    _running(led, "a", owner="live-owner")       # a live run named 'a'
    p = tmp_path / "journal.jsonl"
    _write_legacy(p)
    Mg.migrate_jsonl(p, led, is_alive=lambda pid: False)
    assert led.inspect("a")["origin"] == "ledger"   # live run untouched
    assert led.inspect("a")["owner"] == "live-owner"


# ── read model / health ─────────────────────────────────────────────────────
def test_read_model_is_owner_safe(tmp_path):
    led = _led(tmp_path)
    _running(led, "r", owner="ajay", pid=os.getpid())
    rm = led.read_model("ajay", is_alive=lambda p: True)
    assert rm["active_count"] == 1
    row = rm["active_runs"][0]
    # no argv / stdout / secrets / raw metadata anywhere in the read model
    assert set(row) == {"run_id", "owner", "harness_id", "operation_id", "state",
                        "duration_sec", "last_heartbeat_age_sec", "class",
                        "cancellation", "recovery_status", "verification_status",
                        "failure_code"}


def test_read_model_scoped_to_owner(tmp_path):
    led = _led(tmp_path)
    _running(led, "mine", owner="ajay", pid=os.getpid())
    _running(led, "theirs", owner="bob", pid=os.getpid())
    rm = led.read_model("ajay", is_alive=lambda p: True)
    assert [r["run_id"] for r in rm["active_runs"]] == ["mine"]


def test_health_reports_integrity_and_census(tmp_path):
    led = _led(tmp_path)
    _running(led, "r"); led.complete("r", state=L.SUCCEEDED)
    h = led.health()
    assert h["integrity"] == "ok" and h["ok"] is True
    assert h["by_state"].get("succeeded") == 1
    assert h["idempotency_collisions"] == 0
