"""M252 — Monte Carlo Risk Engine.

Repeatable random-return simulations: sequence risk, ruin, targets, recovery.
Paper only. Deterministic given seed.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

from saathi.platform.tg.intelligence.models import AUTHORITY_VALUES

MAX_SIMULATIONS = 2000
DEFAULT_SIMULATIONS = 500


def _rng(seed: int):
    i = 0
    while True:
        h = hashlib.sha256(f"ii-mc:{seed}:{i}".encode()).hexdigest()
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


class MonteCarloRiskEngine:
    """Institutional Monte Carlo risk simulations (offline, seedable)."""

    def simulate(
        self,
        returns: list[float] | None = None,
        *,
        n_simulations: int = DEFAULT_SIMULATIONS,
        horizon: int = 60,
        seed: int = 42,
        initial_equity: float = 100_000.0,
        ruin_threshold: float = 0.50,
        target_return: float = 0.10,
        block_size: int = 5,
    ) -> dict[str, Any]:
        n_simulations = max(1, min(int(n_simulations), MAX_SIMULATIONS))
        if not returns:
            # default mild positive paper returns
            returns = self._default_returns(seed=seed)
        returns = [float(r) for r in returns]
        if len(returns) < 5:
            return {
                "ok": False,
                "code": "INSUFFICIENT_RETURNS",
                **AUTHORITY_VALUES,
            }

        rng = _rng(seed)
        final_returns: list[float] = []
        max_drawdowns: list[float] = []
        ruin_flags: list[bool] = []
        target_flags: list[bool] = []
        recovery_days: list[float] = []
        worst_paths: list[dict[str, Any]] = []

        for sim in range(n_simulations):
            path = self._block_bootstrap(returns, horizon, block_size, rng)
            tot, mdd, series, rec = self._path_stats(path, initial_equity, ruin_threshold)
            final_returns.append(tot)
            max_drawdowns.append(mdd)
            ruined = mdd >= ruin_threshold or (series[-1] / initial_equity - 1) <= -ruin_threshold
            ruin_flags.append(ruined)
            target_flags.append(tot >= target_return)
            recovery_days.append(rec)
            if sim < 5 or mdd > 0.3:
                worst_paths.append({
                    "sim": sim,
                    "total_return": round(tot, 6),
                    "max_drawdown": round(mdd, 6),
                    "final_equity": round(series[-1], 4),
                })

        final_returns.sort()
        max_drawdowns.sort()
        worst_paths = sorted(worst_paths, key=lambda x: x["max_drawdown"], reverse=True)[:10]

        p_ruin = sum(1 for x in ruin_flags if x) / n_simulations
        p_target = sum(1 for x in target_flags if x) / n_simulations
        mean_rec = sum(recovery_days) / len(recovery_days) if recovery_days else 0.0

        result = {
            "ok": True,
            "engine": "monte_carlo_v1",
            "n_simulations": n_simulations,
            "horizon_bars": horizon,
            "seed": seed,
            "initial_equity": initial_equity,
            "block_size": block_size,
            "method": "block_bootstrap_return_resample",
            "repeatable": True,
            "probability_of_ruin": round(p_ruin, 6),
            "probability_of_target_return": round(p_target, 6),
            "target_return": target_return,
            "ruin_threshold": ruin_threshold,
            "sequence_risk": {
                "mean_max_drawdown": round(sum(max_drawdowns) / len(max_drawdowns), 6),
                "p95_max_drawdown": round(_percentile(max_drawdowns, 95), 6),
                "p99_max_drawdown": round(_percentile(max_drawdowns, 99), 6),
                "note": "Order of returns materially affects path outcomes (sequence risk).",
            },
            "return_distribution": {
                "p5": round(_percentile(final_returns, 5), 6),
                "p25": round(_percentile(final_returns, 25), 6),
                "p50": round(_percentile(final_returns, 50), 6),
                "p75": round(_percentile(final_returns, 75), 6),
                "p95": round(_percentile(final_returns, 95), 6),
                "mean": round(sum(final_returns) / len(final_returns), 6),
            },
            "confidence_intervals": {
                "return_90": [
                    round(_percentile(final_returns, 5), 6),
                    round(_percentile(final_returns, 95), 6),
                ],
                "return_95": [
                    round(_percentile(final_returns, 2.5), 6),
                    round(_percentile(final_returns, 97.5), 6),
                ],
                "drawdown_90": [
                    round(_percentile(max_drawdowns, 5), 6),
                    round(_percentile(max_drawdowns, 95), 6),
                ],
            },
            "worst_case_scenarios": worst_paths,
            "recovery_analysis": {
                "mean_bars_to_recover_or_horizon": round(mean_rec, 2),
                "note": "Bars until equity recovers peak after first 10% DD, else horizon.",
            },
            "evidence_hash": hashlib.sha256(
                f"mc:{seed}:{n_simulations}:{horizon}:{p_ruin:.6f}:{p_target:.6f}".encode()
            ).hexdigest(),
            **AUTHORITY_VALUES,
        }
        return result

    def _default_returns(self, seed: int = 42, n: int = 80) -> list[float]:
        rng = _rng(seed)
        out = []
        for _ in range(n):
            u = next(rng)
            out.append(0.0005 + (u - 0.5) * 0.02)
        return out

    def _block_bootstrap(
        self,
        returns: list[float],
        horizon: int,
        block_size: int,
        rng,
    ) -> list[float]:
        n = len(returns)
        path: list[float] = []
        while len(path) < horizon:
            start = int(next(rng) * max(1, n - block_size + 1))
            block = returns[start : start + block_size]
            if not block:
                block = [returns[int(next(rng) * n)]]
            path.extend(block)
        return path[:horizon]

    def _path_stats(
        self,
        rets: list[float],
        initial: float,
        ruin_threshold: float,
    ) -> tuple[float, float, list[float], float]:
        eq = initial
        peak = initial
        max_dd = 0.0
        series = [eq]
        recover_at = float(len(rets))
        saw_dd = False
        for i, r in enumerate(rets):
            eq *= 1.0 + r
            peak = max(peak, eq)
            dd = (peak - eq) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
            if not saw_dd and dd >= 0.10:
                saw_dd = True
            if saw_dd and eq >= peak * 0.999 and recover_at == float(len(rets)):
                recover_at = float(i)
            series.append(eq)
        total = (eq / initial) - 1.0 if initial else 0.0
        return total, max_dd, series, recover_at
