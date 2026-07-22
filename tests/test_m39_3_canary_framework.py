"""M39.3 — Canary-readiness framework tests (offline; CANARY never granted)."""
from __future__ import annotations

import json

import pytest

from saathi.credentials import m39_3 as m
from saathi.credentials.leakscan import is_clean

GRANT_KEYS = ("grants_canary", "grants_active", "grants_rollout", "grants_production", "grants_write")


def _valid_record():
    rec = {f: "x" for f in m._REQUIRED_APPROVAL_FIELDS}
    rec["provider"] = "github_meta"
    rec["endpoints"] = ["user", "meta"]
    rec["methods"] = ["GET"]
    rec["rollout_percent"] = 3
    rec["explicit_acknowledgements"] = list(m._REQUIRED_APPROVAL_ACKS)
    return rec


# ── never grants ─────────────────────────────────────────────────────────────
def test_default_decision_not_granted():
    d = m.evaluate_canary_decision()
    assert d["decision"] == "CANARY_NOT_GRANTED"
    for k in GRANT_KEYS:
        assert d[k] is False


def test_best_case_still_not_granted():
    allmet = {p["id"]: True for p in m.CANARY_PREREQUISITES}
    d = m.evaluate_canary_decision(
        prerequisite_state=allmet, operator_approval_record=_valid_record()
    )
    # live evidence is NOT_EXERCISED in this series → never granted
    assert d["decision"] == "CANARY_NOT_GRANTED"
    for k in GRANT_KEYS:
        assert d[k] is False


def test_valid_record_is_input_not_grant():
    v = m.validate_operator_approval_record(_valid_record())
    assert v["valid"] is True
    assert v["grants_canary"] is False


# ── prerequisites deny-by-default + immutable ────────────────────────────────
def test_prerequisites_deny_by_default():
    p = m.evaluate_prerequisites()
    assert p["all_met"] is False
    assert p["held"] == 0 and p["total"] == 13
    assert p["immutable"] is True
    assert len(p["unmet"]) == 13


def test_prerequisite_ids_stable():
    ids = [p["id"] for p in m.CANARY_PREREQUISITES]
    assert ids == [f"PRQ-{i}" for i in range(1, 14)]


# ── approval record validation ───────────────────────────────────────────────
def test_absent_record_invalid():
    v = m.validate_operator_approval_record(None)
    assert v["valid"] is False and v["present"] is False
    assert "no_operator_approval_record" in v["problems"]


def test_record_missing_acks_invalid():
    rec = _valid_record()
    rec["explicit_acknowledgements"] = ["I_AUTHORIZE_BOUNDED_CANARY"]
    v = m.validate_operator_approval_record(rec)
    assert v["valid"] is False
    assert any(p.startswith("missing_acknowledgement:") for p in v["problems"])


def test_record_rollout_out_of_bounds():
    rec = _valid_record()
    rec["rollout_percent"] = 50
    v = m.validate_operator_approval_record(rec)
    assert v["valid"] is False and "rollout_percent_out_of_bounds" in v["problems"]


def test_record_endpoint_not_allowlisted():
    rec = _valid_record()
    rec["endpoints"] = ["repos"]
    v = m.validate_operator_approval_record(rec)
    assert v["valid"] is False and "endpoint_not_allowlisted" in v["problems"]


def test_record_method_not_allowlisted():
    rec = _valid_record()
    rec["methods"] = ["POST"]
    v = m.validate_operator_approval_record(rec)
    assert v["valid"] is False and "method_not_allowlisted" in v["problems"]


# ── framework definitions ────────────────────────────────────────────────────
def test_framework_has_triggers_breakers_exit():
    f = m.framework_definitions()
    assert len(f["rollback_triggers"]) == 7
    assert len(f["circuit_breakers"]) == 3
    assert "graduate_requires_all" in f["exit_criteria"]
    assert "abort_if_any" in f["exit_criteria"]
    assert f["rollout_bounds"] == {"min_percent": 1, "max_percent": 5}


def test_rollout_ceiling_bounded():
    assert m.ROLLOUT_MAX_PERCENT <= 5


# ── determinism + leak ───────────────────────────────────────────────────────
def test_decision_deterministic_and_clean():
    a = m.evaluate_canary_decision()
    b = m.evaluate_canary_decision()
    assert a["fingerprint"] == b["fingerprint"]
    assert is_clean(a)


def test_evidence_deterministic_and_clean():
    a = m.build_m39_3_evidence()
    b = m.build_m39_3_evidence()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["summary"]["grants_canary"] is False
    assert a["summary"]["verdict"] == "CANARY_FRAMEWORK_COMPLETE_CANARY_NOT_GRANTED"
    for name, body in a.items():
        assert is_clean(body), name


def test_authorities_not_granted():
    d = m.evaluate_canary_decision()
    for k, v in d["authorities"].items():
        assert v == "NOT GRANTED"
    assert d["trading_guardian"] == "UNENGAGED"


def test_evidence_emit(tmp_path):
    res = m.emit_m39_3_evidence(tmp_path)
    assert res["count"] == 6
    for p in res["written"]:
        assert is_clean(json.loads(open(p).read()))
