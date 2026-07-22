"""M35 — Sandbox account registry, read-only session lifecycle, eligibility.

Offline and synthetic. No network, no real secret, no write.
"""
from __future__ import annotations

import pytest

from saathi.credentials.broker import CredentialBroker
from saathi.credentials.m35 import (
    AccountVerificationState,
    M35Error,
    SandboxAccountRegistry,
    SessionLeaseStore,
    SessionState,
    build_approval,
    compose_session_eligibility,
    run_sandbox_session,
)
from saathi.connectors.providers.external.profiles import resolve_external_profile

PROFILE = resolve_external_profile("github_meta")
SYNTH = "SYNTHETIC_SECRET_VALUE"
CLK = lambda: 1000.0


def _broker():
    return CredentialBroker(persist=False, clock=CLK)


def _cred(b, **kw):
    return b.create_reference(owner_scope="user:test", provider_id="github_meta",
                              credential_type="api_key", secret_fields={"api_key": SYNTH},
                              scopes=("metadata:read",), connector_ids=("gov.http",), **kw)


def _registry():
    return SandboxAccountRegistry(clock=CLK)


def _account(reg, *, env="SANDBOX", scopes=("metadata:read",), verify=True):
    a = reg.register_sandbox(provider_id="github_meta", environment_class=env,
                             subject="SYNTHETIC_ACCOUNT_SUBJECT", display_alias="sbx",
                             declared_scopes=scopes)
    if verify:
        reg.verify(a.account_ref_id, observed_scopes=scopes)
    return a


def _approval(cred_id, acct_id, **over):
    kw = dict(purpose="m35_readonly_verify", provider_id="github_meta", account_ref_id=acct_id,
              credential_ref_id=cred_id, operation="get_meta", environment_class="SANDBOX",
              approved_scopes=("metadata:read",), read_only_acknowledged=True, sandbox_acknowledged=True,
              secret_access_acknowledged=True, non_production_acknowledged=True, write_prohibited=True)
    kw.update(over)
    return build_approval(**kw)


def _run(**over):
    b = _broker(); reg = _registry(); leases = SessionLeaseStore(clock=CLK)
    cred = _cred(b); acct = _account(reg)
    appr = _approval(cred.credential_ref_id, acct.account_ref_id)
    kw = dict(provider_id="github_meta", profile=PROFILE, account_registry=reg,
              account_ref_id=acct.account_ref_id, broker=b, credential_ref_id=cred.credential_ref_id,
              approval=appr, lease_store=leases, environment_class="SANDBOX",
              requested_scopes=("metadata:read",), observed_scopes=("metadata:read",),
              synthetic=True, clock=CLK)
    kw.update(over)
    return b, reg, leases, cred, acct, appr, run_sandbox_session(**kw)


# ── sandbox account registry ─────────────────────────────────────────────────
def test_synthetic_account_registers():
    reg = _registry()
    a = _account(reg, verify=False)
    assert a.provider_id == "github_meta"
    assert a.verification_state == AccountVerificationState.UNVERIFIED.value


def test_account_subject_is_fingerprinted():
    reg = _registry()
    a = _account(reg, verify=False)
    assert "SYNTHETIC_ACCOUNT_SUBJECT" not in a.account_subject_fingerprint
    assert len(a.account_subject_fingerprint) == 32


def test_production_account_fails():
    reg = _registry()
    with pytest.raises(M35Error) as e:
        reg.register_sandbox(provider_id="github_meta", environment_class="PRODUCTION",
                             subject="s", declared_scopes=("metadata:read",))
    assert e.value.code == "production_environment_forbidden"


def test_account_provider_required():
    reg = _registry()
    with pytest.raises(M35Error) as e:
        reg.register_sandbox(provider_id="", environment_class="SANDBOX", subject="s")
    assert e.value.code == "provider_required"


def test_account_prohibited_provider_fails():
    reg = _registry()
    with pytest.raises(M35Error):
        reg.register_sandbox(provider_id="binance_trade", environment_class="SANDBOX", subject="s")


def test_account_raw_email_alias_rejected():
    reg = _registry()
    with pytest.raises(M35Error) as e:
        reg.register_sandbox(provider_id="github_meta", environment_class="SANDBOX",
                             subject="s", display_alias="user@example.com", declared_scopes=())
    assert e.value.code == "raw_personal_identifier"


def test_account_password_metadata_rejected():
    reg = _registry()
    with pytest.raises(M35Error) as e:
        reg.register_sandbox(provider_id="github_meta", environment_class="SANDBOX",
                             subject="s", declared_scopes=(), metadata={"password": "x"})
    assert e.value.code == "forbidden_account_field"


def test_account_raw_email_metadata_rejected():
    reg = _registry()
    with pytest.raises(M35Error) as e:
        reg.register_sandbox(provider_id="github_meta", environment_class="SANDBOX",
                             subject="s", declared_scopes=(), metadata={"note": "reach me at a@b.co"})
    assert e.value.code in ("raw_personal_identifier", "forbidden_account_field")


def test_account_forbidden_scope_rejected():
    reg = _registry()
    with pytest.raises(M35Error):
        reg.register_sandbox(provider_id="github_meta", environment_class="SANDBOX",
                             subject="s", declared_scopes=("repo:write",))


def test_account_verify_synthetic():
    reg = _registry()
    a = _account(reg, verify=False)
    reg.verify(a.account_ref_id, synthetic=True)
    assert reg.is_verified(a.account_ref_id)
    assert a.verification_state == AccountVerificationState.SYNTHETIC_VERIFIED.value


def test_account_verify_observed():
    reg = _registry()
    a = _account(reg)
    assert a.verification_state == AccountVerificationState.VERIFIED.value


def test_account_verify_mismatch():
    reg = _registry()
    a = _account(reg, verify=False)
    reg.verify(a.account_ref_id, observed_scopes=("metadata:read", "public:read"))
    assert a.verification_state == AccountVerificationState.MISMATCHED.value


def test_account_safe_dict_no_secret():
    reg = _registry()
    a = _account(reg)
    d = a.to_safe_dict()
    assert d["contains_secret_values"] is False


def test_account_drift_detected():
    reg = _registry()
    a = _account(reg)
    fp = a.drift_fingerprint()
    assert reg.check_drift(a.account_ref_id, expected_fingerprint=fp)["drifted"] is False
    a.declared_scopes = ("public:read",)
    assert reg.check_drift(a.account_ref_id, expected_fingerprint=fp)["drifted"] is True


def test_account_revoke():
    reg = _registry()
    a = _account(reg)
    reg.revoke(a.account_ref_id, reason="test")
    assert a.verification_state == AccountVerificationState.REVOKED.value
    assert reg.is_verified(a.account_ref_id) is False


def test_verify_revoked_account_fails():
    reg = _registry()
    a = _account(reg)
    reg.revoke(a.account_ref_id, reason="x")
    with pytest.raises(M35Error) as e:
        reg.verify(a.account_ref_id, synthetic=True)
    assert e.value.code == "account_revoked"


# ── session lifecycle (happy path) ───────────────────────────────────────────
def test_synthetic_session_completes():
    _b, _r, _l, _c, _a, _ap, res = _run()
    assert res["ok"] is True
    assert res["session_state"] == SessionState.COMPLETED.value
    assert res["handle_closed"] is True
    assert res["credential_fingerprint"]  # derived


def test_session_no_external_call_or_write():
    *_ignore, res = _run()
    assert res["external_calls"] == 0 and res["external_writes"] == 0


def test_session_result_leak_clean():
    from saathi.credentials.m35 import is_clean
    *_ignore, res = _run()
    assert is_clean(res)
    assert SYNTH.lower() not in str(res).lower()


def test_session_rollout_off():
    *_ignore, res = _run()
    assert res["rollout_state"] == {"connector": "OFF", "provider": "OFF", "inference": "OFF",
                                    "canary_providers": 0, "active_providers": 0}


def test_session_trading_guardian_unchanged():
    *_ignore, res = _run()
    assert res["trading_guardian"] == "UNCHANGED / UNENGAGED"


def test_session_consumes_lease():
    b, reg, leases, cred, acct, appr, res = _run()
    lease = leases.get(res["session"]["lease_id"])
    assert lease.uses_remaining == 0


def test_session_secret_handle_released():
    *_ignore, res = _run()
    assert res["handle_closed"] is True


# ── session lifecycle (fail-closed) ──────────────────────────────────────────
def test_session_requires_verified_account():
    b = _broker(); reg = _registry(); leases = SessionLeaseStore(clock=CLK)
    cred = _cred(b); acct = _account(reg, verify=False)
    appr = _approval(cred.credential_ref_id, acct.account_ref_id)
    res = run_sandbox_session(provider_id="github_meta", profile=PROFILE, account_registry=reg,
                              account_ref_id=acct.account_ref_id, broker=b, credential_ref_id=cred.credential_ref_id,
                              approval=appr, lease_store=leases, environment_class="SANDBOX",
                              requested_scopes=("metadata:read",), observed_scopes=("metadata:read",), clock=CLK)
    assert res["ok"] is False and res["reason"] == "account_not_verified"


def test_session_production_env_aborts():
    b = _broker(); reg = _registry(); leases = SessionLeaseStore(clock=CLK)
    cred = _cred(b); acct = _account(reg)
    appr = _approval(cred.credential_ref_id, acct.account_ref_id)
    res = run_sandbox_session(provider_id="github_meta", profile=PROFILE, account_registry=reg,
                              account_ref_id=acct.account_ref_id, broker=b, credential_ref_id=cred.credential_ref_id,
                              approval=appr, lease_store=leases, environment_class="PRODUCTION",
                              requested_scopes=("metadata:read",), observed_scopes=("metadata:read",), clock=CLK)
    assert res["ok"] is False
    assert res["session_state"] == SessionState.ABORTED.value


def test_session_scope_broadening_blocked():
    b, reg, leases, cred, acct, appr, res = _run(requested_scopes=("public:read",))
    # approval only permits metadata:read → approval mismatch fails closed
    assert res["ok"] is False
    assert res["session_state"] == SessionState.ABORTED.value


def test_session_revoked_credential_aborts():
    b = _broker(); reg = _registry(); leases = SessionLeaseStore(clock=CLK)
    cred = _cred(b); acct = _account(reg)
    b.revoke(cred.credential_ref_id, reason="revoked")
    appr = _approval(cred.credential_ref_id, acct.account_ref_id)
    res = run_sandbox_session(provider_id="github_meta", profile=PROFILE, account_registry=reg,
                              account_ref_id=acct.account_ref_id, broker=b, credential_ref_id=cred.credential_ref_id,
                              approval=appr, lease_store=leases, environment_class="SANDBOX",
                              requested_scopes=("metadata:read",), observed_scopes=("metadata:read",), clock=CLK)
    assert res["ok"] is False and "credential_revoked" in res["reason"]


def test_session_revoked_account_aborts():
    b = _broker(); reg = _registry(); leases = SessionLeaseStore(clock=CLK)
    cred = _cred(b); acct = _account(reg)
    reg.revoke(acct.account_ref_id, reason="x")
    appr = _approval(cred.credential_ref_id, acct.account_ref_id)
    res = run_sandbox_session(provider_id="github_meta", profile=PROFILE, account_registry=reg,
                              account_ref_id=acct.account_ref_id, broker=b, credential_ref_id=cred.credential_ref_id,
                              approval=appr, lease_store=leases, environment_class="SANDBOX",
                              requested_scopes=("metadata:read",), observed_scopes=("metadata:read",), clock=CLK)
    assert res["ok"] is False and res["reason"] == "account_not_verified"


def test_session_provider_substitution_aborts():
    b = _broker(); reg = _registry(); leases = SessionLeaseStore(clock=CLK)
    cred = _cred(b); acct = _account(reg)
    appr = _approval(cred.credential_ref_id, acct.account_ref_id)
    res = run_sandbox_session(provider_id="other", profile=PROFILE, account_registry=reg,
                              account_ref_id=acct.account_ref_id, broker=b, credential_ref_id=cred.credential_ref_id,
                              approval=appr, lease_store=leases, environment_class="SANDBOX",
                              requested_scopes=("metadata:read",), observed_scopes=("metadata:read",), clock=CLK)
    assert res["ok"] is False and res["session_state"] == SessionState.ABORTED.value


# ── composed eligibility ─────────────────────────────────────────────────────
def _elig(**over):
    kw = dict(production_certified=True, connector_certified=True, provider_simulation_fresh=True,
              external_profile_fresh=True, credential_valid=True, secret_source_ready=True,
              environment_class="SANDBOX", account_verified=True, scope_verified=True,
              within_ceiling=True, credential_healthy=True, lease_valid=True, approval_valid=True,
              provider_healthy=True, quarantined=False, rollout_off=True)
    kw.update(over)
    return compose_session_eligibility(**kw)


def test_eligibility_all_green():
    ok, blockers = _elig()
    assert ok is True and blockers == []


@pytest.mark.parametrize("kw,blocker", [
    (dict(production_certified=False), "production_not_certified"),
    (dict(connector_certified=False), "connector_not_certified"),
    (dict(credential_valid=False), "credential_invalid"),
    (dict(account_verified=False), "account_not_verified"),
    (dict(scope_verified=False), "scope_not_verified"),
    (dict(within_ceiling=False), "request_exceeds_ceiling"),
    (dict(credential_healthy=False), "credential_unhealthy"),
    (dict(lease_valid=False), "lease_invalid"),
    (dict(approval_valid=False), "approval_invalid"),
    (dict(provider_healthy=False), "provider_unhealthy"),
    (dict(quarantined=True), "provider_quarantined"),
    (dict(rollout_off=False), "rollout_not_off"),
])
def test_eligibility_blockers(kw, blocker):
    ok, blockers = _elig(**kw)
    assert ok is False and blocker in blockers


def test_eligibility_production_env_blocked():
    ok, blockers = _elig(environment_class="PRODUCTION")
    assert ok is False


def test_eligibility_is_pure_no_side_effects():
    # calling twice yields identical results (no mutation)
    a = _elig()
    b = _elig()
    assert a == b
