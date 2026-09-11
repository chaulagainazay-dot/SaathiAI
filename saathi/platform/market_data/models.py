"""M62.2 — canonical, provider-neutral market-data models.

Reuses the M62.1 domain (`saathi.platform.trading_models`): `AssetClass`, the
coarse `DataQuality` the Trading Guardian consumes, `MarketState`, and the `D`
decimal coercion. Adds richer, timezone-AWARE market-data records with a detailed
quality enum + structured findings, plus a mapping down to the guardian's coarse
`DataQuality` (only fully VALID data is tradeable).

No network, no execution, no broker. Data only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from saathi.platform.trading_models import D, AssetClass, DataQuality, MarketState  # reuse
from saathi.platform.market_data.identity import resolve_market_identity


# ── timeframes ────────────────────────────────────────────────────────────────
class Timeframe(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    D1 = "1d"


TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60, Timeframe.M5: 300, Timeframe.M15: 900,
    Timeframe.H1: 3600, Timeframe.D1: 86400,
}
INTRADAY_TIMEFRAMES = frozenset({Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1})


# ── detailed market-data quality ──────────────────────────────────────────────
class MarketDataQuality(str, Enum):
    VALID = "VALID"
    STALE = "STALE"
    INCOMPLETE = "INCOMPLETE"
    OUTLIER = "OUTLIER"
    GAPPED = "GAPPED"
    DUPLICATE = "DUPLICATE"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    UNVERIFIED = "UNVERIFIED"
    MARKET_CLOSED = "MARKET_CLOSED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    INVALID_PRICE = "INVALID_PRICE"


# Only fully VALID market data is tradeable. Everything else maps to a non-VALID
# coarse DataQuality so the Guardian's `price_quality_valid` check fails closed.
def to_data_quality(q: MarketDataQuality) -> DataQuality:
    if q == MarketDataQuality.VALID:
        return DataQuality.VALID
    if q == MarketDataQuality.STALE:
        return DataQuality.STALE
    if q == MarketDataQuality.INCOMPLETE:
        return DataQuality.INCOMPLETE
    if q == MarketDataQuality.OUTLIER:
        return DataQuality.OUTLIER
    if q == MarketDataQuality.GAPPED:
        return DataQuality.GAPPED
    if q == MarketDataQuality.PROVIDER_ERROR:
        return DataQuality.PROVIDER_ERROR
    return DataQuality.UNVERIFIED


@dataclass
class QualityFinding:
    code: str
    detail: str = ""

    def to_public(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


# ── timezone-aware timestamp helpers ──────────────────────────────────────────
def require_aware(dt: datetime, field_name: str = "timestamp") -> datetime:
    """Reject naive timestamps. Return the datetime unchanged if aware."""
    if not isinstance(dt, datetime):
        raise ValueError(f"{field_name} must be a datetime, got {type(dt).__name__}")
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{field_name} must be timezone-aware (naive datetimes are rejected)")
    return dt


def is_aware(dt: Any) -> bool:
    return isinstance(dt, datetime) and dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None


def to_epoch(dt: datetime) -> float:
    return require_aware(dt).timestamp()


# ── records ───────────────────────────────────────────────────────────────────
@dataclass
class MDInstrument:
    provider: str
    venue: str
    symbol: str
    canonical_symbol: str
    asset_class: AssetClass
    base_currency: str = "USD"
    quote_currency: str = "USD"
    price_precision: int = 2
    quantity_precision: int = 0
    minimum_quantity: Decimal = field(default_factory=lambda: Decimal("0"))
    minimum_notional: Decimal = field(default_factory=lambda: Decimal("0"))
    timezone: str = "UTC"
    market_calendar: str = "DEFAULT_24_5"
    status: str = "active"

    def __post_init__(self) -> None:
        identity = resolve_market_identity(
            instrument_id=self.canonical_symbol,
            venue=self.venue,
            asset_class=self.asset_class,
        )
        self.venue = identity.venue

    def to_public(self) -> dict[str, Any]:
        return {
            "provider": self.provider, "venue": self.venue, "symbol": self.symbol,
            "canonical_symbol": self.canonical_symbol, "asset_class": self.asset_class.value,
            "base_currency": self.base_currency, "quote_currency": self.quote_currency,
            "price_precision": self.price_precision, "quantity_precision": self.quantity_precision,
            "minimum_quantity": str(self.minimum_quantity), "minimum_notional": str(self.minimum_notional),
            "timezone": self.timezone, "market_calendar": self.market_calendar, "status": self.status,
        }


@dataclass
class MDQuote:
    instrument: str          # canonical symbol
    provider: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    bid_size: Decimal
    ask_size: Decimal
    source_time: datetime    # timezone-aware provider timestamp
    ingested_at: datetime    # timezone-aware receipt timestamp
    quality: MarketDataQuality = MarketDataQuality.UNVERIFIED
    findings: list[QualityFinding] = field(default_factory=list)

    def data_quality(self) -> DataQuality:
        return to_data_quality(self.quality)

    def to_public(self) -> dict[str, Any]:
        return {
            "instrument": self.instrument, "provider": self.provider, "bid": str(self.bid),
            "ask": str(self.ask), "last": str(self.last), "bid_size": str(self.bid_size),
            "ask_size": str(self.ask_size), "source_time": self.source_time.isoformat(),
            "ingested_at": self.ingested_at.isoformat(), "quality": self.quality.value,
            "findings": [f.to_public() for f in self.findings],
        }


@dataclass
class MDBar:
    instrument: str
    timeframe: Timeframe
    provider: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    start_time: datetime     # timezone-aware
    end_time: datetime       # timezone-aware
    source_time: datetime
    ingested_at: datetime
    quality: MarketDataQuality = MarketDataQuality.UNVERIFIED
    findings: list[QualityFinding] = field(default_factory=list)

    def data_quality(self) -> DataQuality:
        return to_data_quality(self.quality)

    def to_public(self) -> dict[str, Any]:
        return {
            "instrument": self.instrument, "timeframe": self.timeframe.value, "provider": self.provider,
            "open": str(self.open), "high": str(self.high), "low": str(self.low), "close": str(self.close),
            "volume": str(self.volume), "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(), "source_time": self.source_time.isoformat(),
            "ingested_at": self.ingested_at.isoformat(), "quality": self.quality.value,
            "findings": [f.to_public() for f in self.findings],
        }


# ── freshness policy ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FreshnessPolicy:
    """Configurable max-age (seconds) per data type. Not hidden in UI."""
    quote_max_age_sec: float = 15.0
    intraday_bar_max_age_sec: float = 600.0     # 10 min
    daily_bar_max_age_sec: float = 172800.0     # 48 h
    instrument_max_age_sec: float = 604800.0    # 7 d

    def bar_max_age(self, tf: Timeframe) -> float:
        return self.intraday_bar_max_age_sec if tf in INTRADAY_TIMEFRAMES else self.daily_bar_max_age_sec


DEFAULT_FRESHNESS = FreshnessPolicy()
