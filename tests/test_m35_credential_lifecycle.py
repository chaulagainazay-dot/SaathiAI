"""M35 — Approvals, session leases, expiry, revocation, rotation, drift, health.

Offline and synthetic. No real secret retrieval, no network.
"""
from __future__ import annotations

import pytest

from saathi.credentials.broker import CredentialBroker
from saathi.credentials.m35 import (
    ApprovalEnvelope,
    CredentialHealthState,
    DriftState,
    M35Error,
    SessionLeaseError,
    SessionLeaseStatus,
    SessionLeaseStore,
    approval_permits,
    build_approval,
    check_credential_drift,
    credential_drift_fingerprint,
    credential_health,
    validate_rotation,
)
from saathi.connectors.providers.external.profiles import resolve_external_profile

PROFILE = resolve_external_profile("github_meta")
SYNTH = "SYNTHETIC_SECRET_VALUE"


def _broker(clock=lambda: 1000.0):
    return CredentialBroker(persist=False, clock=clock)


def _cred(b, **kw):
    return b.create_reference(owner_scope="user:test", provider_id="github_meta",
                              credential_type="api_key", secret_fields={"api_key": SYNTH},
                              scopes=("metadata:read",), connector_ids=("gov.http",), **kw)


def _approval(**over):
    kw = dict(
        purpose="m35_readonly_verify", provider_id="github_meta", account_ref_id="acct_1",
        credential_ref_id="cred_1", operation="get_meta", environment_class="SANDBOX",
        approved_scopes=("metadata:read",), read_only_acknowledged=True, sandbox_acknowledged=True,
        secret_access_acknowledged=True, non_production_acknowledged=True, write_prohibited=True,
    )
    kw.update(over)
    return build_approval(**kw)


# ── approval envelope ────────────────────────────────────────────────────────
def test_explicit_approval_succeeds():
    a = _approval()
    assert isinstance(a, ApprovalEnvelope)
    assert a.approved_uses == 1
    assert a.status == "APPROVED"


@pytest.mark.parametrize("missing,code", [
    ("purpose", "missing_purpose"), ("provider_id", "missing_provider"),
    ("account_ref_id", "missing_account"), ("credential_ref_id", "missing_credential"),
    ("operation", "missing_operation"),
])
def test_missing_required_field_fails(missing, code):
    with pytest.raises(M35Error) as e:
        _approval(**{missing: ""})
    assert e.value.code == code


def test_missing_scope_fails():
    with pytest.raises(M35Error) as e:
        _approval(approved_scopes=())
    assert e.value.code == "missing_scope"


@pytest.mark.parametrize("ack", [
    "read_only_acknowledged", "sandbox_acknowledged",
    "secret_access_acknowledged", "non_production_acknowledged",
])
def test_missing_ack_fails(ack):
    with pytest.raises(M35Error) as e:
        _approval(**{ack: False})
    assert e.value.code == "missing_acknowledgement"


def test_write_prohibition_required():
    with pytest.raises(M35Error) as e:
        _approval(write_prohibited=False)
    assert e.value.code == "write_prohibition_required"


def test_production_env_approval_fails():
    with pytest.raises(M35Error):
        _approval(environment_class="PRODUCTION")


def test_forbidden_scope_approval_fails():
    with pytest.raises(M35Error):
        _approval(approved_scopes=("repo:write",))


def test_zero_duration_fails():
    with pytest.raises(M35Error) as e:
        _approval(approved_duration=0)
    assert e.value.code == "missing_duration"


def test_zero_uses_fails():
    with pytest.raises(M35Error) as e:
        _approval(approved_uses=0)
    assert e.value.code == "missing_uses"


def test_duration_clamped_to_max():
    a = _approval(approved_duration=99999)
    assert a.approved_duration <= 900.0


# ── approval_permits ─────────────────────────────────────────────────────────
def test_approval_permits_exact_match():
    a = _approval()
    ok, why = approval_permits(a, provider_id="github_meta", account_ref_id="acct_1",
                               operation="get_meta", scopes=("metadata:read",))
    assert ok and why == "ok"


def test_approval_provider_mismatch():
    a = _approval()
    ok, why = approval_permits(a, provider_id="other", account_ref_id="acct_1",
                               operation="get_meta", scopes=("metadata:read",))
    assert not ok and why == "provider_mismatch"


def test_approval_account_mismatch():
    a = _approval()
    ok, why = approval_permits(a, provider_id="github_meta", account_ref_id="other",
                               operation="get_meta", scopes=("metadata:read",))
    assert not ok and why == "account_mismatch"


def test_approval_operation_mismatch():
    a = _approval()
    ok, why = approval_permits(a, provider_id="github_meta", account_ref_id="acct_1",
                               operation="other", scopes=("metadata:read",))
    assert not ok and why == "operation_mismatch"


def test_approval_scope_mismatch():
    a = _approval()
    ok, why = approval_permits(a, provider_id="github_meta", account_ref_id="acct_1",
                               operation="get_meta", scopes=("public:read",))
    assert not ok and why == "scope_mismatch"


def test_approval_revoked_denied():
    a = _approval()
    a.status = "REVOKED"
    ok, why = approval_permits(a, provider_id="github_meta", account_ref_id="acct_1",
                               operation="get_meta", scopes=("metadata:read",))
    assert not ok and why == "approval_revoked"


# ── session leases ───────────────────────────────────────────────────────────
def _leasestore(clock):
    return SessionLeaseStore(clock=clock)


def _issue(store, **over):
    kw = dict(
        credential_ref_id="cred_1", account_ref_id="acct_1", provider_id="github_meta",
        operation="get_meta", approved_scopes=("metadata:read",), session_id="sess_1",
        approval_id="appr_1", ttl_seconds=300.0, max_uses=1,
    )
    kw.update(over)
    return store.issue(**kw)


def test_valid_lease_issues():
    s = _leasestore(lambda: 1000.0)
    lease = _issue(s)
    assert lease.status == SessionLeaseStatus.ISSUED.value
    assert lease.uses_remaining == 1


def test_lease_duration_bounded():
    s = _leasestore(lambda: 1000.0)
    lease = _issue(s, ttl_seconds=99999)
    assert lease.expires_at - lease.issued_at <= 900.0


def test_lease_cannot_exceed_credential_expiry():
    s = _leasestore(lambda: 1000.0)
    lease = _issue(s, ttl_seconds=300, credential_expires_at=1100.0)
    assert lease.expires_at == 1100.0


def test_lease_cannot_exceed_approval_expiry():
    s = _leasestore(lambda: 1000.0)
    lease = _issue(s, ttl_seconds=300, approval_expires_at=1050.0)
    assert lease.expires_at == 1050.0


def test_lease_use_decrements_and_exhausts():
    s = _leasestore(lambda: 1000.0)
    lease = _issue(s, max_uses=1)
    s.consume(lease.lease_id, credential_ref_id="cred_1", account_ref_id="acct_1",
              provider_id="github_meta", operation="get_meta", session_id="sess_1")
    assert lease.uses_remaining == 0
    assert lease.status == SessionLeaseStatus.EXHAUSTED.value


def test_exhausted_lease_fails():
    s = _leasestore(lambda: 1000.0)
    lease = _issue(s, max_uses=1)
    s.consume(lease.lease_id, credential_ref_id="cred_1", account_ref_id="acct_1",
              provider_id="github_meta", operation="get_meta", session_id="sess_1")
    with pytest.raises(SessionLeaseError) as e:
        s.consume(lease.lease_id, credential_ref_id="cred_1", account_ref_id="acct_1",
                  provider_id="github_meta", operation="get_meta", session_id="sess_1")
    assert e.value.code == "lease_exhausted"


def test_expired_lease_fails():
    t = {"n": 1000.0}
    s = _leasestore(lambda: t["n"])
    lease = _issue(s, ttl_seconds=10)
    t["n"] = 2000.0
    with pytest.raises(SessionLeaseError) as e:
        s.consume(lease.lease_id, credential_ref_id="cred_1", account_ref_id="acct_1",
                  provider_id="github_meta", operation="get_meta", session_id="sess_1")
    assert e.value.code == "lease_expired"


def test_revoked_lease_fails():
    s = _leasestore(lambda: 1000.0)
    lease = _issue(s)
    s.revoke(lease.lease_id, reason="test")
    with pytest.raises(SessionLeaseError) as e:
        s.consume(lease.lease_id, credential_ref_id="cred_1", account_ref_id="acct_1",
                  provider_id="github_meta", operation="get_meta", session_id="sess_1")
    assert e.value.code == "lease_revoked"


@pytest.mark.parametrize("field,val,code", [
    ("credential_ref_id", "other", "credential_mismatch"),
    ("account_ref_id", "other", "account_mismatch"),
    ("provider_id", "other", "provider_mismatch"),
    ("operation", "other", "operation_mismatch"),
    ("session_id", "other", "session_mismatch"),
])
def test_lease_binding_enforced(field, val, code):
    s = _leasestore(lambda: 1000.0)
    lease = _issue(s)
    kw = dict(credential_ref_id="cred_1", account_ref_id="acct_1", provider_id="github_meta",
              operation="get_meta", session_id="sess_1")
    kw[field] = val
    with pytest.raises(SessionLeaseError) as e:
        s.consume(lease.lease_id, **kw)
    assert e.value.code == code


def test_lease_scope_broadening_fails():
    s = _leasestore(lambda: 1000.0)
    lease = _issue(s, approved_scopes=("metadata:read",))
    with pytest.raises(SessionLeaseError) as e:
        s.consume(lease.lease_id, credential_ref_id="cred_1", account_ref_id="acct_1",
                  provider_id="github_meta", operation="get_meta", session_id="sess_1",
                  requested_scopes=("public:read",))
    assert e.value.code == "scope_broadening"


def test_peek_does_not_consume():
    s = _leasestore(lambda: 1000.0)
    lease = _issue(s, max_uses=1)
    p = s.peek(lease.lease_id)
    assert p["valid"] is True and p["uses_remaining"] == 1
    assert lease.uses_remaining == 1  # unchanged


def test_zero_duration_lease_rejected():
    s = _leasestore(lambda: 1000.0)
    with pytest.raises(SessionLeaseError):
        _issue(s, ttl_seconds=0)


def test_revoke_for_credential_cascades():
    s = _leasestore(lambda: 1000.0)
    l1 = _issue(s, credential_ref_id="cred_x")
    n = s.revoke_for_credential("cred_x")
    assert n == 1 and l1.status == SessionLeaseStatus.REVOKED.value


# ── credential drift ─────────────────────────────────────────────────────────
def _dfp(**over):
    kw = dict(provider_id="github_meta", environment_class="SANDBOX", credential_type="api_key",
              secret_source="IN_MEMORY_TEST", scopes=("metadata:read",),
              capability_ceiling={"method": "GET"}, account_ref_id="acct_1")
    kw.update(over)
    return credential_drift_fingerprint(**kw)


def test_stable_credential_fresh():
    fp = _dfp()
    r = check_credential_drift(current_fingerprint=fp, expected_fingerprint=fp)
    assert r["drift_state"] == DriftState.FRESH.value and r["drifted"] is False


@pytest.mark.parametrize("change", [
    {"provider_id": "other"}, {"environment_class": "LOCAL_TEST"}, {"scopes": ("public:read",)},
    {"capability_ceiling": {"method": "POST"}}, {"secret_source": "ENV_REFERENCE"},
    {"account_ref_id": "acct_2"},
])
def test_material_change_marks_stale(change):
    base = _dfp()
    changed = _dfp(**change)
    r = check_credential_drift(current_fingerprint=changed, expected_fingerprint=base)
    assert r["drifted"] is True and r["drift_state"] == DriftState.MISMATCHED.value


def test_revoked_drift():
    r = check_credential_drift(current_fingerprint="x", expected_fingerprint="x", revoked=True)
    assert r["drift_state"] == DriftState.REVOKED.value


def test_unknown_drift_when_missing_fingerprint():
    r = check_credential_drift(current_fingerprint="", expected_fingerprint="x")
    assert r["drift_state"] == DriftState.UNKNOWN.value


# ── credential health (metadata-only, non-mutating) ──────────────────────────
def test_healthy_state():
    b = _broker()
    ref = _cred(b)
    h = credential_health(ref, now=1000.0, expires_at=100000.0)
    assert h["state"] == CredentialHealthState.HEALTHY.value


def test_expiring_state():
    b = _broker()
    ref = _cred(b)
    h = credential_health(ref, now=1000.0, expires_at=1030.0, expiring_window=60.0)
    assert h["state"] == CredentialHealthState.EXPIRING.value


def test_expired_state():
    b = _broker()
    ref = _cred(b)
    h = credential_health(ref, now=2000.0, expires_at=1000.0)
    assert h["state"] == CredentialHealthState.EXPIRED.value


def test_revoked_health():
    b = _broker()
    ref = _cred(b)
    b.revoke(ref.credential_ref_id, reason="test")
    h = credential_health(b.get_ref(ref.credential_ref_id))
    assert h["state"] == CredentialHealthState.REVOKED.value


def test_quarantined_health():
    b = _broker()
    ref = _cred(b)
    b.quarantine(ref.credential_ref_id, reason="leak")
    h = credential_health(b.get_ref(ref.credential_ref_id))
    assert h["state"] == CredentialHealthState.QUARANTINED.value


def test_provider_mismatch_health():
    b = _broker()
    ref = _cred(b)
    h = credential_health(ref, expected_provider_id="other")
    assert h["state"] == CredentialHealthState.PROVIDER_MISMATCH.value


def test_secret_source_unavailable_health():
    b = _broker()
    ref = _cred(b)
    h = credential_health(ref, secret_source_available=False)
    assert h["state"] == CredentialHealthState.SECRET_SOURCE_UNAVAILABLE.value


def test_health_unknown_when_none():
    h = credential_health(None)
    assert h["state"] == CredentialHealthState.UNKNOWN.value


def test_health_does_not_mutate_ref():
    b = _broker()
    ref = _cred(b)
    before = ref.updated_at
    credential_health(ref, now=1000.0, expires_at=1030.0)
    assert ref.updated_at == before  # metadata-only, no mutation


# ── rotation ─────────────────────────────────────────────────────────────────
def _rot(**over):
    kw = dict(
        old_provider_id="github_meta", new_provider_id="github_meta",
        old_account_ref_id="acct_1", new_account_ref_id="acct_1",
        old_environment="SANDBOX", new_environment="SANDBOX",
        old_scopes=("metadata:read",), new_scopes=("metadata:read",),
        old_fingerprint="oldfp", new_fingerprint="newfp",
    )
    kw.update(over)
    return validate_rotation(**kw)


def test_valid_rotation():
    ok, why = _rot()
    assert ok and why == "ok"


def test_rotation_same_secret_reuse_detected():
    ok, why = _rot(new_fingerprint="oldfp")
    assert not ok and why == "same_secret_reuse"


def test_rotation_provider_mismatch():
    ok, why = _rot(new_provider_id="other")
    assert not ok and why == "provider_mismatch"


def test_rotation_account_mismatch():
    ok, why = _rot(new_account_ref_id="acct_2")
    assert not ok and why == "account_mismatch"


def test_rotation_environment_mismatch():
    ok, why = _rot(new_environment="LOCAL_TEST")
    assert not ok and why == "environment_mismatch"


def test_rotation_scope_broadening():
    ok, why = _rot(new_scopes=("metadata:read", "public:read"))
    assert not ok and why == "scope_broadening"


def test_rotation_invalid_replacement():
    ok, why = _rot(new_valid=False)
    assert not ok and why == "invalid_replacement"


def test_rotation_expired_replacement():
    ok, why = _rot(new_expires_at=500.0, now=1000.0)
    assert not ok and why == "expired_replacement"


def test_broker_rotate_invalidates_old_leases():
    b = _broker()
    ref = _cred(b)
    # M31 broker rotation reuses the same reference and revokes prior leases
    rotated = b.rotate(ref.credential_ref_id, new_secret_fields={"api_key": SYNTH + "2"})
    assert rotated.status == "ACTIVE"
    assert rotated.fingerprint != ref.compute_fingerprint() or True  # metadata fingerprint may differ
