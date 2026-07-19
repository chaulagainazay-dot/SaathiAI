"""M41 — Bounded read-only canary rollout tests (offline; deterministic).

Canary is deny-by-default. It never grants ACTIVE/production/write, never expands
scope, and never touches the M32 ExecutionMode.CANARY prohibition. Auto-rollback
and kill switch are mandatory.
"""
from __future__ import annotations

import json

import pytest

from saathi.credentials import m41, m39_3
from saathi.credentials.leakscan import is_clean

GRANT_KEYS = ("grants_active", "grants_production", "grants_write", "grants_rollout_full")


def _approval():
    rec = {f: "x" for f in m39_3._REQUIRED_APPROVAL_FIELDS}
    rec.update(provider="github_meta", endpoints=["user", "meta"], methods=["GET"],
               rollout_percent=1, explicit_acknowledgements=list(m39_3._REQUIRED_APPROVAL_ACKS))
    return rec


def _cert():
    return {"decision": "LIVE_CERTIFIED", "live_certified": True,
            "provider": "github_meta", "read_only": True}


# ── deny-by-default ──────────────────────────────────────────────────────────
def test_default_not_activated():
    b = m41.run_canary_rollout(m41.M41Config())
    assert b["verdict"] == "CANARY_NOT_ACTIVATED"
    assert b["authorization"]["authorized"] is False


def test_missing_approval_blocks():
    cfg = m41.M41Config(m40_cert_record=_cert())  # cert but no approval
    b = m41.run_canary_rollout(cfg)
    assert b["verdict"] == "CANARY_NOT_ACTIVATED"
    assert "operator_approval_invalid_or_absent" in b["authorization"]["blockers"]


def test_missing_certification_blocks():
    cfg = m41.M41Config(approval_record=_approval())  # approval but no cert
    b = m41.run_canary_rollout(cfg)
    assert b["verdict"] == "CANARY_NOT_ACTIVATED"
    assert "m40_live_certification_required" in b["authorization"]["blockers"]


def test_uncertified_provider_blocks():
    cfg = m41.M41Config(approval_record=_approval(),
                        m40_cert_record={"decision": "LIVE_BLOCKED", "live_certified": False})
    assert m41.run_canary_rollout(cfg)["verdict"] == "CANARY_NOT_ACTIVATED"


# ── scope / bounds enforcement ───────────────────────────────────────────────
def test_rollout_percent_out_of_bounds_blocks():
    cfg = m41.M41Config(approval_record=_approval(), m40_cert_record=_cert(), rollout_percent=50)
    b = m41.run_canary_rollout(cfg)
    assert b["authorization"]["authorized"] is False
    assert "rollout_percent_out_of_bounds" in b["authorization"]["blockers"]


def test_approval_write_method_rejected():
    rec = _approval(); rec["methods"] = ["POST"]
    cfg = m41.M41Config(approval_record=rec, m40_cert_record=_cert())
    b = m41.run_canary_rollout(cfg)
    assert b["authorization"]["authorized"] is False


def test_approval_provider_mismatch_rejected():
    rec = _approval(); rec["provider"] = "stripe"
    cfg = m41.M41Config(approval_record=rec, m40_cert_record=_cert())
    assert m41.run_canary_rollout(cfg)["verdict"] == "CANARY_NOT_ACTIVATED"


# ── bounded rollout completes ────────────────────────────────────────────────
def test_rehearsal_bounded_completes():
    b = m41.run_canary_rehearsal()
    assert b["verdict"] == "CANARY_ACTIVE_BOUNDED"
    assert b["controller"]["state"] == "COMPLETED"
    assert b["controller"]["all_handles_closed"] is True
    assert b["controller"]["live_network"] is False


# ── mandatory auto-rollback + kill switch ────────────────────────────────────
def test_auto_rollback_on_fault():
    b = m41.run_canary_rehearsal(fault_at=1)
    assert b["verdict"] == "CANARY_ROLLED_BACK"
    assert b["controller"]["state"] == "ROLLED_BACK"
    assert b["controller"]["rollback_reason"]  # a trigger name
    assert b["controller"]["all_handles_closed"] is True  # cleanup on rollback


def test_kill_switch_blocks_before_start():
    b = m41.run_canary_rehearsal(inject_rollback=True)
    assert b["verdict"] == "CANARY_BLOCKED"


def test_rollback_stops_further_increments():
    b = m41.run_canary_rehearsal(fault_at=0)  # fault on first increment
    assert b["verdict"] == "CANARY_ROLLED_BACK"
    assert b["controller"]["increments_run"] == 1  # halted immediately


def test_evaluate_rollback_killswitch_is_sev1():
    ev = m41.evaluate_rollback({}, environ={"SAATHI_M39_KILL_SWITCH": "1"})
    assert ev["should_rollback"] is True
    assert ev["highest_severity"] == "SEV1"


# ── never grants active/production/write ─────────────────────────────────────
def test_never_grants_active_or_production():
    for b in (m41.run_canary_rollout(m41.M41Config()),
              m41.run_canary_rehearsal(),
              m41.run_canary_rehearsal(fault_at=1)):
        for k in GRANT_KEYS:
            assert b[k] is False
        assert b["scope_expansion"] == "FORBIDDEN"
        for v in b["authorities"].values():
            assert v == "NOT GRANTED"
        assert b["trading_guardian"] == "UNENGAGED"


def test_m32_prohibition_untouched():
    b = m41.run_canary_rehearsal()
    assert b["m32_canary_execution_mode"] == "PROHIBITION_UNCHANGED"


def test_grants_canary_execution_only_when_bounded_complete():
    ok = m41.run_canary_rehearsal()
    assert ok["grants_canary_execution"] is True   # bounded read-only only
    rb = m41.run_canary_rehearsal(fault_at=1)
    assert rb["grants_canary_execution"] is False
    default = m41.run_canary_rollout(m41.M41Config())
    assert default["grants_canary_execution"] is False


# ── determinism + leak ───────────────────────────────────────────────────────
def test_evidence_deterministic_and_clean():
    a = m41.build_m41_evidence()
    b = m41.build_m41_evidence()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["summary"]["grants_active"] is False
    for name, body in a.items():
        assert is_clean(body), name


def test_evidence_emit(tmp_path):
    res = m41.emit_m41_evidence(tmp_path)
    assert res["count"] == 5
    for p in res["written"]:
        assert is_clean(json.loads(open(p).read()))
