"""Chart-ready read model + cross-source reconciliation + chat/voice/catalyst consumers.

Backend contracts only (no UI HTML). Current-market authority stays with the official
NEPSE browser observation; the tracker supplies THIRD_PARTY historical/descriptive context.
"""
from __future__ import annotations

import re
import time
from decimal import Decimal

from saathi.platform.market_data.tracker import indicators as ind
from saathi.platform.market_data.tracker.models import (
    QuoteReconciliation, ReconVerdict, TrackerStatus,
)
from saathi.platform.market_data.tracker.provider import get_provider

_RECON_TOLERANCE = Decimal("0.005")   # 0.5% → CONFIRMED band


def _official_ltp(symbol: str):
    """Latest official observed LTP for a symbol (authoritative for current market)."""
    try:
        from saathi.platform.market_data.nepse_live_service import get_default_service
        snap = get_default_service().snapshot()
        if snap is None:
            return None, False   # official unavailable
        o = snap.get(symbol)
        return (o.ltp if o else None), True
    except Exception:
        return None, False


def reconcile_current(symbol: str, *, provider=None) -> QuoteReconciliation:
    """Official NEPSE (authority) vs tracker current LTP. Never overwrites; reports both."""
    provider = provider or get_provider()
    official, official_up = _official_ltp(symbol)
    tracker, st = provider.tracker_ltp(symbol)
    if official is None and official_up is False:
        v = ReconVerdict.OFFICIAL_UNAVAILABLE
    elif tracker is None:
        v = ReconVerdict.TRACKER_UNAVAILABLE
    elif official is None:
        v = ReconVerdict.OFFICIAL_UNAVAILABLE
    else:
        diff = abs(official - tracker)
        band = official * _RECON_TOLERANCE
        v = ReconVerdict.CONFIRMED if diff <= band else ReconVerdict.SOURCE_DISAGREEMENT
    diff = (official - tracker) if (official is not None and tracker is not None) else None
    note = {"CONFIRMED": "official and tracker agree",
            "SOURCE_DISAGREEMENT": "values differ; official NEPSE is authoritative for current LTP",
            "OFFICIAL_UNAVAILABLE": "no official observation cached; tracker shown as third-party only",
            "TRACKER_UNAVAILABLE": "tracker did not return a value",
            "TRACKER_STALE": "tracker value stale"}[v.value]
    return QuoteReconciliation(symbol=symbol, verdict=v, official_ltp=official,
                               tracker_ltp=tracker, difference=diff, note=note)


def build_chart_model(symbol: str, range_: str = "1Y", *, which_indicators=None,
                      provider=None, include_fundamentals: bool = True,
                      include_dividends: bool = True) -> dict:
    """MarketChartModel — reusable backend contract for a native SaathiOS chart."""
    provider = provider or get_provider()
    series, st = provider.market_history(symbol, range_)
    base = {"symbol": symbol.upper(), "range": range_,
            "source": "NEPSE_PORTFOLIO_TRACKER",
            "source_badge": "NEPSE Portfolio Tracker · Third-party historical",
            "current_market_authority": "OFFICIAL_PAGE_OBSERVED",
            "point_in_time_capability": "HISTORICAL_KNOWLEDGE_TIME_UNSUPPORTED",
            "status": st.value}
    if series is None:
        base["available"] = False
        base["limitations"] = ["history unavailable: " + st.value]
        return base
    computed = ind.compute_all(series, which=which_indicators)
    model = {**base, "available": True, "timeframe": series.timeframe,
             "freshness": series.freshness, "retrieved_at": series.retrieved_at,
             "first_date": series.first_date, "last_date": series.last_date,
             "latest_close": None if series.latest_close is None else str(series.latest_close),
             "n_points": len(series.points),
             "ohlc": [p.to_public() for p in series.points],
             "volume": [{"business_date": p.business_date, "volume": str(p.volume)} for p in series.points],
             "indicators": {k: v.to_public() for k, v in computed.items()},
             "indicators_kind": ind.KIND,
             "limitations": list(series.limitations) + [
                 "third-party series; not canonical MD-1; no look-ahead/backtest use"]}
    if include_fundamentals:
        f, fst = provider.fundamentals(symbol)
        model["fundamentals"] = f.to_public() if f else {"status": fst.value}
    if include_dividends:
        d, dst = provider.dividends(symbol)
        model["dividends"] = [x.to_public() for x in d] if d else []
        model["dividends_status"] = dst.value
    return model


# ── chat / voice (same read models; source always exposed) ─────────────────────
_SYM_RE = re.compile(r"\b([A-Z]{2,10}\d{0,4})\b")
_RANGE_WORDS = {"1d": "1D", "1 day": "1D", "1w": "1W", "1 week": "1W", "1m": "1M",
                "1 month": "1M", "3m": "3M", "3 month": "3M", "6m": "6M", "6 month": "6M",
                "1y": "1Y", "1 year": "1Y", "year": "1Y", "5y": "5Y", "5 year": "5Y"}


_STOPWORDS = {
    "RSI", "MACD", "PE", "PB", "EPS", "ATR", "SMA", "EMA", "SHOW", "WHAT", "THE", "TREND",
    "PRICE", "LATEST", "CURRENT", "NOW", "YEAR", "MONTH", "WEEK", "DAY", "DIVIDEND",
    "DIVIDENDS", "COMPARE", "AND", "OVER", "FOR", "IS", "OF", "OFFICIAL", "HISTORY",
    "CHART", "GIVE", "ME", "MY", "TO", "VS", "RATIO", "YIELD", "FUNDAMENTAL", "FUNDAMENTALS",
}


def _pick_symbol(q: str):
    for tok in _SYM_RE.findall(q.upper()):
        if tok not in _STOPWORDS:
            return tok
    return None


def _pick_range(ql: str) -> str:
    for k, v in _RANGE_WORDS.items():
        if k in ql:
            return v
    return "1Y"


def chat_answer_tracker(query: str, *, provider=None) -> dict:
    """Deterministic. Current-price → official first; history/indicator/fundamental → tracker."""
    provider = provider or get_provider()
    q = query or ""
    ql = q.lower()
    sym = _pick_symbol(q)
    src_third = "NEPSE Portfolio Tracker (third-party historical)"
    if sym is None:
        return {"answer": "Name a NEPSE symbol (e.g. NABIL) and ask for its trend, RSI, P/E, or dividends.",
                "source": None}
    # current price → official authority
    if any(w in ql for w in ("current", "latest", "right now", "now", "official")) and \
            not any(w in ql for w in ("trend", "history", "rsi", "macd", "chart", "year", "month", "week")):
        rec = reconcile_current(sym, provider=provider)
        d = rec.to_public()
        if rec.official_ltp is not None:
            return {"answer": f"{sym} latest OFFICIAL NEPSE LTP is NPR {rec.official_ltp} "
                              f"(tracker {rec.tracker_ltp}, {rec.verdict.value}).",
                    "source": "Official NEPSE (authoritative)", "reconciliation": d}
        return {"answer": f"No official observation cached; {sym} tracker LTP is NPR {rec.tracker_ltp} "
                          f"(third-party).", "source": src_third, "reconciliation": d}
    # RSI / indicators
    if "rsi" in ql:
        series, st = provider.market_history(sym, _pick_range(ql))
        if series is None:
            return {"answer": f"{sym} history unavailable ({st.value}).", "source": src_third}
        r = ind.rsi(series.closes).series["rsi"]
        last = next((x for x in reversed(r) if x is not None), None)
        return {"answer": f"{sym} RSI(14) is {last} (descriptive analytics, not a signal). "
                          f"Source: {src_third}, {series.range}.", "source": src_third,
                "point_in_time": "HISTORICAL_KNOWLEDGE_TIME_UNSUPPORTED"}
    # fundamentals
    if any(w in ql for w in ("p/e", "pe ratio", " pe", "p/b", "pb ratio", "eps", "dividend yield", "fundamental")):
        f, st = provider.fundamentals(sym)
        if f is None:
            return {"answer": f"{sym} fundamentals unavailable ({st.value}).", "source": src_third}
        return {"answer": f"{sym}: EPS {f.eps}, P/E {f.pe_ratio}, P/B {f.pb_ratio}, "
                          f"dividend yield {f.dividend_yield}%, sector {f.sector}. Source: {src_third}.",
                "source": src_third}
    # dividends
    if "dividend" in ql:
        d, st = provider.dividends(sym)
        if not d:
            return {"answer": f"No dividend records for {sym} ({st.value}).", "source": src_third}
        latest = d[0]
        return {"answer": f"{sym} latest dividend (FY {latest.fiscal_year}): cash {latest.cash_dividend}, "
                          f"bonus {latest.bonus_share}, total {latest.total_dividend}. Source: {src_third}.",
                "source": src_third}
    # trend / history
    rng = _pick_range(ql)
    series, st = provider.market_history(sym, rng)
    if series is None:
        return {"answer": f"{sym} history unavailable ({st.value}).", "source": src_third}
    first, last = series.points[0].close, series.points[-1].close
    pct = (last - first) / first * 100 if first else Decimal(0)
    return {"answer": f"{sym} {rng} trend: {series.first_date} {first} → {series.last_date} {last} "
                      f"({pct:+.2f}%), {len(series.points)} points. Source: {src_third}.",
            "source": src_third, "range": rng,
            "point_in_time": "HISTORICAL_KNOWLEDGE_TIME_UNSUPPORTED"}


def voice_answer_tracker(query: str, *, provider=None) -> str:
    a = chat_answer_tracker(query, provider=provider)
    return a.get("answer", "")


def catalyst_historical_context(symbol: str, range_: str = "3M", *, provider=None) -> dict:
    """THIRD_PARTY_HISTORICAL_CONTEXT for a research event — descriptive, never the
    canonical historical market reaction (that remains MD-1 only)."""
    provider = provider or get_provider()
    series, st = provider.market_history(symbol, range_)
    ctx = {"context_kind": "THIRD_PARTY_HISTORICAL_CONTEXT",
           "is_canonical_reaction": False, "source": "NEPSE_PORTFOLIO_TRACKER",
           "source_authority": "THIRD_PARTY_STRUCTURED_MARKET_DATA",
           "point_in_time_capability": "HISTORICAL_KNOWLEDGE_TIME_UNSUPPORTED",
           "note": "descriptive history only; canonical historical reaction requires MD-1",
           "symbol": symbol.upper(), "range": range_, "status": st.value}
    if series is None:
        ctx["available"] = False
        return ctx
    first, last = series.points[0].close, series.points[-1].close
    ctx.update({"available": True, "first_date": series.first_date, "last_date": series.last_date,
                "first_close": str(first), "last_close": str(last),
                "change_pct": str(round((last - first) / first * 100, 2)) if first else None,
                "n_points": len(series.points)})
    return ctx
