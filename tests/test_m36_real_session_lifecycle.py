"""M36 — Real session lifecycle (offline fixture transport)."""
from __future__ import annotations

import json

import pytest

from saathi.connectors.providers.external.testkit import make_transport, public_resolver
from saathi.connectors.providers.external.transport import SendContext
from saathi.credentials.backends import InMemoryTestSecretBackend
from saathi.credentials.broker import CredentialBroker
from saathi.credentials.m35 import SandboxAccountRegistry, SessionLeaseStore, subject_fingerprint
from saathi.credentials import m36
from saathi.credentials.m36 import (
    M36Error,
    M36_ACK_TOKENS,
    AuthorizationStore,
    CleanupDisposition,
    M36SessionState,
    attest_cleanup,
    compose_m36_eligibility,
    qualify_sandbox_identity,
    run_m36_session,
    CallBudget,
)

CLK = lambda: 2_000_000.0
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
        # Authorization must be present for identity path in real mode; fixture always accepts
        path = ctx.url.split("api.github.com", 1)[-1] if "api.github.com" in ctx.url else ctx.url
        if path.startswith("/user") or ctx.url.rstrip("/").endswith("/user"):
            return {
                "status_code": 200,
                "headers": {
                    "content-type": "application/json",
                    "x-oauth-scopes": "read:user",
                },
                "body_bytes": _USER_BODY,
                "content_type": "application/json",
                "location": "",
                "decompressed_size": len(_USER_BODY),
            }
        return {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "body_bytes": _META_BODY,
            "content_type": "application/json",
            "location": "",
            "decompressed_size": len(_META_BODY),
        }
    return _s


def _fixture_transport():
    return make_transport(sender=_path_sender(), resolver=public_resolver())


def _setup():
    broker = CredentialBroker(persist=False, clock=CLK)
    reg = SandboxAccountRegistry(clock=CLK)
    leases = SessionLeaseStore(clock=CLK)
    auth_store = AuthorizationStore(clock=CLK)
    backend = InMemoryTestSecretBackend()
    backend.put("m36/test/loc", {"api_key": SYNTH})
    cred = broker.create_reference(
        owner_scope="user:test", provider_id="github_meta", credential_type="api_key",
        secret_fields={"api_key": SYNTH}, scopes=("identity:read", "metadata:read"),
        connector_ids=("gov.http",),
    )
    acct = reg.register_sandbox(
        provider_id="github_meta", environment_class="SANDBOX",
        subject=SUBJECT_ID, display_alias="sbx-m36",
        declared_scopes=("identity:read", "metadata:read"),
    )
    reg.verify(acct.account_ref_id, observed_scopes=("identity:read", "metadata:read"))
    # align expected fingerprint with subject id fingerprint
    acct.account_subject_fingerprint = SUBJECT_FP
    auth = auth_store.create(
        provider_id="github_meta",
        account_ref_id=acct.account_ref_id,
        credential_ref_id=cred.credential_ref_id,
        acknowledgements=ALL_ACKS,
        secret_source_kind="IN_MEMORY_TEST",
    )
    qual = qualify_sandbox_identity(
        provider_id="github_meta", account_alias="sbx-m36", environment_class="SANDBOX",
        declared_purpose="m36 disposable sandbox verification",
        revocation_plan="manual_pat_delete", expiration_or_deletion_plan="delete_after",
        operator_disposable_ack=True,
    )
    return broker, reg, leases, auth_store, backend, cred, acct, auth, qual


def _run(**over):
    broker, reg, leases, auth_store, backend, cred, acct, auth, qual = _setup()
    kw = dict(
        authorization_store=auth_store,
        authorization_id=auth.authorization_id,
        account_registry=reg,
        account_ref_id=acct.account_ref_id,
        broker=broker,
        credential_ref_id=cred.credential_ref_id,
        lease_store=leases,
        secret_backend=backend,
        secret_locator="m36/test/loc",
        identity_qualification=qual,
        transport=_fixture_transport(),
        synthetic_offline=True,
        live_enabled=False,
        live_env_flag=False,
        expected_subject_fingerprint=SUBJECT_FP,
        clock=CLK,
        session_id="sess_m36_test_001",
    )
    kw.update(over)
    return run_m36_session(**kw), leases, auth_store, auth


def test_valid_synthetic_session_completes():
    res, _, _, _ = _run()
    assert res["ok"] is True
    assert res["handle_closed"] is True
    assert res["session"]["credential_fingerprint"]
    assert res["call_budget"]["consumed"] == 2  # identity + operation
    assert res["external_writes"] == 0


def test_session_state_transitions():
    res, _, _, _ = _run()
    transitions = res["session"]["transitions"]
    assert "AUTHORIZED" in transitions
    assert "ACCOUNT_QUALIFIED" in transitions
    assert "LEASED" in transitions
    assert "SECRET_LOADED" in transitions
    assert "IDENTITY_VERIFIED" in transitions
    assert "SCOPE_VERIFIED" in transitions
    assert "COMPLETED" in transitions
    assert "SECRET_CLOSED" in transitions


def test_session_cannot_switch_provider():
    res, _, _, _ = _run()
    assert res["session"]["provider_id"] == "github_meta"


def test_session_cannot_switch_account_via_auth():
    broker, reg, leases, auth_store, backend, cred, acct, auth, qual = _setup()
    other = reg.register_sandbox(
        provider_id="github_meta", environment_class="SANDBOX", subject="999",
        display_alias="other", declared_scopes=("identity:read", "metadata:read"),
    )
    reg.verify(other.account_ref_id, observed_scopes=("identity:read", "metadata:read"))
    res = run_m36_session(
        authorization_store=auth_store, authorization_id=auth.authorization_id,
        account_registry=reg, account_ref_id=other.account_ref_id, broker=broker,
        credential_ref_id=cred.credential_ref_id, lease_store=leases,
        secret_backend=backend, secret_locator="m36/test/loc",
        identity_qualification=qual, transport=_fixture_transport(),
        synthetic_offline=True, expected_subject_fingerprint=SUBJECT_FP, clock=CLK,
    )
    assert res["ok"] is False
    assert "account" in res["reason"] or "authorization" in res["reason"]


def test_session_cannot_switch_credential():
    broker, reg, leases, auth_store, backend, cred, acct, auth, qual = _setup()
    other = broker.create_reference(
        owner_scope="user:test", provider_id="github_meta", credential_type="api_key",
        secret_fields={"api_key": "OTHER"}, scopes=("identity:read", "metadata:read"),
        connector_ids=("gov.http",),
    )
    res = run_m36_session(
        authorization_store=auth_store, authorization_id=auth.authorization_id,
        account_registry=reg, account_ref_id=acct.account_ref_id, broker=broker,
        credential_ref_id=other.credential_ref_id, lease_store=leases,
        secret_backend=backend, secret_locator="m36/test/loc",
        identity_qualification=qual, transport=_fixture_transport(),
        synthetic_offline=True, expected_subject_fingerprint=SUBJECT_FP, clock=CLK,
    )
    assert res["ok"] is False


def test_failed_identity_closes_handle():
    def bad_sender(ctx: SendContext):
        return {
            "status_code": 401, "headers": {}, "body_bytes": b'{"message":"bad"}',
            "content_type": "application/json", "location": "", "decompressed_size": 15,
        }
    tr = make_transport(sender=bad_sender, resolver=public_resolver())
    res, _, _, _ = _run(transport=tr)
    assert res["ok"] is False
    assert res["handle_closed"] is True
    assert res["session"]["reliability"] == "AUTHENTICATION_FAILURE"


def test_call_budget_fourth_rejected():
    b = CallBudget(3)
    b.consume(kind="identity")
    b.consume(kind="operation")
    b.consume(kind="operation")
    with pytest.raises(M36Error) as e:
        b.consume(kind="operation")
    assert e.value.code == "call_budget_exhausted"


def test_completed_session_consumes_lease():
    res, leases, _, auth = _run()
    assert res["ok"]
    peek = leases.peek(res["session"]["lease_id"])
    assert peek["status"] == "REVOKED" or not peek["valid"]


def test_authorization_consumed_after_session():
    res, _, store, auth = _run()
    assert res["ok"]
    a = store.get(auth.authorization_id)
    assert a is not None
    assert a.status == "CONSUMED" or a.uses_remaining == 0


def test_unqualified_account_blocks():
    res, _, _, _ = _run(identity_qualification={"qualified": False, "classification": "REJECTED"})
    assert res["ok"] is False
    assert "identity" in res["reason"]


def test_cleanup_lease_revocation():
    res, leases, _, _ = _run()
    from saathi.credentials.m36 import M36Session
    sess = M36Session(
        session_id=res["session"]["session_id"],
        authorization_id=res["session"]["authorization_id"],
        provider_id="github_meta",
        account_ref_id=res["session"]["account_ref_id"],
        credential_ref_id=res["session"]["credential_ref_id"],
        operation="get_meta", endpoint="/meta", method="GET",
        environment_class="SANDBOX",
        lease_id=res["session"]["lease_id"],
    )
    out = attest_cleanup(sess, disposition=CleanupDisposition.LEASE_REVOKED.value, lease_store=leases)
    assert out["cleanup_disposition"] == "LEASE_REVOKED"


def test_silent_active_cleanup_fails():
    from saathi.credentials.m36 import M36Session
    sess = M36Session(
        session_id="s", authorization_id="a", provider_id="github_meta",
        account_ref_id="acct", credential_ref_id="cred",
        operation="get_meta", endpoint="/meta", method="GET", environment_class="SANDBOX",
    )
    with pytest.raises(M36Error) as e:
        attest_cleanup(sess, disposition=CleanupDisposition.SILENT_ACTIVE.value)
    assert e.value.code == "silent_active_credential_forbidden"


def test_eligibility_full_pass():
    ok, blockers = compose_m36_eligibility(
        production_certified=True, connector_certified=True, m30_drift_fresh=True,
        m31_credential_governance=True, m32_provider_adapter_verified=True,
        m33_external_profile_verified=True, m34_live_controls=True,
        m35_sandbox_governance=True, m36_authorization_valid=True,
        sandbox_identity_qualified=True, credential_healthy=True,
        credential_fingerprint_present=True, account_verified=True,
        scope_verified=True, approval_valid=True, lease_valid=True,
        call_budget_remaining=True, provider_healthy=True, quarantined=False,
        rollout_off=True, verification_only_exception=True,
    )
    assert ok is True
    assert blockers == []


@pytest.mark.parametrize("flag,code", [
    ("production_certified", "production_not_certified"),
    ("m36_authorization_valid", "m36_authorization_missing"),
    ("sandbox_identity_qualified", "identity_not_qualified"),
    ("call_budget_remaining", "call_budget_exhausted"),
    ("rollout_off", "rollout_not_off"),
])
def test_eligibility_blocks(flag, code):
    kw = dict(
        production_certified=True, connector_certified=True, m30_drift_fresh=True,
        m31_credential_governance=True, m32_provider_adapter_verified=True,
        m33_external_profile_verified=True, m34_live_controls=True,
        m35_sandbox_governance=True, m36_authorization_valid=True,
        sandbox_identity_qualified=True, credential_healthy=True,
        credential_fingerprint_present=True, account_verified=True,
        scope_verified=True, approval_valid=True, lease_valid=True,
        call_budget_remaining=True, provider_healthy=True, quarantined=False,
        rollout_off=True, verification_only_exception=True,
    )
    kw[flag] = False
    ok, blockers = compose_m36_eligibility(**kw)
    assert ok is False
    assert code in blockers


def test_quarantine_blocks_eligibility():
    ok, blockers = compose_m36_eligibility(
        production_certified=True, connector_certified=True, m30_drift_fresh=True,
        m31_credential_governance=True, m32_provider_adapter_verified=True,
        m33_external_profile_verified=True, m34_live_controls=True,
        m35_sandbox_governance=True, m36_authorization_valid=True,
        sandbox_identity_qualified=True, credential_healthy=True,
        credential_fingerprint_present=True, account_verified=True,
        scope_verified=True, approval_valid=True, lease_valid=True,
        call_budget_remaining=True, provider_healthy=True, quarantined=True,
        rollout_off=True, verification_only_exception=True,
    )
    assert ok is False
    assert "quarantined" in blockers


def test_verification_exception_session_specific():
    res, _, store, auth = _run()
    # cannot reuse authorization
    res2 = run_m36_session(
        authorization_store=store, authorization_id=auth.authorization_id,
        account_registry=SandboxAccountRegistry(clock=CLK),
        account_ref_id=res["session"]["account_ref_id"],
        broker=CredentialBroker(persist=False, clock=CLK),
        credential_ref_id=res["session"]["credential_ref_id"],
        lease_store=SessionLeaseStore(clock=CLK),
        secret_backend=InMemoryTestSecretBackend(),
        secret_locator="x",
        identity_qualification={"qualified": True, "classification": "DISPOSABLE_SANDBOX"},
        transport=_fixture_transport(), synthetic_offline=True, clock=CLK,
    )
    assert res2["ok"] is False


def test_rollout_remains_off():
    res, _, _, _ = _run()
    assert res["rollout_state"]["connector"] == "OFF"
    assert res["rollout_state"]["canary_providers"] == 0
    assert res["rollout_state"]["active_providers"] == 0


def test_no_secret_in_session_result():
    res, _, _, _ = _run()
    blob = json.dumps(res, default=str)
    assert SYNTH not in blob
    assert "Bearer " not in blob


def test_account_mismatch_quarantines():
    res, _, _, _ = _run(expected_subject_fingerprint="deadbeef" * 4)
    assert res["ok"] is False
    assert res["quarantine"]["active"] is True or "account_mismatch" in res["reason"]


def test_write_methods_blocked_offline():
    from saathi.credentials.m36 import assert_read_only_operation
    for m in ("POST", "PUT", "PATCH", "DELETE"):
        with pytest.raises(M36Error):
            assert_read_only_operation(m)
