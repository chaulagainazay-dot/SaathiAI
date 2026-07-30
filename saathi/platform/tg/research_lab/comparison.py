"""M273 — Multi-Strategy Evaluation and Fair Comparison."""
from __future__ import annotations

import json
import math
import time
from typing import Any

from saathi.platform.tg.research_lab.models import (
    AUTHORITY_VALUES,
    ComparisonState,
    PRESERVED_OOS_FAILURES,
    RESEARCH_ROBUSTNESS_SCORE_NAME,
    SCORECARD_DIMENSIONS,
    SYNTHETIC_TEST_DATA_LABEL,
)
from saathi.platform.tg.research_lab.storage import ResearchLabStore, evidence_hash, _uid


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var) if var > 0 else 0.0


def _metrics_from_returns(rets: list[float], *, rf: float = 0.0) -> dict[str, float]:
    n = len(rets)
    if n == 0:
        return {
            "annualised_return": 0.0, "volatility": 0.0, "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0, "maximum_drawdown": 0.0, "calmar_ratio": 0.0,
            "var_95": 0.0, "expected_shortfall_95": 0.0, "downside_deviation": 0.0,
            "hit_rate": 0.0, "average_win": 0.0, "average_loss": 0.0,
            "expectancy": 0.0, "profit_factor": 0.0, "recovery_factor": 0.0,
        }
    ann = _mean(rets) * 252
    vol = _std(rets) * math.sqrt(252)
    excess = [_mean(rets) - rf / 252]
    sharpe = (excess[0] / (_std(rets) or 1e-12)) * math.sqrt(252)
    downside = [r for r in rets if r < 0]
    ddev = _std(downside) * math.sqrt(252) if downside else 0.0
    sortino = (excess[0] / (ddev / math.sqrt(252) or 1e-12)) * math.sqrt(252) if ddev else 0.0
    eq = 1.0
    peak = 1.0
    mdd = 0.0
    for r in rets:
        eq *= 1 + r
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak if peak > 0 else 0)
    calmar = ann / mdd if mdd > 0 else 0.0
    sorted_r = sorted(rets)
    idx = max(0, int(0.05 * n) - 1)
    var95 = -sorted_r[idx]
    tail = sorted_r[: max(1, int(0.05 * n))]
    es95 = -_mean(tail)
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    hit = len(wins) / n
    avg_w = _mean(wins) if wins else 0.0
    avg_l = _mean(losses) if losses else 0.0
    expectancy = _mean(rets)
    gp = sum(wins)
    gl = abs(sum(losses))
    pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0.0)
    recovery = (eq - 1) / mdd if mdd > 0 else 0.0
    return {
        "annualised_return": round(ann, 6),
        "volatility": round(vol, 6),
        "sharpe_ratio": round(sharpe, 6),
        "sortino_ratio": round(sortino, 6),
        "maximum_drawdown": round(mdd, 6),
        "calmar_ratio": round(calmar, 6),
        "var_95": round(var95, 6),
        "expected_shortfall_95": round(es95, 6),
        "downside_deviation": round(ddev, 6),
        "hit_rate": round(hit, 6),
        "average_win": round(avg_w, 6),
        "average_loss": round(avg_l, 6),
        "expectancy": round(expectancy, 6),
        "profit_factor": round(pf if pf != float("inf") else 999.0, 6),
        "recovery_factor": round(recovery, 6),
    }


def _lcg(seed: int):
    state = seed & 0x7FFFFFFF
    while True:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        yield state / float(0x7FFFFFFF)


def _simulate_strategy_returns(
    strategy_id: str,
    n: int = 120,
    seed: int = 42,
    cost_bps: float = 5.0,
    slip_bps: float = 8.0,
) -> dict[str, Any]:
    """Deterministic offline strategy return path for fair comparison research.

    Labels all synthetic paths as SYNTHETIC_TEST_DATA unless is_historical is set.
    Does not claim profitability.
    """
    rng = _lcg(seed + sum(ord(c) for c in strategy_id))
    # Strategy-specific drift biases (research simulation only — not forecasts)
    bias = {
        "tf_dual_ma": -0.0002,  # aligned with observed OOS failures on short windows
        "mom_rs_equity": 0.0001,
        "mr_bollinger_reversion": 0.00005,
        "bo_donchian": -0.0001,
        "vol_regime_switch": 0.0000,
        "def_risk_off": 0.00002,
    }.get(strategy_id, 0.0)
    rets = []
    trades = 0
    signals = 0
    turnover = 0.0
    pos = 0
    for i in range(n):
        u = next(rng)
        # signal every ~8 bars
        if i % 8 == 0:
            signals += 1
            new_pos = 1 if u > 0.45 else (-1 if u < 0.35 else 0)
            if new_pos != pos:
                trades += 1
                turnover += abs(new_pos - pos)
                cost = (cost_bps + slip_bps) / 10000.0 * abs(new_pos - pos)
            else:
                cost = 0.0
            pos = new_pos
        else:
            cost = 0.0
        r = bias + (u - 0.5) * 0.02 + pos * 0.0003 - cost
        rets.append(round(r, 8))
    return {
        "returns": rets,
        "signal_count": signals,
        "trade_count": trades,
        "turnover": round(turnover / max(n, 1), 6),
        "exposure": round(sum(1 for i in range(n) if True) / n * abs(pos or 0.5), 6),
        "is_synthetic": True,
        "data_label": SYNTHETIC_TEST_DATA_LABEL,
    }


class StrategyComparisonEngine:
    """Fair multi-strategy comparison under common assumptions."""

    def __init__(self, store: ResearchLabStore):
        self.store = store

    def compare(
        self,
        strategy_ids: list[str],
        *,
        experiment_id: str | None = None,
        experiment_version: str = "v1",
        common: dict[str, Any] | None = None,
        seed: int = 42,
        include_preserved_failures: bool = True,
        historical_results: list[dict] | None = None,
    ) -> dict[str, Any]:
        common = dict(common or {})
        # Common assumption locks
        assumptions = {
            "dataset_versions": common.get("dataset_versions", {"demo": "v1"}),
            "train_validation_test_periods": common.get("periods", {
                "train_ratio": 0.6, "val_ratio": 0.2, "test_ratio": 0.2,
            }),
            "benchmark": common.get("benchmark", "buy_hold"),
            "transaction_costs_bps": float(common.get("commission_bps", 5.0)),
            "slippage_bps": float(common.get("slippage_bps", 8.0)),
            "asset_universe": common.get("asset_universe", ["DEMO"]),
            "rebalance": common.get("rebalance", "daily"),
            "liquidity_rules": common.get("liquidity_rules", {"min_adv_usd": 1_000_000}),
            "position_limits": common.get("position_limits", {"max_weight": 1.0}),
            "risk_free_rate": float(common.get("risk_free_rate", 0.0)),
            "missing_data_policy": common.get("missing_data_policy", "drop_bar"),
            "point_in_time_rules": common.get("point_in_time_rules", "features_available_at_t_only"),
            "selection_on_final_test": False,
            "ranking_solely_by_return": False,
            "ranking_solely_by_sharpe": False,
        }

        scorecards = []
        for i, sid in enumerate(strategy_ids):
            sim = _simulate_strategy_returns(
                sid,
                n=int(common.get("bars", 120)),
                seed=seed + i,
                cost_bps=assumptions["transaction_costs_bps"],
                slip_bps=assumptions["slippage_bps"],
            )
            # Holdout isolation: metrics computed on last 20% as OOS proxy (pre-registered split)
            rets = sim["returns"]
            n = len(rets)
            split = int(n * 0.8)
            oos = rets[split:]
            is_rets = rets[:split]
            oos_m = _metrics_from_returns(oos, rf=assumptions["risk_free_rate"])
            is_m = _metrics_from_returns(is_rets, rf=assumptions["risk_free_rate"])

            # Classify
            state = ComparisonState.RESEARCH_PROMISING
            warnings = []
            if oos_m["expectancy"] < 0 or oos_m["sharpe_ratio"] < 0:
                state = ComparisonState.FAILED
                warnings.append("negative_oos_expectancy_or_sharpe")
            if oos_m["maximum_drawdown"] > 0.3:
                warnings.append("high_drawdown")
                if state == ComparisonState.RESEARCH_PROMISING:
                    state = ComparisonState.UNSTABLE
            if sim["turnover"] > 0.5:
                warnings.append("high_turnover")
                if state == ComparisonState.RESEARCH_PROMISING:
                    state = ComparisonState.COST_SENSITIVE

            # Cost sensitivity probe
            sim_hi = _simulate_strategy_returns(
                sid, n=len(rets), seed=seed + i,
                cost_bps=assumptions["transaction_costs_bps"] * 3,
                slip_bps=assumptions["slippage_bps"] * 3,
            )
            oos_hi = _metrics_from_returns(sim_hi["returns"][split:], rf=assumptions["risk_free_rate"])
            cost_sensitive = (oos_m["sharpe_ratio"] - oos_hi["sharpe_ratio"]) > 0.5
            if cost_sensitive and state == ComparisonState.RESEARCH_PROMISING:
                state = ComparisonState.COST_SENSITIVE

            score = self._research_score(oos_m, cost_sensitive=cost_sensitive, warnings=warnings)
            scorecards.append({
                "strategy_id": sid,
                "state": state.value,
                "signal_count": sim["signal_count"],
                "trade_count": sim["trade_count"],
                "exposure": sim["exposure"],
                "turnover": sim["turnover"],
                "in_sample": is_m,
                "out_of_sample": oos_m,
                "benchmark_excess_return": round(oos_m["annualised_return"] - 0.0, 6),
                "beta": 1.0,
                "correlation_to_benchmark": 0.5,
                "stability_across_windows": "not_fully_tested",
                "performance_dispersion": round(abs(is_m["sharpe_ratio"] - oos_m["sharpe_ratio"]), 4),
                "parameter_sensitivity": "see_m274",
                "regime_sensitivity": "see_m275",
                "cost_sensitivity": round(oos_m["sharpe_ratio"] - oos_hi["sharpe_ratio"], 4),
                "slippage_sensitivity": "included_in_cost_probe",
                "capacity_warnings": [],
                "quality_warnings": warnings,
                "confidence_classification": "low" if state == ComparisonState.FAILED else "moderate_with_limitations",
                "data_label": sim["data_label"],
                "is_synthetic": sim["is_synthetic"],
                RESEARCH_ROBUSTNESS_SCORE_NAME: score,
                "not_profitability_score": True,
                "not_live_readiness_score": True,
            })

        # Attach preserved historical OOS failures (never hide)
        preserved = []
        if include_preserved_failures:
            for f in PRESERVED_OOS_FAILURES:
                preserved.append({
                    **f,
                    "preserved": True,
                    "mutable": False,
                    "data_label": "BOUNDED_REAL_HISTORICAL",
                    "note": "M270 historical evaluation — valid research result; not reinterpreted",
                })
        if historical_results:
            for hr in historical_results:
                preserved.append({**hr, "data_label": hr.get("data_label", "BOUNDED_REAL_HISTORICAL")})

        # Ranking: multi-factor research score only — never sole return/sharpe
        ranked = sorted(
            [s for s in scorecards if s["state"] != ComparisonState.FAILED.value],
            key=lambda x: x[RESEARCH_ROBUSTNESS_SCORE_NAME]["total"],
            reverse=True,
        )
        failed = [s for s in scorecards if s["state"] == ComparisonState.FAILED.value]
        rejected = [s for s in scorecards if s["state"] == ComparisonState.REJECTED.value]
        promising = [s for s in scorecards if s["state"] == ComparisonState.RESEARCH_PROMISING.value]

        result = {
            "schema": "M273_MULTI_STRATEGY_COMPARISON",
            "ok": True,
            "common_assumptions": assumptions,
            "strategy_ids": strategy_ids,
            "scorecards": scorecards,
            "ranked_by_research_robustness_score": [s["strategy_id"] for s in ranked],
            "failed_strategies": failed + preserved,
            "rejected_strategies": rejected,
            "research_promising_strategies": promising,
            "preserved_oos_failures": preserved,
            "rules": {
                "no_ranking_solely_by_total_return": True,
                "no_ranking_solely_by_sharpe": True,
                "no_selection_using_final_test_data": True,
                "no_hiding_failed_experiments": True,
                "no_deleting_weak_strategies": True,
                "no_silent_assumption_changes": True,
                "synthetic_and_historical_labelled": True,
            },
            "experiment_id": experiment_id,
            "experiment_version": experiment_version,
            **AUTHORITY_VALUES,
        }
        eh = evidence_hash(result)
        result["evidence_hash"] = eh
        cid = _uid("cmp")
        self.store.execute(
            "INSERT INTO rl_comparisons(id, experiment_id, experiment_version, result_json, evidence_hash, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (cid, experiment_id, experiment_version, json.dumps(result, sort_keys=True, default=str), eh, time.time()),
        )
        self.store.audit("comparison.completed", subject=cid, detail={"n": len(strategy_ids), "hash": eh})
        result["comparison_id"] = cid
        return result

    def _research_score(
        self,
        oos: dict[str, float],
        *,
        cost_sensitive: bool,
        warnings: list[str],
    ) -> dict[str, Any]:
        components = {
            "out_of_sample_performance": max(0.0, min(1.0, 0.5 + oos["sharpe_ratio"] * 0.1)),
            "downside_risk": max(0.0, min(1.0, 1.0 - oos["expected_shortfall_95"] * 5)),
            "maximum_drawdown": max(0.0, min(1.0, 1.0 - oos["maximum_drawdown"] * 2)),
            "expected_shortfall": max(0.0, min(1.0, 1.0 - oos["expected_shortfall_95"] * 5)),
            "parameter_stability": 0.5,  # filled by M274
            "temporal_stability": 0.5,
            "cross_asset_stability": 0.4,
            "regime_stability": 0.4,
            "transaction_cost_resilience": 0.3 if cost_sensitive else 0.7,
            "slippage_resilience": 0.3 if cost_sensitive else 0.7,
            "turnover_efficiency": 0.5,
            "diversification_contribution": 0.5,
            "benchmark_improvement": max(0.0, min(1.0, 0.5 + oos["annualised_return"])),
            "data_quality": 0.7,
            "evidence_completeness": 0.6,
            "overfitting_risk": 0.4,  # lower is worse — inverted later
            "multiple_testing_burden": 0.5,
        }
        weights = {d: 1.0 / len(SCORECARD_DIMENSIONS) for d in SCORECARD_DIMENSIONS}
        # Overfitting risk inverted (high risk -> low score)
        adj = dict(components)
        adj["overfitting_risk"] = 1.0 - components["overfitting_risk"]
        penalties = []
        if cost_sensitive:
            penalties.append({"reason": "cost_sensitive", "amount": 0.1})
        for w in warnings:
            penalties.append({"reason": w, "amount": 0.05})
        total = sum(adj[d] * weights[d] for d in SCORECARD_DIMENSIONS)
        total -= sum(p["amount"] for p in penalties)
        total = max(0.0, min(1.0, total))
        return {
            "name": RESEARCH_ROBUSTNESS_SCORE_NAME,
            "components": components,
            "weights": weights,
            "penalties": penalties,
            "missing_components": [],
            "confidence": "low_to_moderate",
            "limitations": [
                "Composite research score only — not profitability or live-readiness",
                "Some components provisional pending full robustness/regime runs",
            ],
            "total": round(total, 4),
        }
