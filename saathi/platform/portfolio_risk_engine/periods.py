"""UTC day/week boundaries for loss budgets (fail closed if undefined)."""
from __future__ import annotations

import time as _time
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Iterable

from saathi.platform.fund_ledger.money import D, q_money


def utc_day_start(ts: float | None = None) -> float:
    t = datetime.fromtimestamp(ts if ts is not None else _time.time(), tz=timezone.utc)
    start = datetime(t.year, t.month, t.day, tzinfo=timezone.utc)
    return start.timestamp()


def utc_week_start(ts: float | None = None) -> float:
    """ISO week: Monday 00:00 UTC."""
    t = datetime.fromtimestamp(ts if ts is not None else _time.time(), tz=timezone.utc)
    monday = t - timedelta(days=t.weekday())
    start = datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc)
    return start.timestamp()


def period_pnl(
    nav_series: Iterable[tuple[float, Decimal | str]],
    *,
    period_start: float,
    current_nav: Decimal,
) -> dict:
    """Loss/gain vs first NAV at or before period_start; if none, DATA_INSUFFICIENT."""
    series = sorted(((float(ts), D(nav)) for ts, nav in nav_series), key=lambda x: x[0])
    baseline = None
    for ts, nav in series:
        if ts <= period_start:
            baseline = nav
        elif baseline is None and ts >= period_start:
            baseline = nav
            break
    if baseline is None:
        # try first point in period
        for ts, nav in series:
            if ts >= period_start:
                baseline = nav
                break
    if baseline is None:
        return {
            "ok": False,
            "reason": "DATA_INSUFFICIENT",
            "period_start": period_start,
            "pnl": None,
            "pnl_pct": None,
            "baseline_nav": None,
        }
    pnl = q_money(current_nav - baseline)
    pnl_pct = q_money(pnl / baseline) if baseline != 0 else Decimal("0")
    return {
        "ok": True,
        "period_start": period_start,
        "pnl": str(pnl),
        "pnl_pct": str(pnl_pct),
        "baseline_nav": str(q_money(baseline)),
        "current_nav": str(q_money(current_nav)),
    }
