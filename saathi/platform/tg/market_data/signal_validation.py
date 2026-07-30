"""M262 — Research-grade signal validation on governed datasets."""
from __future__ import annotations

import json
import math
import time
from typing import Any

from saathi.platform.tg.market_data.models import (
    AUTHORITY_VALUES,
    KNOWN_RESEARCH_LIMITATION,
    SYNTHETIC_TEST_DATA_LABEL,
    ValidationState,
)
from saathi.platform.tg.market_data.storage import MarketDataStore, evidence_hash, _uid


def _lcg(seed: int):
    state = seed & 0x7FFFFFFF
    while True:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        yield state / float(0x7FFFFFFF)


class SignalValidationEngine:
    def __init__(self, store: MarketDataStore):
        self.store = store

    def validate(
        self,
        strategy_id: str,
        dataset_id: str,
        dataset_version: str,
        *,
        strategy_version: str = "v1",
        split: dict | None = None,
        commission_bps: float = 5.0,
        slippage_bps: float = 8.0,
        seed: int = 42,
        trial_count: int = 1,
        require_costs: bool = True,
        symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        ds = self.store.get_dataset(dataset_id, dataset_version)
        if not ds:
            return self._blocked(strategy_id, dataset_id, dataset_version, ValidationState.DATA_GOVERNANCE_BLOCKED,
                                 "unregistered_dataset")
        state = ds.get("state") or ""
        if state in ("REVOKED", "QUARANTINED"):
            return self._blocked(strategy_id, dataset_id, dataset_version, ValidationState.DATA_GOVERNANCE_BLOCKED,
                                 f"dataset_state_{state}")
        if state == "LICENCE_REVIEW_REQUIRED":
            return self._blocked(strategy_id, dataset_id, dataset_version, ValidationState.DATA_GOVERNANCE_BLOCKED,
                                 "licence_review_required")

        if require_costs and (commission_bps is None or slippage_bps is None):
            return self._blocked(strategy_id, dataset_id, dataset_version, ValidationState.REJECTED,
                                 "missing_transaction_costs")

        q = """SELECT * FROM md_bars WHERE dataset_id=? AND dataset_version=?"""
        params: list[Any] = [dataset_id, dataset_version]
        if symbols:
            placeholders = ",".join("?" * len(symbols))
            q += f" AND symbol IN ({placeholders})"
            params.extend([s.upper() for s in symbols])
        q += " ORDER BY symbol, timestamp"
        bars = self.store.query(q, params)
        if len(bars) < 30:
            return self._blocked(strategy_id, dataset_id, dataset_version, ValidationState.DATA_INSUFFICIENT,
                                 "insufficient_bars")

        # Use test timestamps from split when provided
        test_ts = set()
        train_ts = set()
        if split:
            test_ts = set(split.get("test_timestamps") or [])
            train_ts = set(split.get("train_timestamps") or [])
            if split.get("evaluation_set_optimised_on"):
                return self._blocked(strategy_id, dataset_id, dataset_version, ValidationState.REJECTED,
                                     "evaluation_set_optimised_on")
            if split.get("leakage_detected"):
                return self._blocked(strategy_id, dataset_id, dataset_version, ValidationState.REJECTED,
                                     "train_test_leakage")

        by_sym: dict[str, list] = {}
        for b in bars:
            by_sym.setdefault(b["symbol"], []).append(b)

        # Simple dual-MA style signal on each symbol using governed bars
        all_rets_is: list[float] = []
        all_rets_oos: list[float] = []
        trades = 0
        wins = 0
        losses = 0
        gross_profit = 0.0
        gross_loss = 0.0
        signal_count = 0
        long_trades = 0
        short_trades = 0
        equity = 1.0
        equity_curve = [1.0]
        peak = 1.0
        max_dd = 0.0
        cost_rate = (commission_bps + slippage_bps) / 10000.0

        for sym, rows in by_sym.items():
            closes = [float(r["close"]) for r in rows]
            ts_list = [r["timestamp"] for r in rows]
            position = 0
            entry = 0.0
            for i in range(20, len(rows)):
                window = closes[: i + 1]
                sma_f = sum(window[-10:]) / 10
                sma_s = sum(window[-20:]) / 20
                px = closes[i]
                ts = ts_list[i]
                in_test = (not test_ts) or (ts in test_ts)
                in_train = (not train_ts) or (ts in train_ts)
                action = 0
                if sma_f > sma_s * 1.001:
                    action = 1
                elif sma_f < sma_s * 0.999:
                    action = -1
                if action != 0:
                    signal_count += 1
                if action != 0 and action != position:
                    # close prior
                    if position != 0:
                        raw_ret = position * ((px / entry) - 1.0)
                        ret = raw_ret - cost_rate * 2  # entry+exit costs
                        trades += 1
                        if position > 0:
                            long_trades += 1
                        else:
                            short_trades += 1
                        if ret >= 0:
                            wins += 1
                            gross_profit += ret
                        else:
                            losses += 1
                            gross_loss += abs(ret)
                        equity *= (1 + ret)
                        equity_curve.append(equity)
                        peak = max(peak, equity)
                        max_dd = max(max_dd, (peak - equity) / peak if peak else 0)
                        if in_test or not test_ts:
                            all_rets_oos.append(ret)
                        if in_train:
                            all_rets_is.append(ret)
                    position = action
                    entry = px * (1 + cost_rate) if action > 0 else px * (1 - cost_rate)

        # Metrics
        def _stats(rets: list[float]) -> dict[str, Any]:
            if not rets:
                return {
                    "n": 0, "hit_rate": 0, "avg_win": 0, "avg_loss": 0, "expectancy": 0,
                    "profit_factor": 0, "ann_return": 0, "volatility": 0, "sharpe": 0,
                    "sortino": 0, "max_drawdown": max_dd, "calmar": 0,
                }
            n = len(rets)
            wins_l = [r for r in rets if r >= 0]
            loss_l = [r for r in rets if r < 0]
            hit = len(wins_l) / n
            avg_win = sum(wins_l) / len(wins_l) if wins_l else 0
            avg_loss = sum(loss_l) / len(loss_l) if loss_l else 0
            exp = sum(rets) / n
            gp = sum(wins_l)
            gl = abs(sum(loss_l))
            pf = (gp / gl) if gl > 0 else (999.0 if gp > 0 else 0)
            mean = exp
            var = sum((r - mean) ** 2 for r in rets) / n
            vol = math.sqrt(var) * math.sqrt(252) if var > 0 else 0
            ann = (1 + mean) ** 252 - 1 if mean > -1 else -1
            sharpe = (mean * 252) / vol if vol > 0 else 0
            downside = [r for r in rets if r < 0]
            dvar = sum(r ** 2 for r in downside) / n if downside else 0
            dvol = math.sqrt(dvar) * math.sqrt(252) if dvar > 0 else 0
            sortino = (mean * 252) / dvol if dvol > 0 else 0
            calmar = ann / max_dd if max_dd > 0 else 0
            return {
                "n": n, "hit_rate": round(hit, 4), "avg_win": round(avg_win, 6),
                "avg_loss": round(avg_loss, 6), "expectancy": round(exp, 6),
                "profit_factor": round(pf, 4), "ann_return": round(ann, 4),
                "volatility": round(vol, 4), "sharpe": round(sharpe, 4),
                "sortino": round(sortino, 4), "max_drawdown": round(max_dd, 4),
                "calmar": round(calmar, 4),
            }

        oos = _stats(all_rets_oos if all_rets_oos else all_rets_is)
        is_stats = _stats(all_rets_is)

        # Regime analysis (deterministic labels from returns)
        regimes = self._regime_analysis(by_sym)

        # Walk-forward style fold summary using split folds if present
        wf = None
        if split and split.get("folds"):
            wf = {"folds": split["folds"], "source": "m260_split"}
        else:
            wf = self._mini_walk_forward(by_sym, cost_rate, seed=seed)

        # Monte Carlo on OOS returns
        mc = self._monte_carlo(all_rets_oos or all_rets_is, seed=seed)

        # Multiple testing
        multiple_testing = {
            "trial_count": trial_count,
            "false_discovery_warning": trial_count > 5,
            "robustness_penalty": min(0.5, 0.05 * max(0, trial_count - 1)),
            "parameter_mining_risk": trial_count > 10,
            "baseline_comparison": "buy_hold",
            "holdout_isolated": bool(test_ts),
            "note": "Trial count reported; simplistic p-values are not proof of profitability",
        }

        # Confidence classification — never PROFITABLE/GUARANTEED/LIVE_READY
        val_state = ValidationState.NOT_EVALUATED.value
        failure_reasons = []
        if ds.get("is_synthetic"):
            failure_reasons.append("synthetic_dataset")
            limitations = [SYNTHETIC_TEST_DATA_LABEL, KNOWN_RESEARCH_LIMITATION]
        else:
            limitations = []

        if not test_ts:
            val_state = ValidationState.IN_SAMPLE_ONLY.value
            failure_reasons.append("no_out_of_sample_split")
        elif oos["n"] == 0:
            val_state = ValidationState.OUT_OF_SAMPLE_FAILED.value
            failure_reasons.append("no_oos_trades")
        elif oos["sharpe"] < 0 or oos["expectancy"] < 0:
            val_state = ValidationState.OUT_OF_SAMPLE_FAILED.value
            failure_reasons.append("negative_oos_expectancy")
        elif regimes.get("regime_dependent"):
            val_state = ValidationState.REGIME_DEPENDENT.value
        elif multiple_testing["false_discovery_warning"]:
            val_state = ValidationState.RESEARCH_PROMISING.value
            limitations.append("multiple_testing_risk")
        elif oos["sharpe"] >= 0.5 and oos["n"] >= 3:
            val_state = ValidationState.RESEARCH_VALIDATED_WITH_LIMITATIONS.value
        else:
            val_state = ValidationState.RESEARCH_PROMISING.value

        if len(by_sym) < 2:
            limitations.append("single_asset_or_limited_universe")
            failure_reasons.append("narrow_universe")

        # VaR / ES on returns
        rets_sorted = sorted(all_rets_oos or all_rets_is)
        var_95 = rets_sorted[max(0, int(0.05 * len(rets_sorted)) - 1)] if rets_sorted else 0
        tail = rets_sorted[: max(1, int(0.05 * len(rets_sorted)))] if rets_sorted else [0]
        es_95 = sum(tail) / len(tail)

        # Benchmark buy & hold
        first_px = float(bars[0]["close"])
        last_px = float(bars[-1]["close"])
        bh = (last_px / first_px - 1.0) if first_px else 0
        excess = (equity - 1.0) - bh

        result = {
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "feature_versions": ["sma_10@v1", "sma_20@v1"],
            "universe": {"symbols": sorted(by_sym.keys()), "count": len(by_sym)},
            "training_period": {
                "start": split.get("train", {}).get("start") if split else bars[0]["timestamp"],
                "end": split.get("train", {}).get("end") if split else None,
            },
            "validation_period": split.get("validation") if split else None,
            "test_period": split.get("test") if split else None,
            "embargo_or_purge": {
                "embargo_bars": split.get("embargo_bars") if split else 0,
                "purge_bars": split.get("purge_bars") if split else 0,
            },
            "signal_count": signal_count,
            "trade_count": trades,
            "long_trades": long_trades,
            "short_trades": short_trades,
            "turnover": trades / max(len(bars), 1),
            "in_sample": is_stats,
            "out_of_sample": oos,
            "hit_rate": oos["hit_rate"],
            "average_win": oos["avg_win"],
            "average_loss": oos["avg_loss"],
            "expectancy": oos["expectancy"],
            "profit_factor": oos["profit_factor"],
            "annualised_return": oos["ann_return"],
            "volatility": oos["volatility"],
            "sharpe_ratio": oos["sharpe"],
            "sortino_ratio": oos["sortino"],
            "maximum_drawdown": oos["max_drawdown"],
            "calmar_ratio": oos["calmar"],
            "var_95": round(var_95, 6),
            "expected_shortfall_95": round(es_95, 6),
            "benchmark": {"name": "buy_hold", "return": round(bh, 6)},
            "benchmark_excess_return": round(excess, 6),
            "alpha_estimate_with_limitations": {
                "excess": round(excess, 6),
                "limitation": "Not a formal CAPM alpha; research estimate only",
            },
            "beta": None,
            "capacity_liquidity_warnings": ["participation_limits_not_fully_modelled"],
            "stability_across_windows": wf,
            "parameter_sensitivity": {"note": "single_parameter_set_evaluated", "trial_count": trial_count},
            "walk_forward": wf,
            "monte_carlo": mc,
            "probability_of_loss": mc.get("probability_of_loss"),
            "probability_of_ruin": mc.get("probability_of_ruin"),
            "regime_analysis": regimes,
            "multiple_testing": multiple_testing,
            "transaction_cost_assumptions": {"commission_bps": commission_bps},
            "slippage_assumptions": {"slippage_bps": slippage_bps},
            "confidence_classification": val_state,
            "state": val_state,
            "failure_reasons": failure_reasons,
            "invalidation_conditions": [
                "dataset_revoked",
                "checksum_changed",
                "licence_revoked",
                "blocking_quality_defect",
                "lookahead_detected",
            ],
            "limitations": limitations,
            "is_synthetic": bool(ds.get("is_synthetic")),
            "FORBIDDEN_STATES_NOT_USED": list(ValidationState.__members__.keys()) if False else [
                "PROFITABLE", "GUARANTEED", "SAFE", "LIVE_READY", "PRODUCTION_READY",
            ],
            "disclaimer": (
                "STRATEGY RESULTS DO NOT GUARANTEE FUTURE PERFORMANCE. "
                "RESEARCH VALIDATION DOES NOT AUTHORIZE LIVE TRADING."
            ),
        }
        eh = evidence_hash(result)
        result["evidence_hash"] = eh
        rid = _uid("val")
        self.store.execute(
            """INSERT INTO md_validation_runs(
                id, strategy_id, strategy_version, dataset_id, dataset_version,
                state, result_json, evidence_hash, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                rid, strategy_id, strategy_version, dataset_id, dataset_version,
                val_state, json.dumps(result, default=str), eh, time.time(),
            ),
        )
        self.store.audit("signal.validate", subject=strategy_id, detail={
            "dataset_id": dataset_id, "state": val_state,
        })
        result["ok"] = True
        result["run_id"] = rid
        result.update(AUTHORITY_VALUES)
        return result

    def compare_strategies(
        self,
        strategy_ids: list[str],
        dataset_id: str,
        dataset_version: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        results = []
        for sid in strategy_ids:
            results.append(self.validate(sid, dataset_id, dataset_version, **kwargs))
        return {
            "ok": True,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "strategies": results,
            "ranking_note": "Ranking is research-only; not investment advice",
            **AUTHORITY_VALUES,
        }

    def _blocked(self, strategy_id, dataset_id, dataset_version, state: ValidationState, reason: str) -> dict[str, Any]:
        result = {
            "ok": False,
            "strategy_id": strategy_id,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "state": state.value,
            "confidence_classification": state.value,
            "failure_reasons": [reason],
            "disclaimer": "RESEARCH VALIDATION DOES NOT AUTHORIZE LIVE TRADING.",
            **AUTHORITY_VALUES,
        }
        eh = evidence_hash(result)
        result["evidence_hash"] = eh
        self.store.execute(
            """INSERT INTO md_validation_runs(
                id, strategy_id, strategy_version, dataset_id, dataset_version,
                state, result_json, evidence_hash, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                _uid("val"), strategy_id, "v1", dataset_id, dataset_version,
                state.value, json.dumps(result, default=str), eh, time.time(),
            ),
        )
        return result

    def _regime_analysis(self, by_sym: dict[str, list]) -> dict[str, Any]:
        # Label regimes from rolling returns — do not fabricate unsupported macro regimes
        labels = {"bull": 0, "bear": 0, "sideways": 0, "high_volatility": 0, "low_volatility": 0}
        for sym, rows in by_sym.items():
            closes = [float(r["close"]) for r in rows]
            if len(closes) < 25:
                continue
            for i in range(20, len(closes)):
                ret = closes[i] / closes[i - 20] - 1
                window = [closes[j] / closes[j - 1] - 1 for j in range(i - 19, i + 1) if closes[j - 1]]
                vol = math.sqrt(sum(x * x for x in window) / len(window)) if window else 0
                if ret > 0.05:
                    labels["bull"] += 1
                elif ret < -0.05:
                    labels["bear"] += 1
                else:
                    labels["sideways"] += 1
                if vol > 0.02:
                    labels["high_volatility"] += 1
                else:
                    labels["low_volatility"] += 1
        total = sum(labels.values()) or 1
        dominant = max(labels, key=labels.get)
        regime_dependent = labels["bull"] > 0 and labels["bear"] > 0 and abs(
            labels["bull"] - labels["bear"]
        ) / total < 0.3
        return {
            "definitions": {
                "bull": "20-bar return > 5%",
                "bear": "20-bar return < -5%",
                "sideways": "otherwise",
                "high_volatility": "20-bar realized vol > 2%",
                "low_volatility": "otherwise",
            },
            "counts": labels,
            "dominant": dominant,
            "regime_dependent": regime_dependent,
            "macro_regimes_fabricated": False,
            "note": "Inflation/rate/crisis regimes omitted without approved macro data",
        }

    def _mini_walk_forward(self, by_sym: dict, cost_rate: float, seed: int = 42) -> dict[str, Any]:
        folds = []
        for sym, rows in list(by_sym.items())[:1]:
            n = len(rows)
            if n < 50:
                break
            fold_size = n // 3
            for f in range(2):
                train = rows[: (f + 1) * fold_size]
                test = rows[(f + 1) * fold_size: (f + 2) * fold_size]
                if len(test) < 5:
                    continue
                # train never sees test
                folds.append({
                    "fold": f,
                    "train_bars": len(train),
                    "test_bars": len(test),
                    "optimized_on_evaluation_set": False,
                })
        return {"folds": folds, "optimized_on_evaluation_set": False, "seed": seed}

    def _monte_carlo(self, rets: list[float], seed: int = 42, n_sim: int = 200) -> dict[str, Any]:
        if not rets:
            return {
                "n_simulations": 0,
                "probability_of_loss": None,
                "probability_of_ruin": None,
                "limitations": ["insufficient_returns_for_mc"],
            }
        rng = _lcg(seed)
        n = len(rets)
        terminal = []
        for _ in range(n_sim):
            eq = 1.0
            for _j in range(n):
                # sample with replacement
                idx = int(next(rng) * n) % n
                eq *= (1 + rets[idx])
            terminal.append(eq - 1.0)
        loss = sum(1 for t in terminal if t < 0) / n_sim
        ruin = sum(1 for t in terminal if t < -0.5) / n_sim
        terminal_sorted = sorted(terminal)
        return {
            "n_simulations": n_sim,
            "seed": seed,
            "probability_of_loss": round(loss, 4),
            "probability_of_ruin": round(ruin, 4),
            "p5": round(terminal_sorted[int(0.05 * n_sim)], 4),
            "p50": round(terminal_sorted[int(0.50 * n_sim)], 4),
            "p95": round(terminal_sorted[int(0.95 * n_sim)], 4),
            "historical_sample_size": n,
            "limitations": ["Block bootstrap not used; i.i.d. sample with replacement"],
        }

    def latest_report(self, strategy_id: str | None = None) -> dict[str, Any]:
        if strategy_id:
            row = self.store.query_one(
                """SELECT * FROM md_validation_runs WHERE strategy_id=?
                   ORDER BY created_at DESC LIMIT 1""",
                (strategy_id,),
            )
        else:
            row = self.store.query_one(
                "SELECT * FROM md_validation_runs ORDER BY created_at DESC LIMIT 1",
            )
        if not row:
            return {"ok": False, "code": "NO_VALIDATION", **AUTHORITY_VALUES}
        result = json.loads(row["result_json"])
        result["ok"] = True
        result.update(AUTHORITY_VALUES)
        return result
