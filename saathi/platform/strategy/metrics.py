"""M62.4 — performance metrics with explicit sample sufficiency.

Every metric is returned as a ``Metric`` carrying value + status + required sample
size + warnings + a calculation version. Zero denominators and thin samples are
handled explicitly: we return status ``INSUFFICIENT`` / ``UNDEFINED`` rather than
``inf`` or a misleading number. Decimal for money-scale values; ratios use Decimal
too for determinism.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from saathi.platform.strategy.models import EquityPoint, SimulatedOrder, SimOrderStatus, D, q2

METRICS_VERSION = "m62_4.metrics.v1"

# annualization: periods-per-year by timeframe (bars). Daily default.
PERIODS_PER_YEAR = {"1d": Decimal("252"), "1h": Decimal("1638"), "15m": Decimal("6552"),
                    "5m": Decimal("19656"), "1m": Decimal("98280")}


class MetricStatus(str):
    OK = "OK"
    INSUFFICIENT = "INSUFFICIENT_SAMPLE"
    UNDEFINED = "UNDEFINED"


@dataclass
class Metric:
    name: str
    value: Decimal | None
    status: str
    required_samples: int = 0
    observed_samples: int = 0
    warnings: list[str] = field(default_factory=list)
    version: str = METRICS_VERSION

    def to_public(self) -> dict[str, Any]:
        return {"name": self.name, "value": (str(self.value) if self.value is not None else None),
                "status": self.status, "required_samples": self.required_samples,
                "observed_samples": self.observed_samples, "warnings": self.warnings, "version": self.version}


def _sqrt(x: Decimal) -> Decimal:
    return x.sqrt() if x > 0 else Decimal("0")


def _returns(curve: list[EquityPoint]) -> list[Decimal]:
    rets = []
    for i in range(1, len(curve)):
        prev = curve[i - 1].equity
        if prev == 0:
            continue
        rets.append((curve[i].equity - prev) / prev)
    return rets


def _mean(xs: list[Decimal]) -> Decimal:
    return sum(xs) / Decimal(len(xs)) if xs else Decimal("0")


def _std(xs: list[Decimal]) -> Decimal:
    if len(xs) < 2:
        return Decimal("0")
    m = _mean(xs)
    var = sum((x - m) ** 2 for x in xs) / Decimal(len(xs) - 1)
    return _sqrt(var)


def compute_metrics(
    curve: list[EquityPoint],
    fills: list[SimulatedOrder],
    *,
    timeframe: str = "1d",
    starting_cash: Decimal,
    total_fees: Decimal,
    total_slippage_cost: Decimal,
    turnover: Decimal,
    benchmark_return: Decimal | None = None,
    min_observations: int = 20,
    min_trades: int = 5,
) -> dict[str, Metric]:
    out: dict[str, Metric] = {}
    n = len(curve)
    rets = _returns(curve)
    ppy = PERIODS_PER_YEAR.get(timeframe, Decimal("252"))

    def put(name, value, status=MetricStatus.OK, req=0, warns=None):
        out[name] = Metric(name=name, value=(q2(value) if isinstance(value, Decimal) and value is not None else value),
                           status=status, required_samples=req, observed_samples=n, warnings=warns or [])

    put("number_of_observations", Decimal(n), MetricStatus.OK)

    if n < 2:
        for m in ("total_return", "annualized_return", "annualized_volatility", "sharpe_ratio",
                  "sortino_ratio", "max_drawdown", "calmar_ratio"):
            put(m, None, MetricStatus.INSUFFICIENT, req=min_observations)
    else:
        start_eq, end_eq = curve[0].equity, curve[-1].equity
        total_ret = (end_eq - start_eq) / start_eq if start_eq else Decimal("0")
        put("total_return", total_ret, req=min_observations if n < min_observations else 0,
            warns=["thin sample"] if n < min_observations else None)

        mean_r, std_r = _mean(rets), _std(rets)
        ann_ret = mean_r * ppy
        ann_vol = std_r * _sqrt(ppy)
        put("annualized_return", ann_ret)
        put("annualized_volatility", ann_vol)

        if ann_vol == 0:
            put("sharpe_ratio", None, MetricStatus.UNDEFINED, warns=["zero volatility"])
        else:
            put("sharpe_ratio", ann_ret / ann_vol,
                MetricStatus.OK if n >= min_observations else MetricStatus.INSUFFICIENT, req=min_observations)

        downside = [r for r in rets if r < 0]
        dstd = _std(downside) * _sqrt(ppy) if len(downside) >= 2 else Decimal("0")
        if dstd == 0:
            put("sortino_ratio", None, MetricStatus.UNDEFINED, warns=["no downside variance"])
        else:
            put("sortino_ratio", ann_ret / dstd)

        max_dd = max((p.drawdown for p in curve), default=Decimal("0"))
        put("max_drawdown", max_dd)
        if max_dd == 0:
            put("calmar_ratio", None, MetricStatus.UNDEFINED, warns=["zero drawdown"])
        else:
            put("calmar_ratio", ann_ret / max_dd)

    # ── trade statistics ─────────────────────────────────────────────────
    closed = _trade_pnls(fills)
    wins = [p for p in closed if p > 0]
    losses = [p for p in closed if p < 0]
    tc = len(closed)
    put("trade_count", Decimal(tc), MetricStatus.OK if tc >= min_trades else MetricStatus.INSUFFICIENT, req=min_trades)
    out["trade_count"].observed_samples = tc

    if tc == 0:
        for m in ("win_rate", "loss_rate", "profit_factor", "expectancy", "average_win",
                  "average_loss", "largest_win", "largest_loss", "average_holding_period"):
            out[m] = Metric(name=m, value=None, status=MetricStatus.INSUFFICIENT,
                            required_samples=min_trades, observed_samples=0)
    else:
        put("win_rate", Decimal(len(wins)) / Decimal(tc)); out["win_rate"].observed_samples = tc
        put("loss_rate", Decimal(len(losses)) / Decimal(tc)); out["loss_rate"].observed_samples = tc
        gross_win = sum(wins, Decimal("0"))
        gross_loss = abs(sum(losses, Decimal("0")))
        if gross_loss == 0:
            out["profit_factor"] = Metric("profit_factor", None, MetricStatus.UNDEFINED, observed_samples=tc,
                                          warnings=["no losing trades"])
        else:
            put("profit_factor", gross_win / gross_loss); out["profit_factor"].observed_samples = tc
        put("expectancy", sum(closed, Decimal("0")) / Decimal(tc)); out["expectancy"].observed_samples = tc
        put("average_win", _mean(wins) if wins else Decimal("0")); out["average_win"].observed_samples = len(wins)
        put("average_loss", _mean(losses) if losses else Decimal("0")); out["average_loss"].observed_samples = len(losses)
        put("largest_win", max(wins) if wins else Decimal("0"))
        put("largest_loss", min(losses) if losses else Decimal("0"))
        put("average_holding_period", _avg_holding(fills)); out["average_holding_period"].observed_samples = tc

    # ── cost / exposure diagnostics ──────────────────────────────────────
    put("fee_impact", D(total_fees))
    put("slippage_impact", D(total_slippage_cost))
    put("turnover", D(turnover))
    if benchmark_return is not None and n >= 2:
        start_eq, end_eq = curve[0].equity, curve[-1].equity
        total_ret = (end_eq - start_eq) / start_eq if start_eq else Decimal("0")
        put("benchmark_return", D(benchmark_return))
        put("active_return", total_ret - D(benchmark_return))
    else:
        out["benchmark_return"] = Metric("benchmark_return", None, MetricStatus.INSUFFICIENT)
        out["active_return"] = Metric("active_return", None, MetricStatus.INSUFFICIENT)
    return out


def _trade_pnls(fills: list[SimulatedOrder]) -> list[Decimal]:
    """Reconstruct realized round-trip P&Ls (average-cost, long-only). A SELL closes
    against the running average buy cost."""
    pnls: list[Decimal] = []
    qty = Decimal("0")
    avg = Decimal("0")
    for f in fills:
        if f.status not in (SimOrderStatus.FILLED, SimOrderStatus.PARTIAL):
            continue
        q = D(f.quantity); px = D(f.fill_price); fee = D(f.fees)
        if f.side == "BUY":
            newq = qty + q
            if newq > 0:
                avg = ((avg * qty) + px * q) / newq
            qty = newq
        else:
            sq = min(q, qty)
            if sq > 0:
                pnls.append((px - avg) * sq - fee)
                qty -= sq
                if qty == 0:
                    avg = Decimal("0")
    return pnls


def _avg_holding(fills: list[SimulatedOrder]) -> Decimal:
    """Average bars held between a buy and its closing sell (FIFO on epochs)."""
    open_epochs: list[float] = []
    holds: list[float] = []
    for f in fills:
        if f.status not in (SimOrderStatus.FILLED, SimOrderStatus.PARTIAL):
            continue
        if f.side == "BUY":
            open_epochs.append(f.fill_epoch)
        elif open_epochs:
            entry = open_epochs.pop(0)
            holds.append(f.fill_epoch - entry)
    if not holds:
        return Decimal("0")
    return Decimal(str(sum(holds) / len(holds)))
