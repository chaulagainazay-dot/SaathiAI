"""Exposure limits, drawdown manager, risk budgeting."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.portfolio_risk.models import AUTHORITY_VALUES, DEFAULT_MAX_LEVERAGE, LimitState


DEFAULT_LIMITS = {
    "max_leverage": DEFAULT_MAX_LEVERAGE,
    "max_position_weight": 0.35,
    "max_sector_weight": 0.50,
    "max_drawdown": 0.20,
    "max_var_95": 0.05,
    "max_expected_shortfall_95": 0.08,
    "max_gross_exposure": 1.0,
    "min_cash_pct": 0.0,
    "max_correlation_avg": 0.85,
}


class LimitsEngine:
    def __init__(self, limits: dict[str, float] | None = None):
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}

    def evaluate(self, analytics: dict[str, Any]) -> dict[str, Any]:
        a = analytics.get("analytics") or analytics
        breaches = []
        warnings = []

        def check(name: str, value: float, limit: float, higher_is_breach: bool = True):
            if higher_is_breach:
                if value > limit * 1.0 + 1e-9:
                    breaches.append({"limit": name, "value": value, "threshold": limit, "severity": "breach"})
                elif value > limit * 0.85:
                    warnings.append({"limit": name, "value": value, "threshold": limit, "severity": "warning"})
            else:
                if value < limit - 1e-9:
                    breaches.append({"limit": name, "value": value, "threshold": limit, "severity": "breach"})

        check("max_leverage", float(a.get("leverage", 0)), float(self.limits["max_leverage"]))
        check("max_drawdown", float(a.get("maximum_drawdown", 0)), float(self.limits["max_drawdown"]))
        check("max_var_95", float(a.get("var_95", 0)), float(self.limits["max_var_95"]))
        check("max_expected_shortfall_95", float(a.get("expected_shortfall_95", 0)), float(self.limits["max_expected_shortfall_95"]))
        check("max_gross_exposure", float(a.get("gross_exposure", 0)) / max(float(a.get("equity", 1)), 1e-9),
              float(self.limits["max_gross_exposure"]))

        top_w = float((analytics.get("diversification") or {}).get("top_weight") or 0)
        check("max_position_weight", top_w, float(self.limits["max_position_weight"]))

        for sec, w in (analytics.get("sector_exposure") or {}).items():
            if w > float(self.limits["max_sector_weight"]) + 1e-9:
                breaches.append({"limit": "max_sector_weight", "sector": sec, "value": w,
                                 "threshold": self.limits["max_sector_weight"], "severity": "breach"})

        state = LimitState.WITHIN_LIMITS
        if breaches:
            state = LimitState.BREACHED
        elif warnings:
            state = LimitState.WARNING

        # Risk budgets (equal risk contribution target vs actual)
        risk_attr = analytics.get("risk_attribution") or []
        n = len(risk_attr) or 1
        target = 1.0 / n
        budgets = [
            {
                "symbol": r["symbol"],
                "actual": r["risk_contribution"],
                "target": round(target, 6),
                "delta": round(r["risk_contribution"] - target, 6),
            }
            for r in risk_attr
        ]

        return {
            "ok": True,
            "state": state.value,
            "limits": self.limits,
            "breaches": breaches,
            "warnings": warnings,
            "risk_budgets": budgets,
            "drawdown_manager": {
                "current_drawdown": a.get("maximum_drawdown"),
                "limit": self.limits["max_drawdown"],
                "action": "HALT_RESEARCH_REBALANCE" if state == LimitState.BREACHED else "MONITOR",
            },
            **AUTHORITY_VALUES,
        }
