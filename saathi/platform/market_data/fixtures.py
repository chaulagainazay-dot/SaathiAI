"""M62.2 — deterministic, network-free fixture provider.

Stable across runs: fixed base time, fixed seed, explicit UTC, Decimal prices.
Datasets include both VALID and intentionally-INVALID records so certification can
prove the quality layer catches defects. Not optimized for profitability.

Each dataset has a content hash (sha256 over its canonical serialization) exposed
via `fixture_manifest()` for reproducibility evidence.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from saathi.platform.market_data.models import (
    MDInstrument, MDQuote, MDBar, Timeframe, TIMEFRAME_SECONDS, MarketDataQuality,
)
from saathi.platform.market_data.provider import (
    MarketDataProvider, ProviderResult, ProviderStatus, MarketClock,
)
from saathi.platform.market_data.calendar import DEFAULT_24_5, RTH_UTC, get_calendar
from saathi.platform.trading_models import AssetClass, MarketState

# Fixed deterministic base — a Monday, 00:00 UTC.
BASE = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
FIXTURE_VERSION = "m62_2.v1"

DATASETS = (
    "TRENDING", "MEAN_REVERTING", "FLAT", "HIGH_VOLATILITY", "GAP_DOWN", "ILLIQUID",
    "FLASH_CRASH_LIKE", "MISSING_BARS", "DUPLICATE_BARS", "OUT_OF_ORDER_BARS",
    "STALE_QUOTES", "FUTURE_TIMESTAMPS", "INVALID_OHLC", "ABNORMAL_SPREAD", "MARKET_CLOSED",
)


def _prng(seed: str):
    """Deterministic pseudo-random Decimals in [-1, 1] from a seed (sha256 stream)."""
    i = 0
    while True:
        h = hashlib.sha256(f"{seed}:{i}".encode()).hexdigest()
        # map first 8 hex to [0,1)
        val = int(h[:8], 16) / 0xFFFFFFFF
        yield Decimal(str(round(val * 2 - 1, 6)))
        i += 1


def _bar(symbol, tf, start, o, h, l, c, v, provider="fixture"):
    dur = TIMEFRAME_SECONDS[tf]
    end = start + timedelta(seconds=dur)
    return MDBar(instrument=symbol, timeframe=tf, provider=provider,
                 open=Decimal(str(o)), high=Decimal(str(h)), low=Decimal(str(l)),
                 close=Decimal(str(c)), volume=Decimal(str(v)),
                 start_time=start, end_time=end, source_time=end, ingested_at=end)


def _price_path(name, n=30, start_price=Decimal("100")):
    """Return list of (open, high, low, close, volume) deterministically."""
    out = []
    px = start_price
    rng = _prng(name)
    for k in range(n):
        r = next(rng)
        if name == "TRENDING":
            drift = Decimal("0.5")
            nxt = px + drift + r * Decimal("0.2")
        elif name == "MEAN_REVERTING":
            nxt = start_price + r * Decimal("2")
        elif name == "FLAT":
            nxt = start_price
        elif name == "HIGH_VOLATILITY":
            nxt = px + r * Decimal("8")
        elif name == "ILLIQUID":
            nxt = px + r * Decimal("0.1")
        else:
            nxt = px + r
        if nxt <= 0:
            nxt = Decimal("1")
        o = px
        c = nxt
        hi = max(o, c) + abs(r) * Decimal("0.3")
        lo = min(o, c) - abs(r) * Decimal("0.3")
        if lo <= 0:
            lo = Decimal("0.5")
        vol = Decimal("100") if name == "ILLIQUID" else Decimal("100000")
        out.append((o.quantize(Decimal("0.01")), hi.quantize(Decimal("0.01")),
                    lo.quantize(Decimal("0.01")), c.quantize(Decimal("0.01")), vol))
        px = nxt
    return out


def build_bars(name: str, timeframe: Timeframe = Timeframe.D1, n: int = 30) -> list[MDBar]:
    """Deterministic bar dataset for `name`, with defects injected where the name
    denotes a defect class."""
    step = TIMEFRAME_SECONDS[timeframe]
    if name in ("TRENDING", "MEAN_REVERTING", "FLAT", "HIGH_VOLATILITY", "ILLIQUID"):
        path = _price_path(name, n)
        return [_bar(name, timeframe, BASE + timedelta(seconds=step * k), *path[k]) for k in range(n)]
    if name == "GAP_DOWN":
        path = _price_path("FLAT", n)
        bars = [_bar(name, timeframe, BASE + timedelta(seconds=step * k), *path[k]) for k in range(n)]
        # a real gap-down: bar 15 opens far below prior close (valid OHLC, just a jump)
        b = bars[15]
        b.open = Decimal("60"); b.high = Decimal("61"); b.low = Decimal("55"); b.close = Decimal("58")
        return bars
    if name == "FLASH_CRASH_LIKE":
        path = _price_path("FLAT", n)
        bars = [_bar(name, timeframe, BASE + timedelta(seconds=step * k), *path[k]) for k in range(n)]
        b = bars[10]
        b.open = Decimal("100"); b.high = Decimal("100"); b.low = Decimal("30"); b.close = Decimal("35")
        return bars
    if name == "MISSING_BARS":
        path = _price_path("FLAT", n)
        bars = [_bar(name, timeframe, BASE + timedelta(seconds=step * k), *path[k]) for k in range(n)]
        del bars[12:15]  # remove 3 intervals -> gap
        return bars
    if name == "DUPLICATE_BARS":
        bars = build_bars("FLAT", timeframe, n)
        for b in bars:
            b.instrument = name
        bars.insert(6, bars[5])  # duplicate interval
        return bars
    if name == "OUT_OF_ORDER_BARS":
        bars = build_bars("FLAT", timeframe, n)
        for b in bars:
            b.instrument = name
        bars[7], bars[8] = bars[8], bars[7]  # swap two
        return bars
    if name == "INVALID_OHLC":
        bars = build_bars("FLAT", timeframe, n)
        for b in bars:
            b.instrument = name
        bad = bars[9]
        bad.high = Decimal("50"); bad.low = Decimal("120")  # high < low
        return bars
    if name == "FUTURE_TIMESTAMPS":
        bars = build_bars("FLAT", timeframe, n)
        for b in bars:
            b.instrument = name
        far = BASE + timedelta(days=3650)  # year 2036
        bars[-1].start_time = far
        bars[-1].end_time = far + timedelta(seconds=step)
        bars[-1].source_time = far
        return bars
    # quote-only datasets: no bars
    return build_bars("FLAT", timeframe, n)


def build_quote(name: str, *, now: datetime) -> MDQuote:
    """Deterministic quote for `name`, with defects for quote defect classes."""
    src = now
    if name == "STALE_QUOTES":
        src = now - timedelta(hours=2)  # far older than freshness window
    if name == "FUTURE_TIMESTAMPS":
        src = now + timedelta(hours=1)
    bid, ask, last = Decimal("99.98"), Decimal("100.02"), Decimal("100.00")
    if name == "ABNORMAL_SPREAD":
        bid, ask = Decimal("80.00"), Decimal("120.00")  # 40% spread
    if name == "INVALID_OHLC":
        bid, ask = Decimal("-1.00"), Decimal("100.00")  # invalid price
    return MDQuote(instrument=name, provider="fixture", bid=bid, ask=ask, last=last,
                   bid_size=Decimal("10"), ask_size=Decimal("10"),
                   source_time=src, ingested_at=now, quality=MarketDataQuality.UNVERIFIED)


def _instrument(name: str) -> MDInstrument:
    cal = "RTH_UTC" if name == "MARKET_CLOSED" else "DEFAULT_24_5"
    return MDInstrument(provider="fixture", venue="SIM", symbol=name, canonical_symbol=name,
                        asset_class=AssetClass.EQUITY, timezone="UTC", market_calendar=cal)


class FixtureProvider(MarketDataProvider):
    """Serves deterministic datasets. Symbol == dataset name. Read-only."""
    name = "fixture"

    def __init__(self, *, timeframe: Timeframe = Timeframe.D1, n: int = 30):
        self.timeframe = timeframe
        self.n = n

    def get_instrument(self, symbol):
        if symbol not in DATASETS:
            return ProviderResult.error(ProviderStatus.NOT_FOUND, f"unknown fixture symbol {symbol}")
        return ProviderResult.success(_instrument(symbol))

    def get_quote(self, symbol, *, now):
        if symbol not in DATASETS:
            return ProviderResult.error(ProviderStatus.NOT_FOUND, symbol)
        return ProviderResult.success(build_quote(symbol, now=now))

    def get_bars(self, symbol, timeframe, start, end, *, now):
        if symbol not in DATASETS:
            return ProviderResult.error(ProviderStatus.NOT_FOUND, symbol)
        if timeframe not in Timeframe:
            return ProviderResult.error(ProviderStatus.UNSUPPORTED, str(timeframe))
        bars = [b for b in build_bars(symbol, timeframe, self.n)
                if start <= b.start_time <= end]
        return ProviderResult.success(bars)

    def get_market_clock(self, venue, *, now):
        cal = RTH_UTC if venue == "RTH" else DEFAULT_24_5
        return ProviderResult.success(MarketClock(venue=venue, at=now, state=cal.state_at(now)))


def _canonical(records) -> str:
    return json.dumps([r.to_public() for r in records], sort_keys=True, default=str)


def dataset_hash(name: str, timeframe: Timeframe = Timeframe.D1, n: int = 30) -> str:
    bars = build_bars(name, timeframe, n)
    return hashlib.sha256(_canonical(bars).encode()).hexdigest()


def fixture_manifest(timeframe: Timeframe = Timeframe.D1, n: int = 30) -> dict:
    return {
        "version": FIXTURE_VERSION,
        "base_time_utc": BASE.isoformat(),
        "timeframe": timeframe.value,
        "bars_per_dataset": n,
        "datasets": {name: dataset_hash(name, timeframe, n) for name in DATASETS},
    }
