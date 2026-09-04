"""M187 — Strict historical data quality gates.

Fail-closed. Quarantined/rejected datasets cannot promote strategies.
"""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from typing import Any

from saathi.platform.tg.historical.models import (
    AdjustedPriceBar,
    DataQualityReport,
    DataQualityVerdict,
    DatasetCoverage,
)
from saathi.platform.nepse.calendar import (
    NEPAL_TZ,
    CalendarCoverageStatus,
    NepseCalendar,
    SessionClassification,
)
from saathi.platform.tg.historical.calendars import (
    expected_session_audit,
    expected_sessions,
    get_market_calendar,
)


MAX_JUMP = Decimal("0.50")


def evaluate_dataset_quality(
    bars: list[AdjustedPriceBar],
    *,
    calendar_name: str = "DEFAULT_24_5",
    currency: str = "USD",
    timezone: str = "UTC",
    timeframe: str = "1d",
    min_rows: int = 20,
    require_benchmark: bool = False,
    benchmark_present: bool = False,
    sector_coverage_ratio: float = 1.0,
    corporate_action_status: str = "NONE",
    nepse_calendar: NepseCalendar | None = None,
) -> DataQualityReport:
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    missing = duplicates = outliers = invalid_ohlc = zero_px = neg_vol = 0
    confirmed_closed_bars = 0

    if not bars:
        return DataQualityReport(
            verdict=DataQualityVerdict.REJECTED,
            score=0.0,
            findings=[{"code": "EMPTY_DATASET", "detail": "no bars"}],
            corporate_action_status=corporate_action_status,
        )

    # Chronological + unique key
    seen: set[tuple[str, float]] = set()
    prev_ts: float | None = None
    prev_close: Decimal | None = None
    out_of_order = 0
    for b in bars:
        key = (b.instrument, b.ts)
        if key in seen:
            duplicates += 1
            findings.append({"code": "DUPLICATE_BAR", "detail": f"{b.instrument}@{b.ts}"})
        seen.add(key)
        if prev_ts is not None and b.ts < prev_ts:
            out_of_order += 1
            findings.append({"code": "OUT_OF_ORDER", "detail": f"{b.ts} < {prev_ts}"})
        prev_ts = b.ts

        if b.volume < 0:
            neg_vol += 1
            findings.append({"code": "NEGATIVE_VOLUME", "detail": str(b.volume)})
        if any(x <= 0 for x in (b.open, b.high, b.low, b.close)):
            # zero or negative prices
            if any(x == 0 for x in (b.open, b.high, b.low, b.close)):
                zero_px += 1
                findings.append({"code": "ZERO_PRICE", "detail": b.instrument})
            if any(x < 0 for x in (b.open, b.high, b.low, b.close)):
                invalid_ohlc += 1
                findings.append({"code": "NEGATIVE_PRICE", "detail": b.instrument})
        if b.high < b.low or not (b.low <= b.open <= b.high and b.low <= b.close <= b.high):
            invalid_ohlc += 1
            findings.append({"code": "INVALID_OHLC", "detail": f"{b.instrument}@{b.ts}"})
        if prev_close is not None and prev_close > 0:
            move = abs(b.close - prev_close) / prev_close
            if move > MAX_JUMP:
                outliers += 1
                findings.append({"code": "OUTLIER_JUMP", "detail": str(move)})
        prev_close = b.close

    # Coverage / missing sessions (daily)
    instruments = sorted({b.instrument for b in bars})
    times = [b.ts for b in bars]
    start, end = min(times), max(times)
    session_audit = expected_session_audit(
        calendar_name,
        start,
        end,
        timeframe=timeframe,
        nepse_calendar=nepse_calendar,
    )
    expected = (
        [item.session_start_epoch for item in session_audit.sessions if item.is_expected]
        if calendar_name == "NEPSE"
        else expected_sessions(calendar_name, start, end, timeframe=timeframe)
    )
    if calendar_name == "NEPSE":
        if session_audit.coverage_status is CalendarCoverageStatus.HOLIDAY_COVERAGE_UNKNOWN:
            warnings.append("nepse_holiday_coverage_unknown")
            findings.append(
                {
                    "code": "HOLIDAY_COVERAGE_UNKNOWN",
                    "detail": "weekly candidates retained; certified backtest coverage unavailable",
                }
            )
        classification_by_day = {item.day: item.classification for item in session_audit.sessions}
        for bar in bars:
            local_day = datetime.fromtimestamp(bar.ts, tz=dt_timezone.utc).astimezone(NEPAL_TZ).date()
            if classification_by_day.get(local_day) is SessionClassification.CONFIRMED_CLOSED:
                confirmed_closed_bars += 1
                findings.append(
                    {
                        "code": "CONFIRMED_CLOSED_SESSION_BAR",
                        "detail": f"{bar.instrument}@{local_day.isoformat()}",
                    }
                )
    # multi-instrument: estimate missing as expected * n_inst - unique keys for primary
    primary = instruments[0]
    primary_ts = {b.ts for b in bars if b.instrument == primary}
    if expected and timeframe == "1d":
        # align expected to midnight buckets present in data
        missing = max(0, len(expected) - len(primary_ts))
        if missing > 0:
            findings.append({"code": "MISSING_SESSIONS", "detail": f"missing≈{missing}"})
            if missing > max(3, int(0.15 * len(expected))):
                warnings.append("high_missing_session_rate")
    coverage_ratio = 1.0
    if expected:
        coverage_ratio = min(1.0, len(primary_ts) / max(1, len(expected)))

    if currency not in ("USD", "NPR", "EUR", "GBP", "JPY", "USDT", "BTC"):
        findings.append({"code": "UNKNOWN_CURRENCY", "detail": currency})
        warnings.append("unknown_currency")
    if not timezone:
        findings.append({"code": "MISSING_TIMEZONE", "detail": ""})
    if get_market_calendar(calendar_name) is None:
        findings.append({"code": "UNSUPPORTED_CALENDAR", "detail": calendar_name})

    if require_benchmark and not benchmark_present:
        findings.append({"code": "MISSING_BENCHMARK", "detail": "benchmark required"})
        warnings.append("incomplete_benchmark")
    if sector_coverage_ratio < 0.5:
        warnings.append("low_sector_metadata_coverage")
        findings.append({"code": "SECTOR_COVERAGE_LOW", "detail": str(sector_coverage_ratio)})

    # Critical failures → REJECTED / QUARANTINED
    critical = invalid_ohlc > 0 or neg_vol > 0 or zero_px > 0 or out_of_order > 0
    critical = critical or (duplicates > max(2, int(0.05 * len(bars))))
    critical = critical or confirmed_closed_bars > 0
    if get_market_calendar(calendar_name) is None:
        critical = True

    row_count = len(bars)
    if row_count < min_rows:
        return DataQualityReport(
            verdict=DataQualityVerdict.INSUFFICIENT_COVERAGE,
            score=0.2,
            findings=findings + [{"code": "INSUFFICIENT_ROWS", "detail": f"{row_count}<{min_rows}"}],
            row_count=row_count,
            missing_bar_count=missing,
            duplicate_bar_count=duplicates,
            outlier_count=outliers,
            invalid_ohlc_count=invalid_ohlc,
            zero_price_count=zero_px,
            negative_volume_count=neg_vol,
            corporate_action_status=corporate_action_status,
            warnings=warnings,
        )

    if critical:
        verdict = DataQualityVerdict.REJECTED if (invalid_ohlc or neg_vol or zero_px) else DataQualityVerdict.QUARANTINED
        return DataQualityReport(
            verdict=verdict,
            score=0.1,
            findings=findings,
            row_count=row_count,
            missing_bar_count=missing,
            duplicate_bar_count=duplicates,
            outlier_count=outliers,
            invalid_ohlc_count=invalid_ohlc,
            zero_price_count=zero_px,
            negative_volume_count=neg_vol,
            corporate_action_status=corporate_action_status,
            warnings=warnings,
        )

    # Score components (visible; not sole gate)
    score = 1.0
    score -= min(0.3, outliers * 0.02)
    score -= min(0.2, missing / max(1, row_count) * 0.5)
    score -= min(0.1, duplicates * 0.01)
    if warnings:
        score -= 0.05 * len(warnings)
    score = max(0.0, min(1.0, score))

    if outliers > 0 or missing > 0 or warnings:
        verdict = DataQualityVerdict.ACCEPTED_WITH_WARNINGS
    else:
        verdict = DataQualityVerdict.ACCEPTED

    return DataQualityReport(
        verdict=verdict,
        score=round(score, 4),
        findings=findings,
        row_count=row_count,
        missing_bar_count=missing,
        duplicate_bar_count=duplicates,
        outlier_count=outliers,
        invalid_ohlc_count=invalid_ohlc,
        zero_price_count=zero_px,
        negative_volume_count=neg_vol,
        corporate_action_status=corporate_action_status,
        warnings=warnings,
    )


def build_coverage(
    bars: list[AdjustedPriceBar],
    *,
    calendar_name: str = "DEFAULT_24_5",
    timeframe: str = "1d",
    nepse_calendar: NepseCalendar | None = None,
) -> DatasetCoverage:
    if not bars:
        return DatasetCoverage()
    times = [b.ts for b in bars]
    instruments = sorted({b.instrument for b in bars})
    start, end = min(times), max(times)
    session_audit = expected_session_audit(
        calendar_name,
        start,
        end,
        timeframe=timeframe,
        nepse_calendar=nepse_calendar,
    )
    expected = (
        [item.session_start_epoch for item in session_audit.sessions if item.is_expected]
        if calendar_name == "NEPSE"
        else expected_sessions(calendar_name, start, end, timeframe=timeframe)
    )
    primary = instruments[0]
    primary_ts = {b.ts for b in bars if b.instrument == primary}
    missing = max(0, len(expected) - len(primary_ts)) if expected else 0
    ratio = (len(primary_ts) / len(expected)) if expected else 1.0
    return DatasetCoverage(
        date_start=start,
        date_end=end,
        trading_days=len(primary_ts),
        calendar_days=int((end - start) / 86400) + 1 if end >= start else 0,
        instruments=instruments,
        missing_sessions=missing,
        coverage_ratio=min(1.0, ratio),
        calendar_coverage_status=session_audit.coverage_status.value,
        confirmed_open_sessions=session_audit.confirmed_open_count,
        potential_open_sessions=session_audit.potential_open_count,
        confirmed_closed_sessions=session_audit.confirmed_closed_count,
    )
