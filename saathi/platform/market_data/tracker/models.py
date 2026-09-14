"""Tracker read-model domain (pure, no network). THIRD_PARTY_HISTORICAL_SERIES."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum

SOURCE = "NEPSE_PORTFOLIO_TRACKER"
SOURCE_AUTHORITY = "THIRD_PARTY_STRUCTURED_MARKET_DATA"
DATA_CLASS = "THIRD_PARTY_HISTORICAL_SERIES"
POINT_IN_TIME = "HISTORICAL_KNOWLEDGE_TIME_UNSUPPORTED"
_KATHMANDU = timezone(timedelta(hours=5, minutes=45))
_NEPSE_CLOSE_H = 15  # business_date candles are stamped at the session close, local

# ranges the public API is verified to serve, and their granularity.
RANGE_GRANULARITY = {
    "1D": "INTRADAY", "1W": "DAILY", "1M": "DAILY", "3M": "DAILY",
    "6M": "DAILY", "1Y": "DAILY", "5Y": "DAILY",
}
SUPPORTED_RANGES = tuple(RANGE_GRANULARITY.keys())


class TrackerStatus(str, Enum):
    TRACKER_AVAILABLE = "TRACKER_AVAILABLE"
    TRACKER_STALE = "TRACKER_STALE"
    TRACKER_UNAVAILABLE = "TRACKER_UNAVAILABLE"
    TRACKER_SCHEMA_CHANGED = "TRACKER_SCHEMA_CHANGED"
    TRACKER_RATE_LIMITED = "TRACKER_RATE_LIMITED"
    INVALID_SERIES = "INVALID_SERIES"
    SYMBOL_UNRESOLVED = "SYMBOL_UNRESOLVED"
    HISTORICAL_RANGE_UNAVAILABLE = "HISTORICAL_RANGE_UNAVAILABLE"
    POINT_IN_TIME_UNAVAILABLE = "POINT_IN_TIME_UNAVAILABLE"


class ReconVerdict(str, Enum):
    CONFIRMED = "CONFIRMED"
    SOURCE_DISAGREEMENT = "SOURCE_DISAGREEMENT"
    TRACKER_STALE = "TRACKER_STALE"
    OFFICIAL_UNAVAILABLE = "OFFICIAL_UNAVAILABLE"
    TRACKER_UNAVAILABLE = "TRACKER_UNAVAILABLE"


def dec(v) -> Decimal | None:
    if v is None:
        return None
    t = str(v).strip().replace(",", "")
    if t in ("", "-", "--", "N/A", "null", "None"):
        return None
    try:
        return Decimal(t)
    except (InvalidOperation, ValueError):
        return None


def business_date_epoch(bd: str) -> float | None:
    """Epoch for a business_date candle, stamped at NEPSE session close (Kathmandu)."""
    try:
        d = datetime.strptime(str(bd)[:10], "%Y-%m-%d")
        return d.replace(hour=_NEPSE_CLOSE_H, tzinfo=_KATHMANDU).timestamp()
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class MarketPoint:
    timestamp: float
    business_date: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    turnover: Decimal | None = None

    def to_public(self) -> dict:
        def s(v):
            return None if v is None else str(v)
        return {"timestamp": self.timestamp, "business_date": self.business_date,
                "open": s(self.open), "high": s(self.high), "low": s(self.low),
                "close": s(self.close), "volume": s(self.volume), "turnover": s(self.turnover)}


@dataclass(frozen=True)
class MarketSeries:
    symbol: str
    instrument_id: str
    range: str
    timeframe: str                      # INTRADAY | DAILY
    retrieved_at: float
    points: tuple[MarketPoint, ...] = ()
    source: str = SOURCE
    source_authority: str = SOURCE_AUTHORITY
    data_class: str = DATA_CLASS
    point_in_time_capability: str = POINT_IN_TIME
    freshness: str = "TRACKER_AVAILABLE"
    limitations: tuple[str, ...] = ()

    @property
    def closes(self) -> list[Decimal]:
        return [p.close for p in self.points]

    @property
    def first_date(self) -> str | None:
        return self.points[0].business_date if self.points else None

    @property
    def last_date(self) -> str | None:
        return self.points[-1].business_date if self.points else None

    @property
    def latest_close(self) -> Decimal | None:
        return self.points[-1].close if self.points else None

    def to_public(self, *, include_points: bool = True) -> dict:
        d = {"symbol": self.symbol, "instrument_id": self.instrument_id, "range": self.range,
             "timeframe": self.timeframe, "retrieved_at": self.retrieved_at,
             "source": self.source, "source_authority": self.source_authority,
             "data_class": self.data_class,
             "point_in_time_capability": self.point_in_time_capability,
             "freshness": self.freshness, "n_points": len(self.points),
             "first_date": self.first_date, "last_date": self.last_date,
             "latest_close": None if self.latest_close is None else str(self.latest_close),
             "limitations": list(self.limitations)}
        if include_points:
            d["points"] = [p.to_public() for p in self.points]
        return d


@dataclass(frozen=True)
class FundamentalSnapshot:
    symbol: str
    instrument_id: str
    retrieved_at: float
    company_name: str = ""
    sector: str | None = None
    eps: Decimal | None = None
    pe_ratio: Decimal | None = None
    pb_ratio: Decimal | None = None
    dividend_yield: Decimal | None = None
    market_cap: Decimal | None = None
    week52_high: Decimal | None = None
    week52_low: Decimal | None = None
    last_traded_price: Decimal | None = None
    source: str = SOURCE
    source_authority: str = SOURCE_AUTHORITY
    limitations: tuple[str, ...] = ()

    def to_public(self) -> dict:
        def s(v):
            return None if v is None else str(v)
        return {"symbol": self.symbol, "instrument_id": self.instrument_id,
                "company_name": self.company_name, "sector": self.sector,
                "eps": s(self.eps), "pe_ratio": s(self.pe_ratio), "pb_ratio": s(self.pb_ratio),
                "dividend_yield": s(self.dividend_yield), "market_cap": s(self.market_cap),
                "week52_high": s(self.week52_high), "week52_low": s(self.week52_low),
                "last_traded_price": s(self.last_traded_price), "retrieved_at": self.retrieved_at,
                "source": self.source, "source_authority": self.source_authority,
                "note": "descriptive fundamentals; NOT a trade rating",
                "limitations": list(self.limitations)}


@dataclass(frozen=True)
class DividendRecord:
    symbol: str
    fiscal_year: str = ""
    bonus_share: Decimal | None = None
    cash_dividend: Decimal | None = None
    total_dividend: Decimal | None = None
    book_close_date: str | None = None
    published_date: str | None = None

    def to_public(self) -> dict:
        def s(v):
            return None if v is None else str(v)
        return {"symbol": self.symbol, "fiscal_year": self.fiscal_year,
                "bonus_share": s(self.bonus_share), "cash_dividend": s(self.cash_dividend),
                "total_dividend": s(self.total_dividend), "book_close_date": self.book_close_date,
                "published_date": self.published_date}


@dataclass(frozen=True)
class QuoteReconciliation:
    symbol: str
    verdict: ReconVerdict
    official_ltp: Decimal | None
    tracker_ltp: Decimal | None
    difference: Decimal | None
    official_source: str = "OFFICIAL_PAGE_OBSERVED"
    tracker_source: str = SOURCE
    authority: str = "OFFICIAL_PAGE_OBSERVED"     # official wins current-market
    note: str = ""

    def to_public(self) -> dict:
        def s(v):
            return None if v is None else str(v)
        return {"symbol": self.symbol, "verdict": self.verdict.value,
                "official_ltp": s(self.official_ltp), "tracker_ltp": s(self.tracker_ltp),
                "difference": s(self.difference), "official_source": self.official_source,
                "tracker_source": self.tracker_source,
                "current_market_authority": self.authority, "note": self.note}
