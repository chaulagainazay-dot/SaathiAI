"""M34 — Reliability qualification, repeatability, verification state, canary readiness."""
from __future__ import annotations

import pytest

from saathi.connectors.providers.external.m34 import (
    CanaryReadiness,
    LiveCall,
    ReliabilityQualification,
    RepeatabilityClass,
    assess_canary_readiness,
    canary_readiness_status,
    check_m34_drift,
    classify_repeatability,
    compute_m34_fingerprint,
    qualify_reliability,
    reliability_status,
    run_m34_live_verification,
)
from saathi.connectors.providers.external.models import ExternalVerificationState
from saathi.connectors.providers.external.profiles import resolve_external_profile
from saathi.connectors.providers.external.verification import ExternalVerificationStore
from saathi.connectors.providers.external.verify import offline_transport
from saathi.connectors.providers.external.testkit import fixture_sender, make_transport, raising_sender

_GOOD = b'{"verifiable_password_authentication":false,"hooks":["1.2.3.0/24"],"pages":["5.6.7.0/24"]}'


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


def _call(n, *, ok=True, fp="x", data=None, code="", schema="COMPATIBLE_EXACT"):
    return LiveCall(
        call_number=n, mode="LIVE_RELIABILITY_VERIFY", success=ok,
        failure_code=code, schema_compat=schema if ok else "",
        normalized_fingerprint=fp if ok else "", normalized_data=(data or {"a": 1}) if ok else {},
    )


# ── repeatability ────────────────────────────────────────────────────────────
def test_repeatability_stable_exact():
    calls = [_call(1, fp="a"), _call(2, fp="a"), _call(3, fp="a")]
    assert classify_repeatability(calls) == RepeatabilityClass.STABLE_EXACT.value


def test_repeatability_dynamic_variation_ignored():
    calls = [
        _call(1, fp="a", data={"a": 1, "timestamp": 10}),
        _call(2, fp="b", data={"a": 1, "timestamp": 20}),
    ]
    assert classify_repeatability(calls) == RepeatabilityClass.EXPECTED_DYNAMIC_VARIATION.value


def test_repeatability_unexpected_variation():
    calls = [_call(1, fp="a", data={"a": 1}), _call(2, fp="b", data={"b": 2})]
    assert classify_repeatability(calls) == RepeatabilityClass.UNEXPECTED_VARIATION.value


def test_repeatability_single_call_non_comparable():
    assert classify_repeatability([_call(1)]) == RepeatabilityClass.NON_COMPARABLE.value


# ── reliability ──────────────────────────────────────────────────────────────
def test_two_successful_calls_qualify():
    q, lim = qualify_reliability([_call(1, fp="a"), _call(2, fp="a")], approved_budget=3)
    assert q == ReliabilityQualification.QUALIFIED_WITH_LIMITATIONS.value
    assert "no_write_authority" in lim


def test_single_success_insufficient():
    q, lim = qualify_reliability([_call(1, fp="a")], approved_budget=1)
    assert q == ReliabilityQualification.NOT_QUALIFIED_INSUFFICIENT_EVIDENCE.value


def test_security_failure_dominates():
    calls = [_call(1, ok=False, code="SSRF_POLICY_BLOCKED"), _call(2, fp="a"), _call(3, fp="a")]
    q, _ = qualify_reliability(calls, approved_budget=3)
    assert q == ReliabilityQualification.NOT_QUALIFIED_SECURITY_FAILURE.value


def test_schema_failure_blocks_qualification():
    calls = [_call(1, ok=False, code="SCHEMA_INCOMPATIBLE"), _call(2, fp="a")]
    q, _ = qualify_reliability(calls, approved_budget=3)
    assert q == ReliabilityQualification.NOT_QUALIFIED_SCHEMA_FAILURE.value


def test_all_transient_not_qualified():
    calls = [_call(1, ok=False, code="NETWORK_TIMEOUT"), _call(2, ok=False, code="CONNECTION_RESET")]
    q, _ = qualify_reliability(calls, approved_budget=3)
    assert q == ReliabilityQualification.NOT_QUALIFIED_TRANSIENT_FAILURE.value


def test_qualification_does_not_activate_rollout(tmp_path):
    res = _run(tmp_path, make_transport(sender=fixture_sender(body_bytes=_GOOD)))
    assert res["reliability_qualification"] == "QUALIFIED_WITH_LIMITATIONS"
    assert res["rollout_state"]["provider"] == "OFF"
    assert res["rollout_state"]["canary_providers"] == 0


# ── verification state ───────────────────────────────────────────────────────
def test_success_sets_external_read_only_verified(tmp_path):
    res = _run(tmp_path, make_transport(sender=fixture_sender(body_bytes=_GOOD)))
    assert res["verification_state"] == "EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS"
    assert res["external_state_persisted"] == "EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS"


def test_failure_does_not_set_success(tmp_path):
    res = _run(tmp_path, make_transport(sender=raising_sender(TimeoutError("t"))))
    assert res["verification_state"] == "EXTERNAL_VERIFICATION_FAILED"
    assert res["ok"] is False


def test_state_persisted_to_store(tmp_path):
    store = _store(tmp_path)
    run_m34_live_verification(
        "github_meta", ack_read_only=True, ack_network=True, ack_non_production=True,
        ack_call_budget=True, max_calls=3, transport=make_transport(sender=fixture_sender(body_bytes=_GOOD)),
        enabled=True, store=store, evidence_dir=str(tmp_path),
    )
    rec = store.get("github_meta")
    assert rec.state == "EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS"
    assert rec.live_call_count == 3


def test_eligibility_read_is_non_mutating(tmp_path):
    store = _store(tmp_path)
    # a read must not create or change a record
    before = store.get("github_meta").state
    reliability_status("github_meta", store=store, evidence_dir=str(tmp_path))
    canary_readiness_status("github_meta", store=store, evidence_dir=str(tmp_path))
    check_m34_drift("github_meta", store=store, mark_stale=False)
    after = store.get("github_meta").state
    assert before == after == "UNVERIFIED"


def test_state_operation_specific(tmp_path):
    res = _run(tmp_path, make_transport(sender=fixture_sender(body_bytes=_GOOD)))
    body_scope = [c for c in res["calls"]]
    # verification is about get_meta only; unsupported scope is explicit in evidence
    assert res["operation"] == "get_meta"


# ── canary readiness ─────────────────────────────────────────────────────────
def test_canary_ready_when_all_conditions_met():
    a, detail = assess_canary_readiness(
        reliability="QUALIFIED_WITH_LIMITATIONS",
        external_state="EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS",
        fresh=True, provider_healthy=True, quarantined=False, leak_clean=True,
        direct_network_bypasses=0, external_writes=0, rollout_off=True,
    )
    assert a == CanaryReadiness.CANARY_READY_WITH_LIMITATIONS.value
    assert "rollout_remains_off" in detail


@pytest.mark.parametrize("kw,blocker", [
    (dict(reliability="NOT_QUALIFIED_INSUFFICIENT_EVIDENCE"), "reliability_not_qualified"),
    (dict(fresh=False), "external_verification_not_fresh"),
    (dict(provider_healthy=False), "provider_unhealthy"),
    (dict(quarantined=True), "provider_quarantined"),
    (dict(leak_clean=False), "leak_scan_not_clean"),
    (dict(direct_network_bypasses=1), "direct_network_bypasses_nonzero"),
    (dict(external_writes=1), "external_writes_nonzero"),
])
def test_canary_not_ready_conditions(kw, blocker):
    base = dict(
        reliability="QUALIFIED_WITH_LIMITATIONS",
        external_state="EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS",
        fresh=True, provider_healthy=True, quarantined=False, leak_clean=True,
        direct_network_bypasses=0, external_writes=0, rollout_off=True,
    )
    base.update(kw)
    a, blockers = assess_canary_readiness(**base)
    assert a == CanaryReadiness.NOT_CANARY_READY.value
    assert any(blocker in b for b in blockers)


def test_canary_assessment_does_not_activate(tmp_path):
    res = _run(tmp_path, make_transport(sender=fixture_sender(body_bytes=_GOOD)))
    assert res["canary_readiness"] in ("CANARY_READY_WITH_LIMITATIONS", "NOT_CANARY_READY")
    assert res["rollout_state"]["canary_providers"] == 0
    assert res["rollout_state"]["active_providers"] == 0


# ── fingerprint / drift ──────────────────────────────────────────────────────
def test_m34_fingerprint_deterministic():
    p = resolve_external_profile("github_meta")
    assert compute_m34_fingerprint(p) == compute_m34_fingerprint(p)


def test_m34_fingerprint_differs_from_m33():
    from saathi.connectors.providers.external.verification import compute_external_fingerprint
    from saathi.connectors.providers.external.profiles import schema_for
    from saathi.connectors.providers.external.verify import fixture_hash_for

    p = resolve_external_profile("github_meta")
    m33 = compute_external_fingerprint(profile=p, schema=schema_for("github_meta"), fixture_hash=fixture_hash_for("github_meta"))
    assert compute_m34_fingerprint(p) != m33


def test_drift_false_on_fresh_record(tmp_path):
    store = _store(tmp_path)
    p = resolve_external_profile("github_meta")
    store.record_verification(
        "github_meta", state="EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS",
        fingerprint=compute_m34_fingerprint(p), verified_at="1752800000",
    )
    rep = check_m34_drift("github_meta", store=store, mark_stale=False)
    assert rep["drifted"] is False


def test_reliability_status_reports_fresh(tmp_path):
    store = _store(tmp_path)
    run_m34_live_verification(
        "github_meta", ack_read_only=True, ack_network=True, ack_non_production=True,
        ack_call_budget=True, max_calls=3, transport=make_transport(sender=fixture_sender(body_bytes=_GOOD)),
        enabled=True, store=store, evidence_dir=str(tmp_path),
    )
    st = reliability_status("github_meta", store=store, evidence_dir=str(tmp_path))
    assert st["external_state"] == "EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS"
    assert st["fresh"] is True
