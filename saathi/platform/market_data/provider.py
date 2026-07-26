"""M62.2 — read-only market-data provider contract.

Providers NEVER submit orders. Results carry an explicit status so a failure can
never silently become an empty-but-valid dataset. No external provider is required
for M62.2 — the deterministic fixture provider (fixtures.py) satisfies the contract.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from saathi.platform.market_data.models import MDInstrument, MDQuote, MDBar, Timeframe
from saathi.platform.trading_models import MarketState

T = TypeVar("T")


class ProviderStatus(str, Enum):
    SUCCESS = "SUCCESS"
    NOT_FOUND = "NOT_FOUND"
    UNSUPPORTED = "UNSUPPORTED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    AUTH_FAILURE = "AUTH_FAILURE"
    UNAVAILABLE = "UNAVAILABLE"
    MALFORMED = "MALFORMED"


ERROR_STATUSES = frozenset(s for s in ProviderStatus if s != ProviderStatus.SUCCESS)


@dataclass
class ProviderResult(Generic[T]):
    status: ProviderStatus
    data: T | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == ProviderStatus.SUCCESS

    @classmethod
    def success(cls, data: T) -> "ProviderResult[T]":
        return cls(status=ProviderStatus.SUCCESS, data=data)

    @classmethod
    def error(cls, status: ProviderStatus, detail: str = "") -> "ProviderResult[T]":
        return cls(status=status, data=None, detail=detail)

    def to_public(self) -> dict[str, Any]:
        return {"status": self.status.value, "detail": self.detail, "has_data": self.data is not None}


@dataclass
class MarketClock:
    venue: str
    at: datetime
    state: MarketState
    next_open: datetime | None = None
    next_close: datetime | None = None


class MarketDataProvider(ABC):
    """Read-only. Concrete providers must map their transport failures onto
    ProviderStatus and NEVER raise raw transport exceptions to callers."""

    name: str = "abstract"

    @abstractmethod
    def get_instrument(self, symbol: str) -> ProviderResult[MDInstrument]: ...

    @abstractmethod
    def get_quote(self, symbol: str, *, now: datetime) -> ProviderResult[MDQuote]: ...

    @abstractmethod
    def get_bars(self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime,
                 *, now: datetime) -> ProviderResult[list[MDBar]]: ...

    @abstractmethod
    def get_market_clock(self, venue: str, *, now: datetime) -> ProviderResult[MarketClock]: ...

    def list_supported_timeframes(self) -> list[Timeframe]:
        return list(Timeframe)
