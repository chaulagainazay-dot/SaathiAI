"""M42 — Canary evidence review & graduation decision tests (offline, deterministic).

M42 grants nothing. Fail-closed. Operator attestation is never accepted where
machine proof is required.
"""
from __future__ import annotations

import json

import pytest

from saathi.credentials import m42
from saathi.credentials.leakscan import is_clean

FORBIDDEN = ("ACTIVE", "PRODUCTION", "WRITE", "FULL_ROLLOUT", "SCOPE_EXPANSION", "TRADING_GUARDIAN")


# ── fixtures ─────────────────────────────────────────────────────────────────
def _cert(**over):
    b = {
        "schema": "m40.live_certification_record.v1", "milestone": "M40",
        "decision": "LIVE_CERTIFIED", "live_certified": True, "live_exercised": True,
        "provider": "github_meta", "read_only": True, "writes": [],
        "operations": ["GET /user", "GET /meta"],
        "account_subject_fingerprint": "c7cd7f4d6bee55c2847614692022af73",
        "revocation_phase": {"http_401_confirmed": True, "verdict": "LIVE_CERTIFIED"},
        "grants_active": False, "grants_production": False, "grants_canary": False,
        "authority_state": {"ACTIVE": "NOT GRANTED", "PRODUCTION_DEPLOYMENT": "NOT AUTHORIZED",
                            "WRITE": "NOT GRANTED"},
        "trading_guardian": "UNCHANGED / UNENGAGED", "fingerprint": "cert00",
        "contains_secret_values": False,
    }
    b.update(over)
    return b


def _canary_machine(**over):
    """A MACHINE-proven canary body (positive path)."""
    b = {
        "schema": "m41.canary_machine_completion.v1", "milestone": "M41",
        "verdict_reported_by_operator": "CANARY_ACTIVE_BOUNDED",
        "machine_verified_live": True, "live_exercised": True,
        "provider": "github_meta", "mode": "read_only_canary",
        "machine_reevaluation": {"m39_5_alerts_fired": 0, "m41_should_rollback": False},
        "operator_reported_signals": {"identity": "unchanged", "scope": "unchanged",
                                      "kill_switch": "tested", "automatic_rollback": "armed"},
        "credential_lifecycle": {"status": "CLOSED", "machine_verified_here": True},
        "grants_active": False, "grants_production": False, "grants_write": False,
        "authority_state": {"active": "NOT GRANTED", "production": "NOT AUTHORIZED",
                            "write": "NOT GRANTED"},
        "m32_canary_execution_mode": "PROHIBITION_UNCHANGED",
        "trading_guardian": "UNCHANGED / UNENGAGED", "fingerprint": "canary00",
        "contains_secret_values": False,
    }
    b.update(over)
    return b


def _canary_attested(**over):
    b = _canary_machine()
    b.update({"source": "OPERATOR_ATTESTED", "machine_verified_live": False,
              "session_executed_live": False})
    b.pop("live_exercised", None)
    b.update(over)
    return b


def _loaded(cert=None, canary=None, drop=None, invalid=None):
    """Build a loaded-evidence dict. drop=keys to make MISSING; invalid=keys to malform."""
    drop = drop or []
    invalid = invalid or {}
    bodies = {
        "m40_live_cert": cert if cert is not None else _cert(),
        "m40_validation": {"schema": "m40", "verdict": "LIVE_STAGES_PASSED_PENDING_REVOCATION",
                           "live_exercised": True, "fingerprint": "val0", "contains_secret_values": False},
        "m40_revocation": {"schema": "m40", "verdict": "LIVE_CERTIFIED", "live_exercised": True,
                           "fingerprint": "rev0", "contains_secret_values": False},
        "m41_bounded_canary": canary if canary is not None else _canary_machine(),
        "m41_rehearsal": {"schema": "m41", "verdict": "CANARY_ACTIVE_BOUNDED", "mode": "rehearsal",
                          "fingerprint": "reh0", "contains_secret_values": False},
        "m41_rollback_proof": {"schema": "m41", "verdict": "CANARY_ROLLED_BACK", "mode": "rehearsal",
                               "fingerprint": "rb0", "contains_secret_values": False},
        "m41_summary": {"schema": "m41.summary.v1", "fingerprint": "sum0", "contains_secret_values": False},
    }
    loaded = {}
    for spec in m42.REQUIRED_ARTIFACTS:
        k = spec["key"]
        if k in drop:
            loaded[k] = {"path": f"x/{k}.json", "body": None, "read_error": "missing", "spec": k}
        elif k in invalid:
            loaded[k] = {"path": f"x/{k}.json", "body": None, "read_error": "unreadable:JSONDecodeError", "spec": k}
        else:
            loaded[k] = {"path": f"x/{k}.json", "body": bodies[k], "read_error": None, "spec": k}
    return loaded


# ── positive path (machine-proven) ───────────────────────────────────────────
def test_positive_machine_proven_recommended():
    r = m42.run_graduation_review(loaded=_loaded())
    assert r["recommendation"] == "GRADUATION_RECOMMENDED"
    assert r["criteria_failed"] == 0 and r["criteria_blocked"] == 0
    assert r["abort_conditions_present"] == []
    assert r["grants_anything"] is False


def test_positive_grants_nothing():
    r = m42.run_graduation_review(loaded=_loaded())
    assert r["explicitly_not_granted"] == list(FORBIDDEN)
    assert r["alters_runtime_authority"] is False


# ── provenance: operator attestation where machine proof required ────────────
def test_operator_attested_canary_not_recommended():
    r = m42.run_graduation_review(loaded=_loaded(canary=_canary_attested()))
    assert r["recommendation"] == "GRADUATION_NOT_RECOMMENDED"
    assert "AB-PROV" in r["abort_conditions_present"]


def test_real_repo_evidence_recommended_post_machine_proof():
    # Post M43.1 Phase 6: a genuine machine-verified canary record is committed at
    # docs/evidence/m43/machine_verified_canary_completion.json. It supersedes the
    # operator-attested default (machine_override), so provenance is MACHINE_PROOF,
    # AB-PROV is lifted, and the review is RECOMMENDED. Advisory only — grants nothing.
    from pathlib import Path
    assert Path("docs/evidence/m43/machine_verified_canary_completion.json").exists()
    r = m42.run_graduation_review()
    assert r["recommendation"] == "GRADUATION_RECOMMENDED"
    assert r["abort_conditions_present"] == []
    assert "AB-PROV" not in r["abort_conditions_present"]
    # recommendation grants no operational authority
    assert r["grants_anything"] is False
    assert r["alters_runtime_authority"] is False
    assert r["explicitly_not_granted"] == list(FORBIDDEN)


def test_real_repo_without_machine_record_not_recommended(tmp_path):
    # Negative guard preserved from the pre-proof state: with the machine record ABSENT,
    # the operator-attested default must NOT graduate (AB-PROV present). Built
    # deterministically from real m40/m41 evidence, omitting docs/evidence/m43.
    import shutil
    for d in ("m40", "m41"):
        shutil.copytree(f"docs/evidence/{d}", tmp_path / d)
    # deliberately do NOT copy docs/evidence/m43 (no machine record on disk)
    r = m42.run_graduation_review(base=str(tmp_path))
    assert r["recommendation"] == "GRADUATION_NOT_RECOMMENDED"
    assert "AB-PROV" in r["abort_conditions_present"]
    assert r["grants_anything"] is False


# ── missing evidence -> BLOCKED ──────────────────────────────────────────────
@pytest.mark.parametrize("missing", ["m40_live_cert", "m40_revocation", "m41_bounded_canary"])
def test_missing_mandatory_blocks(missing):
    r = m42.run_graduation_review(loaded=_loaded(drop=[missing]))
    assert r["recommendation"] == "GRADUATION_BLOCKED"


def test_missing_lifecycle_closure_not_recommended():
    c = _canary_machine(); c["credential_lifecycle"] = {"status": "OPEN"}
    r = m42.run_graduation_review(loaded=_loaded(canary=c))
    assert r["recommendation"] == "GRADUATION_NOT_RECOMMENDED"


# ── invalid / malformed evidence -> BLOCKED ──────────────────────────────────
def test_malformed_mandatory_blocks():
    r = m42.run_graduation_review(loaded=_loaded(invalid={"m40_live_cert": True}))
    assert r["recommendation"] == "GRADUATION_BLOCKED"


def test_wrong_provider_not_recommended():
    r = m42.run_graduation_review(loaded=_loaded(cert=_cert(provider="stripe")))
    assert r["recommendation"] in ("GRADUATION_NOT_RECOMMENDED", "GRADUATION_BLOCKED")
    assert r["recommendation"] != "GRADUATION_RECOMMENDED"


# ── security / authority -> never recommend ──────────────────────────────────
@pytest.mark.parametrize("field", ["grants_active", "grants_production", "grants_write"])
def test_prohibited_grant_prevents_recommendation(field):
    r = m42.run_graduation_review(loaded=_loaded(canary=_canary_machine(**{field: True})))
    assert r["recommendation"] != "GRADUATION_RECOMMENDED"
    assert "AB-5" in r["abort_conditions_present"]


def test_trading_guardian_engaged_prevents_recommendation():
    r = m42.run_graduation_review(loaded=_loaded(cert=_cert(trading_guardian="ENGAGED")))
    assert r["recommendation"] != "GRADUATION_RECOMMENDED"
    assert "AB-11" in r["abort_conditions_present"]


def test_active_authority_in_state_rejected():
    c = _cert(authority_state={"ACTIVE": "GRANTED"})
    r = m42.run_graduation_review(loaded=_loaded(cert=c))
    assert r["recommendation"] != "GRADUATION_RECOMMENDED"


# ── canary integrity ─────────────────────────────────────────────────────────
def test_unresolved_alert_prevents_recommendation():
    c = _canary_machine()
    c["machine_reevaluation"] = {"m39_5_alerts_fired": 2, "m41_should_rollback": False}
    r = m42.run_graduation_review(loaded=_loaded(canary=c))
    assert r["recommendation"] != "GRADUATION_RECOMMENDED"


def test_rollback_condition_prevents_recommendation():
    c = _canary_machine()
    c["machine_reevaluation"] = {"m39_5_alerts_fired": 0, "m41_should_rollback": True}
    r = m42.run_graduation_review(loaded=_loaded(canary=c))
    assert r["recommendation"] != "GRADUATION_RECOMMENDED"


def test_identity_drift_prevents_recommendation():
    c = _canary_machine()
    c["operator_reported_signals"]["identity"] = "changed"
    r = m42.run_graduation_review(loaded=_loaded(canary=c))
    assert r["recommendation"] != "GRADUATION_RECOMMENDED"


def test_missing_revocation_proof_prevents_recommendation():
    r = m42.run_graduation_review(loaded=_loaded(cert=_cert(revocation_phase={"http_401_confirmed": False})))
    assert r["recommendation"] != "GRADUATION_RECOMMENDED"


# ── provenance: simulation substituted for live ──────────────────────────────
def test_simulated_m40_not_live_rejected():
    r = m42.run_graduation_review(loaded=_loaded(cert=_cert(live_exercised=False, verdict="SIMULATED_NOT_LIVE")))
    assert r["recommendation"] != "GRADUATION_RECOMMENDED"


# ── never converts BLOCKED to RECOMMENDED ────────────────────────────────────
def test_blocked_never_becomes_recommended():
    r = m42.run_graduation_review(loaded=_loaded(drop=["m40_live_cert"]))
    assert r["recommendation"] == "GRADUATION_BLOCKED"
    assert r["grants_anything"] is False


# ── determinism + leak ───────────────────────────────────────────────────────
def test_deterministic_recommendation():
    a = m42.run_graduation_review(loaded=_loaded())
    b = m42.run_graduation_review(loaded=_loaded())
    assert a["fingerprint"] == b["fingerprint"]
    assert a["evidence_digest"] == b["evidence_digest"]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_evidence_deterministic_and_clean():
    a = m42.build_m42_evidence()
    b = m42.build_m42_evidence()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    for name, body in a.items():
        assert is_clean(body), name
    assert a["summary"]["grants_anything"] is False


def test_m32_prohibition_preserved():
    assert m42._m32_prohibition_intact() is True


def test_evidence_emit(tmp_path):
    res = m42.emit_m42_evidence(tmp_path)
    assert res["count"] == 5
    for p in res["written"]:
        assert is_clean(json.loads(open(p).read()))
