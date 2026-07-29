"""Paper portfolio analytics — deterministic metrics from ledger/equity curve."""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from saathi.platform.tg.paper_activation.models import D, PaperPortfolio


def _trade_pnls(portfolio: PaperPortfolio) -> list[float]:
    """Approximate closed-trade pnls from position history sells."""
    pnls: list[float] = []
    for pos in portfolio.positions.values():
        for h in pos.history:
            if h.get("event") == "sell" and "pnl" in h:
                pnls.append(float(D(h["pnl"])))
    # also use realized if no history granularity
    if not pnls and portfolio.realized_pnl != 0:
        pnls.append(float(portfolio.realized_pnl))
    return pnls


def compute_analytics(portfolio: PaperPortfolio) -> dict[str, Any]:
    pnls = _trade_pnls(portfolio)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    n = len(pnls)
    win_rate = (len(wins) / n) if n else 0.0
    gross_win = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    expectancy = (sum(pnls) / n) if n else 0.0
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    avg_r = (avg_win / abs(avg_loss)) if avg_loss else 0.0

    # equity curve stats
    curve = portfolio.equity_curve
    rets: list[float] = []
    for i in range(1, len(curve)):
        prev = float(curve[i - 1].equity)
        cur = float(curve[i].equity)
        if prev > 0:
            rets.append((cur - prev) / prev)
    sharpe = 0.0
    sortino = 0.0
    if rets:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / len(rets)
        std = math.sqrt(var) if var > 0 else 0.0
        sharpe = (mean / std) * math.sqrt(252) if std > 0 else 0.0
        downside = [r for r in rets if r < 0]
        if downside:
            dvar = sum(r ** 2 for r in downside) / len(downside)
            dstd = math.sqrt(dvar)
            sortino = (mean / dstd) * math.sqrt(252) if dstd > 0 else 0.0

    eq = float(portfolio.compute_equity())
    start = float(portfolio.starting_cash)
    total_ret = (eq / start - 1.0) if start else 0.0
    dd = float(portfolio.drawdown_pct()) / 100.0
    calmar = (total_ret / dd) if dd > 0 else 0.0

    # Ulcer index (approx from curve)
    ulcer = 0.0
    if curve:
        peak = float(curve[0].equity)
        sq = 0.0
        for s in curve:
            e = float(s.equity)
            peak = max(peak, e)
            dd_i = (peak - e) / peak * 100 if peak else 0
            sq += dd_i ** 2
        ulcer = math.sqrt(sq / len(curve))

    # MAE/MFE proxies from marks vs avg (open positions)
    mae = mfe = 0.0
    for sym, pos in portfolio.positions.items():
        if pos.quantity <= 0:
            continue
        mark = float(portfolio.marks.get(sym, pos.avg_price))
        avg = float(pos.avg_price)
        move = (mark - avg) / avg if avg else 0
        mfe = max(mfe, move)
        mae = min(mae, move)

    exposure = {}
    eq_d = portfolio.compute_equity() or Decimal("1")
    for sym, pos in portfolio.positions.items():
        if pos.quantity <= 0:
            continue
        mv = pos.quantity * portfolio.marks.get(sym, pos.avg_price)
        exposure[sym] = str((mv / eq_d) * Decimal("100"))

    return {
        "trade_count": n,
        "win_rate": round(win_rate, 6),
        "profit_factor": None if math.isinf(profit_factor) else round(profit_factor, 6),
        "expectancy": round(expectancy, 6),
        "average_r": round(avg_r, 6),
        "average_hold_time": None,  # requires timestamps per round-trip; not claimed
        "mae": round(mae, 6),
        "mfe": round(mfe, 6),
        "sharpe": round(sharpe, 6),
        "sortino": round(sortino, 6),
        "calmar": round(calmar, 6),
        "ulcer": round(ulcer, 6),
        "total_return": round(total_ret, 6),
        "max_drawdown_pct": str(portfolio.drawdown_pct()),
        "equity": str(portfolio.compute_equity()),
        "realized_pnl": str(portfolio.realized_pnl),
        "unrealized_pnl": str(portfolio.unrealized_pnl()),
        "rolling_equity": [s.to_public() for s in curve[-100:]],
        "exposure_heatmap": exposure,
        "paper_only": True,
        "live_authorized": False,
        "disclaimer": "Simulated analytics. Historical paper results are not future results.",
    }


def compare_portfolios(portfolios: list[PaperPortfolio]) -> dict[str, Any]:
    rows = {}
    for p in portfolios:
        a = compute_analytics(p)
        rows[p.id] = {
            "name": p.name,
            "total_return": a["total_return"],
            "max_drawdown_pct": a["max_drawdown_pct"],
            "sharpe": a["sharpe"],
            "trade_count": a["trade_count"],
            "win_rate": a["win_rate"],
        }
    ranking = sorted(rows.keys(), key=lambda i: (-float(rows[i]["max_drawdown_pct"] or 0), rows[i]["total_return"]), reverse=True)
    return {
        "portfolios": rows,
        "ranking": ranking,
        "paper_only": True,
        "note": "Ranking prioritizes lower drawdown then return. Not a profitability claim.",
    }
