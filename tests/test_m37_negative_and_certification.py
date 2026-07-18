"""M37 — Negative validation matrix and security certification (offline)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.credentials.leakscan import is_clean
from saathi.credentials.m36 import M36Error, reject_forbidden_cli_argv
from saathi.credentials.m37 import (
    SecurityCertificationState,
    assess_security_certification,
    run_m37_validation,
    run_negative_validation,
    run_provider_lifecycle,
    write_m37_evidence,
    preflight_summary,
    validation_summary_body,
    compute_m37_fingerprint,
    SYNTH_SECRET,
)


def test_negative_matrix_all_pass():
    rep = run_negative_validation()
    assert rep["failed"] == 0, json.dumps([c for c in rep["cases"] if not c.get("pass")], indent=2)
    assert rep["all_handles_closed"] is True
    assert rep["all_leak_clean"] is True
    assert rep["passed"] == rep["total"]


def test_negative_no_secrets_in_report():
    rep = run_negative_validation()
    blob = json.dumps(rep)
    assert SYNTH_SECRET not in blob
    assert "ghp_" not in blob
    assert is_clean(rep)


@pytest.mark.parametrize("flag", ["--token", "--api-key", "--password", "--secret"])
def test_cli_rejects_secrets(flag):
    with pytest.raises(M36Error):
        reject_forbidden_cli_argv([flag, "x"])


def test_full_validation_offline():
    result = run_m37_validation(live_exercised=False)
    assert result["ok"] is True
    assert result["m36_regression_ok"] is True
    assert result["provider"]["contract_ok"] is True
    assert result["live_exercised"] is False
    cert = result["certification"]
    assert cert["state"] == SecurityCertificationState.SECURITY_CERTIFIED_WITH_LIMITATIONS.value
    assert cert["authorities"]["production_authorization"] == "NOT GRANTED"
    assert cert["authorities"]["rollout_authorization"] == "NOT GRANTED"
    assert cert["authorities"]["CANARY_authorization"] == "NOT GRANTED"
    assert cert["authorities"]["ACTIVE_authorization"] == "NOT GRANTED"
    assert cert["authorities"]["write_authority"] == "NOT GRANTED"
    assert result["m38_started"] is False
    assert is_clean(result)


def test_certification_proofs_present():
    result = run_m37_validation(live_exercised=False)
    proofs = result["certification"]["proofs"]
    for key in (
        "credential_isolation", "reference_only_loading", "memory_cleanup",
        "sender_isolation", "fingerprint_correctness", "scope_validation",
        "budget_enforcement", "authorization_gates", "session_lifecycle",
        "provider_abstraction", "negative_paths",
    ):
        assert proofs.get(key) is True, key
    assert proofs.get("live_sandbox_session") is False


def test_live_certification_would_require_live_flag():
    # When live_exercised=True but still fixture (operator would set), full cert possible
    life = run_provider_lifecycle(live_exercised=True)
    neg = run_negative_validation()
    cert = assess_security_certification(
        lifecycle=life, negative=neg, provider_contract_ok=True, live_exercised=True,
    )
    assert cert["state"] == SecurityCertificationState.SECURITY_CERTIFIED.value
    assert "live_sandbox_not_exercised" not in cert["limitations"]


def test_evidence_write(tmp_path):
    result = run_m37_validation(live_exercised=False)
    bodies = {
        "baseline": {"milestone": "M37", "live": False, "fingerprint": compute_m37_fingerprint()},
        "validation_summary": validation_summary_body(result),
        "security_certification": result["certification"],
        "negative_validation": result["negative"],
        "lifecycle": result["lifecycle"],
        "provider_model": result["provider"],
        "leak_scan": {"clean": True, "findings": []},
        "verification_fingerprint": {"fingerprint": compute_m37_fingerprint()},
    }
    written = write_m37_evidence(bodies, evidence_dir=str(tmp_path))
    assert len(written) == len(bodies)
    for p in Path(tmp_path).iterdir():
        assert SYNTH_SECRET not in p.read_text()
        assert is_clean(json.loads(p.read_text()))


def test_preflight_banner():
    p = preflight_summary()
    assert p["milestone"] == "M37"
    assert p["m38_started"] is False
    assert "ROLLOUT OFF" in p["banner"]


def test_rollout_remains_off_in_lifecycle():
    rec = run_provider_lifecycle()
    d = rec.to_safe_dict()
    assert d["authorities"]["rollout_authorization"] == "NOT GRANTED"
    assert d["m38_started"] is False
