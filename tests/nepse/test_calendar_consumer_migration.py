"""NEPSE-CAL-1.1 consumer-migration contract tests.

These tests intentionally describe the corrected semantics before the legacy
consumers are changed.  No holiday dates are fixtures here: a covered year is
an explicit test input, while the default calendar remains unsourced.
"""
from __future__ import annotations

import ast
import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from saathi.platform.market_data.fixtures import build_bars
from saathi.platform.market_data.models import MDQuote, MarketDataQuality, Timeframe
from saathi.platform.market_data.quality import classify_quote
from saathi.platform.nepse.calendar import (
    NEPAL_TZ,
    NEPSE_CALENDAR_V2_CANONICAL,
    NEPSE_TRADING_WEEKDAYS,
    CalendarCoverageStatus,
    NepseCalendar,
    SessionClassification,
)
from saathi.platform.strategy.engine import run_backtest
from saathi.platform.strategy.fixtures import valid_momentum
from saathi.platform.tg.historical.calendars import (
    NEPSE_CALENDAR_V1_LEGACY_INVALID,
    expected_session_audit,
    get_market_calendar,
)
from saathi.platform.tg.historical.import_service import HistoricalImportService
from saathi.platform.tg.historical.models import DatasetManifest
from saathi.platform.tg.historical.research import HistoricalResearchRunner
from saathi.platform.tg.market_data.calendar import CalendarEngine
from saathi.platform.tg.market_data.quality import QualityEngine
from saathi.platform.tg.paper_simulation.calendar import TradingCalendar


SUNDAY = date(2026, 8, 30)
MONDAY = date(2026, 8, 31)
THURSDAY = date(2026, 9, 3)
FRIDAY = date(2026, 9, 4)
SATURDAY = date(2026, 9, 5)


def _at(day: date, hour: int = 13) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=NEPAL_TZ)


def _quote(*, source_time: datetime) -> MDQuote:
    return MDQuote(
        instrument="NEPSE:NABIL",
        provider="fixture",
        bid=Decimal("499"),
        ask=Decimal("501"),
        last=Decimal("500"),
        bid_size=Decimal("10"),
        ask_size=Decimal("10"),
        source_time=source_time,
        ingested_at=source_time,
    )


def _write_nepse_week(path: Path) -> Path:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["date", "symbol", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        for index, day in enumerate([SUNDAY, MONDAY, date(2026, 9, 1), date(2026, 9, 2), THURSDAY]):
            px = Decimal("500") + index
            writer.writerow(
                {
                    "date": day.isoformat(),
                    "symbol": "NABIL",
                    "open": str(px),
                    "high": str(px + 2),
                    "low": str(px - 2),
                    "close": str(px + 1),
                    "volume": "1000",
                }
            )
    return path


def test_typed_session_classification_preserves_unknown_holiday_coverage():
    unsourced = NepseCalendar()
    covered = NepseCalendar(covered_years={2026}, dataset_version="test-sourced-2026")

    assert unsourced.classify_session(SUNDAY) is SessionClassification.POTENTIAL_OPEN_HOLIDAY_UNKNOWN
    assert unsourced.classify_session(THURSDAY) is SessionClassification.POTENTIAL_OPEN_HOLIDAY_UNKNOWN
    assert unsourced.classify_session(FRIDAY) is SessionClassification.CONFIRMED_CLOSED
    assert unsourced.classify_session(SATURDAY) is SessionClassification.CONFIRMED_CLOSED
    assert covered.classify_session(SUNDAY) is SessionClassification.CONFIRMED_OPEN
    assert covered.coverage_status([SUNDAY, THURSDAY]) is CalendarCoverageStatus.COMPLETE
    assert unsourced.coverage_status([SUNDAY, THURSDAY]) is CalendarCoverageStatus.HOLIDAY_COVERAGE_UNKNOWN


def test_legacy_wrapper_delegates_nepse_weekdays_and_removes_fixture_holidays():
    compat = get_market_calendar("NEPSE")
    assert compat is not None
    assert compat.calendar_version == NEPSE_CALENDAR_V2_CANONICAL
    assert compat.open_weekdays == NEPSE_TRADING_WEEKDAYS
    assert SUNDAY.weekday() in compat.open_weekdays
    assert FRIDAY.weekday() not in compat.open_weekdays
    assert compat.closed_dates == frozenset()
    assert compat.state_at(_at(FRIDAY)).value == "CLOSED"
    assert compat.state_at(_at(SUNDAY)).value == "UNKNOWN"


def test_expected_session_audit_uses_weekly_candidates_without_inventing_holidays():
    audit = expected_session_audit(
        "NEPSE",
        _at(SUNDAY, 0).timestamp(),
        _at(SATURDAY, 23).timestamp(),
    )
    assert audit.expected_session_count == 5
    assert audit.confirmed_open_count == 0
    assert audit.potential_open_count == 5
    assert audit.confirmed_closed_count == 2
    assert audit.coverage_status is CalendarCoverageStatus.HOLIDAY_COVERAGE_UNKNOWN
    assert [item.day for item in audit.sessions if item.is_expected] == [
        SUNDAY,
        MONDAY,
        date(2026, 9, 1),
        date(2026, 9, 2),
        THURSDAY,
    ]


def test_nepse_import_keeps_potential_sessions_and_records_canonical_provenance(tmp_path):
    path = _write_nepse_week(tmp_path / "nepse.csv")
    out = HistoricalImportService().import_file(
        path,
        adapter="nepse",
        default_instrument="NABIL",
        min_rows=1,
    )

    assert out["status"] == "ACCEPTED_WITH_WARNINGS"
    assert out["version"]["row_count"] == 5
    manifest = out["version"]["manifest"]
    assert manifest["calendar_name"] == "NEPSE"
    assert manifest["calendar_version"] == NEPSE_CALENDAR_V2_CANONICAL
    assert manifest["calendar_source_version"] == "unsourced"
    assert manifest["calendar_coverage_status"] == "HOLIDAY_COVERAGE_UNKNOWN"
    assert "nepse_holiday_coverage_unknown" in out["quality"]["warnings"]
    assert out["promotable"] is False


def test_historical_research_backtest_rejects_nepse_without_calendar_coverage(tmp_path):
    path = _write_nepse_week(tmp_path / "nepse.csv")
    service = HistoricalImportService()
    imported = service.import_file(path, adapter="nepse", default_instrument="NABIL", min_rows=1)
    version = service.store.get_version(imported["dataset"]["id"], "1.0.0")
    assert version is not None

    result = HistoricalResearchRunner().run(
        strategy_slug="trend_following",
        dataset_version=version,
    )
    assert result["status"] == "REJECTED"
    assert result["reason"] == "NEPSE_CALENDAR_COVERAGE_REQUIRED"
    assert result["calendar_policy"] == "REQUIRE_CALENDAR_COVERAGE"


def test_direct_nepse_backtest_fails_closed_when_calendar_truth_is_uncovered():
    bars = build_bars("TRENDING", Timeframe.D1, 30)
    result = run_backtest(valid_momentum(), bars, calendar="NEPSE")

    assert result.status == "REJECTED"
    assert result.reason == "NEPSE_CALENDAR_COVERAGE_REQUIRED"
    assert result.manifest["calendar_version"] == NEPSE_CALENDAR_V2_CANONICAL
    assert result.manifest["calendar_coverage_status"] == "HOLIDAY_COVERAGE_UNKNOWN"
    assert result.manifest["calendar_policy"] == "REQUIRE_CALENDAR_COVERAGE"


def test_direct_nepse_backtest_uses_confirmed_calendar_when_year_is_covered():
    bars = build_bars("TRENDING", Timeframe.D1, 50)
    years = {bar.start_time.astimezone(NEPAL_TZ).year for bar in bars}
    calendar = NepseCalendar(covered_years=years, dataset_version="test-sourced-years")
    session_bars = [
        bar
        for bar in bars
        if calendar.is_trading_weekday(bar.start_time.astimezone(NEPAL_TZ).date())
    ]
    result = run_backtest(
        valid_momentum(),
        session_bars,
        calendar="NEPSE",
        nepse_calendar=calendar,
    )

    assert result.reason != "NEPSE_CALENDAR_COVERAGE_REQUIRED"
    assert result.reason != "NEPSE_CONFIRMED_CLOSED_SESSION_BAR"
    assert result.manifest["calendar_coverage_status"] == "COMPLETE"
    assert result.manifest["calendar_source_version"] == "test-sourced-years"


def test_direct_nepse_backtest_rejects_bar_on_confirmed_closed_day():
    bars = build_bars("TRENDING", Timeframe.D1, 50)
    years = {bar.start_time.astimezone(NEPAL_TZ).year for bar in bars}
    calendar = NepseCalendar(covered_years=years, dataset_version="test-sourced-years")
    result = run_backtest(
        valid_momentum(),
        bars,
        calendar="NEPSE",
        nepse_calendar=calendar,
    )
    assert result.status == "REJECTED"
    assert result.reason == "NEPSE_CONFIRMED_CLOSED_SESSION_BAR"


def test_closed_nepse_weekend_quote_is_market_closed_not_stale():
    quote = _quote(source_time=_at(THURSDAY, 14))
    quality = classify_quote(quote, now=_at(FRIDAY), nepse_calendar=NepseCalendar())
    assert quality is MarketDataQuality.MARKET_CLOSED
    assert all(f.code != "STALE" for f in quote.findings)


def test_sunday_quote_is_active_when_covered_and_unknown_when_unsourced():
    now = _at(SUNDAY)
    covered_quote = _quote(source_time=now - timedelta(seconds=1))
    unknown_quote = _quote(source_time=now - timedelta(hours=1))

    assert classify_quote(
        covered_quote,
        now=now,
        nepse_calendar=NepseCalendar(covered_years={2026}, dataset_version="test-sourced-2026"),
    ) is MarketDataQuality.VALID
    assert classify_quote(
        unknown_quote,
        now=now,
        nepse_calendar=NepseCalendar(),
    ) is MarketDataQuality.UNVERIFIED
    assert any(f.code == "CALENDAR_COVERAGE_UNKNOWN" for f in unknown_quote.findings)


class _CalendarStoreStub:
    def get_dataset(self, _dataset_id, _dataset_version):
        return {"exchange": "NEPSE", "asset_class": "equity"}

    def query(self, _sql, _args):
        return [
            {"symbol": "NABIL", "timestamp": _at(SUNDAY).isoformat(), "asset_class": "equity"},
            {"symbol": "NABIL", "timestamp": _at(FRIDAY).isoformat(), "asset_class": "equity"},
        ]


def test_bar_alignment_uses_nepse_classification_not_western_weekends():
    engine = CalendarEngine.__new__(CalendarEngine)
    engine.store = _CalendarStoreStub()
    result = engine.check_bars("ds", "1")

    sunday = [issue for issue in result["issues"] if issue["ts"].startswith(SUNDAY.isoformat())]
    friday = [issue for issue in result["issues"] if issue["ts"].startswith(FRIDAY.isoformat())]
    assert {issue["code"] for issue in sunday} == {"calendar_coverage_unknown"}
    assert {issue["code"] for issue in friday} == {"confirmed_closed_session_bar"}
    assert result["calendar_version"] == NEPSE_CALENDAR_V2_CANONICAL


class _QualityStoreStub:
    def __init__(self):
        self.dataset = {
            "id": "ds",
            "version": "1",
            "exchange": "NEPSE",
            "asset_class": "equity",
            "is_synthetic": False,
        }

    def get_dataset(self, _dataset_id, _dataset_version):
        return self.dataset

    def query(self, _sql, _args):
        return [
            {
                "symbol": "NABIL",
                "timestamp": _at(SUNDAY).isoformat(),
                "asset_class": "equity",
                "open": 500,
                "high": 502,
                "low": 499,
                "close": 501,
                "volume": 100,
            },
            {
                "symbol": "NABIL",
                "timestamp": _at(FRIDAY).isoformat(),
                "asset_class": "equity",
                "open": 501,
                "high": 503,
                "low": 500,
                "close": 502,
                "volume": 100,
            },
        ]

    def execute(self, *_args):
        return None

    def upsert_dataset(self, dataset):
        self.dataset = dataset

    def audit(self, *_args, **_kwargs):
        return None


def test_quality_engine_does_not_apply_saturday_sunday_rules_to_nepse():
    result = QualityEngine(_QualityStoreStub()).evaluate("ds", "1")
    calendar_findings = [item for item in result["findings"] if item["kind"] == "calendar"]
    assert [item["code"] for item in calendar_findings] == [
        "calendar_coverage_unknown",
        "confirmed_closed_session_bar",
    ]
    assert result["calendar_version"] == NEPSE_CALENDAR_V2_CANONICAL


def test_paper_session_description_uses_nepse_timezone_and_weekdays():
    result = TradingCalendar().for_symbol("NEPSE:NABIL")
    assert result["timezone"] == "Asia/Kathmandu"
    assert result["weekdays"] == sorted(NEPSE_TRADING_WEEKDAYS)
    assert result["open"] == "11:00"
    assert result["close"] == "15:00"
    assert result["calendar_version"] == NEPSE_CALENDAR_V2_CANONICAL


def test_unversioned_old_nepse_manifest_is_not_silently_relabelled_canonical():
    public = DatasetManifest(
        dataset_id="legacy",
        market="NEPSE",
        calendar_name="NEPSE",
    ).to_public()
    assert public["calendar_version"] == NEPSE_CALENDAR_V1_LEGACY_INVALID
    assert public["calendar_coverage_status"] == "UNKNOWN"


def test_no_independent_legacy_nepse_market_calendar_remains():
    source_path = Path(__file__).parents[2] / "saathi/platform/tg/historical/calendars.py"
    source = source_path.read_text()
    tree = ast.parse(source)
    nepse_assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "NEPSE"
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
    ]
    assert not nepse_assignments
    assert "NEPSE_HOLIDAYS_2024_2025" not in source


# ══════════════════════════════════════════════════════════════════════════
# NEPSE-CAL-1.1 fresh-context review findings
# ══════════════════════════════════════════════════════════════════════════

def test_nepse_instrument_cannot_bypass_the_calendar_gate_by_omitting_it():
    """R-A: the coverage gate keyed on calendar_name == "NEPSE" only. A caller
    that passed a NEPSE instrument but left calendar at its DEFAULT_24_5 default
    skipped the gate entirely and could produce fills over uncovered dates."""
    defn = valid_momentum()
    defn.instrument_universe = ["NEPSE:NABIL"]
    bars = build_bars("NEPSE:NABIL", Timeframe.D1, 30)

    result = run_backtest(defn, bars)          # calendar deliberately omitted

    assert result.status == "REJECTED"
    assert result.reason == "NEPSE_INSTRUMENT_REQUIRES_NEPSE_CALENDAR"


def test_nepse_instrument_with_an_explicitly_wrong_calendar_is_rejected():
    defn = valid_momentum()
    defn.instrument_universe = ["NEPSE:NABIL"]
    bars = build_bars("NEPSE:NABIL", Timeframe.D1, 30)

    result = run_backtest(defn, bars, calendar="US_RTH")

    assert result.status == "REJECTED"
    assert result.reason == "NEPSE_INSTRUMENT_REQUIRES_NEPSE_CALENDAR"


def test_a_non_nepse_instrument_is_unaffected_by_the_new_guard():
    """The guard must not change behaviour for any other venue."""
    result = run_backtest(valid_momentum(), build_bars("TRENDING", Timeframe.D1, 30))
    assert result.reason != "NEPSE_INSTRUMENT_REQUIRES_NEPSE_CALENDAR"


def test_confirmed_closed_session_bar_blocks_market_data_quality_not_just_scores_it():
    """R-C: tg/historical/quality.py folds confirmed_closed bars into `critical`
    and forces REJECTED. tg/market_data/quality.py appended a finding and nudged
    the score, but never populated `blocking` — so a dataset carrying NEPSE
    Friday/Saturday bars could still be certified RESEARCH_USABLE."""
    result = QualityEngine(_QualityStoreStub()).evaluate("ds", "1")
    codes = {item["code"] for item in result["findings"] if item["kind"] == "calendar"}
    assert "confirmed_closed_session_bar" in codes
    assert "confirmed_closed_session_bar" in result["blocking_defects"]
    assert result["classification"] in ("REJECTED", "QUARANTINED"), (
        "a confirmed-closed NEPSE bar must block certification the same way "
        "tg/historical/quality.py does, got "
        f"{result['classification']}"
    )


class _OffsetlessStoreStub(_QualityStoreStub):
    def query(self, _sql, _args):
        # 2026-09-03T19:00 with no offset. Read as UTC it is Thursday; in
        # Kathmandu (+05:45) it is 2026-09-04T00:45 — a Friday, NEPSE closed.
        return [{
            "symbol": "NABIL",
            "timestamp": "2026-09-03T19:00:00",
            "asset_class": "equity",
            "open": 500, "high": 502, "low": 499, "close": 501, "volume": 100,
        }]


def test_an_offsetless_timestamp_is_treated_as_utc_not_string_sliced():
    """R-D: with +05:45, an offset-less instant late in the UTC day belongs to the
    NEXT Kathmandu date. Slicing the raw string put the bar on the wrong side of a
    Thursday/Friday boundary, silently accepting a closed-day bar as valid."""
    result = QualityEngine(_OffsetlessStoreStub()).evaluate("ds", "1")
    codes = {item["code"] for item in result["findings"] if item["kind"] == "calendar"}
    assert "confirmed_closed_session_bar" in codes, (
        "offset-less timestamp was not converted to Kathmandu time; the bar was "
        f"judged on its raw UTC date. calendar findings={codes}"
    )
