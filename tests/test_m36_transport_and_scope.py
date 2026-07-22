"""M36 — Transport security, scope classification, call budget (offline)."""
from __future__ import annotations

import json

import pytest

from saathi.connectors.providers.external.endpoint_policy import EndpointPolicyError, validate_endpoint
from saathi.connectors.providers.external.testkit import (
    make_transport, public_resolver, private_resolver, rebinding_resolver,
    good_tls_prober, fixture_sender, raising_sender,
)
from saathi.connectors.providers.external.transport import SendContext
from saathi.connectors.providers.external.request_envelope import build_request_envelope
from saathi.credentials.m36 import (
    M36Error,
    CallBudget,
    classify_observed_scopes,
    parse_github_oauth_scopes,
    meta_operation_profile,
    identity_operation_profile,
    profile_for_operation,
    assert_read_only_operation,
    make_authenticated_sender,
    normalize_identity_response,
    normalize_meta_response,
    M36ScopeResult,
)
from saathi.credentials.m35 import SecretHandle, subject_fingerprint


def test_canonical_profiles_same_provider():
    meta = meta_operation_profile()
    ident = identity_operation_profile()
    assert meta.provider_id == ident.provider_id == "github_meta"
    assert "api.github.com" in meta.hostname_allowlist
    assert ident.canonical_path == "/user"
    assert meta.canonical_path == "/meta"


def test_unknown_operation_fails():
    with pytest.raises(M36Error):
        profile_for_operation("create_repo")


def test_http_rejected_by_endpoint_policy():
    p = meta_operation_profile()
    with pytest.raises(EndpointPolicyError):
        validate_endpoint("http://api.github.com/meta", p)


def test_unknown_host_rejected():
    p = meta_operation_profile()
    with pytest.raises(EndpointPolicyError):
        validate_endpoint("https://evil.example/meta", p)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_write_methods_rejected(method):
    with pytest.raises(M36Error):
        assert_read_only_operation(method)


def test_get_allowed():
    assert_read_only_operation("GET")


def test_private_address_blocked():
    tr = make_transport(sender=fixture_sender(body_bytes=b"{}"), resolver=private_resolver())
    p = meta_operation_profile()
    env = build_request_envelope(p, request_id="t1")
    res = tr.send(p, env)
    assert res.ok is False
    assert "SSRF" in res.failure_code or "DNS" in res.failure_code or res.failure_code


def test_rebinding_blocked():
    tr = make_transport(sender=fixture_sender(body_bytes=b"{}"), resolver=rebinding_resolver())
    p = meta_operation_profile()
    env = build_request_envelope(p, request_id="t1")
    res = tr.send(p, env)
    assert res.ok is False


def test_timeout_bounded():
    tr = make_transport(sender=raising_sender(TimeoutError("t")))
    p = meta_operation_profile()
    env = build_request_envelope(p, request_id="t1")
    res = tr.send(p, env)
    assert res.ok is False
    assert res.failure_code == "NETWORK_TIMEOUT"


def test_response_size_enforced_at_transport():
    big = b"x" * (300 * 1024)
    tr = make_transport(sender=fixture_sender(body_bytes=big))
    p = meta_operation_profile()
    env = build_request_envelope(p, request_id="t1")
    res = tr.send(p, env)
    assert res.ok is False
    assert res.failure_code == "RESPONSE_TOO_LARGE"


def test_auth_header_injected_only_in_sender():
    seen = {}

    def base(ctx: SendContext):
        seen["has_auth"] = "Authorization" in ctx.headers
        seen["auth_preview"] = "REDACTED" if "Authorization" in ctx.headers else None
        return {
            "status_code": 200, "headers": {"content-type": "application/json"},
            "body_bytes": b"{}", "content_type": "application/json",
            "location": "", "decompressed_size": 2,
        }

    handle = SecretHandle(
        {"api_key": "synth_token_value_xyz"},
        session_id="s1", lease_id="l1", provider_id="github_meta", account_ref_id="a1",
    )
    sender = make_authenticated_sender(base, handle, session_id="s1")
    ctx = SendContext(
        method="GET", url="https://api.github.com/user", host="api.github.com", port=443,
        pinned_ips=("140.82.112.3",), headers={"accept": "application/json"},
        timeout=5.0, response_limit=1024,
    )
    sender(ctx)
    assert seen["has_auth"] is True
    handle.close()


def test_envelope_has_no_authorization():
    p = identity_operation_profile()
    env = build_request_envelope(p, request_id="t1")
    assert "authorization" not in {k.lower() for k in env.safe_headers}


# ── scope ────────────────────────────────────────────────────────────────────
def test_parse_oauth_scopes():
    assert parse_github_oauth_scopes("read:user, repo") == ("read:user", "repo")


def test_read_only_observed_passes():
    r = classify_observed_scopes(("identity:read",), ("read:user",))
    assert r["result"] in (
        M36ScopeResult.VERIFIED_READ_ONLY.value,
        M36ScopeResult.VERIFIED_WITH_EXTRA_READ_SCOPE.value,
    )


def test_write_scope_fails():
    r = classify_observed_scopes(("identity:read",), ("repo",))
    assert r["result"] == M36ScopeResult.WRITE_SCOPE_PRESENT.value


def test_admin_scope_fails():
    r = classify_observed_scopes(("identity:read",), ("admin:org",))
    assert r["result"] == M36ScopeResult.WRITE_SCOPE_PRESENT.value


def test_workflow_scope_fails():
    r = classify_observed_scopes(("identity:read",), ("workflow",))
    assert r["result"] == M36ScopeResult.WRITE_SCOPE_PRESENT.value


def test_billing_scope_fails():
    r = classify_observed_scopes(("identity:read",), ("read:billing",))
    assert r["result"] == M36ScopeResult.WRITE_SCOPE_PRESENT.value


def test_unknown_scope_fails():
    r = classify_observed_scopes(("identity:read",), ("totally_unknown_material_scope_xyz",))
    assert r["result"] in (M36ScopeResult.UNKNOWN.value, M36ScopeResult.WRITE_SCOPE_PRESENT.value)


def test_missing_scope_metadata_not_verified():
    r = classify_observed_scopes(("identity:read",), None)
    assert r["result"] == M36ScopeResult.DECLARED_ONLY_UNOBSERVED.value
    assert r.get("honest_limitation") is True


def test_empty_oauth_scopes_public_readonly():
    r = classify_observed_scopes(("metadata:read",), ())
    assert r["result"] == M36ScopeResult.VERIFIED_READ_ONLY.value


def test_extra_read_scope_classified():
    r = classify_observed_scopes(("identity:read",), ("read:user", "read:org"))
    assert r["result"] in (
        M36ScopeResult.VERIFIED_WITH_EXTRA_READ_SCOPE.value,
        M36ScopeResult.VERIFIED_READ_ONLY.value,
    )


# ── call budget ──────────────────────────────────────────────────────────────
def test_call_budget_includes_retries():
    b = CallBudget(3)
    b.consume(kind="identity")
    b.consume(kind="operation", is_retry=True)
    assert b.retries == 1
    assert b.consumed == 2


def test_fourth_call_rejected():
    b = CallBudget(3)
    b.consume(); b.consume(); b.consume()
    with pytest.raises(M36Error) as e:
        b.consume()
    assert e.value.code == "call_budget_exhausted"


def test_budget_accounting_fields():
    b = CallBudget(3)
    b.consume(kind="identity")
    b.consume(kind="operation", is_redirect=True)
    d = b.to_dict()
    assert d["identity_calls"] == 1
    assert d["operation_calls"] == 1
    assert d["redirect_calls"] == 1
    assert d["writes"] == 0
    assert d["financial_calls"] == 0
    assert d["trading_calls"] == 0


# ── normalization ────────────────────────────────────────────────────────────
def test_normalize_identity_discards_personal():
    body = json.dumps({
        "id": 99, "login": "secretuser", "email": "a@b.com",
        "name": "Person", "avatar_url": "https://x/y.png",
    }).encode()
    exp = subject_fingerprint("99", provider_id="github_meta")
    n = normalize_identity_response(
        status_code=200, headers={"content-type": "application/json", "x-oauth-scopes": "read:user"},
        body_bytes=body, expected_subject_fingerprint=exp, provider_id="github_meta",
        transport_ok=True, tls={"verified": True}, latency_ms=100,
    )
    blob = json.dumps(n)
    assert "secretuser" not in blob
    assert "a@b.com" not in blob
    assert "Person" not in blob
    assert "avatar" not in blob
    assert n["account_match"] is True
    assert n["contains_raw_identity"] is False


def test_normalize_meta_no_raw_body():
    body = json.dumps({
        "verifiable_password_authentication": False,
        "hooks": ["1.2.3.0/24"], "pages": ["5.6.7.0/24"],
    }).encode()
    n = normalize_meta_response(
        status_code=200, body_bytes=body, content_type="application/json",
        latency_ms=50, transport_ok=True, tls={"verified": True},
    )
    assert n["schema_valid"] is True
    assert n["raw_body_persisted"] is False
    assert "1.2.3.0/24" not in json.dumps(n)
