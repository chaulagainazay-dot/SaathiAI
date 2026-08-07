"""M208–M215 — Extended paper campaign validation & operational graduation.

PAPER ONLY. Live trading never authorized.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from saathi.platform.tg import LIVE_TRADING_AUTHORIZED, LIVE_ORDER_CAPABLE, BROKER_CREDENTIAL_SUPPORT
from saathi.platform.tg.domain import StrategyEvaluationVerdict
from saathi.platform.tg.historical.qualification import QualificationGates
from saathi.platform.tg.paper_activation.ops import (
    TERMINAL_VERDICT,
    HealthClass,
    StrategyClassification,
    CampaignCertOutcome,
    reset_ops_gov_for_tests,
    DurableGovError,
)
from saathi.platform.tg.paper_activation.ops.models import LLM_BOUNDARY, PAPER_POSTURE


def _qual():
    gates = QualificationGates(
        non_fixture_authoritative_dataset=True, accepted_data_quality=True,
        sufficient_date_coverage=True, sufficient_trade_count=True, untouched_final_oos=True,
        walk_forward_completed=True, stress_completed=True, monte_carlo_completed=True,
        realistic_fees=True, realistic_spread=True, realistic_slippage=True,
        corporate_actions_validated=True, no_critical_data_quality_failure=True,
        no_look_ahead_leakage=True, no_unresolved_reconciliation=True, acceptable_drawdown=True,
        acceptable_risk_of_ruin=True, parameter_stability=True, no_critical_cost_sensitivity=True,
        no_critical_regime_dependence=True, immutable_strategy_version=True,
        immutable_dataset_version=True, complete_evidence_journal=True,
        policy_compatibility=True, deterministic_risk_controls=True,
    )
    return {
        "verdict": StrategyEvaluationVerdict.PAPER_ELIGIBLE.value,
        "data_classification": "HISTORICAL_LOCAL_DATASET",
        "authoritative": True,
        "gates": gates.to_public(),
    }


def _svc(tmp_path: Path):
    return reset_ops_gov_for_tests(tmp_path / "paper_ops.db")


def _activate(svc, strategy="trend_following", cash="100000"):
    port = svc.create_portfolio(starting_cash=cash)
    pid = port["portfolio"]["id"]
    req = svc.request_approval(
        strategy_slug=strategy, qualification=_qual(), reason="test",
        operator_id="op", operator_identity="operator:h",
    )
    apid = req["approval"]["id"]
    svc.decide_approval(approval_id=apid, decision="approve", operator_id="op", operator_identity="operator:h")
    act = svc.activate_strategy(
        strategy_slug=strategy, approval_id=apid, portfolio_id=pid, operator_identity="operator:h",
    )
    return pid, apid, act


def _trade_roundtrip(svc, pid, strategy="trend_following"):
    svc.place_order(
        portfolio_id=pid, strategy_slug=strategy, symbol="AAA", side="BUY",
        quantity="10", idempotency_key=f"buy-{time.time()}",
    )
    svc.process_market(pid, symbol="AAA", bid="99", ask="101", last="100")
    svc.place_order(
        portfolio_id=pid, strategy_slug=strategy, symbol="AAA", side="SELL",
        quantity="10", idempotency_key=f"sell-{time.time()}",
    )
    svc.process_market(pid, symbol="AAA", bid="104", ask="106", last="105")


# ── authority ────────────────────────────────────────────────────────────────
def test_paper_only_constants_and_posture(tmp_path):
    assert LIVE_TRADING_AUTHORIZED is False
    assert LIVE_ORDER_CAPABLE is False
    assert BROKER_CREDENTIAL_SUPPORT is False
    svc = _svc(tmp_path)
    p = svc.posture()
    assert p["paper_only"] is True
    assert p["live_trading_authorized"] is False
    assert p["llm_boundary"]["llm_may_authorize_live"] is False
    assert p["llm_boundary"]["llm_may_graduate_strategies"] is False
    assert p["llm_boundary"]["llm_may_execute_trades"] is False
    v = svc.terminal_verdict()
    assert v["verdict"] == TERMINAL_VERDICT
    assert v["strategy_auto_promoted_to_live"] is False
    assert "THE SYSTEM REMAINS PAPER ONLY." in v["statements"]


def test_llm_cannot_approve_or_graduate_authority_flags():
    assert LLM_BOUNDARY["llm_may_approve_campaigns"] is False
    assert LLM_BOUNDARY["llm_may_graduate_strategies"] is False
    assert LLM_BOUNDARY["llm_may_modify_evidence"] is False
    assert PAPER_POSTURE["strategy_auto_promoted_to_live"] is False


# ── M208 multi-campaign ──────────────────────────────────────────────────────
def test_multi_campaign_groups_templates_clone_compare(tmp_path):
    svc = _svc(tmp_path)
    g = svc.create_group(name="cohort-a", tags=["alpha"], owner="operator:h")
    assert g["group"]["id"]
    tpl = svc.create_template(
        name="trend-30d", strategy_slug="trend_following",
        body={"initial_cash": "50000", "min_trade_count": 5, "tags": ["tpl"]},
    )
    a = svc.campaign_create(
        strategy_slug="trend_following", group_id=g["group"]["id"],
        template_id=tpl["template"]["id"], owner="operator:h",
        tags=["paper", "m208"], objectives_text="validate ops excellence",
        min_trade_count=5, min_duration_sec=60,
    )
    cid = a["campaign"]["id"]
    assert a["campaign"]["group_id"] == g["group"]["id"]
    assert a["campaign"]["owner"] == "operator:h"
    assert "paper" in a["campaign"]["tags"]
    assert a["campaign"]["version_history"]

    cloned = svc.campaign_clone(cid, owner="operator:h")
    assert cloned["cloned_from"] == cid
    assert cloned["campaign"]["cloned_from"] == cid
    assert cloned["campaign"]["id"] != cid

    svc.campaign_update(cid, notes="updated note", tags=["paper", "updated"])
    full = svc.campaign_get(cid)["campaign"]
    assert full["notes"] == "updated note"
    assert "updated" in full["tags"]

    cmp = svc.campaign_compare([cid, cloned["campaign"]["id"]])
    assert len(cmp["campaigns"]) == 2
    assert cmp["paper_only"] is True
    assert cmp["live_authorized"] is False

    listed = svc.list_campaigns()
    assert len(listed["campaigns"]) >= 2


def test_campaign_schedule_archive_pause_resume(tmp_path):
    svc = _svc(tmp_path)
    pid, apid, _ = _activate(svc)
    camp = svc.campaign_create(strategy_slug="trend_following", owner="op")
    cid = camp["campaign"]["id"]
    svc.gov.campaign_approve(cid, approval_id=apid, operator_identity="operator:h")
    sched = svc.campaign_schedule(cid, start_at=time.time() + 86400, operator_identity="operator:h")
    assert sched["campaign"]["status"] == "SCHEDULED"

    # dependency self-ref blocked
    with pytest.raises(DurableGovError) as ei:
        svc.campaign_set_dependencies(cid, [cid])
    assert ei.value.code == "INVALID_DEPENDENCY"

    # start via durable after approve path: set APPROVED and start
    c = svc.gov.store.get_campaign(cid)
    c["status"] = "APPROVED"
    c["approval_id"] = apid
    svc.gov.store.save_campaign(c)
    started = svc.gov.campaign_start(cid, operator_identity="operator:h")
    assert started["campaign"]["status"] == "ACTIVE"
    paused = svc.gov.campaign_pause(cid, reason="ops test")
    assert paused["campaign"]["status"] == "PAUSED"
    resumed = svc.campaign_resume(cid, operator_identity="operator:h")
    assert resumed["campaign"]["status"] == "ACTIVE"
    done = svc.gov.campaign_complete(cid, operator_identity="operator:h")
    assert done["campaign"]["status"] == "COMPLETED"
    arch = svc.campaign_archive(cid, operator_identity="operator:h")
    assert arch["campaign"]["status"] == "ARCHIVED"
    assert arch["campaign"]["archived_at"]


def test_concurrent_campaigns(tmp_path):
    svc = _svc(tmp_path)
    ids = []
    for i in range(3):
        c = svc.campaign_create(strategy_slug="trend_following", tags=[f"c{i}"], owner="op")
        ids.append(c["campaign"]["id"])
    assert len(set(ids)) == 3
    assert len(svc.list_campaigns()["campaigns"]) >= 3


# ── M209 monitoring ──────────────────────────────────────────────────────────
def test_operational_health_classes(tmp_path):
    svc = _svc(tmp_path)
    h = svc.health()
    assert h["classification"] in {e.value for e in HealthClass}
    assert "portfolio_health" in h["components"]
    assert "storage_health" in h["components"]
    assert "worker_health" in h["components"]
    assert "recovery_readiness" in h["components"]
    assert h["paper_only"] is True
    camp = svc.campaign_create(strategy_slug="trend_following")
    ch = svc.campaign_health(camp["campaign"]["id"])
    assert ch["classification"] in {e.value for e in HealthClass}


# ── M210 graduation ──────────────────────────────────────────────────────────
def test_graduation_never_authorizes_live(tmp_path):
    svc = _svc(tmp_path)
    pid, apid, _ = _activate(svc)
    for _ in range(3):
        _trade_roundtrip(svc, pid)
    camp = svc.campaign_create(
        strategy_slug="trend_following", min_trade_count=1, min_duration_sec=1,
    )
    cid = camp["campaign"]["id"]
    svc.gov.campaign_approve(cid, approval_id=apid, operator_identity="operator:h")
    # link portfolio and complete
    c = svc.gov.store.get_campaign(cid)
    c["status"] = "ACTIVE"
    c["portfolio_id"] = pid
    c["start_date"] = time.time() - 10 * 86400
    c["approval_id"] = apid
    svc.gov.store.save_campaign(c)
    svc.gov.campaign_complete(cid, operator_identity="operator:h")

    g = svc.graduate(cid, actor="operator:h", criteria={
        "min_duration_sec": 1, "min_trades": 1, "max_drawdown_pct": 99,
    })
    assert g["live_authorized"] is False
    assert g["auto_promoted_to_live"] is False
    assert g["classification"] in {e.value for e in StrategyClassification}
    assert g["classification"] != "LIVE_APPROVED"
    assert "LIVE TRADING IS NOT AUTHORIZED" in g["disclaimer"]

    hist = svc.graduation_history(cid)
    assert len(hist["evaluations"]) >= 1


def test_graduation_draft_is_research_only(tmp_path):
    svc = _svc(tmp_path)
    camp = svc.campaign_create(strategy_slug="trend_following")
    g = svc.graduate(camp["campaign"]["id"])
    assert g["classification"] == StrategyClassification.RESEARCH_ONLY.value
    assert g["live_authorized"] is False


# ── M211 intelligence ────────────────────────────────────────────────────────
def test_intelligence_recommendations_not_auto_applied(tmp_path):
    svc = _svc(tmp_path)
    svc.campaign_create(strategy_slug="trend_following")
    scan = svc.scan_intelligence()
    assert scan["auto_applied"] is False
    assert scan["modifies_portfolios"] is False
    assert scan["paper_only"] is True
    for r in scan["recommendations"]:
        assert r["auto_applied"] is False
        assert r["modifies_portfolio"] is False


# ── M212 analytics ───────────────────────────────────────────────────────────
def test_rolling_analytics_and_reports(tmp_path):
    svc = _svc(tmp_path)
    pid, _, _ = _activate(svc)
    _trade_roundtrip(svc, pid)
    for i in range(5):
        svc.record_equity(pid)
        # nudge marks
        svc.process_market(pid, symbol="AAA", bid=str(100 + i), ask=str(102 + i), last=str(101 + i))
    roll = svc.rolling_analytics(pid, window=3)
    assert roll["paper_only"] is True
    assert "rolling_sharpe" in roll
    assert "rolling_drawdown" in roll
    camp = svc.campaign_create(strategy_slug="trend_following")
    c = svc.gov.store.get_campaign(camp["campaign"]["id"])
    c["portfolio_id"] = pid
    svc.gov.store.save_campaign(c)
    rep = svc.campaign_report(camp["campaign"]["id"])
    assert rep["kind"] == "campaign_report"
    assert rep["live_authorized"] is False
    w = svc.weekly_report()
    assert w["paper_only"] is True
    m = svc.monthly_report()
    assert m["kind"] == "monthly_ops_report"


# ── M213 simulation ──────────────────────────────────────────────────────────
def test_ops_simulation_suite(tmp_path):
    svc = _svc(tmp_path)
    pid, _, _ = _activate(svc)
    suite = svc.simulate_suite(portfolio_id=pid)
    assert suite["total"] >= 12
    assert suite["paper_only"] is True
    assert suite["live_authorized"] is False
    hol = svc.simulate("market_holiday")
    assert hol["result"]["ok"] is True
    rec = svc.simulate("recovery_exercise", portfolio_id=pid)
    assert "RECOVERY" in rec["verdict"] or rec["result"].get("ok") is True
    ks = svc.simulate("kill_switch")
    assert ks["result"]["engaged"] is False  # dry-run


# ── M214 evidence ────────────────────────────────────────────────────────────
def test_campaign_certification_immutable(tmp_path):
    svc = _svc(tmp_path)
    pid, apid, _ = _activate(svc)
    _trade_roundtrip(svc, pid)
    camp = svc.campaign_create(strategy_slug="trend_following", min_trade_count=1, min_duration_sec=1)
    cid = camp["campaign"]["id"]
    c = svc.gov.store.get_campaign(cid)
    c["status"] = "COMPLETED"
    c["portfolio_id"] = pid
    c["start_date"] = time.time() - 20 * 86400
    c["actual_end_date"] = time.time()
    c["approval_id"] = apid
    svc.gov.store.save_campaign(c)

    cert = svc.certify_campaign(cid, actor="operator:h")
    assert cert["immutable"] is True
    assert cert["live_authorized"] is False
    assert cert["auto_promoted_to_live"] is False
    assert cert["outcome"] in {e.value for e in CampaignCertOutcome}
    assert cert["fingerprint"]
    listed = svc.list_evidence(campaign_id=cid)
    assert len(listed["evidence"]) >= 1
    got = svc.get_evidence(cert["id"])
    assert got["fingerprint"] == cert["fingerprint"]
    assert "THE SYSTEM REMAINS PAPER ONLY" in cert["disclaimer"]


# ── M215 dashboard ───────────────────────────────────────────────────────────
def test_ops_dashboard_surfaces(tmp_path):
    svc = _svc(tmp_path)
    svc.campaign_create(strategy_slug="trend_following", tags=["dash"])
    d = svc.ops_dashboard()
    assert d["paper_only"] is True
    assert d["live_authorized"] is False
    assert d["labels"]["paper_only"] == "PAPER ONLY"
    assert d["labels"]["no_live"] == "NO LIVE TRADING"
    for key in (
        "campaign_overview", "strategy_rankings", "portfolio_rankings",
        "operational_health", "risk_center", "evidence_center",
        "incident_center", "recovery_center", "scheduler", "storage",
        "workers", "campaign_timeline", "graduation_status",
        "certification_reports",
    ):
        assert key in d


# ── negative / authority ─────────────────────────────────────────────────────
def test_unknown_campaign_errors(tmp_path):
    svc = _svc(tmp_path)
    with pytest.raises(DurableGovError):
        svc.campaign_get("missing")
    with pytest.raises(DurableGovError):
        svc.graduate("missing")


def test_stress_many_campaigns_and_health(tmp_path):
    svc = _svc(tmp_path)
    for i in range(8):
        svc.campaign_create(strategy_slug="trend_following", tags=[f"s{i}"])
    h = svc.health()
    assert h["classification"] in {e.value for e in HealthClass}
    d = svc.ops_dashboard()
    assert d["campaign_overview"]["total"] >= 8
