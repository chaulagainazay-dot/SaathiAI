"""M45 — Runtime attestation & bounded rollout readiness tests (fail-closed)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.credentials import m44, m45
from saathi.credentials.leakscan import is_clean
from saathi.credentials.m44 import (
    PROVIDER_ID,
    RolloutRequest,
    sign_request,
)
from saathi.credentials.m45 import (
    AttestationProvenance,
    CollectorConfig,
    M45Verdict,
    RuntimeAttestationSnapshot,
    SnapshotLifecycle,
    attest_snapshot,
    check_request_readiness,
    collect_runtime_snapshot,
    create_snapshot,
    module_fingerprint,
    sign_snapshot,
    snapshot_fingerprint,
    validate_snapshot,
    verify_snapshot_integrity,
)


def _observed_cfg(**kw) -> CollectorConfig:
    base = dict(
        mode="observe",
        open_security_alerts=0,
        unresolved_incidents=0,
        rollback_active=False,
        error_budget_state="healthy",
        audit_ledger_state="intact",
        requested_rollout_percent=1,
        maximum_policy_percent=5,
        approved_scope="read_only:github_meta:/meta",
        fixed_now="2026-07-22T12:00:00+00:00",
    )
    base.update(kw)
    return CollectorConfig(**base)


def _attested(**kw) -> RuntimeAttestationSnapshot:
    return attest_snapshot(collect_runtime_snapshot(_observed_cfg(**kw)))


def _genuine_m44_request(**overrides) -> RolloutRequest:
    gs = m44.resolve_graduation_state()
    fields = dict(
        rollout_id="R-M45-1",
        operator_identity="operator:test",
        approval_timestamp="2026-07-22T00:00:00+00:00",
        expiration="2100-01-01T00:00:00+00:00",
        purpose="m45 readiness",
        scope="read_only:github_meta:/meta",
        provider=PROVIDER_ID,
        resource="github_meta:/meta",
        rollout_percent=1,
        risk_level="low",
        rollback_owner="operator:rb",
        incident_owner="operator:inc",
        policy="ReadOnlyLimited",
        approval_fingerprints=("APPROVAL_REF",),
        evidence_fingerprints=(
            gs["machine_record_fingerprint"],
            gs["review_fingerprint"],
        ),
        acknowledgements=m44.M44_ACK_TOKENS,
    )
    fields.update(overrides)
    req = RolloutRequest(**fields)
    req.operator_signature = sign_request(req)
    return req


# ── framework readiness ──────────────────────────────────────────────────────
def test_framework_state_advisory():
    s = m45.framework_status()
    assert s["state"] == m45.FRAMEWORK_STATE
    assert s["framework_ready"] is True
    assert s["authorizes_execution"] is False
    assert s["grants_anything"] is False
    assert s["hardware_attestation_supported"] is False
    assert s["m32_prohibition"] == "UNCHANGED"
    assert s["trading_guardian"] == "UNCHANGED / UNENGAGED"


def test_default_empty_snapshot_denied():
    r = validate_snapshot(RuntimeAttestationSnapshot())
    assert r["verdict"] != M45Verdict.SNAPSHOT_VALIDATED_ADVISORY_ONLY.value
    assert r["authorizes_execution"] is False


def test_valid_snapshot_grants_nothing():
    snap = _attested()
    r = validate_snapshot(snap, now="2026-07-22T12:00:00+00:00")
    assert r["verdict"] == M45Verdict.SNAPSHOT_VALIDATED_ADVISORY_ONLY.value
    assert r["authorizes_execution"] is False
    assert r["grants_anything"] is False
    assert r["alters_runtime_authority"] is False


# ── integrity / tamper ───────────────────────────────────────────────────────
def test_integrity_roundtrip():
    snap = _attested()
    v = verify_snapshot_integrity(snap)
    assert v["valid"] is True


def test_tampered_fingerprint_detected():
    snap = _attested()
    snap.integrity_fingerprint = "deadbeef" * 4
    r = validate_snapshot(snap, now="2026-07-22T12:00:00+00:00")
    assert r["verdict"] == M45Verdict.SNAPSHOT_TAMPERED.value


def test_tampered_field_breaks_signature():
    snap = _attested()
    snap.provider = "evil_provider"
    # integrity no longer matches core
    r = validate_snapshot(snap, now="2026-07-22T12:00:00+00:00")
    assert r["verdict"] in (
        M45Verdict.SNAPSHOT_TAMPERED.value,
        M45Verdict.SNAPSHOT_BLOCKED.value,
        M45Verdict.SNAPSHOT_INVALID.value,
    )
    assert r["authorizes_execution"] is False


def test_missing_signature_invalid():
    snap = _attested()
    snap.attestation_signature = ""
    v = verify_snapshot_integrity(snap)
    assert v["valid"] is False
    assert "missing_attestation_signature" in v["reasons"]


# ── expiry / time ────────────────────────────────────────────────────────────
def test_expired_snapshot():
    snap = _attested(ttl_seconds=60)
    r = validate_snapshot(snap, now="2026-07-22T14:00:00+00:00")
    assert r["verdict"] == M45Verdict.SNAPSHOT_EXPIRED.value


def test_future_generated_blocked():
    snap = _attested(fixed_now="2026-07-22T15:00:00+00:00")
    r = validate_snapshot(snap, now="2026-07-22T12:00:00+00:00")
    assert "generated_in_future" in r["blockers"]


# ── replay / duplicate ───────────────────────────────────────────────────────
def test_duplicate_snapshot_blocked():
    snap = _attested()
    r = validate_snapshot(
        snap, now="2026-07-22T12:00:00+00:00",
        seen_snapshot_ids={snap.snapshot_id})
    assert "duplicate_or_replayed_snapshot" in r["blockers"]


# ── identity / git bindings ──────────────────────────────────────────────────
def test_wrong_machine_identity():
    snap = _attested()
    r = validate_snapshot(
        snap, now="2026-07-22T12:00:00+00:00",
        expected_machine_fp="OTHER_MACHINE")
    assert "machine_identity_mismatch" in r["blockers"]


def test_wrong_process_identity():
    snap = _attested()
    r = validate_snapshot(
        snap, now="2026-07-22T12:00:00+00:00",
        expected_process_fp="OTHER_PROCESS")
    assert "process_identity_mismatch" in r["blockers"]


def test_wrong_branch():
    snap = _attested(fixed_branch="wrong-branch")
    r = validate_snapshot(
        snap, now="2026-07-22T12:00:00+00:00",
        expected_branch="milestone/m42-graduation-review")
    assert "branch_mismatch" in r["blockers"]


def test_wrong_commit():
    snap = _attested(fixed_commit="0" * 40)
    r = validate_snapshot(
        snap, now="2026-07-22T12:00:00+00:00",
        expected_commit="1" * 40)
    assert "repository_commit_mismatch" in r["blockers"]


def test_dirty_repo_when_clean_required():
    snap = _attested(fixed_dirty="dirty")
    r = validate_snapshot(
        snap, now="2026-07-22T12:00:00+00:00",
        require_clean_repo=True)
    assert "repository_not_clean" in r["blockers"]


# ── provider / scope / credential ────────────────────────────────────────────
def test_provider_mismatch():
    snap = _attested()
    # re-attest after change won't work — use expected_provider
    r = validate_snapshot(
        snap, now="2026-07-22T12:00:00+00:00",
        expected_provider="other")
    assert "provider_mismatch" in r["blockers"]


def test_scope_mismatch():
    snap = _attested(approved_scope="read_only:github_meta:/meta")
    r = validate_snapshot(
        snap, now="2026-07-22T12:00:00+00:00",
        expected_scope="read_only:github_meta:/user")
    assert "scope_mismatch" in r["blockers"]


def test_credential_reference_mismatch():
    snap = _attested(credential_reference_fingerprint="ABC")
    r = validate_snapshot(
        snap, now="2026-07-22T12:00:00+00:00",
        expected_cred_fp="XYZ")
    assert "credential_reference_mismatch" in r["blockers"]


def test_credential_missing_when_required():
    snap = _attested(credential_present=False)
    r = validate_snapshot(
        snap, now="2026-07-22T12:00:00+00:00",
        require_credential=True)
    assert "credential_missing" in r["blockers"]


def test_credential_unexpectedly_present():
    snap = _attested(credential_present=True,
                     credential_reference_kind="OS_KEYCHAIN_REFERENCE",
                     credential_reference_fingerprint="ref1")
    r = validate_snapshot(
        snap, now="2026-07-22T12:00:00+00:00",
        forbid_credential=True)
    assert "credential_unexpectedly_present" in r["blockers"]


def test_secret_read_flag_blocks_attest():
    raw = collect_runtime_snapshot(_observed_cfg())
    raw.credential_secret_read = True
    with pytest.raises(m45.M45Error):
        attest_snapshot(raw)


def test_secret_read_flag_blocks_validate():
    snap = _attested()
    # force flag after attest (tamper path)
    snap.credential_secret_read = True
    snap.integrity_fingerprint = snapshot_fingerprint(snap)
    snap.attestation_signature = sign_snapshot(snap)
    r = validate_snapshot(snap, now="2026-07-22T12:00:00+00:00")
    assert "secret_read_during_collection" in r["blockers"] or \
        "secret_read_flag_true" in r.get("blockers", []) or \
        r["verdict"] != M45Verdict.SNAPSHOT_VALIDATED_ADVISORY_ONLY.value


# ── safety switches ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("field,value,blocker", [
    ("live_network_allowed", True, "live_network_enabled"),
    ("write_operations_allowed", True, "write_operations_enabled"),
    ("deployment_allowed", True, "deployment_enabled"),
    ("rollout_execution_allowed", True, "rollout_execution_enabled"),
    ("open_security_alerts", 1, "open_security_alerts"),
    ("unresolved_incidents", 1, "unresolved_incidents"),
    ("rollback_active", True, "rollback_active"),
    ("kill_switch_active", True, "kill_switch_active"),
    ("error_budget_state", "exhausted", "error_budget_unhealthy"),
    ("audit_ledger_state", "broken", "audit_ledger_invalid"),
    ("m32_state", "PROHIBITION_CHANGED", "m32_changed"),
    ("trading_guardian_state", "ENGAGED", "trading_guardian_engaged"),
])
def test_safety_flags_block(field, value, blocker):
    snap = _attested()
    setattr(snap, field, value)
    snap.integrity_fingerprint = snapshot_fingerprint(snap)
    snap.attestation_signature = sign_snapshot(snap)
    r = validate_snapshot(snap, now="2026-07-22T12:00:00+00:00")
    assert blocker in r["blockers"]
    assert r["authorizes_execution"] is False


def test_kill_switch_env_during_collect(monkeypatch):
    snap = attest_snapshot(collect_runtime_snapshot(
        _observed_cfg(environ={"SAATHI_M39_KILL_SWITCH": "1"})))
    assert snap.kill_switch_active is True
    r = validate_snapshot(snap, now="2026-07-22T12:00:00+00:00")
    assert "kill_switch_active" in r["blockers"]


def test_percentage_above_policy():
    snap = _attested(requested_rollout_percent=50, maximum_policy_percent=5)
    r = validate_snapshot(snap, now="2026-07-22T12:00:00+00:00")
    assert "percentage_above_policy" in r["blockers"]


# ── provenance classes ───────────────────────────────────────────────────────
def test_simulated_snapshot_insufficient():
    raw = collect_runtime_snapshot(_observed_cfg(mode="simulate"))
    # manual sign without elevating
    raw.integrity_fingerprint = snapshot_fingerprint(raw)
    raw.attestation_signature = sign_snapshot(raw)
    assert raw.attestation_provenance == AttestationProvenance.SIMULATED.value
    r = validate_snapshot(raw, now="2026-07-22T12:00:00+00:00")
    assert any("provenance" in b for b in r["blockers"])


def test_self_reported_insufficient():
    raw = collect_runtime_snapshot(_observed_cfg(mode="self_report"))
    raw.integrity_fingerprint = snapshot_fingerprint(raw)
    raw.attestation_signature = sign_snapshot(raw)
    r = validate_snapshot(raw, now="2026-07-22T12:00:00+00:00")
    assert any("provenance" in b for b in r["blockers"])


def test_unsigned_machine_observed_insufficient():
    raw = collect_runtime_snapshot(_observed_cfg())
    assert raw.attestation_provenance == AttestationProvenance.LOCAL_MACHINE_OBSERVED.value
    assert not raw.attestation_signature
    r = validate_snapshot(raw, now="2026-07-22T12:00:00+00:00")
    assert r["verdict"] != M45Verdict.SNAPSHOT_VALIDATED_ADVISORY_ONLY.value


def test_hardware_attested_claim_rejected():
    snap = _attested()
    snap.attestation_provenance = AttestationProvenance.HARDWARE_ATTESTED.value
    snap.integrity_fingerprint = snapshot_fingerprint(snap)
    snap.attestation_signature = sign_snapshot(snap)
    r = validate_snapshot(
        snap, now="2026-07-22T12:00:00+00:00",
        require_provenance=(AttestationProvenance.HARDWARE_ATTESTED.value,))
    assert "hardware_attested_not_supported" in r["blockers"]


# ── evidence bindings ────────────────────────────────────────────────────────
def test_missing_m43_binding_blocks():
    snap = _attested()
    snap.m43_machine_fingerprint = ""
    snap.integrity_fingerprint = snapshot_fingerprint(snap)
    snap.attestation_signature = sign_snapshot(snap)
    r = validate_snapshot(snap, now="2026-07-22T12:00:00+00:00")
    assert "m43_binding_missing" in r["blockers"]


def test_missing_m44_completion_binding_blocks():
    snap = _attested()
    snap.m44_completion_fingerprint = ""
    snap.integrity_fingerprint = snapshot_fingerprint(snap)
    snap.attestation_signature = sign_snapshot(snap)
    r = validate_snapshot(snap, now="2026-07-22T12:00:00+00:00")
    assert "m44_completion_binding_missing" in r["blockers"]


def test_unknown_fields_make_ineligible(tmp_path):
    """Hermetic empty base ⇒ unknowns ⇒ not validated."""
    cfg = _observed_cfg(base=tmp_path)
    raw = collect_runtime_snapshot(cfg)
    assert raw.unknown_fields  # missing evidence
    snap = attest_snapshot(raw)
    r = validate_snapshot(snap, now="2026-07-22T12:00:00+00:00")
    assert "unknown_fields_present" in r["blockers"]


# ── lifecycle ledger ─────────────────────────────────────────────────────────
def test_ledger_lifecycle(tmp_path):
    p = tmp_path / "snap.jsonl"
    out = create_snapshot(_observed_cfg(), path=p, persist=True)
    sid = out["snapshot"]["snapshot_id"]
    m45.expire_snapshot(sid, path=p)
    m45.invalidate_snapshot("other", path=p)
    v = m45.verify_ledger_chain(p)
    assert v["intact"] is True
    hist = m45.show_snapshot_history(sid, p)
    assert hist["count"] >= 1
    assert m45.list_snapshots(p)["count"] >= 1


def test_ledger_tamper_detected(tmp_path):
    p = tmp_path / "snap.jsonl"
    create_snapshot(_observed_cfg(), path=p, persist=True)
    lines = p.read_text().splitlines()
    bad = json.loads(lines[0])
    bad["payload"]["snapshot_id"] = "TAMPER"
    p.write_text(json.dumps(bad) + "\n")
    v = m45.verify_ledger_chain(p)
    assert v["intact"] is False


# ── M44 integration ──────────────────────────────────────────────────────────
def test_to_m44_runtime_clears_gates():
    snap = _attested()
    rt = m45.to_m44_runtime_snapshot(snap, operator_approval_present=True)
    blockers = m44.runtime_gate_blockers(rt)
    assert blockers == []


def test_readiness_with_genuine_chain():
    snap = _attested(
        requested_rollout_percent=1,
        maximum_policy_percent=5,
        fixed_dirty="clean",
    )
    req = _genuine_m44_request(rollout_percent=1)
    r = check_request_readiness(
        req, snap, now="2026-07-22T12:00:00+00:00")
    assert r["verdict"] == M45Verdict.BOUNDED_ROLLOUT_READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION.value
    assert r["ready_for_separate_operator_authorization"] is True
    assert r["authorizes_execution"] is False
    assert r["grants_anything"] is False
    assert r["requires_separate_execution_authorization"] is True


def test_readiness_still_grants_nothing():
    snap = _attested(requested_rollout_percent=1, maximum_policy_percent=5)
    req = _genuine_m44_request(rollout_percent=1)
    r = check_request_readiness(req, snap, now="2026-07-22T12:00:00+00:00")
    assert r["authorizes_execution"] is False
    assert r["alters_runtime_authority"] is False
    for v in r["authorities"].values():
        assert v == "NOT GRANTED"


def test_readiness_fails_without_attested_snapshot():
    snap = collect_runtime_snapshot(_observed_cfg())  # unsigned
    req = _genuine_m44_request()
    r = check_request_readiness(req, snap, now="2026-07-22T12:00:00+00:00")
    assert r["ready_for_separate_operator_authorization"] is False
    assert r["verdict"] == M45Verdict.REQUEST_NOT_READY.value


def test_readiness_fails_on_percent_above_ceiling():
    snap = _attested(requested_rollout_percent=1, maximum_policy_percent=5)
    req = _genuine_m44_request(rollout_percent=25)  # above ReadOnlyLimited also
    # re-sign after percent change
    req.operator_signature = sign_request(req)
    r = check_request_readiness(req, snap, now="2026-07-22T12:00:00+00:00")
    assert r["ready_for_separate_operator_authorization"] is False


def test_stale_request_expired():
    snap = _attested(requested_rollout_percent=1, maximum_policy_percent=5)
    req = _genuine_m44_request(
        approval_timestamp="2020-01-01T00:00:00+00:00",
        expiration="2020-01-02T00:00:00+00:00")
    req.operator_signature = sign_request(req)
    r = check_request_readiness(req, snap, now="2026-07-22T12:00:00+00:00")
    assert r["ready_for_separate_operator_authorization"] is False


# ── schema / leak / determinism ──────────────────────────────────────────────
def test_outputs_leak_clean():
    snap = _attested()
    assert is_clean(snap.to_public())
    assert is_clean(validate_snapshot(snap, now="2026-07-22T12:00:00+00:00"))
    assert is_clean(m45.framework_status())
    assert is_clean(m45.simulate())
    assert is_clean(m45.build_runtime_attestation_completion())


def test_evidence_bundle_clean():
    bundle = m45.build_m45_evidence()
    for name, body in bundle.items():
        assert is_clean(body), name
    assert bundle["summary"]["state"] == m45.FRAMEWORK_STATE
    assert bundle["summary"]["authorizes_execution"] is False


def test_module_fingerprint_stable():
    assert module_fingerprint() == module_fingerprint()


def test_fingerprint_deterministic():
    snap = _attested(fixed_machine_fp="M", fixed_process_fp="P",
                     fixed_commit="C", fixed_branch="B", fixed_dirty="clean")
    a = snapshot_fingerprint(snap)
    b = snapshot_fingerprint(snap)
    assert a == b


def test_malformed_schema_blocked():
    snap = _attested()
    snap.schema_version = "wrong"
    snap.integrity_fingerprint = snapshot_fingerprint(snap)
    snap.attestation_signature = sign_snapshot(snap)
    r = validate_snapshot(snap, now="2026-07-22T12:00:00+00:00")
    assert "schema_invalid" in r["blockers"] or r["verdict"] != \
        M45Verdict.SNAPSHOT_VALIDATED_ADVISORY_ONLY.value


def test_m32_prohibition_intact():
    from saathi.connectors.providers.models import M32_PROHIBITED_MODES, ExecutionMode
    assert ExecutionMode.CANARY in M32_PROHIBITED_MODES
    assert ExecutionMode.ACTIVE in M32_PROHIBITED_MODES


def test_completion_bindings_present():
    c = m45.build_runtime_attestation_completion()
    assert c["verdict"] == m45.FRAMEWORK_STATE
    assert c["bindings"]["m43_machine_fingerprint"]
    assert c["bindings"]["m44_completion_fingerprint"]
    assert c["bindings"]["m45_module_fingerprint"] == module_fingerprint()
    assert c["authorizes_execution"] is False
    assert c["hardware_attestation_supported"] is False


def test_lifecycle_enum_complete():
    names = {s.value for s in SnapshotLifecycle}
    for required in ("CREATED", "VALIDATED", "ELIGIBLE_ADVISORY_ONLY", "EXPIRED",
                     "INVALIDATED", "SUPERSEDED", "REVOKED", "TAMPERED", "BLOCKED"):
        assert required in names
