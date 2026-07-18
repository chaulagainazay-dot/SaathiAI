"""M33 — External provider security: selection, endpoint policy, DNS/SSRF, TLS,
request/response boundaries, redirects, schema compatibility, fixtures.

Deterministic; injected transport/DNS/TLS only; NO network. Every external
behaviour is exercised offline.
"""
from __future__ import annotations

import dataclasses

import pytest

from saathi.connectors.providers.external.dns_ssrf import (
    DnsSsrfError,
    classify_address,
    is_public_address,
    resolve_and_validate,
)
from saathi.connectors.providers.external.endpoint_policy import (
    EndpointPolicyError,
    caller_attempts_endpoint_override,
    hostname_allowed,
    validate_endpoint,
    validate_redirect_target,
)
from saathi.connectors.providers.external.fixtures import (
    FixtureError,
    assert_fixture_clean,
    fixture_body,
    load_fixture,
    sanitize_fixture_body,
    scan_fixture,
)
from saathi.connectors.providers.external.models import (
    ExternalFailure,
    ExternalProfileError,
    M33_ALLOWED_METHODS,
    M33_FORBIDDEN_METHODS,
    validate_external_profile,
)
from saathi.connectors.providers.external.profiles import (
    GITHUB_META,
    GITHUB_META_SCHEMA,
    is_external_candidate,
    list_external_profiles,
    resolve_external_profile,
)
from saathi.connectors.providers.external.request_envelope import (
    RequestEnvelopeError,
    build_request_envelope,
)
from saathi.connectors.providers.external.response_envelope import (
    ResponseEnvelopeError,
    build_response_envelope,
)
from saathi.connectors.providers.external.schema import SchemaDrift, validate_schema
from saathi.connectors.providers.external.testkit import (
    empty_resolver,
    failing_resolver,
    fixture_sender,
    good_tls_prober,
    make_transport,
    mixed_resolver,
    private_resolver,
    public_resolver,
    raising_sender,
    rebinding_resolver,
    timeout_resolver,
    tls_prober,
)
from saathi.connectors.providers.external.tls_policy import (
    TlsPolicy,
    TlsPolicyError,
    TlsResult,
    classify_tls,
    safe_tls_metadata,
)

P = GITHUB_META


def _env():
    return build_request_envelope(P, request_id="t")


# ── Provider selection (1–10) ────────────────────────────────────────────────
def test_exactly_one_candidate_selected():
    assert list_external_profiles() == ["github_meta"]


def test_candidate_requires_documentation_reference():
    assert P.official_documentation_reference.startswith("https://docs.github.com")


def test_credential_free_read_only_provider_accepted():
    assert P.auth_profile == "none"
    validate_external_profile(P)  # no raise


def test_unofficial_endpoint_rejected_by_allowlist():
    with pytest.raises(EndpointPolicyError):
        validate_endpoint("https://evil.example.com/meta", P)


def test_write_capable_provider_rejected():
    for m in ("POST", "PUT", "PATCH", "DELETE"):
        bad = dataclasses.replace(P, method=m)
        with pytest.raises(ExternalProfileError):
            validate_external_profile(bad)


@pytest.mark.parametrize("pid", ["stripe_payment", "paypal_transfer", "my_bank_api"])
def test_financial_provider_rejected(pid):
    with pytest.raises(ExternalProfileError):
        resolve_external_profile(pid)


@pytest.mark.parametrize("pid", ["binance_trade", "coinbase_exchange", "ftx_order", "my_broker"])
def test_trading_provider_rejected(pid):
    with pytest.raises(ExternalProfileError):
        resolve_external_profile(pid)


@pytest.mark.parametrize("pid", ["facebook", "instagram", "youtube_publish", "linkedin_publish"])
def test_social_publishing_provider_rejected(pid):
    with pytest.raises(ExternalProfileError):
        resolve_external_profile(pid)


def test_personal_email_provider_rejected():
    with pytest.raises(ExternalProfileError):
        resolve_external_profile("gmail")


def test_unknown_terms_status_fails_closed():
    bad = dataclasses.replace(P, terms_review_status="UNCERTAIN")
    with pytest.raises(ExternalProfileError):
        validate_external_profile(bad)


# ── Endpoint policy (11–24) ───────────────────────────────────────────────────
def test_canonical_https_host_passes():
    host, port, path = validate_endpoint(P.endpoint_reference, P)
    assert (host, port) == ("api.github.com", 443)


def test_http_endpoint_fails():
    with pytest.raises(EndpointPolicyError):
        validate_endpoint("http://api.github.com/meta", P)


def test_arbitrary_hostname_fails():
    with pytest.raises(EndpointPolicyError):
        validate_endpoint("https://api.github.com.attacker.com/meta", P)


def test_wildcard_hostname_fails():
    assert not hostname_allowed("*.github.com", P)
    with pytest.raises(EndpointPolicyError):
        validate_endpoint("https://*.github.com/meta", P)


def test_caller_supplied_endpoint_fails():
    assert caller_attempts_endpoint_override({"url": "https://x"}) == "url"
    assert caller_attempts_endpoint_override({"endpoint": "x"}) == "endpoint"


def test_caller_supplied_port_fails():
    assert caller_attempts_endpoint_override({"port": 8080}) == "port"
    with pytest.raises(EndpointPolicyError):
        validate_endpoint("https://api.github.com:8443/meta", P)


def test_loopback_external_destination_fails():
    with pytest.raises(EndpointPolicyError):
        validate_endpoint("https://localhost/meta", P)


def test_private_ipv4_destination_fails():
    with pytest.raises(DnsSsrfError):
        resolve_and_validate("api.github.com", resolver=private_resolver(("10.0.0.9",)))


def test_private_ipv6_destination_fails():
    with pytest.raises(DnsSsrfError):
        resolve_and_validate("api.github.com", resolver=private_resolver(("fd00::1",)))


def test_link_local_destination_fails():
    with pytest.raises(DnsSsrfError):
        resolve_and_validate("api.github.com", resolver=private_resolver(("169.254.10.10",)))


def test_metadata_service_destination_fails():
    with pytest.raises(DnsSsrfError):
        resolve_and_validate("api.github.com", resolver=private_resolver(("169.254.169.254",)))


def test_reserved_destination_fails():
    assert classify_address("0.0.0.0") in ("unspecified", "reserved")
    with pytest.raises(DnsSsrfError):
        resolve_and_validate("api.github.com", resolver=private_resolver(("240.0.0.1",)))


def test_alternate_ip_override_fails():
    assert caller_attempts_endpoint_override({"ip": "1.2.3.4"}) == "ip"
    assert caller_attempts_endpoint_override({"address": "1.2.3.4"}) == "address"


def test_caller_supplied_proxy_fails():
    assert caller_attempts_endpoint_override({"proxy": "http://x"}) == "proxy"
    assert caller_attempts_endpoint_override({"https_proxy": "x"}) == "https_proxy"


# ── DNS & SSRF (25–34) ────────────────────────────────────────────────────────
def test_approved_public_dns_passes():
    assert resolve_and_validate("api.github.com", resolver=public_resolver()) == ["140.82.112.3"]


def test_private_dns_result_fails():
    with pytest.raises(DnsSsrfError):
        resolve_and_validate("api.github.com", resolver=private_resolver())


def test_mixed_public_private_fails_safe():
    with pytest.raises(DnsSsrfError):
        resolve_and_validate("api.github.com", resolver=mixed_resolver())


def test_dns_failure_classifies_safely():
    with pytest.raises(DnsSsrfError) as e:
        resolve_and_validate("api.github.com", resolver=failing_resolver())
    assert e.value.code == ExternalFailure.DNS_RESOLUTION_FAILED


def test_dns_timeout_classifies_safely():
    with pytest.raises(DnsSsrfError) as e:
        resolve_and_validate("api.github.com", resolver=timeout_resolver())
    assert e.value.code == ExternalFailure.NETWORK_TIMEOUT


def test_redirect_destination_is_revalidated():
    with pytest.raises(EndpointPolicyError):
        validate_redirect_target("https://evil.com/x", P)
    validate_redirect_target("https://api.github.com/other", P)  # host ok on redirect


def test_dns_rebinding_simulation_fails():
    with pytest.raises(DnsSsrfError):
        resolve_and_validate("api.github.com", resolver=rebinding_resolver())


def test_caller_cannot_set_host_header():
    with pytest.raises(RequestEnvelopeError):
        build_request_envelope(P, request_id="x", extra_headers={"host": "evil"})


def test_caller_cannot_set_sni():
    assert caller_attempts_endpoint_override({"sni": "evil"}) == "sni"


def test_encoded_internal_host_injection_fails():
    with pytest.raises(DnsSsrfError):
        resolve_and_validate("api.github.com", resolver=private_resolver(("127.0.0.1",)))


def test_empty_dns_fails():
    with pytest.raises(DnsSsrfError):
        resolve_and_validate("api.github.com", resolver=empty_resolver())


# ── TLS (35–43) ───────────────────────────────────────────────────────────────
def test_valid_certificate_passes():
    classify_tls(TlsResult(verified=True, hostname_match=True, protocol="TLSv1.3"), TlsPolicy())


def test_invalid_certificate_fails():
    with pytest.raises(TlsPolicyError) as e:
        classify_tls(TlsResult(verified=False), TlsPolicy())
    assert e.value.code == ExternalFailure.TLS_CERTIFICATE_FAILED


def test_expired_certificate_fails():
    with pytest.raises(TlsPolicyError):
        classify_tls(TlsResult(verified=True, expired=True), TlsPolicy())


def test_hostname_mismatch_fails():
    with pytest.raises(TlsPolicyError) as e:
        classify_tls(TlsResult(verified=True, hostname_match=False), TlsPolicy())
    assert e.value.code == ExternalFailure.TLS_HOSTNAME_FAILED


def test_verification_disabled_configuration_fails():
    with pytest.raises(TlsPolicyError):
        classify_tls(TlsResult(verified=True), TlsPolicy(allow_insecure=True))


def test_insecure_ssl_context_fails():
    with pytest.raises(TlsPolicyError):
        classify_tls(TlsResult(verified=True), TlsPolicy(require_verification=False))


def test_https_downgrade_fails():
    with pytest.raises(EndpointPolicyError) as e:
        validate_endpoint("http://api.github.com/meta", P)
    assert e.value.code == ExternalFailure.ENDPOINT_POLICY_BLOCKED


def test_tls_error_contains_no_secret():
    try:
        classify_tls(TlsResult(verified=False), TlsPolicy())
    except TlsPolicyError as e:
        s = str(e).lower()
        assert "token" not in s and "secret" not in s and "bearer" not in s


def test_tls_metadata_bounded():
    md = safe_tls_metadata(TlsResult(protocol="TLSv1.3"))
    assert md["privacy_safe"] and set(md) == {"protocol", "verified", "hostname_match", "privacy_safe"}


def test_low_tls_version_fails():
    with pytest.raises(TlsPolicyError):
        classify_tls(TlsResult(verified=True, protocol="TLSv1"), TlsPolicy())


# ── Request boundary (44–59) ──────────────────────────────────────────────────
def test_get_allowed():
    assert _env().method == "GET"


def test_head_allowed_only_when_declared():
    head = dataclasses.replace(P, method="HEAD")
    validate_external_profile(head)
    assert build_request_envelope(head, request_id="x").method == "HEAD"


@pytest.mark.parametrize("m", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"])
def test_write_methods_forbidden(m):
    assert m in M33_FORBIDDEN_METHODS and m not in M33_ALLOWED_METHODS
    with pytest.raises(ExternalProfileError):
        validate_external_profile(dataclasses.replace(P, method=m))


def test_arbitrary_path_and_traversal_fail():
    with pytest.raises(RequestEnvelopeError):
        build_request_envelope(dataclasses.replace(P, canonical_path="/meta/../secret"), request_id="x")


def test_encoded_path_traversal_fails():
    with pytest.raises(RequestEnvelopeError):
        build_request_envelope(dataclasses.replace(P, canonical_path="/%2e%2e/etc"), request_id="x")


def test_crlf_header_injection_fails():
    with pytest.raises(RequestEnvelopeError):
        build_request_envelope(P, request_id="x", extra_headers={"x-note": "a\r\nInjected: 1"})


def test_authorization_injection_fails():
    with pytest.raises(RequestEnvelopeError):
        build_request_envelope(P, request_id="x", extra_headers={"authorization": "Bearer x"})


def test_cookie_injection_fails():
    with pytest.raises(RequestEnvelopeError):
        build_request_envelope(P, request_id="x", extra_headers={"cookie": "s=1"})


def test_xforwarded_injection_fails():
    with pytest.raises(RequestEnvelopeError):
        build_request_envelope(P, request_id="x", extra_headers={"x-forwarded-for": "1.2.3.4"})


def test_query_amplification_fails():
    with pytest.raises(RequestEnvelopeError):
        build_request_envelope(P, request_id="x", query={f"k{i}": i for i in range(20)})


def test_unbounded_list_param_fails():
    with pytest.raises(RequestEnvelopeError):
        build_request_envelope(P, request_id="x", query={"a": [1, 2, 3]})


def test_oversized_request_field_fails():
    with pytest.raises(RequestEnvelopeError):
        build_request_envelope(P, request_id="x", query={"a": "y" * 5000})


# ── Response boundary (60–70) ─────────────────────────────────────────────────
def _raw(body=b'{"ok":true}', status=200, headers=None, ct="application/json", decompressed=None):
    return {
        "status_code": status, "headers": headers or {"content-type": ct},
        "body_bytes": body, "content_type": ct,
        "decompressed_size": len(body) if decompressed is None else decompressed,
    }


def test_valid_response_normalizes():
    r = build_response_envelope(_raw(), response_limit=1024)
    assert r.status_code == 200 and r.normalized_data


def test_oversized_response_fails():
    with pytest.raises(ResponseEnvelopeError) as e:
        build_response_envelope(_raw(body=b"x" * 2048), response_limit=1024)
    assert e.value.code == ExternalFailure.RESPONSE_TOO_LARGE


def test_oversized_decompressed_response_fails():
    with pytest.raises(ResponseEnvelopeError) as e:
        build_response_envelope(_raw(body=b"{}", decompressed=999999), response_limit=1024)
    assert e.value.code == ExternalFailure.DECOMPRESSION_LIMIT_EXCEEDED


def test_unsupported_content_type_fails():
    with pytest.raises(ResponseEnvelopeError) as e:
        build_response_envelope(_raw(ct="text/html"), response_limit=1024)
    assert e.value.code == ExternalFailure.UNSUPPORTED_CONTENT_TYPE


def test_malformed_encoding_fails():
    with pytest.raises(ResponseEnvelopeError):
        build_response_envelope(_raw(body=b"{not json"), response_limit=1024)


def test_cookie_and_auth_headers_removed():
    r = build_response_envelope(
        _raw(headers={"content-type": "application/json", "set-cookie": "s=1", "authorization": "Bearer x"}),
        response_limit=1024,
    )
    assert "set-cookie" not in r.safe_headers and "authorization" not in r.safe_headers


def test_raw_response_and_client_do_not_escape():
    r = build_response_envelope(_raw(), response_limit=1024)
    d = r.to_dict()
    assert "socket" not in d and "client" not in d


def test_unsafe_stack_trace_removed():
    r = build_response_envelope(
        _raw(body=b'{"ok":true,"traceback":"File x line 1 secret"}'), response_limit=1024,
    )
    assert "traceback" not in r.normalized_data


def test_provider_request_id_retained_when_safe():
    r = build_response_envelope(
        _raw(headers={"content-type": "application/json", "x-github-request-id": "REQ123"}),
        response_limit=1024,
    )
    assert r.provider_request_id_safe == "REQ123"


# ── Redirects (71–80) ─────────────────────────────────────────────────────────
def _send(profile, **kw):
    tr = make_transport(**{k: v for k, v in kw.items() if k in ("resolver", "tls_prober_fn", "sender")})
    return tr.send(profile, build_request_envelope(profile, request_id="x"))


def test_no_redirect_passes():
    body = b'{"verifiable_password_authentication":false,"hooks":["1.2.3.0/24"],"pages":["5.6.7.0/24"]}'
    r = _send(P, sender=fixture_sender(body_bytes=body))
    assert r.ok


def test_redirect_to_unknown_host_fails():
    one = dataclasses.replace(P, redirect_limit=1)
    r = _send(one, sender=fixture_sender(status=302, headers={"location": "https://evil.com/x"}, body_bytes=b""))
    assert r.failure_code == ExternalFailure.REDIRECT_POLICY_BLOCKED.value


def test_redirect_to_http_fails():
    one = dataclasses.replace(P, redirect_limit=1)
    r = _send(one, sender=fixture_sender(status=302, headers={"location": "http://api.github.com/x"}, body_bytes=b""))
    assert r.failure_code == ExternalFailure.REDIRECT_POLICY_BLOCKED.value


def test_redirect_ceiling_enforced_zero():
    r = _send(P, sender=fixture_sender(status=302, headers={"location": "https://api.github.com/x"}, body_bytes=b""))
    assert r.failure_code == ExternalFailure.REDIRECT_POLICY_BLOCKED.value


def test_redirect_loop_fails():
    one = dataclasses.replace(P, redirect_limit=2)
    r = _send(one, sender=fixture_sender(status=302, headers={"location": "https://api.github.com/meta"}, body_bytes=b""))
    assert r.failure_code == ExternalFailure.REDIRECT_POLICY_BLOCKED.value


def test_redirect_evidence_sanitized():
    r = _send(P, sender=fixture_sender(status=302, headers={"location": "https://api.github.com/x"}, body_bytes=b""))
    for hop in r.redirect_chain:
        assert set(hop) <= {"host", "status", "scheme"}


# ── Schema compatibility (81–90) ──────────────────────────────────────────────
_GOOD = {"verifiable_password_authentication": False, "hooks": ["1.2.3.0/24"], "pages": ["5.6.7.0/24"]}


def test_expected_schema_passes():
    assert validate_schema(_GOOD, GITHUB_META_SCHEMA).compatible


def test_additive_field_classified():
    res = validate_schema({**_GOOD, "new_thing": [1]}, GITHUB_META_SCHEMA)
    assert res.compatible and res.overall == SchemaDrift.COMPATIBLE_ADDITIVE.value


def test_missing_required_field_fails():
    res = validate_schema({"hooks": [], "pages": []}, GITHUB_META_SCHEMA)
    assert not res.compatible and res.overall == SchemaDrift.INCOMPATIBLE_MISSING_FIELD.value


def test_type_change_fails():
    res = validate_schema({**_GOOD, "hooks": "nope"}, GITHUB_META_SCHEMA)
    assert not res.compatible and res.overall == SchemaDrift.INCOMPATIBLE_TYPE_CHANGE.value


def test_enum_change_fails():
    from saathi.connectors.providers.external.schema import SchemaContract, SchemaField

    c = SchemaContract("x", "v1", (SchemaField("color", "string", required=True, enum=("red", "blue")),))
    res = validate_schema({"color": "green"}, c)
    assert not res.compatible and res.overall == SchemaDrift.INCOMPATIBLE_ENUM_CHANGE.value


def test_null_change_handled_safely():
    res = validate_schema({**_GOOD, "verifiable_password_authentication": None}, GITHUB_META_SCHEMA)
    assert not res.compatible


def test_oversized_array_fails():
    res = validate_schema({**_GOOD, "hooks": ["x"] * 20000}, GITHUB_META_SCHEMA)
    assert not res.compatible


def test_oversized_string_fails():
    from saathi.connectors.providers.external.schema import SchemaContract, SchemaField

    c = SchemaContract("x", "v1", (SchemaField("s", "string", required=True),))
    assert not validate_schema({"s": "y" * 99999}, c).compatible


def test_partial_response_not_full_success():
    # required field missing → never a success
    assert not validate_schema({"pages": ["1.2.3.0/24"]}, GITHUB_META_SCHEMA).compatible


def test_unknown_incompatible_schema_fails_closed():
    assert not validate_schema(["not", "an", "object"], GITHUB_META_SCHEMA).compatible


# ── Fixtures (91–98) ──────────────────────────────────────────────────────────
def test_sanitized_fixture_passes():
    doc = load_fixture("github_meta")
    assert doc["provider_id"] == "github_meta" and "body" in doc


def test_fixture_with_token_fails_leak_scan():
    import pytest as _p
    from saathi.credentials.leakscan import LeakDetected

    with _p.raises(LeakDetected):
        assert_fixture_clean({"access_token": "ghp_" + "a" * 30})


def test_fixture_with_cookie_fails():
    from saathi.credentials.leakscan import LeakDetected

    with pytest.raises(LeakDetected):
        assert_fixture_clean({"cookie": "session=abc123def456"})


def test_fixture_with_personal_data_scrubbed():
    cleaned = sanitize_fixture_body({"password": "x", "public": 1})
    assert "password" not in cleaned and cleaned.get("public") == 1


def test_fixture_provenance_recorded():
    doc = load_fixture("github_meta")
    assert doc["capture_method"] and doc["official_documentation_reference"]


def test_fixture_size_bounded():
    doc = load_fixture("github_meta")
    import json

    assert len(json.dumps(doc)) < 64 * 1024


def test_raw_provider_response_not_committed():
    # fixture holds a normalized body, not a raw HTTP response object
    doc = load_fixture("github_meta")
    assert "socket" not in doc and "raw_headers" not in doc


def test_normalized_fixture_deterministic():
    assert fixture_body("github_meta") == fixture_body("github_meta")


def test_fixture_scan_clean():
    assert scan_fixture(load_fixture("github_meta")) == []


def test_missing_fixture_fails_closed():
    with pytest.raises(FixtureError):
        load_fixture("github_meta", "does_not_exist")


def test_is_external_candidate():
    assert is_external_candidate("github_meta") and not is_external_candidate("binance")
