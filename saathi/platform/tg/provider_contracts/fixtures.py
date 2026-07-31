"""Deterministic synthetic public-market fixtures."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from saathi.platform.tg.provider_contracts.errors import (
    ProviderContractError,
    ProviderErrorCode,
)

QUOTES = {
    "AAPL": {
        "symbol": "AAPL",
        "bid": "218.10",
        "ask": "218.14",
        "last": "218.12",
        "currency": "USD",
        "as_of": "2026-01-15T14:30:00Z",
    },
    "BTC-USD": {
        "symbol": "BTC-USD",
        "bid": "104250.00",
        "ask": "104260.00",
        "last": "104255.00",
        "currency": "USD",
        "as_of": "2026-01-15T14:30:00Z",
    },
}

CANDLES = {
    ("AAPL", "1d"): [
        {"time": "2026-01-13T00:00:00Z", "open": "215.00", "high": "219.00", "low": "214.50", "close": "218.00", "volume": 48120000},
        {"time": "2026-01-14T00:00:00Z", "open": "218.00", "high": "219.20", "low": "216.80", "close": "217.50", "volume": 43710000},
        {"time": "2026-01-15T00:00:00Z", "open": "217.50", "high": "219.10", "low": "217.20", "close": "218.12", "volume": 40250000},
    ],
    ("BTC-USD", "1h"): [
        {"time": "2026-01-15T12:00:00Z", "open": "103900.00", "high": "104100.00", "low": "103850.00", "close": "104020.00", "volume": "812.50"},
        {"time": "2026-01-15T13:00:00Z", "open": "104020.00", "high": "104300.00", "low": "103980.00", "close": "104210.00", "volume": "905.25"},
        {"time": "2026-01-15T14:00:00Z", "open": "104210.00", "high": "104320.00", "low": "104180.00", "close": "104255.00", "volume": "522.75"},
    ],
}

ORDERBOOKS = {
    "AAPL": {
        "symbol": "AAPL",
        "bids": [["218.10", 500], ["218.08", 750], ["218.05", 900]],
        "asks": [["218.14", 400], ["218.16", 625], ["218.20", 1000]],
        "depth": 3,
        "as_of": "2026-01-15T14:30:00Z",
    },
    "BTC-USD": {
        "symbol": "BTC-USD",
        "bids": [["104250.00", "1.25"], ["104240.00", "2.10"], ["104230.00", "3.40"]],
        "asks": [["104260.00", "1.10"], ["104270.00", "2.25"], ["104280.00", "3.15"]],
        "depth": 3,
        "as_of": "2026-01-15T14:30:00Z",
    },
}


class FixtureCatalog:
    def list_fixtures(self) -> list[dict[str, Any]]:
        fixtures = []
        for symbol in sorted(QUOTES):
            fixtures.append({"fixture_id": f"quote:{symbol}", "operation": "quotes.get", "symbol": symbol})
        for symbol, interval in sorted(CANDLES):
            fixtures.append({
                "fixture_id": f"candles:{symbol}:{interval}",
                "operation": "candles.list",
                "symbol": symbol,
                "interval": interval,
            })
        for symbol in sorted(ORDERBOOKS):
            fixtures.append({"fixture_id": f"orderbook:{symbol}", "operation": "orderbook.get", "symbol": symbol})
        return fixtures

    def resolve(self, operation: str, params: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        symbol = params.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ProviderContractError(
                ProviderErrorCode.INVALID_REQUEST,
                "symbol is required",
            )
        if operation == "quotes.get":
            value = QUOTES.get(symbol)
            fixture_id = f"quote:{symbol}"
        elif operation == "candles.list":
            interval = params.get("interval")
            if not isinstance(interval, str) or not interval:
                raise ProviderContractError(
                    ProviderErrorCode.INVALID_REQUEST,
                    "interval is required",
                )
            value = CANDLES.get((symbol, interval))
            fixture_id = f"candles:{symbol}:{interval}"
        elif operation == "orderbook.get":
            value = ORDERBOOKS.get(symbol)
            fixture_id = f"orderbook:{symbol}"
        else:
            raise ProviderContractError(
                ProviderErrorCode.UNSUPPORTED,
                "Fixture operation is unsupported",
                details={"operation": operation},
            )
        if value is None:
            raise ProviderContractError(
                ProviderErrorCode.UNAVAILABLE,
                "Deterministic fixture is unavailable",
                details={"operation": operation, "symbol": symbol},
            )
        return fixture_id, {"fixture": deepcopy(value), "synthetic": True, "repeatable": True}
