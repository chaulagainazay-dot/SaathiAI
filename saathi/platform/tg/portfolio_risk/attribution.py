"""Research performance attribution."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.portfolio_risk.models import AUTHORITY_VALUES
from saathi.platform.tg.portfolio_risk.analytics import _asset_returns, _mean


class PerformanceAttribution:
    def attribute(self, analytics: dict[str, Any], *, seed: int = 42) -> dict[str, Any]:
        positions = analytics.get("positions") or []
        # Brinson-lite: allocation vs selection using equal-weight benchmark
        n = len(positions) or 1
        bench_w = 1.0 / n
        rows = []
        total_alloc = 0.0
        total_select = 0.0
        for i, p in enumerate(positions):
            w_p = float(p.get("weight") or 0)
            rets = _asset_returns(p.get("symbol", "X"), 40, seed + i)
            r_p = _mean(rets) * 252
            r_b = _mean(_asset_returns("BENCH", 40, seed)) * 252
            alloc = (w_p - bench_w) * r_b
            select = bench_w * (r_p - r_b)
            interaction = (w_p - bench_w) * (r_p - r_b)
            total_alloc += alloc
            total_select += select
            rows.append({
                "symbol": p.get("symbol"),
                "weight": w_p,
                "active_weight": round(w_p - bench_w, 6),
                "asset_return_ann": round(r_p, 6),
                "allocation_effect": round(alloc, 6),
                "selection_effect": round(select, 6),
                "interaction_effect": round(interaction, 6),
            })
        return {
            "ok": True,
            "method": "brinson_lite_equal_weight_benchmark",
            "label": "RESEARCH_ATTRIBUTION_NOT_OFFICIAL_GIPS",
            "total_allocation_effect": round(total_alloc, 6),
            "total_selection_effect": round(total_select, 6),
            "positions": rows,
            "factor_attribution": analytics.get("factor_exposure"),
            **AUTHORITY_VALUES,
        }
