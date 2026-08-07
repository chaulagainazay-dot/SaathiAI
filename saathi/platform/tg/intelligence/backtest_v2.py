"""M250 — Deterministic Backtesting Engine V2.

Historical replay with costs, slippage, commissions, partial fills, capital limits.
Paper / offline only.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

from saathi.platform.tg.intelligence.models import AUTHORITY_VALUES


def _lcg(seed: int):
    state = seed & 0x7FFFFFFF
    while True:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        yield state / float(0x7FFFFFFF)


def _synth_bars(n: int = 120, seed: int = 42, regime: str = "trend") -> list[dict[str, float]]:
    rng = _lcg(seed)
    px = 100.0
    bars = []
    for i in range(n):
        u = next(rng)
        if regime == "trend":
            drift = 0.0012
        elif regime == "mean_revert":
            drift = -0.0003 * (px - 100) / 100
        else:
            drift = 0.0
        noise = (u - 0.5) * 0.02
        ret = drift + noise
        o = px
        c = px * (1 + ret)
        h = max(o, c) * (1 + abs(noise) * 0.3)
        l = min(o, c) * (1 - abs(noise) * 0.3)
        vol = 1_000_000 * (0.8 + u * 0.4)
        bars.append({
            "i": i,
            "open": round(o, 6),
            "high": round(h, 6),
            "low": round(l, 6),
            "close": round(c, 6),
            "volume": round(vol, 2),
        })
        px = c
    return bars


class BacktestEngineV2:
    """Deterministic multi-strategy backtester with realistic cost model."""

    def run(
        self,
        strategy_id: str = "tf_dual_ma",
        *,
        bars: list[dict[str, float]] | None = None,
        capital: float = 100_000.0,
        commission_bps: float = 5.0,
        slippage_bps: float = 8.0,
        liquidity_participation: float = 0.10,
        partial_fill: bool = True,
        seed: int = 42,
        benchmark: str = "buy_hold",
        regime: str = "trend",
    ) -> dict[str, Any]:
        bars = bars or _synth_bars(120, seed=seed, regime=regime)
        if len(bars) < 30:
            return {
                "ok": False,
                "code": "INSUFFICIENT_BARS",
                "bars": len(bars),
                **AUTHORITY_VALUES,
            }

        cash = capital
        qty = 0.0
        avg_cost = 0.0
        equity_curve: list[float] = []
        drawdown_curve: list[float] = []
        trades: list[dict[str, Any]] = []
        peak = capital
        total_fees = 0.0
        total_slip = 0.0
        wins = 0
        losses = 0
        gross_profit = 0.0
        gross_loss = 0.0
        monthly: dict[str, float] = {}
        yearly: dict[str, float] = {}

        closes = [float(b["close"]) for b in bars]
        for i in range(25, len(bars)):
            window = closes[: i + 1]
            sma_fast = sum(window[-10:]) / 10
            sma_slow = sum(window[-20:]) / 20
            px = closes[i]
            bar = bars[i]
            signal = 0
            if strategy_id.startswith("mr_") or "mean" in strategy_id:
                mid = sum(window[-20:]) / 20
                if px < mid * 0.98:
                    signal = 1
                elif px > mid * 1.02:
                    signal = -1
            elif strategy_id.startswith("bo_") or "breakout" in strategy_id:
                hi = max(window[-20:-1])
                lo = min(window[-20:-1])
                if px >= hi:
                    signal = 1
                elif px <= lo:
                    signal = -1
            else:
                # momentum / trend default
                if sma_fast > sma_slow:
                    signal = 1
                elif sma_fast < sma_slow:
                    signal = -1

            # target position: long or flat for paper simplicity
            target_qty = 0.0
            if signal > 0 and cash > 0:
                risk_capital = min(cash, capital * 0.95)
                raw_qty = risk_capital / px
                # liquidity assumption
                max_by_liq = float(bar.get("volume", 1e6)) * liquidity_participation
                target_qty = min(raw_qty, max_by_liq)
                if partial_fill and target_qty > max_by_liq * 0.5:
                    target_qty *= 0.85  # partial

            delta = target_qty - qty
            if abs(delta) * px > 50:  # min notional
                side = "BUY" if delta > 0 else "SELL"
                fill_qty = abs(delta)
                slip = px * (slippage_bps / 10000.0)
                fill_px = px + slip if side == "BUY" else px - slip
                fee = fill_qty * fill_px * (commission_bps / 10000.0)
                notional = fill_qty * fill_px
                if side == "BUY":
                    if notional + fee > cash:
                        fill_qty = max(0.0, (cash - fee) / fill_px) if fill_px > 0 else 0.0
                        notional = fill_qty * fill_px
                    cash -= notional + fee
                    if qty + fill_qty > 0:
                        avg_cost = ((avg_cost * qty) + notional) / (qty + fill_qty) if (qty + fill_qty) else 0.0
                    qty += fill_qty
                else:
                    proceeds = notional - fee
                    cash += proceeds
                    pnl = (fill_px - avg_cost) * fill_qty
                    if pnl >= 0:
                        wins += 1
                        gross_profit += pnl
                    else:
                        losses += 1
                        gross_loss += abs(pnl)
                    qty = max(0.0, qty - fill_qty)
                    if qty == 0:
                        avg_cost = 0.0
                total_fees += fee
                total_slip += fill_qty * slip
                trades.append({
                    "bar": i,
                    "side": side,
                    "qty": round(fill_qty, 6),
                    "price": round(fill_px, 6),
                    "fee": round(fee, 4),
                    "slippage": round(fill_qty * slip, 4),
                })

            mtm = cash + qty * px
            equity_curve.append(round(mtm, 4))
            peak = max(peak, mtm)
            dd = (peak - mtm) / peak if peak > 0 else 0.0
            drawdown_curve.append(round(dd, 6))

            # monthly/yearly buckets (bar index as proxy calendar)
            month_key = f"M{(i // 21) % 12 + 1:02d}"
            year_key = f"Y{2020 + i // 252}"
            if i > 25:
                prev = equity_curve[-2] if len(equity_curve) > 1 else capital
                day_ret = (mtm / prev - 1.0) if prev else 0.0
                monthly[month_key] = monthly.get(month_key, 0.0) + day_ret
                yearly[year_key] = yearly.get(year_key, 0.0) + day_ret

        final = equity_curve[-1] if equity_curve else capital
        total_return = (final / capital) - 1.0 if capital else 0.0
        rets = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]
            if prev:
                rets.append(equity_curve[i] / prev - 1.0)
        vol = (sum(r * r for r in rets) / len(rets)) ** 0.5 * math.sqrt(252) if rets else 0.0
        mean_d = sum(rets) / len(rets) if rets else 0.0
        sharpe = (mean_d * 252) / vol if vol > 0 else 0.0
        max_dd = max(drawdown_curve) if drawdown_curve else 0.0
        n_trades = len(trades)
        win_rate = wins / (wins + losses) if (wins + losses) else 0.0
        avg_win = gross_profit / wins if wins else 0.0
        avg_loss = gross_loss / losses if losses else 0.0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

        # Benchmark buy & hold
        bh_final = capital * (closes[-1] / closes[25]) if closes[25] else capital
        bh_return = (bh_final / capital) - 1.0

        # Attribution
        attribution = {
            "gross_pnl": round(final - capital + total_fees + total_slip, 4),
            "fees": round(-total_fees, 4),
            "slippage": round(-total_slip, 4),
            "net_pnl": round(final - capital, 4),
            "benchmark_excess": round(total_return - bh_return, 6),
        }

        result = {
            "ok": True,
            "engine": "backtest_v2",
            "strategy_id": strategy_id,
            "seed": seed,
            "bars": len(bars),
            "capital": capital,
            "final_equity": round(final, 4),
            "total_return": round(total_return, 6),
            "volatility": round(vol, 6),
            "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 6),
            "equity_curve": equity_curve,
            "drawdown_curve": drawdown_curve,
            "monthly_returns": {k: round(v, 6) for k, v in monthly.items()},
            "yearly_returns": {k: round(v, 6) for k, v in yearly.items()},
            "win_rate": round(win_rate, 4),
            "expectancy": round(expectancy, 4),
            "profit_factor": round(min(profit_factor, 999.0), 4),
            "n_trades": n_trades,
            "costs": {
                "commission_bps": commission_bps,
                "slippage_bps": slippage_bps,
                "total_fees": round(total_fees, 4),
                "total_slippage": round(total_slip, 4),
                "liquidity_participation": liquidity_participation,
                "partial_fills": partial_fill,
            },
            "capital_limits": {"starting": capital, "no_leverage": True, "no_margin": True},
            "benchmark": {
                "name": benchmark,
                "return": round(bh_return, 6),
                "final_equity": round(bh_final, 4),
            },
            "performance_attribution": attribution,
            "trades_sample": trades[:20],
            "deterministic": True,
            "evidence_hash": hashlib.sha256(
                f"{strategy_id}:{seed}:{len(bars)}:{final:.4f}".encode()
            ).hexdigest(),
            **AUTHORITY_VALUES,
        }
        return result

    def compare(self, strategy_ids: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        ids = strategy_ids or ["tf_dual_ma", "mr_bollinger_reversion", "bo_donchian", "mom_rs_equity"]
        results = {}
        for sid in ids:
            results[sid] = self.run(sid, **kwargs)
        ranking = sorted(
            ids,
            key=lambda s: (results[s].get("sharpe", 0), results[s].get("total_return", 0)),
            reverse=True,
        )
        return {
            "strategies": ids,
            "results": results,
            "ranking": ranking,
            "disclaimer": "Simulated comparison only. Not future performance.",
            **AUTHORITY_VALUES,
        }
