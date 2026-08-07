"""M249 — Portfolio Intelligence Engine.

Paper portfolios only. Institutional risk and exposure analytics.
"""
from __future__ import annotations

import math
from typing import Any

from saathi.platform.tg.intelligence.models import AUTHORITY_VALUES

# Default paper portfolio fixture (deterministic)
DEFAULT_PAPER_PORTFOLIO: dict[str, Any] = {
    "id": "paper_core_demo",
    "name": "Paper Core Demo",
    "currency": "USD",
    "cash": 25000.0,
    "starting_equity": 100000.0,
    "positions": [
        {
            "symbol": "SPY",
            "quantity": 100,
            "avg_cost": 420.0,
            "mark": 450.0,
            "sector": "Broad Market",
            "geography": "US",
            "asset_class": "equity_etf",
            "beta": 1.0,
        },
        {
            "symbol": "QQQ",
            "quantity": 50,
            "avg_cost": 350.0,
            "mark": 380.0,
            "sector": "Technology",
            "geography": "US",
            "asset_class": "equity_etf",
            "beta": 1.15,
        },
        {
            "symbol": "EFA",
            "quantity": 80,
            "avg_cost": 70.0,
            "mark": 72.0,
            "sector": "International",
            "geography": "Developed ex-US",
            "asset_class": "equity_etf",
            "beta": 0.9,
        },
        {
            "symbol": "TLT",
            "quantity": 60,
            "avg_cost": 95.0,
            "mark": 90.0,
            "sector": "Fixed Income",
            "geography": "US",
            "asset_class": "bond_etf",
            "beta": -0.2,
        },
        {
            "symbol": "GLD",
            "quantity": 40,
            "avg_cost": 180.0,
            "mark": 190.0,
            "sector": "Commodities",
            "geography": "Global",
            "asset_class": "commodity_etf",
            "beta": 0.1,
        },
    ],
    "realized_pnl": 1250.0,
    "returns_daily": None,  # filled by engine if absent
}


def _default_returns(n: int = 60, seed: int = 7) -> list[float]:
    """Deterministic mild-positive daily returns with drawdowns."""
    out = []
    state = seed
    for i in range(n):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        noise = ((state % 2000) / 2000.0 - 0.5) * 0.02
        # inject a drawdown window
        if 20 <= i < 30:
            r = -0.008 + noise * 0.5
        else:
            r = 0.0008 + noise
        out.append(round(r, 8))
    return out


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var) if var > 0 else 0.0


def _percentile(sorted_xs: list[float], p: float) -> float:
    if not sorted_xs:
        return 0.0
    if p <= 0:
        return sorted_xs[0]
    if p >= 100:
        return sorted_xs[-1]
    k = (len(sorted_xs) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_xs[int(k)]
    return sorted_xs[f] * (c - k) + sorted_xs[c] * (k - f)


class PortfolioIntelligenceEngine:
    """Compute institutional portfolio metrics from paper state."""

    def analyze(self, portfolio: dict[str, Any] | None = None) -> dict[str, Any]:
        p = dict(portfolio or DEFAULT_PAPER_PORTFOLIO)
        positions = list(p.get("positions") or [])
        cash = float(p.get("cash", 0))
        realized = float(p.get("realized_pnl", 0))
        rets = list(p.get("returns_daily") or _default_returns())

        pos_values = []
        gross = 0.0
        unrealized = 0.0
        sector: dict[str, float] = {}
        geo: dict[str, float] = {}
        asset_class: dict[str, float] = {}
        beta_weighted = 0.0

        for pos in positions:
            qty = float(pos.get("quantity", 0))
            mark = float(pos.get("mark", pos.get("avg_cost", 0)))
            cost = float(pos.get("avg_cost", mark))
            mv = qty * mark
            cost_basis = qty * cost
            upl = mv - cost_basis
            gross += abs(mv)
            unrealized += upl
            beta_weighted += mv * float(pos.get("beta", 1.0))
            sector[pos.get("sector", "UNKNOWN")] = sector.get(pos.get("sector", "UNKNOWN"), 0) + abs(mv)
            geo[pos.get("geography", "UNKNOWN")] = geo.get(pos.get("geography", "UNKNOWN"), 0) + abs(mv)
            asset_class[pos.get("asset_class", "UNKNOWN")] = asset_class.get(pos.get("asset_class", "UNKNOWN"), 0) + abs(mv)
            pos_values.append({
                "symbol": pos.get("symbol"),
                "market_value": round(mv, 4),
                "unrealized_pnl": round(upl, 4),
                "weight": 0.0,  # filled below
                "sector": pos.get("sector"),
                "geography": pos.get("geography"),
                "asset_class": pos.get("asset_class"),
                "beta": float(pos.get("beta", 1.0)),
            })

        equity = cash + sum(v["market_value"] for v in pos_values)
        if equity <= 0:
            equity = 1.0
        for v in pos_values:
            v["weight"] = round(v["market_value"] / equity, 6)

        weights = [v["weight"] for v in pos_values]
        hhi = sum(w * w for w in weights)  # Herfindahl
        top_weight = max(weights) if weights else 0.0
        n_eff = (1.0 / hhi) if hhi > 0 else 0.0
        diversification = min(1.0, n_eff / max(1, len(pos_values))) if pos_values else 0.0

        def exp_map(m: dict[str, float]) -> dict[str, float]:
            return {k: round(v / equity, 6) for k, v in sorted(m.items())}

        # Risk metrics from returns
        vol = _std(rets) * math.sqrt(252)
        mean_d = _mean(rets)
        sharpe = (mean_d * 252) / vol if vol > 0 else 0.0
        downside = [r for r in rets if r < 0]
        dstd = _std(downside) * math.sqrt(252) if downside else 0.0
        sortino = (mean_d * 252) / dstd if dstd > 0 else 0.0

        # Equity curve & max drawdown
        eq = float(p.get("starting_equity", equity))
        peak = eq
        max_dd = 0.0
        curve = [eq]
        for r in rets:
            eq *= 1.0 + r
            peak = max(peak, eq)
            dd = (peak - eq) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
            curve.append(round(eq, 4))

        # Historical VaR / ES (parametric + historical hybrid, labeled paper)
        sorted_rets = sorted(rets)
        var_95 = -_percentile(sorted_rets, 5)
        var_99 = -_percentile(sorted_rets, 1)
        tail_95 = [r for r in sorted_rets if r <= -var_95] or sorted_rets[: max(1, len(sorted_rets) // 20)]
        es_95 = -_mean(tail_95)

        portfolio_beta = (beta_weighted / gross) if gross > 0 else 0.0

        # Correlation matrix (simplified pairwise from synthetic series)
        corr = self._correlation_matrix(positions, rets)

        return {
            "portfolio_id": p.get("id", "paper"),
            "name": p.get("name", "Paper Portfolio"),
            "currency": p.get("currency", "USD"),
            "allocation": {
                "cash": round(cash, 4),
                "invested": round(gross, 4),
                "equity": round(cash + sum(v["market_value"] for v in pos_values), 4),
                "cash_utilisation": round(1.0 - cash / (cash + gross) if (cash + gross) > 0 else 0.0, 6),
                "positions": pos_values,
            },
            "diversification": {
                "herfindahl": round(hhi, 6),
                "effective_n": round(n_eff, 4),
                "score": round(diversification, 4),
                "position_count": len(pos_values),
            },
            "concentration": {
                "top_position_weight": round(top_weight, 6),
                "top_3_weight": round(sum(sorted(weights, reverse=True)[:3]), 6),
                "hhi": round(hhi, 6),
            },
            "sector_exposure": exp_map(sector),
            "geographic_exposure": exp_map(geo),
            "asset_class_exposure": exp_map(asset_class),
            "cash_utilisation": round(gross / (cash + gross) if (cash + gross) > 0 else 0.0, 6),
            "unrealised_pnl": round(unrealized, 4),
            "realised_pnl": round(realized, 4),
            "total_pnl": round(unrealized + realized, 4),
            "portfolio_beta": round(portfolio_beta, 4),
            "volatility_annualized": round(vol, 6),
            "sharpe_ratio": round(sharpe, 4),
            "sortino_ratio": round(sortino, 4),
            "maximum_drawdown": round(max_dd, 6),
            "correlation": corr,
            "var": {
                "method": "historical_paper",
                "var_95_1d": round(var_95, 6),
                "var_99_1d": round(var_99, 6),
                "expected_shortfall_95": round(es_95, 6),
                "horizon": "1d",
                "disclaimer": "Paper historical VaR from synthetic/offline returns; not regulatory capital.",
            },
            "equity_curve_tail": curve[-20:],
            "funds_label": "SIMULATED",
            "disclaimer": "SIMULATED FUNDS — NOT REAL MONEY — PAPER ONLY",
            **AUTHORITY_VALUES,
        }

    def risk_report(self, portfolio: dict[str, Any] | None = None) -> dict[str, Any]:
        a = self.analyze(portfolio)
        alerts = []
        if a["concentration"]["top_position_weight"] > 0.35:
            alerts.append({"severity": "warn", "code": "HIGH_CONCENTRATION", "message": "Top position > 35%"})
        if a["maximum_drawdown"] > 0.15:
            alerts.append({"severity": "warn", "code": "DRAWDOWN_ELEVATED", "message": "Max DD > 15%"})
        if a["var"]["var_95_1d"] > 0.03:
            alerts.append({"severity": "info", "code": "VAR_ELEVATED", "message": "1d VaR 95% > 3%"})
        if a["cash_utilisation"] > 0.95:
            alerts.append({"severity": "info", "code": "LOW_CASH", "message": "Cash utilisation > 95%"})
        return {
            "portfolio_id": a["portfolio_id"],
            "risk_summary": {
                "volatility": a["volatility_annualized"],
                "sharpe": a["sharpe_ratio"],
                "sortino": a["sortino_ratio"],
                "max_drawdown": a["maximum_drawdown"],
                "beta": a["portfolio_beta"],
                "var_95": a["var"]["var_95_1d"],
                "expected_shortfall_95": a["var"]["expected_shortfall_95"],
            },
            "exposures": {
                "sector": a["sector_exposure"],
                "geographic": a["geographic_exposure"],
                "asset_class": a["asset_class_exposure"],
            },
            "concentration": a["concentration"],
            "diversification": a["diversification"],
            "alerts": alerts,
            **AUTHORITY_VALUES,
        }

    def _correlation_matrix(self, positions: list[dict], base_rets: list[float]) -> dict[str, Any]:
        symbols = [p.get("symbol", f"P{i}") for i, p in enumerate(positions)]
        # Deterministic pseudo-correlations from betas
        matrix = {}
        for i, a in enumerate(positions):
            row = {}
            ba = float(a.get("beta", 1.0))
            for j, b in enumerate(positions):
                if i == j:
                    row[symbols[j]] = 1.0
                else:
                    bb = float(b.get("beta", 1.0))
                    # simple synthetic corr in [-0.3, 0.95]
                    c = max(-0.3, min(0.95, 0.4 + 0.4 * ba * bb / (1 + abs(ba - bb))))
                    if a.get("asset_class") != b.get("asset_class"):
                        c *= 0.5
                    row[symbols[j]] = round(c, 4)
            matrix[symbols[i]] = row
        return {
            "symbols": symbols,
            "matrix": matrix,
            "method": "synthetic_beta_structure_paper",
            "note": "Offline paper correlation structure; not live market corr.",
        }
