"""Descriptive technical indicators — pure, deterministic, reproducible.

These are DESCRIPTIVE_ANALYTICS ONLY. They are NOT buy/sell/entry/exit signals,
target prices, stop-losses, or position sizing. No dependency on the strategy/signal
contracts. Every result exposes its parameters. Values align 1:1 with the input
series; warm-up positions are None (never fabricated).
"""
from __future__ import annotations

from dataclasses import dataclass, field

KIND = "DESCRIPTIVE_ANALYTICS"

# conventional defaults (exposed in output, not hidden)
DEFAULTS = {
    "sma": [20, 50], "ema": [12, 26], "rsi": 14, "macd": (12, 26, 9),
    "bollinger": (20, 2.0), "atr": 14,
}


@dataclass(frozen=True)
class IndicatorResult:
    name: str
    params: dict
    series: dict            # {line_name: [float|None, ...]} aligned to input length
    kind: str = KIND

    def to_public(self) -> dict:
        return {"name": self.name, "kind": self.kind, "params": self.params,
                "series": self.series}


def _f(xs) -> list[float]:
    return [float(x) for x in xs]


def sma(closes, period: int = 20) -> IndicatorResult:
    c = _f(closes)
    out: list = [None] * len(c)
    s = 0.0
    for i, v in enumerate(c):
        s += v
        if i >= period:
            s -= c[i - period]
        if i >= period - 1:
            out[i] = round(s / period, 6)
    return IndicatorResult("SMA", {"period": period}, {f"sma_{period}": out})


def ema(closes, period: int = 12) -> IndicatorResult:
    c = _f(closes)
    out: list = [None] * len(c)
    if len(c) < period:
        return IndicatorResult("EMA", {"period": period}, {f"ema_{period}": out})
    k = 2.0 / (period + 1)
    seed = sum(c[:period]) / period
    out[period - 1] = round(seed, 6)
    prev = seed
    for i in range(period, len(c)):
        prev = c[i] * k + prev * (1 - k)
        out[i] = round(prev, 6)
    return IndicatorResult("EMA", {"period": period}, {f"ema_{period}": out})


def _ema_raw(values, period):
    out = [None] * len(values)
    xs = [v for v in values]
    # first index where enough non-None exist
    start = period - 1
    if len([v for v in xs[:period] if v is not None]) < period:
        return out
    k = 2.0 / (period + 1)
    seed = sum(xs[:period]) / period
    out[start] = seed
    prev = seed
    for i in range(period, len(xs)):
        if xs[i] is None:
            out[i] = prev
            continue
        prev = xs[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes, period: int = 14) -> IndicatorResult:
    c = _f(closes)
    out: list = [None] * len(c)
    if len(c) <= period:
        return IndicatorResult("RSI", {"period": period}, {"rsi": out})
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        d = c[i] - c[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / period, losses / period
    out[period] = round(100 - 100 / (1 + (ag / al if al else float("inf"))), 4) if al else 100.0
    for i in range(period + 1, len(c)):
        d = c[i] - c[i - 1]
        ag = (ag * (period - 1) + max(d, 0.0)) / period
        al = (al * (period - 1) + max(-d, 0.0)) / period
        out[i] = round(100 - 100 / (1 + (ag / al)), 4) if al else 100.0
    return IndicatorResult("RSI", {"period": period}, {"rsi": out})


def macd(closes, fast: int = 12, slow: int = 26, signal: int = 9) -> IndicatorResult:
    c = _f(closes)
    ef = ema(c, fast).series[f"ema_{fast}"]
    es = ema(c, slow).series[f"ema_{slow}"]
    line = [None if (ef[i] is None or es[i] is None) else round(ef[i] - es[i], 6)
            for i in range(len(c))]
    sig_raw = _ema_raw([v for v in line], signal)
    sig = [None if v is None else round(v, 6) for v in sig_raw]
    hist = [None if (line[i] is None or sig[i] is None) else round(line[i] - sig[i], 6)
            for i in range(len(c))]
    return IndicatorResult("MACD", {"fast": fast, "slow": slow, "signal": signal},
                           {"macd": line, "signal": sig, "histogram": hist})


def bollinger(closes, period: int = 20, num_std: float = 2.0) -> IndicatorResult:
    c = _f(closes)
    mid = sma(c, period).series[f"sma_{period}"]
    upper: list = [None] * len(c)
    lower: list = [None] * len(c)
    for i in range(len(c)):
        if mid[i] is None:
            continue
        window = c[i - period + 1:i + 1]
        m = mid[i]
        var = sum((x - m) ** 2 for x in window) / period
        sd = var ** 0.5
        upper[i] = round(m + num_std * sd, 6)
        lower[i] = round(m - num_std * sd, 6)
    return IndicatorResult("BOLLINGER", {"period": period, "num_std": num_std},
                           {f"bb_mid_{period}": mid, "bb_upper": upper, "bb_lower": lower})


def atr(points, period: int = 14) -> IndicatorResult:
    """Average True Range from OHLC points (needs high/low/close)."""
    highs = [float(p.high) for p in points]
    lows = [float(p.low) for p in points]
    closes = [float(p.close) for p in points]
    n = len(points)
    out: list = [None] * n
    if n <= period:
        return IndicatorResult("ATR", {"period": period}, {"atr": out})
    tr = [None] * n
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]))
    first = sum(tr[1:period + 1]) / period
    out[period] = round(first, 6)
    prev = first
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + tr[i]) / period
        out[i] = round(prev, 6)
    return IndicatorResult("ATR", {"period": period}, {"atr": out})


def compute_all(series, *, which=None) -> dict[str, IndicatorResult]:
    """Compute the requested descriptive indicators on a MarketSeries.
    `which` = subset of {'sma','ema','rsi','macd','bollinger','atr'} (default all)."""
    which = set(which or ("sma", "ema", "rsi", "macd", "bollinger", "atr"))
    closes = series.closes
    out: dict[str, IndicatorResult] = {}
    if "sma" in which:
        for p in DEFAULTS["sma"]:
            out[f"sma_{p}"] = sma(closes, p)
    if "ema" in which:
        for p in DEFAULTS["ema"]:
            out[f"ema_{p}"] = ema(closes, p)
    if "rsi" in which:
        out["rsi"] = rsi(closes, DEFAULTS["rsi"])
    if "macd" in which:
        out["macd"] = macd(closes, *DEFAULTS["macd"])
    if "bollinger" in which:
        out["bollinger"] = bollinger(closes, *DEFAULTS["bollinger"])
    if "atr" in which:
        out["atr"] = atr(series.points, DEFAULTS["atr"])
    return out
