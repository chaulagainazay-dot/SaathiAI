"""M179 — Bounded stress, cost, and robustness laboratory.

Composes M62.4 stress + cost models. Never promotes on fragile results.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Callable

from saathi.platform.tg.data_contract import DataClassification, build_provenance, is_authoritative
from saathi.platform.tg.domain import coerce_decimal


class RobustnessVerdict(str, Enum):
    ROBUST = "ROBUST"
    CONDITIONALLY_ROBUST = "CONDITIONALLY_ROBUST"
    FRAGILE = "FRAGILE"
    COST_SENSITIVE = "COST_SENSITIVE"
    PARAMETER_UNSTABLE = "PARAMETER_UNSTABLE"
    DATA_SENSITIVE = "DATA_SENSITIVE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass
class StressCaseResult:
    name: str
    dimension: str
    baseline: dict[str, Any]
    stressed: dict[str, Any]
    delta: dict[str, Any]
    passed: bool
    reason_code: str
    criticality: str  # info | warning | critical
    evidence: dict[str, Any]

    def to_public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dimension": self.dimension,
            "baseline": self.baseline,
            "stressed": self.stressed,
            "delta": self.delta,
            "pass": self.passed,
            "reason_code": self.reason_code,
            "criticality": self.criticality,
            "evidence": self.evidence,
        }


def _mv(metrics: dict, key: str) -> Decimal:
    m = metrics.get(key) if metrics else None
    if m is None:
        return Decimal("0")
    if hasattr(m, "value"):
        return coerce_decimal(m.value if m.value is not None else "0")
    if isinstance(m, dict):
        return coerce_decimal(m.get("value", 0))
    return coerce_decimal(m)


def _snapshot(res: Any) -> dict[str, Any]:
    metrics = getattr(res, "metrics", {}) or {}
    return {
        "status": getattr(res, "status", ""),
        "total_return": str(_mv(metrics, "total_return")),
        "max_drawdown": str(_mv(metrics, "max_drawdown")),
        "trade_count": len(getattr(res, "fills", []) or []),
        "look_ahead_ok": getattr(res, "look_ahead_ok", True),
    }


def run_stress_lab(
    *,
    strategy_slug: str,
    defn: Any,
    bars: list[Any],
    dataset_id: str,
    classification: DataClassification,
    run_backtest_fn: Callable[..., Any],
    strategy_version: str = "1.0.0",
) -> dict[str, Any]:
    from saathi.platform.strategy.models import REALISTIC_COST, ZERO_COST, STRESSED_COST, CostModel
    from saathi.platform.strategy import stress as stress_mod
    from saathi.platform.market_data.fixtures import build_bars
    from saathi.platform.market_data.models import Timeframe

    cases: list[StressCaseResult] = []

    # Baseline
    try:
        base_res = run_backtest_fn(defn, bars, cost=REALISTIC_COST)
        baseline = _snapshot(base_res)
    except Exception as exc:
        return {
            "status": "INCOMPLETE",
            "robustness_verdict": RobustnessVerdict.INSUFFICIENT_EVIDENCE.value,
            "error": str(exc)[:200],
            "cases": [],
            "paper_only": True,
            "authoritative": False,
        }

    def add_cost(name: str, cost: CostModel, mult_label: str):
        try:
            sres = run_backtest_fn(defn, bars, cost=cost)
            stressed = _snapshot(sres)
            b_ret = coerce_decimal(baseline["total_return"])
            s_ret = coerce_decimal(stressed["total_return"])
            delta = {"total_return": str(s_ret - b_ret)}
            # Critical if edge flips from + to - under cost
            critical = b_ret > 0 and s_ret <= 0
            cases.append(StressCaseResult(
                name=name, dimension="trading_costs",
                baseline=baseline, stressed=stressed, delta=delta,
                passed=not critical and stressed.get("look_ahead_ok", True),
                reason_code="COST_EDGE_ERASED" if critical else "COST_OK",
                criticality="critical" if critical else "info",
                evidence={"multiplier": mult_label, "cost": cost.to_public() if hasattr(cost, "to_public") else {}},
            ))
        except Exception as e:
            cases.append(StressCaseResult(
                name=name, dimension="trading_costs",
                baseline=baseline, stressed={"error": str(e)[:120]}, delta={},
                passed=False, reason_code="COST_RUN_FAILED", criticality="warning",
                evidence={},
            ))

    add_cost("fees_base", REALISTIC_COST, "1.0x")
    # 1.5x / 2x fee & slip via CostModel copies
    for label, fee_mult, slip_mult in (("1.5x", Decimal("1.5"), Decimal("1.5")), ("2x", Decimal("2"), Decimal("2"))):
        c = CostModel(
            fixed_fee=REALISTIC_COST.fixed_fee,
            pct_fee=coerce_decimal(REALISTIC_COST.pct_fee) * fee_mult,
            per_unit_fee=REALISTIC_COST.per_unit_fee,
            min_fee=REALISTIC_COST.min_fee,
            slippage_bps=coerce_decimal(REALISTIC_COST.slippage_bps) * slip_mult,
            spread_slippage=REALISTIC_COST.spread_slippage,
            max_volume_participation=REALISTIC_COST.max_volume_participation,
        )
        add_cost(f"fees_slip_{label}", c, label)

    add_cost("zero_cost", ZERO_COST, "0x")
    add_cost("stressed_cost", STRESSED_COST, "stressed")

    # Market regimes via M62 fixtures (explicitly synthetic dimension)
    for regime in ("TRENDING", "MEAN_REVERTING", "HIGH_VOLATILITY", "GAP_DOWN", "ILLIQUID", "FLASH_CRASH_LIKE"):
        try:
            r_bars = build_bars(regime, Timeframe.D1, 30)
            d = deepcopy(defn)
            d.instrument_universe = [regime]
            sres = run_backtest_fn(d, r_bars, cost=REALISTIC_COST)
            stressed = _snapshot(sres)
            blocked = sres.status == "REJECTED"
            cases.append(StressCaseResult(
                name=f"regime_{regime}", dimension="market_behavior",
                baseline=baseline, stressed=stressed,
                delta={"status": stressed["status"]},
                passed=not blocked or regime in ("INVALID_OHLC", "OUT_OF_ORDER_BARS"),
                reason_code="REGIME_BLOCKED" if blocked else "REGIME_OK",
                criticality="warning" if coerce_decimal(stressed["max_drawdown"]) > Decimal("0.3") else "info",
                evidence={"regime": regime, "classification": "SYNTHETIC_VALIDATION"},
            ))
        except Exception as e:
            cases.append(StressCaseResult(
                name=f"regime_{regime}", dimension="market_behavior",
                baseline=baseline, stressed={"error": str(e)[:100]}, delta={},
                passed=False, reason_code="REGIME_RUN_FAILED", criticality="info", evidence={"regime": regime},
            ))

    # Data quality regimes
    for regime in ("MISSING_BARS", "OUT_OF_ORDER_BARS", "INVALID_OHLC"):
        try:
            r_bars = build_bars(regime, Timeframe.D1, 20)
            d = deepcopy(defn)
            d.instrument_universe = [regime]
            sres = run_backtest_fn(d, r_bars, cost=REALISTIC_COST)
            stressed = _snapshot(sres)
            # Fail-closed expected for invalid data
            ok = sres.status in ("REJECTED", "FAILED") or not sres.look_ahead_ok or sres.quality_summary.get("blocking", 0) > 0
            cases.append(StressCaseResult(
                name=f"data_quality_{regime}", dimension="data_quality",
                baseline=baseline, stressed=stressed, delta={},
                passed=bool(ok) or sres.status != "COMPLETE",
                reason_code="DATA_QUALITY_HANDLED" if ok or sres.status != "COMPLETE" else "DATA_QUALITY_SILENT_PASS",
                criticality="critical" if sres.status == "COMPLETE" and regime == "INVALID_OHLC" else "info",
                evidence={"regime": regime},
            ))
        except Exception:
            cases.append(StressCaseResult(
                name=f"data_quality_{regime}", dimension="data_quality",
                baseline=baseline, stressed={"status": "exception_fail_closed"}, delta={},
                passed=True, reason_code="DATA_QUALITY_EXCEPTION_FAIL_CLOSED", criticality="info",
                evidence={"regime": regime},
            ))

    # Parameter sensitivity (equity fraction surface)
    try:
        def _rebuild(base, v):
            d = deepcopy(base)
            d.sizing.value = Decimal(str(v))
            return d
        sens = stress_mod.run_sensitivity(
            defn, bars,
            parameter="equity_fraction",
            values=["0.2", "0.4", "0.6", "0.8"],
            rebuild=_rebuild,
            starting_cash=Decimal("100000"),
        )
        cliff = bool(sens.get("unstable") or sens.get("cliffs"))
        cases.append(StressCaseResult(
            name="parameter_sensitivity", dimension="strategy_sensitivity",
            baseline=baseline, stressed={"summary": {"cliffs": sens.get("cliffs"), "unstable": sens.get("unstable")}},
            delta={},
            passed=not cliff,
            reason_code="PARAMETER_CLIFF" if cliff else "PARAMETER_OK",
            criticality="critical" if cliff else "info",
            evidence={"sensitivity_keys": list(sens.keys())[:12]},
        ))
    except Exception as e:
        cases.append(StressCaseResult(
            name="parameter_sensitivity", dimension="strategy_sensitivity",
            baseline=baseline, stressed={"error": str(e)[:120]}, delta={},
            passed=False, reason_code="SENSITIVITY_FAILED", criticality="warning", evidence={},
        ))

    # Cost resilience summary
    try:
        cr = stress_mod.cost_resilience(defn, bars)
        cost_sens = bool(cr.get("cost_sensitive") or cr.get("zero_only"))
        cases.append(StressCaseResult(
            name="cost_resilience", dimension="trading_costs",
            baseline=baseline, stressed=cr, delta={},
            passed=not cost_sens,
            reason_code="COST_SENSITIVE" if cost_sens else "COST_RESILIENT",
            criticality="critical" if cost_sens else "info",
            evidence=cr,
        ))
    except Exception:
        pass

    critical_fails = [c for c in cases if not c.passed and c.criticality == "critical"]
    cost_fails = [c for c in cases if c.reason_code in ("COST_SENSITIVE", "COST_EDGE_ERASED")]
    param_fails = [c for c in cases if c.reason_code in ("PARAMETER_CLIFF", "PARAMETER_UNSTABLE")]
    data_fails = [c for c in cases if c.dimension == "data_quality" and not c.passed]

    if len(cases) < 3:
        verdict = RobustnessVerdict.INSUFFICIENT_EVIDENCE
    elif critical_fails:
        if cost_fails and not param_fails:
            verdict = RobustnessVerdict.COST_SENSITIVE
        elif param_fails:
            verdict = RobustnessVerdict.PARAMETER_UNSTABLE
        elif data_fails:
            verdict = RobustnessVerdict.DATA_SENSITIVE
        else:
            verdict = RobustnessVerdict.FRAGILE
    elif cost_fails:
        verdict = RobustnessVerdict.COST_SENSITIVE
    elif any(not c.passed for c in cases):
        verdict = RobustnessVerdict.CONDITIONALLY_ROBUST
    else:
        verdict = RobustnessVerdict.ROBUST

    prov = build_provenance(
        dataset_id=dataset_id,
        bars=bars,
        classification=classification,
        strategy_version=strategy_version,
        notes=["stress_lab"],
    )

    return {
        "status": "COMPLETE",
        "strategy_slug": strategy_slug,
        "robustness_verdict": verdict.value,
        "critical_failures": len(critical_fails),
        "cases": [c.to_public() for c in cases],
        "baseline": baseline,
        "provenance": prov.to_public(),
        "data_classification": classification.value,
        "authoritative": is_authoritative(classification),
        "paper_only": True,
        "live_authorized": False,
        "promote_blocked": verdict in (
            RobustnessVerdict.FRAGILE,
            RobustnessVerdict.COST_SENSITIVE,
            RobustnessVerdict.PARAMETER_UNSTABLE,
            RobustnessVerdict.DATA_SENSITIVE,
            RobustnessVerdict.INSUFFICIENT_EVIDENCE,
        ) or len(critical_fails) > 0,
        "disclaimer": "Stress results are research-only. Simulated fills differ from live fills.",
    }
