"""M43 — Machine-verified bounded canary tests (offline; deterministic; fail-closed).

M43 grants nothing. A real in-session live run is required for MACHINE_PROOF; the
rehearsal is SIMULATED and must NOT clear AB-PROV. No fabricated live evidence.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from saathi.credentials import m43, m42, m41
from saathi.credentials.leakscan import is_clean


def _val_ok():
    return {"ok": True, "live_network": True,
            "verifications": {k: True for k in
                              ["endpoint_identity_bound", "bounded_read_only_completed",
                               "cleanup_complete", "secret_handle_destroyed", "budget_compliant",
                               "rollback_state_clean", "zero_error_budget_held", "no_rollback_triggered"]}}


def _rev_ok():
    return {"ok": True, "http_401_confirmed": True, "revocation_effective": True,
            "secret_handle_destroyed": True}


# ── deny-by-default / fail-closed ────────────────────────────────────────────
def test_default_no_credential_blocked():
    b = m43.run_machine_verified_canary(m43.M43Config())
    assert b["verdict"] == "MACHINE_CANARY_BLOCKED"
    assert b["machine_verified"] is False


def test_kill_switch_blocks():
    b = m43.run_machine_verified_canary(
        m43.M43Config(environ={"SAATHI_M39_KILL_SWITCH": "1"}))
    assert b["verdict"] == "MACHINE_CANARY_BLOCKED"


def test_missing_approval_blocks():
    approval, cert = m41._valid_rehearsal_records()
    cfg = m43.M43Config(mode="rehearsal", m40_cert_record=cert)  # no approval
    b = m43.run_machine_verified_canary(cfg)
    assert b["verdict"] == "MACHINE_CANARY_BLOCKED"


def test_grants_nothing_everywhere():
    for body in (m43.run_machine_verified_canary(m43.M43Config()), m43.run_rehearsal()):
        assert body["grants_anything"] is False
        assert body["grants_active"] is False and body["grants_production"] is False
        assert body["grants_write"] is False
        assert body["m32_canary_execution_mode"] == "PROHIBITION_UNCHANGED"
        for v in body["authorities"].values():
            assert v == "NOT GRANTED"
        assert body["trading_guardian"] == "UNCHANGED / UNENGAGED"


# ── rehearsal proves flow but is SIMULATED (not machine-live) ────────────────
def test_rehearsal_flow_verified_but_simulated():
    r = m43.run_rehearsal()
    assert r["verdict"] == "MACHINE_CANARY_VERIFIED"
    assert r["validation_phase"]["ok"] is True
    assert r["revocation_phase"]["ok"] is True
    rec = r["machine_record"]
    assert rec["source"] == "SIMULATED_REHEARSAL"
    assert rec["machine_verified_live"] is False   # rehearsal is not live machine proof


def test_rehearsal_record_does_not_clear_ab_prov(tmp_path):
    # a SIMULATED rehearsal record must NOT lift AB-PROV in M42
    shutil.copytree("docs/evidence/m40", tmp_path / "m40")
    shutil.copytree("docs/evidence/m41", tmp_path / "m41")
    (tmp_path / "m43").mkdir()
    rec = m43.run_rehearsal()["machine_record"]  # SIMULATED
    (tmp_path / "m43" / "machine_verified_canary_completion.json").write_text(json.dumps(rec))
    r = m42.run_graduation_review(base=str(tmp_path))
    assert r["recommendation"] == "GRADUATION_NOT_RECOMMENDED"
    assert "AB-PROV" in r["abort_conditions_present"]


# ── machine record (live) clears AB-PROV -> RECOMMENDED (temp only) ──────────
def test_machine_record_clears_ab_prov(tmp_path):
    shutil.copytree("docs/evidence/m40", tmp_path / "m40")
    shutil.copytree("docs/evidence/m41", tmp_path / "m41")
    (tmp_path / "m43").mkdir()
    rec = m43.assemble_machine_record(_val_ok(), _rev_ok())
    assert rec["machine_verified_live"] is True and rec["machine_verified"] is True
    (tmp_path / "m43" / "machine_verified_canary_completion.json").write_text(json.dumps(rec))
    r = m42.run_graduation_review(base=str(tmp_path))
    assert r["recommendation"] == "GRADUATION_RECOMMENDED"
    assert r["abort_conditions_present"] == []


def test_machine_record_failed_revocation_not_verified():
    rec = m43.assemble_machine_record(_val_ok(), {"ok": False, "http_401_confirmed": False})
    assert rec["machine_verified"] is False
    assert rec["credential_lifecycle"]["status"] == "OPEN"


# ── phase verification: fail-closed on incomplete verification ───────────────
def test_validation_phase_fails_on_incomplete(monkeypatch):
    # force the underlying rollout to report an unclosed handle
    import saathi.credentials.m41 as m41mod

    def _bad_rollout(cfg):
        return {"verdict": "CANARY_ACTIVE_BOUNDED",
                "authorization": {"authorized": True, "blockers": []},
                "controller": {"state": "COMPLETED", "increments": [{"index": 0}],
                               "all_handles_closed": False, "live_network": True,
                               "errors": 0, "rollback_reason": ""}}
    monkeypatch.setattr(m43.m41, "run_canary_rollout", _bad_rollout)
    approval, cert = m41._valid_rehearsal_records()
    v = m43.run_validation_phase(m43.M43Config(mode="rehearsal", approval_record=approval,
                                               m40_cert_record=cert))
    assert v["ok"] is False
    assert v["verifications"]["cleanup_complete"] is False


def test_revocation_phase_token_still_valid_fails():
    # simulate a revocation retry where the token still authenticates
    import saathi.credentials.m43 as m43mod
    from saathi.credentials import m39

    def _still_valid(**kw):
        return {"ok": True, "reason": "ok", "handle_closed": True, "live_network": True}
    orig = m39.run_live_single_session
    try:
        m39.run_live_single_session = _still_valid
        # rehearsal path imports run_live_single_session from m39 at call time
        cfg = m43.M43Config(mode="live", secret_source_kind="OS_KEYCHAIN_REFERENCE",
                            secret_locator="svc:x", live_flag=True)
        rev = m43.run_revocation_phase(cfg)
        assert rev["ok"] is False
        assert rev.get("revocation_effective") is False
    finally:
        m39.run_live_single_session = orig


# ── determinism + leak + backward compat ─────────────────────────────────────
def test_evidence_deterministic_and_clean():
    a = m43.build_m43_evidence()
    b = m43.build_m43_evidence()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    for name, body in a.items():
        assert is_clean(body), name
    assert a["summary"]["grants_anything"] is False


def test_emit_evidence(tmp_path):
    res = m43.emit_m43_evidence(tmp_path)
    assert res["count"] == 3
    for p in res["written"]:
        assert is_clean(json.loads(open(p).read()))


def test_m32_prohibition_intact():
    from saathi.connectors.providers.models import M32_PROHIBITED_MODES, ExecutionMode
    assert ExecutionMode.CANARY in M32_PROHIBITED_MODES
    assert ExecutionMode.ACTIVE in M32_PROHIBITED_MODES


def test_backward_compat_intact():
    from saathi.credentials import m39_4
    assert m39_4.backward_compatibility_check()["all_present"] is True


def test_real_repo_m42_still_not_recommended():
    # no machine record on disk -> M42 must remain NOT_RECOMMENDED (no fabrication)
    assert not Path("docs/evidence/m43/machine_verified_canary_completion.json").exists()
    assert m42.run_graduation_review()["recommendation"] == "GRADUATION_NOT_RECOMMENDED"
