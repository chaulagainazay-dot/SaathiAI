"""Position sizing and dynamic allocation (research-only)."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.portfolio_risk.models import AUTHORITY_VALUES, DEFAULT_MAX_LEVERAGE
from saathi.platform.tg.portfolio_risk.errors import PortfolioRiskError


class PositionSizingEngine:
    """Deterministic research position sizing — not live order authority."""

    METHODS = ("fixed_fractional", "equal_weight", "inverse_volatility", "risk_parity_lite")

    def size(
        self,
        symbols: list[str],
        *,
        equity: float = 100_000.0,
        method: str = "equal_weight",
        volatilities: dict[str, float] | None = None,
        max_weight: float = 0.35,
        max_leverage: float = DEFAULT_MAX_LEVERAGE,
    ) -> dict[str, Any]:
        if max_leverage > DEFAULT_MAX_LEVERAGE + 1e-9:
            raise PortfolioRiskError(
                "LEVERAGE_POLICY",
                f"max_leverage {max_leverage} exceeds policy {DEFAULT_MAX_LEVERAGE}",
            )
        if not symbols:
            raise PortfolioRiskError("NO_SYMBOLS", "symbols required")
        method = method.lower()
        if method not in self.METHODS:
            raise PortfolioRiskError("UNKNOWN_METHOD", method)

        n = len(symbols)
        volatilities = volatilities or {s: 0.15 for s in symbols}

        if method == "equal_weight":
            raw = {s: 1.0 / n for s in symbols}
        elif method == "fixed_fractional":
            frac = min(max_weight, 1.0 / n)
            raw = {s: frac for s in symbols}
        elif method in ("inverse_volatility", "risk_parity_lite"):
            inv = {s: 1.0 / max(float(volatilities.get(s, 0.15)), 1e-6) for s in symbols}
            ssum = sum(inv.values())
            raw = {s: inv[s] / ssum for s in symbols}
        else:
            raw = {s: 1.0 / n for s in symbols}

        # Cap and renorm under leverage
        investable = min(1.0, max_leverage)
        capped = {s: min(max_weight, raw[s]) for s in symbols}
        tot = sum(capped.values()) or 1.0
        weights = {s: investable * capped[s] / tot for s in symbols}
        # re-cap once
        weights = {s: min(max_weight, weights[s]) for s in symbols}
        tot = sum(weights.values()) or 1.0
        weights = {s: investable * weights[s] / tot for s in symbols}

        notionals = {s: round(equity * weights[s], 2) for s in symbols}
        return {
            "ok": True,
            "method": method,
            "weights": {k: round(v, 6) for k, v in weights.items()},
            "notionals": notionals,
            "equity": equity,
            "cash_weight": round(max(0.0, 1.0 - sum(weights.values())), 6),
            "max_leverage": max_leverage,
            "authorizes_execution": False,
            **AUTHORITY_VALUES,
        }

    def dynamic_allocation(
        self,
        base_weights: dict[str, float],
        *,
        regime: str = "normal",
        vol_scale: float = 1.0,
    ) -> dict[str, Any]:
        """Regime-aware scaling of pre-frozen weights (no test leakage — regime is input)."""
        scale = 1.0
        if regime in ("high_volatility", "risk_off", "downward_trend"):
            scale = 0.7
        elif regime in ("low_volatility", "upward_trend"):
            scale = 1.0
        scale *= max(0.3, min(1.2, 1.0 / max(vol_scale, 0.5)))
        weights = {k: round(v * scale, 6) for k, v in base_weights.items()}
        tot = sum(weights.values())
        if tot > 1.0:
            weights = {k: round(v / tot, 6) for k, v in weights.items()}
        return {
            "ok": True,
            "regime": regime,
            "scale": round(scale, 4),
            "weights": weights,
            "cash_weight": round(max(0.0, 1.0 - sum(weights.values())), 6),
            "rule": "predefined_regime_scale",
            "test_set_tuning": False,
            **AUTHORITY_VALUES,
        }
