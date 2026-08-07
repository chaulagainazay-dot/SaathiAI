"""M277 — Strategy ensembles and adaptive allocation (research only)."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.research_lab.allocation import freeze_allocation_rule
from saathi.platform.tg.research_lab.comparison import _metrics_from_returns, _simulate_strategy_returns
from saathi.platform.tg.research_lab.models import AUTHORITY_VALUES, EnsembleMethod, EnsembleState
from saathi.platform.tg.research_lab.storage import ResearchLabStore, evidence_hash, _uid


class EnsembleEngine:
    def __init__(self, store: ResearchLabStore):
        self.store = store

    def build(
        self,
        strategy_ids: list[str],
        *,
        method: str = EnsembleMethod.EQUAL_WEIGHT.value,
        seed: int = 42,
        train_ratio: float = 0.6,
        val_ratio: float = 0.2,
        leakage_tune_on_test: bool = False,
        turnover_limit: float = 1.0,
        regime_labels_train: list[str] | None = None,
    ) -> dict[str, Any]:
        if leakage_tune_on_test:
            return {
                "schema": "M277_STRATEGY_ENSEMBLE_REPORT",
                "ok": False,
                "state": EnsembleState.LEAKAGE_BLOCKED.value,
                "code": "ALLOCATION_LEAKAGE_DETECTED",
                "message": "Allocation rules must not be tuned on final test data",
                "fail_closed": True,
                **AUTHORITY_VALUES,
            }

        # Fit on train, freeze, validate on val, evaluate once on test
        paths = {}
        for i, sid in enumerate(strategy_ids):
            sim = _simulate_strategy_returns(sid, n=150, seed=seed + i)
            paths[sid] = sim["returns"]

        n = min(len(v) for v in paths.values())
        t_end = int(n * train_ratio)
        v_end = int(n * (train_ratio + val_ratio))

        # Train-fit weights
        train_vols = {}
        train_sharpes = {}
        for sid, rets in paths.items():
            m = _metrics_from_returns(rets[:t_end])
            train_vols[sid] = max(m["volatility"], 1e-6)
            train_sharpes[sid] = m["sharpe_ratio"]

        if method == EnsembleMethod.EQUAL_WEIGHT.value:
            w = {sid: 1.0 / len(strategy_ids) for sid in strategy_ids}
        elif method == EnsembleMethod.RISK_WEIGHTED.value:
            inv = {sid: 1.0 / train_vols[sid] for sid in strategy_ids}
            s = sum(inv.values())
            w = {sid: inv[sid] / s for sid in strategy_ids}
        elif method == EnsembleMethod.CONFIDENCE_WEIGHTED.value:
            # confidence proxy from train sharpe clipped
            raw = {sid: max(0.0, train_sharpes[sid]) for sid in strategy_ids}
            s = sum(raw.values()) or 1.0
            if s <= 0:
                w = {sid: 1.0 / len(strategy_ids) for sid in strategy_ids}
            else:
                w = {sid: raw[sid] / s for sid in strategy_ids}
        elif method == EnsembleMethod.REGIME_CONDITIONED.value:
            # Pre-defined: if majority train regime is downward, prefer defensive/vol
            regime_labels_train = regime_labels_train or ["sideways"] * t_end
            # weights fitted only on train regime distribution
            w = {sid: 1.0 / len(strategy_ids) for sid in strategy_ids}
            if "downward_trend" in regime_labels_train:
                # tilt to lower vol
                inv = {sid: 1.0 / train_vols[sid] for sid in strategy_ids}
                s = sum(inv.values())
                w = {sid: inv[sid] / s for sid in strategy_ids}
        elif method == EnsembleMethod.CAPPED_RANKING.value:
            ranked = sorted(strategy_ids, key=lambda s: train_sharpes[s], reverse=True)
            w = {sid: 0.0 for sid in strategy_ids}
            top = ranked[: max(1, len(ranked) // 2)]
            for sid in top:
                w[sid] = 1.0 / len(top)
        else:
            # drawdown_controlled / vol targeted → risk weighted
            inv = {sid: 1.0 / train_vols[sid] for sid in strategy_ids}
            s = sum(inv.values())
            w = {sid: inv[sid] / s for sid in strategy_ids}

        rule = freeze_allocation_rule(method, strategy_ids, w, version="v1", fitted_on="training")

        # Validation metrics with frozen weights
        def ensemble_rets(start: int, end: int) -> list[float]:
            out = []
            for t in range(start, end):
                out.append(sum(w[sid] * paths[sid][t] for sid in strategy_ids))
            return out

        val_m = _metrics_from_returns(ensemble_rets(t_end, v_end))
        test_m = _metrics_from_returns(ensemble_rets(v_end, n))

        # Baselines
        eq_w = {sid: 1.0 / len(strategy_ids) for sid in strategy_ids}
        def base_rets(weights, start, end):
            return [sum(weights[sid] * paths[sid][t] for sid in strategy_ids) for t in range(start, end)]
        eq_test = _metrics_from_returns(base_rets(eq_w, v_end, n))
        # best single without test leakage (selected on train)
        best_sid = max(strategy_ids, key=lambda s: train_sharpes[s])
        best_test = _metrics_from_returns(paths[best_sid][v_end:n])

        # Turnover vs equal weight rebalance proxy
        turnover = 0.5 * sum(abs(w[sid] - eq_w[sid]) for sid in strategy_ids)
        state = EnsembleState.RESEARCH_VALIDATED_WITH_LIMITATIONS
        if turnover > turnover_limit:
            state = EnsembleState.TURNOVER_EXCESSIVE
        elif test_m["sharpe_ratio"] < eq_test["sharpe_ratio"] and test_m["sharpe_ratio"] < best_test["sharpe_ratio"]:
            state = EnsembleState.NO_BENEFIT_OVER_BASELINE
        elif test_m["expectancy"] < 0:
            state = EnsembleState.REJECTED
        elif abs(max(w.values()) - min(w.values())) < 1e-9 and method != EnsembleMethod.EQUAL_WEIGHT.value:
            state = EnsembleState.UNSTABLE

        # Max weight concentration
        if max(w.values()) > 0.9:
            state = EnsembleState.UNSTABLE

        result = {
            "schema": "M277_STRATEGY_ENSEMBLE_REPORT",
            "ok": state not in (
                EnsembleState.LEAKAGE_BLOCKED.value,
                EnsembleState.REJECTED.value,
            ),
            "state": state.value,
            "method": method,
            "strategy_ids": strategy_ids,
            "weights": {k: round(v, 6) for k, v in w.items()},
            "allocation_rule": rule,
            "workflow": {
                "fit_on": "training",
                "freeze_allocation_rules": True,
                "validate_on": "validation",
                "evaluate_once_on": "test",
                "revisions": 0,
                "trial_count": 1,
            },
            "validation_metrics": val_m,
            "test_metrics": test_m,
            "baselines": {
                "equal_weight": eq_test,
                "best_single_train_selected": {"strategy_id": best_sid, **best_test},
            },
            "turnover": round(turnover, 6),
            "leakage_controls": {
                "target_leakage": False,
                "test_set_allocation_tuning": False,
                "hidden_future_regime_information": False,
                "selection_on_final_test": False,
            },
            "explanation": {
                "selected_strategies": strategy_ids,
                "excluded_strategies": [],
                "assigned_weights": w,
                "regime_inputs": regime_labels_train[:5] if regime_labels_train else [],
                "confidence_inputs": train_sharpes,
                "risk_inputs": train_vols,
                "cost_assumptions": {"included_in_path_sim": True},
                "turnover_implications": turnover,
                "invalidation_criteria": ["test_leakage", "turnover_excess", "oos_failure"],
            },
            "limitations": [
                "Research ensemble only; does not authorize execution",
                "Synthetic paths unless bound to governed historical runs",
            ],
            **AUTHORITY_VALUES,
        }
        eh = evidence_hash(result)
        result["evidence_hash"] = eh
        eid = _uid("ens")
        self.store.execute(
            "INSERT INTO rl_ensembles(id, method, config_json, result_json, evidence_hash, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (eid, method, json.dumps({"strategy_ids": strategy_ids, "method": method}, sort_keys=True),
             json.dumps(result, sort_keys=True, default=str), eh, time.time()),
        )
        result["ensemble_id"] = eid
        return result
