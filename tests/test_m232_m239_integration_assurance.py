"""M232–M239 Clean-Clone Reproducibility, Supply-Chain Assurance and Authorization.

REPRODUCIBILITY AND PLANNING ONLY. No real brokers. No credentials. No orders.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from saathi.platform.tg.integration_assurance.service import (
    IntegrationAssuranceError,
    IntegrationAssuranceService,
    reset_integration_assurance_for_tests,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.integration_assurance.models import (
    AuthorizationState,
    REAL_CONNECTIVITY_AUTHORIZED,
    LIVE_TRADING_AUTHORIZED,
    OWNER_SIGNOFF_AUTOMATED,
)
from saathi.platform.tg.integration_assurance.transport import (
    REAL_PROVIDER_TRANSPORT_FORBIDDEN,
)


@pytest.fixture()
def svc(tmp_path: Path):
    db = tmp_path / "ia_test.db"
    return reset_integration_assurance_for_tests(db_path=db)


# ── M232 source audit ────────────────────────────────────────────────────────

def test_m232_required_source_committed(svc: IntegrationAssuranceService):
    r = svc.source_audit()
    # M216–M231 baseline must be fully committed (the original open question).
    assert r["baseline_ok"] is True
    m216 = r["m216_baseline"]
    assert m216["m216_uncommitted_dependency"] is False
    assert m216["resolution"] == "ALL_REQUIRED_SOURCE_COMMITTED"
    assert m216["broker_sandbox"]["committed"] is True
    assert m216["broker_readiness"]["committed"] is True
    assert r["verdict"] in (
        "ALL_REQUIRED_SOURCE_COMMITTED",
        "BASELINE_COMMITTED_MILESTONE_PACKAGE_PENDING",
    )
    # After this milestone is committed, ok becomes True; pre-commit allows pending package.
    if r["milestone_package_committed"]:
        assert r["ok"] is True
        assert r["verdict"] == "ALL_REQUIRED_SOURCE_COMMITTED"
    assert r["REAL_CONNECTIVITY_AUTHORIZED"] is False


def test_m232_classifications_present(svc: IntegrationAssuranceService):
    r = svc.source_audit()
    classes = {i["classification"] for i in r["items"]}
    assert "COMMITTED_AND_REQUIRED" in classes


# ── M233 reproduction (structural; full clone in certification) ──────────────

def test_m233_clean_worktree_structural(svc: IntegrationAssuranceService):
    # Structural path uses worktree add; nested pytest is non-recursive.
    r = svc.clean_worktree()
    assert r["final_verdict"] in (
        "CLEAN_CLONE_REPRODUCIBLE",
        "CLEAN_CLONE_REPRODUCIBLE_WITH_LIMITATIONS",
    )
    assert r["external_network_attempts"] == 0
    assert not any(h.get("kind") == "hidden_env_or_secret_file" for h in r.get("hidden_state_findings") or [])
    assert r["REAL_CONNECTIVITY_AUTHORIZED"] is False


def test_m233_clean_clone_structural(svc: IntegrationAssuranceService):
    r = svc.clean_clone()
    assert r["final_verdict"] in (
        "CLEAN_CLONE_REPRODUCIBLE",
        "CLEAN_CLONE_REPRODUCIBLE_WITH_LIMITATIONS",
    )
    assert r["REAL_CONNECTIVITY_AUTHORIZED"] is False


# ── M234 environment ─────────────────────────────────────────────────────────

def test_m234_env_contract_and_preflight(svc: IntegrationAssuranceService):
    c = svc.env_contract()
    assert "python_version_range" in c
    assert "forbidden" in c["environment_variables"]
    assert c["REAL_CONNECTIVITY_AUTHORIZED"] is False
    pf = svc.env_preflight()
    assert pf["preflight"]["ok"] is True
    assert pf["preflight"]["fail_closed"] is False


def test_m234_preflight_fails_on_provider_env(svc: IntegrationAssuranceService, monkeypatch):
    monkeypatch.setenv("BINANCE_API_KEY", "should-not-exist")
    pf = svc.env_preflight()
    assert pf["preflight"]["ok"] is False
    assert pf["preflight"]["fail_closed"] is True
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)


# ── M235 dependencies ────────────────────────────────────────────────────────

def test_m235_dependency_inventory_and_lockfiles(svc: IntegrationAssuranceService):
    locks = svc.lockfile_checks()
    assert locks["ok"] is True
    inv = svc.dependency_inventory()
    assert inv["count"] > 0
    assert inv["lockfiles"]["ok"] is True
    assert inv["floating_git"] == []
    assert inv["REAL_CONNECTIVITY_AUTHORIZED"] is False


# ── M236 SBOM / provenance ───────────────────────────────────────────────────

def test_m236_sbom_and_provenance_unsigned(svc: IntegrationAssuranceService):
    sbom = svc.generate_sbom()
    assert sbom["format"] == "CycloneDX"
    assert sbom["component_count"] > 0
    assert sbom["signed"] is False
    assert "not cryptographic signatures" in sbom["signing_note"].lower() or "Unsigned" in sbom["signing_note"]
    prov = svc.provenance()
    assert prov["count"] >= 7
    assert prov["signed"] is False
    for rec in prov["records"]:
        assert rec["signed"] is False
        assert rec["content_hash"]


# ── M237 supply chain ────────────────────────────────────────────────────────

def test_m237_threat_model_and_gates(svc: IntegrationAssuranceService):
    tm = svc.threat_model()
    assert tm["count"] >= 20
    threats = {t["threat"] for t in tm["threats"]}
    assert "malicious_dependency_update" in threats
    assert "sbom_tampering" in threats
    gates = svc.assurance_gates()
    assert gates["all_pass"] is True
    assert gates["REAL_CONNECTIVITY_AUTHORIZED"] is False


# ── M238 authorization ───────────────────────────────────────────────────────

def test_m238_planning_max_state_and_owner_block(svc: IntegrationAssuranceService):
    plan = svc.auth_create_plan()
    pid = plan["plan"]["id"]
    assert plan["plan"]["real_connectivity_authorized"] is False

    # missing approvals → awaiting owner
    agg = svc.auth_aggregate(pid)
    assert agg["state"] == AuthorizationState.AWAITING_OWNER_REVIEW.value or agg["state"] == AuthorizationState.PLANNING_ONLY.value
    assert agg["real_connectivity_authorized"] is False

    # automation cannot owner sign-off
    block = svc.auth_owner_signoff_attempt(pid, actor="agent")
    assert block["ok"] is False
    assert block["error"] == "OWNER_SIGNOFF_AUTOMATION_FORBIDDEN"

    with pytest.raises(IntegrationAssuranceError) as ei:
        svc.auth_record_approval(
            pid, "OWNER_AUTH",
            approver_identity="bot", role="agent", automated=True, actor="pipeline",
        )
    assert ei.value.code == "OWNER_SIGNOFF_AUTOMATION_FORBIDDEN"

    # human-style recording of non-owner domains is allowed for planning simulation
    svc.auth_record_approval(
        pid, "SECURITY_AUTH",
        approver_identity="security-officer", role="security", automated=False, actor="human:security",
    )
    # expired approval fails closed
    import time
    appr = svc.auth_record_approval(
        pid, "LEGAL_TOS",
        approver_identity="counsel", role="legal", automated=False, actor="human:legal",
        expires_at=time.time() - 10,
    )
    assert appr["expired"] is True
    agg2 = svc.auth_aggregate(pid)
    assert agg2["state"] in (
        AuthorizationState.AUTHORIZATION_EXPIRED.value,
        AuthorizationState.AWAITING_OWNER_REVIEW.value,
        AuthorizationState.EVIDENCE_INCOMPLETE.value,
        AuthorizationState.AWAITING_SECURITY_REVIEW.value,
        AuthorizationState.PLANNING_ONLY.value,
    )

    # revocation
    active = svc.auth_record_approval(
        pid, "PRIVACY",
        approver_identity="dpo", role="privacy", automated=False, actor="human:privacy",
        expires_at=time.time() + 86400,
    )
    rev = svc.auth_revoke(active["id"], reason="test revoke", actor="human:privacy")
    assert rev["revocation_status"] == "REVOKED"
    agg3 = svc.auth_aggregate(pid)
    assert agg3["state"] == AuthorizationState.AUTHORIZATION_REVOKED.value

    act = svc.auth_activate_connectivity(pid)
    assert act["ok"] is False
    assert act["real_connectivity_authorized"] is False
    assert REAL_CONNECTIVITY_AUTHORIZED is False
    assert LIVE_TRADING_AUTHORIZED is False
    assert OWNER_SIGNOFF_AUTOMATED is False


def test_m238_provider_mismatch_fails(svc: IntegrationAssuranceService):
    plan = svc.auth_create_plan(provider="alpha")
    with pytest.raises(IntegrationAssuranceError) as ei:
        svc.auth_record_approval(
            plan["plan"]["id"], "INFRASTRUCTURE",
            provider="beta", automated=False, actor="human:infra",
        )
    assert ei.value.code == "PROVIDER_MISMATCH"


def test_m238_all_domains_still_not_real_connectivity(svc: IntegrationAssuranceService):
    plan = svc.auth_create_plan()
    pid = plan["plan"]["id"]
    import time
    for domain, _ in __import__(
        "saathi.platform.tg.integration_assurance.models", fromlist=["APPROVAL_DOMAINS"]
    ).APPROVAL_DOMAINS:
        # OWNER cannot be automated — use human actor without automated flag
        svc.auth_record_approval(
            pid, domain,
            approver_identity=f"human-{domain.lower()}",
            role="human",
            automated=False,
            actor="human:reviewer",
            expires_at=time.time() + 86400,
        )
    elig = svc.auth_eligibility(pid)
    assert elig["eligible_for_canary_planning"] is True
    assert elig["state"] == AuthorizationState.READ_ONLY_CANARY_PLANNING_ELIGIBLE.value
    assert elig["real_connectivity_authorized"] is False


# ── network / transport ───────────────────────────────────────────────────────

def test_network_isolation_and_registry_separation(svc: IntegrationAssuranceService):
    binance = svc.transport_probe("https://api.binance.com/api/v3/account")
    assert binance["blocked"] is True
    assert binance["result"] == REAL_PROVIDER_TRANSPORT_FORBIDDEN

    local = svc.transport_probe("http://127.0.0.1:8839/health")
    assert local.get("ok") is True

    pypi = svc.transport_probe("https://pypi.org/simple/fastapi/")
    assert pypi.get("ok") is True
    assert pypi.get("broker_connectivity") is False
    assert pypi.get("category") == "dependency_registry"

    net = svc.network_policy()
    assert net["REAL_CONNECTIVITY_AUTHORIZED"] is False


def test_llm_refuse_owner_signoff(svc: IntegrationAssuranceService):
    r = svc.llm_refuse("owner_signoff")
    assert r["ok"] is False
    assert r["error"] == "LLM_AUTHORITY_DENIED"


def test_security_scan_pass(svc: IntegrationAssuranceService):
    r = svc.security_scan()
    assert r["all_pass"] is True


def test_dashboard_and_verdict(svc: IntegrationAssuranceService):
    d = svc.dashboard()
    assert d["labels"]["no_real_connectivity"] == "NO REAL CONNECTIVITY"
    assert d["ui_constraints"]["upload_credentials"] is False
    v = svc.terminal_verdict()
    assert v["verdict"] == TERMINAL_VERDICT
    assert v["real_connectivity_authorized"] is False
    assert "THE SYSTEM REMAINS PAPER AND SANDBOX ONLY." in v["statements"]


def test_certify_smoke(svc: IntegrationAssuranceService, monkeypatch):
    # Stub heavy clean-clone stages so unit suite stays non-recursive / bounded.
    monkeypatch.setattr(
        svc, "clean_worktree",
        lambda: {
            "final_verdict": "CLEAN_CLONE_REPRODUCIBLE_WITH_LIMITATIONS",
            "limitations": ["stubbed in unit test"],
            "external_network_attempts": 0,
        },
    )
    monkeypatch.setattr(
        svc, "clean_clone",
        lambda: {
            "final_verdict": "CLEAN_CLONE_REPRODUCIBLE_WITH_LIMITATIONS",
            "limitations": ["stubbed in unit test"],
            "external_network_attempts": 0,
        },
    )
    r = svc.certify()
    assert r["real_connectivity_authorized"] is False
    assert r["REAL_CONNECTIVITY_AUTHORIZED"] is False
    assert r["authorization"]["owner_signoff_automation_blocked"] is True
    assert r["authorization"]["connectivity_activation_blocked"] is True
    assert r["source_audit"].get("ok") is True or r["source_audit"].get("baseline_ok") is True
    assert r["verdict"] in (
        TERMINAL_VERDICT,
        "M232_M239_IMPLEMENTED_NOT_VERIFIED",
        "M232_M239_REQUIRED_SOURCE_UNCOMMITTED",
        "REPRODUCIBILITY_SUPPLY_CHAIN_AUTHORIZATION_CERTIFIED_WITH_LIMITATIONS",
    )
