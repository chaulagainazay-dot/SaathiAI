"""M200–M207 — Durable paper ledger, concurrency, restart, recovery, campaigns."""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path

import pytest

from saathi.platform.tg import LIVE_TRADING_AUTHORIZED, LIVE_ORDER_CAPABLE, BROKER_CREDENTIAL_SUPPORT
from saathi.platform.tg.domain import StrategyEvaluationVerdict
from saathi.platform.tg.historical.qualification import QualificationGates
from saathi.platform.tg.paper_activation.durable import (
    reset_durable_gov_for_tests,
    DurableGovError,
    DurablePaperStore,
)
from saathi.platform.tg.paper_activation.durable.events import fingerprint
from saathi.platform.tg.paper_activation.durable.store import IdempotencyConflict


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
    return reset_durable_gov_for_tests(tmp_path / "paper_gov.db")


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


def test_paper_only_constants():
    assert LIVE_TRADING_AUTHORIZED is False
    assert LIVE_ORDER_CAPABLE is False
    assert BROKER_CREDENTIAL_SUPPORT is False


def test_storage_migrate_and_health(tmp_path):
    svc = _svc(tmp_path)
    m = svc.migrate()
    assert m["status"] == "MIGRATED"
    h = svc.storage_status()
    assert h["status"] == "HEALTHY"
    assert h["paper_only"] is True
    p = svc.posture()
    assert p["durable"] is True
    assert p["llm_boundary"]["llm_may_approve"] is False
    assert p["llm_boundary"]["llm_may_authorize_live"] is False


def test_idempotent_portfolio_and_order(tmp_path):
    svc = _svc(tmp_path)
    a = svc.create_portfolio(idempotency_key="k1")
    b = svc.create_portfolio(idempotency_key="k1")
    assert a["portfolio"]["id"] == b["portfolio"]["id"]
    pid, _, _ = _activate(svc)
    o1 = svc.place_order(
        portfolio_id=pid, strategy_slug="trend_following", symbol="A", side="BUY",
        quantity="1", idempotency_key="ok1",
    )
    o2 = svc.place_order(
        portfolio_id=pid, strategy_slug="trend_following", symbol="A", side="BUY",
        quantity="1", idempotency_key="ok1",
    )
    assert o1["order"]["id"] == o2["order"]["id"]


def test_single_use_approval_consume(tmp_path):
    svc = _svc(tmp_path)
    pid, apid, _ = _activate(svc)
    with pytest.raises(DurableGovError):
        svc.activate_strategy(
            strategy_slug="trend_following", approval_id=apid, portfolio_id=pid,
            operator_identity="operator:h",
        )


def test_concurrent_approval_consume(tmp_path):
    svc = _svc(tmp_path)
    port = svc.create_portfolio()
    pid = port["portfolio"]["id"]
    req = svc.request_approval(
        strategy_slug="trend_following", qualification=_qual(), reason="c",
        operator_id="op", operator_identity="operator:h",
    )
    apid = req["approval"]["id"]
    svc.decide_approval(approval_id=apid, decision="approve", operator_id="op", operator_identity="operator:h")
    results = []
    errors = []

    def worker(i):
        try:
            results.append(svc.activate_strategy(
                strategy_slug="trend_following", approval_id=apid, portfolio_id=pid,
                operator_identity="operator:h", idempotency_key=f"c{i}",
            ))
        except DurableGovError as e:
            errors.append(e.code)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 1
    assert len(errors) == 3


def test_restart_preserves_state(tmp_path):
    db = tmp_path / "r.db"
    svc = reset_durable_gov_for_tests(db)
    pid, _, _ = _activate(svc)
    svc.place_order(portfolio_id=pid, strategy_slug="trend_following", symbol="SPY", side="BUY", quantity="5")
    svc.process_market(pid, symbol="SPY", bid="50", ask="50.1", last="50")
    cash_before = svc.get_portfolio(pid)["portfolio"]["cash"]
    svc.store.close()
    svc2 = reset_durable_gov_for_tests(db)
    p = svc2.get_portfolio(pid)["portfolio"]
    assert p["cash"] == cash_before
    assert "SPY" in p["positions"]
    assert svc2.reconcile(pid)["reconciliation"]["verdict"] in ("RECONCILED", "RECONCILED_WITH_WARNINGS")


def test_duplicate_fill_effect_blocked(tmp_path):
    svc = _svc(tmp_path)
    pid, _, _ = _activate(svc)
    o = svc.place_order(portfolio_id=pid, strategy_slug="trend_following", symbol="X", side="BUY", quantity="2")
    svc.process_market(pid, symbol="X", bid="10", ask="10.1", last="10")
    cash1 = svc.get_portfolio(pid)["portfolio"]["cash"]
    # reprocess same market — should not double-fill same remaining
    svc.process_market(pid, symbol="X", bid="10", ask="10.1", last="10")
    cash2 = svc.get_portfolio(pid)["portfolio"]["cash"]
    assert cash1 == cash2


def test_kill_switch_durable_and_llm_blocked(tmp_path):
    svc = _svc(tmp_path)
    pid, _, _ = _activate(svc)
    with pytest.raises(DurableGovError) as ei:
        svc.activate_kill_switch(reason="x", activated_by="llm:model")
    assert ei.value.code == "SELF_APPROVAL_FORBIDDEN"
    svc.activate_kill_switch(reason="halt", activated_by="operator:h")
    assert svc.store.kill_switch_active()
    with pytest.raises(DurableGovError):
        svc.place_order(portfolio_id=pid, strategy_slug="trend_following", symbol="Z", side="BUY", quantity="1")
    # restart retains kill switch
    db = svc.store.db_path
    svc.store.close()
    svc2 = reset_durable_gov_for_tests(db)
    assert svc2.store.kill_switch_active()


def test_fixture_cannot_activate(tmp_path):
    svc = _svc(tmp_path)
    with pytest.raises(DurableGovError) as ei:
        svc.request_approval(
            strategy_slug="trend_following",
            qualification={
                "verdict": "RESEARCH_ONLY",
                "data_classification": "SYNTHETIC_VALIDATION",
                "authoritative": False,
                "gates": {},
            },
            reason="nope", operator_id="op", operator_identity="operator:h",
        )
    assert ei.value.code == "NOT_PAPER_ELIGIBLE"


def test_backup_and_isolated_recovery(tmp_path):
    svc = _svc(tmp_path)
    pid, _, _ = _activate(svc)
    svc.place_order(portfolio_id=pid, strategy_slug="trend_following", symbol="B", side="BUY", quantity="3")
    svc.process_market(pid, symbol="B", bid="20", ask="20.1", last="20")
    bak = svc.backup_create(tmp_path / "backups")
    assert Path(bak["path"]).is_file()
    ver = svc.backup_verify(bak)
    assert ver["ok"] is True
    rec = svc.recovery_test(bak["path"], tmp_path / "isolated_recovery.db")
    assert rec["source_untouched"] is True
    assert rec["verdict"] in ("RECOVERY_VERIFIED", "RECOVERY_VERIFIED_WITH_WARNINGS")
    # source still works
    assert svc.get_portfolio(pid)["portfolio"]["id"] == pid


def test_campaign_lifecycle(tmp_path):
    svc = _svc(tmp_path)
    # need approval first
    port = svc.create_portfolio()
    req = svc.request_approval(
        strategy_slug="trend_following", qualification=_qual(), reason="camp",
        operator_id="op", operator_identity="operator:h",
    )
    apid = req["approval"]["id"]
    svc.decide_approval(approval_id=apid, decision="approve", operator_id="op", operator_identity="operator:h")
    camp = svc.campaign_create(strategy_slug="trend_following")
    cid = camp["campaign"]["id"]
    svc.campaign_approve(cid, approval_id=apid, operator_identity="operator:h")
    started = svc.campaign_start(cid, operator_identity="operator:h")
    assert started["campaign"]["status"] == "ACTIVE"
    assert started["live_authorized"] is False
    done = svc.campaign_complete(cid, operator_identity="operator:h")
    assert done["campaign"]["status"] == "COMPLETED"
    assert done["live_authorized"] is False


def test_event_ledger_immutable_and_replay(tmp_path):
    svc = _svc(tmp_path)
    pid, _, _ = _activate(svc)
    events = svc.list_events(limit=100)["events"]
    assert len(events) >= 3
    assert all(e.get("immutable") for e in events)
    r = svc.replay(pid)
    assert "projected_cash" in r["replay"]


def test_scheduler_disabled_by_default(tmp_path):
    svc = _svc(tmp_path)
    out = svc.run_scheduled_jobs(enable=False)
    assert out["enabled"] is False
    out2 = svc.run_scheduled_jobs(enable=True)
    assert out2["enabled"] is True


def test_unreconciled_blocks_via_halt(tmp_path):
    svc = _svc(tmp_path)
    pid, _, _ = _activate(svc)
    # force negative cash path via direct store corruption then recon
    p = svc.store.get_portfolio(pid)
    p["cash"] = "-1"
    svc.store.save_portfolio(p, expected_version=p["version"])
    r = svc.reconcile(pid, auto_halt=True)
    assert r["reconciliation"]["fail_closed"] is True
    p2 = svc.get_portfolio(pid)["portfolio"]
    assert p2["status"] == "HALTED"


def test_prohibited_live_path_absent():
    from saathi.platform.tg.paper_activation.durable import service as svc_mod
    src = Path(svc_mod.__file__).read_text()
    assert "live_order_capable" in src or "LIVE" in src
    assert "api.binance.com/api/v3/order" not in src
