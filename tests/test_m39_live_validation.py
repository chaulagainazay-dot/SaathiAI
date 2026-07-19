"""M39 — Live disposable sandbox validation gates (offline fail-closed)."""
from __future__ import annotations

import json
import os

import pytest

from saathi.credentials import m39
from saathi.credentials.leakscan import is_clean, scan
from saathi.credentials.m37 import SYNTH_SECRET, SUBJECT_FP, fixture_transport
from saathi.credentials.m38 import MultiSessionCoordinator, SessionState


def test_preflight_fail_closed_missing_flag():
    pf = m39.run_live_preflight(m39.PreflightInput(
        branch="milestone/m7-security-engine", head="abc", working_tree_class="NOISE_ONLY",
        secret_source_kind="OS_KEYCHAIN_REFERENCE", secret_locator="svc:acct",
        secret_ref_exists=True, authorization_present=True,
        acknowledgements=tuple(m39.M39_ACK_TOKENS), live_flag=False,
    ))
    assert pf["ok"] is False
    assert "live_feature_flag_missing" in pf["blockers"]
    assert pf["network_calls_performed"] == 0


def test_preflight_missing_acknowledgement():
    pf = m39.run_live_preflight(m39.PreflightInput(
        branch="b", head="h", working_tree_class="CLEAN",
        secret_source_kind="OS_KEYCHAIN_REFERENCE", secret_locator="s",
        secret_ref_exists=True, authorization_present=True,
        acknowledgements=(), live_flag=True,
    ))
    assert pf["ok"] is False
    assert "missing_acknowledgement" in pf["blockers"]


def test_preflight_missing_secret_reference():
    pf = m39.run_live_preflight(m39.PreflightInput(
        branch="b", head="h", working_tree_class="CLEAN",
        secret_source_kind="OS_KEYCHAIN_REFERENCE", secret_locator="",
        secret_ref_exists=False, authorization_present=True,
        acknowledgements=tuple(m39.M39_ACK_TOKENS), live_flag=True,
    ))
    assert pf["ok"] is False
    assert "missing_secret_locator" in pf["blockers"]


def test_rejected_raw_secret_input():
    with pytest.raises(m39.M39Error) as e:
        m39.reject_m39_forbidden_argv(["m39-run", "--token=ghp_abcdefghijklmnopqrstuvwxyz12"])
    assert e.value.code in ("raw_secret_cli_rejected", "token_shaped_argument_rejected")


def test_raw_locator_rejected():
    with pytest.raises(m39.M39Error) as e:
        m39.qualify_secret_reference(
            source_kind="ENV_REFERENCE",
            locator="ghp_abcdefghijklmnopqrstuvwxyz12",
            require_exists=False,
        )
    assert e.value.code == "raw_secret_locator_rejected"


def test_provider_allowlist():
    pf = m39.run_live_preflight(m39.PreflightInput(
        branch="b", head="h", working_tree_class="CLEAN",
        secret_source_kind="OS_KEYCHAIN_REFERENCE", secret_locator="s",
        secret_ref_exists=True, authorization_present=True,
        acknowledgements=tuple(m39.M39_ACK_TOKENS), live_flag=True,
        provider_id="other_provider",
    ))
    assert not pf["ok"]
    assert "provider_not_allowlisted" in pf["blockers"]


def test_endpoint_allowlist():
    pf = m39.run_live_preflight(m39.PreflightInput(
        branch="b", head="h", working_tree_class="CLEAN",
        secret_source_kind="OS_KEYCHAIN_REFERENCE", secret_locator="s",
        secret_ref_exists=True, authorization_present=True,
        acknowledgements=tuple(m39.M39_ACK_TOKENS), live_flag=True,
        endpoints=("/admin",),
    ))
    assert not pf["ok"]
    assert "endpoint_not_allowlisted" in pf["blockers"]


def test_method_allowlist():
    pf = m39.run_live_preflight(m39.PreflightInput(
        branch="b", head="h", working_tree_class="CLEAN",
        secret_source_kind="OS_KEYCHAIN_REFERENCE", secret_locator="s",
        secret_ref_exists=True, authorization_present=True,
        acknowledgements=tuple(m39.M39_ACK_TOKENS), live_flag=True,
        methods=("DELETE",),
    ))
    assert not pf["ok"]
    assert "method_not_allowlisted" in pf["blockers"]


def test_identity_mismatch_offline():
    from saathi.credentials.m37 import run_provider_lifecycle
    life = run_provider_lifecycle(
        transport=fixture_transport(
            identity_body=json.dumps({"id": 111, "type": "User"}).encode(),
        ),
        expected_subject_fingerprint=SUBJECT_FP,
        session_id="id_mis",
    )
    assert life.ok is False


def test_unexpected_scope():
    from saathi.credentials.m36 import classify_observed_scopes
    scope = classify_observed_scopes(("identity:read",), ("repo",))
    assert scope["result"] == "WRITE_SCOPE_PRESENT"


def test_call_budget_exhaustion():
    from saathi.credentials.m36 import CallBudget, M36Error
    cb = CallBudget(2)
    cb.consume(kind="identity")
    cb.consume(kind="operation")
    with pytest.raises(M36Error) as e:
        cb.consume(kind="operation")
    assert e.value.code == "call_budget_exhausted"


def test_aggregate_budget_exhaustion():
    from saathi.credentials.m38 import M38Error
    c = MultiSessionCoordinator(aggregate_call_budget=2, clock=lambda: 1.0)
    c.aggregate_calls_used = 2
    with pytest.raises(M38Error) as e:
        c.start_session(credential_ref_id="x", call_budget=2)
    assert e.value.code == "aggregate_call_budget_exhausted"


def test_separate_session_handles_and_leases():
    multi = m39.run_live_multisession(
        secret_source_kind="IN_MEMORY_TEST",
        secret_locator="m39/t",
        acknowledgements=tuple(m39.M39_ACK_TOKENS),
        allow_offline_fixture=True,
    )
    assert multi["ok"] is True
    assert multi["isolation"]["separate_session_ids"] is True
    assert len(multi["sessions"]) == 2
    assert multi["cleanup_idempotent"] is True


def test_cleanup_independence():
    multi = m39.run_live_multisession(
        secret_source_kind="IN_MEMORY_TEST",
        secret_locator="m39/t2",
        acknowledgements=tuple(m39.M39_ACK_TOKENS),
        allow_offline_fixture=True,
    )
    states = [s.get("state") for s in multi["sessions"]]
    assert all(s == SessionState.CLEANED.value for s in states)


def test_kill_switch_behavior():
    ks = m39.LiveKillSwitch()
    ks.trip("test")
    with pytest.raises(m39.M39Error) as e:
        ks.assert_allows_provider_call()
    assert e.value.code == "kill_switch_active"
    d = ks.to_dict()
    assert d["grants_authority"] is False
    assert d["prevents_new_provider_calls"] is True


def test_recovery_after_local_interruption():
    rec = m39.run_interruption_recovery_validation(offline=True)
    assert rec["failed"] == 0
    assert rec["status"] == m39.LiveExerciseStatus.PASSED.value


def test_duplicate_recovery():
    c = MultiSessionCoordinator(clock=lambda: 2.0)
    c.start_session(credential_ref_id="c", session_id="dup", interrupt_after="identity")
    a = c.recover_session("dup")
    b = c.recover_session("dup")
    assert a.get("ok") is not None
    assert b.get("idempotent") is True or b.get("ok") is True


def test_external_revocation_confirmation_state():
    pending = m39.record_external_revocation(confirmed=False)
    assert pending["status"] == "PENDING"
    conf = m39.record_external_revocation(confirmed=True, operator_note="revoked")
    assert conf["status"] == "CONFIRMED"
    assert conf["saathios_has_token_delete_authority"] is False


def test_canary_recommendation_blocked_without_secret():
    can = m39.evaluate_canary_eligibility(secret_reference_supplied=False)
    assert can["verdict"] == m39.CanaryEligibilityVerdict.BLOCKED_OPERATOR_SECRET_REQUIRED.value
    assert can["grants_canary"] is False


def test_canary_ready_path_no_grant():
    can = m39.evaluate_canary_eligibility(
        secret_reference_supplied=True,
        live_single_status=m39.LiveExerciseStatus.PASSED.value,
        live_multi_status=m39.LiveExerciseStatus.PASSED.value,
        identity_qualified=True,
        scope_qualified=True,
        external_revocation_confirmed=True,
        leak_scan_clean=True,
        cleanup_complete=True,
        leases_revoked=True,
    )
    assert can["verdict"] == m39.CanaryEligibilityVerdict.READY_FOR_OPERATOR_CANARY_DECISION.value
    assert can["grants_canary"] is False
    assert can["grants_production"] is False


def test_canary_blocked_external_revocation():
    can = m39.evaluate_canary_eligibility(
        secret_reference_supplied=True,
        live_single_status=m39.LiveExerciseStatus.PASSED.value,
        live_multi_status=m39.LiveExerciseStatus.PASSED.value,
        identity_qualified=True,
        scope_qualified=True,
        external_revocation_confirmed=False,
        leak_scan_clean=True,
    )
    assert can["verdict"] == m39.CanaryEligibilityVerdict.BLOCKED_EXTERNAL_REVOCATION_REQUIRED.value
    assert can["grants_canary"] is False


def test_authority_non_escalation():
    assert all(v == "NOT GRANTED" for v in m39.AUTHORITIES.values())
    body = m39.authority_state_body()
    assert body["m39_may_grant_canary"] is False
    assert body["m40_started"] is False


def test_leak_scanning_without_exposing_matches():
    findings = scan({"h": "Bearer ghp_abcdefghijklmnopqrstuvwxyz12"})
    assert len(findings) >= 1
    for f in findings:
        assert "ghp_" not in f.preview
        assert "Bearer " not in f.preview


def test_sanitized_provider_errors():
    err = m39.sanitize_provider_error({
        "headers": {"Authorization": "Bearer secretvalue"},
        "message": "unauthorized",
        "status": 401,
    })
    blob = json.dumps(err)
    assert "Authorization" not in blob
    assert "Bearer" not in blob
    assert "secretvalue" not in blob


def test_live_single_requires_flag():
    out = m39.run_live_single_session(
        secret_source_kind="OS_KEYCHAIN_REFERENCE",
        secret_locator="svc:acct",
        acknowledgements=tuple(m39.M39_ACK_TOKENS),
        live_flag=False,
    )
    assert out["ok"] is False
    assert out["reason"] == "live_feature_flag_missing"


def test_offline_fixture_single_session():
    out = m39.run_live_single_session(
        secret_source_kind="IN_MEMORY_TEST",
        secret_locator="m39/fx",
        acknowledgements=tuple(m39.M39_ACK_TOKENS),
        allow_offline_fixture=True,
    )
    assert out["ok"] is True
    assert out["handle_closed"] is True
    assert out["call_budget_used"] <= m39.PER_SESSION_CALL_BUDGET
    assert SYNTH_SECRET not in json.dumps(out)
    assert is_clean(out)


def test_full_validation_blocked_without_operator_secret():
    r = m39.run_m39_validation()
    assert r["ok"] is True  # offline prep healthy
    assert r["executive_verdict"] == "M39 BLOCKED — OPERATOR SECRET REFERENCE REQUIRED"
    assert r["canary_eligibility"]["grants_canary"] is False
    assert r["live_single_session"]["status"] == m39.LiveExerciseStatus.NOT_EXERCISED.value
    assert r["m40_started"] is False
    assert is_clean(r)


def test_offline_failure_gates_all_pass():
    g = m39.run_offline_failure_gates()
    assert g["failed"] == 0
    assert g["passed"] == g["total"]


def test_acks_require_all_ten():
    with pytest.raises(m39.M39Error):
        m39.validate_acknowledgements(m39.M39_ACK_TOKENS[:-1])
    ok = m39.validate_acknowledgements(tuple(m39.M39_ACK_TOKENS))
    assert ok["all_present"] is True
    assert ok["inferred_from_docs"] is False


def test_env_flag_default_closed():
    assert m39.live_flag_enabled({}) is False
    assert m39.live_flag_enabled({m39.ENV_LIVE_FLAG: "0"}) is False
    assert m39.live_flag_enabled({m39.ENV_LIVE_FLAG: "1"}) is True
