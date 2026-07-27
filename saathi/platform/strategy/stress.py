"""M62.4 — stress testing + parameter sensitivity.

Stress: run a strategy against the deterministic M62.2 fixture regimes (trending,
mean-reverting, flat, high-vol, gap-down, illiquid, flash-crash, and the defect
datasets). Invalid datasets must block; defect regimes must surface, never silently
pass.

Sensitivity: vary one strategy parameter across bounded neighbours and record the
performance surface, trade count, drawdown, and cost impact. Cliff-edge behaviour
(a metric that swings sharply between adjacent parameter points) is flagged so a
strategy that "works" only at a single lucky value is not mistaken for robust.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from saathi.platform.market_data.fixtures import build_bars as md_build_bars, DATASETS
from saathi.platform.strategy.models import StrategyDefinition, CostModel, REALISTIC_COST, ZERO_COST, STRESSED_COST, D
from saathi.platform.strategy.engine import run_backtest


# regimes we actively assert behaviour on (subset of M62.2 DATASETS)
STRESS_REGIMES = (
    "TRENDING", "MEAN_REVERTING", "FLAT", "HIGH_VOLATILITY", "GAP_DOWN", "ILLIQUID",
    "FLASH_CRASH_LIKE", "MISSING_BARS", "OUT_OF_ORDER_BARS", "INVALID_OHLC",
)


def run_stress(defn: StrategyDefinition, *, starting_cash: Decimal = Decimal("100000"),
               cost: CostModel | None = None, n: int = 30) -> dict[str, Any]:
    from saathi.platform.market_data.models import Timeframe
    results: dict[str, Any] = {}
    for regime in STRESS_REGIMES:
        bars = md_build_bars(regime, defn.timeframe if isinstance(defn.timeframe, Timeframe) else Timeframe.D1, n)
        # point the strategy universe at this regime's synthetic instrument
        d = _retarget(defn, regime)
        res = run_backtest(d, bars, starting_cash=starting_cash, cost=cost or defn.cost_model)
        tr = res.metrics.get("total_return")
        dd = res.metrics.get("max_drawdown")
        results[regime] = {
            "status": res.status, "reason": res.reason, "blocking": res.quality_summary.get("blocking", 0),
            "total_return": (tr.value if tr else None), "max_drawdown": (dd.value if dd else None),
            "trade_count": len(res.fills), "look_ahead_ok": res.look_ahead_ok,
        }
    results["_summary"] = {
        "blocked_invalid": [r for r in STRESS_REGIMES if results[r]["status"] == "REJECTED"],
        "completed": [r for r in STRESS_REGIMES if results[r]["status"] == "COMPLETE"],
    }
    return results


def cost_resilience(defn: StrategyDefinition, bars, *, starting_cash: Decimal = Decimal("100000")) -> dict[str, Any]:
    """Run zero / realistic / stressed cost cases. A strategy profitable ONLY at zero
    cost is flagged cost_sensitive."""
    out = {}
    for label, cost in (("zero", ZERO_COST), ("realistic", REALISTIC_COST), ("stressed", STRESSED_COST)):
        res = run_backtest(defn, bars, starting_cash=starting_cash, cost=cost)
        tr = res.metrics.get("total_return")
        out[label] = {"status": res.status, "total_return": (tr.value if tr else None)}
    zero_tr = D(out["zero"]["total_return"] or "0")
    real_tr = D(out["realistic"]["total_return"] or "0")
    stress_tr = D(out["stressed"]["total_return"] or "0")
    # zero_only: costs of the realistic tier alone erase the edge (strictest)
    out["zero_only"] = bool(zero_tr > 0 and real_tr <= 0)
    # cost_sensitive: profitable at zero but not under the stressed-cost tier (fragile)
    out["cost_sensitive"] = bool(zero_tr > 0 and stress_tr <= 0)
    return out


def _retarget(defn: StrategyDefinition, symbol: str) -> StrategyDefinition:
    import copy
    d = copy.deepcopy(defn)
    d.instrument_universe = [symbol]
    return d


def run_sensitivity(
    base: StrategyDefinition,
    bars,
    *,
    parameter: str,
    values: list[Any],
    rebuild: Callable[[StrategyDefinition, Any], StrategyDefinition],
    starting_cash: Decimal = Decimal("100000"),
    cost: CostModel | None = None,
    cliff_threshold: Decimal = Decimal("0.5"),
) -> dict[str, Any]:
    """For each value, rebuild the strategy and record its surface point. Detect a
    cliff when |Δtotal_return| between adjacent points exceeds ``cliff_threshold``
    (absolute return units)."""
    surface = []
    for v in values:
        d = rebuild(base, v)
        res = run_backtest(d, bars, starting_cash=starting_cash, cost=cost or base.cost_model)
        tr = res.metrics.get("total_return")
        dd = res.metrics.get("max_drawdown")
        surface.append({
            "value": v, "status": res.status,
            "total_return": (tr.value if tr and tr.value is not None else None),
            "max_drawdown": (dd.value if dd and dd.value is not None else None),
            "trade_count": len(res.fills), "fees": str(res.metrics["fee_impact"].value) if "fee_impact" in res.metrics else "0",
        })
    cliffs = []
    for a, b in zip(surface, surface[1:]):
        ra, rb = a["total_return"], b["total_return"]
        if ra is not None and rb is not None:
            if abs(D(rb) - D(ra)) > cliff_threshold:
                cliffs.append({"from": a["value"], "to": b["value"], "delta": str(D(rb) - D(ra))})
    return {"parameter": parameter, "surface": surface, "cliffs": cliffs,
            "unstable": bool(cliffs)}
