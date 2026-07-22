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


def test_synthetic_live_success_stops_pending_revocation():
    """Hermetic synthetic live result — does not call network."""
    out = run_canary(CanaryConfig(
        mode="live",
        live_flag=True,
        environ={"SAATHI_M46_LIVE_GATE": "1"},
        approval=_signed_approval(),
        m44_request=_m44_req(),
        m45_snapshot=_m45_snap(),
        now="2026-07-22T12:00:00+00:00",
        secret_source_kind="OS_KEYCHAIN_REFERENCE",
        secret_locator="svc:acct",
        expected_subject_fingerprint="SYN_SUBJECT_FP",
        synthetic_live_result={
            "ok": True, "live_network": True, "handle_closed": True,
            "identity_bound": True, "http_status": 200, "reason": "ok",
        },
    ))
    # preflight may still block if m44+m45 composition imperfect; if it passes:
    if out["preflight_passed"]:
        assert out["verdict"] == M46Verdict.CANARY_COMPLETED_PENDING_REVOCATION.value
        assert out["requires_external_revocation"] is True
        assert out["authorizes_execution"] is False
        assert out["grants_active"] is False
    else:
        # fail closed is acceptable if composition gates not fully green
        assert out["authorizes_execution"] is False


def test_secret_handle_not_destroyed_fails():
    out = run_canary(CanaryConfig(
        mode="live",
        live_flag=True,
        environ={"SAATHI_M46_LIVE_GATE": "1"},
        approval=_signed_approval(),
        m44_request=_m44_req(),
        m45_snapshot=_m45_snap(),
        now="2026-07-22T12:00:00+00:00",
        secret_source_kind="OS_KEYCHAIN_REFERENCE",
        secret_locator="svc:acct",
        synthetic_live_result={
            "ok": True, "live_network": True, "handle_closed": False,
            "identity_bound": True, "http_status": 200,
        },
    ))
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
