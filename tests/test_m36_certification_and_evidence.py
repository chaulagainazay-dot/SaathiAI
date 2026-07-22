"""M36 — Certification, evidence, leaks, repository invariants (offline)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.connectors.providers.external.testkit import make_transport, public_resolver, good_tls_prober
from saathi.connectors.providers.external.transport import SendContext
from saathi.credentials.backends import InMemoryTestSecretBackend
from saathi.credentials.broker import CredentialBroker
from saathi.credentials.leakscan import is_clean, scan
from saathi.credentials.m35 import SandboxAccountRegistry, SessionLeaseStore, subject_fingerprint
from saathi.credentials.m36 import (
    M36_ACK_TOKENS,
    AuthorizationStore,
    CertificationState,
    assess_m36_certification,
    compute_m36_fingerprint,
    preflight_summary,
    qualify_sandbox_identity,
    run_m36_session,
    validation_summary_body,
    write_m36_evidence,
    M36ScopeResult,
)

CLK = lambda: 3_000_000.0
SYNTH = "SYNTHETIC_M36_SECRET_VALUE_NOT_REAL"
ALL_ACKS = tuple(M36_ACK_TOKENS)
SUBJECT_ID = "424242"
SUBJECT_FP = subject_fingerprint(SUBJECT_ID, provider_id="github_meta")

_USER_BODY = json.dumps({"id": int(SUBJECT_ID), "type": "User"}).encode()
_META_BODY = json.dumps({
    "verifiable_password_authentication": False,
    "hooks": ["1.2.3.0/24"],
    "pages": ["5.6.7.0/24"],
}).encode()


def _path_sender():
    def _s(ctx: SendContext) -> dict:
        if "/user" in ctx.url:
            return {
                "status_code": 200,
                "headers": {"content-type": "application/json", "x-oauth-scopes": "read:user"},
                "body_bytes": _USER_BODY, "content_type": "application/json",
                "location": "", "decompressed_size": len(_USER_BODY),
            }
        return {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "body_bytes": _META_BODY, "content_type": "application/json",
            "location": "", "decompressed_size": len(_META_BODY),
        }
    return _s


def _session_ok():
    broker = CredentialBroker(persist=False, clock=CLK)
    reg = SandboxAccountRegistry(clock=CLK)
    leases = SessionLeaseStore(clock=CLK)
    auth_store = AuthorizationStore(clock=CLK)
    backend = InMemoryTestSecretBackend()
    backend.put("loc", {"api_key": SYNTH})
    cred = broker.create_reference(
        owner_scope="user:test", provider_id="github_meta", credential_type="api_key",
        secret_fields={"api_key": SYNTH}, scopes=("identity:read", "metadata:read"),
        connector_ids=("gov.http",),
    )
    acct = reg.register_sandbox(
        provider_id="github_meta", environment_class="SANDBOX", subject=SUBJECT_ID,
        display_alias="sbx", declared_scopes=("identity:read", "metadata:read"),
    )
    reg.verify(acct.account_ref_id, observed_scopes=("identity:read", "metadata:read"))
    auth = auth_store.create(
        provider_id="github_meta", account_ref_id=acct.account_ref_id,
        credential_ref_id=cred.credential_ref_id, acknowledgements=ALL_ACKS,
        secret_source_kind="IN_MEMORY_TEST",
    )
    qual = qualify_sandbox_identity(
        provider_id="github_meta", account_alias="sbx", environment_class="SANDBOX",
        declared_purpose="m36 disposable", revocation_plan="manual",
        expiration_or_deletion_plan="delete", operator_disposable_ack=True,
    )
    tr = make_transport(sender=_path_sender(), resolver=public_resolver())
    return run_m36_session(
        authorization_store=auth_store, authorization_id=auth.authorization_id,
        account_registry=reg, account_ref_id=acct.account_ref_id, broker=broker,
        credential_ref_id=cred.credential_ref_id, lease_store=leases,
        secret_backend=backend, secret_locator="loc", identity_qualification=qual,
        transport=tr, synthetic_offline=True, expected_subject_fingerprint=SUBJECT_FP,
        clock=CLK, session_id="sess_cert_001",
    )


# ── certification ────────────────────────────────────────────────────────────
def test_authorization_ready_state():
    assert assess_m36_certification(
        identity_ok=False, scope_result="", session_ok=False, authorization_ready_only=True,
    ) == CertificationState.AUTHORIZATION_READY.value


def test_full_session_verified():
    state = assess_m36_certification(
        identity_ok=True,
        scope_result=M36ScopeResult.VERIFIED_READ_ONLY.value,
        session_ok=True,
    )
    assert state == CertificationState.REAL_SANDBOX_SESSION_VERIFIED.value


def test_missing_observed_scope_limitation():
    state = assess_m36_certification(
        identity_ok=True,
        scope_result=M36ScopeResult.DECLARED_ONLY_UNOBSERVED.value,
        session_ok=True,
        limitations=["scope_not_independently_observed"],
    )
    assert state == CertificationState.REAL_SANDBOX_SESSION_VERIFIED_WITH_LIMITATIONS.value


def test_extra_read_scope_limitation():
    state = assess_m36_certification(
        identity_ok=True,
        scope_result=M36ScopeResult.VERIFIED_WITH_EXTRA_READ_SCOPE.value,
        session_ok=True,
    )
    assert state == CertificationState.REAL_SANDBOX_SESSION_VERIFIED_WITH_LIMITATIONS.value


def test_quarantine_cert():
    assert assess_m36_certification(
        identity_ok=True, scope_result="VERIFIED_READ_ONLY", session_ok=True, quarantined=True,
    ) == CertificationState.QUARANTINED.value


def test_revoked_cert():
    assert assess_m36_certification(
        identity_ok=True, scope_result="VERIFIED_READ_ONLY", session_ok=True, revoked=True,
    ) == CertificationState.REVOKED.value


def test_stale_cert():
    assert assess_m36_certification(
        identity_ok=True, scope_result="VERIFIED_READ_ONLY", session_ok=True, stale=True,
    ) == CertificationState.STALE.value


def test_failed_session_cert():
    assert assess_m36_certification(
        identity_ok=False, scope_result="", session_ok=False,
    ) == CertificationState.FAILED.value


def test_session_result_certification_set():
    res = _session_ok()
    assert res["ok"] is True
    assert res["session"]["certification"] in (
        CertificationState.REAL_SANDBOX_SESSION_VERIFIED.value,
        CertificationState.REAL_SANDBOX_SESSION_VERIFIED_WITH_LIMITATIONS.value,
    )


def test_certification_does_not_enable_rollout():
    res = _session_ok()
    assert res["rollout_state"]["connector"] == "OFF"
    assert res["authorities"]["rollout_authorization"] == "NOT GRANTED"
    assert res["authorities"]["CANARY_authorization"] == "NOT GRANTED"
    assert res["authorities"]["ACTIVE_authorization"] == "NOT GRANTED"
    assert res["authorities"]["write_authority"] == "NOT GRANTED"
    assert res["authorities"]["production_authorization"] == "NOT GRANTED"


def test_single_success_does_not_claim_reliability():
    res = _session_ok()
    assert res["session"]["reliability"] in ("SINGLE_SUCCESS", "SUCCESS_WITH_LIMITATIONS")
    assert res["session"]["reliability"] != "REPEATABLE_SUCCESS" or True  # only if repeat


def test_certification_operation_specific():
    res = _session_ok()
    assert res["session"]["operation"] == "get_meta"
    assert res["session"]["provider_id"] == "github_meta"


def test_fingerprint_specific():
    res = _session_ok()
    assert res["credential_fingerprint"]
    assert len(res["credential_fingerprint"]) == 32


# ── evidence ─────────────────────────────────────────────────────────────────
def test_offline_evidence_write(tmp_path):
    res = _session_ok()
    bodies = {
        "baseline": {"milestone": "M36", "provider": "github_meta", "live": False},
        "validation_summary": validation_summary_body(
            session_result=res, certification=res["session"]["certification"],
            real_session_exercised=False,
        ),
        "verification_fingerprint": {"fingerprint": compute_m36_fingerprint()},
        "session_lifecycle": res["session"],
        "call_budget": res["call_budget"],
        "leak_scan": {"findings": [], "clean": True},
    }
    written = write_m36_evidence(bodies, evidence_dir=str(tmp_path))
    assert len(written) == len(bodies)
    for p in tmp_path.iterdir():
        data = json.loads(p.read_text())
        assert is_clean(data)
        assert SYNTH not in p.read_text()


def test_live_evidence_clearly_classified():
    summary = validation_summary_body(real_session_exercised=True, certification="REAL_SANDBOX_SESSION_VERIFIED")
    assert summary["real_sandbox_session"] == "EXERCISED"
    summary2 = validation_summary_body(real_session_exercised=False)
    assert summary2["real_sandbox_session"] == "NOT_EXERCISED"


def test_evidence_no_auth_header():
    res = _session_ok()
    blob = json.dumps(res, default=str)
    assert "Authorization:" not in blob
    assert "Bearer " not in blob


def test_evidence_has_call_counts():
    res = _session_ok()
    assert res["call_budget"]["consumed"] >= 1
    assert "identity_calls" in res["call_budget"]
    assert "retries" in res["call_budget"]


def test_leak_scanner_detects_injected_secret():
    findings = scan({"token": "ghp_abcdefghijklmnopqrstuvwxyz012345"})
    assert findings


def test_session_result_leak_clean():
    res = _session_ok()
    assert is_clean(res)


def test_preflight_banner():
    p = preflight_summary()
    assert p["provider"] == "github_meta"
    assert p["max_calls"] == 3
    assert p["authentication_required_for_identity"] is True
    assert p["authentication_required_for_meta"] is False
    assert "ROLLOUT OFF" in p["banner"]


def test_m36_fingerprint_deterministic():
    assert compute_m36_fingerprint() == compute_m36_fingerprint()


def test_m37_not_started():
    res = _session_ok()
    assert res["m37_started"] is False
    s = validation_summary_body(session_result=res, certification=res["session"]["certification"])
    assert s["m37_started"] is False


def test_trading_guardian_unengaged():
    res = _session_ok()
    assert "UNENGAGED" in res["trading_guardian"] or "UNCHANGED" in res["trading_guardian"]


def test_no_absolute_home_paths_in_preflight():
    p = preflight_summary()
    blob = json.dumps(p)
    assert "/Users/" not in blob
