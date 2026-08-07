"""Deterministic market fixtures for tests and local research."""
from __future__ import annotations

from decimal import Decimal

from saathi.platform.tg.domain import MarketBar, MarketSnapshot


def _bars(symbol: str, closes: list[str], volumes: list[str] | None = None, start_ts: float = 1_700_000_000.0) -> list[MarketBar]:
    out: list[MarketBar] = []
    vols = volumes or ["100000"] * len(closes)
    for i, c in enumerate(closes):
        px = Decimal(c)
        v = Decimal(vols[i] if i < len(vols) else vols[-1])
        out.append(MarketBar(
            symbol=symbol,
            ts=start_ts + i * 86400,
            open=px * Decimal("0.995"),
            high=px * Decimal("1.01"),
            low=px * Decimal("0.99"),
            close=px,
            volume=v,
            timeframe="1d",
            source_identity="fixture",
            quality="VALID",
        ))
    return out


def mean_reverting_snapshot(symbol: str = "MR_TEST") -> MarketSnapshot:
    # Decline then green confirmation bar with volume spike
    closes = [str(100 - i) for i in range(12)] + ["87"]  # bounce
    vols = ["100000"] * 12 + ["250000"]
    bars = _bars(symbol, closes, vols)
    last = bars[-1]
    return MarketSnapshot(
        symbol=symbol,
        last_price=last.close,
        bid=last.close - Decimal("0.01"),
        ask=last.close + Decimal("0.01"),
        spread=Decimal("0.02"),
        volume=last.volume,
        avg_traded_value=Decimal("5000000"),
        volatility=Decimal("0.02"),
        market_state="OPEN",
        data_quality="VALID",
        freshness_seconds=10,
        bars=bars,
        source_identity="fixture",
        sector="TECH",
        breadth=Decimal("0.55"),
        benchmark_return=Decimal("-0.01"),
    )


def trending_snapshot(symbol: str = "TREND_TEST") -> MarketSnapshot:
    closes = [str(100 + i * 2) for i in range(25)]
    vols = ["150000"] * 24 + ["220000"]
    bars = _bars(symbol, closes, vols)
    last = bars[-1]
    return MarketSnapshot(
        symbol=symbol,
        last_price=last.close,
        bid=last.close - Decimal("0.01"),
        ask=last.close + Decimal("0.01"),
        spread=Decimal("0.01"),
        volume=last.volume,
        avg_traded_value=Decimal("8000000"),
        volatility=Decimal("0.015"),
        market_state="OPEN",
        data_quality="VALID",
        freshness_seconds=5,
        bars=bars,
        source_identity="fixture",
        sector="TECH",
        breadth=Decimal("0.62"),
        benchmark_return=Decimal("0.05"),
    )


def momentum_snapshot(symbol: str = "MOM_TEST") -> MarketSnapshot:
    closes = [str(50 + i) for i in range(15)]
    bars = _bars(symbol, closes, ["200000"] * 15)
    last = bars[-1]
    return MarketSnapshot(
        symbol=symbol,
        last_price=last.close,
        bid=last.close - Decimal("0.02"),
        ask=last.close + Decimal("0.02"),
        spread=Decimal("0.04"),
        volume=last.volume,
        avg_traded_value=Decimal("4000000"),
        volatility=Decimal("0.018"),
        market_state="OPEN",
        data_quality="VALID",
        freshness_seconds=8,
        bars=bars,
        source_identity="fixture",
        sector="FIN",
        breadth=Decimal("0.58"),
        benchmark_return=Decimal("0.01"),
    )


def sparse_snapshot(symbol: str = "SPARSE") -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        last_price=Decimal("10"),
        data_quality="VALID",
        freshness_seconds=0,
        bars=_bars(symbol, ["10", "10.1"]),
        source_identity="fixture",
    )


def event_risk_snapshot(symbol: str = "EVENT") -> MarketSnapshot:
    snap = trending_snapshot(symbol)
    snap.event_risk = True
    snap.earnings_window = True
    return snap
