"""M34 — Live external verification: runtime, schema, rate-limit, evidence tests.

Offline: transport injected, ``enabled`` explicit, store + evidence in tmp_path.
"""
from __future__ import annotations

import json

import pytest

from saathi.connectors.providers.external.m34 import (
    classify_schema_compat,
    latency_bucket,
    normalized_fingerprint,
    run_m34_live_verification,
    size_bucket,
    write_m34_evidence,
)
from saathi.connectors.providers.external.verification import ExternalVerificationStore
from saathi.connectors.providers.external.verify import offline_transport
from saathi.connectors.providers.external.testkit import fixture_sender, make_transport, raising_sender

_GOOD_BODY = b'{"verifiable_password_authentication":false,"hooks":["1.2.3.0/24"],"pages":["5.6.7.0/24"]}'


def _store(tmp_path):
    return ExternalVerificationStore(tmp_path / "m34_reg.json", clock=lambda: 1752800000.0)


def _run(tmp_path, transport, **kw):
    defaults = dict(
        ack_read_only=True, ack_network=True, ack_non_production=True, ack_call_budget=True,
        max_calls=3, transport=transport, enabled=True, store=_store(tmp_path),
        evidence_dir=str(tmp_path),
    )
    defaults.update(kw)
    return run_m34_live_verification("github_meta", **defaults)


def _rl_transport(**sender_kw):
    return make_transport(sender=fixture_sender(body_bytes=_GOOD_BODY, **sender_kw))


# ── latency buckets ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("ms,bucket", [
    (10, "UNDER_250_MS"), (300, "250_TO_500_MS"), (700, "500_MS_TO_1_S"),
    (1500, "1_TO_2_S"), (3000, "2_TO_5_S"), (9000, "OVER_5_S"),
])
def test_latency_buckets(ms, bucket):
    assert latency_bucket(ms) == bucket


def test_latency_timeout_bucket():
    assert latency_bucket(0, timed_out=True) == "TIMEOUT"


def test_size_buckets():
    assert size_bucket(0) == "EMPTY"
    assert size_bucket(1000) == "UNDER_4_KIB"
    assert size_bucket(10 * 1024) == "4_TO_64_KIB"


# ── successful call surface ──────────────────────────────────────────────────
def test_success_records_bounded_call(tmp_path):
    res = _run(tmp_path, _rl_transport())
    assert res["ok"] is True
    assert res["actual_call_count"] == 3
    for c in res["calls"]:
        assert c["latency_bucket"]
        assert c["schema_result"] == "COMPATIBLE_EXACT"
        assert c["success_or_failure"] == "success"
        assert c["tls_verified"] is True
        assert c["redirect_count"] == 0


def test_rate_limit_headers_parsed(tmp_path):
    tr = _rl_transport(headers={"x-ratelimit-limit": "60", "x-ratelimit-remaining": "59"})
    res = _run(tmp_path, tr)
    rl = res["calls"][0]["rate_limit_summary"]
    assert rl["rate_limit_visibility"] == "EXPOSED"
    assert rl["limit_present"] is True


def test_rate_limit_absent_classifies_not_exposed(tmp_path):
    tr = make_transport(sender=fixture_sender(body_bytes=_GOOD_BODY))  # no rate headers
    res = _run(tmp_path, tr)
    rl = res["calls"][0]["rate_limit_summary"]
    assert rl["rate_limit_visibility"] == "NOT_EXPOSED"


def test_429_does_not_qualify(tmp_path):
    tr = _rl_transport(status=429, headers={"retry-after": "1"})
    res = _run(tmp_path, tr)
    assert res["ok"] is False
    # a 429 is a provider condition, never a success or a security failure
    assert res["successful_calls"] == 0


# ── schema classification ────────────────────────────────────────────────────
def test_schema_compat_classifier():
    assert classify_schema_compat({"overall": "COMPATIBLE_EXACT"}) == "COMPATIBLE_EXACT"
    assert classify_schema_compat({"overall": "COMPATIBLE_ADDITIVE"}) == "COMPATIBLE_ADDITIVE"
    assert classify_schema_compat({"overall": "weird"}) == "UNKNOWN_SCHEMA_CHANGE"
    assert classify_schema_compat({}) == "UNKNOWN_SCHEMA_CHANGE"


def test_additive_schema_passes_with_limitation(tmp_path):
    body = b'{"verifiable_password_authentication":false,"hooks":["1.2.3.0/24"],"pages":["5.6.7.0/24"],"new_field":[1]}'
    res = _run(tmp_path, make_transport(sender=fixture_sender(body_bytes=body)))
    assert res["ok"] is True
    assert "COMPATIBLE_ADDITIVE" in res["schema_compatibility"]


def test_missing_required_field_fails(tmp_path):
    body = b'{"pages":["5.6.7.0/24"]}'  # missing required verifiable_password_authentication/hooks
    res = _run(tmp_path, make_transport(sender=fixture_sender(body_bytes=body)))
    assert res["ok"] is False
    assert res["reliability_qualification"] == "NOT_QUALIFIED_SCHEMA_FAILURE"


def test_type_change_fails(tmp_path):
    body = b'{"verifiable_password_authentication":false,"hooks":"nope","pages":["5.6.7.0/24"]}'
    res = _run(tmp_path, make_transport(sender=fixture_sender(body_bytes=body)))
    assert res["ok"] is False
    assert res["reliability_qualification"] == "NOT_QUALIFIED_SCHEMA_FAILURE"


# ── failure classification ───────────────────────────────────────────────────
def test_transient_timeout_classifies(tmp_path):
    res = _run(tmp_path, make_transport(sender=raising_sender(TimeoutError("t"))))
    assert res["ok"] is False
    assert res["reliability_qualification"] == "NOT_QUALIFIED_TRANSIENT_FAILURE"


def test_provider_unavailable_classifies(tmp_path):
    res = _run(tmp_path, _rl_transport(status=503))
    assert res["ok"] is False
    assert res["reliability_qualification"] in (
        "NOT_QUALIFIED_PROVIDER_FAILURE", "NOT_QUALIFIED_INSUFFICIENT_EVIDENCE",
    )


# ── evidence writer ──────────────────────────────────────────────────────────
def test_evidence_written_and_bounded(tmp_path):
    res = _run(tmp_path, _rl_transport())
    written = write_m34_evidence(res, evidence_dir=str(tmp_path))
    names = {p.split("/")[-1] for p in written}
    for expect in (
        "authorization.json", "provider_identity.json", "live_call_01.json",
        "schema_compatibility.json", "repeatability.json", "reliability_qualification.json",
        "canary_readiness.json", "verification_state.json", "verification_fingerprint.json",
        "leak_scan_results.json", "redaction_results.json", "validation_summary.json",
    ):
        assert expect in names, expect
    # every live_call evidence file is bounded and has no raw body/headers
    call1 = json.loads((tmp_path / "live_call_01.json").read_text())["body"]
    assert "body_bytes" not in call1 and "headers" not in call1
    assert "normalized_result_fingerprint" in call1


def test_validation_summary_invariants(tmp_path):
    res = _run(tmp_path, _rl_transport())
    write_m34_evidence(res, evidence_dir=str(tmp_path))
    body = json.loads((tmp_path / "validation_summary.json").read_text())["body"]
    for k in (
        "external_write_calls", "financial_provider_calls", "trading_provider_calls",
        "private_network_calls", "tls_verification_bypasses", "unsafe_redirects_followed",
        "raw_responses_committed", "secret_leaks", "production_credentials",
        "canary_providers", "active_providers",
    ):
        assert body[k] == 0
    assert body["provider_rollout"] == "OFF"
    assert body["trading_guardian"] == "UNCHANGED / UNENGAGED"


def test_normalized_fingerprint_order_independent():
    a = normalized_fingerprint({"a": [1, 2], "b": 3})
    b = normalized_fingerprint({"b": 3, "a": [1, 2]})
    assert a == b


# ── no import-time / no auto network ─────────────────────────────────────────
def test_module_import_makes_no_call():
    import importlib

    import saathi.connectors.providers.external.m34 as m
    importlib.reload(m)  # reload must not perform any network/DNS/TLS operation
    assert m.M34_DEFAULT_CALL_BUDGET == 3


def test_default_disabled_without_env(tmp_path, monkeypatch):
    monkeypatch.delenv("SAATHI_M33_EXTERNAL_VERIFY_ENABLED", raising=False)
    monkeypatch.delenv("SAATHI_M34_LIVE_VERIFY_ENABLED", raising=False)
    res = run_m34_live_verification(
        "github_meta", ack_read_only=True, ack_network=True, ack_non_production=True,
        ack_call_budget=True, transport=offline_transport("github_meta"),
        store=_store(tmp_path), evidence_dir=str(tmp_path),
    )
    assert res["success_or_failure"] == "aborted"
