"""M62.2 — market-data quality classification. Pure functions.

Validation and normalization are SEPARATE. These functions never repair invalid
financial values — they classify and record findings, failing closed. A record
is `VALID` only when it survives every check.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from saathi.platform.market_data.models import (
    MDQuote, MDBar, MarketDataQuality, QualityFinding, Timeframe,
    TIMEFRAME_SECONDS, INTRADAY_TIMEFRAMES, is_aware, FreshnessPolicy, DEFAULT_FRESHNESS,
)
from saathi.platform.nepse.calendar import (
    NEPAL_TZ,
    NepseCalendar,
    SessionClassification,
    SessionState,
)


# Spread wider than this fraction of mid is flagged abnormal.
MAX_SPREAD_FRACTION = Decimal("0.10")
# Bar-to-bar close move larger than this fraction is flagged an outlier.
MAX_BAR_JUMP_FRACTION = Decimal("0.50")


def _finding(findings: list[QualityFinding], code: str, detail: str = "") -> None:
    findings.append(QualityFinding(code=code, detail=detail))


def classify_quote(q: MDQuote, *, now: datetime, policy: FreshnessPolicy = DEFAULT_FRESHNESS,
                   market_open: bool | None = None,
                   nepse_calendar: NepseCalendar | None = None) -> MarketDataQuality:
    """Classify a quote in place (sets q.quality, appends q.findings). Fail-closed."""
    f = q.findings
    # timestamps must be aware
    if not is_aware(q.source_time) or not is_aware(q.ingested_at):
        _finding(f, "INVALID_TIMESTAMP", "naive timestamp")
        q.quality = MarketDataQuality.INVALID_TIMESTAMP
        return q.quality
    # future timestamp
    if q.source_time > now:
        _finding(f, "FUTURE_TIMESTAMP", f"source_time {q.source_time.isoformat()} > now")
        q.quality = MarketDataQuality.INVALID_TIMESTAMP
        return q.quality
    # completeness
    if q.bid is None or q.ask is None or q.last is None:
        _finding(f, "MISSING_FIELD", "bid/ask/last required")
        q.quality = MarketDataQuality.INCOMPLETE
        return q.quality
    # price validity
    if q.bid <= 0 or q.ask <= 0 or q.last <= 0:
        _finding(f, "NON_POSITIVE_PRICE", "bid/ask/last must be > 0")
        q.quality = MarketDataQuality.INVALID_PRICE
        return q.quality
    if q.bid > q.ask:
        _finding(f, "CROSSED_BOOK", f"bid {q.bid} > ask {q.ask}")
        q.quality = MarketDataQuality.INVALID_PRICE
        return q.quality
    # abnormal spread
    mid = (q.bid + q.ask) / 2
    if mid > 0 and (q.ask - q.bid) / mid > MAX_SPREAD_FRACTION:
        _finding(f, "ABNORMAL_SPREAD", f"spread {(q.ask - q.bid)} on mid {mid}")
        q.quality = MarketDataQuality.OUTLIER
        return q.quality
    # NEPSE session truth is calendar-owned. Unknown holiday coverage is not
    # stale data and must not be collapsed into either open or closed.
    if q.instrument.upper().startswith("NEPSE:"):
        canonical = nepse_calendar or NepseCalendar()
        date_classification = canonical.classify_session(now.astimezone(NEPAL_TZ).date())
        if date_classification in (
            SessionClassification.POTENTIAL_OPEN_HOLIDAY_UNKNOWN,
            SessionClassification.UNKNOWN,
        ):
            _finding(f, "CALENDAR_COVERAGE_UNKNOWN", "NEPSE holiday coverage unavailable")
            q.quality = MarketDataQuality.UNVERIFIED
            return q.quality
        market_open = canonical.session_state(now) is SessionState.OPEN
    # market closed (explicit signal)
    if market_open is False:
        _finding(f, "MARKET_CLOSED", "quote observed while market closed")
        q.quality = MarketDataQuality.MARKET_CLOSED
        return q.quality
    # freshness
    age = (now - q.source_time).total_seconds()
    if age > policy.quote_max_age_sec:
        _finding(f, "STALE", f"age {age:.1f}s > {policy.quote_max_age_sec}s")
        q.quality = MarketDataQuality.STALE
        return q.quality
    q.quality = MarketDataQuality.VALID
    return q.quality


def classify_bar(b: MDBar, *, now: datetime, policy: FreshnessPolicy = DEFAULT_FRESHNESS,
                 prev_close: Decimal | None = None) -> MarketDataQuality:
    """Classify a single bar (OHLC invariants + freshness). Fail-closed."""
    f = b.findings
    if not (is_aware(b.start_time) and is_aware(b.end_time) and is_aware(b.source_time)):
        _finding(f, "INVALID_TIMESTAMP", "naive timestamp")
        b.quality = MarketDataQuality.INVALID_TIMESTAMP
        return b.quality
    if b.start_time > now or b.end_time > now:
        _finding(f, "FUTURE_TIMESTAMP", "bar in the future")
        b.quality = MarketDataQuality.INVALID_TIMESTAMP
        return b.quality
    # duration must match timeframe and be positive
    dur = (b.end_time - b.start_time).total_seconds()
    if dur <= 0:
        _finding(f, "NON_POSITIVE_DURATION", f"duration {dur}s")
        b.quality = MarketDataQuality.INVALID_TIMESTAMP
        return b.quality
    if abs(dur - TIMEFRAME_SECONDS[b.timeframe]) > 1:
        _finding(f, "UNEXPECTED_TIMEFRAME", f"duration {dur}s != {TIMEFRAME_SECONDS[b.timeframe]}s")
        b.quality = MarketDataQuality.INCOMPLETE
        return b.quality
    if None in (b.open, b.high, b.low, b.close):
        _finding(f, "MISSING_OHLC", "OHLC required")
        b.quality = MarketDataQuality.INCOMPLETE
        return b.quality
    if any(v < 0 for v in (b.open, b.high, b.low, b.close)) or b.volume < 0:
        _finding(f, "NEGATIVE_VALUE", "OHLCV must be >= 0")
        b.quality = MarketDataQuality.INVALID_PRICE
        return b.quality
    if b.high < b.low:
        _finding(f, "HIGH_LT_LOW", f"high {b.high} < low {b.low}")
        b.quality = MarketDataQuality.INVALID_PRICE
        return b.quality
    if not (b.low <= b.open <= b.high and b.low <= b.close <= b.high):
        _finding(f, "OHLC_OUT_OF_RANGE", "open/close outside [low, high]")
        b.quality = MarketDataQuality.INVALID_PRICE
        return b.quality
    # abnormal jump vs previous close
    if prev_close is not None and prev_close > 0:
        move = abs(b.close - prev_close) / prev_close
        if move > MAX_BAR_JUMP_FRACTION:
            _finding(f, "ABNORMAL_JUMP", f"close move {move} > {MAX_BAR_JUMP_FRACTION}")
            b.quality = MarketDataQuality.OUTLIER
            return b.quality
    # NOTE: staleness is a DECISION-TIME property of the *latest* bar, not a
    # per-bar validity gate — historical bars are legitimately old. Use
    # `is_bar_fresh()` at trade-decision time. A bar that survives every structural
    # check is VALID regardless of age.
    b.quality = MarketDataQuality.VALID
    return b.quality


def is_bar_fresh(b: MDBar, *, now: datetime, policy: FreshnessPolicy = DEFAULT_FRESHNESS) -> bool:
    """Decision-time freshness for the LATEST bar (not a validity gate for history)."""
    if not is_aware(b.end_time):
        return False
    return (now - b.end_time).total_seconds() <= policy.bar_max_age(b.timeframe)


def classify_series(bars: list[MDBar], *, now: datetime, policy: FreshnessPolicy = DEFAULT_FRESHNESS) -> dict:
    """Classify a chronological bar series: per-bar OHLC + series-level duplicate,
    out-of-order, and gap detection. Returns a summary dict. Does not reorder or
    repair; it marks quality on each bar."""
    step = None
    seen: set[float] = set()
    duplicates = out_of_order = gaps = 0
    prev_start: datetime | None = None
    prev_close: Decimal | None = None
    for b in bars:
        classify_bar(b, now=now, policy=policy, prev_close=prev_close)
        step = TIMEFRAME_SECONDS[b.timeframe]
        key = b.start_time.timestamp() if is_aware(b.start_time) else None
        if key is not None:
            if key in seen:
                duplicates += 1
                b.findings.append(QualityFinding("DUPLICATE_INTERVAL", b.start_time.isoformat()))
                if b.quality == MarketDataQuality.VALID:
                    b.quality = MarketDataQuality.DUPLICATE
            seen.add(key)
        if prev_start is not None and key is not None:
            delta = b.start_time.timestamp() - prev_start.timestamp()
            if delta < 0:
                out_of_order += 1
                b.findings.append(QualityFinding("OUT_OF_ORDER", b.start_time.isoformat()))
                if b.quality == MarketDataQuality.VALID:
                    b.quality = MarketDataQuality.OUT_OF_ORDER
            elif step and delta > step:
                missing = int(round(delta / step)) - 1
                if missing > 0:
                    gaps += missing
                    b.findings.append(QualityFinding("GAP_BEFORE", f"{missing} missing interval(s)"))
                    if b.quality == MarketDataQuality.VALID:
                        b.quality = MarketDataQuality.GAPPED
        prev_start = b.start_time if key is not None else prev_start
        prev_close = b.close
    valid = sum(1 for b in bars if b.quality == MarketDataQuality.VALID)
    return {
        "count": len(bars), "valid": valid, "duplicates": duplicates,
        "out_of_order": out_of_order, "gaps": gaps,
        "invalid": len(bars) - valid,
    }


def classify_freshness_age(age_seconds: float, max_age_seconds: float) -> MarketDataQuality:
    return MarketDataQuality.VALID if age_seconds <= max_age_seconds else MarketDataQuality.STALE
