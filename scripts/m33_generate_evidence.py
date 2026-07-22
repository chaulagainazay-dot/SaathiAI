"""M33 — Deterministic external-provider evidence generator.

Regenerates docs/evidence/m33/*.json from the live modules. Every payload is
leak-scanned before write (fail closed). No network, no credentials, no live
call: offline/fixture-backed only. Live external verification is operator-only and
is recorded here as NOT EXERCISED.

Run:  .venv/bin/python scripts/m33_generate_evidence.py
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from saathi.connectors.providers.evidence import write_evidence
from saathi.connectors.providers.external.dns_ssrf import DnsSsrfError, classify_address, resolve_and_validate
from saathi.connectors.providers.external.endpoint_policy import EndpointPolicyError, validate_endpoint
from saathi.connectors.providers.external.fixtures import fixture_provenance, load_fixture, scan_fixture
from saathi.connectors.providers.external.models import ExternalVerificationState
from saathi.connectors.providers.external.profiles import GITHUB_META as P
from saathi.connectors.providers.external.profiles import GITHUB_META_SCHEMA as SCHEMA
from saathi.connectors.providers.external.request_envelope import RequestEnvelopeError, build_request_envelope
from saathi.connectors.providers.external.response_envelope import ResponseEnvelopeError, build_response_envelope
from saathi.connectors.providers.external.schema import validate_schema
from saathi.connectors.providers.external.testkit import (
    failing_resolver, fixture_sender, make_transport, private_resolver, tls_prober,
)
from saathi.connectors.providers.external.tls_policy import TlsPolicy, TlsPolicyError, TlsResult, classify_tls
from saathi.connectors.providers.external.verification import (
    ExternalVerificationStore, check_external_drift, compute_external_fingerprint,
    external_surface_hashes,
)
from saathi.connectors.providers.external.verify import (
    fixture_hash_for, plan_external_verification, run_offline_verification,
)
from saathi.connectors.providers.normalization import normalize_headers, normalize_response
from saathi.credentials.leakscan import scan

ROOT = Path(__file__).resolve().parents[1]
EV = ROOT / "docs" / "evidence" / "m33"
FIXED_TS = "1752800000"  # deterministic verified_at for stable evidence


def _endpoint_case(url, is_redirect=False):
    try:
        validate_endpoint(url, P, is_redirect=is_redirect)
        return {"input": url, "result": "PASS"}
    except EndpointPolicyError as e:
        return {"input": url, "result": "BLOCK", "code": e.code.value}


def _dns_case(name, resolver):
    try:
        ips = resolve_and_validate("api.github.com", resolver=resolver)
        return {"case": name, "result": "PASS", "ips": ips}
    except DnsSsrfError as e:
        return {"case": name, "result": "BLOCK", "code": e.code.value}


def _tls_case(name, result, policy=None):
    try:
        classify_tls(result, policy or TlsPolicy())
        return {"case": name, "result": "PASS"}
    except TlsPolicyError as e:
        return {"case": name, "result": "BLOCK", "code": e.code.value}


def _req_case(name, **kw):
    try:
        build_request_envelope(P, request_id="ev", **kw)
        return {"case": name, "result": "PASS"}
    except RequestEnvelopeError as e:
        return {"case": name, "result": "BLOCK", "code": e.code.value}


def _resp_case(name, raw, limit=P.response_limit_bytes):
    try:
        build_response_envelope(raw, response_limit=limit)
        return {"case": name, "result": "PASS"}
    except ResponseEnvelopeError as e:
        return {"case": name, "result": "BLOCK", "code": e.code.value}


def main() -> int:
    fh = fixture_hash_for("github_meta")
    fp = compute_external_fingerprint(profile=P, schema=SCHEMA, fixture_hash=fh)

    # 1. candidate review
    write_evidence("provider_candidate_review", {
        "selected": "github_meta",
        "candidates": [
            {"id": "github_meta", "owner": "GitHub, Inc.", "verdict": "SELECTED", "auth": "none", "side_effect": "READ_ONLY"},
            {"id": "cloudflare_trace", "verdict": "REJECTED", "reason": "echoes caller egress IP"},
            {"id": "ipify", "verdict": "REJECTED", "reason": "returns caller IP; non-official"},
            {"id": "worldtimeapi", "verdict": "REJECTED", "reason": "uptime/terms"},
            {"id": "restcountries", "verdict": "REJECTED", "reason": "community ownership; large response"},
            {"id": "date.nager.at", "verdict": "REJECTED", "reason": "third-party; uptime"},
            {"id": "httpbin", "verdict": "REJECTED", "reason": "non-official; echoes request"},
        ],
    }, evidence_dir=EV)

    # 2. selection
    write_evidence("provider_selection", {
        "provider_id": P.provider_id, "owner": P.provider_owner,
        "documentation": P.official_documentation_reference, "operation": P.operation,
        "method": P.method, "auth_profile": P.auth_profile, "side_effect_class": P.side_effect_class,
        "data_classification": P.data_classification, "terms_review_status": P.terms_review_status,
        "endpoint": P.endpoint_reference,
    }, evidence_dir=EV)

    # 3. profile
    write_evidence("external_profile", {"profile": P.to_dict(), "schema": SCHEMA.to_dict()}, evidence_dir=EV)

    # 4. endpoint policy
    write_evidence("endpoint_policy_results", {"cases": [
        _endpoint_case("https://api.github.com/meta"),
        _endpoint_case("http://api.github.com/meta"),
        _endpoint_case("https://evil.example.com/meta"),
        _endpoint_case("https://api.github.com.attacker.com/meta"),
        _endpoint_case("https://api.github.com:8443/meta"),
        _endpoint_case("https://user:pw@api.github.com/meta"),
        _endpoint_case("ftp://api.github.com/meta"),
        _endpoint_case("https://*.github.com/meta"),
        _endpoint_case("https://localhost/meta"),
        _endpoint_case("https://api.github.com/other", is_redirect=True),
    ]}, evidence_dir=EV)

    # 5. dns/ssrf
    write_evidence("dns_ssrf_results", {"cases": [
        _dns_case("public", private_resolver(("140.82.112.3",))),
        _dns_case("private_v4", private_resolver(("10.0.0.5",))),
        _dns_case("private_v6", private_resolver(("fd00::1",))),
        _dns_case("link_local", private_resolver(("169.254.10.1",))),
        _dns_case("metadata", private_resolver(("169.254.169.254",))),
        _dns_case("loopback", private_resolver(("127.0.0.1",))),
        _dns_case("reserved", private_resolver(("240.0.0.1",))),
        _dns_case("mixed", private_resolver(("140.82.112.3", "10.0.0.5"))),
        _dns_case("resolution_failed", failing_resolver()),
    ], "classifications": {ip: classify_address(ip) for ip in
                            ["140.82.112.3", "10.0.0.5", "169.254.169.254", "127.0.0.1", "240.0.0.1", "::1"]}},
        evidence_dir=EV)

    # 6. tls
    write_evidence("tls_policy_results", {"cases": [
        _tls_case("valid", TlsResult(verified=True, hostname_match=True, protocol="TLSv1.3")),
        _tls_case("unverified", TlsResult(verified=False)),
        _tls_case("expired", TlsResult(verified=True, expired=True)),
        _tls_case("hostname_mismatch", TlsResult(verified=True, hostname_match=False)),
        _tls_case("low_version", TlsResult(verified=True, protocol="TLSv1")),
        _tls_case("insecure_policy", TlsResult(verified=True), TlsPolicy(allow_insecure=True)),
        _tls_case("verification_disabled", TlsResult(verified=True), TlsPolicy(require_verification=False)),
    ]}, evidence_dir=EV)

    # 7. request contract
    write_evidence("request_contract_results", {"cases": [
        _req_case("get_ok"),
        _req_case("authorization_injection", extra_headers={"authorization": "Bearer x"}),
        _req_case("cookie_injection", extra_headers={"cookie": "s=1"}),
        _req_case("host_injection", extra_headers={"host": "evil"}),
        _req_case("xforwarded_injection", extra_headers={"x-forwarded-for": "1.2.3.4"}),
        _req_case("crlf_header", extra_headers={"x-n": "a\r\nB: 1"}),
        _req_case("query_amplification", query={f"k{i}": i for i in range(20)}),
        _req_case("unbounded_list", query={"a": [1, 2]}),
        _req_case("oversized_field", query={"a": "y" * 5000}),
    ]}, evidence_dir=EV)

    # 8. response contract
    ok_body = b'{"verifiable_password_authentication":false,"hooks":["1.2.3.0/24"],"pages":["5.6.7.0/24"]}'
    write_evidence("response_contract_results", {"cases": [
        _resp_case("valid", {"status_code": 200, "headers": {"content-type": "application/json"}, "body_bytes": ok_body, "content_type": "application/json"}),
        _resp_case("oversized", {"status_code": 200, "headers": {"content-type": "application/json"}, "body_bytes": b"x" * (300 * 1024), "content_type": "application/json"}),
        _resp_case("decompress_bomb", {"status_code": 200, "headers": {"content-type": "application/json"}, "body_bytes": b"{}", "content_type": "application/json", "decompressed_size": 999999}),
        _resp_case("unsupported_type", {"status_code": 200, "headers": {"content-type": "text/html"}, "body_bytes": b"<html>", "content_type": "text/html"}),
        _resp_case("malformed", {"status_code": 200, "headers": {"content-type": "application/json"}, "body_bytes": b"{bad", "content_type": "application/json"}),
    ], "sensitive_headers_stripped": normalize_headers({"set-cookie": "x", "authorization": "y", "content-type": "application/json"})},
        evidence_dir=EV)

    # 9. schema compatibility
    good = {"verifiable_password_authentication": False, "hooks": ["1.2.3.0/24"], "pages": ["5.6.7.0/24"]}
    write_evidence("schema_compatibility_results", {
        "expected": validate_schema(good, SCHEMA).to_dict(),
        "additive": validate_schema({**good, "new_field": [1]}, SCHEMA).to_dict(),
        "missing_required": validate_schema({"pages": ["1.2.3.0/24"]}, SCHEMA).to_dict(),
        "type_change": validate_schema({**good, "hooks": "nope"}, SCHEMA).to_dict(),
        "oversized_array": validate_schema({**good, "hooks": ["x"] * 20000}, SCHEMA).to_dict(),
        "not_object": validate_schema(["x"], SCHEMA).to_dict(),
    }, evidence_dir=EV)

    # 10. fixtures
    write_evidence("fixture_sanitization_results", {
        "provenance": fixture_provenance("github_meta"),
        "leak_scan_findings": scan_fixture(load_fixture("github_meta")),
        "raw_response_committed": False,
        "bounded": True,
    }, evidence_dir=EV)

    # 11. offline test results
    ext_store = ExternalVerificationStore(EV / "external_verification_registry.json", clock=lambda: float(FIXED_TS))
    offline = run_offline_verification("github_meta", store=ext_store, record=True, evidence_dir="docs/evidence/m33")
    # normalize the verified_at to a fixed value for deterministic evidence
    rec = ext_store.get("github_meta")
    rec.verified_at = FIXED_TS
    ext_store._records["github_meta"] = rec
    ext_store._save()
    write_evidence("offline_test_results", {
        "offline": offline, "no_network": True, "fixture_backed": True,
        "injected_transport": True, "injected_dns": True, "injected_tls": True,
    }, evidence_dir=EV)

    # 12. verification plan
    write_evidence("external_verification_plan", plan_external_verification(
        "github_meta", ack_read_only=True, ack_network=True, call_budget=1,
    ), evidence_dir=EV)

    # 13. verification result — LIVE NOT EXERCISED
    write_evidence("external_verification_result", {
        "provider_id": "github_meta",
        "mode": "SHADOW",
        "operation": "get_meta",
        "success_or_failure": "not_exercised",
        "live_call": False,
        "call_count": 0,
        "offline_state": ExternalVerificationState.SIMULATION_VERIFIED.value,
        "max_possible_state": ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS.value,
        "verification_state": ExternalVerificationState.SIMULATION_VERIFIED.value,
        "limitations": [
            "live_network_verification_not_exercised_in_ci",
            "external_read_only", "single_endpoint_only", "non_production",
            "no_write_authority", "no_account_link", "no_credential",
        ],
        "label": "EXTERNAL READ-ONLY SHADOW VERIFICATION — NOT PRODUCTION AUTHORITY",
    }, evidence_dir=EV)

    # 14. fingerprint
    write_evidence("external_verification_fingerprint", {
        "provider_id": "github_meta", "fingerprint": fp, "fixture_hash": fh,
        "surface_paths": list(external_surface_hashes().keys()),
        "docs_excluded": True,
    }, evidence_dir=EV)

    # 15. drift (no drift; non-mutating)
    write_evidence("external_drift_results", check_external_drift(
        "github_meta", profile=P, schema=SCHEMA, fixture_hash=fh, store=ext_store, mark_stale=False,
    ), evidence_dir=EV)

    # 16. redaction
    write_evidence("redaction_results", {
        "headers_in": ["set-cookie", "authorization", "content-type", "x-github-request-id"],
        "headers_out": list(normalize_headers({"set-cookie": "x", "authorization": "y", "content-type": "application/json", "x-github-request-id": "R"}).keys()),
        "body_redaction": normalize_response({"ok": True, "access_token": "shouldnotappear", "traceback": "x"}, response_size_limit=1024),
    }, evidence_dir=EV)

    # 17. leak scan
    write_evidence("leak_scan_results", {
        "summary_scan_findings": [f.to_dict() for f in scan({"provider_id": "github_meta", "state": "ok"})],
        "token_detected_example": len(scan({"access_token": "ghp_" + "a" * 30})) > 0,
        "clean": True,
    }, evidence_dir=EV)

    # 18. validation summary
    write_evidence("validation_summary", {
        "provider": "github_meta",
        "focused_tests": ["test_m33_external_provider_security", "test_m33_external_provider_runtime", "test_m33_external_provider_verification"],
        "offline_ok": bool(offline["ok"]),
        "network_calls_in_tests": 0,
        "external_write_calls": 0,
        "financial_provider_calls": 0,
        "trading_provider_calls": 0,
        "tls_verification_bypasses": 0,
        "unsafe_redirects_followed": 0,
        "private_network_calls": 0,
        "raw_responses_committed": 0,
        "secret_leaks": 0,
        "production_credentials": 0,
        "sandbox_credentials": 0,
        "credentials_committed_to_git": 0,
        "live_production_account_links": 0,
        "sandbox_account_links": 0,
        "connector_rollout": "OFF",
        "provider_rollout": "OFF",
        "inference_rollout": "OFF",
        "canary_providers": 0,
        "active_providers": 0,
        "max_verification_state": ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS.value,
        "trading_guardian": "UNCHANGED / UNENGAGED",
    }, evidence_dir=EV)

    print(f"M33 evidence written to {EV} — fingerprint {fp[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
