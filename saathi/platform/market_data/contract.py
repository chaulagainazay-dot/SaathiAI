"""MD-1 — canonical point-in-time market data contract.

The defect this closes
----------------------
SaathiOS was ``as_of``-only. A research or backtest filter written as
``as_of <= decision_time`` admits a quarterly result the moment the quarter
ends — weeks before anyone could have read it. That is the look-ahead defect
recorded in ``docs/evaluations/tradingagents/LOOKAHEAD_AUDIT.md`` (upstream
scored 6/10 on exactly this), and it was unfixed here.

Four timestamps, and why each exists
------------------------------------
``event_timestamp``  when the underlying market event occurred
``as_of``            the economic period the observation represents
``available_at``     the earliest instant SaathiOS could *legitimately* have
                     known it — publication, filing, or release time
``received_at``      when SaathiOS actually took delivery

For live quotes all four collapse to roughly the same instant. They diverge
sharply for anything published on a lag: fundamentals, indices, corporate
actions, revised series. **The only correct look-ahead filter is
``available_at <= decision_time``.**

Convergence, not a fifth enum
-----------------------------
Four ``AssetClass`` enums exist in this tree with different casing and members
(``platform/trading_models``, ``tg/broker_sandbox/models``,
``tg/market_data/models``, and the unrelated business-category one in
``investment.py``). This module defines the canonical one and provides
``asset_class_from_legacy`` to adapt the others. The legacy enums are *not*
deleted: they have consumers this milestone has no mandate to break.

Authority
---------
Data only. No execution, approval, risk, or ledger authority. No network I/O.
Cannot import the ledger or the execution plane — enforced by test.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Sequence

from saathi.platform.trading_models import DataQuality

__all__ = [
    "AssetClass",
    "asset_class_from_legacy",
    "MarketStatus",
    "DataAvailability",
    "PointInTime",
    "ProviderReference",
    "MarketDataEvent",
    "CanonicalQuote",
    "CanonicalTrade",
    "CanonicalBar",
    "MarketDataSnapshot",
    "visible_at",
]


# ── asset class ────────────────────────────────────────────────────────────

class AssetClass(str, Enum):
    """Canonical instrument asset class."""

    EQUITY = "EQUITY"
    ETF = "ETF"
    INDEX = "INDEX"
    CRYPTO = "CRYPTO"
    FX = "FX"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    CASH = "CASH"
    DEBENTURE = "DEBENTURE"
    MUTUAL_FUND = "MUTUAL_FUND"


_LEGACY_ASSET_CLASS: dict[str, AssetClass] = {
    "EQUITY": AssetClass.EQUITY,
    "STOCK": AssetClass.EQUITY,
    "SHARE": AssetClass.EQUITY,
    "ETF": AssetClass.ETF,
    "INDEX": AssetClass.INDEX,
    "CRYPTO": AssetClass.CRYPTO,
    "FX": AssetClass.FX,
    "FUTURES": AssetClass.FUTURES,
    "OPTIONS": AssetClass.OPTIONS,
    "CASH": AssetClass.CASH,
    "DEBENTURE": AssetClass.DEBENTURE,
    "CORPORATE_DEBENTURE": AssetClass.DEBENTURE,
    "MUTUAL_FUND": AssetClass.MUTUAL_FUND,
    "MUTUALFUND": AssetClass.MUTUAL_FUND,
}


def asset_class_from_legacy(value: Any) -> AssetClass:
    """Map any legacy ``AssetClass`` spelling onto the canonical enum.

    Raises on an unmappable value rather than defaulting. Silently defaulting an
    unknown asset class to EQUITY would misclassify the instrument everywhere
    downstream — in concentration limits, in construction, and in risk.
    """
    if isinstance(value, AssetClass):
        return value
    key = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if key in _LEGACY_ASSET_CLASS:
        return _LEGACY_ASSET_CLASS[key]
    raise ValueError(f"unmappable asset class {value!r}")


class MarketStatus(str, Enum):
    PRE_OPEN = "PRE_OPEN"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    HALTED = "HALTED"
    AUCTION = "AUCTION"
    UNKNOWN = "UNKNOWN"       # safe default: never assume a market is open


class DataAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_YET_AVAILABLE = "NOT_YET_AVAILABLE"
    UNKNOWN = "UNKNOWN"


# ── point in time ──────────────────────────────────────────────────────────

def _require_aware(name: str, value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{name} must be a datetime, got {type(value).__name__}")
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(
            f"{name} must be timezone-aware; a naive datetime compares wrongly "
            "across timezones and would silently corrupt point-in-time filtering"
        )
    return value


@dataclass(frozen=True)
class PointInTime:
    """The four timestamps every market-data observation carries."""

    event_timestamp: datetime
    as_of: datetime
    available_at: datetime
    received_at: datetime

    def __post_init__(self) -> None:
        for name in ("event_timestamp", "as_of", "available_at", "received_at"):
            _require_aware(name, getattr(self, name))
        if self.available_at < self.as_of:
            raise ValueError(
                f"available_at {self.available_at.isoformat()} precedes as_of "
                f"{self.as_of.isoformat()}: an observation cannot be knowable "
                "before the period it describes has ended"
            )
        if self.received_at < self.available_at:
            raise ValueError(
                f"received_at {self.received_at.isoformat()} precedes available_at "
                f"{self.available_at.isoformat()}: SaathiOS cannot receive data "
                "before it was published"
            )

    @property
    def publication_lag(self) -> timedelta:
        """How long after the period end the observation became knowable."""
        return self.available_at - self.as_of

    def availability_at(self, decision_time: datetime) -> DataAvailability:
        _require_aware("decision_time", decision_time)
        return (
            DataAvailability.AVAILABLE
            if self.available_at <= decision_time
            else DataAvailability.NOT_YET_AVAILABLE
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "event_timestamp": self.event_timestamp.isoformat(),
            "as_of": self.as_of.isoformat(),
            "available_at": self.available_at.isoformat(),
            "received_at": self.received_at.isoformat(),
        }


@dataclass(frozen=True)
class ProviderReference:
    """Where an observation came from, and how to find it again."""

    provider: str
    provider_event_id: str = ""
    sequence: int = 0
    source_ref: str = ""
    is_delayed: bool = False
    delay_seconds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_event_id": self.provider_event_id,
            "sequence": self.sequence,
            "source_ref": self.source_ref,
            "is_delayed": self.is_delayed,
            "delay_seconds": self.delay_seconds,
        }


# ── events ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MarketDataEvent:
    """Base for every canonical observation."""

    instrument_id: str
    venue: str
    asset_class: AssetClass
    currency: str
    point_in_time: PointInTime
    provider: ProviderReference
    quality: DataQuality = DataQuality.UNVERIFIED
    market_status: MarketStatus = MarketStatus.UNKNOWN

    event_type: str = field(init=False, default="EVENT")

    def __post_init__(self) -> None:
        if not self.instrument_id:
            raise ValueError("instrument_id is required")

    def is_visible_at(self, decision_time: datetime) -> bool:
        return self.point_in_time.availability_at(decision_time) is DataAvailability.AVAILABLE

    def _base_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "instrument_id": self.instrument_id,
            "venue": self.venue,
            "asset_class": self.asset_class.value,
            "currency": self.currency,
            "point_in_time": self.point_in_time.to_dict(),
            "provider": self.provider.to_dict(),
            "quality": self.quality.value,
            "market_status": self.market_status.value,
        }

    def to_dict(self) -> dict[str, Any]:
        return self._base_dict()


def _require_non_negative(name: str, value: Decimal) -> Decimal:
    if value < 0:
        raise ValueError(f"{name} must not be negative, got {value}")
    return value


@dataclass(frozen=True)
class CanonicalQuote(MarketDataEvent):
    bid: Decimal = Decimal("0")
    ask: Decimal = Decimal("0")
    last: Decimal = Decimal("0")
    bid_size: Decimal = Decimal("0")
    ask_size: Decimal = Decimal("0")

    event_type: str = field(init=False, default="QUOTE")

    def __post_init__(self) -> None:
        super().__post_init__()
        for name in ("bid", "ask", "last", "bid_size", "ask_size"):
            _require_non_negative(name, getattr(self, name))
        if self.is_two_sided and self.bid > self.ask:
            raise ValueError(f"crossed quote: bid {self.bid} exceeds ask {self.ask}")

    @property
    def is_two_sided(self) -> bool:
        """True only when both sides are genuinely present.

        Zero is the field default, so it means "absent", not "priced at zero".
        A venue publishing only one side is normal; deriving a spread or a mid
        from one real side and one absent side is not.
        """
        return self.bid > 0 and self.ask > 0

    @property
    def spread(self) -> Decimal:
        if not self.is_two_sided:
            raise ValueError(
                f"spread is undefined for a one-sided quote "
                f"(bid={self.bid}, ask={self.ask})"
            )
        return self.ask - self.bid

    @property
    def mid(self) -> Decimal:
        if not self.is_two_sided:
            raise ValueError(
                f"mid is undefined for a one-sided quote "
                f"(bid={self.bid}, ask={self.ask})"
            )
        return (self.ask + self.bid) / Decimal("2")

    def to_dict(self) -> dict[str, Any]:
        d = self._base_dict()
        d.update(
            bid=str(self.bid), ask=str(self.ask), last=str(self.last),
            bid_size=str(self.bid_size), ask_size=str(self.ask_size),
        )
        return d


@dataclass(frozen=True)
class CanonicalTrade(MarketDataEvent):
    price: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    trade_id: str = ""

    event_type: str = field(init=False, default="TRADE")

    def __post_init__(self) -> None:
        super().__post_init__()
        _require_non_negative("price", self.price)
        if self.quantity <= 0:
            raise ValueError(f"trade quantity must be positive, got {self.quantity}")

    def to_dict(self) -> dict[str, Any]:
        d = self._base_dict()
        d.update(price=str(self.price), quantity=str(self.quantity), trade_id=self.trade_id)
        return d


@dataclass(frozen=True)
class CanonicalBar(MarketDataEvent):
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: Decimal = Decimal("0")
    timeframe: str = "1d"

    event_type: str = field(init=False, default="BAR")

    def __post_init__(self) -> None:
        super().__post_init__()
        for name in ("open", "high", "low", "close", "volume"):
            _require_non_negative(name, getattr(self, name))
        # Zero is the field default, so it means "absent". A bar is either fully
        # populated or fully empty (a genuine no-trade session). A partially
        # populated bar — high=100 with low=open=close=0 — used to satisfy the
        # ordering checks and pass, describing a session that cannot exist.
        ohlc = (self.open, self.high, self.low, self.close)
        populated = [v for v in ohlc if v > 0]
        if populated and len(populated) != 4:
            raise ValueError(
                f"partially populated bar: open={self.open} high={self.high} "
                f"low={self.low} close={self.close}; a bar must be fully priced "
                "or fully empty"
            )
        if self.high < self.low:
            raise ValueError(f"bar high {self.high} is below low {self.low}")
        if not (self.low <= self.open <= self.high):
            raise ValueError(f"bar open {self.open} outside [{self.low}, {self.high}]")
        if not (self.low <= self.close <= self.high):
            raise ValueError(f"bar close {self.close} outside [{self.low}, {self.high}]")

    def to_dict(self) -> dict[str, Any]:
        d = self._base_dict()
        d.update(
            open=str(self.open), high=str(self.high), low=str(self.low),
            close=str(self.close), volume=str(self.volume), timeframe=self.timeframe,
        )
        return d


# ── point-in-time filtering ────────────────────────────────────────────────

def visible_at(
    events: Iterable[MarketDataEvent], decision_time: datetime
) -> list[MarketDataEvent]:
    """Every event SaathiOS could legitimately have known at ``decision_time``.

    This is the only correct look-ahead filter. Filtering on ``as_of`` instead
    admits data that had not been published yet.
    """
    _require_aware("decision_time", decision_time)
    return [e for e in events if e.is_visible_at(decision_time)]


@dataclass(frozen=True)
class MarketDataSnapshot:
    """What was knowable at one instant, with the events that prove it."""

    decision_time: datetime
    events: tuple[MarketDataEvent, ...] = ()
    market_status: MarketStatus = MarketStatus.UNKNOWN

    def __post_init__(self) -> None:
        _require_aware("decision_time", self.decision_time)

    @property
    def visible_events(self) -> list[MarketDataEvent]:
        return visible_at(self.events, self.decision_time)

    @property
    def withheld_events(self) -> list[MarketDataEvent]:
        """Events excluded for not yet being published — kept for evidence."""
        return [e for e in self.events if not e.is_visible_at(self.decision_time)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_time": self.decision_time.isoformat(),
            "market_status": self.market_status.value,
            "visible": [e.to_dict() for e in self.visible_events],
            "withheld_count": len(self.withheld_events),
        }
