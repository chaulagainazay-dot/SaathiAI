from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
import stat
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from saathi.platform.backtest.strategy_crypto import (
    CryptoQualificationRunner,
    qualification_inputs_from_certification,
)
from saathi.platform.market_data.contract import AssetClass, HistoricalBar
from saathi.platform.market_data.crypto_dataset import (
    AcquisitionPolicy,
    ArchiveFormatError,
    ArchiveSpec,
    ChecksumMismatchError,
    ConflictingRevisionError,
    DatasetQualityStatus,
    OversizedArchiveError,
    ZipSecurityError,
    audit_continuity,
    canonical_historical_hash,
    certify_verified_archives,
    merge_historical_bars,
    normalize_verified_archive,
    persist_certification,
    verify_persisted_reproducibility,
    verify_source_archive,
)


RETRIEVED_AT = datetime(2026, 9, 2, 13, 15, tzinfo=UTC)


def _policy(
    *,
    symbols: tuple[str, ...] = ("BTCUSDT",),
    start: date = date(2024, 1, 1),
    end: date = date(2024, 1, 31),
) -> AcquisitionPolicy:
    return AcquisitionPolicy(symbols=symbols, interval="1d", coverage_start=start, coverage_end=end)


def _row(
    day: date,
    *,
    timestamp_unit: str = "milliseconds",
    open_: str = "100",
    high: str = "101",
    low: str = "99",
    close: str = "100.5",
    volume: str = "10",
    ignore: str = "0",
) -> str:
    opened = datetime(day.year, day.month, day.day, tzinfo=UTC)
    scale = 1_000_000 if timestamp_unit == "microseconds" else 1_000
    open_time = int(opened.timestamp()) * scale
    close_time = int((opened + timedelta(days=1)).timestamp()) * scale - 1
    return ",".join(
        (
            str(open_time),
            open_,
            high,
            low,
            close,
            volume,
            str(close_time),
            "1000",
            "5",
            "4",
            "400",
            ignore,
        )
    )


def _zip(spec: ArchiveSpec, rows: list[str], *, member_name: str | None = None) -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr(member_name or spec.csv_filename, "\n".join(rows) + "\n")
    return stream.getvalue()


def _verified(
    spec: ArchiveSpec,
    rows: list[str],
    *,
    member_name: str | None = None,
):
    payload = _zip(spec, rows, member_name=member_name)
    digest = sha256(payload).hexdigest()
    return verify_source_archive(
        spec,
        payload,
        f"{digest}  {spec.filename}\n".encode(),
        retrieved_at=RETRIEVED_AT,
    )


def test_checksum_success_records_published_and_actual_hash():
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    verified = _verified(spec, [_row(date(2024, 1, 1))])
    assert verified.published_sha256 == verified.actual_sha256
    assert verified.actual_sha256 == sha256(verified.archive_bytes).hexdigest()


def test_checksum_failure_is_quarantinable_and_never_ingested():
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    payload = _zip(spec, [_row(date(2024, 1, 1))])
    with pytest.raises(ChecksumMismatchError) as failure:
        verify_source_archive(
            spec,
            payload,
            f"{'0' * 64}  {spec.filename}\n".encode(),
            retrieved_at=RETRIEVED_AT,
        )
    assert failure.value.expected_sha256 == "0" * 64
    assert failure.value.actual_sha256 == sha256(payload).hexdigest()


def test_persisted_source_archive_and_checksum_are_read_only(tmp_path):
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    verified = _verified(spec, [_row(date(2024, 1, day)) for day in range(1, 32)])
    certification = certify_verified_archives((verified,), _policy())
    location = persist_certification(certification, (verified,), root=tmp_path)
    for filename in (spec.filename, spec.checksum_filename):
        mode = (location / "raw" / spec.symbol / filename).stat().st_mode
        assert mode & stat.S_IWUSR == 0


def test_manifest_and_dataset_identity_are_stable_for_exact_inputs():
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    verified = _verified(spec, [_row(date(2024, 1, day)) for day in range(1, 32)])
    first = certify_verified_archives((verified,), _policy())
    second = certify_verified_archives((verified,), _policy())
    assert first.dataset_id == second.dataset_id
    assert first.dataset_version == second.dataset_version
    assert first.to_public() == second.to_public()


@pytest.mark.parametrize(
    ("symbol", "instrument_id"),
    (("BTCUSDT", "BINANCE:BTC/USDT"), ("ETHUSDT", "BINANCE:ETH/USDT")),
)
def test_btc_and_eth_use_canonical_instrument_identity(symbol, instrument_id):
    spec = ArchiveSpec(symbol, "1d", 2024, 1)
    bar = normalize_verified_archive(_verified(spec, [_row(date(2024, 1, 1))]))[0]
    assert type(bar) is HistoricalBar
    assert bar.instrument_id == instrument_id


def test_archive_normalizes_to_spot_venue_asset_and_quote_identity():
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    bar = normalize_verified_archive(_verified(spec, [_row(date(2024, 1, 1))]))[0]
    assert bar.venue == "BINANCE"
    assert bar.asset_class is AssetClass.CRYPTO
    assert bar.currency == "USDT"
    assert bar.timeframe == "1d"


def test_wrong_futures_or_non_spot_path_is_rejected():
    with pytest.raises(ValueError, match="spot"):
        ArchiveSpec("BTCUSDT", "1d", 2024, 1, market_type="um")


@pytest.mark.parametrize(
    ("day", "unit"),
    ((date(2024, 12, 31), "milliseconds"), (date(2025, 1, 1), "microseconds")),
)
def test_timestamp_units_normalize_to_timezone_aware_utc(day, unit):
    spec = ArchiveSpec("BTCUSDT", "1d", day.year, day.month)
    bar = normalize_verified_archive(_verified(spec, [_row(day, timestamp_unit=unit)]))[0]
    assert bar.point_in_time.event_timestamp == datetime(day.year, day.month, day.day, tzinfo=UTC)
    assert bar.as_of == datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(days=1)


def test_impossible_ohlc_is_rejected():
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    verified = _verified(spec, [_row(date(2024, 1, 1), high="99")])
    with pytest.raises(ArchiveFormatError, match="OHLC"):
        normalize_verified_archive(verified)


def test_negative_volume_is_rejected():
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    verified = _verified(spec, [_row(date(2024, 1, 1), volume="-1")])
    with pytest.raises(ArchiveFormatError, match="volume"):
        normalize_verified_archive(verified)


def test_identical_duplicate_bar_is_deduplicated_with_provenance():
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    bar = normalize_verified_archive(_verified(spec, [_row(date(2024, 1, 1))]))[0]
    merged = merge_historical_bars((bar, bar))
    assert merged.bars == (bar,)
    assert merged.identical_duplicate_count == 1
    assert merged.duplicate_provenance[0][0] == bar.source_record_id


def test_conflicting_duplicate_bar_is_rejected_not_silently_selected():
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    bar = normalize_verified_archive(_verified(spec, [_row(date(2024, 1, 1))]))[0]
    conflict = replace(bar, close=Decimal("101"), revision_id="different-revision")
    with pytest.raises(ConflictingRevisionError):
        merge_historical_bars((bar, conflict))


def test_missing_interval_is_recorded_and_never_synthesized():
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    bars = normalize_verified_archive(
        _verified(spec, [_row(date(2024, 1, 1)), _row(date(2024, 1, 3))])
    )
    audit = audit_continuity(bars, date(2024, 1, 1), date(2024, 1, 3))
    assert audit.missing_intervals == (datetime(2024, 1, 2, tzinfo=UTC),)
    assert len(bars) == 2


def test_archive_boundary_duplicate_is_deduplicated():
    january = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    february = ArchiveSpec("BTCUSDT", "1d", 2024, 2)
    first = normalize_verified_archive(_verified(january, [_row(date(2024, 2, 1))]))
    second = normalize_verified_archive(_verified(february, [_row(date(2024, 2, 1))]))
    merged = merge_historical_bars(first + second)
    assert len(merged.bars) == 1
    assert merged.identical_duplicate_count == 1


def test_canonical_dataset_hash_is_order_independent_and_reproducible():
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    bars = normalize_verified_archive(
        _verified(spec, [_row(date(2024, 1, 1)), _row(date(2024, 1, 2))])
    )
    assert canonical_historical_hash(bars) == canonical_historical_hash(reversed(bars))


def test_changed_official_archive_checksum_creates_new_dataset_version():
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    first = _verified(spec, [_row(date(2024, 1, day)) for day in range(1, 32)])
    revised = _verified(
        spec,
        [_row(date(2024, 1, day), ignore="1") for day in range(1, 32)],
    )
    assert normalize_verified_archive(first)[0].open == normalize_verified_archive(revised)[0].open
    assert certify_verified_archives((first,), _policy()).dataset_version != certify_verified_archives(
        (revised,), _policy()
    ).dataset_version


def test_zip_path_traversal_is_rejected_without_extraction():
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    verified = _verified(spec, [_row(date(2024, 1, 1))], member_name="../escape.csv")
    with pytest.raises(ZipSecurityError):
        normalize_verified_archive(verified)


def test_oversized_expansion_is_rejected_before_csv_parsing():
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr(spec.csv_filename, b"0" * 2_000_001)
    payload = stream.getvalue()
    digest = sha256(payload).hexdigest()
    verified = verify_source_archive(
        spec,
        payload,
        f"{digest}  {spec.filename}\n".encode(),
        retrieved_at=RETRIEVED_AT,
    )
    with pytest.raises(OversizedArchiveError):
        normalize_verified_archive(verified)


def test_unexpected_extra_archive_member_is_rejected():
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr(spec.csv_filename, _row(date(2024, 1, 1)) + "\n")
        archive.writestr("surprise.txt", "not accepted")
    payload = stream.getvalue()
    digest = sha256(payload).hexdigest()
    verified = verify_source_archive(
        spec,
        payload,
        f"{digest}  {spec.filename}\n".encode(),
        retrieved_at=RETRIEVED_AT,
    )
    with pytest.raises(ZipSecurityError):
        normalize_verified_archive(verified)


def test_header_or_malformed_csv_is_rejected():
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    header = "open_time,open,high,low,close,volume,close_time,quote_volume,trades,taker_base,taker_quote,ignore"
    with pytest.raises(ArchiveFormatError):
        normalize_verified_archive(_verified(spec, [header, header]))


def test_persisted_dataset_recreates_the_same_normalized_checksum(tmp_path):
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    verified = _verified(spec, [_row(date(2024, 1, day)) for day in range(1, 32)])
    certification = certify_verified_archives((verified,), _policy())
    location = persist_certification(certification, (verified,), root=tmp_path)
    assert verify_persisted_reproducibility(location) is True
    manifest = json.loads((location / "manifest.json").read_text())
    assert manifest["content_checksum"] == certification.content_checksum


def test_acquisition_freezes_splits_without_evaluating_test_returns(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("strategy evaluation spent TEST during dataset acquisition")

    monkeypatch.setattr(CryptoQualificationRunner, "qualify", forbidden)
    spec = ArchiveSpec("BTCUSDT", "1d", 2024, 1)
    verified = _verified(spec, [_row(date(2024, 1, day)) for day in range(1, 32)])
    certification = certify_verified_archives((verified,), _policy())
    split = certification.split_freezes["BINANCE:BTC/USDT"]
    assert split.train_end_index == 18
    assert split.validation_end_index == 24
    assert certification.performance_evaluations == 0
    assert certification.test_periods_spent == 0


def test_complete_long_coverage_is_real_historical_and_pit_limited():
    policy = _policy(start=date(2024, 1, 1), end=date(2024, 9, 30))
    archives = []
    cursor = date(2024, 1, 1)
    while cursor <= policy.coverage_end:
        spec = ArchiveSpec("BTCUSDT", "1d", cursor.year, cursor.month)
        next_month = (date(cursor.year + 1, 1, 1) if cursor.month == 12 else date(cursor.year, cursor.month + 1, 1))
        last = min(policy.coverage_end + timedelta(days=1), next_month)
        rows = []
        day = cursor
        while day < last:
            rows.append(_row(day))
            day += timedelta(days=1)
        archives.append(_verified(spec, rows))
        cursor = next_month
    certification = certify_verified_archives(tuple(archives), policy)
    assert certification.quality_status is DatasetQualityStatus.CERTIFIED_REAL_HISTORICAL
    assert certification.data_mode == "HISTORICAL"
    assert "ARCHIVE_PUBLICATION_HISTORY_NOT_RECONSTRUCTED" in certification.limitations
    inputs = qualification_inputs_from_certification(certification)
    snapshot, rows = inputs["BINANCE:BTC/USDT"]
    assert snapshot.content_hash == canonical_historical_hash(rows)
    assert snapshot.revision_snapshot == certification.source_revision_checksum
