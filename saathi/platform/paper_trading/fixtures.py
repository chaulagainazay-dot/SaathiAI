"""M62.5 — deterministic paper-broker certification fixtures.

Bounded, hashed market events (never live data, never wall-clock). Used by the test
suite and the evidence manifest to prove deterministic acceptance/rejection/fill.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.paper_trading.models import ENGINE_VERSION, _hash

FIXTURE_VERSION = "paper-fixtures/1.0.0"


def market_event(symbol: str, *, bid: str, ask: str, last: str | None = None, liquidity: str = "1000000",
                 quality: str = "VALID", market_state: str = "OPEN", ts: float = 1000.0, ref: str = "") -> dict[str, Any]:
    """A deterministic market-event dict accepted by the paper-trading tools."""
    return {"symbol": symbol, "bid": bid, "ask": ask, "last": last if last is not None else ask,
            "liquidity": liquidity, "quality": quality, "market_state": market_state, "ts": ts,
            "ref": ref or f"fx:{symbol}:{ts}"}


# Canonical scenarios (bid, ask spread around ~100).
VALID_TIGHT = market_event("TRENDING", bid="99.98", ask="100.02", last="100.00", ref="fx:valid:1")
VALID_LOW_LIQUIDITY = market_event("TRENDING", bid="99.98", ask="100.02", liquidity="40", ref="fx:lowliq:1")
STALE = market_event("TRENDING", bid="99.98", ask="100.02", quality="STALE", ref="fx:stale:1")
INVALID_PRICE = market_event("TRENDING", bid="-1.00", ask="100.02", quality="UNVERIFIED", ref="fx:invalid:1")
MARKET_CLOSED = market_event("TRENDING", bid="99.98", ask="100.02", market_state="CLOSED", ref="fx:closed:1")
CROSS_UP = market_event("TRENDING", bid="104.98", ask="105.02", last="105.00", ref="fx:crossup:1")


def fixture_manifest() -> dict[str, Any]:
    events = {"VALID_TIGHT": VALID_TIGHT, "VALID_LOW_LIQUIDITY": VALID_LOW_LIQUIDITY, "STALE": STALE,
              "INVALID_PRICE": INVALID_PRICE, "MARKET_CLOSED": MARKET_CLOSED, "CROSS_UP": CROSS_UP}
    return {"version": FIXTURE_VERSION, "engine": ENGINE_VERSION, "events": events,
            "hash": _hash(events)}
