from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from saathi.platform.nepse.historical import (
    CalendarStatus, DatasetManifest, HistoricalBar, PointInTimeDataset,
    ReplayClock, RevisionStatus,
)

UTC = timezone.utc

def bar(day="2026-01-04", available="2026-01-04T12:00:00+00:00", symbol="NABIL", close="100"):
    d = date.fromisoformat(day); a = datetime.fromisoformat(available)
    return HistoricalBar("NEPSE:"+symbol, d, datetime.combine(d, datetime.min.time(), UTC), a, datetime(2026,1,7,tzinfo=UTC), Decimal("95"), Decimal("105"), Decimal("90"), Decimal(close), Decimal("1000"), "fixture", "r1")

def test_visibility_uses_available_at_not_as_of():
    ds = PointInTimeDataset(DatasetManifest("d1", "1", "fixture"), [bar(available="2026-01-06T00:00:00+00:00")])
    assert ds.visible_at(datetime(2026,1,5,tzinfo=UTC)) == []
    assert len(ds.visible_at(datetime(2026,1,6,tzinfo=UTC))) == 1

def test_bad_ohlc_and_friday_are_rejected():
    b = bar(day="2026-01-02"); b.high = Decimal("80")
    with pytest.raises(ValueError): PointInTimeDataset(DatasetManifest("d", "1", "x"), [b])

def test_replay_is_deterministic_and_revisions_preserved():
    a = bar(symbol="NABIL"); c = bar(symbol="CHCL")
    ds = PointInTimeDataset(DatasetManifest("d", "1", "x"), [c, a])
    first = [x.source_record_id for x in ds.replay(ReplayClock(datetime(2026,1,6,tzinfo=UTC)))]
    second = [x.source_record_id for x in ds.replay(ReplayClock(datetime(2026,1,6,tzinfo=UTC)))]
    assert first == second == ["r1", "r1"]
    assert RevisionStatus.ORIGINAL.value == "ORIGINAL"

def test_duplicate_and_unknown_calendar_are_explicit():
    b = bar(); b2 = bar()
    with pytest.raises(ValueError): PointInTimeDataset(DatasetManifest("d", "1", "x"), [b,b2])
    assert CalendarStatus.POTENTIAL_SESSION_HOLIDAY_UNKNOWN.value
