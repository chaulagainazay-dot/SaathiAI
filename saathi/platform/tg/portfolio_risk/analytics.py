"""Portfolio analytics, attribution, exposures, correlation, diversification."""
from __future__ import annotations

import math
from typing import Any

from saathi.platform.tg.portfolio_risk.models import AUTHORITY_VALUES, DEFAULT_DEMO_PORTFOLIO


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var) if var > 0 else 0.0


def _default_returns(n: int = 90, seed: int = 11) -> list[float]:
    out = []
    state = seed
    for i in range(n):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        noise = ((state % 2000) / 2000.0 - 0.5) * 0.018
        if 30 <= i < 40:
            r = -0.01 + noise * 0.4
        else:
            r = 0.0006 + noise
        out.append(round(r, 8))
    return out


def _asset_returns(symbol: str, n: int, seed: int) -> list[float]:
    base = _default_returns(n, seed + sum(ord(c) for c in symbol) % 97)
    # slight symbol-specific drift
    drift = (sum(ord(c) for c in symbol) % 7 - 3) * 0.00005
    return [round(r + drift, 8) for r in base]


class PortfolioAnalytics:
    """Institutional paper portfolio analytics (research metrics, not regulatory capital)."""

    def analyze(self, portfolio: dict[str, Any] | None = None) -> dict[str, Any]:
        p = dict(portfolio or DEFAULT_DEMO_PORTFOLIO)
        positions = list(p.get("positions") or [])
        cash = float(p.get("cash", 0))
        rets = list(p.get("returns_daily") or _default_returns())

        pos_rows = []
        sector: dict[str, float] = {}
        geo: dict[str, float] = {}
        asset_class: dict[str, float] = {}
        beta_mv = 0.0
        gross = 0.0
        unrealized = 0.0
        factor_exp: dict[str, float] = {"market": 0.0, "size": 0.0, "value": 0.0, "momentum": 0.0}

        for pos in positions:
            qty = float(pos.get("quantity", 0))
            mark = float(pos.get("mark", pos.get("avg_cost", 0)))
            cost = float(pos.get("avg_cost", mark))
            mv = qty * mark
            upl = mv - qty * cost
            gross += abs(mv)
            unrealized += upl
            beta = float(pos.get("beta", 1.0))
            beta_mv += mv * beta
            sec = pos.get("sector", "UNKNOWN")
            sector[sec] = sector.get(sec, 0) + abs(mv)
            g = pos.get("geography", "UNKNOWN")
            geo[g] = geo.get(g, 0) + abs(mv)
            ac = pos.get("asset_class", "UNKNOWN")
            asset_class[ac] = asset_class.get(ac, 0) + abs(mv)
            loadings = pos.get("factor_loadings") or {}
            for fk in factor_exp:
                factor_exp[fk] += abs(mv) * float(loadings.get(fk, 0.0))
            pos_rows.append({
                "symbol": pos.get("symbol"),
                "quantity": qty,
                "mark": mark,
                "market_value": round(mv, 4),
                "unrealized_pnl": round(upl, 4),
                "weight": 0.0,
                "sector": sec,
                "geography": g,
                "asset_class": ac,
                "beta": beta,
                "factor_loadings": loadings,
            })

        equity = cash + sum(r["market_value"] for r in pos_rows)
        if equity <= 0:
            equity = 1.0
        for r in pos_rows:
            r["weight"] = round(r["market_value"] / equity, 6)

        # Position attribution (PnL contribution)
        total_upl = unrealized or 1e-12
        position_attribution = [
            {
                "symbol": r["symbol"],
                "pnl": r["unrealized_pnl"],
                "pnl_contribution": round(r["unrealized_pnl"] / total_upl, 6),
                "weight": r["weight"],
            }
            for r in pos_rows
        ]

        # Risk metrics
        vol = _std(rets) * math.sqrt(252)
        mean_d = _mean(rets)
        sharpe = (mean_d * 252) / vol if vol > 0 else 0.0
        downside = [r for r in rets if r < 0]
        dstd = _std(downside) * math.sqrt(252) if downside else 0.0
        sortino = (mean_d * 252) / dstd if dstd > 0 else 0.0
        eq = float(p.get("starting_equity", equity))
        peak = eq
        max_dd = 0.0
        for r in rets:
            eq *= 1 + r
            peak = max(peak, eq)
            max_dd = max(max_dd, (peak - eq) / peak if peak else 0)

        sorted_r = sorted(rets)
        n = len(sorted_r)
        var95 = -sorted_r[max(0, int(0.05 * n) - 1)] if n else 0.0
        tail = sorted_r[: max(1, int(0.05 * n))] if n else [0.0]
        es95 = -_mean(tail)

        weights = [r["weight"] for r in pos_rows]
        hhi = sum(w * w for w in weights)
        n_eff = (1.0 / hhi) if hhi > 0 else 0.0
        diversification_ratio = min(1.0, n_eff / max(1, len(pos_rows))) if pos_rows else 0.0

        portfolio_beta = (beta_mv / gross) if gross > 0 else 0.0
        factor_exposure = {
            k: round(v / gross, 6) if gross > 0 else 0.0 for k, v in factor_exp.items()
        }

        # Correlation matrix from synthetic asset returns
        corr = self._correlation(pos_rows, seed=int(p.get("seed", 11)))

        # Risk attribution: component variance share using beta proxy
        risk_attr = []
        beta_sum = sum(abs(r["weight"] * r["beta"]) for r in pos_rows) or 1.0
        for r in pos_rows:
            rc = abs(r["weight"] * r["beta"]) / beta_sum
            risk_attr.append({
                "symbol": r["symbol"],
                "risk_contribution": round(rc, 6),
                "marginal_beta": r["beta"],
                "weight": r["weight"],
            })

        def exp_map(m: dict[str, float]) -> dict[str, float]:
            return {k: round(v / equity, 6) for k, v in sorted(m.items())}

        return {
            "ok": True,
            "portfolio_id": p.get("id", "paper"),
            "name": p.get("name", "Paper Portfolio"),
            "currency": p.get("currency", "USD"),
            "analytics": {
                "cash": round(cash, 4),
                "equity": round(equity, 4),
                "gross_exposure": round(gross, 4),
                "net_exposure": round(gross if all(r["market_value"] >= 0 for r in pos_rows) else sum(r["market_value"] for r in pos_rows), 4),
                "unrealized_pnl": round(unrealized, 4),
                "realized_pnl": round(float(p.get("realized_pnl", 0)), 4),
                "leverage": round(gross / equity, 6) if equity else 0.0,
                "volatility": round(vol, 6),
                "sharpe_ratio": round(sharpe, 6),
                "sortino_ratio": round(sortino, 6),
                "maximum_drawdown": round(max_dd, 6),
                "var_95": round(var95, 6),
                "expected_shortfall_95": round(es95, 6),
                "portfolio_beta": round(portfolio_beta, 6),
                "hhi": round(hhi, 6),
                "effective_n": round(n_eff, 4),
                "diversification_ratio": round(diversification_ratio, 6),
            },
            "positions": pos_rows,
            "position_attribution": position_attribution,
            "risk_attribution": risk_attr,
            "factor_exposure": factor_exposure,
            "beta_exposure": {"portfolio_beta": round(portfolio_beta, 6), "by_position": {r["symbol"]: r["beta"] for r in pos_rows}},
            "sector_exposure": exp_map(sector),
            "geography_exposure": exp_map(geo),
            "asset_class_exposure": exp_map(asset_class),
            "correlation_matrix": corr,
            "diversification": {
                "hhi": round(hhi, 6),
                "effective_n": round(n_eff, 4),
                "ratio": round(diversification_ratio, 6),
                "top_weight": round(max(weights) if weights else 0.0, 6),
            },
            "labels": {
                "research_metrics_only": True,
                "not_regulatory_capital": True,
                "not_investment_advice": True,
            },
            **AUTHORITY_VALUES,
        }

    def _correlation(self, pos_rows: list[dict], seed: int = 11) -> dict[str, Any]:
        symbols = [r["symbol"] for r in pos_rows]
        n = 60
        series = {s: _asset_returns(s, n, seed) for s in symbols}
        matrix = {}
        for a in symbols:
            matrix[a] = {}
            for b in symbols:
                if a == b:
                    matrix[a][b] = 1.0
                    continue
                xa, xb = series[a], series[b]
                ma, mb = _mean(xa), _mean(xb)
                num = sum((xa[i] - ma) * (xb[i] - mb) for i in range(n))
                da = math.sqrt(sum((x - ma) ** 2 for x in xa))
                db = math.sqrt(sum((x - mb) ** 2 for x in xb))
                c = num / (da * db) if da and db else 0.0
                matrix[a][b] = round(c, 4)
        return {"symbols": symbols, "matrix": matrix, "method": "synthetic_return_series", "label": "RESEARCH_APPROXIMATION"}
