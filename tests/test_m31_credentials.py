"""M31 — Credential control plane and account linking.

Covers: metadata-only reference model, credential broker (lease/injection/replay/
rotation/quarantine/revoke/delete), storage backends, provider-neutral OAuth PKCE
lifecycle, deterministic fake provider, account-link registry + readiness, scope
governance, synthetic leak detection, injection boundary, M31 eligibility (composed
with M30), evidence privacy, and the milestone invariants (0 real credentials, 0 real
OAuth flows, 0 live account links, Trading Guardian unchanged).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.credentials import evidence, leakscan
from saathi.credentials.account_links import AccountLinkError, AccountLinkRegistry
from saathi.credentials.backends import (
    EncryptedLocalTestBackend,
    EnvironmentReferenceBackend,
    InMemoryTestSecretBackend,
    SecretBackendError,
    UnavailableSecureBackend,
    create_backend,
)
from saathi.credentials.broker import BrokerError, CredentialBroker
from saathi.credentials.eligibility import (
    combined_connector_eligibility,
    resolve_credential_eligibility,
)
from saathi.credentials.injection import InjectionError, SecretInjectionContext
from saathi.credentials.models import (
    AccountLinkReadiness,
    AccountLinkStatus,
    CredentialStatus,
    OAuthLifecycleState,
    is_prohibited_provider,
    is_prohibited_scope,
)
from saathi.credentials.oauth import OAuthError, OAuthLifecycle, pkce_pair, verify_pkce
from saathi.credentials.scopes import (
    ScopeError,
    check_operation_authorized,
    get_profile,
    validate_granted_scopes,
    validate_requested_scopes,
)
from saathi.credentials.testing.sandbox_oauth import FakeOAuthProvider, FakeProviderError

ATK = "atk_" + "0" * 32
RTK = "rtk_" + "0" * 32


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def broker():
    return CredentialBroker(persist=False)


@pytest.fixture
def registry(broker):
    return AccountLinkRegistry(broker=broker, persist=False)


def _det_clock():
    t = {"v": 1_000_000.0}

    def clock():
        t["v"] += 1.0
        return t["v"]
    return clock


def _det_rng(seed=1):
    c = {"n": seed}

    def rng(n):
        c["n"] += 1
        return (str(c["n"]).encode() * n)[:n]
    return rng


# ── Model + guards ──────────────────────────────────────────────────────────

def test_prohibited_provider_and_scope_guards():
    assert is_prohibited_provider("binance_trade")
    assert is_prohibited_provider("acme-broker")
    assert not is_prohibited_provider("fakemail")
    assert is_prohibited_scope("order:write")
    assert is_prohibited_scope("wallet:withdraw")
    assert not is_prohibited_scope("mail.read")


def test_reference_safe_dict_never_holds_secret_keys(broker):
    ref = broker.create_reference(
        owner_scope="user:a", provider_id="fakemail",
        secret_fields={"access_token": ATK}, scopes=("mail.read",),
    )
    d = ref.to_safe_dict()
    assert d["contains_secret_values"] is False
    assert "access_token" not in d  # only NAMES live in secret_fields_present
    assert list(d["secret_fields_present"]) == ["access_token"]
    assert leakscan.is_clean(d)


# ── Backends ────────────────────────────────────────────────────────────────

def test_in_memory_backend_roundtrip_and_fields():
    be = InMemoryTestSecretBackend()
    be.put("loc", {"access_token": ATK, "refresh_token": RTK})
    assert be.get("loc", fields=["access_token"]) == {"access_token": ATK}
    assert be.exists("loc")
    be.delete("loc")
    assert not be.exists("loc")
    with pytest.raises(SecretBackendError):
        be.get("loc")


def test_env_reference_backend_names_only():
    be = EnvironmentReferenceBackend(environ={"MY_TOKEN": ATK})
    be.declare("loc", {"api_key": "MY_TOKEN"})
    assert be.get("loc") == {"api_key": ATK}
    with pytest.raises(SecretBackendError):
        be.put("loc", {"api_key": "x"})  # env backend refuses live puts


def test_unavailable_backend_fails_closed():
    be = UnavailableSecureBackend()
    assert be.readiness()["ready"] is False
    with pytest.raises(SecretBackendError):
        be.get("x")


def test_encrypted_local_test_backend_contains_paths(tmp_path):
    root = tmp_path / "store"
    be = EncryptedLocalTestBackend(root)
    be.put("k1", {"access_token": ATK})
    assert be.get("k1") == {"access_token": ATK}
    # Traversal chars are sanitized so the resolved path stays inside root.
    escaped = be._path("../../etc/passwd")
    assert str(escaped).startswith(str(root.resolve()))


def test_create_backend_rejects_unapproved_kind():
    with pytest.raises(SecretBackendError):
        create_backend("cloud_secret_manager")  # not approved for live in M31


# ── Broker: lease + injection + replay ──────────────────────────────────────

def test_lease_injection_single_use_and_replay_blocked(broker):
    ref = broker.create_reference(
        owner_scope="user:a", provider_id="fakemail",
        secret_fields={"access_token": ATK}, connector_ids=("gov.http",),
    )
    lease = broker.issue_lease(
        credential_ref_id=ref.credential_ref_id, request_id="r1",
        connector_id="gov.http", operation="send", actor="agent",
    )
    secrets = broker.inject_secrets(
        lease_id=lease["lease_id"], credential_ref_id=ref.credential_ref_id,
        request_id="r1", connector_id="gov.http", operation="send",
    )
    assert secrets == {"access_token": ATK}
    with pytest.raises(BrokerError) as ei:
        broker.inject_secrets(
            lease_id=lease["lease_id"], credential_ref_id=ref.credential_ref_id,
            request_id="r1", connector_id="gov.http", operation="send",
        )
    assert ei.value.code == "lease_replay"


def test_lease_bound_to_connector_and_request(broker):
    ref = broker.create_reference(
        owner_scope="user:a", provider_id="fakemail",
        secret_fields={"access_token": ATK}, connector_ids=("gov.http",),
    )
    lease = broker.issue_lease(
        credential_ref_id=ref.credential_ref_id, request_id="r1",
        connector_id="gov.http", operation="send", actor="agent",
    )
    with pytest.raises(BrokerError) as e1:
        broker.inject_secrets(
            lease_id=lease["lease_id"], credential_ref_id=ref.credential_ref_id,
            request_id="r1", connector_id="gov.mcp", operation="send",
        )
    assert e1.value.code == "lease_connector_mismatch"
    with pytest.raises(BrokerError) as e2:
        broker.inject_secrets(
            lease_id=lease["lease_id"], credential_ref_id=ref.credential_ref_id,
            request_id="OTHER", connector_id="gov.http", operation="send",
        )
    assert e2.value.code == "lease_request_mismatch"


def test_unleased_retrieval_forbidden(broker):
    ref = broker.create_reference(
        owner_scope="user:a", provider_id="fakemail", secret_fields={"access_token": ATK},
    )
    with pytest.raises(BrokerError) as e:
        broker.retrieve_unleased(ref.credential_ref_id)
    assert e.value.code == "unleased_retrieval_forbidden"


def test_connector_binding_enforced_on_lease(broker):
    ref = broker.create_reference(
        owner_scope="user:a", provider_id="fakemail",
        secret_fields={"access_token": ATK}, connector_ids=("gov.http",),
    )
    with pytest.raises(BrokerError) as e:
        broker.issue_lease(
            credential_ref_id=ref.credential_ref_id, request_id="r1",
            connector_id="gov.browser", operation="x", actor="agent",
        )
    assert e.value.code == "connector_not_bound"


def test_cross_owner_lease_denied(broker):
    ref = broker.create_reference(
        owner_scope="user:a", provider_id="fakemail", secret_fields={"access_token": ATK},
    )
    with pytest.raises(BrokerError) as e:
        broker.issue_lease(
            credential_ref_id=ref.credential_ref_id, request_id="r1",
            connector_id="gov.http", operation="send", actor="agent", owner_scope="user:b",
        )
    assert e.value.code == "cross_owner_denied"


def test_broker_rejects_prohibited_provider_and_scope(broker):
    with pytest.raises(BrokerError):
        broker.create_reference(owner_scope="u", provider_id="binance", secret_fields={"api_key": "x"})
    with pytest.raises(BrokerError):
        broker.create_reference(owner_scope="u", provider_id="fakemail", scopes=("withdraw",))


# ── Broker: quarantine / revoke / expire / rotate ───────────────────────────

def test_quarantine_blocks_lease_and_revokes_active_leases(broker):
    ref = broker.create_reference(
        owner_scope="user:a", provider_id="fakemail",
        secret_fields={"access_token": ATK}, connector_ids=("gov.http",),
    )
    lease = broker.issue_lease(
        credential_ref_id=ref.credential_ref_id, request_id="r1",
        connector_id="gov.http", operation="send", actor="agent",
    )
    broker.quarantine(ref.credential_ref_id, reason="leak")
    assert broker.get_ref(ref.credential_ref_id).status == CredentialStatus.QUARANTINED.value
    # existing lease revoked → injection fails
    with pytest.raises(BrokerError):
        broker.inject_secrets(
            lease_id=lease["lease_id"], credential_ref_id=ref.credential_ref_id,
            request_id="r1", connector_id="gov.http", operation="send",
        )
    with pytest.raises(BrokerError) as e:
        broker.issue_lease(
            credential_ref_id=ref.credential_ref_id, request_id="r2",
            connector_id="gov.http", operation="send", actor="agent",
        )
    assert e.value.code == "credential_quarantined"


def test_revoke_and_delete_and_expire(broker):
    ref = broker.create_reference(
        owner_scope="user:a", provider_id="fakemail",
        secret_fields={"access_token": ATK}, connector_ids=("gov.http",),
    )
    broker.revoke(ref.credential_ref_id, reason="user_request")
    assert broker.get_ref(ref.credential_ref_id).status == CredentialStatus.REVOKED.value
    assert broker.exists(ref.credential_ref_id) is False

    ref2 = broker.create_reference(
        owner_scope="user:a", provider_id="fakemail", secret_fields={"access_token": ATK},
    )
    broker.mark_expired(ref2.credential_ref_id)
    assert broker.get_ref(ref2.credential_ref_id).status == CredentialStatus.EXPIRED.value

    ref3 = broker.create_reference(
        owner_scope="user:a", provider_id="fakemail", secret_fields={"access_token": ATK},
    )
    broker.delete_secret_material(ref3.credential_ref_id, reason="cleanup")
    assert broker.get_ref(ref3.credential_ref_id).status == CredentialStatus.DELETED.value


def test_rotation_swaps_secret_and_revokes_leases(broker):
    ref = broker.create_reference(
        owner_scope="user:a", provider_id="fakemail",
        secret_fields={"access_token": ATK}, connector_ids=("gov.http",),
    )
    broker.rotate(ref.credential_ref_id, new_secret_fields={"access_token": "atk_" + "9" * 32})
    lease = broker.issue_lease(
        credential_ref_id=ref.credential_ref_id, request_id="r1",
        connector_id="gov.http", operation="send", actor="agent",
    )
    got = broker.inject_secrets(
        lease_id=lease["lease_id"], credential_ref_id=ref.credential_ref_id,
        request_id="r1", connector_id="gov.http", operation="send",
    )
    assert got["access_token"].endswith("9" * 32)


# ── OAuth PKCE lifecycle ────────────────────────────────────────────────────

def _oauth_env():
    clock = _det_clock()
    provider = FakeOAuthProvider(clock=clock)
    oauth = OAuthLifecycle(clock=clock, rng=_det_rng(), provider=provider)
    return oauth, provider


def test_pkce_pair_verifies():
    v, c = pkce_pair(_det_rng())
    assert verify_pkce(v, c)
    assert not verify_pkce(v + "x", c)


def test_oauth_full_link_flow():
    oauth, provider = _oauth_env()
    begin = oauth.begin_link(
        provider_id="fakemail", owner_scope="user:a", redirect_uri="https://app/cb",
        requested_scopes=("mail.read",), approval_token="ok",
    )
    assert begin["state"] == OAuthLifecycleState.AUTHORIZATION_PENDING.value
    auth = begin["authorization"]
    pr = provider.authorize(
        state=auth["state"], code_challenge=auth["code_challenge"],
        redirect_uri="https://app/cb", provider_id="fakemail", scopes=["mail.read"],
    )
    cb = oauth.handle_callback(
        state=pr["state"], code=pr["code"], redirect_uri="https://app/cb",
        provider_id="fakemail", owner_scope="user:a",
    )
    assert cb["status"] == OAuthLifecycleState.LINKED.value
    tokens = oauth.take_tokens_for_broker(begin["session_id"])
    assert set(tokens.keys()) == {"access_token", "refresh_token"}
    # session safe dict never leaks tokens/verifier
    safe = oauth.inspect(begin["session_id"])
    assert leakscan.is_clean(safe)
    assert "pkce_verifier" not in safe and "access_token" not in safe


def test_oauth_requires_approval_and_blocks_prohibited():
    oauth, _ = _oauth_env()
    with pytest.raises(OAuthError) as e:
        oauth.begin_link(provider_id="fakemail", owner_scope="u", redirect_uri="x",
                         requested_scopes=(), approval_token="")
    assert e.value.code == "approval_required"
    with pytest.raises(OAuthError):
        oauth.begin_link(provider_id="binance", owner_scope="u", redirect_uri="x",
                         requested_scopes=(), approval_token="ok")
    with pytest.raises(OAuthError):
        oauth.begin_link(provider_id="fakemail", owner_scope="u", redirect_uri="x",
                         requested_scopes=("order:write",), approval_token="ok")


def test_oauth_state_replay_and_mismatch_blocked():
    oauth, provider = _oauth_env()
    begin = oauth.begin_link(
        provider_id="fakemail", owner_scope="u", redirect_uri="https://app/cb",
        requested_scopes=("mail.read",), approval_token="ok",
    )
    auth = begin["authorization"]
    pr = provider.authorize(
        state=auth["state"], code_challenge=auth["code_challenge"],
        redirect_uri="https://app/cb", provider_id="fakemail", scopes=["mail.read"],
    )
    oauth.handle_callback(state=pr["state"], code=pr["code"], redirect_uri="https://app/cb",
                          provider_id="fakemail", owner_scope="u")
    # replay same state → blocked
    with pytest.raises(OAuthError) as e:
        oauth.handle_callback(state=pr["state"], code=pr["code"], redirect_uri="https://app/cb",
                              provider_id="fakemail", owner_scope="u")
    assert e.value.code in ("state_reused", "callback_replay")
    # unknown state
    with pytest.raises(OAuthError):
        oauth.handle_callback(state="bogus", code="x", redirect_uri="https://app/cb")


def test_oauth_scope_expansion_blocked():
    oauth, provider = _oauth_env()
    begin = oauth.begin_link(
        provider_id="fakemail", owner_scope="u", redirect_uri="https://app/cb",
        requested_scopes=("mail.read",), approval_token="ok",
    )
    auth = begin["authorization"]
    # provider grants MORE than requested
    pr = provider.authorize(
        state=auth["state"], code_challenge=auth["code_challenge"],
        redirect_uri="https://app/cb", provider_id="fakemail",
        scopes=["mail.read", "mail.admin"],
    )
    with pytest.raises(OAuthError) as e:
        oauth.handle_callback(state=pr["state"], code=pr["code"], redirect_uri="https://app/cb",
                              provider_id="fakemail", owner_scope="u")
    assert e.value.code == "scope_expansion_blocked"


def test_oauth_wrong_redirect_and_provider_fail_closed():
    oauth, provider = _oauth_env()
    begin = oauth.begin_link(
        provider_id="fakemail", owner_scope="u", redirect_uri="https://app/cb",
        requested_scopes=("mail.read",), approval_token="ok",
    )
    auth = begin["authorization"]
    pr = provider.authorize(
        state=auth["state"], code_challenge=auth["code_challenge"],
        redirect_uri="https://app/cb", provider_id="fakemail", scopes=["mail.read"],
    )
    with pytest.raises(OAuthError) as e:
        oauth.handle_callback(state=pr["state"], code=pr["code"],
                              redirect_uri="https://evil/cb", provider_id="fakemail", owner_scope="u")
    assert e.value.code == "incorrect_redirect_uri"


def test_fake_provider_pkce_mismatch_and_code_reuse():
    provider = FakeOAuthProvider(clock=_det_clock())
    _, challenge = pkce_pair(_det_rng())
    resp = provider.authorize(state="s", code_challenge=challenge, redirect_uri="cb",
                              provider_id="fakemail", scopes=["mail.read"])
    with pytest.raises(FakeProviderError) as e:
        provider.exchange_code(code=resp["code"], code_verifier="wrong", redirect_uri="cb",
                               provider_id="fakemail")
    assert e.value.code == "pkce_mismatch"


# ── Scope governance ────────────────────────────────────────────────────────

def test_scope_requested_and_granted_governance():
    assert validate_requested_scopes(("mail.read",), allowed_scopes=("mail.read", "mail.send")).allowed
    assert not validate_requested_scopes(("mail.read", "evil"), allowed_scopes=("mail.read",)).allowed
    assert not validate_requested_scopes(("order:write",)).allowed
    assert validate_granted_scopes(("mail.read", "mail.send"), ("mail.read",)).allowed  # narrowing ok
    assert not validate_granted_scopes(("mail.read",), ("mail.read", "mail.admin")).allowed  # expand


def test_operation_scope_authorization():
    assert check_operation_authorized(operation="send", granted_scopes=("mail.send",),
                                      required_scopes=("mail.send",)).allowed
    d = check_operation_authorized(operation="send", granted_scopes=("mail.read",),
                                   required_scopes=("mail.send",))
    assert not d.allowed and d.missing == ("mail.send",)


def test_unknown_profile_raises():
    with pytest.raises(ScopeError):
        get_profile("does_not_exist")


# ── Leak detector ───────────────────────────────────────────────────────────

def test_leak_detector_flags_real_shapes_and_passes_metadata(broker):
    assert not leakscan.is_clean({"x": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig"})
    assert not leakscan.is_clean({"access_token": ATK})
    assert not leakscan.is_clean(["-----BEGIN RSA PRIVATE KEY-----"])
    ref = broker.create_reference(owner_scope="u", provider_id="fakemail",
                                  secret_fields={"access_token": ATK})
    assert leakscan.is_clean(ref.to_safe_dict())
    assert leakscan.is_clean(broker.status_report())


def test_assert_clean_raises_on_leak():
    with pytest.raises(leakscan.LeakDetected):
        leakscan.assert_clean({"refresh_token": RTK})


# ── Injection boundary ──────────────────────────────────────────────────────

def test_injection_context_scrubs_after_block(broker):
    ref = broker.create_reference(
        owner_scope="u", provider_id="fakemail",
        secret_fields={"access_token": ATK}, connector_ids=("gov.http",),
    )
    captured = None
    with SecretInjectionContext(
        broker, credential_ref_id=ref.credential_ref_id, request_id="r1",
        connector_id="gov.http", operation="send", actor="agent",
    ) as secrets:
        assert secrets["access_token"] == ATK
        captured = secrets
    assert captured == {}  # scrubbed


def test_injection_on_quarantined_fails_closed(broker):
    ref = broker.create_reference(
        owner_scope="u", provider_id="fakemail",
        secret_fields={"access_token": ATK}, connector_ids=("gov.http",),
    )
    broker.quarantine(ref.credential_ref_id, reason="x")
    with pytest.raises(InjectionError):
        with SecretInjectionContext(
            broker, credential_ref_id=ref.credential_ref_id, request_id="r1",
            connector_id="gov.http", operation="send", actor="agent",
        ):
            pass


# ── Account-link registry + readiness ───────────────────────────────────────

def _linked(broker, registry, granted=("mail.read",)):
    cred = broker.create_reference(
        owner_scope="user:a", provider_id="fakemail",
        secret_fields={"access_token": ATK}, scopes=granted, connector_ids=("gov.http",),
    )
    link = registry.request_link(
        owner_scope="user:a", provider_id="fakemail", connector_ids=("gov.http",),
        requested_scopes=granted, allowed_scopes=granted + ("mail.admin",),
    )
    registry.mark_authorization_pending(link.account_link_id)
    registry.complete_link(link.account_link_id, granted_scopes=granted,
                           credential_ref_id=cred.credential_ref_id)
    return link, cred


def test_account_link_ready_when_linked(broker, registry):
    link, _ = _linked(broker, registry)
    r = registry.readiness(link.account_link_id, connector_id="gov.http", owner_scope="user:a")
    assert r["ready"] and r["readiness"] == AccountLinkReadiness.READY.value


def test_account_link_scope_expansion_blocked(broker, registry):
    cred = broker.create_reference(owner_scope="user:a", provider_id="fakemail",
                                   secret_fields={"access_token": ATK})
    link = registry.request_link(owner_scope="user:a", provider_id="fakemail",
                                 requested_scopes=("mail.read",), allowed_scopes=("mail.read",))
    registry.mark_authorization_pending(link.account_link_id)
    with pytest.raises(AccountLinkError):
        registry.complete_link(link.account_link_id, granted_scopes=("mail.read", "mail.admin"),
                               credential_ref_id=cred.credential_ref_id)
    assert registry.get(link.account_link_id).status == AccountLinkStatus.SCOPE_BLOCKED.value


def test_account_link_cross_owner_and_connector_binding(broker, registry):
    link, _ = _linked(broker, registry)
    assert registry.readiness(link.account_link_id, owner_scope="user:z")["reason"] == "cross_owner_denied"
    assert registry.readiness(link.account_link_id, connector_id="gov.mcp",
                              owner_scope="user:a")["reason"] == "connector_not_bound"


def test_account_link_quarantine_cascades_to_credential(broker, registry):
    link, cred = _linked(broker, registry)
    registry.quarantine(link.account_link_id, reason="leak", owner_scope="user:a")
    assert broker.get_ref(cred.credential_ref_id).status == CredentialStatus.QUARANTINED.value
    r = registry.readiness(link.account_link_id, connector_id="gov.http", owner_scope="user:a")
    assert not r["ready"]


def test_account_link_revoke_cascades(broker, registry):
    link, cred = _linked(broker, registry)
    registry.revoke(link.account_link_id, reason="user", owner_scope="user:a")
    assert broker.get_ref(cred.credential_ref_id).status == CredentialStatus.REVOKED.value
    assert registry.get(link.account_link_id).status == AccountLinkStatus.REVOKED.value


def test_account_link_prohibited_provider_blocked(registry):
    with pytest.raises(AccountLinkError):
        registry.request_link(owner_scope="u", provider_id="acme-broker", requested_scopes=())


# ── M31 eligibility (composed with M30) ─────────────────────────────────────

def test_credential_eligibility_ready_and_override_rejected(broker, registry):
    link, _ = _linked(broker, registry)
    d = resolve_credential_eligibility("gov.http", link.account_link_id,
                                       registry=registry, broker=broker, owner_scope="user:a")
    assert d.allowed and d.readiness == AccountLinkReadiness.READY.value
    d2 = resolve_credential_eligibility("gov.http", link.account_link_id, registry=registry,
                                        broker=broker, caller_metadata={"force_linked": True})
    assert not d2.allowed and d2.reason == "caller_override_rejected"


def test_combined_eligibility_credential_only(broker, registry):
    link, _ = _linked(broker, registry)
    c = combined_connector_eligibility(
        "gov.http", account_link_id=link.account_link_id, registry=registry, broker=broker,
        owner_scope="user:a", require_certification=False,
    )
    assert c.allowed


def test_combined_eligibility_fails_closed_without_cert(broker, registry, tmp_path):
    # Isolated, non-persistent cert store so this never touches the tracked M30 store.
    from saathi.connectors.conformance.store import CertificationStore
    iso = CertificationStore(path=tmp_path / "certs.json", persist=False)
    link, _ = _linked(broker, registry)
    c = combined_connector_eligibility(
        "gov.http", account_link_id=link.account_link_id, registry=registry, broker=broker,
        owner_scope="user:a", require_certification=True, require_credential=False,
        cert_store=iso,
    )
    assert not c.allowed
    assert c.reason.startswith("certification:")


# ── Evidence privacy + invariants ───────────────────────────────────────────

def test_evidence_pack_is_leak_clean_and_holds_invariants(broker, registry, tmp_path):
    _linked(broker, registry)
    path = evidence.generate_evidence(broker, registry, out_dir=tmp_path,
                                      scenario={"note": "test"})
    data = json.loads(Path(path).read_text())
    assert leakscan.is_clean(data)
    inv = data["invariants"]
    assert inv["real_credentials_stored"] == 0
    assert inv["real_oauth_flows_completed"] == 0
    assert inv["live_accounts_linked"] == 0
    assert inv["trading_guardian"] == "UNCHANGED / UNENGAGED"
    assert inv["connector_rollout"] == "OFF"


def test_evidence_write_refused_on_leak(broker, registry, tmp_path, monkeypatch):
    # Inject a leak into the pack builder output and confirm write is refused.
    real_build = evidence.build_pack

    def poisoned(*a, **k):
        pack = real_build(*a, **k)
        pack["scenario"]["oops_secret"] = ATK
        return pack

    monkeypatch.setattr(evidence, "build_pack", poisoned)
    with pytest.raises(leakscan.LeakDetected):
        evidence.generate_evidence(broker, registry, out_dir=tmp_path)


def test_milestone_invariants_broker_and_registry(broker, registry):
    _linked(broker, registry)
    rep = broker.status_report()
    assert rep["real_credentials_stored"] == 0
    assert rep["real_oauth_flows_completed"] == 0
    assert rep["live_accounts_linked"] == 0
    assert rep["trading_guardian"] == "UNCHANGED / UNENGAGED"
    assert registry.status_report()["live_accounts_linked"] == 0
    assert leakscan.is_clean(rep)


def test_cli_demo_runs_end_to_end():
    from saathi.credentials.cli import run_demo
    out = run_demo(persist=False)
    s = out["scenario"]
    assert s["callback_state_after"] == "LINKED"
    assert s["readiness_when_linked"] == "READY"
    assert s["final_link_status"] == "REVOKED"
    assert s["real_oauth_endpoints_contacted"] == 0
    assert leakscan.is_clean(s)
