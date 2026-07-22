"""M35 — Credential reference, secret-source, secret-handle, scope, ceiling security.

Every test is OFFLINE and synthetic: no network, no real secret source, no
Keychain, no real environment secret. Synthetic secrets are unmistakably fake.
"""
from __future__ import annotations

import json
import pickle

import pytest

from saathi.credentials import m35
from saathi.credentials.broker import CredentialBroker
from saathi.credentials.m35 import (
    CapabilityCeiling,
    EnvironmentClass,
    M35Error,
    M35ScopeClass,
    SecretHandle,
    SecretHandleError,
    SecretSourceKind,
    assert_environment_allowed,
    assert_scopes_allowed,
    ceiling_from_profile,
    classify_environment,
    classify_scope,
    intersect_ceilings,
    m35_secret_fingerprint,
    request_within_ceiling,
    scope_is_allowed,
    subject_fingerprint,
    validate_secret_source,
    verify_scope_evidence,
    ScopeVerificationState,
)
from saathi.connectors.providers.external.profiles import resolve_external_profile

SYNTH = "SYNTHETIC_SECRET_VALUE"
PROFILE = resolve_external_profile("github_meta")


def _broker():
    return CredentialBroker(persist=False, clock=lambda: 1000.0)


def _cred(broker, *, provider_id="github_meta", scopes=("metadata:read",), fields=None):
    return broker.create_reference(
        owner_scope="user:test", provider_id=provider_id, credential_type="api_key",
        secret_fields=fields or {"api_key": SYNTH}, scopes=scopes, connector_ids=("gov.http",),
    )


# ── environment classification ───────────────────────────────────────────────
@pytest.mark.parametrize("val,cls", [
    ("SYNTHETIC", "SYNTHETIC"), ("LOCAL_TEST", "LOCAL_TEST"), ("SANDBOX", "SANDBOX"),
    ("test", "LOCAL_TEST"), ("dev", "LOCAL_TEST"), ("sandbox", "SANDBOX"), ("prod", "PRODUCTION"),
])
def test_environment_classification(val, cls):
    assert classify_environment(val) == cls


def test_unknown_environment_fails():
    with pytest.raises(M35Error) as e:
        classify_environment("weird_env")
    assert e.value.code == "unknown_environment"


def test_synthetic_env_allowed():
    assert assert_environment_allowed("SYNTHETIC") == "SYNTHETIC"


def test_local_test_env_allowed():
    assert assert_environment_allowed("LOCAL_TEST") == "LOCAL_TEST"


def test_sandbox_env_allowed():
    assert assert_environment_allowed("SANDBOX") == "SANDBOX"


def test_production_env_fails_closed():
    with pytest.raises(M35Error) as e:
        assert_environment_allowed("PRODUCTION")
    assert e.value.code == "production_environment_forbidden"


def test_production_alias_fails_closed():
    for p in ("prod", "production", "live"):
        with pytest.raises(M35Error) as e:
            assert_environment_allowed(p)
        assert e.value.code == "production_environment_forbidden"


# ── credential reference ─────────────────────────────────────────────────────
def test_synthetic_reference_registers():
    b = _broker()
    ref = _cred(b)
    assert ref.provider_id == "github_meta"
    assert ref.status == "ACTIVE"


def test_reference_contains_no_secret_values():
    b = _broker()
    ref = _cred(b)
    d = ref.to_safe_dict()
    assert d["contains_secret_values"] is False
    assert "api_key" not in d  # only field NAMES recorded, under secret_fields_present
    assert "api_key" in ref.secret_fields_present


def test_reference_serialization_has_no_secret():
    b = _broker()
    ref = _cred(b)
    blob = json.dumps(ref.to_safe_dict()).lower()
    assert SYNTH.lower() not in blob


def test_prohibited_provider_reference_fails():
    b = _broker()
    with pytest.raises(Exception):
        b.create_reference(owner_scope="user:test", provider_id="binance_trade",
                           secret_fields={"api_key": SYNTH}, scopes=())


# ── secret source policy ─────────────────────────────────────────────────────
def test_in_memory_source_retrievable():
    r = validate_secret_source(SecretSourceKind.IN_MEMORY_TEST.value, want_retrieval=True)
    assert r["retrievable"] is True
    assert r["fallback_permitted"] is False


@pytest.mark.parametrize("kind", [
    SecretSourceKind.ENV_REFERENCE.value, SecretSourceKind.OS_KEYCHAIN_REFERENCE.value,
    SecretSourceKind.ENCRYPTED_STORE_REFERENCE.value, SecretSourceKind.EXTERNAL_SECRET_MANAGER_REFERENCE.value,
])
def test_other_sources_structural_only(kind):
    r = validate_secret_source(kind)
    assert r["structural_only"] is True
    assert r["retrievable"] is False


@pytest.mark.parametrize("kind", [
    SecretSourceKind.ENV_REFERENCE.value, SecretSourceKind.OS_KEYCHAIN_REFERENCE.value,
    SecretSourceKind.ENCRYPTED_STORE_REFERENCE.value, SecretSourceKind.EXTERNAL_SECRET_MANAGER_REFERENCE.value,
])
def test_non_retrievable_retrieval_fails(kind):
    with pytest.raises(M35Error) as e:
        validate_secret_source(kind, want_retrieval=True)
    assert e.value.code == "secret_source_not_retrievable"


@pytest.mark.parametrize("bad", [
    "PLAINTEXT", "REPOSITORY_FILE", "COMMAND_LINE_VALUE", "LOG_EMBEDDED",
    "EVIDENCE_EMBEDDED", "CALLER_RAW_SECRET",
])
def test_prohibited_sources_fail_closed(bad):
    with pytest.raises(M35Error) as e:
        validate_secret_source(bad)
    assert e.value.code == "prohibited_secret_source"


def test_unknown_source_fails():
    with pytest.raises(M35Error) as e:
        validate_secret_source("MADE_UP")
    assert e.value.code == "unknown_secret_source"


def test_no_fallback_declared():
    for s in SecretSourceKind:
        assert validate_secret_source(s.value)["fallback_permitted"] is False


# ── secret handle ────────────────────────────────────────────────────────────
def _handle():
    return SecretHandle({"api_key": SYNTH}, session_id="s1", lease_id="l1",
                        provider_id="github_meta", account_ref_id="a1")


def test_repr_redacted():
    assert SYNTH not in repr(_handle())


def test_str_redacted():
    assert SYNTH not in str(_handle())


def test_json_serialization_fails():
    with pytest.raises(TypeError):
        json.dumps(_handle())


def test_to_json_blocked():
    with pytest.raises(SecretHandleError):
        _handle().to_json()


def test_pickle_blocked():
    with pytest.raises((SecretHandleError, Exception)):
        pickle.dumps(_handle())


def test_leakscan_cannot_see_handle_secret():
    # a handle embedded in a structure exposes no secret bytes to the scanner
    assert m35.is_clean({"handle": repr(_handle())})


def test_use_requires_session():
    h = _handle()
    with pytest.raises(SecretHandleError) as e:
        h.use("api_key", lambda v: v, session_id="wrong")
    assert e.value.code == "session_mismatch"


def test_use_unknown_field():
    h = _handle()
    with pytest.raises(SecretHandleError) as e:
        h.use("nope", lambda v: v, session_id="s1")
    assert e.value.code == "unknown_field"


def test_use_exposes_only_via_consumer():
    h = _handle()
    seen = h.use("api_key", lambda v: v.upper(), session_id="s1")
    assert seen == SYNTH.upper()


def test_closed_handle_rejects_use():
    h = _handle()
    h.close()
    with pytest.raises(SecretHandleError) as e:
        h.use("api_key", lambda v: v, session_id="s1")
    assert e.value.code == "handle_closed"


def test_close_is_idempotent():
    h = _handle()
    h.close()
    h.close()  # no raise
    assert h.field_names == ()


def test_context_manager_closes():
    with _handle() as h:
        assert h.field_names == ("api_key",)
    with pytest.raises(SecretHandleError):
        h.use("api_key", lambda v: v, session_id="s1")


def test_zeroize_clears_buffer():
    h = _handle()
    buf = h._fields["api_key"]  # noqa: SLF001
    h.close()
    assert all(b == 0 for b in buf)


def test_equality_does_not_expose_secret():
    h = _handle()
    assert (h == SYNTH) is False
    assert (h == _handle()) is False
    assert h == h


def test_matches_fingerprint_without_exposing():
    h = _handle()
    fp = m35_secret_fingerprint({"api_key": SYNTH}, provider_id="github_meta", account_ref_id="a1")
    assert h.matches_fingerprint(fp, provider_id="github_meta", account_ref_id="a1", session_id="s1") is True
    assert h.matches_fingerprint("deadbeef", provider_id="github_meta", account_ref_id="a1", session_id="s1") is False


# ── fingerprinting ───────────────────────────────────────────────────────────
def test_same_secret_stable_fingerprint():
    a = m35_secret_fingerprint({"api_key": SYNTH}, provider_id="github_meta", account_ref_id="a1")
    b = m35_secret_fingerprint({"api_key": SYNTH}, provider_id="github_meta", account_ref_id="a1")
    assert a == b and a


def test_different_secret_different_fingerprint():
    a = m35_secret_fingerprint({"api_key": SYNTH}, provider_id="github_meta")
    b = m35_secret_fingerprint({"api_key": SYNTH + "2"}, provider_id="github_meta")
    assert a != b


def test_provider_binding_changes_fingerprint():
    a = m35_secret_fingerprint({"api_key": SYNTH}, provider_id="github_meta")
    b = m35_secret_fingerprint({"api_key": SYNTH}, provider_id="other")
    assert a != b


def test_account_binding_changes_fingerprint():
    a = m35_secret_fingerprint({"api_key": SYNTH}, provider_id="github_meta", account_ref_id="a1")
    b = m35_secret_fingerprint({"api_key": SYNTH}, provider_id="github_meta", account_ref_id="a2")
    assert a != b


def test_fingerprint_reveals_no_secret_or_affixes():
    fp = m35_secret_fingerprint({"api_key": SYNTH}, provider_id="github_meta")
    assert SYNTH not in fp
    assert SYNTH[:4] not in fp and SYNTH[-4:] not in fp


def test_fingerprint_fixed_width_no_length_leak():
    short = m35_secret_fingerprint({"api_key": "x"}, provider_id="github_meta")
    longv = m35_secret_fingerprint({"api_key": "x" * 500}, provider_id="github_meta")
    assert len(short) == len(longv) == 32


def test_fingerprint_absent_when_no_secret():
    assert m35_secret_fingerprint(None, provider_id="github_meta") == ""
    assert m35_secret_fingerprint({}, provider_id="github_meta") == ""
    assert m35_secret_fingerprint("", provider_id="github_meta") == ""


def test_fingerprint_cannot_authenticate():
    fp = m35_secret_fingerprint({"api_key": SYNTH}, provider_id="github_meta")
    # feeding the fingerprint back as the secret produces a different fingerprint
    assert m35_secret_fingerprint({"api_key": fp}, provider_id="github_meta") != fp


def test_subject_fingerprint_non_reversible():
    fp = subject_fingerprint("SYNTHETIC_ACCOUNT_SUBJECT", provider_id="github_meta")
    assert "SYNTHETIC_ACCOUNT_SUBJECT" not in fp and len(fp) == 32


# ── scope classes ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("scope", ["identity:read", "metadata:read", "public:read", "sandbox:read"])
def test_allowed_read_scopes(scope):
    assert scope_is_allowed(scope) is True


@pytest.mark.parametrize("scope", [
    "repo:write", "admin:all", "owner", "billing:read", "payment:send", "transfer_funds",
    "withdraw", "trade:execute", "order:write", "portfolio:control", "secret:read",
    "user_management", "email:send", "calendar:write", "social:publish", "cloud:admin",
])
def test_forbidden_scopes_fail(scope):
    assert scope_is_allowed(scope) is False


def test_unknown_scope_fails_closed():
    assert classify_scope("quux:frobnicate") == "UNKNOWN"
    assert scope_is_allowed("quux:frobnicate") is False


def test_assert_scopes_allowed_passes_reads():
    assert assert_scopes_allowed(("metadata:read", "public:read")) == ("metadata:read", "public:read")


def test_assert_scopes_rejects_unknown():
    with pytest.raises(M35Error) as e:
        assert_scopes_allowed(("metadata:read", "quux:xyz"))
    assert e.value.code == "unknown_scope"


def test_assert_scopes_rejects_forbidden():
    with pytest.raises(M35Error) as e:
        assert_scopes_allowed(("metadata:read", "repo:write"))
    assert e.value.code == "forbidden_scope"


# ── scope verification states ────────────────────────────────────────────────
def test_scope_declared_only_insufficient():
    state, _ = verify_scope_evidence(("metadata:read",), None)
    assert state == ScopeVerificationState.DECLARED.value


def test_scope_synthetic_verified():
    state, _ = verify_scope_evidence(("metadata:read",), None, synthetic=True)
    assert state == ScopeVerificationState.VERIFIED.value


def test_scope_observed_matches_verified():
    state, _ = verify_scope_evidence(("metadata:read",), ("metadata:read",))
    assert state == ScopeVerificationState.VERIFIED.value


def test_scope_observed_broadens_mismatched():
    state, _ = verify_scope_evidence(("metadata:read",), ("metadata:read", "public:read"))
    assert state == ScopeVerificationState.MISMATCHED.value


def test_scope_unknown_declared():
    state, _ = verify_scope_evidence(("quux:xyz",), ("quux:xyz",))
    assert state == ScopeVerificationState.UNKNOWN.value


# ── capability ceiling ───────────────────────────────────────────────────────
def _ceiling(scopes=("metadata:read",), env="SANDBOX"):
    return ceiling_from_profile(PROFILE, environment_class=env, allowed_scopes=scopes)


def test_ceiling_from_profile():
    c = _ceiling()
    assert c.provider_id == "github_meta" and c.operation == "get_meta" and c.method == "GET"
    assert c.data_classification == "PUBLIC"


def test_exact_subset_within_ceiling():
    ok, why = request_within_ceiling({
        "provider_id": "github_meta", "operation": "get_meta", "method": "GET",
        "scopes": ("metadata:read",),
    }, _ceiling())
    assert ok and why == "ok"


def test_provider_substitution_fails():
    ok, why = request_within_ceiling({"provider_id": "other", "operation": "get_meta", "method": "GET"}, _ceiling())
    assert not ok and why == "provider_substitution"


def test_operation_broadening_fails():
    ok, why = request_within_ceiling({"provider_id": "github_meta", "operation": "list_repos", "method": "GET"}, _ceiling())
    assert not ok and why == "operation_broadening"


def test_method_broadening_fails():
    ok, why = request_within_ceiling({"provider_id": "github_meta", "operation": "get_meta", "method": "POST"}, _ceiling())
    assert not ok and why in ("method_broadening", "write_method_blocked")


def test_write_method_blocked():
    ok, why = request_within_ceiling({"provider_id": "github_meta", "operation": "get_meta", "method": "DELETE"}, _ceiling())
    assert not ok


def test_scope_broadening_fails():
    ok, why = request_within_ceiling({
        "provider_id": "github_meta", "operation": "get_meta", "method": "GET",
        "scopes": ("metadata:read", "public:read"),
    }, _ceiling())
    assert not ok and why == "scope_broadening"


def test_data_classification_broadening_fails():
    ok, why = request_within_ceiling({
        "provider_id": "github_meta", "operation": "get_meta", "method": "GET",
        "data_classification": "CONFIDENTIAL",
    }, _ceiling())
    assert not ok and why == "data_classification_broadening"


def test_side_effect_escalation_fails():
    ok, why = request_within_ceiling({
        "provider_id": "github_meta", "operation": "get_meta", "method": "GET",
        "side_effect_class": "WRITE",
    }, _ceiling())
    assert not ok and why == "side_effect_escalation"


def test_intersect_ceilings_agrees():
    c = intersect_ceilings(_ceiling(("metadata:read", "public:read")), _ceiling(("metadata:read",)))
    assert set(c.allowed_scopes) == {"metadata:read"}


def test_intersect_ceilings_conflict():
    with pytest.raises(M35Error) as e:
        intersect_ceilings(_ceiling(env="SANDBOX"), _ceiling(env="LOCAL_TEST"))
    assert e.value.code == "ceiling_conflict"


def test_ceiling_rejects_production():
    with pytest.raises(M35Error):
        ceiling_from_profile(PROFILE, environment_class="PRODUCTION", allowed_scopes=("metadata:read",))
