"""M44 — Limited Rollout Authorization Framework tests (offline; deterministic).

M44 grants NOTHING. The maximal verdict is advisory-only. These tests prove
fail-closed behaviour: deny-by-default, tamper-evidence, bounded percentages,
policy enforcement, evidence-chain requirements, and no authority anywhere.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from saathi.credentials import m44
from saathi.credentials.m44 import (
    M44Verdict,
    RolloutRequest,
    RuntimeSnapshot,
    RollbackTrigger,
    EvidenceDescriptor,
    sign_request,
    validate_request,
)
from saathi.credentials.leakscan import is_clean
from saathi.credentials.m39 import PROVIDER_ID


# ── helpers ──────────────────────────────────────────────────────────────────
def _evidence_index():
    return {
        "M43FP": EvidenceDescriptor("M43FP", "m43_machine_canary",
                                    machine_verified_live=True, credential_lifecycle_closed=True),
        "M42FP": EvidenceDescriptor("M42FP", "m42_graduation", graduation_recommended=True),
    }


def _valid_request(policy="ReadOnlyLimited", percent=5, **over):
    req = RolloutRequest(
        rollout_id="R-0001",
        operator_identity="operator:alice",
        approval_timestamp="2026-07-22T00:00:00+00:00",
        expiration="2100-01-01T00:00:00+00:00",
        purpose="bounded read-only canary of github_meta",
        scope="read_only:github_meta:/meta",
        provider=PROVIDER_ID,
        resource="github_meta:/meta",
        rollout_percent=percent,
        risk_level="low",
        rollback_owner="operator:bob",
        incident_owner="operator:carol",
        policy=policy,
        approval_fingerprints=("APPROVAL_FP_1",),
        evidence_fingerprints=("M43FP", "M42FP"),
        acknowledgements=m44.M44_ACK_TOKENS,
    )
    for k, v in over.items():
        setattr(req, k, v)
    req.operator_signature = sign_request(req)
    return req


def _validate(req, **kw):
    kw.setdefault("now", "2026-07-22T00:00:00+00:00")
    kw.setdefault("evidence_index", _evidence_index())
    kw.setdefault("runtime", RuntimeSnapshot(machine_proof_present=True,
                                             operator_approval_present=True))
    return validate_request(req, **kw)


# ── framework readiness / advisory-only ──────────────────────────────────────
def test_framework_state_is_ready_advisory():
    s = m44.framework_status()
    assert s["state"] == "ROLLOUT_AUTHORIZATION_FRAMEWORK_READY"   # canonical
    assert s["state_legacy_alias"] == "ROLL_OUT_AUTHORIZATION_FRAMEWORK_READY"
    assert s["state"] != "PRODUCTION_READY"
    assert s["framework_ready"] is True
    assert s["advisory_only"] is True
    assert s["authorizes_execution"] is False
    assert s["alters_runtime_authority"] is False


def test_framework_grants_nothing():
    s = m44.framework_status()
    for k in ("grants_anything", "grants_active", "grants_production",
              "grants_write", "expands_scope"):
        assert s[k] is False
    assert s["requires_separate_execution_authorization"] is True
    assert s["trading_guardian"] == "UNCHANGED / UNENGAGED"
    assert s["m32_prohibition"] == "UNCHANGED"


# ── deny-by-default ──────────────────────────────────────────────────────────
def test_empty_request_denied_incomplete():
    r = validate_request(RolloutRequest())
    assert r["verdict"] == M44Verdict.ROLLOUT_REQUEST_INCOMPLETE.value
    assert r["authorizes_execution"] is False
    assert any(b.startswith("missing:") for b in r["blockers"])


def test_each_missing_mandatory_field_denies():
    for f in m44.MANDATORY_FIELDS:
        req = _valid_request()
        empty = () if isinstance(getattr(req, f), tuple) else (
            None if f == "rollout_percent" else "")
        setattr(req, f, empty)
        req.operator_signature = sign_request(req)
        r = _validate(req)
        assert r["verdict"] != M44Verdict.ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY.value, f


# ── positive path ────────────────────────────────────────────────────────────
def test_valid_request_advisory_only():
    r = _validate(_valid_request())
    assert r["verdict"] == M44Verdict.ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY.value
    assert r["blockers"] == []
    # even a VALIDATED verdict authorizes nothing:
    assert r["authorizes_execution"] is False
    assert r["grants_anything"] is False
    assert r["requires_separate_execution_authorization"] is True
    assert r["advisory_only"] is True


def test_all_builtin_policies_have_no_live_execution():
    for name, pol in m44.POLICIES.items():
        assert pol.permits_live_execution is False, name


# ── tampering / signature ────────────────────────────────────────────────────
def test_tampered_field_breaks_signature():
    req = _valid_request()
    req.rollout_percent = 2  # change after signing
    r = _validate(req)
    assert "operator_signature_invalid" in r["blockers"]
    assert r["verdict"] == M44Verdict.ROLLOUT_VALIDATION_FAILED.value


def test_missing_signature_denied():
    req = _valid_request()
    req.operator_signature = ""
    r = _validate(req)
    assert "operator_signature_invalid" in r["blockers"]


def test_wrong_operator_signature_denied():
    req = _valid_request()
    req.operator_signature = sign_request(req, operator_identity="operator:mallory")
    r = _validate(req)
    assert "operator_signature_invalid" in r["blockers"]


# ── expiration ───────────────────────────────────────────────────────────────
def test_expired_authorization_denied():
    req = _valid_request(expiration="2026-07-21T00:00:00+00:00")
    r = _validate(req, now="2026-07-22T00:00:00+00:00")
    assert "authorization_expired" in r["blockers"]


def test_approval_after_expiration_denied():
    req = _valid_request(approval_timestamp="2101-01-01T00:00:00+00:00",
                         expiration="2100-01-01T00:00:00+00:00")
    r = _validate(req, now="2026-07-22T00:00:00+00:00")
    assert "approval_after_expiration" in r["blockers"]


def test_unparseable_timestamp_denied():
    req = _valid_request(expiration="not-a-date")
    r = _validate(req)
    assert "timestamp_unparseable" in r["blockers"]


# ── provider / identity / scope ──────────────────────────────────────────────
def test_wrong_provider_denied():
    req = _valid_request(provider="stripe_meta")
    r = _validate(req)
    assert "provider_mismatch" in r["blockers"]


def test_scope_not_allowed_denied():
    req = _valid_request(scope="write:github_meta:/repos")
    r = _validate(req)
    assert "scope_not_allowed" in r["blockers"]


def test_risk_level_not_allowed_by_policy():
    # ProductionCandidate allows only low/medium
    req = _valid_request(policy="ProductionCandidate", percent=5, risk_level="critical")
    r = _validate(req)
    assert "risk_level_not_allowed" in r["blockers"]


# ── percentage guard ─────────────────────────────────────────────────────────
def test_percentage_negative_rejected():
    pol = m44.get_policy("ReadOnlyExtended")
    b = m44.check_percentage(pol, -1)
    assert "percentage_negative" in b


def test_percentage_above_policy_rejected():
    pol = m44.get_policy("ReadOnlyLimited")   # max 5
    b = m44.check_percentage(pol, 10)
    assert "percentage_above_policy_ceiling" in b


def test_percentage_fractional_rejected():
    pol = m44.get_policy("ReadOnlyExtended")
    b = m44.check_percentage(pol, 2.5)
    assert "percentage_not_integer" in b


def test_percentage_missing_rejected():
    pol = m44.get_policy("ReadOnlyExtended")
    assert m44.check_percentage(pol, None) == ["percentage_missing"]


def test_percentage_off_policy_step_rejected():
    pol = m44.get_policy("ReadOnlyLimited")   # allows 1,2,5 only
    b = m44.check_percentage(pol, 25)
    assert "percentage_not_permitted_by_policy" in b


def test_percentage_bool_rejected():
    pol = m44.get_policy("ReadOnlyExtended")
    assert "percentage_not_integer" in m44.check_percentage(pol, True)


# ── evidence chain ───────────────────────────────────────────────────────────
def test_missing_machine_proof_denied():
    idx = {"M42FP": EvidenceDescriptor("M42FP", "m42_graduation", graduation_recommended=True)}
    req = _valid_request(evidence_fingerprints=("M42FP",))
    r = _validate(req, evidence_index=idx)
    assert "machine_proof_absent" in r["blockers"]


def test_unresolved_evidence_denied():
    req = _valid_request(evidence_fingerprints=("UNKNOWN_FP",))
    r = _validate(req, evidence_index=_evidence_index())
    assert "evidence_chain_unresolved" in r["blockers"]


def test_credential_not_closed_denied():
    idx = {
        "M43FP": EvidenceDescriptor("M43FP", "m43_machine_canary",
                                    machine_verified_live=True, credential_lifecycle_closed=False),
        "M42FP": EvidenceDescriptor("M42FP", "m42_graduation", graduation_recommended=True),
    }
    r = _validate(_valid_request(), evidence_index=idx)
    assert "credential_lifecycle_not_closed" in r["blockers"]


def test_graduation_not_recommended_denied():
    idx = {
        "M43FP": EvidenceDescriptor("M43FP", "m43_machine_canary",
                                    machine_verified_live=True, credential_lifecycle_closed=True),
        "M42FP": EvidenceDescriptor("M42FP", "m42_graduation", graduation_recommended=False),
    }
    r = _validate(_valid_request(), evidence_index=idx)
    assert "graduation_not_recommended" in r["blockers"]


def test_dryrun_needs_no_evidence_chain():
    # DryRun requires no machine proof / graduation; 0% only.
    req = _valid_request(policy="DryRun", percent=0)
    r = _validate(req, evidence_index={})
    assert "machine_proof_absent" not in r["blockers"]


# ── runtime safety gates ─────────────────────────────────────────────────────
def test_default_runtime_snapshot_blocks():
    b = m44.runtime_gate_blockers(RuntimeSnapshot())
    assert "machine_proof_absent" in b
    assert "operator_approval_absent" in b


@pytest.mark.parametrize("flag,blocker", [
    ("identity_drift", "identity_drift"),
    ("provider_mismatch", "provider_mismatch"),
    ("credential_mismatch", "credential_mismatch"),
    ("rollback_active", "rollback_active"),
    ("kill_switch_active", "kill_switch_active"),
    ("incident_unresolved", "incident_unresolved"),
    ("security_alert_open", "security_alert_open"),
    ("trading_guardian_active", "trading_guardian_active"),
    ("m32_prohibition_violated", "m32_prohibition_violated"),
])
def test_each_unsafe_condition_blocks(flag, blocker):
    snap = RuntimeSnapshot(machine_proof_present=True, operator_approval_present=True)
    setattr(snap, flag, True)
    assert blocker in m44.runtime_gate_blockers(snap)


def test_kill_switch_env_blocks():
    snap = RuntimeSnapshot(machine_proof_present=True, operator_approval_present=True)
    b = m44.runtime_gate_blockers(snap, environ={"SAATHI_M39_KILL_SWITCH": "1"})
    assert "kill_switch_active" in b


def test_validation_blocked_by_runtime_gate():
    r = _validate(_valid_request(),
                  runtime=RuntimeSnapshot(machine_proof_present=True,
                                          operator_approval_present=True,
                                          security_alert_open=True))
    assert "gate:security_alert_open" in r["blockers"]


# ── rollback contracts ───────────────────────────────────────────────────────
def test_rollback_deterministic_no_trigger():
    d = m44.evaluate_rollback({})
    assert d["rollback_required"] is False
    assert d["deterministic"] is True


def test_rollback_fires_on_trigger():
    d = m44.evaluate_rollback({RollbackTrigger.ERROR_BUDGET_EXCEEDED.value: True})
    assert d["rollback_required"] is True
    assert "error_budget_exceeded" in d["triggers_fired"]
    assert d["rollback_kind"] == "automatic"


def test_all_rollback_triggers_recognized():
    for t in RollbackTrigger:
        d = m44.evaluate_rollback({t.value: True})
        assert t.value in d["triggers_fired"]


# ── policy registry / extensibility ──────────────────────────────────────────
def test_unknown_policy_denied():
    req = _valid_request(policy="DoesNotExist")
    r = _validate(req)
    assert any("unknown_policy" in b for b in r["blockers"])


def test_register_policy_rejects_live_execution():
    bad = m44.RolloutPolicy(
        name="Rogue", max_percent=5, allowed_percents=(1,),
        allowed_scopes=m44.ALLOWED_SCOPES, allowed_providers=frozenset({PROVIDER_ID}),
        allowed_risk_levels=frozenset({"low"}), required_acknowledgements=m44.M44_ACK_TOKENS,
        requires_machine_proof=True, requires_closed_credential=True,
        requires_graduation_recommended=True, permits_live_execution=True)
    with pytest.raises(m44.M44Error):
        m44.register_policy(bad)


def test_register_valid_policy_then_use(tmp_path):
    pol = m44.RolloutPolicy(
        name="ReadOnlyTiny", max_percent=1, allowed_percents=(1,),
        allowed_scopes=m44.ALLOWED_SCOPES, allowed_providers=frozenset({PROVIDER_ID}),
        allowed_risk_levels=frozenset({"low"}), required_acknowledgements=m44.M44_ACK_TOKENS,
        requires_machine_proof=True, requires_closed_credential=True,
        requires_graduation_recommended=True, permits_live_execution=False)
    m44.register_policy(pol)
    try:
        req = _valid_request(policy="ReadOnlyTiny", percent=1)
        r = _validate(req)
        assert r["verdict"] == M44Verdict.ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY.value
    finally:
        m44.POLICIES.pop("ReadOnlyTiny", None)


# ── ledger: immutability / hash chain ────────────────────────────────────────
def test_ledger_append_and_chain(tmp_path):
    p = tmp_path / "ledger.jsonl"
    m44.append_ledger(m44.LedgerEvent.CREATED, {"rollout_id": "R1"}, p)
    m44.append_ledger(m44.LedgerEvent.VALIDATED, {"rollout_id": "R1", "verdict": "x"}, p)
    chain = m44.verify_ledger_chain(p)
    assert chain["intact"] is True
    assert chain["entries"] == 2


def test_ledger_tamper_detected(tmp_path):
    p = tmp_path / "ledger.jsonl"
    m44.append_ledger(m44.LedgerEvent.CREATED, {"rollout_id": "R1"}, p)
    m44.append_ledger(m44.LedgerEvent.VALIDATED, {"rollout_id": "R1", "verdict": "x"}, p)
    lines = p.read_text().splitlines()
    entry = json.loads(lines[0])
    entry["payload"]["rollout_id"] = "TAMPERED"
    lines[0] = json.dumps(entry, sort_keys=True)
    p.write_text("\n".join(lines) + "\n")
    chain = m44.verify_ledger_chain(p)
    assert chain["intact"] is False
    assert chain["broken_at"] == 0


def test_create_and_review_persist(tmp_path):
    p = tmp_path / "ledger.jsonl"
    req = _valid_request()
    m44.create_rollout(req, path=p, persist=True)
    m44.review_rollout(req, path=p, persist=True,
                       now="2026-07-22T00:00:00+00:00",
                       evidence_index=_evidence_index(),
                       runtime=RuntimeSnapshot(machine_proof_present=True,
                                               operator_approval_present=True))
    assert m44.verify_ledger_chain(p)["intact"] is True
    show = m44.audit_show_rollout("R-0001", p)
    assert show["count"] == 2


# ── audit API: read-only, no secrets ─────────────────────────────────────────
def test_audit_endpoints_leak_clean(tmp_path):
    p = tmp_path / "ledger.jsonl"
    req = _valid_request()
    m44.create_rollout(req, path=p, persist=True)
    m44.review_rollout(req, path=p, persist=True,
                       now="2026-07-22T00:00:00+00:00",
                       evidence_index=_evidence_index(),
                       runtime=RuntimeSnapshot(machine_proof_present=True,
                                               operator_approval_present=True))
    for fn in (m44.audit_show_rollout, m44.audit_show_approvals,
               m44.audit_show_evidence_chain, m44.audit_show_validation,
               m44.audit_show_rollback_history, m44.audit_show_incident_history):
        out = fn("R-0001", p)
        assert is_clean(out), fn.__name__
        assert out["contains_secret_values"] is False


def test_audit_validation_reports_verdict(tmp_path):
    p = tmp_path / "ledger.jsonl"
    req = _valid_request()
    m44.review_rollout(req, path=p, persist=True,
                       now="2026-07-22T00:00:00+00:00",
                       evidence_index=_evidence_index(),
                       runtime=RuntimeSnapshot(machine_proof_present=True,
                                               operator_approval_present=True))
    v = m44.audit_show_validation("R-0001", p)
    assert v["verdict"] == M44Verdict.ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY.value


# ── schema / serialization ───────────────────────────────────────────────────
def test_validation_result_serializable_and_clean():
    r = _validate(_valid_request())
    s = json.dumps(r, sort_keys=True)
    assert json.loads(s)["verdict"] == r["verdict"]
    assert is_clean(r)


def test_request_fingerprint_deterministic():
    a = _valid_request()
    b = _valid_request()
    assert m44.request_fingerprint(a) == m44.request_fingerprint(b)


def test_request_fingerprint_changes_on_edit():
    a = _valid_request()
    fp1 = m44.request_fingerprint(a)
    a.rollout_percent = 2
    assert m44.request_fingerprint(a) != fp1


def test_policy_fingerprint_stable():
    assert m44.get_policy("ReadOnlyLimited").fingerprint() == \
           m44.get_policy("ReadOnlyLimited").fingerprint()


# ── security regression: no authority, no secrets anywhere ───────────────────
def test_no_secret_material_in_any_output():
    outputs = [m44.framework_status(), m44.simulate("Simulation"),
               _validate(_valid_request()), m44.build_m44_evidence()]
    for o in outputs:
        assert is_clean(o)


def test_leaky_ledger_payload_refused(tmp_path):
    p = tmp_path / "ledger.jsonl"
    with pytest.raises(AssertionError):
        m44.append_ledger(m44.LedgerEvent.CREATED,
                          {"rollout_id": "R1", "token": "ghp_" + "a" * 36}, p)


def test_simulation_is_not_live():
    sim = m44.simulate("Simulation")
    assert sim["mode"] == "SIMULATED_NOT_LIVE"
    assert sim["authorizes_execution"] is False
    assert sim["grants_anything"] is False


def test_evidence_bundle_state_advisory():
    ev = m44.build_m44_evidence()
    assert ev["summary"]["state"] == "ROLLOUT_AUTHORIZATION_FRAMEWORK_READY"
    assert ev["summary"]["state_legacy_alias"] == "ROLL_OUT_AUTHORIZATION_FRAMEWORK_READY"
    assert ev["summary"]["authorizes_execution"] is False
    assert ev["summary"]["alters_runtime_authority"] is False
    assert ev["summary"]["grants_anything"] is False


# ══ M44.1 — evidence precedence & provenance verification ═════════════════════
def _genuine_machine_record():
    return {
        "source": "MACHINE", "machine_verified": True, "machine_verified_live": True,
        "credential_lifecycle": {"status": "CLOSED", "http_401_confirmed": True},
        "contains_secret_values": False,
    }


def test_verify_genuine_machine_record():
    v = m44.verify_machine_record(_genuine_machine_record())
    assert v["verified"] is True
    assert v["provenance"] == m44.PROV_MACHINE_PROOF
    assert v["reasons"] == []


def test_verify_operator_attested_rejected():
    rec = _genuine_machine_record()
    rec["source"] = "OPERATOR_ATTESTED"
    v = m44.verify_machine_record(rec)
    assert v["verified"] is False
    assert v["provenance"] == m44.PROV_OPERATOR_ATTESTED


def test_verify_simulated_rejected():
    rec = _genuine_machine_record()
    rec["source"] = "SIMULATED_REHEARSAL"
    v = m44.verify_machine_record(rec)
    assert v["verified"] is False
    assert v["provenance"] == m44.PROV_SIMULATED
    assert "source_simulated" in v["reasons"]


def test_verify_machine_verified_but_not_live_rejected():
    rec = _genuine_machine_record()
    rec["machine_verified_live"] = False
    v = m44.verify_machine_record(rec)
    assert v["verified"] is False
    assert "not_machine_verified_live" in v["reasons"]


def test_verify_lifecycle_not_closed_rejected():
    rec = _genuine_machine_record()
    rec["credential_lifecycle"]["status"] = "OPEN"
    v = m44.verify_machine_record(rec)
    assert v["verified"] is False
    assert "credential_lifecycle_not_closed" in v["reasons"]


def test_verify_missing_http_401_rejected():
    rec = _genuine_machine_record()
    rec["credential_lifecycle"]["http_401_confirmed"] = False
    v = m44.verify_machine_record(rec)
    assert v["verified"] is False
    assert "http_401_not_confirmed" in v["reasons"]


def test_verify_empty_record_rejected():
    v = m44.verify_machine_record({})
    assert v["verified"] is False
    assert v["provenance"] == m44.PROV_ABSENT


def test_resolve_uses_live_review_not_stale_file():
    """M44 must derive graduation from the live machine-override-aware M42 review,
    never from the stale stored graduation_recommendation.json string."""
    import json as _json
    stale = _json.load(open("docs/evidence/m42/graduation_recommendation.json"))
    stale_fp = stale.get("fingerprint")
    assert stale.get("recommendation") == "GRADUATION_NOT_RECOMMENDED"   # the stale string
    gs = m44.resolve_graduation_state()
    # the resolved review fingerprint is the LIVE one, not the stale file's
    assert gs["review_fingerprint"] != stale_fp
    idx = m44.load_evidence_index()
    assert stale_fp not in idx                       # stale artifact never indexed


def test_resolve_genuine_chain_recommended_machine_proof():
    gs = m44.resolve_graduation_state()
    assert gs["recommendation"] == "GRADUATION_RECOMMENDED"
    assert gs["provenance"] == m44.PROV_MACHINE_PROOF
    assert gs["graduation_recommended"] is True
    assert gs["machine_record_verified"] is True


def test_graduation_requires_verified_machine_record(tmp_path):
    """Defence in depth: even if the live M42 review recommends, a missing/invalid
    machine record at the resolution base yields graduation_recommended False —
    a stale artifact cannot ride on the review string alone."""
    gs = m44.resolve_graduation_state(base=tmp_path)   # no machine record here
    assert gs["machine_record_verified"] is False
    assert gs["graduation_recommended"] is False       # regardless of live review


def test_stale_index_cannot_satisfy_graduation(tmp_path):
    idx = m44.load_evidence_index(base=tmp_path)        # machine record absent
    grad_descs = [d for d in idx.values() if d.kind == "m42_graduation"]
    assert all(d.graduation_recommended is False for d in grad_descs)


# ══ M44.1 — genuine end-to-end integration (real on-disk evidence) ════════════
def _genuine_request():
    gs = m44.resolve_graduation_state()
    req = RolloutRequest(
        rollout_id="R-GENUINE-1", operator_identity="operator:ajay",
        approval_timestamp="2026-07-22T00:00:00+00:00",
        expiration="2100-01-01T00:00:00+00:00",
        purpose="bounded read-only canary against genuine M43.1 chain",
        scope="read_only:github_meta:/meta", provider=PROVIDER_ID,
        resource="github_meta:/meta", rollout_percent=5, risk_level="low",
        rollback_owner="operator:rb", incident_owner="operator:inc",
        policy="ReadOnlyLimited",
        approval_fingerprints=("APPROVAL_REF",),
        evidence_fingerprints=(gs["machine_record_fingerprint"], gs["review_fingerprint"]),
        acknowledgements=m44.M44_ACK_TOKENS)
    req.operator_signature = sign_request(req)
    return req


def test_genuine_request_reaches_advisory_only():
    req = _genuine_request()
    r = validate_request(
        req, now="2026-07-22T00:00:00+00:00",
        evidence_index=m44.load_evidence_index(),          # real on-disk resolution
        runtime=RuntimeSnapshot(machine_proof_present=True, operator_approval_present=True))
    assert r["verdict"] == M44Verdict.ROLLOUT_AUTHORIZATION_VALIDATED_ADVISORY_ONLY.value
    # advisory only — still authorizes nothing:
    assert r["authorizes_execution"] is False
    assert r["alters_runtime_authority"] is False
    assert r["grants_anything"] is False
    assert r["requires_separate_execution_authorization"] is True
    assert m44.PROV_MACHINE_PROOF in r["evidence_provenance"]


def test_unreferenced_machine_record_cannot_authorize():
    """An on-disk machine record that the request does NOT reference must not
    silently satisfy the machine-proof criterion."""
    req = _genuine_request()
    req.evidence_fingerprints = (m44.resolve_graduation_state()["review_fingerprint"],)  # drop machine fp
    req.operator_signature = sign_request(req)
    r = validate_request(
        req, now="2026-07-22T00:00:00+00:00",
        evidence_index=m44.load_evidence_index(),
        runtime=RuntimeSnapshot(machine_proof_present=True, operator_approval_present=True))
    assert "machine_proof_absent" in r["blockers"]
    assert r["verdict"] == M44Verdict.ROLLOUT_VALIDATION_FAILED.value


def test_request_fingerprints_must_resolve():
    req = _genuine_request()
    req.evidence_fingerprints = ("NONEXISTENT_FP",)
    req.operator_signature = sign_request(req)
    r = validate_request(
        req, now="2026-07-22T00:00:00+00:00",
        evidence_index=m44.load_evidence_index(),
        runtime=RuntimeSnapshot(machine_proof_present=True, operator_approval_present=True))
    assert "evidence_chain_unresolved" in r["blockers"]


def test_validation_reports_evidence_provenance():
    r = _validate(_valid_request())
    assert "evidence_provenance" in r
    assert r["alters_runtime_authority"] is False


def test_verify_provider_mismatch_rejected():
    rec = _genuine_machine_record()
    rec["provider"] = "not_github_meta"
    v = m44.verify_machine_record(rec)
    assert v["verified"] is False
    assert "provider_mismatch" in v["reasons"]


def test_verify_identity_mismatch_rejected():
    rec = _genuine_machine_record()
    rec["machine_signals"] = dict(rec.get("machine_signals") or {}, identity="changed")
    v = m44.verify_machine_record(rec)
    assert v["verified"] is False
    assert "identity_mismatch" in v["reasons"]


def test_verify_scope_mismatch_rejected():
    rec = _genuine_machine_record()
    rec["machine_signals"] = dict(rec.get("machine_signals") or {}, scope="write_expanded")
    v = m44.verify_machine_record(rec)
    assert v["verified"] is False
    assert "scope_mismatch" in v["reasons"]


def test_isolated_base_does_not_use_real_repo_machine_proof(tmp_path):
    """Hermetic base without evidence must not inherit real-repo RECOMMENDED state."""
    gs = m44.resolve_graduation_state(base=tmp_path)
    assert gs["machine_record_verified"] is False
    assert gs["graduation_recommended"] is False
    # live review against empty m42 base must not recommend
    assert gs["recommendation"] in (
        "GRADUATION_NOT_RECOMMENDED", "GRADUATION_BLOCKED",
        "GRADUATION_REVIEW_UNAVAILABLE",
    ) or gs["recommendation"] != "GRADUATION_RECOMMENDED" or not gs["graduation_recommended"]


def test_framework_completion_advisory_only():
    c = m44.build_framework_completion()
    assert c["schema"] == "m44.framework_completion.v1"
    assert c["verdict"] == m44.FRAMEWORK_STATE
    assert c["authorizes_execution"] is False
    assert c["grants_anything"] is False
    assert c["alters_runtime_authority"] is False
    assert c["runtime_execution_authority"] is False
    assert c["m32_prohibition"] == "UNCHANGED"
    assert c["trading_guardian"] == "UNCHANGED / UNENGAGED"
    assert c["deployment"] is False and c["push"] is False
    assert c["contains_secret_values"] is False
    assert is_clean(c)
    # genuine chain is reflected without trusting the stale static string
    assert c["evidence_resolution"]["stale_static_file_not_trusted"] == m44.M42_GRADUATION_PATH
    assert c["evidence_resolution"]["machine_record_verified"] is True
    assert c["evidence_resolution"]["graduation_recommended_advisory"] is True
    assert c["module_fingerprint"] == m44.module_fingerprint()
