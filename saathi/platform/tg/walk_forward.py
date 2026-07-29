"""M178 — Deterministic walk-forward and rolling OOS evaluation for TG.

Composes M62.4 walk_forward primitives. Parameter selection occurs only on
train/validation; final test remains untouched (selected_before_test=True).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from statistics import median
from typing import Any, Callable

from saathi.platform.tg.data_contract import (
    DataClassification,
    build_provenance,
    incomplete_result,
    is_authoritative,
)
from saathi.platform.tg.domain import coerce_decimal


@dataclass
class WalkForwardConfig:
    mode: str = "expanding"  # expanding | rolling | anchored
    n_folds: int = 3
    train_min: int = 15
    test_size: int = 8
    embargo_bars: int = 1
    selection_criterion: str = "max_validation_return_min_drawdown"
    candidate_parameter_sets: list[dict[str, Any]] = field(default_factory=list)
    cost_tier: str = "realistic"
    seed: int = 0


def _metric_val(metrics: dict, key: str, default: str = "0") -> Decimal:
    m = metrics.get(key)
    if m is None:
        return coerce_decimal(default)
    if hasattr(m, "value"):
        return coerce_decimal(m.value if m.value is not None else default)
    if isinstance(m, dict):
        return coerce_decimal(m.get("value", default))
    return coerce_decimal(m)


def _score_validation(metrics: dict) -> Decimal:
    """Higher is better; drawdown penalized. Deterministic."""
    ret = _metric_val(metrics, "total_return")
    dd = abs(_metric_val(metrics, "max_drawdown"))
    return ret - dd * Decimal("0.5")


def run_walk_forward(
    *,
    strategy_slug: str,
    bars: list[Any],
    dataset_id: str,
    classification: DataClassification,
    strategy_builder: Callable[[dict[str, Any]], Any],
    run_backtest_fn: Callable[..., Any],
    config: WalkForwardConfig | None = None,
    strategy_version: str = "1.0.0",
    policy_version: str = "1.0.0",
) -> dict[str, Any]:
    """Execute walk-forward. Never optimizes on final test period."""
    from saathi.platform.strategy.walk_forward import build_folds, Fold, aggregate_folds

    cfg = config or WalkForwardConfig()
    if not bars or len(bars) < cfg.train_min + cfg.test_size:
        return incomplete_result(
            reason="insufficient_bars_for_walk_forward",
            dataset_id=dataset_id,
            strategy_version=strategy_version,
        )

    def _epoch(b):
        st = getattr(b, "start_time", None)
        if st is not None and hasattr(st, "timestamp"):
            return st.timestamp()
        return float(getattr(b, "ts", 0) or 0)

    epochs = sorted(_epoch(b) for b in bars)
    mode = "expanding" if cfg.mode in ("expanding", "anchored") else "rolling"
    try:
        ranges = build_folds(
            epochs,
            n_folds=cfg.n_folds,
            mode=mode,
            train_min=cfg.train_min,
            test_size=cfg.test_size,
        )
    except ValueError as e:
        return incomplete_result(
            reason="walk_forward_fold_build_failed",
            dataset_id=dataset_id,
            error=str(e),
            strategy_version=strategy_version,
        )

    candidates = cfg.candidate_parameter_sets or [{}]
    folds: list[Fold] = []
    rejected_params: list[dict[str, Any]] = []

    def bars_in(range_t: tuple[float, float], embargo: int = 0) -> list[Any]:
        lo, hi = range_t
        # embargo: skip first embargo bars after lo for leakage control
        selected = [b for b in bars if lo <= _epoch(b) < hi]
        if embargo > 0 and len(selected) > embargo:
            return selected[embargo:]
        return selected

    for idx, (train_r, val_r, test_r) in enumerate(ranges):
        # Apply embargo between validation and test
        train_bars = bars_in(train_r)
        val_bars = bars_in(val_r)
        test_bars = bars_in(test_r, embargo=cfg.embargo_bars)

        best_params: dict[str, Any] = {}
        best_score = Decimal("-999999")
        fold_rejected = []

        # Parameter selection ONLY on train+validation — never look at test
        for params in candidates:
            try:
                defn = strategy_builder(params)
                # validation window only for selection score
                if not val_bars:
                    continue
                vres = run_backtest_fn(defn, val_bars, seed=cfg.seed)
                if getattr(vres, "status", "") not in ("COMPLETE", "complete", ""):
                    if getattr(vres, "status", None) and vres.status not in ("COMPLETE",):
                        fold_rejected.append({"params": params, "reason": vres.status})
                        continue
                score = _score_validation(vres.metrics or {})
                if score > best_score:
                    best_score = score
                    best_params = dict(params)
            except Exception as exc:
                fold_rejected.append({"params": params, "reason": str(exc)[:120]})

        rejected_params.extend(fold_rejected)

        # NOW evaluate on untouched test with selected params only
        fold = Fold(
            index=idx,
            train_range=train_r,
            validation_range=val_r,
            test_range=test_r,
            parameters=best_params,
            dataset_hash="",
            strategy_version=0,
            selected_before_test=True,
        )
        try:
            defn = strategy_builder(best_params)
            if not test_bars:
                fold.status = "EMPTY"
            else:
                tres = run_backtest_fn(defn, test_bars, seed=cfg.seed)
                fold.status = "OK" if tres.status == "COMPLETE" else "FAILED"
                if tres.status != "COMPLETE" and tres.status:
                    fold.status = "FAILED" if tres.status != "COMPLETE" else "OK"
                # Accept COMPLETE only
                if getattr(tres, "status", "COMPLETE") == "COMPLETE" or (
                    getattr(tres, "look_ahead_ok", True) and tres.metrics
                ):
                    if getattr(tres, "status", "") in ("COMPLETE", ""):
                        fold.status = "OK"
                fold.metrics = {
                    "total_return": str(_metric_val(tres.metrics or {}, "total_return")),
                    "max_drawdown": str(_metric_val(tres.metrics or {}, "max_drawdown")),
                    "trade_count": str(len(getattr(tres, "fills", []) or [])),
                    "fees": str(_metric_val(tres.metrics or {}, "total_fees")),
                    "slippage": str(_metric_val(tres.metrics or {}, "total_slippage")),
                }
                fold.trade_count = len(getattr(tres, "fills", []) or [])
                fold.dataset_hash = getattr(tres, "result_hash", "")[:16]
        except Exception as exc:
            fold.status = "FAILED"
            fold.metrics = {"error": str(exc)[:160]}

        folds.append(fold)

    agg = aggregate_folds(folds)
    ok_folds = [f for f in folds if f.status == "OK"]
    returns = [coerce_decimal(f.metrics.get("total_return", 0)) for f in ok_folds]
    drawdowns = [abs(coerce_decimal(f.metrics.get("max_drawdown", 0))) for f in ok_folds]
    profitable = sum(1 for r in returns if r > 0)

    # Parameter stability: fraction of folds sharing the mode parameters
    param_keys = [json_dumps(f.parameters) for f in folds if f.status == "OK"]
    stability = Decimal("0")
    if param_keys:
        mode_p = max(set(param_keys), key=param_keys.count)
        stability = Decimal(param_keys.count(mode_p)) / Decimal(len(param_keys))

    oos_expectancy = (sum(returns) / Decimal(len(returns))) if returns else Decimal("0")
    median_ret = Decimal(str(median([float(r) for r in returns]))) if returns else Decimal("0")
    median_dd = Decimal(str(median([float(d) for d in drawdowns]))) if drawdowns else Decimal("0")
    worst_dd = max(drawdowns) if drawdowns else Decimal("0")
    variability = Decimal("0")
    if len(returns) >= 2:
        mean_r = sum(returns) / Decimal(len(returns))
        variance = sum((r - mean_r) ** 2 for r in returns) / Decimal(len(returns) - 1)
        variability = variance  # variance as stability inverse signal

    # Profit factor proxy from positive/negative fold returns
    wins = sum(r for r in returns if r > 0)
    losses = abs(sum(r for r in returns if r < 0))
    pf = (wins / losses) if losses > 0 else (Decimal("999") if wins > 0 else None)

    prov = build_provenance(
        dataset_id=dataset_id,
        bars=bars,
        classification=classification,
        strategy_version=strategy_version,
        notes=["walk_forward", f"mode={cfg.mode}", f"embargo={cfg.embargo_bars}"],
    )

    consistent = (
        len(ok_folds) >= max(1, cfg.n_folds // 2)
        and stability >= Decimal("0.5")
        and worst_dd <= Decimal("0.35")
    )

    return {
        "status": "COMPLETE",
        "mode": cfg.mode,
        "n_folds": len(folds),
        "profitable_fold_pct": str(
            (Decimal(profitable) / Decimal(len(ok_folds)) * 100) if ok_folds else Decimal("0")
        ),
        "median_fold_return": str(median_ret),
        "median_fold_drawdown": str(median_dd),
        "worst_fold_drawdown": str(worst_dd),
        "fold_to_fold_variability": str(variability),
        "parameter_stability": str(stability),
        "out_of_sample_expectancy": str(oos_expectancy),
        "out_of_sample_profit_factor": str(pf) if pf is not None else None,
        "selection_criterion": cfg.selection_criterion,
        "n_candidate_parameter_sets": len(candidates),
        "rejected_parameter_sets": rejected_params[:50],
        "folds": [f.to_public() for f in folds],
        "aggregate": agg,
        "walk_forward_consistent": consistent,
        "final_test_untouched": all(f.selected_before_test for f in folds),
        "embargo_bars": cfg.embargo_bars,
        "cost_tier": cfg.cost_tier,
        "provenance": prov.to_public(),
        "data_classification": classification.value,
        "authoritative": is_authoritative(classification),
        "paper_only": True,
        "live_authorized": False,
        "disclaimer": "Walk-forward OOS is research only. Not future performance.",
    }


def json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, sort_keys=True, default=str)
