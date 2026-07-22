"""M39.5 — Monitoring & incident response tests (offline; synthetic signals)."""
from __future__ import annotations

import json

from saathi.credentials import m39_5 as m
from saathi.credentials.leakscan import is_clean


def _good_event():
    return {
        "event_type": "m39.single_session_blocked", "session_id": "s",
        "privacy_safe": True, "contains_secret_values": False, "reason": "x",
    }


def test_good_event_valid():
    assert m.validate_audit_event(_good_event())["valid"] is True


def test_empty_event_invalid():
    v = m.validate_audit_event(None)
    assert v["valid"] is False and "empty_event" in v["problems"]


def test_unknown_event_type_invalid():
    e = _good_event(); e["event_type"] = "m39.mystery"
    assert m.validate_audit_event(e)["valid"] is False


def test_missing_required_field_invalid():
    e = _good_event(); del e["reason"]
    v = m.validate_audit_event(e)
    assert v["valid"] is False and any(p.startswith("missing_field:") for p in v["problems"])


def test_forbidden_field_rejected():
    e = _good_event(); e["token"] = "zzz"
    v = m.validate_audit_event(e)
    assert v["valid"] is False
    assert "forbidden_field:token" in v["problems"]


def test_not_privacy_safe_rejected():
    e = _good_event(); e["privacy_safe"] = False
    assert m.validate_audit_event(e)["valid"] is False


def test_claims_secret_values_rejected():
    e = _good_event(); e["contains_secret_values"] = True
    v = m.validate_audit_event(e)
    assert v["valid"] is False and "claims_secret_values" in v["problems"]


# ── alerts ───────────────────────────────────────────────────────────────────
def test_quiet_signals_no_alerts():
    assert m.detect_alerts({})["fired_count"] == 0


def test_secret_resolution_failure_is_sev1():
    a = m.detect_alerts({"secret_resolution_failures": 1})
    assert any(f["id"] == "ALT-4" for f in a["fired"])
    assert a["highest_severity"] == "SEV1"


def test_budget_exhaustion_alert():
    a = m.detect_alerts({"aggregate_calls_used": 12})
    assert any(f["id"] == "ALT-2" for f in a["fired"])


def test_canary_escalation_attempt_sev1():
    a = m.detect_alerts({"canary_grant_attempts": 1})
    assert any(f["id"] == "ALT-9" for f in a["fired"])
    assert a["highest_severity"] == "SEV1"


def test_kill_switch_alert_boolean():
    a = m.detect_alerts({"kill_switch_active": True})
    assert any(f["id"] == "ALT-7" for f in a["fired"])


def test_alert_definitions_count():
    assert len(m.alert_definitions()["alerts"]) == 9


# ── runbooks + metrics ───────────────────────────────────────────────────────
def test_runbooks_present():
    assert len(m.incident_runbook()["steps"]) == 6
    assert len(m.recovery_runbook()["steps"]) == 6
    assert len(m.incident_severity_definitions()["levels"]) == 3


def test_metrics_contract_redacted():
    mc = m.metrics_contract()
    assert len(mc["metrics"]) == 8
    assert mc["contains_secret_values"] is False


# ── evidence ─────────────────────────────────────────────────────────────────
def test_evidence_deterministic_and_clean():
    a = m.build_m39_5_evidence()
    b = m.build_m39_5_evidence()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["summary"]["verdict"] == "MONITORING_INCIDENT_SURFACE_COMPLETE_OFFLINE"
    for k, v in a["summary"]["authorities"].items():
        assert v == "NOT GRANTED"
    for name, body in a.items():
        assert is_clean(body), name


def test_evidence_emit(tmp_path):
    res = m.emit_m39_5_evidence(tmp_path)
    assert res["count"] == 11
    for p in res["written"]:
        assert is_clean(json.loads(open(p).read()))
