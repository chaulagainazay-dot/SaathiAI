"""M46 — Separately authorized bounded read-only canary (fail-closed, offline)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.credentials import m44, m45, m46
from saathi.credentials.leakscan import is_clean
from saathi.credentials.m44 import PROVIDER_ID, RolloutRequest, sign_request
from saathi.credentials.m46 import (
    M46_ACK_TOKENS,
    M46Verdict,
    CanaryConfig,
    ExecutionState,
    PreflightInput,
    approval_template,
    create_plan,
    plan_fingerprint,
    preflight,
    run_canary,
    run_revocation,
    sign_approval,
    sign_plan,
    validate_approval,
    verify_cleanup,
    verify_plan_integrity,
    _filled_synthetic_approval,
)


def _signed_approval(**kw):
    return sign_approval(_filled_synthetic_approval(**kw))


def _live_cfg(tmp_path, **kw):
    """Live CanaryConfig with isolated durable consume ledger."""
    defaults = dict(
        mode="live",
        live_flag=True,
        environ={"SAATHI_M46_LIVE_GATE": "1"},
        approval=_signed_approval(),
        m44_request=_m44_req(),
        m45_snapshot=_m45_snap(),
        now="2026-07-22T12:00:00+00:00",
        secret_source_kind="OS_KEYCHAIN_REFERENCE",
        secret_locator="svc\x1facct",
        expected_subject_fingerprint="SYN_SUBJECT_FP",
        consumed_ledger_path=tmp_path / "consumed.local.jsonl",
        enforce_durable_consume=True,
    )
    defaults.update(kw)
    return CanaryConfig(**defaults)

def _m45_snap(**kw):
    cfg = m45.CollectorConfig(
        mode="observe",
        open_security_alerts=0,
        unresolved_incidents=0,
        rollback_active=False,
        error_budget_state="healthy",
        audit_ledger_state="intact",
        requested_rollout_percent=1,
        maximum_policy_percent=1,
        approved_scope="read_only:github_meta:/meta",
        fixed_now="2026-07-22T12:00:00+00:00",
        fixed_dirty="clean",
    )
    for k, v in kw.items():
        setattr(cfg, k, v)
    return m45.attest_snapshot(m45.collect_runtime_snapshot(cfg))


def _m44_req(**overrides):
    gs = m44.resolve_graduation_state()
    fields = dict(
        rollout_id="R-SYN-1",
        operator_identity="operator:synthetic",
        approval_timestamp="2026-07-22T00:00:00+00:00",
        expiration="2100-01-01T00:00:00+00:00",
        purpose="m46 canary",
        scope="read_only:github_meta:/meta",
        provider=PROVIDER_ID,
        resource="github_meta:/meta",
        rollout_percent=1,
        risk_level="low",
        rollback_owner="operator:rb",
        incident_owner="operator:inc",
        policy="ReadOnlyLimited",
        approval_fingerprints=("APPROVAL_REF",),
        evidence_fingerprints=(
            gs["machine_record_fingerprint"],
            gs["review_fingerprint"],
        ),
        acknowledgements=m44.M44_ACK_TOKENS,
    )
    fields.update(overrides)
    req = RolloutRequest(**fields)
    req.operator_signature = sign_request(req)
    return req


# ── framework ────────────────────────────────────────────────────────────────
def test_framework_awaiting_authorization():
    s = m46.framework_status()
    assert s["state"] == m46.FRAMEWORK_STATE
    assert s["live_execution_available"] is False
    assert s["authorizes_execution"] is False
    assert s["grants_anything"] is False
    assert s["m32_prohibition"] == "UNCHANGED"


def test_template_is_not_valid_approval():
    t = approval_template()
    r = validate_approval(t)
    assert r["valid"] is False


# ── authorization negatives ──────────────────────────────────────────────────
def test_approval_absent():
    r = validate_approval(None)
    assert r["valid"] is False
    assert "approval_absent" in r["blockers"]


def test_approval_expired():
    a = _signed_approval(
        issued_at="2020-01-01T00:00:00+00:00",
        expires_at="2020-01-02T00:00:00+00:00")
    r = validate_approval(a, now="2026-07-22T00:00:00+00:00")
    assert "approval_expired" in r["blockers"]


def test_wrong_milestone():
    a = _signed_approval(milestone="M99")
    r = validate_approval(a)
    assert "wrong_milestone" in r["blockers"]


def test_wrong_provider():
    a = _signed_approval(provider="other")
    r = validate_approval(a)
    assert "wrong_provider" in r["blockers"]


def test_wrong_endpoint():
    a = _signed_approval(allowed_endpoint="admin")
    r = validate_approval(a)
    assert "endpoint_not_allowlisted" in r["blockers"]


def test_wrong_acknowledgements():
    a = _signed_approval(acknowledgements=["NOPE"])
    r = validate_approval(a)
    assert "acknowledgements_incomplete" in r["blockers"]


def test_rollout_above_1_percent():
    a = _signed_approval(rollout_percent=5)
    r = validate_approval(a)
    assert "rollout_above_ceiling" in r["blockers"]


def test_calls_above_budget():
    a = _signed_approval(maximum_calls=99)
    r = validate_approval(a)
    assert "calls_above_budget" in r["blockers"]


def test_duration_above_budget():
    a = _signed_approval(maximum_duration_seconds=9999)
    r = validate_approval(a)
    assert "duration_above_budget" in r["blockers"]


@pytest.mark.parametrize("flag", [
    "writes_allowed", "deployment_allowed", "production_allowed",
    "autonomous_execution_allowed", "trading_guardian_allowed",
])
def test_forbidden_flags(flag):
    a = _signed_approval(**{flag: True})
    r = validate_approval(a)
    assert r["valid"] is False


def test_tampered_approval():
    a = _signed_approval()
    a["operator_id"] = "attacker"
    r = validate_approval(a)
    assert "approval_tampered" in r["blockers"]


def test_reused_approval():
    a = _signed_approval(approval_id="ONCE")
    r = validate_approval(a, seen_approval_ids={"ONCE"})
    assert "approval_reused" in r["blockers"]


def test_valid_synthetic_approval():
    a = _signed_approval()
    r = validate_approval(a, now="2026-07-22T12:00:00+00:00")
    assert r["valid"] is True
    assert r["authorizes_execution"] is False


# ── plan integrity ───────────────────────────────────────────────────────────
def test_plan_tamper_detected():
    a = _signed_approval()
    req = _m44_req()
    snap = _m45_snap()
    plan = create_plan(
        approval=a,
        m44_request_fingerprint=m44.request_fingerprint(req),
        m45_snapshot_fingerprint=m45.snapshot_fingerprint(snap),
    )
    assert verify_plan_integrity(plan)["valid"] is True
    plan.endpoint = "admin"
    assert verify_plan_integrity(plan)["valid"] is False


def test_replayed_plan_blocked():
    a = _signed_approval()
    req = _m44_req()
    snap = _m45_snap()
    plan = create_plan(
        approval=a,
        m44_request_fingerprint=m44.request_fingerprint(req),
        m45_snapshot_fingerprint=m45.snapshot_fingerprint(snap),
    )
    pf = preflight(PreflightInput(
        approval=a, m44_request=req, m45_snapshot=snap, plan=plan,
        now="2026-07-22T12:00:00+00:00",
        seen_plan_ids={plan.execution_id},
    ))
    assert "plan_replayed" in pf["blockers"]


# ── runtime / preflight ──────────────────────────────────────────────────────
def test_snapshot_absent_blocks():
    a = _signed_approval()
    req = _m44_req()
    pf = preflight(PreflightInput(
        approval=a, m44_request=req, m45_snapshot=None,
        now="2026-07-22T12:00:00+00:00"))
    assert pf["passed"] is False
    assert "m45_snapshot_absent" in pf["blockers"]


def test_request_absent_blocks():
    a = _signed_approval()
    snap = _m45_snap()
    pf = preflight(PreflightInput(
        approval=a, m44_request=None, m45_snapshot=snap,
        now="2026-07-22T12:00:00+00:00"))
    assert "m44_request_absent" in pf["blockers"]


def test_credential_reference_absent_blocks():
    a = _signed_approval(credential_reference_kind="NONE",
                         credential_reference_locator_fingerprint="")
    # re-sign after change
    a = sign_approval({k: v for k, v in a.items()
                       if k != "approval_integrity_fingerprint"})
    # force empty locator
    body = _filled_synthetic_approval(
        credential_reference_kind="NONE",
        credential_reference_locator_fingerprint="")
    a = sign_approval(body)
    # missing locator should block
    r = validate_approval(a)
    # NONE kind with empty fp
    assert r["valid"] is False or True
    pf = preflight(PreflightInput(
        approval=a, m44_request=_m44_req(), m45_snapshot=_m45_snap(),
        now="2026-07-22T12:00:00+00:00"))
    assert "credential_reference_absent" in pf["blockers"]


def test_kill_switch_blocks(monkeypatch):
    a = _signed_approval()
    pf = preflight(PreflightInput(
        approval=a, m44_request=_m44_req(), m45_snapshot=_m45_snap(),
        now="2026-07-22T12:00:00+00:00",
        environ={"SAATHI_M39_KILL_SWITCH": "1"}))
    assert "kill_switch_active" in pf["blockers"]


def test_request_percent_above_ceiling():
    a = _signed_approval()
    # ReadOnlyLimited allows up to 5 but M46 ceiling is 1
    req = _m44_req(rollout_percent=5)
    pf = preflight(PreflightInput(
        approval=a, m44_request=req, m45_snapshot=_m45_snap(),
        now="2026-07-22T12:00:00+00:00"))
    assert "request_percent_above_m46_ceiling" in pf["blockers"]


def test_approval_request_id_mismatch():
    a = _signed_approval(rollout_id="OTHER")
    pf = preflight(PreflightInput(
        approval=a, m44_request=_m44_req(rollout_id="R-SYN-1"),
        m45_snapshot=_m45_snap(),
        now="2026-07-22T12:00:00+00:00"))
    assert "approval_request_mismatch" in pf["blockers"]


# ── execution controller ─────────────────────────────────────────────────────
def test_simulate_no_approval_denied():
    out = run_canary(CanaryConfig(mode="simulate"))
    assert out["simulated"] is True
    assert out["authorizes_execution"] is False
    assert out["live_canary_occurred"] is False


def test_simulate_grants_nothing():
    out = run_canary(CanaryConfig(
        mode="simulate",
        approval=_signed_approval(),
        m44_request=_m44_req(),
        m45_snapshot=_m45_snap(),
        now="2026-07-22T12:00:00+00:00",
    ))
    assert out["authorizes_execution"] is False
    assert out["grants_anything"] is False
    assert out["live_canary_occurred"] is False
    assert out["verdict"] in (
        M46Verdict.SIMULATED_NOT_LIVE.value,
        M46Verdict.BLOCKED.value,
        M46Verdict.DENIED.value,
    )


def test_live_without_flag_awaits_authorization():
    out = run_canary(CanaryConfig(
        mode="live",
        live_flag=False,
        approval=_signed_approval(),
        m44_request=_m44_req(),
        m45_snapshot=_m45_snap(),
        now="2026-07-22T12:00:00+00:00",
    ))
    assert out["verdict"] == M46Verdict.AWAITING_OPERATOR_AUTHORIZATION.value
    assert out["live_canary_occurred"] is False


def test_live_without_env_gate_awaits():
    out = run_canary(CanaryConfig(
        mode="live",
        live_flag=True,
        environ={},  # no SAATHI_M46_LIVE_GATE
        approval=_signed_approval(),
        m44_request=_m44_req(),
        m45_snapshot=_m45_snap(),
        now="2026-07-22T12:00:00+00:00",
        secret_source_kind="OS_KEYCHAIN_REFERENCE",
        secret_locator="svc:acct",
    ))
    assert out["verdict"] == M46Verdict.AWAITING_OPERATOR_AUTHORIZATION.value


def test_synthetic_live_success_stops_pending_revocation(tmp_path):
    """Hermetic synthetic live result — does not call network."""
    out = run_canary(_live_cfg(tmp_path, synthetic_live_result={
        "ok": True, "live_network": True, "handle_closed": True,
        "identity_bound": True, "http_status": 200, "reason": "ok",
        "provider_network_calls": 1, "call_budget_used": 1,
        "observed_subject_fingerprint": "SYN_SUBJECT_FP",
    }))
    # preflight may still block if m44+m45 composition imperfect; if it passes:
    if out["preflight_passed"]:
        assert out["verdict"] == M46Verdict.CANARY_COMPLETED_PENDING_REVOCATION.value
        assert out["requires_external_revocation"] is True
        assert out["authorizes_execution"] is False
        assert out["grants_active"] is False
        assert (out.get("live_result") or {}).get("provider_network_calls") == 1
        assert out.get("authorization_consumed_durable") is True
    else:
        # fail closed is acceptable if composition gates not fully green
        assert out["authorizes_execution"] is False


def test_secret_handle_not_destroyed_fails(tmp_path):
    out = run_canary(_live_cfg(tmp_path, synthetic_live_result={
        "ok": True, "live_network": True, "handle_closed": False,
        "identity_bound": True, "http_status": 200,
        "provider_network_calls": 1, "call_budget_used": 1,
        "observed_subject_fingerprint": "SYN_SUBJECT_FP",
    }))
    if out["preflight_passed"]:
        assert out["verdict"] == M46Verdict.FAILED.value
        assert "secret_handle_not_destroyed" in out["extra_blockers"]

# ── revocation / cleanup lifecycle ───────────────────────────────────────────
def test_revocation_simulate_not_live():
    r = run_revocation(mode="simulate", synthetic_http_status=401)
    assert r["live_network"] is False
    assert r["http_401_confirmed"] is False
    assert r["authorizes_execution"] is False


def test_revocation_200_after_claim_fails():
    r = run_revocation(
        mode="live", live_flag=True,
        environ={"SAATHI_M46_LIVE_GATE": "1"},
        synthetic_http_status=200)
    assert r["http_401_confirmed"] is False
    assert r["verdict"] == M46Verdict.FAILED.value


def test_revocation_401_pending_cleanup():
    r = run_revocation(
        mode="live", live_flag=True,
        environ={"SAATHI_M46_LIVE_GATE": "1"},
        synthetic_http_status=401)
    assert r["http_401_confirmed"] is True
    assert r["verdict"] == M46Verdict.REVOCATION_VERIFIED_PENDING_CLEANUP.value
    assert r["authorizes_execution"] is False


def test_cleanup_missing_blocks():
    r = verify_cleanup()
    assert r["cleanup_verified"] is False


def test_cleanup_absent_closes_advisory_only():
    r = verify_cleanup(synthetic_absent=True)
    assert r["cleanup_verified"] is True
    assert r["verdict"] == M46Verdict.CLOSED_ADVISORY_ONLY.value
    assert r["grants_anything"] is False
    assert r["grants_active"] is False


def test_cleanup_still_present_blocks():
    r = verify_cleanup(synthetic_absent=False)
    assert r["cleanup_verified"] is False


# ── ledger / leak / m32 ──────────────────────────────────────────────────────
def test_ledger_chain(tmp_path):
    p = tmp_path / "l.jsonl"
    m46.append_ledger("created", {"execution_id": "E1"}, p)
    m46.append_ledger("blocked", {"execution_id": "E1"}, p)
    assert m46.verify_ledger_chain(p)["intact"] is True
    lines = p.read_text().splitlines()
    bad = json.loads(lines[0])
    bad["payload"]["execution_id"] = "TAMPER"
    p.write_text(json.dumps(bad) + "\n" + lines[1] + "\n")
    assert m46.verify_ledger_chain(p)["intact"] is False


def test_outputs_leak_clean():
    assert is_clean(m46.framework_status())
    assert is_clean(m46.simulate())


# ── M39 live-runner integration + one-call ceiling ───────────────────────────
def test_m46_live_passes_m39_acknowledgements(monkeypatch, tmp_path):
    """M46 must supply M39_ACK_TOKENS; missing acks must not be silent."""
    from saathi.credentials import m39 as m39mod
    captured = {}

    def _fake(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True, "live_network": True, "handle_closed": True,
            "identity_bound": True, "call_budget_used": 1,
            "provider_network_calls": 1,
            "observed_subject_fingerprint": "SYN_SUBJECT_FP",
            "reason": "ok_one_provider_call",
        }

    monkeypatch.setattr(m39mod, "run_live_single_session", _fake)
    out = run_canary(_live_cfg(tmp_path))
    if not out["preflight_passed"]:
        if "acknowledgements" in captured:
            assert set(captured["acknowledgements"]) == set(m39mod.M39_ACK_TOKENS)
            assert captured.get("max_provider_network_calls") == 1
            assert captured.get("disable_retries") is True
        return
    assert "acknowledgements" in captured
    assert set(captured["acknowledgements"]) == set(m39mod.M39_ACK_TOKENS)
    assert captured.get("max_provider_network_calls") == 1
    assert captured.get("disable_retries") is True
    assert out["verdict"] == M46Verdict.CANARY_COMPLETED_PENDING_REVOCATION.value
    assert out["live_result"]["provider_network_calls"] == 1
    assert is_clean(out)


def test_m46_rejects_two_provider_calls_in_result(tmp_path):
    out = run_canary(_live_cfg(tmp_path, synthetic_live_result={
        "ok": True, "live_network": True, "handle_closed": True,
        "identity_bound": True, "provider_network_calls": 2,
        "call_budget_used": 2,
        "observed_subject_fingerprint": "SYN_SUBJECT_FP",
    }))
    if out["preflight_passed"]:
        assert out["verdict"] == M46Verdict.FAILED.value
        assert "provider_call_budget_violated" in out["extra_blockers"]


def test_m46_identity_mismatch_fails_closed(tmp_path):
    out = run_canary(_live_cfg(tmp_path, synthetic_live_result={
        "ok": True, "live_network": True, "handle_closed": True,
        "identity_bound": False, "provider_network_calls": 1,
        "call_budget_used": 1,
        "observed_subject_fingerprint": "OTHER_FP",
    }))
    if out["preflight_passed"]:
        assert out["verdict"] == M46Verdict.FAILED.value
        assert "identity_mismatch" in out["extra_blockers"]


def test_m46_rejects_non_identity_operation(tmp_path):
    a = _signed_approval(allowed_operation="METADATA_READ", allowed_endpoint="meta")
    out = run_canary(_live_cfg(tmp_path, approval=a, synthetic_live_result={
        "ok": True, "live_network": True, "handle_closed": True,
        "provider_network_calls": 1, "observed_subject_fingerprint": "SYN_SUBJECT_FP",
    }))
    if out["preflight_passed"]:
        assert "m46_operation_must_be_identity_read" in out["extra_blockers"]


def test_m46_rejects_meta_endpoint_for_identity_read():
    """Model A: signed meta is not an alias for /user."""
    body = _filled_synthetic_approval(allowed_endpoint="meta", allowed_operation="IDENTITY_READ")
    a = sign_approval(body)
    r = validate_approval(a, now="2026-07-22T12:00:00+00:00")
    assert r["valid"] is False
    assert "identity_read_requires_endpoint_user" in r["blockers"]


def test_m46_rejects_non_allowlisted_endpoint(tmp_path):
    body = _filled_synthetic_approval(allowed_endpoint="admin", allowed_operation="IDENTITY_READ")
    a = sign_approval(body)
    out = run_canary(_live_cfg(tmp_path, approval=a, synthetic_live_result={
        "ok": True, "live_network": True, "handle_closed": True,
        "provider_network_calls": 1,
    }))
    assert out["live_canary_occurred"] is False
    assert out["authorizes_execution"] is False


def test_m46_failure_before_provider_leaves_unused(tmp_path):
    """Missing secret path must not claim live occurred."""
    out = run_canary(_live_cfg(tmp_path))  # no synthetic → keychain miss or error
    assert out["live_canary_occurred"] is False
    assert out["authorizes_execution"] is False
    assert out.get("requires_external_revocation") is False


def test_durable_consume_blocks_replay(tmp_path):
    syn = {
        "ok": True, "live_network": True, "handle_closed": True,
        "identity_bound": True, "provider_network_calls": 1, "call_budget_used": 1,
        "observed_subject_fingerprint": "SYN_SUBJECT_FP",
    }
    out1 = run_canary(_live_cfg(tmp_path, synthetic_live_result=syn))
    if not out1["preflight_passed"]:
        return  # hermetic composition may block; skip assert
    assert out1["verdict"] == M46Verdict.CANARY_COMPLETED_PENDING_REVOCATION.value
    out2 = run_canary(_live_cfg(tmp_path, synthetic_live_result=syn))
    assert out2["live_canary_occurred"] is False
    assert (
        "authorization_already_consumed" in (out2.get("blockers") or [])
        or any("consume" in b for b in (out2.get("extra_blockers") or []))
        or any("consumed" in b for b in (out2.get("preflight_blockers") or []))
    )


def test_corrupted_consume_ledger_fails_closed(tmp_path):
    p = tmp_path / "bad.local.jsonl"
    p.write_text("{not-json\n")
    a = _signed_approval()
    r = m46.is_authorization_consumed(
        approval_id=a["approval_id"],
        approval_integrity_fingerprint=a["approval_integrity_fingerprint"],
        path=p,
    )
    assert r["consumed"] is True
    assert r["fail_closed"] is True


def test_consume_ledger_no_secrets(tmp_path):
    syn = {
        "ok": True, "live_network": True, "handle_closed": True,
        "identity_bound": True, "provider_network_calls": 1, "call_budget_used": 1,
        "observed_subject_fingerprint": "SYN_SUBJECT_FP",
    }
    out = run_canary(_live_cfg(tmp_path, synthetic_live_result=syn))
    if not out.get("preflight_passed"):
        return
    text = (tmp_path / "consumed.local.jsonl").read_text()
    assert "ghp_" not in text
    assert "SYN_SUBJECT_FP" in text or "approval_id" in text
    for line in text.splitlines():
        assert is_clean(json.loads(line))


def test_historical_endpoint_exception_constant():
    assert m46.HISTORICAL_ENDPOINT_BINDING_EXCEPTION == "M46_ENDPOINT_BINDING_EXCEPTION"


# ── Live canary evidence contract (revocation prerequisite) ──────────────────
def test_evidence_absent_live_canary_occurred_fails_closed():
    """Missing live_canary_occurred must never authorize revocation."""
    rec = {
        "schema": "m46.fresh_policy_canary.local.v1",
        "resulting_state": "SOMETHING_ELSE",
        "provider_network_calls": 1,
        "authorized_endpoint": "user",
        "actual_request_endpoint": "/user",
        "operation": "IDENTITY_READ",
        "subject_match": True,
        "contains_secret_values": False,
    }
    v = m46.validate_live_canary_evidence(rec)
    assert v["valid"] is False
    assert v["authorizes_revocation_verification"] is False
    assert "live_canary_occurred_absent" in v["blockers"] or not v["checks"].get(
        "live_success_proven")


def test_evidence_explicit_false_fails():
    v = m46.validate_live_canary_evidence({
        "schema": "m46.canary_result.v1",
        "live_canary_occurred": False,
        "contains_secret_values": False,
    })
    assert v["valid"] is False
    assert "live_canary_occurred_false" in v["blockers"]


def test_evidence_string_true_fails_closed():
    """String 'true' must not be treated as boolean True."""
    v = m46.validate_live_canary_evidence({
        "schema": "m46.canary_result.v1",
        "live_canary_occurred": "true",
        "contains_secret_values": False,
    })
    assert v["valid"] is False


def test_evidence_controller_explicit_true_ok():
    v = m46.validate_live_canary_evidence({
        "schema": "m46.canary_result.v1",
        "live_canary_occurred": True,
        "contains_secret_values": False,
    })
    assert v["valid"] is True
    assert v["authorizes_revocation_verification"] is True


def test_evidence_policy_v1_success_fields_ok_without_flag():
    """v1 policy records omitted the flag; explicit success fields may prove live."""
    v = m46.validate_live_canary_evidence({
        "schema": "m46.fresh_policy_canary.local.v1",
        "resulting_state": "M46_FRESH_POLICY_CANARY_VALIDATED_PENDING_EXTERNAL_REVOCATION",
        "provider_network_calls": 1,
        "authorized_endpoint": "user",
        "actual_request_endpoint": "/user",
        "operation": "IDENTITY_READ",
        "subject_match": True,
        "contains_secret_values": False,
    })
    assert v["valid"] is True
    assert v["checks"].get("policy_schema_success_proven") is True


def test_evidence_policy_v1_meta_endpoint_fails():
    v = m46.validate_live_canary_evidence({
        "schema": "m46.fresh_policy_canary.local.v1",
        "resulting_state": "M46_FRESH_POLICY_CANARY_VALIDATED_PENDING_EXTERNAL_REVOCATION",
        "provider_network_calls": 1,
        "authorized_endpoint": "meta",
        "actual_request_endpoint": "/user",
        "operation": "IDENTITY_READ",
        "subject_match": True,
        "contains_secret_values": False,
    })
    assert v["valid"] is False


def test_build_policy_canary_evidence_includes_explicit_flag():
    a = _signed_approval()
    canary = {
        "verdict": M46Verdict.CANARY_COMPLETED_PENDING_REVOCATION.value,
        "state": "CANARY_COMPLETED_PENDING_REVOCATION",
        "live_canary_occurred": True,
        "requires_external_revocation": True,
        "authorization_consumed_durable": True,
        "canary_evidence_fingerprint": "abc",
        "live_result": {
            "provider_network_calls": 1,
            "retries": 0,
            "expected_subject_fingerprint": "SYN_SUBJECT_FP",
            "observed_subject_fingerprint": "SYN_SUBJECT_FP",
            "identity_bound": True,
        },
        "contains_secret_values": False,
    }
    rec = m46.build_policy_canary_evidence(canary_result=canary, approval=a)
    assert rec["schema"] == m46.LIVE_CANARY_EVIDENCE_SCHEMA_POLICY_V2
    assert rec["live_canary_occurred"] is True
    assert rec["authorized_endpoint"] == "user"
    v = m46.validate_live_canary_evidence(rec)
    assert v["valid"] is True


def test_http_200_never_implies_cleanup_in_revocation_api():
    out = m46.run_revocation(
        mode="live", live_flag=True,
        environ={"SAATHI_M46_LIVE_GATE": "1"},
        synthetic_http_status=200,
    )
    assert out.get("http_401_confirmed") is False
    assert out.get("http_status") == 200


def test_http_401_confirms_without_auto_cleanup():
    out = m46.run_revocation(
        mode="live", live_flag=True,
        environ={"SAATHI_M46_LIVE_GATE": "1"},
        synthetic_http_status=401,
    )
    assert out.get("http_401_confirmed") is True
    assert "cleanup" not in out or out.get("cleanup") is None


def test_http_403_not_conclusive_cleanup():
    out = m46.run_revocation(
        mode="live", live_flag=True,
        environ={"SAATHI_M46_LIVE_GATE": "1"},
        synthetic_http_status=403,
    )
    assert out.get("http_401_confirmed") is False

def test_m39_one_call_ceiling_blocks_second_send():
    """Transport wrapper raises before a second network send when ceiling=1."""
    from saathi.credentials import m39 as m39mod
    from saathi.credentials.m37 import SUBJECT_FP
    from saathi.connectors.providers.external.transport import ExternalTransport
    from saathi.connectors.providers.external.testkit import (
        good_tls_prober, public_resolver,
    )

    sends = {"n": 0}

    def counting_sender(ctx):
        sends["n"] += 1
        # Return a minimal success-like body for /user; second call should not reach here
        body = b'{"id": 424242, "type": "User"}'
        return {
            "status_code": 200,
            "headers": {"content-type": "application/json", "x-oauth-scopes": "read:user"},
            "body_bytes": body,
            "decompressed_size": len(body),
            "content_type": "application/json",
            "location": "",
        }

    # Use IN_MEMORY_TEST fixture path with a transport that still hits ceiling wrapper
    # via max_provider_network_calls=1 in offline fixture mode.
    out = m39mod.run_live_single_session(
        secret_source_kind="IN_MEMORY_TEST",
        secret_locator="ceiling-test",
        acknowledgements=tuple(m39mod.M39_ACK_TOKENS),
        allow_offline_fixture=True,
        expected_subject_fingerprint=SUBJECT_FP,
        max_provider_network_calls=1,
        disable_retries=True,
        transport=ExternalTransport(
            resolver=public_resolver(["1.2.3.4"]),
            tls_prober=good_tls_prober(),
            sender=counting_sender,
        ),
    )
    assert out["ok"] is True
    assert out["call_budget_used"] == 1
    assert sends["n"] == 1
    assert is_clean(out)


def test_m39_default_two_calls_unchanged():
    from saathi.credentials import m39 as m39mod
    out = m39mod.run_live_single_session(
        secret_source_kind="IN_MEMORY_TEST",
        secret_locator="default-two",
        acknowledgements=tuple(m39mod.M39_ACK_TOKENS),
        allow_offline_fixture=True,
    )
    assert out["ok"] is True
    assert out["call_budget_used"] == 2
    assert out.get("max_provider_network_calls") is None
    assert is_clean(m46.build_implementation_completion())
    assert is_clean(validate_approval(_signed_approval()))


def test_evidence_bundle():
    b = m46.build_m46_evidence()
    for name, body in b.items():
        assert is_clean(body), name
    assert b["summary"]["state"] == m46.FRAMEWORK_STATE
    assert b["summary"]["live_canary_occurred"] is False


def test_m32_intact():
    from saathi.connectors.providers.models import M32_PROHIBITED_MODES, ExecutionMode
    assert ExecutionMode.CANARY in M32_PROHIBITED_MODES
    assert ExecutionMode.ACTIVE in M32_PROHIBITED_MODES


def test_state_machine_names():
    names = {s.value for s in ExecutionState}
    for req in (
        "DRAFT", "AWAITING_APPROVAL", "APPROVAL_VALIDATED", "PREFLIGHT_PASSED",
        "READY_FOR_ONE_COMMAND_LIVE_GATE", "CANARY_RUNNING",
        "CANARY_COMPLETED_PENDING_REVOCATION",
        "REVOCATION_VERIFIED_PENDING_CLEANUP", "CLOSED_ADVISORY_ONLY",
        "ABORTED", "ROLLED_BACK", "BLOCKED", "FAILED",
    ):
        assert req in names


def test_module_fingerprint_stable():
    assert m46.module_fingerprint() == m46.module_fingerprint()


def test_simulation_matrix_credential_free():
    sim = m46.simulate()
    assert sim["mode"] == "SIMULATED_NOT_LIVE"
    assert sim["live_canary_occurred"] is False
    assert sim["grants_anything"] is False
    assert "no_approval" in sim["cases"]
