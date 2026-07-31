"""Deterministic synthetic public-market fixtures created for M320–M327."""
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

TRADES = {
    "AAPL": [
        {"trade_id": "syn-aapl-001", "price": "218.08", "size": 100, "time": "2026-01-15T14:29:58Z"},
        {"trade_id": "syn-aapl-002", "price": "218.10", "size": 50, "time": "2026-01-15T14:29:59Z"},
        {"trade_id": "syn-aapl-003", "price": "218.12", "size": 75, "time": "2026-01-15T14:30:00Z"},
        {"trade_id": "syn-aapl-004", "price": "218.11", "size": 25, "time": "2026-01-15T14:30:01Z"},
        {"trade_id": "syn-aapl-005", "price": "218.13", "size": 80, "time": "2026-01-15T14:30:02Z"},
    ],
    "BTC-USD": [
        {"trade_id": "syn-btc-001", "price": "104250.00", "size": "0.20", "time": "2026-01-15T14:29:58Z"},
        {"trade_id": "syn-btc-002", "price": "104255.00", "size": "0.15", "time": "2026-01-15T14:29:59Z"},
        {"trade_id": "syn-btc-003", "price": "104260.00", "size": "0.08", "time": "2026-01-15T14:30:00Z"},
    ],
}

SYMBOLS = [
    {"symbol": "AAPL", "asset_class": "synthetic_equity", "currency": "USD"},
    {"symbol": "BTC-USD", "asset_class": "synthetic_crypto", "currency": "USD"},
    {"symbol": "SYN-ALPHA", "asset_class": "synthetic_equity", "currency": "USD"},
    {"symbol": "SYN-BETA", "asset_class": "synthetic_equity", "currency": "USD"},
]

MARKET_STATUS = {
    "SYNTHETIC-US": {
        "venue": "SYNTHETIC-US",
        "status": "FIXTURE_OPEN",
        "as_of": "2026-01-15T14:30:00Z",
        "next_transition": "2026-01-15T21:00:00Z",
    },
    "SYNTHETIC-24X7": {
        "venue": "SYNTHETIC-24X7",
        "status": "FIXTURE_CONTINUOUS",
        "as_of": "2026-01-15T14:30:00Z",
        "next_transition": None,
    },
}


def with_provenance(
    data: Mapping[str, Any],
    source_type: str,
) -> dict[str, Any]:
    if source_type not in {"MOCK", "REPLAY"}:
        raise ProviderContractError(
            ProviderErrorCode.INVALID_RESPONSE,
            "Fixture provenance source type is invalid",
            details={"source_type": source_type},
        )
    return {
        **deepcopy(dict(data)),
        "source_type": source_type,
        "live": False,
        "synthetic": True,
        "account_derived": False,
        "execution_capable": False,
        "repeatable": True,
    }


def _pagination(
    values: list[dict[str, Any]],
    params: Mapping[str, Any],
) -> dict[str, Any]:
    limit = params.get("limit", 2)
    cursor = params.get("cursor")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ProviderContractError(
            ProviderErrorCode.INVALID_REQUEST,
            "limit must be an integer between 1 and 100",
        )
    if cursor is None:
        offset = 0
    elif isinstance(cursor, str) and cursor.startswith("offset:"):
        try:
            offset = int(cursor.split(":", 1)[1])
        except ValueError as exc:
            raise ProviderContractError(
                ProviderErrorCode.INVALID_REQUEST,
                "cursor is invalid",
            ) from exc
    else:
        raise ProviderContractError(
            ProviderErrorCode.INVALID_REQUEST,
            "cursor is invalid",
        )
    if offset < 0 or offset > len(values):
        raise ProviderContractError(
            ProviderErrorCode.INVALID_REQUEST,
            "cursor is outside the fixture range",
        )
    end = min(offset + limit, len(values))
    return {
        "items": deepcopy(values[offset:end]),
        "page": {
            "cursor": cursor,
            "next_cursor": f"offset:{end}" if end < len(values) else None,
            "limit": limit,
            "count": end - offset,
            "total": len(values),
        },
    }


def _simulation_controls(params: Mapping[str, Any]) -> int:
    latency = params.get("simulated_latency_ms", 0)
    if isinstance(latency, bool) or not isinstance(latency, int) or not 0 <= latency <= 60_000:
        raise ProviderContractError(
            ProviderErrorCode.INVALID_REQUEST,
            "simulated_latency_ms must be an integer between 0 and 60000",
        )
    simulated_error = params.get("simulate_error")
    if simulated_error is None:
        return latency
    if simulated_error == "timeout":
        raise ProviderContractError(
            ProviderErrorCode.TIMEOUT_SIMULATION,
            "Deterministic offline timeout was simulated",
            details={"waited": False, "simulated_latency_ms": latency},
        )
    if simulated_error == "unavailable":
        raise ProviderContractError(
            ProviderErrorCode.PROVIDER_UNAVAILABLE,
            "Deterministic offline provider unavailability was simulated",
            details={"waited": False, "simulated_latency_ms": latency},
        )
    raise ProviderContractError(
        ProviderErrorCode.INVALID_REQUEST,
        "simulate_error is unsupported",
        details={"allowed": ["timeout", "unavailable"]},
    )


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
        for symbol in sorted(TRADES):
            fixtures.append({"fixture_id": f"trades:{symbol}", "operation": "trades.list", "symbol": symbol})
        fixtures.append({"fixture_id": "symbols:all", "operation": "symbols.list"})
        for venue in sorted(MARKET_STATUS):
            fixtures.append({
                "fixture_id": f"market-status:{venue}",
                "operation": "market_status.get",
                "venue": venue,
            })
        return fixtures

    def resolve(self, operation: str, params: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        latency = _simulation_controls(params)
        symbol = params.get("symbol")
        if operation == "quotes.get":
            self._require_text(symbol, "symbol")
            value = QUOTES.get(symbol)
            fixture_id = f"quote:{symbol}"
        elif operation == "candles.list":
            self._require_text(symbol, "symbol")
            interval = params.get("interval")
            self._require_text(interval, "interval")
            value = CANDLES.get((symbol, interval))
            fixture_id = f"candles:{symbol}:{interval}"
        elif operation == "orderbook.get":
            self._require_text(symbol, "symbol")
            value = ORDERBOOKS.get(symbol)
            fixture_id = f"orderbook:{symbol}"
        elif operation == "trades.list":
            self._require_text(symbol, "symbol")
            trades = TRADES.get(symbol)
            value = _pagination(trades, params) if trades is not None else None
            fixture_id = f"trades:{symbol}"
        elif operation == "symbols.list":
            value = _pagination(SYMBOLS, params)
            fixture_id = "symbols:all"
        elif operation == "market_status.get":
            venue = params.get("venue")
            self._require_text(venue, "venue")
            value = MARKET_STATUS.get(venue)
            fixture_id = f"market-status:{venue}"
        else:
            raise ProviderContractError(
                ProviderErrorCode.UNSUPPORTED_CAPABILITY,
                "Fixture operation is unsupported",
                details={"operation": operation},
            )
        if value is None:
            raise ProviderContractError(
                ProviderErrorCode.FIXTURE_MISSING,
                "Deterministic fixture is unavailable",
                details={"operation": operation, "symbol": symbol},
            )
        return fixture_id, with_provenance(
            {
                "fixture": deepcopy(value),
                "simulated_latency_ms": latency,
                "waited": False,
            },
            "MOCK",
        )

    @staticmethod
    def _require_text(value: Any, name: str) -> None:
        if not isinstance(value, str) or not value:
            raise ProviderContractError(
                ProviderErrorCode.INVALID_REQUEST,
                f"{name} is required",
            )
