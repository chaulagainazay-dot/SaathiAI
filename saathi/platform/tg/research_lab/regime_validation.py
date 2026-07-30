"""M275 — Strategy validation by regime (no look-ahead)."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.research_lab.comparison import _metrics_from_returns
from saathi.platform.tg.research_lab.models import AUTHORITY_VALUES


class RegimeValidationEngine:
    def validate_strategy_by_regime(
        self,
        returns: list[float],
        regime_series: list[dict[str, Any]],
        *,
        strategy_id: str,
    ) -> dict[str, Any]:
        by_reg: dict[str, list[float]] = {}
        n = min(len(returns), len(regime_series))
        for i in range(n):
            lab = (regime_series[i].get("labels") or {}).get("trend", "UNKNOWN")
            if regime_series[i].get("state") in ("REGIME_INSUFFICIENT_DATA", "REGIME_UNKNOWN"):
                lab = "UNKNOWN"
            # Only use regime label available at i (already PIT in classifier)
            by_reg.setdefault(lab, []).append(returns[i])

        matrix = {}
        for lab, rets in by_reg.items():
            m = _metrics_from_returns(rets)
            matrix[lab] = {
                "n": len(rets),
                "expectancy": m["expectancy"],
                "sharpe_ratio": m["sharpe_ratio"],
                "maximum_drawdown": m["maximum_drawdown"],
            }

        # Regime dependence heuristic
        sharpes = [v["sharpe_ratio"] for v in matrix.values() if v["n"] >= 5]
        regime_dependent = (max(sharpes) - min(sharpes)) > 0.8 if len(sharpes) >= 2 else False

        return {
            "ok": True,
            "strategy_id": strategy_id,
            "strategy_by_regime": matrix,
            "regime_dependent": regime_dependent,
            "unknown_included": "UNKNOWN" in matrix,
            "limitations": [
                "Regime labels are research classifications, not live market state feeds",
                "Small-n regimes have low confidence",
            ],
            **AUTHORITY_VALUES,
        }
