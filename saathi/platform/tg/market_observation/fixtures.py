"""Offline observation fixtures — deterministic, no network."""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.market_observation.models import (
    DEFAULT_BENCHMARKS,
    DEFAULT_SYMBOLS,
    DataFreshness,
    ExchangeStatus,
    ObservationSource,
)

# Fixed base prices for determinism
_BASE: dict[str, dict[str, Any]] = {
    "SPY": {"name": "SPDR S&P 500 ETF", "asset_class": "equity_etf", "exchange": "NYSE_ARCA",
            "bid": 450.00, "ask": 450.05, "last": 450.02, "volume": 50_000_000},
    "QQQ": {"name": "Invesco QQQ Trust", "asset_class": "equity_etf", "exchange": "NASDAQ",
            "bid": 390.00, "ask": 390.08, "last": 390.04, "volume": 30_000_000},
    "AAPL": {"name": "Apple Inc.", "asset_class": "equity", "exchange": "NASDAQ",
             "bid": 190.00, "ask": 190.08, "last": 190.04, "volume": 40_000_000},
    "MSFT": {"name": "Microsoft Corp.", "asset_class": "equity", "exchange": "NASDAQ",
             "bid": 420.00, "ask": 420.10, "last": 420.05, "volume": 20_000_000},
    "TLT": {"name": "iShares 20+ Year Treasury Bond ETF", "asset_class": "bond_etf", "exchange": "NASDAQ",
            "bid": 92.00, "ask": 92.05, "last": 92.02, "volume": 10_000_000},
    "GLD": {"name": "SPDR Gold Shares", "asset_class": "commodity_etf", "exchange": "NYSE_ARCA",
            "bid": 195.00, "ask": 195.10, "last": 195.05, "volume": 8_000_000},
    "BTCUSDT": {"name": "Bitcoin / USDT", "asset_class": "crypto", "exchange": "CRYPTO_PAPER",
                "bid": 65000.0, "ask": 65010.0, "last": 65005.0, "volume": 1200.0},
    "ETHUSDT": {"name": "Ethereum / USDT", "asset_class": "crypto", "exchange": "CRYPTO_PAPER",
                "bid": 3200.0, "ask": 3201.5, "last": 3200.8, "volume": 8000.0},
    "AGG": {"name": "iShares Core US Aggregate Bond ETF", "asset_class": "bond_etf", "exchange": "NYSE_ARCA",
            "bid": 98.50, "ask": 98.55, "last": 98.52, "volume": 5_000_000},
}


def symbol_universe() -> list[str]:
    return list(DEFAULT_SYMBOLS)


def symbol_metadata(symbol: str) -> dict[str, Any] | None:
    s = symbol.upper()
    base = _BASE.get(s)
    if not base:
        return None
    return {
        "symbol": s,
        "name": base["name"],
        "asset_class": base["asset_class"],
        "exchange": base["exchange"],
        "currency": "USD" if not s.endswith("USDT") else "USDT",
        "tick_size": 0.01 if base["asset_class"] != "crypto" else 0.1,
        "lot_size": 1.0,
        "source": ObservationSource.OFFLINE_FIXTURE.value,
        "read_only": True,
    }


def quote_fixture(symbol: str, *, seed: int = 0) -> dict[str, Any] | None:
    s = symbol.upper()
    base = _BASE.get(s)
    if not base:
        return None
    # tiny deterministic jitter from seed
    j = ((seed * 17 + sum(ord(c) for c in s)) % 100) / 10000.0
    bid = base["bid"] * (1 + j * 0.01)
    ask = base["ask"] * (1 + j * 0.01)
    last = base["last"] * (1 + j * 0.01)
    return {
        "symbol": s,
        "bid": round(bid, 4),
        "ask": round(ask, 4),
        "last": round(last, 4),
        "volume": base["volume"],
        "source": ObservationSource.OFFLINE_FIXTURE.value,
        "freshness": DataFreshness.FROZEN.value,
        "observed_at": time.time(),
        "authenticated": False,
        "live_stream": False,
        "read_only": True,
    }


def exchange_status_fixture(exchange: str) -> dict[str, Any]:
    ex = exchange.upper()
    if "CRYPTO" in ex:
        status, session = ExchangeStatus.OPEN.value, "24x7"
    else:
        status, session = ExchangeStatus.OPEN.value, "RTH"
    return {
        "exchange": ex,
        "status": status,
        "session": session,
        "source": ObservationSource.OFFLINE_FIXTURE.value,
        "live_feed": False,
        "read_only": True,
    }


def historical_bars_fixture(symbol: str, n: int = 30, seed: int = 42) -> list[dict[str, Any]]:
    q = quote_fixture(symbol, seed=seed)
    if not q:
        return []
    px = q["last"]
    bars = []
    state = seed + sum(ord(c) for c in symbol)
    t0 = time.time() - n * 86400
    for i in range(n):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        ret = ((state % 2000) / 2000.0 - 0.5) * 0.02
        o = px
        c = px * (1 + ret)
        h = max(o, c) * 1.005
        l = min(o, c) * 0.995
        bars.append({
            "symbol": symbol.upper(),
            "ts": t0 + i * 86400,
            "open": round(o, 4),
            "high": round(h, 4),
            "low": round(l, 4),
            "close": round(c, 4),
            "volume": q["volume"] * (0.5 + (state % 100) / 200.0),
            "source": ObservationSource.OFFLINE_FIXTURE.value,
        })
        px = c
    return bars


def corporate_actions_fixture(symbol: str) -> list[dict[str, Any]]:
    s = symbol.upper()
    if s in ("AAPL", "MSFT", "SPY"):
        return [{
            "symbol": s,
            "action_type": "DIVIDEND",
            "ex_date": "2026-06-15",
            "amount": 0.24 if s != "SPY" else 1.5,
            "ratio": None,
            "source": ObservationSource.OFFLINE_FIXTURE.value,
            "read_only": True,
        }]
    if s == "AAPL":
        return [{
            "symbol": s, "action_type": "SPLIT", "ex_date": "2020-08-31",
            "amount": None, "ratio": 4.0,
            "source": ObservationSource.OFFLINE_FIXTURE.value, "read_only": True,
        }]
    return []


def benchmark_fixture(benchmark: str, seed: int = 0) -> dict[str, Any] | None:
    b = benchmark.upper()
    if b not in DEFAULT_BENCHMARKS and b not in _BASE:
        return None
    q = quote_fixture(b if b in _BASE else "SPY", seed=seed)
    if not q:
        return None
    change = ((seed * 13 + sum(ord(c) for c in b)) % 200 - 100) / 10000.0
    return {
        "benchmark": b,
        "level": q["last"],
        "change_pct": round(change, 6),
        "as_of": time.time(),
        "source": ObservationSource.OFFLINE_FIXTURE.value,
        "read_only": True,
    }
