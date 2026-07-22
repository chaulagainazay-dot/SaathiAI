"""M34 — Live external verification: security, authorization, and budget tests.

Every test is OFFLINE: the transport (DNS/TLS/sender) is injected, ``enabled`` is
passed explicitly, and the store + evidence dir are redirected to tmp_path. No test
performs a real DNS, TLS, or network operation. The live env flag is never set.
"""
from __future__ import annotations

import pytest

from saathi.connectors.providers.external.m34 import (
    M34_DEFAULT_CALL_BUDGET,
    M34_MAX_CALL_BUDGET,
    ReliabilityQualification,
    build_authorization,
    plan_m34_verification,
    run_m34_live_verification,
)
from saathi.connectors.providers.external.profiles import resolve_external_profile
from saathi.connectors.providers.external.verification import ExternalVerificationStore
from saathi.connectors.providers.external.verify import offline_transport
from saathi.connectors.providers.external.testkit import (
    fixture_sender, make_transport, private_resolver, raising_sender, tls_prober,
)


def _store(tmp_path):
    return ExternalVerificationStore(tmp_path / "m34_reg.json", clock=lambda: 1752800000.0)


def _ok_transport():
    return offline_transport("github_meta")


def _run(tmp_path, transport, **kw):
    defaults = dict(
        ack_read_only=True, ack_network=True, ack_non_production=True, ack_call_budget=True,
        max_calls=3, transport=transport, enabled=True, store=_store(tmp_path),
        evidence_dir=str(tmp_path),
    )
    defaults.update(kw)
    return run_m34_live_verification("github_meta", **defaults)


# ── authorization (acks) ─────────────────────────────────────────────────────
@pytest.mark.parametrize("drop,expect", [
    ("ack_read_only", "missing_ack_read_only"),
    ("ack_network", "missing_ack_network"),
    ("ack_non_production", "missing_ack_non_production"),
    ("ack_call_budget", "missing_ack_call_budget"),
])
def test_missing_ack_blocks(tmp_path, drop, expect):
    res = _run(tmp_path, _ok_transport(), **{drop: False})
    assert res["ok"] is False
    assert expect in res["blockers"]
    assert res["live_call"] is False


def test_all_acks_required_together(tmp_path):
    res = _run(tmp_path, _ok_transport())
    assert res["ok"] is True
    assert res["authorization"]["operator_authorized"] is True


def test_unknown_provider_blocks(tmp_path):
    res = run_m34_live_verification(
        "not_a_provider", ack_read_only=True, ack_network=True, ack_non_production=True,
        ack_call_budget=True, max_calls=3, transport=_ok_transport(), enabled=True,
        store=_store(tmp_path), evidence_dir=str(tmp_path),
    )
    assert res["ok"] is False
    assert any("provider_invalid" in b for b in res["blockers"])


def test_disabled_env_aborts(tmp_path):
    res = _run(tmp_path, _ok_transport(), enabled=False)
    assert res["ok"] is False
    assert res["success_or_failure"] == "aborted"
    assert res["verification_state"] == "UNVERIFIED"


def test_rollout_unchanged_after_authorization(tmp_path):
    res = _run(tmp_path, _ok_transport())
    assert res["rollout_state"] == {
        "connector": "OFF", "provider": "OFF", "inference": "OFF",
        "canary_providers": 0, "active_providers": 0,
    }


def test_authorization_record_shape(tmp_path):
    profile = resolve_external_profile("github_meta")
    authz = build_authorization(
        profile, ack_read_only=True, ack_network=True, ack_non_production=True,
        ack_call_budget=True, max_calls=3, authorization_time="t",
    )
    d = authz.to_dict()
    for k in (
        "provider_id", "operation", "operator_authorized", "authorization_time",
        "read_only_acknowledged", "network_acknowledged", "non_production_acknowledged",
        "call_budget_acknowledged", "approved_call_budget", "approved_deadline",
        "approved_response_limit", "approved_redirect_limit", "approved_data_classification",
    ):
        assert k in d
    assert d["approved_call_budget"] == 3
    assert d["approved_data_classification"] == "PUBLIC"


# ── call budget ──────────────────────────────────────────────────────────────
def test_default_budget_is_three(tmp_path):
    plan = plan_m34_verification(
        "github_meta", ack_read_only=True, ack_network=True,
        ack_non_production=True, ack_call_budget=True,
    )
    assert plan["approved_call_budget"] == M34_DEFAULT_CALL_BUDGET == 3


def test_zero_budget_blocks(tmp_path):
    plan = plan_m34_verification(
        "github_meta", ack_read_only=True, ack_network=True,
        ack_non_production=True, ack_call_budget=True, max_calls=0,
    )
    assert plan["allowed"] is False
    assert "call_budget_below_minimum" in plan["blockers"]


def test_negative_budget_blocks(tmp_path):
    plan = plan_m34_verification(
        "github_meta", ack_read_only=True, ack_network=True,
        ack_non_production=True, ack_call_budget=True, max_calls=-2,
    )
    assert plan["allowed"] is False
    assert "call_budget_below_minimum" in plan["blockers"]


def test_budget_over_five_blocks(tmp_path):
    plan = plan_m34_verification(
        "github_meta", ack_read_only=True, ack_network=True,
        ack_non_production=True, ack_call_budget=True, max_calls=6,
    )
    assert plan["allowed"] is False
    assert "call_budget_over_maximum" in plan["blockers"]
    assert M34_MAX_CALL_BUDGET == 5


def test_retry_consumes_budget(tmp_path):
    # every call is a transient timeout → a retry is attempted but each consumes
    # budget, so the total call count never exceeds the approved budget.
    tr = make_transport(sender=raising_sender(TimeoutError("t")))
    res = _run(tmp_path, tr, max_calls=3)
    assert res["actual_call_count"] <= 3
    assert res["ok"] is False


def test_budget_exhaustion_fails_safely(tmp_path):
    tr = make_transport(sender=raising_sender(TimeoutError("t")))
    res = _run(tmp_path, tr, max_calls=2)
    assert res["ok"] is False
    assert res["reliability_qualification"] == ReliabilityQualification.NOT_QUALIFIED_TRANSIENT_FAILURE.value


def test_actual_calls_never_exceed_budget(tmp_path):
    for b in (1, 2, 3, 4, 5):
        res = _run(tmp_path, _ok_transport(), max_calls=b)
        assert res["actual_call_count"] <= b


# ── provider identity ────────────────────────────────────────────────────────
def test_correct_identity_passes(tmp_path):
    res = _run(tmp_path, _ok_transport())
    assert res["provider_id"] == "github_meta"
    assert res["operation"] == "get_meta"
    assert res["ok"] is True


def test_no_provider_fallback_on_unknown(tmp_path):
    res = run_m34_live_verification(
        "ghost", ack_read_only=True, ack_network=True, ack_non_production=True,
        ack_call_budget=True, transport=_ok_transport(), enabled=True,
        store=_store(tmp_path), evidence_dir=str(tmp_path),
    )
    assert res["ok"] is False
    assert res["provider_id"] == "ghost"  # never substituted


def test_quarantined_provider_blocks(tmp_path):
    res = _run(tmp_path, _ok_transport(), quarantined=True)
    assert res["ok"] is False
    assert "provider_quarantined" in res["blockers"]


# ── DNS / SSRF ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ips", [
    ("127.0.0.1",), ("10.0.0.5",), ("fd00::1",), ("169.254.10.1",),
    ("169.254.169.254",), ("240.0.0.1",), ("140.82.112.3", "10.0.0.5"),
])
def test_private_or_unsafe_dns_blocks(tmp_path, ips):
    tr = make_transport(resolver=private_resolver(ips), sender=fixture_sender())
    res = _run(tmp_path, tr)
    assert res["ok"] is False
    assert res["reliability_qualification"] == ReliabilityQualification.NOT_QUALIFIED_SECURITY_FAILURE.value


def test_public_dns_passes(tmp_path):
    tr = make_transport(sender=fixture_sender(
        body_bytes=b'{"verifiable_password_authentication":false,"hooks":["1.2.3.0/24"],"pages":["5.6.7.0/24"]}',
    ))
    res = _run(tmp_path, tr)
    assert res["ok"] is True


# ── TLS ──────────────────────────────────────────────────────────────────────
def test_tls_unverified_blocks(tmp_path):
    tr = make_transport(tls_prober_fn=tls_prober(verified=False), sender=fixture_sender())
    res = _run(tmp_path, tr)
    assert res["ok"] is False
    assert res["reliability_qualification"] == ReliabilityQualification.NOT_QUALIFIED_SECURITY_FAILURE.value


def test_tls_hostname_mismatch_blocks(tmp_path):
    tr = make_transport(tls_prober_fn=tls_prober(verified=True, hostname_match=False), sender=fixture_sender())
    res = _run(tmp_path, tr)
    assert res["ok"] is False
    assert res["reliability_qualification"] == ReliabilityQualification.NOT_QUALIFIED_SECURITY_FAILURE.value


# ── response safety / raw containment ────────────────────────────────────────
def test_oversized_response_fails(tmp_path):
    tr = make_transport(sender=fixture_sender(body_bytes=b"x" * (300 * 1024)))
    res = _run(tmp_path, tr)
    assert res["ok"] is False


def test_no_raw_body_in_result_or_evidence(tmp_path):
    import json

    res = _run(tmp_path, _ok_transport())
    blob = json.dumps({k: v for k, v in res.items() if k != "_calls_internal"}, default=str).lower()
    # normalized CIDR strings are allowed; raw secrets / header dumps are not
    for marker in ("set-cookie", "bearer ", "access_token", "refresh_token", "ghp_", "x-github-request-id"):
        assert marker not in blob, marker
    for call in res["calls"]:
        assert "body_bytes" not in call
        assert "headers" not in call
        assert "normalized_result_fingerprint" in call
    assert res["leak_clean"] is True


def test_write_method_never_reachable(tmp_path):
    # the profile is GET-only; the read-only ceiling holds through validation
    res = _run(tmp_path, _ok_transport())
    assert res["ok"] is True
    prof = resolve_external_profile("github_meta")
    assert prof.method == "GET"
