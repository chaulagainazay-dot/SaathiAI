"""Multi-symbol comparison read model — descriptive, THIRD_PARTY, ≤4 symbols.

Deterministic date-intersection alignment (no silent forward-fill). Default mode is
NORMALIZED_PERCENT so differently-priced stocks compare fairly. Not a ranking or a
recommendation.
"""
from __future__ import annotations

from decimal import Decimal

from saathi.platform.market_data.tracker.models import (
    ComparisonSeries, MultiSymbolComparison, TrackerStatus,
)
from saathi.platform.market_data.tracker.provider import get_provider

MAX_SYMBOLS = 4
NORMALIZED = "NORMALIZED_PERCENT"
ABSOLUTE = "ABSOLUTE"


def build_comparison(symbols, range_: str = "1Y", *, mode: str = NORMALIZED, provider=None
                     ) -> MultiSymbolComparison:
    provider = provider or get_provider()
    syms = [str(s).upper() for s in symbols][:MAX_SYMBOLS]
    mode = mode if mode in (NORMALIZED, ABSOLUTE) else NORMALIZED
    limitations: list[str] = []
    if len(symbols) > MAX_SYMBOLS:
        limitations.append(f"limited to first {MAX_SYMBOLS} symbols (M2/8GB clarity bound)")

    per: dict[str, dict[str, Decimal]] = {}
    for s in syms:
        series, st = provider.market_history(s, range_)
        if series is None:
            limitations.append(f"{s} unavailable ({st.value})")
            continue
        per[s] = {p.business_date: p.close for p in series.points}

    available = [s for s in syms if s in per]
    if len(available) < 2:
        return MultiSymbolComparison(tuple(syms), range_, mode, None, None,
                                     limitations=tuple(limitations + ["need >=2 available symbols"]))
    # intersection of trading dates (no forward-fill)
    common = set.intersection(*(set(per[s]) for s in available))
    if not common:
        return MultiSymbolComparison(tuple(available), range_, mode, None, None,
                                     limitations=tuple(limitations + ["no overlapping trading dates"]))
    dates = sorted(common)
    start, end = dates[0], dates[-1]
    for s in available:
        dropped = len(per[s]) - len(dates)
        if dropped > 0:
            limitations.append(f"{s}: {dropped} non-overlapping date(s) excluded")

    out_series = []
    for s in available:
        closes = [per[s][d] for d in dates]
        first, last = closes[0], closes[-1]
        if mode == NORMALIZED:
            pts = tuple((d, (c / first - 1) * 100 if first else None) for d, c in zip(dates, closes))
        else:
            pts = tuple((d, c) for d, c in zip(dates, closes))
        chg = ((last / first - 1) * 100).quantize(Decimal("0.01")) if first else None
        out_series.append(ComparisonSeries(symbol=s, first_close=first, last_close=last,
                                            change_pct=chg, points=pts))
    return MultiSymbolComparison(tuple(available), range_, mode, start, end,
                                 series=tuple(out_series), limitations=tuple(limitations))
