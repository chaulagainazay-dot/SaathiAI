"""Canonical paper drawdown from NAV history."""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from saathi.platform.fund_ledger.money import D, q_money


def compute_drawdown(nav_series: Iterable[tuple[float, Decimal | str]]) -> dict:
    """nav_series: list of (ts, nav) ascending.

    Returns current_drawdown, max_drawdown, peak_nav, current_nav.
    Drawdown = (peak - nav) / peak when peak > 0.
    """
    peak = Decimal("0")
    max_dd = Decimal("0")
    current = Decimal("0")
    current_dd = Decimal("0")
    peak_ts = 0.0
    points = list(nav_series)
    if not points:
        return {
            "current_nav": "0.00",
            "peak_nav": "0.00",
            "current_drawdown": "0.00",
            "max_drawdown": "0.00",
            "peak_ts": None,
            "observations": 0,
        }
    for ts, nav in points:
        n = D(nav)
        current = n
        if n > peak:
            peak = n
            peak_ts = float(ts)
        if peak > 0:
            dd = (peak - n) / peak
            if dd > max_dd:
                max_dd = dd
            current_dd = dd
    return {
        "current_nav": str(q_money(current)),
        "peak_nav": str(q_money(peak)),
        "current_drawdown": str(q_money(current_dd)),
        "max_drawdown": str(q_money(max_dd)),
        "peak_ts": peak_ts,
        "observations": len(points),
    }
