"""M185 — Versioned historical-market-data domain entities.

Dataset versions are immutable after acceptance. Raw prices are never overwritten.
Paper research only — no live trading authority.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


SCHEMA_VERSION = "m184.tg.historical.v1"


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _now() -> float:
    return time.time()


def fingerprint_payload(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DatasetClassification(str, Enum):
    """Mirrors data_contract classifications with explicit historical focus."""

    HISTORICAL_AUTHENTICATED = "HISTORICAL_AUTHENTICATED"
    HISTORICAL_LOCAL_DATASET = "HISTORICAL_LOCAL_DATASET"
    SYNTHETIC_VALIDATION = "SYNTHETIC_VALIDATION"
    FIXTURE_TEST_ONLY = "FIXTURE_TEST_ONLY"
    INCOMPLETE = "INCOMPLETE"
    REJECTED = "REJECTED"


class DataQualityVerdict(str, Enum):
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_WARNINGS = "ACCEPTED_WITH_WARNINGS"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"
    INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"


class CorporateActionType(str, Enum):
    SPLIT = "SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    DIVIDEND = "DIVIDEND"
    SYMBOL_CHANGE = "SYMBOL_CHANGE"
    MERGER = "MERGER"
    DELISTING = "DELISTING"


class AdjustmentMethodology(str, Enum):
    NONE = "NONE"
    SPLIT_ONLY = "SPLIT_ONLY"
    TOTAL_RETURN = "TOTAL_RETURN"
    OPERATOR_SUPPLIED = "OPERATOR_SUPPLIED"


class ImportStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    NORMALIZING = "NORMALIZING"
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_WARNINGS = "ACCEPTED_WITH_WARNINGS"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


@dataclass
class InstrumentMetadata:
    symbol: str
    canonical_symbol: str
    market: str = ""
    currency: str = "USD"
    sector: str = ""
    asset_class: str = "EQUITY"
    timezone: str = "UTC"
    status: str = "active"  # active | delisted | renamed
    notes: list[str] = field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "canonical_symbol": self.canonical_symbol,
            "market": self.market,
            "currency": self.currency,
            "sector": self.sector,
            "asset_class": self.asset_class,
            "timezone": self.timezone,
            "status": self.status,
            "notes": list(self.notes),
        }


@dataclass
class TradingSession:
    name: str
    open_local: str  # HH:MM
    close_local: str
    timezone: str = "UTC"
    weekdays: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])

    def to_public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "open_local": self.open_local,
            "close_local": self.close_local,
            "timezone": self.timezone,
            "weekdays": list(self.weekdays),
        }


@dataclass
class MarketCalendarSpec:
    name: str
    timezone: str
    session: TradingSession
    holidays: list[str] = field(default_factory=list)  # YYYY-MM-DD
    notes: list[str] = field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "timezone": self.timezone,
            "session": self.session.to_public(),
            "holidays": list(self.holidays),
            "notes": list(self.notes),
        }


@dataclass
class CorporateAction:
    id: str = field(default_factory=lambda: _id("ca"))
    instrument: str = ""
    action_type: CorporateActionType = CorporateActionType.SPLIT
    effective_date: str = ""  # YYYY-MM-DD
    factor: str = "1"  # Decimal as string
    cash_amount: str = "0"
    old_symbol: str = ""
    new_symbol: str = ""
    source: str = ""
    notes: list[str] = field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "instrument": self.instrument,
            "action_type": self.action_type.value,
            "effective_date": self.effective_date,
            "factor": self.factor,
            "cash_amount": self.cash_amount,
            "old_symbol": self.old_symbol,
            "new_symbol": self.new_symbol,
            "source": self.source,
            "notes": list(self.notes),
        }


@dataclass
class AdjustedPriceBar:
    """Raw + adjusted OHLC; raw is never mutated by normalization."""

    instrument: str
    ts: float
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    adj_open: Decimal | None = None
    adj_high: Decimal | None = None
    adj_low: Decimal | None = None
    adj_close: Decimal | None = None
    adj_factor: Decimal = field(default_factory=lambda: Decimal("1"))
    timeframe: str = "1d"
    currency: str = "USD"
    source: str = ""
    quality: str = "VALID"

    def to_public(self) -> dict[str, Any]:
        return {
            "instrument": self.instrument,
            "ts": self.ts,
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
            "adj_open": str(self.adj_open) if self.adj_open is not None else None,
            "adj_high": str(self.adj_high) if self.adj_high is not None else None,
            "adj_low": str(self.adj_low) if self.adj_low is not None else None,
            "adj_close": str(self.adj_close) if self.adj_close is not None else None,
            "adj_factor": str(self.adj_factor),
            "timeframe": self.timeframe,
            "currency": self.currency,
            "source": self.source,
            "quality": self.quality,
            "raw_preserved": True,
        }


@dataclass
class DatasetCoverage:
    date_start: float | None = None
    date_end: float | None = None
    trading_days: int = 0
    calendar_days: int = 0
    instruments: list[str] = field(default_factory=list)
    missing_sessions: int = 0
    coverage_ratio: float = 0.0

    def to_public(self) -> dict[str, Any]:
        return {
            "date_start": self.date_start,
            "date_end": self.date_end,
            "trading_days": self.trading_days,
            "calendar_days": self.calendar_days,
            "instruments": list(self.instruments),
            "missing_sessions": self.missing_sessions,
            "coverage_ratio": self.coverage_ratio,
        }


@dataclass
class DataQualityReport:
    verdict: DataQualityVerdict = DataQualityVerdict.REJECTED
    score: float = 0.0  # 0..1 visible component, never sole gate
    findings: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    missing_bar_count: int = 0
    duplicate_bar_count: int = 0
    outlier_count: int = 0
    invalid_ohlc_count: int = 0
    zero_price_count: int = 0
    negative_volume_count: int = 0
    corporate_action_status: str = "UNKNOWN"
    warnings: list[str] = field(default_factory=list)
    evaluated_at: float = field(default_factory=_now)

    def to_public(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "score": self.score,
            "findings": list(self.findings),
            "row_count": self.row_count,
            "missing_bar_count": self.missing_bar_count,
            "duplicate_bar_count": self.duplicate_bar_count,
            "outlier_count": self.outlier_count,
            "invalid_ohlc_count": self.invalid_ohlc_count,
            "zero_price_count": self.zero_price_count,
            "negative_volume_count": self.negative_volume_count,
            "corporate_action_status": self.corporate_action_status,
            "warnings": list(self.warnings),
            "evaluated_at": self.evaluated_at,
            "promotable": self.verdict in (
                DataQualityVerdict.ACCEPTED,
                DataQualityVerdict.ACCEPTED_WITH_WARNINGS,
            ),
        }


@dataclass
class DatasetFingerprint:
    content_fingerprint: str = ""
    source_file_fingerprint: str = ""
    schema_fingerprint: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "content_fingerprint": self.content_fingerprint,
            "source_file_fingerprint": self.source_file_fingerprint,
            "schema_fingerprint": self.schema_fingerprint,
        }


@dataclass
class DatasetQuarantineRecord:
    id: str = field(default_factory=lambda: _id("qtn"))
    dataset_id: str = ""
    version: str = ""
    reason: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=_now)
    org_id: str = ""
    workspace_id: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "version": self.version,
            "reason": self.reason,
            "findings": list(self.findings),
            "created_at": self.created_at,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "usable_for_promotion": False,
        }


@dataclass
class DatasetSource:
    adapter: str  # local_csv | local_parquet | binance_public | yahoo_public | nepse_local
    uri: str = ""  # local path or public endpoint label (never credentials)
    read_only: bool = True
    credentials_required: bool = False
    network_required: bool = False
    provenance_notes: list[str] = field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "uri": self.uri,
            "read_only": True,
            "credentials_required": False,  # always false for TG historical adapters
            "network_required": self.network_required,
            "provenance_notes": list(self.provenance_notes),
            "live_trading": False,
        }


@dataclass
class DatasetManifest:
    schema_version: str = SCHEMA_VERSION
    dataset_id: str = ""
    version: str = "1.0.0"
    market: str = ""
    currency: str = "USD"
    timezone: str = "UTC"
    timeframe: str = "1d"
    instrument_universe: list[str] = field(default_factory=list)
    classification: DatasetClassification = DatasetClassification.INCOMPLETE
    adjustment_methodology: AdjustmentMethodology = AdjustmentMethodology.NONE
    calendar_name: str = "DEFAULT_24_5"
    corporate_actions: list[CorporateAction] = field(default_factory=list)
    source: DatasetSource | None = None
    notes: list[str] = field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "version": self.version,
            "market": self.market,
            "currency": self.currency,
            "timezone": self.timezone,
            "timeframe": self.timeframe,
            "instrument_universe": list(self.instrument_universe),
            "classification": self.classification.value,
            "adjustment_methodology": self.adjustment_methodology.value,
            "calendar_name": self.calendar_name,
            "corporate_actions": [c.to_public() for c in self.corporate_actions],
            "source": self.source.to_public() if self.source else None,
            "notes": list(self.notes),
        }


@dataclass
class DatasetVersion:
    """Immutable after acceptance."""

    id: str = field(default_factory=lambda: _id("dsver"))
    dataset_id: str = ""
    version: str = "1.0.0"
    schema_version: str = SCHEMA_VERSION
    status: ImportStatus = ImportStatus.PENDING
    classification: DatasetClassification = DatasetClassification.INCOMPLETE
    fingerprint: DatasetFingerprint = field(default_factory=DatasetFingerprint)
    coverage: DatasetCoverage = field(default_factory=DatasetCoverage)
    quality: DataQualityReport = field(default_factory=DataQualityReport)
    manifest: DatasetManifest = field(default_factory=DatasetManifest)
    row_count: int = 0
    missing_bar_count: int = 0
    duplicate_bar_count: int = 0
    outlier_count: int = 0
    corporate_action_status: str = "UNKNOWN"
    adjustment_methodology: str = AdjustmentMethodology.NONE.value
    import_timestamp: float = field(default_factory=_now)
    normalization_timestamp: float | None = None
    accepted_at: float | None = None
    immutable: bool = False
    org_id: str = ""
    workspace_id: str = ""
    market: str = ""
    currency: str = "USD"
    timezone: str = "UTC"
    timeframe: str = "1d"
    instrument_universe: list[str] = field(default_factory=list)
    source_path: str = ""
    adapter: str = ""
    bars: list[AdjustedPriceBar] = field(default_factory=list, repr=False)
    transformations: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def accept(self, *, warnings: bool = False) -> None:
        if self.immutable:
            raise RuntimeError("dataset version is immutable")
        self.status = (
            ImportStatus.ACCEPTED_WITH_WARNINGS if warnings else ImportStatus.ACCEPTED
        )
        self.accepted_at = _now()
        self.immutable = True

    def quarantine(self, reason: str) -> None:
        if self.immutable and self.status in (ImportStatus.ACCEPTED, ImportStatus.ACCEPTED_WITH_WARNINGS):
            raise RuntimeError("cannot quarantine accepted immutable version")
        self.status = ImportStatus.QUARANTINED
        self.classification = DatasetClassification.REJECTED
        self.notes.append(f"quarantine:{reason}")

    def reject(self, reason: str) -> None:
        self.status = ImportStatus.REJECTED
        self.classification = DatasetClassification.REJECTED
        self.notes.append(f"reject:{reason}")
        # rejected versions are sealed against promotion but not "accepted"
        self.immutable = True

    @property
    def promotable(self) -> bool:
        return (
            self.immutable
            and self.status in (ImportStatus.ACCEPTED, ImportStatus.ACCEPTED_WITH_WARNINGS)
            and self.classification
            in (
                DatasetClassification.HISTORICAL_AUTHENTICATED,
                DatasetClassification.HISTORICAL_LOCAL_DATASET,
            )
            and self.quality.verdict
            in (DataQualityVerdict.ACCEPTED, DataQualityVerdict.ACCEPTED_WITH_WARNINGS)
        )

    def to_public(self, *, include_bars: bool = False) -> dict[str, Any]:
        out = {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "version": self.version,
            "schema_version": self.schema_version,
            "status": self.status.value,
            "classification": self.classification.value,
            "fingerprint": self.fingerprint.to_public(),
            "coverage": self.coverage.to_public(),
            "quality": self.quality.to_public(),
            "manifest": self.manifest.to_public(),
            "row_count": self.row_count,
            "missing_bar_count": self.missing_bar_count,
            "duplicate_bar_count": self.duplicate_bar_count,
            "outlier_count": self.outlier_count,
            "corporate_action_status": self.corporate_action_status,
            "adjustment_methodology": self.adjustment_methodology,
            "import_timestamp": self.import_timestamp,
            "normalization_timestamp": self.normalization_timestamp,
            "accepted_at": self.accepted_at,
            "immutable": self.immutable,
            "promotable": self.promotable,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "market": self.market,
            "currency": self.currency,
            "timezone": self.timezone,
            "timeframe": self.timeframe,
            "instrument_universe": list(self.instrument_universe),
            "source_path": self.source_path,
            "adapter": self.adapter,
            "transformations": list(self.transformations),
            "notes": list(self.notes),
            "paper_only": True,
            "live_authorized": False,
            "authoritative": self.classification
            in (
                DatasetClassification.HISTORICAL_AUTHENTICATED,
                DatasetClassification.HISTORICAL_LOCAL_DATASET,
            )
            and self.promotable,
        }
        if include_bars:
            out["bars"] = [b.to_public() for b in self.bars[:5000]]
            out["bars_truncated"] = len(self.bars) > 5000
        return out


@dataclass
class HistoricalDataset:
    id: str = field(default_factory=lambda: _id("hds"))
    schema_version: str = SCHEMA_VERSION
    name: str = ""
    market: str = ""
    created_at: float = field(default_factory=_now)
    org_id: str = ""
    workspace_id: str = ""
    latest_version: str = ""
    versions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "schema_version": self.schema_version,
            "name": self.name,
            "market": self.market,
            "created_at": self.created_at,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "latest_version": self.latest_version,
            "versions": list(self.versions),
            "notes": list(self.notes),
            "paper_only": True,
        }


@dataclass
class DataImportRun:
    id: str = field(default_factory=lambda: _id("imp"))
    dataset_id: str = ""
    version: str = ""
    adapter: str = ""
    status: ImportStatus = ImportStatus.PENDING
    source_path: str = ""
    progress: float = 0.0
    message: str = ""
    started_at: float = field(default_factory=_now)
    finished_at: float | None = None
    org_id: str = ""
    workspace_id: str = ""
    error: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "version": self.version,
            "adapter": self.adapter,
            "status": self.status.value,
            "source_path": self.source_path,
            "progress": self.progress,
            "message": self.message,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "error": self.error,
            "paper_only": True,
        }
