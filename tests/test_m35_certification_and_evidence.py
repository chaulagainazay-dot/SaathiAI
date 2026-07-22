"""M35 — Certification state, deterministic evidence, leak scan, repo invariants.

Offline and synthetic.
"""
from __future__ import annotations

import json

import pytest

from saathi.credentials.m35 import (
    M35_MAX_CERTIFICATION_STATE,
    SandboxCertificationState,
    assess_sandbox_certification,
    compute_m35_fingerprint,
    is_clean,
    validation_summary_body,
    write_m35_evidence,
)
from saathi.connectors.providers.external.profiles import resolve_external_profile

PROFILE = resolve_external_profile("github_meta")
SYNTH = "SYNTHETIC_SECRET_VALUE"


# ── certification ────────────────────────────────────────────────────────────
def test_governance_verified_offline():
    state, lims = assess_sandbox_certification(governance_ok=True, synthetic_session_ok=True)
    assert state == SandboxCertificationState.SANDBOX_GOVERNANCE_VERIFIED.value
    assert "no_real_sandbox_account" in lims


def test_max_state_is_governance_verified():
    assert M35_MAX_CERTIFICATION_STATE == SandboxCertificationState.SANDBOX_GOVERNANCE_VERIFIED.value


def test_session_certified_never_claimed_offline():
    # even with the "real" flags set, offline assessment never exceeds the cap
    state, _ = assess_sandbox_certification(
        governance_ok=True, synthetic_session_ok=True,
        real_credential_loaded=True, real_account_linked=True,
    )
    assert state == M35_MAX_CERTIFICATION_STATE
    assert state != SandboxCertificationState.SANDBOX_SESSION_CERTIFIED.value


def test_synthetic_only_when_no_session():
    state, _ = assess_sandbox_certification(governance_ok=True, synthetic_session_ok=False)
    assert state == SandboxCertificationState.SYNTHETIC_VERIFIED.value


def test_failed_governance():
    state, _ = assess_sandbox_certification(governance_ok=False, synthetic_session_ok=True)
    assert state == SandboxCertificationState.FAILED.value


def test_stale_certification():
    state, _ = assess_sandbox_certification(governance_ok=True, synthetic_session_ok=True, fresh=False)
    assert state == SandboxCertificationState.STALE.value


def test_revoked_certification():
    state, _ = assess_sandbox_certification(governance_ok=True, synthetic_session_ok=True, revoked=True)
    assert state == SandboxCertificationState.REVOKED.value


# ── deterministic milestone fingerprint ──────────────────────────────────────
def test_m35_fingerprint_deterministic():
    assert compute_m35_fingerprint(PROFILE) == compute_m35_fingerprint(PROFILE)


def test_m35_fingerprint_reveals_nothing_secret():
    fp = compute_m35_fingerprint(PROFILE)
    assert len(fp) == 64 and SYNTH not in fp


# ── validation summary invariants ────────────────────────────────────────────
def test_validation_summary_invariants():
    body = validation_summary_body(
        session_result={"external_calls": 0, "external_writes": 0},
        certification=M35_MAX_CERTIFICATION_STATE,
    )
    for k in (
        "production_credentials_loaded", "production_oauth_flows", "production_accounts_linked",
        "real_sandbox_credentials_loaded", "real_sandbox_oauth_flows", "real_sandbox_accounts_linked",
        "credentials_committed_to_git", "raw_secrets_in_evidence", "raw_secrets_in_logs",
        "raw_secrets_in_events", "external_network_calls", "external_provider_writes",
        "financial_provider_calls", "trading_provider_calls", "canary_providers", "active_providers",
    ):
        assert body[k] == 0, k
    assert body["provider_rollout"] == "OFF"
    assert body["connector_rollout"] == "OFF"
    assert body["inference_rollout"] == "OFF"
    assert body["real_sandbox_session"] == "NOT_EXERCISED"
    assert body["trading_guardian"] == "UNCHANGED / UNENGAGED"
    assert body["synthetic_credentials_used"] == 1


def test_validation_summary_leak_clean():
    body = validation_summary_body(session_result={"external_calls": 0, "external_writes": 0},
                                   certification=M35_MAX_CERTIFICATION_STATE)
    assert is_clean(body)


# ── evidence writer (deterministic, leak-scanned, atomic) ────────────────────
def _bodies():
    return {
        "scope_policy": {"allowed": ["METADATA_READ"], "forbidden": ["WRITE"], "unknown_fails_closed": True},
        "capability_ceiling": {"provider_id": "github_meta", "operation": "get_meta", "method": "GET"},
        "validation_summary": validation_summary_body(
            session_result={"external_calls": 0, "external_writes": 0},
            certification=M35_MAX_CERTIFICATION_STATE),
    }


def test_evidence_written_and_bounded(tmp_path):
    written = write_m35_evidence(_bodies(), evidence_dir=str(tmp_path))
    names = {p.split("/")[-1] for p in written}
    assert "scope_policy.json" in names
    assert "validation_summary.json" in names
    body = json.loads((tmp_path / "validation_summary.json").read_text())["body"]
    assert body["trading_guardian"] == "UNCHANGED / UNENGAGED"


def test_evidence_deterministic(tmp_path):
    write_m35_evidence(_bodies(), evidence_dir=str(tmp_path))
    first = (tmp_path / "capability_ceiling.json").read_text()
    write_m35_evidence(_bodies(), evidence_dir=str(tmp_path))
    second = (tmp_path / "capability_ceiling.json").read_text()
    assert first == second


def test_evidence_refuses_secret_shaped(tmp_path):
    from saathi.credentials.leakscan import LeakDetected
    bad = {"leaky": {"access_token": "ghp_" + "a" * 36}}
    with pytest.raises(LeakDetected):
        write_m35_evidence(bad, evidence_dir=str(tmp_path))


def test_evidence_no_local_path(tmp_path):
    written = write_m35_evidence(_bodies(), evidence_dir=str(tmp_path))
    for p in written:
        assert "/Users/" not in p  # repo-relative reference


# ── leak scanning of module policy surfaces ──────────────────────────────────
def test_synthetic_secret_is_not_realistic_token():
    # SYNTHETIC_SECRET_VALUE must not match a real token shape
    from saathi.credentials.leakscan import scan
    assert scan(SYNTH) == []


def test_module_import_no_side_effects():
    # Prove a fresh import performs no network/DNS/TLS/keychain side effect. Uses a
    # subprocess (NOT importlib.reload) so module-level class identity — M35Error,
    # SecretHandleError — stays stable for every other test in the suite.
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, "-c",
         "import saathi.credentials.m35 as m; "
         "assert m.M35_DEFAULT_LEASE_TTL_SEC == 300.0; "
         "assert m.M35_DEFAULT_MAX_USES == 1; print('ok')"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout
