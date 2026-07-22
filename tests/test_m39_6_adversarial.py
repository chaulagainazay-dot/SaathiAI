"""M39.6 — Adversarial / negative security tests across the M39.x surface.

Test-only milestone (PRE-M40 offline readiness). Synthetic credentials only.
Attacks the M39 + M39.1–M39.5 surfaces to prove fail-closed behavior against:
raw-secret injection, reference confusion, path/command/endpoint/method escape,
SSRF-like manipulation, provider substitution, scope/canary escalation,
kill-switch/budget bypass, evidence tampering, and unsafe defaults.
"""
from __future__ import annotations

import json

import pytest

from saathi.credentials import m39, m39_1, m39_2, m39_3, m39_4, m39_5
from saathi.credentials.leakscan import is_clean
from saathi.credentials.m39 import M39Error

RAW = "ghp_abcdefghijklmnopqrstuvwxyz12"          # synthetic token shape
BEARER = "Bearer abcdefghijklmnopqrstuvwxyz123456"
SHELL = "svc; rm -rf / #"
TRAVERSAL = "../../etc/passwd"
SSRF = "http://169.254.169.254/latest/meta-data"


# ── raw-secret injection across every locator entry point ────────────────────
@pytest.mark.parametrize("bad", [RAW, BEARER, "raw:sometoken", "gho_" + "z" * 30])
def test_m39_1_plan_rejects_secret_shapes(bad):
    with pytest.raises(M39Error):
        m39_1.build_execution_plan(locator=bad)


@pytest.mark.parametrize("bad", [RAW, BEARER, "raw:x"])
def test_m39_1_backend_availability_rejects_secret_shapes(bad):
    with pytest.raises(M39Error):
        m39_1.check_backend_availability(source_kind="OS_KEYCHAIN_REFERENCE", locator=bad)


def test_m39_1_checklist_rejects_secret_shape():
    with pytest.raises(M39Error):
        m39_1.generate_revocation_checklist(locator=RAW)


def test_m39_qualify_reference_rejects_raw():
    with pytest.raises(M39Error):
        m39.qualify_secret_reference(source_kind="ENV_REFERENCE", locator=RAW, require_exists=False)


# ── env-var value-vs-name confusion ──────────────────────────────────────────
def test_env_reference_rejects_token_shaped_var_name():
    # a token supplied where an env var NAME is expected must be rejected
    with pytest.raises(M39Error):
        m39_1.build_execution_plan(source_kind="ENV_REFERENCE", env_var_name=RAW)


def test_env_reference_does_not_read_value_into_output():
    r = m39_1.check_backend_availability(
        source_kind="ENV_REFERENCE", env_var_name="SAATHI_M396_SECRET",
        environ={"SAATHI_M396_SECRET": RAW},
    )
    assert RAW not in json.dumps(r)
    assert r["resolves_plaintext"] is False


# ── command injection: metacharacter locator is data, never executed ─────────
def test_keychain_parse_treats_shell_metachars_as_literal():
    be = m39.MacOSKeychainReferenceBackend()
    svc, acct = be._parse(SHELL)
    assert svc == SHELL and acct == ""  # no split on ';' or spaces; no execution


# ── endpoint / method / SSRF escape ──────────────────────────────────────────
@pytest.mark.parametrize("ep", ["/repos", TRAVERSAL, SSRF, "/user/../admin"])
def test_endpoint_escape_flagged(ep):
    plan = m39_1.build_execution_plan(endpoints=(ep,), locator="svc:acct")
    assert plan["plan_valid"] is False
    assert "endpoint_not_allowlisted" in plan["problems"]


def test_approval_record_rejects_ssrf_endpoint():
    rec = {f: "x" for f in m39_3._REQUIRED_APPROVAL_FIELDS}
    rec.update(provider="github_meta", endpoints=[SSRF], methods=["GET"],
               rollout_percent=3, explicit_acknowledgements=list(m39_3._REQUIRED_APPROVAL_ACKS))
    v = m39_3.validate_operator_approval_record(rec)
    assert v["valid"] is False and "endpoint_not_allowlisted" in v["problems"]


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_write_method_escape_rejected(method):
    rec = {f: "x" for f in m39_3._REQUIRED_APPROVAL_FIELDS}
    rec.update(provider="github_meta", endpoints=["user"], methods=[method],
               rollout_percent=3, explicit_acknowledgements=list(m39_3._REQUIRED_APPROVAL_ACKS))
    v = m39_3.validate_operator_approval_record(rec)
    assert v["valid"] is False and "method_not_allowlisted" in v["problems"]


# ── provider substitution ────────────────────────────────────────────────────
def test_provider_substitution_checklist_rejected():
    with pytest.raises(M39Error):
        m39_1.generate_revocation_checklist(provider="stripe")


def test_provider_substitution_approval_rejected():
    rec = {f: "x" for f in m39_3._REQUIRED_APPROVAL_FIELDS}
    rec.update(provider="evil.example", endpoints=["user"], methods=["GET"],
               rollout_percent=3, explicit_acknowledgements=list(m39_3._REQUIRED_APPROVAL_ACKS))
    v = m39_3.validate_operator_approval_record(rec)
    assert v["valid"] is False and "provider_not_allowlisted" in v["problems"]


# ── scope / canary escalation ────────────────────────────────────────────────
def test_rollout_escalation_rejected():
    rec = {f: "x" for f in m39_3._REQUIRED_APPROVAL_FIELDS}
    rec.update(provider="github_meta", endpoints=["user"], methods=["GET"],
               rollout_percent=100, explicit_acknowledgements=list(m39_3._REQUIRED_APPROVAL_ACKS))
    v = m39_3.validate_operator_approval_record(rec)
    assert v["valid"] is False and "rollout_percent_out_of_bounds" in v["problems"]


def test_canary_never_granted_even_with_forged_all_met():
    allmet = {p["id"]: True for p in m39_3.CANARY_PREREQUISITES}
    rec = {f: "x" for f in m39_3._REQUIRED_APPROVAL_FIELDS}
    rec.update(provider="github_meta", endpoints=["user", "meta"], methods=["GET"],
               rollout_percent=5, explicit_acknowledgements=list(m39_3._REQUIRED_APPROVAL_ACKS))
    d = m39_3.evaluate_canary_decision(
        prerequisite_state=allmet, operator_approval_record=rec,
        eligibility_kwargs={
            "live_single_status": "PASSED", "live_multi_status": "PASSED",
            "secret_reference_supplied": True, "external_revocation_confirmed": True,
            "identity_qualified": True, "scope_qualified": True,
        },
    )
    # forged "live PASSED" inputs must still not grant — code hardcodes False
    assert d["grants_canary"] is False
    assert d["decision"] == "CANARY_NOT_GRANTED"


def test_canary_escalation_attempt_is_sev1_alert():
    a = m39_5.detect_alerts({"canary_grant_attempts": 3})
    assert a["highest_severity"] == "SEV1"


# ── kill-switch / budget bypass ──────────────────────────────────────────────
def test_kill_switch_env_forces_block_in_preflight():
    inp = m39.PreflightInput(
        branch="b", head="h", secret_source_kind="OS_KEYCHAIN_REFERENCE",
        secret_locator="svc:acct", secret_ref_exists=True, authorization_present=True,
        acknowledgements=m39.M39_ACK_TOKENS, live_flag=True, kill_switch_ready=True,
        environ={"SAATHI_M39_KILL_SWITCH": "1"},
    )
    pf = m39.run_live_preflight(inp)
    assert pf["ok"] is False and "kill_switch_active" in pf["blockers"]


@pytest.mark.parametrize("budget", [4, 99, 0, -1])
def test_budget_bypass_rejected(budget):
    plan = m39_1.build_execution_plan(per_session_budget=budget, locator="svc:acct")
    assert "invalid_per_session_budget" in plan["problems"]


def test_unsafe_deployment_defaults_rejected():
    bad = m39_4.validate_deployment_config({
        "live_flag_default": "on", "rollout": "ON", "canary": "GRANTED",
    })
    assert bad["valid"] is False
    assert "live_flag_default_must_be_off" in bad["problems"]


# ── evidence tampering / event injection ─────────────────────────────────────
def test_event_with_injected_secret_rejected():
    ev = {"event_type": "m39.single_session_blocked", "session_id": "s",
          "privacy_safe": True, "contains_secret_values": False, "reason": "x",
          "authorization": RAW}
    v = m39_5.validate_audit_event(ev)
    assert v["valid"] is False
    assert "forbidden_field:authorization" in v["problems"] or "leak_detected" in v["problems"]


def test_event_claiming_no_secret_but_leaking_rejected():
    ev = {"event_type": "m39.single_session_failed", "session_id": "s",
          "privacy_safe": True, "contains_secret_values": False,
          "reason": f"failed with {RAW}"}
    v = m39_5.validate_audit_event(ev)
    assert v["valid"] is False and "leak_detected" in v["problems"]


# ── exception / output leakage ───────────────────────────────────────────────
def test_error_paths_never_leak_secret():
    # attempt several rejecting calls; ensure no exception message carries the token
    for fn in (
        lambda: m39_1.build_execution_plan(locator=RAW),
        lambda: m39_1.check_backend_availability(source_kind="OS_KEYCHAIN_REFERENCE", locator=RAW),
        lambda: m39_1.generate_revocation_checklist(locator=RAW),
    ):
        try:
            fn()
        except M39Error as e:
            assert RAW not in str(e) and RAW not in getattr(e, "detail", "")


# ── redaction: diagnostics never surface a present secret ────────────────────
def test_diagnostics_never_leak_env_secret():
    d = m39_1.collect_offline_diagnostics(
        environ={"SAATHI_M39_ALLOW_LIVE_SANDBOX_VALIDATION": "1", "SOME_TOKEN": RAW}
    )
    assert RAW not in json.dumps(d)
    assert is_clean(d)


# ── fault simulation stays non-live under adversarial framing ────────────────
def test_simulation_matrix_never_live():
    mx = m39_2.run_simulation_matrix()
    assert mx["invariants"]["no_live_network"] is True
    for r in mx["results"]:
        assert r["live_network"] is False
