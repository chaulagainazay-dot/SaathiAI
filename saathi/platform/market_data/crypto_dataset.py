"""Immutable official Binance Spot daily archive acquisition and certification.

This module is deliberately data-only.  It downloads no private information,
knows no account or execution endpoint, and never evaluates a strategy.  Source
ZIPs are verified against their published SHA-256 before any CSV row is parsed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
from io import BytesIO, StringIO
import csv
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Callable, Iterable, Iterator, Mapping, Sequence
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from saathi.platform.market_data.contract import (
    AssetClass,
    HistoricalBar,
    PointInTime,
    ProviderReference,
)
from saathi.platform.tg.historical.models import (
    AdjustmentMethodology,
    DatasetClassification,
    DatasetManifest,
    DatasetSource,
)
from saathi.platform.trading_models import DataQuality


OFFICIAL_ARCHIVE_HOST = "data.binance.vision"
OFFICIAL_ARCHIVE_BASE = f"https://{OFFICIAL_ARCHIVE_HOST}/data"
OFFICIAL_DOCUMENTATION = "https://github.com/binance/binance-public-data/blob/master/README.md"
NORMALIZATION_VERSION = "crypto-dataset-1-binance-kline-v1"
SCHEMA_VERSION = "BINANCE_SPOT_KLINE_12_V1"
CANONICAL_SCHEMA_VERSION = "MD-1-HISTORICAL-BAR-V1"
SUPPORTED_SYMBOLS: Mapping[str, str] = {
    "BTCUSDT": "BINANCE:BTC/USDT",
    "ETHUSDT": "BINANCE:ETH/USDT",
}
DEFAULT_INTERVAL = "1d"
DEFAULT_COVERAGE_START = date(2018, 1, 1)
DEFAULT_COVERAGE_END = date(2025, 12, 31)
MAX_ARCHIVE_BYTES = 1_000_000
MAX_EXPANDED_BYTES = 2_000_000
MAX_MONTHLY_ROWS = 32
MAX_CHECKSUM_BYTES = 512
MIN_QUALIFICATION_BARS = 240
NETWORK_TIMEOUT_SECONDS = 10


class DatasetQualityStatus(str, Enum):
    CERTIFIED_REAL_HISTORICAL = "CERTIFIED_REAL_HISTORICAL"
    CERTIFIED_WITH_GAPS = "CERTIFIED_WITH_GAPS"
    QUARANTINED = "QUARANTINED"
    CHECKSUM_FAILED = "CHECKSUM_FAILED"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    PIT_LIMITED = "PIT_LIMITED"
    INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"


class DatasetCertificationError(ValueError):
    """Base failure for a source that cannot enter a certified dataset."""


class ChecksumMismatchError(DatasetCertificationError):
    def __init__(self, expected_sha256: str, actual_sha256: str) -> None:
        self.expected_sha256 = expected_sha256
        self.actual_sha256 = actual_sha256
        super().__init__(
            f"archive checksum mismatch: expected {expected_sha256}, got {actual_sha256}"
        )


class ArchiveFormatError(DatasetCertificationError):
    pass


class ZipSecurityError(DatasetCertificationError):
    pass


class OversizedArchiveError(DatasetCertificationError):
    pass


class ConflictingRevisionError(DatasetCertificationError):
    pass


@dataclass(frozen=True, order=True)
class ArchiveSpec:
    symbol: str
    interval: str
    year: int
    month: int
    market_type: str = "spot"

    def __post_init__(self) -> None:
        if self.market_type != "spot":
            raise ValueError("only official Binance spot archives are permitted")
        if self.symbol not in SUPPORTED_SYMBOLS:
            raise ValueError(f"unsupported spot symbol: {self.symbol}")
        if self.interval != DEFAULT_INTERVAL:
            raise ValueError("the frozen STRATEGY-CRYPTO-1 interval is 1d")
        if not (2017 <= self.year <= 2100 and 1 <= self.month <= 12):
            raise ValueError("invalid archive year/month")

    @property
    def filename(self) -> str:
        return f"{self.symbol}-{self.interval}-{self.year:04d}-{self.month:02d}.zip"

    @property
    def checksum_filename(self) -> str:
        return f"{self.filename}.CHECKSUM"

    @property
    def csv_filename(self) -> str:
        return self.filename.removesuffix(".zip") + ".csv"

    @property
    def source_path(self) -> str:
        return (
            f"data/spot/monthly/klines/{self.symbol}/{self.interval}/{self.filename}"
        )

    @property
    def url(self) -> str:
        return f"{OFFICIAL_ARCHIVE_BASE}/spot/monthly/klines/{self.symbol}/{self.interval}/{self.filename}"

    @property
    def checksum_url(self) -> str:
        return f"{self.url}.CHECKSUM"

    def to_public(self) -> dict[str, object]:
        return {
            "provider": "BINANCE",
            "archive_host": OFFICIAL_ARCHIVE_HOST,
            "market_type": self.market_type.upper(),
            "symbol": self.symbol,
            "interval": self.interval,
            "year": self.year,
            "month": self.month,
            "archive_filename": self.filename,
            "checksum_filename": self.checksum_filename,
            "source_reference": self.url,
        }


@dataclass(frozen=True)
class AcquisitionPolicy:
    symbols: tuple[str, ...] = tuple(SUPPORTED_SYMBOLS)
    interval: str = DEFAULT_INTERVAL
    coverage_start: date = DEFAULT_COVERAGE_START
    coverage_end: date = DEFAULT_COVERAGE_END

    def __post_init__(self) -> None:
        if not self.symbols or len(set(self.symbols)) != len(self.symbols):
            raise ValueError("symbols must be non-empty and unique")
        if any(symbol not in SUPPORTED_SYMBOLS for symbol in self.symbols):
            raise ValueError("policy contains an unsupported symbol")
        if self.interval != DEFAULT_INTERVAL:
            raise ValueError("the frozen STRATEGY-CRYPTO-1 interval is 1d")
        if self.coverage_start > self.coverage_end:
            raise ValueError("coverage start is after coverage end")

    def archive_specs(self) -> tuple[ArchiveSpec, ...]:
        specs: list[ArchiveSpec] = []
        cursor = date(self.coverage_start.year, self.coverage_start.month, 1)
        final_month = date(self.coverage_end.year, self.coverage_end.month, 1)
        while cursor <= final_month:
            specs.extend(
                ArchiveSpec(symbol, self.interval, cursor.year, cursor.month)
                for symbol in self.symbols
            )
            cursor = _next_month(cursor)
        return tuple(sorted(specs))

    def to_public(self) -> dict[str, object]:
        return {
            "symbols": list(self.symbols),
            "canonical_instruments": [SUPPORTED_SYMBOLS[s] for s in self.symbols],
            "market_type": "SPOT",
            "interval": self.interval,
            "coverage_start": self.coverage_start.isoformat(),
            "coverage_end": self.coverage_end.isoformat(),
            "selection_basis": "PREDEFINED_CALENDAR_COVERAGE_WITHOUT_STRATEGY_OUTCOMES",
        }


@dataclass(frozen=True)
class VerifiedArchive:
    spec: ArchiveSpec
    archive_bytes: bytes
    checksum_bytes: bytes
    published_sha256: str
    actual_sha256: str
    retrieved_at: datetime

    def to_evidence(self) -> dict[str, object]:
        return {
            **self.spec.to_public(),
            "retrieved_at": self.retrieved_at.isoformat(),
            "published_sha256": self.published_sha256,
            "actual_sha256": self.actual_sha256,
            "checksum_match": self.published_sha256 == self.actual_sha256,
            "archive_bytes": len(self.archive_bytes),
            "schema_version": SCHEMA_VERSION,
            "ingestion_version": NORMALIZATION_VERSION,
        }


@dataclass(frozen=True)
class MergeResult:
    bars: tuple[HistoricalBar, ...]
    identical_duplicate_count: int
    duplicate_provenance: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class ContinuityAudit:
    instrument_id: str
    expected_intervals: int
    observed_intervals: int
    missing_intervals: tuple[datetime, ...]
    duplicate_intervals: tuple[datetime, ...]
    out_of_order: bool

    def to_public(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "expected_intervals": self.expected_intervals,
            "observed_intervals": self.observed_intervals,
            "missing_count": len(self.missing_intervals),
            "missing_intervals": [value.isoformat() for value in self.missing_intervals],
            "duplicate_count": len(self.duplicate_intervals),
            "duplicate_intervals": [value.isoformat() for value in self.duplicate_intervals],
            "out_of_order": self.out_of_order,
            "missing_bars_synthesized": False,
        }


@dataclass(frozen=True)
class DatasetSplitFreeze:
    instrument_id: str
    observation_count: int
    train_end_index: int
    validation_end_index: int
    train_period: tuple[datetime, datetime]
    validation_period: tuple[datetime, datetime]
    test_period: tuple[datetime, datetime]
    walk_forward_policy: tuple[str, ...] = (
        "0-40/40-50/50-60",
        "0-60/60-70/70-80",
    )

    def to_public(self) -> dict[str, object]:
        def period(value: tuple[datetime, datetime]) -> dict[str, str]:
            return {"start": value[0].isoformat(), "end": value[1].isoformat()}

        return {
            "instrument_id": self.instrument_id,
            "observation_count": self.observation_count,
            "train": period(self.train_period),
            "validation": period(self.validation_period),
            "test": period(self.test_period),
            "train_end_index_exclusive": self.train_end_index,
            "validation_end_index_exclusive": self.validation_end_index,
            "walk_forward_policy": list(self.walk_forward_policy),
            "strategy_returns_evaluated": False,
        }


@dataclass(frozen=True)
class DatasetCertification:
    dataset_id: str
    dataset_version: str
    content_checksum: str
    source_revision_checksum: str
    canonical_manifest: DatasetManifest
    policy: AcquisitionPolicy
    bars: tuple[HistoricalBar, ...]
    source_archives: tuple[dict[str, object], ...]
    continuity: Mapping[str, ContinuityAudit]
    split_freezes: Mapping[str, DatasetSplitFreeze]
    quality_status: DatasetQualityStatus
    limitations: tuple[str, ...]
    data_mode: str = "HISTORICAL"
    performance_evaluations: int = 0
    test_periods_spent: int = 0

    def to_public(self) -> dict[str, object]:
        hashes = {
            instrument: canonical_historical_hash(
                bar for bar in self.bars if bar.instrument_id == instrument
            )
            for instrument in sorted(self.continuity)
        }
        return {
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "content_checksum": self.content_checksum,
            "instrument_content_checksums": hashes,
            "source_revision_checksum": self.source_revision_checksum,
            "data_mode": self.data_mode,
            "quality_status": self.quality_status.value,
            "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
            "source_schema_version": SCHEMA_VERSION,
            "normalization_version": NORMALIZATION_VERSION,
            "canonical_manifest": self.canonical_manifest.to_public(),
            "policy": self.policy.to_public(),
            "source_archives": list(self.source_archives),
            "bar_count": len(self.bars),
            "continuity": {
                instrument: report.to_public()
                for instrument, report in sorted(self.continuity.items())
            },
            "split_freezes": {
                instrument: split.to_public()
                for instrument, split in sorted(self.split_freezes.items())
            },
            "point_in_time_policy": {
                "event_timestamp": "BAR_OPEN_UTC",
                "as_of": "EXCLUSIVE_BAR_CLOSE_UTC",
                "available_at": "EXCLUSIVE_BAR_CLOSE_UTC",
                "received_at": "ACTUAL_ARCHIVE_RETRIEVAL_UTC",
                "historical_archive_publication_precision": "NOT_RECONSTRUCTED",
                "future_bar_values_visible_early": False,
            },
            "limitations": list(self.limitations),
            "performance_evaluations": self.performance_evaluations,
            "test_periods_spent": self.test_periods_spent,
            "live_data": False,
            "replay_fixture": False,
            "synthetic": False,
            "private_account": False,
        }


def _next_month(value: date) -> date:
    return date(value.year + 1, 1, 1) if value.month == 12 else date(value.year, value.month + 1, 1)


def _aware_utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _published_checksum(checksum_bytes: bytes, expected_filename: str) -> str:
    if len(checksum_bytes) > MAX_CHECKSUM_BYTES:
        raise ArchiveFormatError("checksum response is oversized")
    try:
        text = checksum_bytes.decode("ascii", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise ArchiveFormatError("checksum is not ASCII") from exc
    match = re.fullmatch(r"([0-9a-fA-F]{64})\s+([^\s]+)", text)
    if match is None or match.group(2) != expected_filename:
        raise ArchiveFormatError("checksum record does not name the exact archive")
    return match.group(1).lower()


def verify_source_archive(
    spec: ArchiveSpec,
    archive_bytes: bytes,
    checksum_bytes: bytes,
    *,
    retrieved_at: datetime,
) -> VerifiedArchive:
    retrieved = _aware_utc(retrieved_at, name="retrieved_at")
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise OversizedArchiveError("compressed archive exceeds bounded size policy")
    expected = _published_checksum(checksum_bytes, spec.filename)
    actual = sha256(archive_bytes).hexdigest()
    if expected != actual:
        raise ChecksumMismatchError(expected, actual)
    return VerifiedArchive(
        spec=spec,
        archive_bytes=archive_bytes,
        checksum_bytes=checksum_bytes,
        published_sha256=expected,
        actual_sha256=actual,
        retrieved_at=retrieved,
    )


def _timestamp(raw: str) -> tuple[datetime, str, timedelta]:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ArchiveFormatError("timestamp is not an integer") from exc
    if 1_000_000_000_000_000 <= value < 10_000_000_000_000_000:
        scale = 1_000_000
        unit = "microseconds"
        quantum = timedelta(microseconds=1)
    elif 1_000_000_000_000 <= value < 10_000_000_000_000:
        scale = 1_000
        unit = "milliseconds"
        quantum = timedelta(milliseconds=1)
    else:
        raise ArchiveFormatError("timestamp unit is ambiguous or out of range")
    seconds, remainder = divmod(value, scale)
    micros = remainder if scale == 1_000_000 else remainder * 1_000
    return datetime.fromtimestamp(seconds, UTC) + timedelta(microseconds=micros), unit, quantum


def _decimal(raw: str, *, name: str, positive: bool = False) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ArchiveFormatError(f"{name} is not a decimal") from exc
    if not value.is_finite():
        raise ArchiveFormatError(f"{name} is not finite")
    if positive and value <= 0:
        raise ArchiveFormatError(f"{name} must be positive")
    if not positive and value < 0:
        raise ArchiveFormatError(f"{name} must not be negative")
    return value


def _validated_zip_payload(verified: VerifiedArchive) -> bytes:
    try:
        with ZipFile(BytesIO(verified.archive_bytes)) as archive:
            infos = archive.infolist()
            if len(infos) != 1:
                raise ZipSecurityError("archive must contain exactly one CSV member")
            info = infos[0]
            member = PurePosixPath(info.filename)
            if (
                info.is_dir()
                or info.filename != verified.spec.csv_filename
                or member.is_absolute()
                or ".." in member.parts
                or len(member.parts) != 1
            ):
                raise ZipSecurityError("archive member path is unexpected or unsafe")
            if info.flag_bits & 0x1:
                raise ZipSecurityError("encrypted archive members are forbidden")
            if info.file_size > MAX_EXPANDED_BYTES:
                raise OversizedArchiveError("archive expansion exceeds bounded size policy")
            payload = archive.read(info)
    except BadZipFile as exc:
        raise ArchiveFormatError("source is not a valid ZIP archive") from exc
    if len(payload) > MAX_EXPANDED_BYTES:
        raise OversizedArchiveError("expanded payload exceeds bounded size policy")
    return payload


def normalize_verified_archive(verified: VerifiedArchive) -> tuple[HistoricalBar, ...]:
    payload = _validated_zip_payload(verified)
    try:
        decoded = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ArchiveFormatError("CSV is not strict UTF-8") from exc
    rows = [row for row in csv.reader(StringIO(decoded, newline="")) if row]
    if len(rows) > MAX_MONTHLY_ROWS:
        raise OversizedArchiveError("monthly daily-kline row count exceeds policy")
    if not rows:
        raise ArchiveFormatError("archive contains no kline rows")

    bars: list[HistoricalBar] = []
    prior_open: datetime | None = None
    for index, row in enumerate(rows):
        if len(row) != 12:
            raise ArchiveFormatError("kline row must contain exactly 12 columns")
        opened, open_unit, _ = _timestamp(row[0])
        closed, close_unit, close_quantum = _timestamp(row[6])
        expected_unit = "microseconds" if opened.date() >= date(2025, 1, 1) else "milliseconds"
        if open_unit != expected_unit or close_unit != expected_unit:
            raise ArchiveFormatError("timestamp unit conflicts with official Spot archive policy")
        close_exclusive = closed + close_quantum
        if opened.tzinfo is None or close_exclusive.tzinfo is None:
            raise ArchiveFormatError("timestamps must normalize to timezone-aware UTC")
        if opened.time() != datetime.min.time() or close_exclusive - opened != timedelta(days=1):
            raise ArchiveFormatError("impossible daily kline open/close interval")
        if prior_open is not None and opened < prior_open:
            raise ArchiveFormatError("archive rows are out of order")
        prior_open = opened

        open_price = _decimal(row[1], name="open", positive=True)
        high = _decimal(row[2], name="high", positive=True)
        low = _decimal(row[3], name="low", positive=True)
        close = _decimal(row[4], name="close", positive=True)
        volume = _decimal(row[5], name="volume")
        _decimal(row[7], name="quote asset volume")
        try:
            trades = int(row[8])
        except ValueError as exc:
            raise ArchiveFormatError("number of trades is not an integer") from exc
        if trades < 0:
            raise ArchiveFormatError("number of trades must not be negative")
        _decimal(row[9], name="taker buy base volume")
        _decimal(row[10], name="taker buy quote volume")
        _decimal(row[11], name="ignore")
        if high < max(open_price, close, low) or low > min(open_price, close, high):
            raise ArchiveFormatError("invalid OHLC ordering")
        if verified.retrieved_at < close_exclusive:
            raise ArchiveFormatError("archive retrieval precedes the bar close")

        instrument_id = SUPPORTED_SYMBOLS[verified.spec.symbol]
        source_record_id = f"{instrument_id}:{verified.spec.interval}:{opened.isoformat()}"
        revision_id = sha256(
            f"{verified.actual_sha256}:{index}:{source_record_id}".encode("utf-8")
        ).hexdigest()
        bars.append(
            HistoricalBar(
                instrument_id=instrument_id,
                venue="BINANCE",
                asset_class=AssetClass.CRYPTO,
                currency="USDT",
                point_in_time=PointInTime(
                    event_timestamp=opened,
                    as_of=close_exclusive,
                    available_at=close_exclusive,
                    received_at=verified.retrieved_at,
                ),
                provider=ProviderReference(
                    provider="BINANCE_PUBLIC_DATA_ARCHIVE",
                    provider_event_id=source_record_id,
                    sequence=index,
                    source_ref=verified.spec.source_path,
                    is_delayed=True,
                    delay_seconds=int((verified.retrieved_at - close_exclusive).total_seconds()),
                ),
                quality=DataQuality.VALID,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
                timeframe=verified.spec.interval,
                source_record_id=source_record_id,
                revision_id=revision_id,
            )
        )
    return tuple(bars)


def _bar_values(bar: HistoricalBar) -> tuple[object, ...]:
    return (
        bar.instrument_id,
        bar.venue,
        bar.asset_class,
        bar.currency,
        bar.point_in_time.event_timestamp,
        bar.as_of,
        bar.available_at,
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume,
        bar.timeframe,
        bar.status,
    )


def merge_historical_bars(bars: Iterable[HistoricalBar]) -> MergeResult:
    grouped: dict[str, list[HistoricalBar]] = {}
    for bar in bars:
        grouped.setdefault(bar.source_record_id, []).append(bar)
    selected: list[HistoricalBar] = []
    duplicate_provenance: list[tuple[str, tuple[str, ...]]] = []
    duplicate_count = 0
    for record_id, revisions in grouped.items():
        reference = revisions[0]
        if any(_bar_values(candidate) != _bar_values(reference) for candidate in revisions[1:]):
            raise ConflictingRevisionError(f"conflicting contents for {record_id}")
        winner = min(revisions, key=lambda bar: (bar.provider.source_ref, bar.revision_id))
        selected.append(winner)
        if len(revisions) > 1:
            duplicate_count += len(revisions) - 1
            duplicate_provenance.append(
                (record_id, tuple(sorted(bar.provider.source_ref for bar in revisions)))
            )
    selected.sort(key=lambda bar: (bar.instrument_id, bar.point_in_time.event_timestamp))
    return MergeResult(
        bars=tuple(selected),
        identical_duplicate_count=duplicate_count,
        duplicate_provenance=tuple(sorted(duplicate_provenance)),
    )


def canonical_historical_hash(bars: Iterable[HistoricalBar]) -> str:
    payload: list[dict[str, object]] = []
    for bar in sorted(bars, key=lambda value: (value.instrument_id, value.point_in_time.event_timestamp)):
        row = bar.to_dict()
        point_in_time = dict(row["point_in_time"])
        point_in_time.pop("received_at", None)
        row["point_in_time"] = point_in_time
        payload.append(row)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def audit_continuity(
    bars: Sequence[HistoricalBar], coverage_start: date, coverage_end: date
) -> ContinuityAudit:
    if coverage_start > coverage_end:
        raise ValueError("coverage start is after coverage end")
    instrument_ids = {bar.instrument_id for bar in bars}
    if len(instrument_ids) > 1:
        raise ValueError("continuity must be audited one instrument at a time")
    ordered_input = [bar.point_in_time.event_timestamp for bar in bars]
    observed = set(ordered_input)
    cursor = datetime(coverage_start.year, coverage_start.month, coverage_start.day, tzinfo=UTC)
    final = datetime(coverage_end.year, coverage_end.month, coverage_end.day, tzinfo=UTC)
    expected: list[datetime] = []
    while cursor <= final:
        expected.append(cursor)
        cursor += timedelta(days=1)
    duplicates = tuple(sorted(value for value in observed if ordered_input.count(value) > 1))
    return ContinuityAudit(
        instrument_id=next(iter(instrument_ids), ""),
        expected_intervals=len(expected),
        observed_intervals=len(observed),
        missing_intervals=tuple(value for value in expected if value not in observed),
        duplicate_intervals=duplicates,
        out_of_order=ordered_input != sorted(ordered_input),
    )


def _freeze_splits(bars: Sequence[HistoricalBar]) -> DatasetSplitFreeze:
    if len(bars) < 6:
        raise DatasetCertificationError("at least six observations are required to freeze splits")
    train_end = int(len(bars) * 0.60)
    validation_end = int(len(bars) * 0.80)
    return DatasetSplitFreeze(
        instrument_id=bars[0].instrument_id,
        observation_count=len(bars),
        train_end_index=train_end,
        validation_end_index=validation_end,
        train_period=(bars[0].as_of, bars[train_end - 1].as_of),
        validation_period=(bars[train_end].as_of, bars[validation_end - 1].as_of),
        test_period=(bars[validation_end].as_of, bars[-1].as_of),
    )


def _source_revision_checksum(
    archives: Sequence[VerifiedArchive], policy: AcquisitionPolicy
) -> str:
    source = {
        archive.spec.source_path: archive.actual_sha256
        for archive in sorted(archives, key=lambda value: value.spec)
    }
    encoded = json.dumps(
        {
            "normalization_version": NORMALIZATION_VERSION,
            "policy": policy.to_public(),
            "source_checksums": source,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def certify_verified_archives(
    archives: Sequence[VerifiedArchive], policy: AcquisitionPolicy
) -> DatasetCertification:
    if not archives:
        raise DatasetCertificationError("no verified source archives supplied")
    expected_specs = set(policy.archive_specs())
    actual_specs = [archive.spec for archive in archives]
    if len(set(actual_specs)) != len(actual_specs):
        raise DatasetCertificationError("duplicate source archive identity")
    if any(spec not in expected_specs for spec in actual_specs):
        raise DatasetCertificationError("source archive falls outside the frozen policy")
    if any(archive.published_sha256 != archive.actual_sha256 for archive in archives):
        raise ChecksumMismatchError("verified", "mismatch")

    normalized: list[HistoricalBar] = []
    for archive in sorted(archives, key=lambda value: value.spec):
        normalized.extend(normalize_verified_archive(archive))
    normalized = [
        bar
        for bar in normalized
        if policy.coverage_start <= bar.point_in_time.event_timestamp.date() <= policy.coverage_end
    ]
    merged = merge_historical_bars(normalized)

    continuity: dict[str, ContinuityAudit] = {}
    splits: dict[str, DatasetSplitFreeze] = {}
    insufficient = set(actual_specs) != expected_specs
    for symbol in policy.symbols:
        instrument = SUPPORTED_SYMBOLS[symbol]
        instrument_bars = tuple(bar for bar in merged.bars if bar.instrument_id == instrument)
        report = audit_continuity(instrument_bars, policy.coverage_start, policy.coverage_end)
        if not report.instrument_id:
            report = ContinuityAudit(
                instrument_id=instrument,
                expected_intervals=report.expected_intervals,
                observed_intervals=report.observed_intervals,
                missing_intervals=report.missing_intervals,
                duplicate_intervals=report.duplicate_intervals,
                out_of_order=report.out_of_order,
            )
        continuity[instrument] = report
        if len(instrument_bars) >= 6:
            splits[instrument] = _freeze_splits(instrument_bars)
        if (
            len(instrument_bars) < MIN_QUALIFICATION_BARS
            or report.missing_intervals
            or report.duplicate_intervals
            or report.out_of_order
        ):
            insufficient = True

    source_revision = _source_revision_checksum(archives, policy)
    version = f"sha256-{source_revision}"
    symbol_component = "-".join(symbol.lower() for symbol in policy.symbols)
    dataset_id = (
        f"binance-spot-{policy.interval}-{policy.coverage_start.isoformat()}-"
        f"{policy.coverage_end.isoformat()}-{symbol_component}"
    )
    content_checksum = canonical_historical_hash(merged.bars)
    quality = (
        DatasetQualityStatus.INSUFFICIENT_COVERAGE
        if insufficient
        else DatasetQualityStatus.CERTIFIED_REAL_HISTORICAL
    )
    notes = [
        "Official Binance public Spot monthly kline archives; every ZIP SHA-256 matched its companion checksum.",
        "Raw archives are retained byte-for-byte and made read-only by local policy.",
        "Historical archive publication instants are not reconstructed; bars become visible only at exclusive bar close.",
        f"Identical archive-boundary rows deduplicated: {merged.identical_duplicate_count}.",
    ]
    canonical_manifest = DatasetManifest(
        dataset_id=dataset_id,
        version=version,
        market="BINANCE_SPOT",
        currency="USDT",
        timezone="UTC",
        timeframe=policy.interval,
        instrument_universe=[SUPPORTED_SYMBOLS[symbol] for symbol in policy.symbols],
        classification=DatasetClassification.HISTORICAL_AUTHENTICATED,
        adjustment_methodology=AdjustmentMethodology.NONE,
        calendar_name="CRYPTO_24_7",
        calendar_version="crypto-24x7-v1",
        calendar_source_version="BINANCE_SPOT",
        calendar_coverage_status="COMPLETE" if not insufficient else "INCOMPLETE",
        calendar_policy="ONE_UTC_BAR_PER_CALENDAR_DAY",
        source=DatasetSource(
            adapter="binance_public_archive",
            uri=OFFICIAL_ARCHIVE_BASE,
            read_only=True,
            credentials_required=False,
            network_required=True,
            provenance_notes=[OFFICIAL_DOCUMENTATION, "SPOT_ONLY", "PUBLIC_NO_CREDENTIALS"],
        ),
        notes=notes,
    )
    limitations = (
        "ARCHIVE_PUBLICATION_HISTORY_NOT_RECONSTRUCTED",
        "BAR_CLOSE_AVAILABILITY_PRECISION",
        "OFFICIAL_ARCHIVES_MAY_PUBLISH_LATER_REVISIONS",
    )
    evidence = tuple(
        archive.to_evidence() for archive in sorted(archives, key=lambda value: value.spec)
    )
    return DatasetCertification(
        dataset_id=dataset_id,
        dataset_version=version,
        content_checksum=content_checksum,
        source_revision_checksum=source_revision,
        canonical_manifest=canonical_manifest,
        policy=policy,
        bars=merged.bars,
        source_archives=evidence,
        continuity=continuity,
        split_freezes=splits,
        quality_status=quality,
        limitations=limitations,
    )


def _write_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o444)


def persist_certification(
    certification: DatasetCertification,
    archives: Sequence[VerifiedArchive],
    *,
    root: Path,
) -> Path:
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    final = root / certification.dataset_version
    expected_manifest = json.dumps(
        certification.to_public(), sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
    if final.exists():
        manifest_path = final / "manifest.json"
        if manifest_path.is_file() and manifest_path.read_bytes() == expected_manifest:
            return final
        raise DatasetCertificationError("dataset version path exists with different contents")

    by_path = {archive.spec.source_path: archive for archive in archives}
    evidence_paths = {str(item["source_reference"]) for item in certification.source_archives}
    if len(by_path) != len(archives) or len(evidence_paths) != len(archives):
        raise DatasetCertificationError("persisted archive set does not match certification")

    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=root))
    try:
        for archive in sorted(archives, key=lambda value: value.spec):
            raw_dir = staging / "raw" / archive.spec.symbol
            _write_once(raw_dir / archive.spec.filename, archive.archive_bytes)
            _write_once(raw_dir / archive.spec.checksum_filename, archive.checksum_bytes)

        for instrument in sorted(certification.continuity):
            symbol = next(symbol for symbol, value in SUPPORTED_SYMBOLS.items() if value == instrument)
            rows = [bar for bar in certification.bars if bar.instrument_id == instrument]
            payload = b"".join(
                json.dumps(bar.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
                for bar in rows
            )
            _write_once(staging / "canonical" / f"{symbol}-{certification.policy.interval}.jsonl", payload)

        _write_once(staging / "manifest.json", expected_manifest)
        _write_once(
            staging / "quality-report.json",
            json.dumps(
                {
                    "quality_status": certification.quality_status.value,
                    "continuity": {
                        key: value.to_public() for key, value in sorted(certification.continuity.items())
                    },
                    "limitations": list(certification.limitations),
                },
                sort_keys=True,
                indent=2,
            ).encode("utf-8") + b"\n",
        )
        staging.rename(final)
    except Exception:
        # Preserve a failed staging directory for forensic review; never replace
        # an existing certified revision or silently discard suspect bytes.
        raise
    return final


def load_persisted_certification(location: Path) -> DatasetCertification:
    location = Path(location).resolve()
    manifest = json.loads((location / "manifest.json").read_text(encoding="utf-8"))
    policy_data = manifest["policy"]
    policy = AcquisitionPolicy(
        symbols=tuple(policy_data["symbols"]),
        interval=policy_data["interval"],
        coverage_start=date.fromisoformat(policy_data["coverage_start"]),
        coverage_end=date.fromisoformat(policy_data["coverage_end"]),
    )
    archives: list[VerifiedArchive] = []
    for item in manifest["source_archives"]:
        spec = ArchiveSpec(
            item["symbol"], item["interval"], int(item["year"]), int(item["month"])
        )
        raw_dir = location / "raw" / spec.symbol
        archives.append(
            verify_source_archive(
                spec,
                (raw_dir / spec.filename).read_bytes(),
                (raw_dir / spec.checksum_filename).read_bytes(),
                retrieved_at=datetime.fromisoformat(item["retrieved_at"]),
            )
        )
    reproduced = certify_verified_archives(tuple(archives), policy)
    if location.name != reproduced.dataset_version:
        raise DatasetCertificationError("dataset directory does not match its immutable version")
    if reproduced.to_public() != manifest:
        raise DatasetCertificationError("manifest does not reproduce from retained source archives")
    for instrument in sorted(reproduced.continuity):
        symbol = next(symbol for symbol, value in SUPPORTED_SYMBOLS.items() if value == instrument)
        expected = b"".join(
            json.dumps(bar.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
            for bar in reproduced.bars
            if bar.instrument_id == instrument
        )
        canonical_path = location / "canonical" / f"{symbol}-{policy.interval}.jsonl"
        if canonical_path.read_bytes() != expected:
            raise DatasetCertificationError("normalized canonical file is not reproducible")
    return reproduced


def verify_persisted_reproducibility(location: Path) -> bool:
    location = Path(location).resolve()
    manifest = json.loads((location / "manifest.json").read_text(encoding="utf-8"))
    reproduced = load_persisted_certification(location)
    return (
        reproduced.dataset_id == manifest["dataset_id"]
        and reproduced.dataset_version == manifest["dataset_version"]
        and reproduced.content_checksum == manifest["content_checksum"]
        and reproduced.source_revision_checksum == manifest["source_revision_checksum"]
    )


def _fetch_bounded(url: str, *, maximum_bytes: int) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != OFFICIAL_ARCHIVE_HOST:
        raise ValueError("only the official Binance HTTPS archive host is allowed")
    request = Request(url, headers={"User-Agent": "SaathiOS-CRYPTO-DATASET-1/1.0"})
    with urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != OFFICIAL_ARCHIVE_HOST:
            raise DatasetCertificationError("archive redirected away from the official host")
        declared = response.headers.get("Content-Length")
        if declared is not None and int(declared) > maximum_bytes:
            raise OversizedArchiveError("declared source size exceeds policy")
        payload = response.read(maximum_bytes + 1)
    if len(payload) > maximum_bytes:
        raise OversizedArchiveError("downloaded source size exceeds policy")
    return payload


def _quarantine_checksum_failure(
    root: Path,
    spec: ArchiveSpec,
    payload: bytes,
    failure: ChecksumMismatchError,
) -> Path:
    quarantine = Path(root).resolve() / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    target = quarantine / f"{spec.filename}.{failure.actual_sha256}.quarantined"
    _write_once(target, payload)
    _write_once(
        target.with_suffix(target.suffix + ".json"),
        json.dumps(
            {
                "quality_status": DatasetQualityStatus.CHECKSUM_FAILED.value,
                "source_reference": spec.url,
                "expected_sha256": failure.expected_sha256,
                "actual_sha256": failure.actual_sha256,
                "ingested": False,
            },
            sort_keys=True,
            indent=2,
        ).encode("utf-8") + b"\n",
    )
    return target


ProgressCallback = Callable[[int, int, ArchiveSpec], None]


def acquire_official_dataset(
    *,
    root: Path,
    policy: AcquisitionPolicy | None = None,
    retrieved_at: datetime | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[DatasetCertification, Path]:
    selected = policy or AcquisitionPolicy()
    retrieval = _aware_utc(retrieved_at or datetime.now(UTC), name="retrieved_at")
    specs = selected.archive_specs()
    verified: list[VerifiedArchive] = []
    for index, spec in enumerate(specs, start=1):
        checksum_bytes = _fetch_bounded(spec.checksum_url, maximum_bytes=MAX_CHECKSUM_BYTES)
        archive_bytes = _fetch_bounded(spec.url, maximum_bytes=MAX_ARCHIVE_BYTES)
        try:
            verified.append(
                verify_source_archive(
                    spec,
                    archive_bytes,
                    checksum_bytes,
                    retrieved_at=retrieval,
                )
            )
        except ChecksumMismatchError as failure:
            _quarantine_checksum_failure(root, spec, archive_bytes, failure)
            raise
        if progress is not None:
            progress(index, len(specs), spec)
    certification = certify_verified_archives(tuple(verified), selected)
    location = persist_certification(certification, tuple(verified), root=Path(root))
    if not verify_persisted_reproducibility(location):
        raise DatasetCertificationError("persisted dataset failed reproducibility verification")
    return certification, location


def default_dataset_root() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "historical" / "certified" / "crypto-dataset-1"


def _progress(index: int, total: int, spec: ArchiveSpec) -> None:
    if index == 1 or index == total or index % 12 == 0:
        print(f"verified {index}/{total}: {spec.filename}", flush=True)


def main() -> int:
    certification, location = acquire_official_dataset(
        root=default_dataset_root(),
        policy=AcquisitionPolicy(),
        progress=_progress,
    )
    print(
        json.dumps(
            {
                "dataset_id": certification.dataset_id,
                "dataset_version": certification.dataset_version,
                "quality_status": certification.quality_status.value,
                "bar_count": len(certification.bars),
                "content_checksum": certification.content_checksum,
                "location": str(location),
                "performance_evaluations": certification.performance_evaluations,
                "test_periods_spent": certification.test_periods_spent,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
