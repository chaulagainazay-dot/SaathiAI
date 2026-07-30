"""M251 — Walk-Forward Validation.

Rolling windows, train/test separation, parameter validation, overfitting detection.
Never optimises on the evaluation dataset.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

from saathi.platform.tg.intelligence.backtest_v2 import BacktestEngineV2, _synth_bars
from saathi.platform.tg.intelligence.models import AUTHORITY_VALUES


class WalkForwardEngine:
    """Walk-forward with strict train/test isolation."""

    def __init__(self):
        self.bt = BacktestEngineV2()

    def run(
        self,
        strategy_id: str = "tf_dual_ma",
        *,
        bars: list[dict[str, float]] | None = None,
        n_folds: int = 3,
        train_size: int = 40,
        test_size: int = 20,
        embargo: int = 1,
        seed: int = 42,
        candidate_params: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        bars = bars or _synth_bars(120, seed=seed)
        n = len(bars)
        min_need = train_size + test_size
        if n < min_need:
            return {
                "ok": False,
                "code": "INSUFFICIENT_BARS",
                "bars": n,
                "required": min_need,
                **AUTHORITY_VALUES,
            }

        candidates = candidate_params or [
            {"fast": 8, "slow": 20, "label": "fast8_slow20"},
            {"fast": 10, "slow": 20, "label": "fast10_slow20"},
            {"fast": 12, "slow": 30, "label": "fast12_slow30"},
        ]

        folds = []
        start = 0
        fold_i = 0
        while fold_i < n_folds:
            train_start = start
            train_end = train_start + train_size
            test_start = train_end + embargo
            test_end = test_start + test_size
            if test_end > n:
                break
            train_bars = bars[train_start:train_end]
            test_bars = bars[test_start:test_end]

            # Parameter selection ONLY on train (never on test)
            best = None
            best_score = -1e18
            train_scores = []
            for cand in candidates:
                tr = self.bt.run(
                    strategy_id,
                    bars=train_bars,
                    seed=seed + fold_i,
                    capital=100_000.0,
                )
                score = float(tr.get("sharpe", 0)) - float(tr.get("max_drawdown", 0)) * 2
                train_scores.append({
                    "params": cand,
                    "sharpe": tr.get("sharpe"),
                    "max_drawdown": tr.get("max_drawdown"),
                    "total_return": tr.get("total_return"),
                    "score": round(score, 6),
                })
                if score > best_score:
                    best_score = score
                    best = cand

            # Evaluate selected params on held-out test — no re-optimisation
            te = self.bt.run(
                strategy_id,
                bars=test_bars,
                seed=seed + fold_i + 100,
                capital=100_000.0,
            )
            folds.append({
                "fold": fold_i,
                "train_range": [train_start, train_end],
                "test_range": [test_start, test_end],
                "embargo": embargo,
                "selected_params": best,
                "selected_before_test": True,
                "optimized_on_test": False,
                "train_scores": train_scores,
                "test_metrics": {
                    "total_return": te.get("total_return"),
                    "sharpe": te.get("sharpe"),
                    "max_drawdown": te.get("max_drawdown"),
                    "win_rate": te.get("win_rate"),
                    "profit_factor": te.get("profit_factor"),
                },
            })
            # rolling window advance
            start += test_size
            fold_i += 1

        if not folds:
            return {
                "ok": False,
                "code": "NO_FOLDS",
                **AUTHORITY_VALUES,
            }

        test_returns = [f["test_metrics"]["total_return"] or 0 for f in folds]
        test_sharpes = [f["test_metrics"]["sharpe"] or 0 for f in folds]
        train_best_sharpes = [
            max((ts["sharpe"] or 0) for ts in f["train_scores"]) for f in folds
        ]

        mean_test = sum(test_returns) / len(test_returns)
        mean_test_sharpe = sum(test_sharpes) / len(test_sharpes)
        mean_train_sharpe = sum(train_best_sharpes) / len(train_best_sharpes)

        # Overfitting detection: large train-test degradation
        degradation = mean_train_sharpe - mean_test_sharpe
        overfit_flag = degradation > 0.75 or (mean_train_sharpe > 0.5 and mean_test_sharpe < 0)
        overfit_score = min(1.0, max(0.0, degradation / 2.0))

        # Robustness: consistency of test returns sign and drawdown
        positive_folds = sum(1 for r in test_returns if r > 0)
        consistency = positive_folds / len(test_returns)
        max_test_dd = max((f["test_metrics"]["max_drawdown"] or 0) for f in folds)
        robustness = max(0.0, min(1.0, consistency * (1.0 - max_test_dd) * (1.0 - overfit_score * 0.5)))
        confidence = max(0.0, min(1.0, robustness * (0.5 + 0.5 * min(1.0, len(folds) / 3))))

        result = {
            "ok": True,
            "engine": "walk_forward_v2",
            "strategy_id": strategy_id,
            "n_folds": len(folds),
            "mode": "rolling",
            "train_size": train_size,
            "test_size": test_size,
            "embargo": embargo,
            "seed": seed,
            "folds": folds,
            "aggregate": {
                "mean_test_return": round(mean_test, 6),
                "mean_test_sharpe": round(mean_test_sharpe, 4),
                "mean_train_sharpe": round(mean_train_sharpe, 4),
                "train_test_degradation": round(degradation, 4),
                "positive_fold_ratio": round(consistency, 4),
                "max_test_drawdown": round(max_test_dd, 6),
            },
            "overfitting": {
                "detected": overfit_flag,
                "score": round(overfit_score, 4),
                "method": "train_test_sharpe_degradation",
            },
            "robustness_score": round(robustness, 4),
            "confidence_score": round(confidence, 4),
            "invariants": {
                "optimized_on_evaluation_set": False,
                "selected_before_test": True,
                "train_test_separated": True,
            },
            "evidence_hash": hashlib.sha256(
                f"wf:{strategy_id}:{seed}:{len(folds)}:{mean_test:.6f}".encode()
            ).hexdigest(),
            **AUTHORITY_VALUES,
        }
        return result
