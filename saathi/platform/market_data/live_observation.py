"""M — LIVE_NEPSE_BROWSER_MARKET_DATA: live observation domain (pure, no browser).

Models + normalization + freshness for LIVE_BROWSER_OBSERVED market data read from
the official NEPSE public website's RENDERED DOM. This is deliberately NOT canonical
historical market data:

    LIVE_BROWSER_OBSERVED  != CANONICAL_HISTORICAL_MARKET_DATA

Browser-observed values describe CURRENT market awareness (LTP, today's OHLC, volume,
turnover, index, breadth, market status). They must never silently become historical
canonical truth (that plane is `md_bars`, written only by the point-in-time importer).
Every observation carries its own observed_at + source freshness. Offline-testable.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum

# ── invariant tags (enforced in code + tests) ──────────────────────────────────
DATA_CLASS = "LIVE_BROWSER_OBSERVED"
SOURCE_AUTHORITY = "NEPAL_STOCK_EXCHANGE"
ACQUISITION_METHOD = "OFFICIAL_LIVE_BROWSER"
EXCHANGE = "NEPSE"

# freshness thresholds (seconds) for a browser-observed snapshot of an OPEN market.
LIVE_MAX_AGE_SEC = 90.0      # observed within ~1.5 min of source "as of"
RECENT_MAX_AGE_SEC = 900.0   # within 15 min


class MarketState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PRE_OPEN = "PRE_OPEN"
    UNKNOWN = "UNKNOWN"


class Freshness(str, Enum):
    LIVE = "LIVE"
    RECENT = "RECENT"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    MARKET_CLOSED = "MARKET_CLOSED"
    PAGE_ERROR = "PAGE_ERROR"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"


class LiveAcquisitionStatus(str, Enum):
    NEPSE_LIVE_AVAILABLE = "NEPSE_LIVE_AVAILABLE"
    NEPSE_LIVE_STALE = "NEPSE_LIVE_STALE"
    NEPSE_MARKET_CLOSED = "NEPSE_MARKET_CLOSED"
    NEPSE_PAGE_UNAVAILABLE = "NEPSE_PAGE_UNAVAILABLE"
    NEPSE_SCHEMA_CHANGED = "NEPSE_SCHEMA_CHANGED"
    NEPSE_BROWSER_FAILED = "NEPSE_BROWSER_FAILED"
    NEPSE_ACCESS_BLOCKED = "NEPSE_ACCESS_BLOCKED"
    PLAYWRIGHT_UNAVAILABLE = "PLAYWRIGHT_UNAVAILABLE"


class SymbolResolution(str, Enum):
    RESOLVED = "RESOLVED"
    SYMBOL_UNRESOLVED = "SYMBOL_UNRESOLVED"


# ── numeric / text normalization ───────────────────────────────────────────────
def num(s) -> Decimal | None:
    """Parse an official cell to Decimal; commas stripped. None on blank/dash/bad."""
    if s is None:
        return None
    t = str(s).strip().replace(",", "")
    if t in ("", "-", "--", "N/A", "NA"):
        return None
    try:
        return Decimal(t)
    except (InvalidOperation, ValueError):
        return None


_LTP_RE = re.compile(r"^\s*([\d,]+(?:\.\d+)?)\s*(?:\(([-+]?[\d,]*\.?\d+)\))?\s*$")


def parse_ltp(cell) -> tuple[Decimal | None, Decimal | None]:
    """`"880.00(1.9)"` -> (Decimal('880.00'), Decimal('1.9')). Point-change in parens."""
    if cell is None:
        return None, None
    m = _LTP_RE.match(str(cell))
    if not m:
        return num(cell), None
    return num(m.group(1)), (num(m.group(2)) if m.group(2) is not None else None)


# "As of Sep 11, 2026, 3:00:00 PM"  (NEPSE = Asia/Kathmandu, UTC+5:45)
_AS_OF_RE = re.compile(r"As of\s+(.+?)\s*$", re.IGNORECASE)
_KATHMANDU_OFFSET_SEC = 5 * 3600 + 45 * 60


def parse_as_of(text: str) -> tuple[str, float | None]:
    """Return (raw_as_of_text, epoch_seconds_or_None). Best-effort; never raises."""
    if not text:
        return "", None
    m = _AS_OF_RE.search(text)
    raw = (m.group(1).strip() if m else text.strip())
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(seconds=_KATHMANDU_OFFSET_SEC))
    for fmt in ("%b %d, %Y, %I:%M:%S %p", "%b %d, %Y, %I:%M %p", "%B %d, %Y, %I:%M:%S %p"):
        try:
            dt = datetime.strptime(raw, fmt).replace(tzinfo=tz)
            return raw, dt.timestamp()
        except ValueError:
            continue
    return raw, None


def market_state_from_text(status_text: str) -> MarketState:
    t = (status_text or "").upper()
    if "PRE" in t and "OPEN" in t:
        return MarketState.PRE_OPEN
    if "CLOSE" in t:
        return MarketState.CLOSED
    if "OPEN" in t:
        return MarketState.OPEN
    return MarketState.UNKNOWN


def compute_freshness(*, now: float, observed_at: float, source_as_of_epoch: float | None,
                      market_status: MarketState) -> Freshness:
    """Freshness of a live observation. A CLOSED market is reported as MARKET_CLOSED
    (never dressed up as LIVE); an OPEN market ages against the source 'as of' time."""
    if market_status == MarketState.CLOSED:
        return Freshness.MARKET_CLOSED
    ref = source_as_of_epoch if source_as_of_epoch else observed_at
    age = max(0.0, now - ref)
    if age <= LIVE_MAX_AGE_SEC:
        return Freshness.LIVE
    if age <= RECENT_MAX_AGE_SEC:
        return Freshness.RECENT
    return Freshness.STALE


# ── domain models ───────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class LiveMarketObservation:
    """One security observed on the official NEPSE rendered page. CURRENT awareness
    only — never a historical canonical bar."""
    observation_id: str
    symbol: str                      # as shown on the official page
    instrument_id: str               # canonical NEPSE:SYM, or "" if unresolved
    observed_at: float               # our read time (epoch)
    source_url: str
    ltp: Decimal | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    previous_close: Decimal | None = None
    volume: Decimal | None = None            # total traded quantity
    turnover: Decimal | None = None          # total traded value
    transactions: Decimal | None = None      # total trades
    point_change: Decimal | None = None
    percent_change: Decimal | None = None
    average_price: Decimal | None = None
    week52_high: Decimal | None = None
    week52_low: Decimal | None = None
    market_cap: Decimal | None = None
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    source_as_of: str = ""
    symbol_resolution: SymbolResolution = SymbolResolution.RESOLVED
    exchange: str = EXCHANGE
    source_authority: str = SOURCE_AUTHORITY
    acquisition_method: str = ACQUISITION_METHOD
    data_class: str = DATA_CLASS
    limitations: tuple[str, ...] = ()

    def to_public(self) -> dict:
        def s(v):
            return None if v is None else str(v)
        return {
            "observation_id": self.observation_id, "exchange": self.exchange,
            "symbol": self.symbol, "instrument_id": self.instrument_id,
            "observed_at": self.observed_at, "source_url": self.source_url,
            "ltp": s(self.ltp), "open": s(self.open), "high": s(self.high), "low": s(self.low),
            "close": s(self.close), "previous_close": s(self.previous_close),
            "volume": s(self.volume), "turnover": s(self.turnover),
            "transactions": s(self.transactions), "point_change": s(self.point_change),
            "percent_change": s(self.percent_change), "average_price": s(self.average_price),
            "week52_high": s(self.week52_high), "week52_low": s(self.week52_low),
            "market_cap": s(self.market_cap), "best_bid": s(self.best_bid),
            "best_ask": s(self.best_ask), "source_as_of": self.source_as_of,
            "symbol_resolution": self.symbol_resolution.value,
            "source_authority": self.source_authority,
            "acquisition_method": self.acquisition_method, "data_class": self.data_class,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class NepseLiveMarketSnapshot:
    """Market-wide live snapshot read from the official NEPSE public site."""
    snapshot_id: str
    observed_at: float
    source_url: str
    market_status: MarketState
    freshness: Freshness
    source_health: LiveAcquisitionStatus
    nepse_index: Decimal | None = None
    index_change: Decimal | None = None
    index_change_percent: Decimal | None = None
    total_turnover: Decimal | None = None
    total_volume: Decimal | None = None           # total traded shares
    total_transactions: Decimal | None = None
    total_scrips_traded: Decimal | None = None
    total_market_cap: Decimal | None = None
    advancers: int | None = None
    decliners: int | None = None
    unchanged: int | None = None
    securities: tuple[LiveMarketObservation, ...] = ()
    source_as_of: str = ""
    source_as_of_epoch: float | None = None
    exchange: str = EXCHANGE
    source_authority: str = SOURCE_AUTHORITY
    acquisition_method: str = ACQUISITION_METHOD
    data_class: str = DATA_CLASS
    limitations: tuple[str, ...] = ()

    @property
    def market_open(self) -> bool:
        return self.market_status == MarketState.OPEN

    def get(self, symbol: str) -> LiveMarketObservation | None:
        sy = (symbol or "").strip().upper()
        for o in self.securities:
            if o.symbol.upper() == sy or o.instrument_id.upper().endswith(":" + sy):
                return o
        return None

    def top_by(self, attr: str, n: int = 5) -> list[LiveMarketObservation]:
        have = [o for o in self.securities if getattr(o, attr) is not None]
        return sorted(have, key=lambda o: getattr(o, attr), reverse=True)[:n]

    def to_public(self) -> dict:
        def s(v):
            return None if v is None else str(v)
        return {
            "snapshot_id": self.snapshot_id, "observed_at": self.observed_at,
            "source_url": self.source_url, "exchange": self.exchange,
            "market_status": self.market_status.value, "market_open": self.market_open,
            "freshness": self.freshness.value, "source_health": self.source_health.value,
            "nepse_index": s(self.nepse_index), "index_change": s(self.index_change),
            "index_change_percent": s(self.index_change_percent),
            "total_turnover": s(self.total_turnover), "total_volume": s(self.total_volume),
            "total_transactions": s(self.total_transactions),
            "total_scrips_traded": s(self.total_scrips_traded),
            "total_market_cap": s(self.total_market_cap),
            "advancers": self.advancers, "decliners": self.decliners, "unchanged": self.unchanged,
            "source_as_of": self.source_as_of, "source_as_of_epoch": self.source_as_of_epoch,
            "source_authority": self.source_authority,
            "acquisition_method": self.acquisition_method, "data_class": self.data_class,
            "securities_count": len(self.securities),
            "securities": [o.to_public() for o in self.securities],
            "limitations": list(self.limitations),
        }

    def summary(self) -> dict:
        """Compact projection (no per-security rows) for dashboards/chat/voice."""
        d = self.to_public()
        d.pop("securities", None)
        return d
