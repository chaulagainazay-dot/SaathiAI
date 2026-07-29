"""M189 — Bounded Monte Carlo and statistical robustness.

Does not invent alternative market histories without labeling.
Trade-sequence reshuffling, block bootstrap, cost perturbation only.
Bounded for 8 GB RAM class machines.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


# Hard bounds for 8 GB class
MAX_SIMULATIONS = 500
DEFAULT_SIMULATIONS = 200
MAX_TRADES_IN_MC = 5000


class MonteCarloVerdict(str, Enum):
    STABLE = "STABLE"
    ACCEPTABLE_WITH_LIMITS = "ACCEPTABLE_WITH_LIMITS"
    TAIL_RISK_HIGH = "TAIL_RISK_HIGH"
    RISK_OF_RUIN_UNACCEPTABLE = "RISK_OF_RUIN_UNACCEPTABLE"
    INSUFFICIENT_TRADES = "INSUFFICIENT_TRADES"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass
class MonteCarloConfig:
    n_simulations: int = DEFAULT_SIMULATIONS
    seed: int = 42
    block_size: int = 5
    methods: list[str] = field(default_factory=lambda: [
        "trade_sequence_shuffle",
        "block_bootstrap",
        "return_resample",
        "slippage_perturbation",
        "fee_perturbation",
        "missed_trade",
        "delayed_entry",
        "gap_through_stop",
        "partial_fill",
    ])
    daily_loss_limit: float = 0.03
    weekly_loss_limit: float = 0.08
    drawdown_ceiling: float = 0.25
    ruin_threshold: float = 0.50  # equity drawdown defining "ruin" under paper assumptions
    initial_equity: float = 100_000.0


def _rng(seed: int):
    """Deterministic float stream in [0, 1)."""
    i = 0
    while True:
        h = hashlib.sha256(f"mc:{seed}:{i}".encode()).hexdigest()
        yield int(h[:12], 16) / float(0xFFFFFFFFFFFF)
        i += 1


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if p <= 0:
        return sorted_vals[0]
    if p >= 100:
        return sorted_vals[-1]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def _equity_path(returns: list[float], initial: float = 100_000.0) -> tuple[float, float, list[float]]:
    """Return final equity, max drawdown, equity series."""
    eq = initial
    peak = initial
    max_dd = 0.0
    series = [eq]
    for r in returns:
        eq *= (1.0 + r)
        peak = max(peak, eq)
        dd = (peak - eq) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
        series.append(eq)
    total_ret = (eq / initial) - 1.0 if initial else 0.0
    return total_ret, max_dd, series


def _loss_streak(returns: list[float]) -> int:
    best = cur = 0
    for r in returns:
        if r < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def extract_trade_returns(backtest_result: dict[str, Any] | None, fills: list[Any] | None = None) -> list[float]:
    """Extract per-trade simple returns from engine result or fill list."""
    rets: list[float] = []
    if fills:
        # pair-wise PnL heuristic not always available; use fill notional deltas if present
        for f in fills:
            if isinstance(f, dict):
                if "pnl" in f:
                    notional = float(f.get("notional") or f.get("qty", 1) or 1)
                    if notional:
                        rets.append(float(f["pnl"]) / abs(float(notional)))
                elif "return" in f:
                    rets.append(float(f["return"]))
    if rets:
        return rets[:MAX_TRADES_IN_MC]

    # Fall back to metrics-derived synthetic trade returns (labeled)
    if backtest_result:
        m = backtest_result.get("metrics") or {}
        n = int(m.get("number_of_trades") or m.get("trade_count") or 0)
        total = float(m.get("total_return") or 0)
        if n <= 0:
            return []
        # equal-split approximation — labeled as synthetic decomposition
        base = total / n
        # mild variation for robustness exercises
        for i in range(min(n, MAX_TRADES_IN_MC)):
            rets.append(base * (1.0 + 0.1 * math.sin(i)))
    return rets


def run_monte_carlo(
    trade_returns: list[float] | None = None,
    *,
    backtest_result: dict[str, Any] | None = None,
    fills: list[Any] | None = None,
    config: MonteCarloConfig | None = None,
    label_synthetic_decomposition: bool = False,
) -> dict[str, Any]:
    cfg = config or MonteCarloConfig()
    n_sim = max(1, min(int(cfg.n_simulations), MAX_SIMULATIONS))
    rets = list(trade_returns or extract_trade_returns(backtest_result, fills))
    if len(rets) < 5:
        return {
            "status": "COMPLETE",
            "monte_carlo_verdict": MonteCarloVerdict.INSUFFICIENT_TRADES.value,
            "simulation_count": 0,
            "seed": cfg.seed,
            "trade_count": len(rets),
            "paper_only": True,
            "methods": list(cfg.methods),
            "disclaimer": "Insufficient trades for Monte Carlo. Not evidence of robustness.",
        }

    stream = _rng(cfg.seed)
    final_returns: list[float] = []
    max_drawdowns: list[float] = []
    loss_streaks: list[int] = []
    ruin_flags: list[int] = []
    daily_breach: list[int] = []
    weekly_breach: list[int] = []
    dd_ceiling_breach: list[int] = []
    recovery_durs: list[int] = []
    cost_sensitivity: list[float] = []

    n = len(rets)
    block = max(1, min(cfg.block_size, n))

    for sim in range(n_sim):
        method = cfg.methods[sim % len(cfg.methods)]
        seq = list(rets)

        if method == "trade_sequence_shuffle":
            # Fisher-Yates with deterministic stream
            for i in range(n - 1, 0, -1):
                j = int(next(stream) * (i + 1))
                seq[i], seq[j] = seq[j], seq[i]
        elif method == "block_bootstrap":
            out: list[float] = []
            while len(out) < n:
                start = int(next(stream) * max(1, n - block + 1))
                out.extend(seq[start:start + block])
            seq = out[:n]
        elif method == "return_resample":
            seq = [seq[int(next(stream) * n)] for _ in range(n)]
        elif method == "slippage_perturbation":
            # haircut each return by 5–20 bps deterministically
            slip = 0.0005 + 0.0015 * next(stream)
            seq = [r - slip for r in seq]
            cost_sensitivity.append(slip)
        elif method == "fee_perturbation":
            fee = 0.0002 + 0.0008 * next(stream)
            seq = [r - fee for r in seq]
            cost_sensitivity.append(fee)
        elif method == "missed_trade":
            # drop ~10% of trades
            seq = [r for i, r in enumerate(seq) if next(stream) > 0.10]
            if not seq:
                seq = list(rets)
        elif method == "delayed_entry":
            # shift returns by 1 (miss first)
            seq = seq[1:] + [0.0]
        elif method == "gap_through_stop":
            # amplify worst 10% losses
            thr = sorted(seq)[max(0, int(0.1 * n) - 1)]
            seq = [r * 1.5 if r <= thr else r for r in seq]
        elif method == "partial_fill":
            seq = [r * (0.5 + 0.5 * next(stream)) for r in seq]
        else:
            # labeled unknown method — identity
            pass

        total_ret, max_dd, series = _equity_path(seq, cfg.initial_equity)
        final_returns.append(total_ret)
        max_drawdowns.append(max_dd)
        loss_streaks.append(_loss_streak(seq))
        ruin_flags.append(1 if max_dd >= cfg.ruin_threshold else 0)
        dd_ceiling_breach.append(1 if max_dd >= cfg.drawdown_ceiling else 0)

        # approximate daily/weekly breach from sequential chunks
        daily_hit = weekly_hit = 0
        chunk = max(1, n // 20)
        for i in range(0, n, chunk):
            chunk_ret = 1.0
            for r in seq[i:i + chunk]:
                chunk_ret *= (1.0 + r)
            chunk_ret -= 1.0
            if chunk_ret <= -cfg.daily_loss_limit:
                daily_hit = 1
            if chunk_ret <= -cfg.weekly_loss_limit:
                weekly_hit = 1
        daily_breach.append(daily_hit)
        weekly_breach.append(weekly_hit)

        # recovery duration: bars from peak to new high after max dd trough
        peak_i = 0
        trough_i = 0
        peak_v = series[0]
        for i, v in enumerate(series):
            if v >= peak_v:
                peak_v = v
                peak_i = i
            if peak_v > 0 and (peak_v - v) / peak_v >= max_dd - 1e-12:
                trough_i = i
        rec = 0
        for i in range(trough_i, len(series)):
            if series[i] >= peak_v:
                rec = i - trough_i
                break
        else:
            rec = len(series) - trough_i
        recovery_durs.append(rec)

    final_returns.sort()
    max_drawdowns.sort()
    loss_streaks_sorted = sorted(loss_streaks)
    recovery_durs.sort()

    risk_of_ruin = sum(ruin_flags) / n_sim
    p_daily = sum(daily_breach) / n_sim
    p_weekly = sum(weekly_breach) / n_sim
    p_dd = sum(dd_ceiling_breach) / n_sim
    median_ret = _percentile(final_returns, 50)
    p05 = _percentile(final_returns, 5)
    p95 = _percentile(final_returns, 95)
    median_dd = _percentile(max_drawdowns, 50)
    worst_dd = _percentile(max_drawdowns, 95)
    p_long_streak = sum(1 for s in loss_streaks if s >= 5) / n_sim

    # Verdict — tail risk required; average alone cannot qualify
    if risk_of_ruin >= 0.10:
        verdict = MonteCarloVerdict.RISK_OF_RUIN_UNACCEPTABLE
    elif worst_dd >= 0.40 or p_dd >= 0.35:
        verdict = MonteCarloVerdict.TAIL_RISK_HIGH
    elif p05 < -0.30 or p_long_streak >= 0.40:
        verdict = MonteCarloVerdict.TAIL_RISK_HIGH
    elif worst_dd <= cfg.drawdown_ceiling and risk_of_ruin < 0.02 and p05 > -0.20:
        verdict = MonteCarloVerdict.STABLE
    else:
        verdict = MonteCarloVerdict.ACCEPTABLE_WITH_LIMITS

    return {
        "status": "COMPLETE",
        "monte_carlo_verdict": verdict.value,
        "simulation_count": n_sim,
        "seed": cfg.seed,
        "trade_count": n,
        "methods": list(cfg.methods),
        "median_return": str(round(median_ret, 6)),
        "return_p05": str(round(p05, 6)),
        "return_p95": str(round(p95, 6)),
        "median_drawdown": str(round(median_dd, 6)),
        "worst_percentile_drawdown": str(round(worst_dd, 6)),
        "risk_of_ruin": str(round(risk_of_ruin, 6)),
        "probability_daily_loss_limit_breach": str(round(p_daily, 6)),
        "probability_weekly_loss_limit_breach": str(round(p_weekly, 6)),
        "probability_drawdown_ceiling_breach": str(round(p_dd, 6)),
        "probability_long_loss_streak": str(round(p_long_streak, 6)),
        "loss_streak_p50": loss_streaks_sorted[len(loss_streaks_sorted) // 2] if loss_streaks_sorted else 0,
        "loss_streak_p95": loss_streaks_sorted[int(0.95 * (len(loss_streaks_sorted) - 1))] if loss_streaks_sorted else 0,
        "recovery_duration_p50": recovery_durs[len(recovery_durs) // 2] if recovery_durs else 0,
        "recovery_duration_p95": recovery_durs[int(0.95 * (len(recovery_durs) - 1))] if recovery_durs else 0,
        "cost_sensitivity_mean_haircut": str(round(sum(cost_sensitivity) / len(cost_sensitivity), 6)) if cost_sensitivity else "0",
        "bounds": {
            "max_simulations": MAX_SIMULATIONS,
            "applied_simulations": n_sim,
            "max_trades": MAX_TRADES_IN_MC,
            "target_machine": "8GB_RAM_class",
        },
        "assumptions": {
            "daily_loss_limit": cfg.daily_loss_limit,
            "weekly_loss_limit": cfg.weekly_loss_limit,
            "drawdown_ceiling": cfg.drawdown_ceiling,
            "ruin_threshold": cfg.ruin_threshold,
            "initial_equity_simulated": cfg.initial_equity,
            "synthetic_trade_decomposition": label_synthetic_decomposition or (
                trade_returns is None and not fills
            ),
        },
        "paper_only": True,
        "live_authorized": False,
        "invented_market_history": False,
        "disclaimer": (
            "Monte Carlo reshuffles or stresses observed trade returns; it does not "
            "create alternative real market histories. Tail risk is required for qualification. "
            "Paper assumptions only — not live trading."
        ),
    }
