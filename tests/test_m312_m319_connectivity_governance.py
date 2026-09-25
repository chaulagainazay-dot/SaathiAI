"""M312–M319 Connectivity Governance tests.

GOVERNANCE ONLY. No provider connection, credentials, OAuth, accounts, orders, canary.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from saathi.platform.tg.connectivity_governance.errors import (
    ApprovalRejected,
    CredentialPolicyViolation,
    SecretFieldDetected,
)
from saathi.platform.tg.connectivity_governance.models import (
    ACCOUNT_ACCESS_AUTHORIZED,
    AUTHORITY_VALUES,
    BROKER_CONNECTIVITY_AUTHORIZED,
    CANARY_ACTIVATION_AUTHORIZED,
    CREDENTIAL_PROVISIONING_AUTHORIZED,
    CURRENT_MATURITY,
    LIVE_TRADING_AUTHORIZED,
    MAX_STATE,
    OAUTH_AUTHORIZED,
    ORDER_SUBMISSION_AUTHORIZED,
    REAL_CONNECTIVITY_AUTHORIZED,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.connectivity_governance.service import (
    ConnectivityGovernanceService,
    reset_connectivity_governance_for_tests,
)


@pytest.fixture()
def svc(tmp_path: Path) -> ConnectivityGovernanceService:
    return reset_connectivity_governance_for_tests(db_path=tmp_path / "cg_test.db")


def test_authority_locks():
    assert LIVE_TRADING_AUTHORIZED is False
    assert REAL_CONNECTIVITY_AUTHORIZED is False
    assert BROKER_CONNECTIVITY_AUTHORIZED is False
    assert ORDER_SUBMISSION_AUTHORIZED is False
    assert ACCOUNT_ACCESS_AUTHORIZED is False
    assert OAUTH_AUTHORIZED is False
    assert CREDENTIAL_PROVISIONING_AUTHORIZED is False
    assert CANARY_ACTIVATION_AUTHORIZED is False
    assert all(
        AUTHORITY_VALUES[k] is False
        for k in AUTHORITY_VALUES
        if k.endswith("_AUTHORIZED") or k in ("API_KEYS_ACCEPTED", "PRODUCTION_AUTHORIZED", "AUTOMATED_INVESTMENT_AUTHORITY")
    )


# --- M312 Charter ---
def test_charter(svc: ConnectivityGovernanceService):
    c = svc.charter()
    assert c["finalized"] is True
    assert len(c["principles"]) >= 20
    assert "broker_login" in c["prohibited_operations"]
    assert c["human_accountability"]["llm_cannot_approve_or_activate"] is True
    assert c["charter_version"]


# --- M313 Authority ---
def test_authority_lattice_no_implicit_expansion(svc: ConnectivityGovernanceService):
    proof = svc.authority_model()["no_implicit_expansion"]
    assert proof["ok"] is True
    assert proof["authority_does_not_implicitly_expand"] is True


def test_deny_overrides_allow(svc: ConnectivityGovernanceService):
    p = svc.authority_model()["deny_overrides_allow"]
    assert p["deny_overrides_allow"] is True


def test_expiry_revocation_emergency(svc: ConnectivityGovernanceService):
    am = svc.authority_model()
    assert am["expiry"]["ok"] is True
    assert am["revocation"]["ok"] is True
    assert am["emergency_override"]["emergency_dominates"] is True


def test_authority_evaluate_prohibited(svc: ConnectivityGovernanceService):
    r = svc.authority_evaluate("live_execution")
    assert r["state"] == "PROHIBITED"
    r2 = svc.authority_evaluate("submit_order")
    assert r2["state"] == "PROHIBITED"


# --- M314 Providers ---
def test_provider_registry(svc: ConnectivityGovernanceService):
    p = svc.list_providers()
    assert p["count"] >= 3
    assert p["any_connected"] is False
    assert p["any_active"] is False
    pol = svc.capability_policy()
    assert "live_execution" in pol["prohibited_capabilities_blocklist"] or "live_order" in pol["prohibited_endpoint_classes"]
    dom = svc.domain_allowlists()
    assert "*" not in "".join(dom["approved_official_domains"])


def test_wildcard_domain_rejected(svc: ConnectivityGovernanceService):
    from saathi.platform.tg.connectivity_governance.errors import ProviderGovernanceError
    with pytest.raises(ProviderGovernanceError):
        svc.register_provider({
            "provider_id": "bad",
            "provider_name": "bad",
            "official_domains": ["*.evil.com"],
            "governance_status": "RESEARCH_ONLY",
        }, actor="human")


def test_prohibit_provider(svc: ConnectivityGovernanceService):
    r = svc.prohibit_provider("prov_binance_docs", actor="ops", reason="jurisdiction")
    assert r["ok"]
    assert r["provider"]["governance_status"] == "PROHIBITED"


# --- M315 Approvals ---
def _draft_kwargs(**over):
    base = dict(
        requestor="alice",
        approval_type="provider_documentation_review",
        provider="prov_mock_contract",
        environment="governance",
        capability_scope=["offline_fixture_access"],
        operation_scope=["documentation_review"],
        jurisdiction="N/A",
        expiry_time=time.time() + 86400,
        allowed_network_destinations=["localhost"],
        evidence_requirements=["docs"],
        revocation_conditions=["operator_request"],
        acknowledgements=["governance_only", "no_activation"],
    )
    base.update(over)
    return base


def test_approval_maker_checker(svc: ConnectivityGovernanceService):
    d = svc.create_approval(**_draft_kwargs())
    aid = d["approval"]["approval_id"]
    svc.submit_approval(aid, actor="alice")
    with pytest.raises(ApprovalRejected) as e:
        svc.review_approval(aid, approver="alice", decision="approve")
    assert "SELF_APPROVAL" in e.value.code


def test_llm_approval_rejected(svc: ConnectivityGovernanceService):
    d = svc.create_approval(**_draft_kwargs())
    aid = d["approval"]["approval_id"]
    svc.submit_approval(aid, actor="alice")
    with pytest.raises(ApprovalRejected) as e:
        svc.review_approval(aid, approver="llm", decision="approve")
    assert "LLM" in e.value.code


def test_approval_not_activation(svc: ConnectivityGovernanceService):
    d = svc.create_approval(**_draft_kwargs())
    aid = d["approval"]["approval_id"]
    svc.submit_approval(aid, actor="alice")
    r = svc.review_approval(aid, approver="bob", decision="approve")
    assert r["approval"]["status"] == "APPROVED_NOT_ACTIVE"
    assert r["activates_connectivity"] is False


def test_approval_requires_expiry(svc: ConnectivityGovernanceService):
    kw = _draft_kwargs()
    kw["expiry_time"] = None
    with pytest.raises(ApprovalRejected):
        svc.create_approval(**kw)


def test_approval_wildcard_scope_rejected(svc: ConnectivityGovernanceService):
    with pytest.raises(ApprovalRejected):
        svc.create_approval(**_draft_kwargs(capability_scope=["*"]))


def test_live_execution_request_rejected(svc: ConnectivityGovernanceService):
    with pytest.raises(ApprovalRejected):
        svc.create_approval(**_draft_kwargs(
            capability_scope=["live_execution"],
            operation_scope=["live_trading"],
        ))


def test_approval_revoke(svc: ConnectivityGovernanceService):
    d = svc.create_approval(**_draft_kwargs())
    aid = d["approval"]["approval_id"]
    svc.submit_approval(aid, actor="alice")
    svc.review_approval(aid, approver="bob", decision="approve")
    r = svc.revoke_approval(aid, actor="ops", reason="operator_request")
    assert r["approval"]["status"] == "REVOKED"


# --- M316 Credentials ---
def test_raw_credential_rejected(svc: ConnectivityGovernanceService):
    r = svc.reject_raw_credential("api_key", "sk_test_abc")
    assert r["refused"] is True
    assert r["stored"] is False


def test_secret_scan(svc: ConnectivityGovernanceService):
    with pytest.raises(SecretFieldDetected):
        svc.scan_secrets({"api_key": "supersecretvalue"})


def test_synthetic_reference(svc: ConnectivityGovernanceService):
    r = svc.declare_synthetic_reference(
        reference="secret-ref://synthetic/not-active",
        owner="human",
        provider="prov_mock_contract",
    )
    assert r["ok"]
    assert r["credential_reference"]["state"] == "REFERENCE_DECLARED"
    assert r["credential_reference"]["active"] is False


def test_real_reference_forbidden(svc: ConnectivityGovernanceService):
    with pytest.raises(CredentialPolicyViolation):
        svc.declare_synthetic_reference(
            reference="vault://prod/real-key",
            owner="human",
            provider="x",
        )


def test_credential_sql_blocked(svc: ConnectivityGovernanceService):
    with pytest.raises(ValueError):
        svc.store.execute("INSERT INTO cg_meta(key, value, updated_at) VALUES('api_key','x',0)")


# --- M317 Revocation / Emergency / Incident ---
def test_emergency_shutdown(svc: ConnectivityGovernanceService):
    r = svc.emergency_shutdown(actor="ops", reason="drill")
    assert r["emergency_shutdown"] is True
    bypass = svc.emergency_bypass_attempt()
    assert bypass["refused"] is True
    # authority evaluate under emergency
    ev = svc.authority_evaluate("offline_fixture_access")
    assert ev["state"] == "EMERGENCY_DISABLED"


def test_incident_workflow(svc: ConnectivityGovernanceService):
    inc = svc.create_incident(
        incident_type="credential_leak",
        actor="ops",
        summary="drill",
        severity="HIGH",
    )
    iid = inc["incident"]["incident_id"]
    svc.advance_incident(iid, step="classify", actor="ops")
    c = svc.advance_incident(iid, step="contain", actor="ops")
    assert c["incident"]["state"] == "CONTAINED"


def test_revocation(svc: ConnectivityGovernanceService):
    r = svc.revoke(scope="provider", target_id="prov_mock_contract", reason="operator_request", actor="ops")
    assert r["ok"]
    assert r["reconnect_allowed"] is False


# --- M318 Threats ---
def test_threat_model(svc: ConnectivityGovernanceService):
    t = svc.list_threats()
    assert t["total"] >= 50
    assert t["critical_count"] >= 10
    assert t["unresolved_critical_count"] == 0
    rs = svc.risk_summary()
    assert rs["total_threats"] >= 50


# --- M319 Integration ---
def test_bootstrap_and_certify(svc: ConnectivityGovernanceService):
    pipe = svc.bootstrap_demo_pipeline()
    assert pipe["ok"] is True
    assert pipe["activates_connectivity"] is False
    assert pipe["provider_connected"] is False
    cert = svc.certify()
    assert cert["ok"] is True
    assert cert["verdict"] == TERMINAL_VERDICT
    assert cert["max_state"] == MAX_STATE
    assert cert["current_maturity"] == CURRENT_MATURITY


def test_dashboard(svc: ConnectivityGovernanceService):
    d = svc.dashboard()
    assert d["current_maturity"] == "GOVERNANCE_ONLY"
    assert "enter_api_key" in d["forbidden_ui_actions"]
    assert "connect_provider" in d["forbidden_ui_actions"]


def test_all_refusals(svc: ConnectivityGovernanceService):
    assert svc.refuse_broker_login()["refused"] is True
    assert svc.refuse_oauth()["refused"] is True
    assert svc.refuse_credentials("k")["refused"] is True
    assert svc.refuse_order()["refused"] is True
    assert svc.refuse_account_access()["refused"] is True
    assert svc.refuse_balance_access()["refused"] is True
    assert svc.refuse_position_access()["refused"] is True
    assert svc.refuse_canary()["refused"] is True
    assert svc.refuse_live_trading()["refused"] is True
    assert svc.refuse_provider_connect()["refused"] is True
    assert svc.refuse_transfer()["refused"] is True
    assert svc.refuse_withdrawal()["refused"] is True


def test_maturity(svc: ConnectivityGovernanceService):
    m = svc.maturity()
    assert m["current"] == "GOVERNANCE_ONLY"
    assert m["can_advance_automatically"] is False
    assert m["live_execution_unlock_path"] is False


def test_security_scan(svc: ConnectivityGovernanceService):
    s = svc.security_scan()
    assert s["ok"] is True
    assert s["llm_authority_scan"]["llm_may_approve"] is False
