"""M240–M247 Provider Canary Planning tests.

PLANNING ONLY. No real brokers. No credentials. No canary activation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from saathi.platform.tg.provider_canary_planning.models import (
    CANARY_ACTIVATION_AUTHORIZED,
    CREDENTIAL_PROVISIONING_AUTHORIZED,
    FALLBACK_PROVIDER,
    LIVE_TRADING_AUTHORIZED,
    PREFERRED_PROVIDER,
    REAL_CONNECTIVITY_AUTHORIZED,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.provider_canary_planning.service import (
    ProviderCanaryPlanningService,
    reset_provider_canary_planning_for_tests,
)
from saathi.platform.tg.provider_canary_planning.transport import (
    REAL_PROVIDER_TRANSPORT_FORBIDDEN,
    TransportGuardError,
)


@pytest.fixture()
def svc(tmp_path: Path):
    db = tmp_path / "pcp_test.db"
    return reset_provider_canary_planning_for_tests(db_path=db)


def test_authority_locks_false():
    assert REAL_CONNECTIVITY_AUTHORIZED is False
    assert CREDENTIAL_PROVISIONING_AUTHORIZED is False
    assert CANARY_ACTIVATION_AUTHORIZED is False
    assert LIVE_TRADING_AUTHORIZED is False


def test_m240_candidates_and_ranking(svc: ProviderCanaryPlanningService):
    c = svc.candidates()
    assert c["count"] == 7
    assert c["preferred_provider"] == PREFERRED_PROVIDER
    assert c["fallback_provider"] == FALLBACK_PROVIDER
    r = svc.rankings()
    assert r["preferred_is_recommendation_only"] is True
    assert r["owner_eligibility_claimed"] is False
    providers = {x["provider"] for x in r["ranking"]}
    assert "alpaca" in providers and "kraken" in providers
    for item in r["ranking"]:
        assert "scores" in item
        for dim, score in item["scores"].items():
            assert "evidence" in score
            assert "confidence" in score
            assert "uncertainty" in score
    assert r["REAL_CONNECTIVITY_AUTHORIZED"] is False


def test_m240_preferred_and_fallback(svc: ProviderCanaryPlanningService):
    p = svc.preferred()
    assert p["preferred_provider"] == "alpaca"
    assert p["recommendation_only"] is True
    assert p["owner_eligibility_claimed"] is False
    f = svc.fallback()
    assert f["fallback_provider"] == "kraken"


def test_m240_sources_inventory(svc: ProviderCanaryPlanningService):
    s = svc.list_sources()
    assert s["count"] >= 10
    assert s["retrieval_date"]
    for src in s["sources"]:
        assert src["url"].startswith("http")
        assert src["title"]
        assert src["confidence"]


def test_m240_scoring_transparency_missing_not_hidden(svc: ProviderCanaryPlanningService):
    r = svc.rankings()
    # At least one candidate must surface unresolved questions
    unresolved = [x for x in r["ranking"] if x["unresolved_questions"]]
    assert len(unresolved) >= 3


def test_m241_capability_map(svc: ProviderCanaryPlanningService):
    m = svc.capabilities_map()
    assert m["provider"] == "alpaca"
    assert m["provider_adapter_implemented"] is False
    families = {e["endpoint_family"] for e in m["endpoints"]}
    assert "balances" in families
    assert "order_placement" in families
    assert "withdrawals" in families
    forbidden = [e for e in m["endpoints"] if e["allowed_or_forbidden"] == "FORBIDDEN"]
    assert len(forbidden) >= 3
    assert any(e["auth_category"] == "TRADING_WRITE" for e in m["endpoints"])
    assert any(e["auth_category"] == "PRIVATE_READ_ONLY" for e in m["endpoints"])


def test_m241_scopes_read_only_and_forbidden(svc: ProviderCanaryPlanningService):
    s = svc.scopes()
    assert s["proposed_read_only_scopes"]
    assert s["forbidden_scopes"]
    assert s["mixed_scope_accepted"] is False
    names = {x["scope_name"] for x in s["forbidden_scopes"]}
    assert "trading_write" in names
    assert "withdrawal" in names


def test_m241_mixed_scope_rejection(svc: ProviderCanaryPlanningService):
    bad = svc.validate_scopes(["account_read", "trading_write", "withdrawal"])
    assert bad["ok"] is False
    assert bad["code"] == "MIXED_OR_WRITE_SCOPE_REJECTED"
    good = svc.validate_scopes(["account_read", "orders_read"])
    assert good["ok"] is True


def test_m242_eligibility_unconfirmed(svc: ProviderCanaryPlanningService):
    e = svc.eligibility_review()
    assert e["result"] == "ELIGIBILITY_UNCONFIRMED"
    assert e["owner_eligibility_claimed"] is False
    assert e["legal_approval_generated_by_automation"] is False
    assert e["unresolved"]
    t = svc.terms_review()
    assert t["terms_review_status"] == "TERMS_REVIEW_INCOMPLETE"
    assert t["legal_approval_generated_by_automation"] is False


def test_m243_canary_designed_not_authorized(svc: ProviderCanaryPlanningService):
    d = svc.canary_design()
    assert d["state"] == "CANARY_DESIGNED_NOT_AUTHORIZED"
    assert d["provider_adapter_implemented"] is False
    assert d["canary_activation_authorized"] is False
    assert "order_placement" in d["must_not"]
    assert "balances" in d["may_read"]
    assert d["network_allowlist_proposal"]
    assert d["endpoint_allowlist_proposal"]
    act = svc.canary_activate_attempt()
    assert act["ok"] is False
    assert act["code"] == "CANARY_ACTIVATION_FORBIDDEN"


def test_m244_credential_ceremony_not_executed(svc: ProviderCanaryPlanningService):
    r = svc.credential_ceremony()
    assert r["status"] == "CREDENTIAL_CEREMONY_DOCUMENTED_NOT_EXECUTED"
    assert r["executed"] is False
    assert r["CREDENTIAL_PROVISIONING_AUTHORIZED"] is False
    assert len(r["ceremony"]["steps"]) == 20
    refuse = svc.refuse_credentials("sk_live_fake")
    assert refuse["ok"] is False
    assert refuse["code"] == "RAW_CREDENTIAL_REJECTED"
    oauth = svc.refuse_oauth()
    assert oauth["ok"] is False


def test_m245_gates_and_aborts(svc: ProviderCanaryPlanningService):
    a = svc.acceptance_gates()
    assert "owner_approval" in a["pre_activation_gates"]
    assert "no_write_capability" in a["success_criteria"]
    ab = svc.abort_gates()
    assert "unexpected_write_scope" in ab["abort_triggers"]
    assert "withdrawal_permission" in ab["abort_triggers"]
    assert ab["automated_recovery_after_security_abort"] is False
    m = svc.monitoring_plan()
    assert "signals" in m
    recon = svc.reconciliation_plan()
    assert "paper_portfolio" in recon["does_not_mutate"]


def test_m246_owner_package_and_signoff_restriction(svc: ProviderCanaryPlanningService):
    pkg = svc.owner_package()
    assert pkg["preferred_provider"] == "alpaca"
    assert pkg["fallback_provider"] == "kraken"
    assert pkg["owner_signoff_generated_by_automation"] is False
    assert pkg["owner_decision"] == ""
    opts = pkg["owner_decision_form"]["options"]
    assert "REJECT" in opts
    assert "REQUEST_CHANGES" in opts
    assert "APPROVE_PLANNING_PACKAGE_ONLY" in opts
    assert "AUTHORIZE_CONNECTIVITY" not in opts
    assert pkg["owner_decision_form"]["connectivity_authorization_option_present"] is False
    blocked = svc.owner_auto_signoff_attempt()
    assert blocked["ok"] is False
    assert blocked["code"] == "OWNER_SIGNOFF_AUTOMATION_FORBIDDEN"


def test_m246_planning_review_status_no_connectivity(svc: ProviderCanaryPlanningService):
    r = svc.planning_review_status("AWAITING_OWNER_REVIEW")
    assert r["ok"] is True
    assert r["grants_connectivity"] is False


def test_m247_dashboard_and_network(svc: ProviderCanaryPlanningService):
    d = svc.dashboard()
    assert d["labels"]["planning_only"] == "PLANNING ONLY"
    assert d["ui_constraints"]["accept_credentials"] is False
    assert d["ui_constraints"]["activate_canary"] is False
    n = svc.network_policy()
    assert n["runtime_provider_transport"] == REAL_PROVIDER_TRANSPORT_FORBIDDEN


def test_transport_blocks_private_provider(svc: ProviderCanaryPlanningService):
    r = svc.transport_probe("https://paper-api.alpaca.markets/v2/account")
    assert r["ok"] is False
    assert r["result"] == REAL_PROVIDER_TRANSPORT_FORBIDDEN
    r2 = svc.transport_probe("https://api.binance.com/api/v3/account")
    assert r2["ok"] is False
    local = svc.transport_probe("http://127.0.0.1:8000/health")
    assert local["ok"] is True


def test_security_scan_and_adapter(svc: ProviderCanaryPlanningService):
    s = svc.security_scan()
    assert s["credential_scan"]["ok"] is True
    assert s["network_isolation"]["ok"] is True
    assert s["llm_boundary_scan"]["ok"] is True
    assert s["runtime_adapter_scan"]["ok"] is True
    assert s["runtime_adapter_scan"]["provider_adapter_implemented"] is False


def test_llm_authority_boundary(svc: ProviderCanaryPlanningService):
    for action in (
        "generate_owner_signoff",
        "activate_canary",
        "create_credentials",
        "connect_provider",
        "enable_live_trading",
        "legal_approval",
    ):
        r = svc.llm_refuse(action)
        assert r["ok"] is False
        assert r["code"] == "LLM_ACTION_FORBIDDEN"


def test_storage_restart_safe(tmp_path: Path):
    db = tmp_path / "restart.db"
    s1 = reset_provider_canary_planning_for_tests(db_path=db)
    r1 = s1.rankings()
    s1.store.close()
    s2 = reset_provider_canary_planning_for_tests(db_path=db)
    r2 = s2.rankings()
    assert r2["preferred_provider"] == r1["preferred_provider"]
    assert len(r2["ranking"]) == len(r1["ranking"])


def test_certify_passes_with_limitations(svc: ProviderCanaryPlanningService):
    c = svc.certify()
    assert c["verdict"] == TERMINAL_VERDICT
    assert c["hard_gates_pass"] is True
    assert c["REAL_CONNECTIVITY_AUTHORIZED"] is False
    assert c["CANARY_ACTIVATION_AUTHORIZED"] is False
    assert c["owner_signoff_generated_by_automation"] is False
    assert c["preferred_provider"] == "alpaca"


def test_posture_and_verdict(svc: ProviderCanaryPlanningService):
    p = svc.posture()
    assert p["planning_only"] is True
    assert p["provider_adapter_implemented"] is False
    v = svc.terminal_verdict()
    assert v["verdict"] == TERMINAL_VERDICT
    assert v["owner_eligibility_claimed"] is False
    assert any("PAPER" in s for s in v["statements"])


def test_threat_model_coverage(svc: ProviderCanaryPlanningService):
    t = svc.threat_model()
    assert t["count"] >= 25
    names = {x["threat"] for x in t["threats"]}
    assert "owner_signoff_fabrication" in names
    assert "hidden_connectivity_path" in names


def test_negative_write_scope_and_activation(svc: ProviderCanaryPlanningService):
    assert svc.validate_scopes(["withdrawal"])["ok"] is False
    assert svc.canary_activate_attempt()["ok"] is False
    assert svc.refuse_credentials("x")["ok"] is False
    assert svc.owner_auto_signoff_attempt()["ok"] is False
