"""ATTRIBUTION-V2 — multi-dimension performance attribution over REAL records.

Answers "what produced the return?" across the dimensions the program actually
trades: strategy, asset, venue, benchmark, cost drag, drawdown, and the outcomes
Guardian prevented.

Distinct from the existing research `PerformanceAttribution` (Brinson-lite over
SYNTHETIC return series, labelled research-only): this operates strictly on
supplied realized/shadow records and never fabricates a return. If a dimension is
not observable, it is reported as DATA_INSUFFICIENT rather than silently zero.

Deterministic Decimal arithmetic. Read-only: attribution explains, it never sizes,
approves, or executes.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class AttributionStatus(str, Enum):
    OK = "OK"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


LABEL = "RESEARCH_ATTRIBUTION_NOT_OFFICIAL_GIPS"


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


@dataclass(frozen=True)
class AttributionRecord:
    """One realized (or shadow) outcome attributable to a decision."""

    strategy_id: str
    symbol: str
    venue: str
    asset_class: str
    gross_pnl: Decimal
    cost: Decimal
    benchmark_pnl: Decimal | None = None
    guardian_blocked: bool = False

    @property
    def net_pnl(self) -> Decimal:
        return self.gross_pnl - self.cost


def _group(records, key) -> dict:
    out: dict[str, dict] = {}
    for r in records:
        k = getattr(r, key)
        bucket = out.setdefault(k, {"gross": Decimal("0"), "cost": Decimal("0"), "net": Decimal("0"), "count": 0})
        bucket["gross"] += r.gross_pnl
        bucket["cost"] += r.cost
        bucket["net"] += r.net_pnl
        bucket["count"] += 1
    return out


def max_drawdown(equity_path) -> Decimal:
    """Max peak-to-trough drawdown of a cumulative equity path."""
    peak = None
    worst = Decimal("0")
    for v in equity_path:
        x = _dec(v)
        peak = x if peak is None else max(peak, x)
        worst = max(worst, peak - x)
    return worst


def attribute(records, *, equity_path=None) -> dict:
    """Attribute realized performance across every observable dimension."""
    records = list(records)
    executed = [r for r in records if not r.guardian_blocked]
    blocked = [r for r in records if r.guardian_blocked]

    if not records:
        return {
            "status": AttributionStatus.DATA_INSUFFICIENT.value,
            "label": LABEL,
            "detail": "no attribution records supplied",
        }

    gross = sum((r.gross_pnl for r in executed), Decimal("0"))
    cost = sum((r.cost for r in executed), Decimal("0"))
    net = gross - cost

    # Benchmark contribution is only reported when every executed record has one —
    # a partial benchmark would misattribute the remainder to skill.
    if executed and all(r.benchmark_pnl is not None for r in executed):
        benchmark = sum((r.benchmark_pnl for r in executed), Decimal("0"))
        excess = net - benchmark
        benchmark_status = AttributionStatus.OK.value
    else:
        benchmark = None
        excess = None
        benchmark_status = AttributionStatus.DATA_INSUFFICIENT.value

    return {
        "status": AttributionStatus.OK.value,
        "label": LABEL,
        "totals": {
            "gross_pnl": gross,
            "cost_drag": cost,
            "net_pnl": net,
            "records": len(executed),
        },
        "by_strategy": _group(executed, "strategy_id"),
        "by_asset": _group(executed, "symbol"),
        "by_venue": _group(executed, "venue"),
        "by_asset_class": _group(executed, "asset_class"),
        "benchmark": {
            "status": benchmark_status,
            "benchmark_pnl": benchmark,
            "excess_vs_benchmark": excess,
        },
        "guardian": {
            "blocked_count": len(blocked),
            "blocked_symbols": sorted({r.symbol for r in blocked}),
            "note": "blocked decisions produced no exposure; their PnL is not claimed",
        },
        "risk": {
            "max_drawdown": max_drawdown(equity_path) if equity_path else None,
            "status": (
                AttributionStatus.OK.value if equity_path else AttributionStatus.DATA_INSUFFICIENT.value
            ),
        },
        "authorizes_execution": False,
    }


def reconciles(result: dict) -> bool:
    """Contributions must sum to the reported net — attribution never leaks PnL."""
    if result.get("status") != AttributionStatus.OK.value:
        return False
    net = result["totals"]["net_pnl"]
    for dimension in ("by_strategy", "by_asset", "by_venue", "by_asset_class"):
        total = sum((b["net"] for b in result[dimension].values()), Decimal("0"))
        if total != net:
            return False
    return True
