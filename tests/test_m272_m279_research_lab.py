"""M272–M279 Multi-Strategy Research Lab tests.

RESEARCH ONLY. No brokers. No API keys. No live trading.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from saathi.platform.tg.research_lab.errors import ResearchLabError
from saathi.platform.tg.research_lab.models import (
    API_KEYS_ACCEPTED,
    BROKER_CONNECTIVITY_AUTHORIZED,
    LIVE_TRADING_AUTHORIZED,
    ORDER_EXECUTION_AUTHORIZED,
    PAPER_EXECUTION_AUTHORIZED,
    PRESERVED_OOS_FAILURES,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.research_lab.service import (
    ResearchLabService,
    reset_research_lab_for_tests,
)


@pytest.fixture()
def svc(tmp_path: Path):
    return reset_research_lab_for_tests(db_path=tmp_path / "rl_test.db")


def test_authority_locks_false():
    assert LIVE_TRADING_AUTHORIZED is False
    assert BROKER_CONNECTIVITY_AUTHORIZED is False
    assert API_KEYS_ACCEPTED is False
    assert ORDER_EXECUTION_AUTHORIZED is False
    assert PAPER_EXECUTION_AUTHORIZED is False


def test_m272_deterministic_ids_and_preregistration(svc: ResearchLabService):
    a = svc.create_experiment(name="det_probe", strategy_ids=["tf_dual_ma"], random_seed=7)
    b = svc.create_experiment(name="det_probe", strategy_ids=["tf_dual_ma"], random_seed=7)
    assert a["experiment_id"] == b["experiment_id"]
    assert a["config_checksum"] == b["config_checksum"]
    assert b.get("idempotent") is True

    with pytest.raises(ResearchLabError) as ei:
        svc.run_experiment(a["experiment_id"])
    assert ei.value.code == "PRE_REGISTRATION_REQUIRED"

    pr = svc.pre_register(a["experiment_id"])
    assert pr["status"] == "PRE_REGISTERED"
    svc.registry.mark_ready(a["experiment_id"])
    run = svc.run_experiment(a["experiment_id"])
    assert run.get("ok") is True
    assert run.get("preserved_oos_failures")


def test_m272_config_change_requires_new_version(svc: ResearchLabService):
    a = svc.create_experiment(name="ver_probe", strategy_ids=["tf_dual_ma"], random_seed=1)
    # Different seed → different experiment id (config-hash identity)
    b = svc.create_experiment(name="ver_probe", strategy_ids=["tf_dual_ma"], random_seed=2)
    assert a["experiment_id"] != b["experiment_id"]
    # Supersession creates child version lineage
    sup = svc.registry.supersede(a["experiment_id"], "v1", "v2", random_seed=99)
    assert sup["ok"] is True
    assert sup["new"]["experiment_version"] == "v2"


def test_m272_immutable_completed_and_replay(svc: ResearchLabService):
    e = svc.create_experiment(name="imm_probe", strategy_ids=["tf_dual_ma"], random_seed=3)
    svc.pre_register(e["experiment_id"])
    svc.registry.mark_ready(e["experiment_id"])
    svc.run_experiment(e["experiment_id"])
    got = svc.get_experiment(e["experiment_id"])
    assert got["immutable"] is True
    replay = svc.replay_experiment(e["experiment_id"])
    assert replay["reproducible"] is True
    assert replay["result"] is not None


def test_m272_lineage_and_invalidate(svc: ResearchLabService):
    e = svc.create_experiment(name="lin_probe", strategy_ids=["tf_dual_ma"], random_seed=4)
    lin = svc.experiment_lineage(e["experiment_id"])
    assert lin["ok"]
    inv = svc.registry.invalidate(e["experiment_id"], "v1", "test_invalidation")
    assert inv["status"] == "INVALIDATED"


def test_m273_comparison_common_assumptions_and_failures(svc: ResearchLabService):
    cmp = svc.compare_strategies(["tf_dual_ma", "mom_rs_equity", "mr_bollinger_reversion"])
    assert cmp["ok"]
    assert cmp["common_assumptions"]["selection_on_final_test"] is False
    assert cmp["rules"]["no_hiding_failed_experiments"] is True
    assert any(f["state"] == "OUT_OF_SAMPLE_FAILED" for f in cmp["preserved_oos_failures"])
    for sc in cmp["scorecards"]:
        assert sc.get("data_label")
        assert sc.get("is_synthetic") is True


def test_m274_robustness_and_multiple_testing(svc: ResearchLabService):
    rob = svc.analyse_robustness("tf_dual_ma", n_parameter_trials=9)
    assert rob["ok"]
    assert "parameter_robustness" in rob
    assert "multiple_testing" in rob
    assert rob["multiple_testing"]["raw_p_values_treated_as_proof"] is False
    assert rob["holdout_isolation"] is True
    assert rob["overall_classification"]


def test_m275_regimes_no_lookahead(svc: ResearchLabService):
    defs = svc.build_regimes()
    assert defs["test_set_used_for_thresholds"] is False
    assert defs["macro_regimes_fabricated"] is False
    cls = svc.classify_regimes()
    assert cls["point_in_time_controls"]["future_information_used"] is False
    assert cls["unknown_regime_supported"] is True
    val = svc.validate_regimes()
    assert "strategy_by_regime" in val


def test_m276_portfolio_constraints_and_leverage(svc: ResearchLabService):
    from saathi.platform.tg.research_lab.comparison import _simulate_strategy_returns
    assets = ["A", "B"]
    rets = {a: _simulate_strategy_returns(a, n=60, seed=i)["returns"] for i, a in enumerate(assets)}
    good = svc.build_portfolio(assets, rets, method="equal_weight", constraints={
        "maximum_asset_weight": 0.6, "leverage_limit": 1.0, "turnover_limit": 1.0,
        "concentration_limit": 0.7, "cash_minimum": 0.0, "gross_exposure": 1.0, "net_exposure": 1.0,
    })
    assert good["ok"] is True
    assert good["hidden_leverage"] is False
    assert abs(sum(good["weights"].values()) + good.get("cash", 0) - 1.0) < 1e-6 or sum(good["weights"].values()) <= 1.0 + 1e-6

    bad = svc.build_portfolio(assets, rets, method="equal_weight", constraints={
        "leverage_limit": 2.0, "maximum_asset_weight": 0.6,
    })
    assert bad["ok"] is False
    assert "LEVERAGE" in bad.get("code", "") or bad.get("state") == "REJECTED"


def test_m276_inverse_vol_and_infeasible(svc: ResearchLabService):
    from saathi.platform.tg.research_lab.comparison import _simulate_strategy_returns
    assets = ["X", "Y", "Z"]
    rets = {a: _simulate_strategy_returns(a, n=50, seed=i + 10)["returns"] for i, a in enumerate(assets)}
    inv = svc.build_portfolio(assets, rets, method="inverse_volatility", constraints={
        "maximum_asset_weight": 0.5, "leverage_limit": 1.0, "turnover_limit": 1.0,
        "concentration_limit": 0.6, "gross_exposure": 1.0, "net_exposure": 1.0,
    })
    assert inv["ok"] is True
    # impossible max weight for 1 asset equal with cap 0.1 and 3 assets → investable/3 > 0.1
    bad = svc.build_portfolio(assets, rets, method="equal_weight", constraints={
        "maximum_asset_weight": 0.1, "leverage_limit": 1.0, "gross_exposure": 1.0, "net_exposure": 1.0,
    })
    assert bad["ok"] is False


def test_m277_ensemble_and_leakage(svc: ResearchLabService):
    ens = svc.build_ensemble(["tf_dual_ma", "mom_rs_equity"], method="equal_weight")
    assert ens["allocation_rule"]["frozen"] is True
    assert ens["leakage_controls"]["test_set_allocation_tuning"] is False
    leak = svc.build_ensemble(["tf_dual_ma", "mom_rs_equity"], leakage_tune_on_test=True)
    assert leak["state"] == "LEAKAGE_BLOCKED"


def test_m278_stress_and_candidate_gates(svc: ResearchLabService):
    from saathi.platform.tg.research_lab.comparison import _simulate_strategy_returns
    assets = ["tf_dual_ma", "mom_rs_equity"]
    rets = {a: _simulate_strategy_returns(a, n=80, seed=i)["returns"] for i, a in enumerate(assets)}
    st = svc.run_stress({a: 0.5 for a in assets}, rets)
    assert st["ok"]
    assert "historical_stresses" in st
    assert "hypothetical_stresses" in st
    assert "statistical_stresses" in st

    cand = svc.evaluate_candidate(
        "strategy", "tf_dual_ma",
        oos_failed=True,
        pre_registered=True,
        evidence_complete=True,
        gates={
            "governed_historical_data": True,
            "pre_registered_experiment": True,
            "out_of_sample_evaluated": True,
            "walk_forward_completed": True,
            "transaction_costs_included": True,
            "slippage_included": True,
            "robustness_completed": True,
            "multiple_testing_disclosed": True,
            "regime_analysis_completed": True,
            "stress_testing_completed": True,
            "evidence_complete": True,
            "authority_violation": False,
            "human_review_required": True,
        },
    )
    assert cand["state"] == "VALIDATION_FAILED"
    assert cand["paper_candidate_authorises_execution"] is False
    assert cand["human_review_status"] == "REQUIRED"

    with pytest.raises(ResearchLabError) as ei:
        svc.candidates.human_approve_paper_candidate(cand["candidate_id"], actor="system")
    assert ei.value.code == "HUMAN_REVIEW_BYPASS_DETECTED"


def test_m278_reject_revoke(svc: ResearchLabService):
    gates = {
        "governed_historical_data": True,
        "pre_registered_experiment": True,
        "out_of_sample_evaluated": True,
        "walk_forward_completed": True,
        "transaction_costs_included": True,
        "slippage_included": True,
        "robustness_completed": True,
        "multiple_testing_disclosed": True,
        "regime_analysis_completed": True,
        "stress_testing_completed": True,
        "evidence_complete": True,
        "authority_violation": False,
        "human_review_required": True,
    }
    cand = svc.evaluate_candidate(
        "strategy", "mom_rs_equity",
        oos_failed=False,
        robustness_failed=False,
        stress_breaches=0,
        pre_registered=True,
        evidence_complete=True,
        gates=gates,
    )
    assert cand["state"] == "COMMITTEE_REVIEW_REQUIRED"
    approved = svc.request_candidate_review(cand["candidate_id"], actor="alice")
    assert "PAPER_CANDIDATE" in approved["state"]
    assert approved["paper_candidate_authorises_execution"] is False
    rev = svc.revoke_candidate(cand["candidate_id"], "new_evidence")
    assert rev["state"] == "REVOKED"


def test_m279_refusals_and_certify(svc: ResearchLabService):
    assert svc.refuse_broker()["refused"] is True
    assert svc.refuse_credentials("k")["refused"] is True
    assert svc.refuse_order()["refused"] is True
    assert svc.refuse_canary()["refused"] is True
    assert svc.refuse_paper_execution()["refused"] is True
    cert = svc.certify()
    assert cert["ok"] is True
    assert cert["verdict"] == TERMINAL_VERDICT
    assert all(f["state"] == "OUT_OF_SAMPLE_FAILED" for f in PRESERVED_OOS_FAILURES)


def test_m279_dashboard_and_export(svc: ResearchLabService):
    svc.bootstrap_demo_pipeline()
    dash = svc.dashboard()
    assert dash["title"]
    assert dash["LIVE_TRADING_AUTHORIZED"] is False
    reg = svc.export_registry()
    assert reg["schema"] == "M272_EXPERIMENT_REGISTRY"
    assert reg["invariant"]["certified_experiment_requires_pre_registration"] is True
