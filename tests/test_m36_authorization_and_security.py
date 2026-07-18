"""M36 — Authorization, identity qualification, secret-source security (offline)."""
from __future__ import annotations

import pytest

from saathi.credentials.backends import InMemoryTestSecretBackend
from saathi.credentials.broker import CredentialBroker
from saathi.credentials.m35 import SandboxAccountRegistry, SessionLeaseStore, SecretHandle
from saathi.credentials import m36
from saathi.credentials.m36 import (
    M36Error,
    AuthorizationStore,
    M36_ACK_TOKENS,
    qualify_sandbox_identity,
    validate_m36_secret_reference,
    retrieve_secret_handle,
    m36_credential_fingerprint,
    reject_forbidden_cli_argv,
    m35_approval_cannot_authorize_m36,
    m36_cannot_authorize_m37,
)

CLK = lambda: 1_000_000.0
SYNTH = "SYNTHETIC_M36_SECRET_VALUE_NOT_REAL"
ALL_ACKS = tuple(M36_ACK_TOKENS)


def _auth_store(**kw):
    return AuthorizationStore(clock=CLK)


def _make_auth(store=None, **over):
    s = store or _auth_store()
    kw = dict(
        provider_id="github_meta",
        account_ref_id="acct_m36_001",
        credential_ref_id="cred_m36_001",
        operation="get_meta",
        endpoint="/meta",
        method="GET",
        environment_class="SANDBOX",
        approved_scopes=("identity:read", "metadata:read"),
        acknowledgements=ALL_ACKS,
        secret_source_kind="IN_MEMORY_TEST",
    )
    kw.update(over)
    return s, s.create(**kw)


# ── authorization ────────────────────────────────────────────────────────────
def test_valid_authorization_succeeds():
    _, a = _make_auth()
    assert a.milestone == "M36"
    assert a.status == "ACTIVE"
    assert a.provider_id == "github_meta"


def test_authorization_provider_specific():
    s, a = _make_auth()
    with pytest.raises(M36Error) as e:
        s.require_valid(a.authorization_id, provider_id="other", account_ref_id=a.account_ref_id,
                        credential_ref_id=a.credential_ref_id, operation=a.operation, endpoint=a.endpoint)
    assert e.value.code == "authorization_provider_mismatch"


def test_authorization_account_specific():
    s, a = _make_auth()
    with pytest.raises(M36Error) as e:
        s.require_valid(a.authorization_id, provider_id=a.provider_id, account_ref_id="wrong",
                        credential_ref_id=a.credential_ref_id, operation=a.operation, endpoint=a.endpoint)
    assert e.value.code == "authorization_account_mismatch"


def test_authorization_credential_specific():
    s, a = _make_auth()
    with pytest.raises(M36Error) as e:
        s.require_valid(a.authorization_id, provider_id=a.provider_id, account_ref_id=a.account_ref_id,
                        credential_ref_id="wrong", operation=a.operation, endpoint=a.endpoint)
    assert e.value.code == "authorization_credential_mismatch"


def test_authorization_operation_specific():
    s, a = _make_auth()
    with pytest.raises(M36Error) as e:
        s.require_valid(a.authorization_id, provider_id=a.provider_id, account_ref_id=a.account_ref_id,
                        credential_ref_id=a.credential_ref_id, operation="get_authenticated_user",
                        endpoint=a.endpoint)
    assert e.value.code == "authorization_operation_mismatch"


def test_authorization_endpoint_specific():
    s, a = _make_auth()
    with pytest.raises(M36Error) as e:
        s.require_valid(a.authorization_id, provider_id=a.provider_id, account_ref_id=a.account_ref_id,
                        credential_ref_id=a.credential_ref_id, operation=a.operation, endpoint="/user")
    assert e.value.code == "authorization_endpoint_mismatch"


def test_authorization_time_bounded():
    store = AuthorizationStore(clock=lambda: 100.0)
    a = store.create(
        provider_id="github_meta", account_ref_id="a", credential_ref_id="c",
        acknowledgements=ALL_ACKS, approved_duration=10.0,
    )
    store._clock = lambda: 200.0  # noqa: SLF001
    with pytest.raises(M36Error) as e:
        store.require_valid(a.authorization_id, provider_id="github_meta", account_ref_id="a",
                            credential_ref_id="c", operation="get_meta", endpoint="/meta")
    assert e.value.code == "authorization_expired"


def test_authorization_use_bounded():
    s, a = _make_auth()
    s.consume(a.authorization_id)
    with pytest.raises(M36Error) as e:
        s.require_valid(a.authorization_id, provider_id=a.provider_id, account_ref_id=a.account_ref_id,
                        credential_ref_id=a.credential_ref_id, operation=a.operation, endpoint=a.endpoint)
    assert e.value.code in ("authorization_consumed", "authorization_use_exhausted")


@pytest.mark.parametrize("missing", list(M36_ACK_TOKENS))
def test_missing_acknowledgement_fails(missing):
    acks = tuple(a for a in M36_ACK_TOKENS if a != missing)
    with pytest.raises(M36Error) as e:
        _make_auth(acknowledgements=acks)
    assert e.value.code == "missing_acknowledgement"
    assert missing in e.value.detail


def test_revoked_authorization_fails():
    s, a = _make_auth()
    s.revoke(a.authorization_id)
    with pytest.raises(M36Error) as e:
        s.require_valid(a.authorization_id, provider_id=a.provider_id, account_ref_id=a.account_ref_id,
                        credential_ref_id=a.credential_ref_id, operation=a.operation, endpoint=a.endpoint)
    assert e.value.code == "authorization_revoked"


def test_m35_approval_cannot_substitute():
    assert m35_approval_cannot_authorize_m36(object()) is True


def test_m36_cannot_authorize_m37():
    _, a = _make_auth()
    assert m36_cannot_authorize_m37(a) is True
    assert a.to_safe_dict()["m37_authorized"] is False


def test_authorization_safe_dict_no_secrets():
    _, a = _make_auth()
    d = a.to_safe_dict()
    assert d["contains_secret_values"] is False
    assert "token" not in str(d).lower() or "I_CONFIRM" in str(d)


def test_write_method_rejected_at_auth():
    with pytest.raises(M36Error) as e:
        _make_auth(method="POST")
    assert e.value.code in ("method_not_read_only", "write_method_blocked")


def test_production_env_rejected_at_auth():
    with pytest.raises(Exception):
        _make_auth(environment_class="PRODUCTION")


# ── identity qualification ───────────────────────────────────────────────────
def _qual(**over):
    kw = dict(
        provider_id="github_meta",
        account_alias="sbx-readonly-01",
        environment_class="SANDBOX",
        declared_purpose="m36 disposable sandbox verification",
        production_usage=False,
        contains_important_data=False,
        revocation_plan="manual_github_pat_delete",
        expiration_or_deletion_plan="delete_account_after_m36",
        account_kind="disposable_sandbox",
        operator_disposable_ack=True,
    )
    kw.update(over)
    return qualify_sandbox_identity(**kw)


def test_disposable_sandbox_qualifies():
    r = _qual()
    assert r["qualified"] is True
    assert r["classification"] == "DISPOSABLE_SANDBOX"


def test_production_identity_fails():
    r = _qual(environment_class="PRODUCTION")
    assert r["qualified"] is False


def test_personal_without_ack_fails():
    r = _qual(operator_disposable_ack=False)
    assert r["qualified"] is False
    assert "missing_disposable_operator_ack" in r["reasons"]


def test_unknown_environment_fails():
    r = _qual(environment_class="UNKNOWN_ENV_XYZ")
    assert r["qualified"] is False


@pytest.mark.parametrize("kind", ["financial", "trading", "payment", "cloud_admin", "personal"])
def test_forbidden_account_kinds(kind):
    r = _qual(account_kind=kind)
    assert r["qualified"] is False


def test_revocation_plan_required():
    r = _qual(revocation_plan="")
    assert r["qualified"] is False


def test_provider_mismatch_identity():
    r = _qual(provider_id="other_provider")
    assert r["qualified"] is False


def test_email_alias_rejected():
    r = _qual(account_alias="user@example.com")
    assert r["qualified"] is False


def test_raw_identity_not_in_qualification():
    r = _qual()
    assert r["contains_raw_identity"] is False
    assert "disclaimer" in r


# ── secret source ────────────────────────────────────────────────────────────
def test_keychain_reference_structural():
    r = validate_m36_secret_reference(source_kind="OS_KEYCHAIN_REFERENCE")
    assert r["source_kind"] == "OS_KEYCHAIN_REFERENCE"
    assert r["fallback_permitted"] is False


def test_env_reference_structural():
    r = validate_m36_secret_reference(source_kind="ENV_REFERENCE")
    assert r["arbitrary_env_scan"] is False


@pytest.mark.parametrize("cls", ["raw_token", "raw_api_key", "raw_password", "raw_secret", "cli_argument"])
def test_raw_locator_rejected(cls):
    with pytest.raises(M36Error) as e:
        validate_m36_secret_reference(source_kind="IN_MEMORY_TEST", locator_classification=cls)
    assert e.value.code == "raw_secret_argument_rejected"


def test_prohibited_source():
    with pytest.raises(M36Error):
        validate_m36_secret_reference(source_kind="PLAINTEXT")


def test_retrieval_without_authorization_fails():
    backend = InMemoryTestSecretBackend()
    backend.put("loc", {"api_key": SYNTH})
    s, a = _make_auth()
    a.status = "REVOKED"
    with pytest.raises(M36Error) as e:
        retrieve_secret_handle(
            backend=backend, locator="loc", authorization=a, lease_id="L1",
            session_id="S1", provider_id="github_meta", account_ref_id=a.account_ref_id,
        )
    assert e.value.code == "retrieval_without_valid_authorization"


def test_retrieval_without_lease_fails():
    backend = InMemoryTestSecretBackend()
    backend.put("loc", {"api_key": SYNTH})
    _, a = _make_auth()
    with pytest.raises(M36Error) as e:
        retrieve_secret_handle(
            backend=backend, locator="loc", authorization=a, lease_id="",
            session_id="S1", provider_id="github_meta", account_ref_id=a.account_ref_id,
        )
    assert e.value.code == "retrieval_without_lease"


def test_retrieval_provider_mismatch():
    backend = InMemoryTestSecretBackend()
    backend.put("loc", {"api_key": SYNTH})
    _, a = _make_auth()
    with pytest.raises(M36Error) as e:
        retrieve_secret_handle(
            backend=backend, locator="loc", authorization=a, lease_id="L1",
            session_id="S1", provider_id="other", account_ref_id=a.account_ref_id,
        )
    assert e.value.code == "retrieval_provider_mismatch"


def test_retrieval_account_mismatch():
    backend = InMemoryTestSecretBackend()
    backend.put("loc", {"api_key": SYNTH})
    _, a = _make_auth()
    with pytest.raises(M36Error) as e:
        retrieve_secret_handle(
            backend=backend, locator="loc", authorization=a, lease_id="L1",
            session_id="S1", provider_id="github_meta", account_ref_id="wrong",
        )
    assert e.value.code == "retrieval_account_mismatch"


def test_secret_handle_closes():
    backend = InMemoryTestSecretBackend()
    backend.put("loc", {"api_key": SYNTH})
    _, a = _make_auth()
    h = retrieve_secret_handle(
        backend=backend, locator="loc", authorization=a, lease_id="L1",
        session_id="S1", provider_id="github_meta", account_ref_id=a.account_ref_id,
    )
    h.close()
    with pytest.raises(Exception):
        h.use("api_key", lambda v: v, session_id="S1")


def test_secret_not_in_repr_or_events():
    backend = InMemoryTestSecretBackend()
    backend.put("loc", {"api_key": SYNTH})
    _, a = _make_auth()
    events = []
    h = retrieve_secret_handle(
        backend=backend, locator="loc", authorization=a, lease_id="L1",
        session_id="S1", provider_id="github_meta", account_ref_id=a.account_ref_id,
        events=events,
    )
    assert SYNTH not in repr(h)
    assert SYNTH not in str(events)
    h.close()


@pytest.mark.parametrize("flag", ["--token", "--api-key", "--password", "--secret", "--authorization-header"])
def test_cli_rejects_raw_secret_flags(flag):
    with pytest.raises(M36Error) as e:
        reject_forbidden_cli_argv([flag, "x"])
    assert e.value.code == "raw_secret_cli_rejected"


# ── fingerprint ──────────────────────────────────────────────────────────────
def test_fingerprint_domain_separated():
    fp1 = m36_credential_fingerprint(
        SYNTH, provider_id="github_meta", account_ref_id="a1",
        credential_type="api_key", environment_class="SANDBOX",
    )
    fp2 = m36_credential_fingerprint(
        SYNTH, provider_id="other", account_ref_id="a1",
        credential_type="api_key", environment_class="SANDBOX",
    )
    assert fp1 != fp2
    assert len(fp1) == 32
    assert SYNTH not in fp1
    assert not fp1.startswith(SYNTH[:4])


def test_fingerprint_account_bound():
    fp1 = m36_credential_fingerprint(
        SYNTH, provider_id="github_meta", account_ref_id="a1",
        credential_type="api_key", environment_class="SANDBOX",
    )
    fp2 = m36_credential_fingerprint(
        SYNTH, provider_id="github_meta", account_ref_id="a2",
        credential_type="api_key", environment_class="SANDBOX",
    )
    assert fp1 != fp2


def test_fingerprint_changes_after_rotation():
    fp1 = m36_credential_fingerprint(
        "secretA", provider_id="github_meta", account_ref_id="a1",
        credential_type="api_key", environment_class="SANDBOX",
    )
    fp2 = m36_credential_fingerprint(
        "secretB", provider_id="github_meta", account_ref_id="a1",
        credential_type="api_key", environment_class="SANDBOX",
    )
    assert fp1 != fp2


def test_fingerprint_alone_cannot_authorize():
    fp = m36_credential_fingerprint(
        SYNTH, provider_id="github_meta", account_ref_id="a1",
        credential_type="api_key", environment_class="SANDBOX",
    )
    # fingerprint is evidence, not an auth token — no API accepts it as secret
    assert isinstance(fp, str) and len(fp) == 32
    with pytest.raises(M36Error):
        _make_auth(acknowledgements=())  # still need real acks


def test_authorization_not_reusable_for_m37():
    _, a = _make_auth()
    d = a.to_safe_dict()
    assert d["milestone"] == "M36"
    assert d["m37_authorized"] is False
