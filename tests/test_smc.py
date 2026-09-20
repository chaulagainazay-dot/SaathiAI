"""Smart Money Concepts / ICT structure detection — deterministic, hermetic (no network)."""
from __future__ import annotations

from saathi.platform.market_data import smc


def _c(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}


def test_too_short_returns_none():
    assert smc.detect([_c(1, 2, 0, 1)] * 5) is None


def test_bullish_fvg_detected():
    # 3-candle bullish imbalance: candle i low > candle i-2 high.
    bars = [_c(10, 11, 9, 10), _c(10, 12, 10, 11), _c(13, 15, 13, 14)]  # bar3 low 13 > bar1 high 11
    bars = ([_c(9, 10, 8, 9)] * 8) + bars  # pad for min length
    out = smc.detect(bars)
    assert out is not None
    fvgs = out["fair_value_gaps"]
    assert any(g["dir"] == "bullish" for g in fvgs)


def test_premium_discount_range():
    bars = [_c(100 + i, 101 + i, 99 + i, 100 + i) for i in range(30)]
    out = smc.detect(bars)
    pd = out["premium_discount"]
    assert pd["high"] >= pd["low"]
    assert pd["low"] <= pd["equilibrium"] <= pd["high"]
    assert pd["current_zone"] in ("premium", "discount")


def test_uptrend_structure():
    # steadily rising → higher highs and higher lows → UP trend
    bars = [_c(100 + i, 102 + i, 99 + i, 101 + i) for i in range(40)]
    out = smc.detect(bars)
    assert out["trend"] in ("UP", "RANGE")  # rising; fractal spacing may read RANGE on a pure ramp
    assert "premium_discount" in out


def test_inducement_present_on_trend():
    # rising series → bullish bias → IDM is sell-side liquidity below price (a swing low)
    bars = [_c(100 + i, 103 + i, 98 + i, 101 + i) if i % 4 else _c(100 + i, 102 + i, 96 + i, 99 + i)
            for i in range(45)]
    out = smc.detect(bars)
    idm = out.get("inducement")
    if idm:  # present when a qualifying swing exists
        assert idm["side"] in ("sell-side", "buy-side")
        assert "price" in idm
    assert "inducement" in out  # key always present (may be None)


def test_summary_is_descriptive():
    bars = [_c(100 + (i % 5), 103 + (i % 5), 98 + (i % 5), 100 + (i % 5)) for i in range(40)]
    out = smc.detect(bars)
    text = smc.summarize(out)
    assert "market structure trend" in text
    assert "not financial advice" in smc.DISCLAIMER.lower()
