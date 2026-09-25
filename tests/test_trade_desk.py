"""Trade Desk — S/R zone clustering + volume-strength proxy (hermetic; no network)."""
from __future__ import annotations

from saathi.platform.market_data import trade_desk as td


def _c(o, h, l, c, v=100):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def test_sr_zones_split_around_price():
    # swing highs above 100, swing lows below → resistance above, support below
    bars = []
    for i in range(40):
        base = 100 + (5 if i % 6 == 0 else -5 if i % 6 == 3 else 0)
        bars.append(_c(base, base + 3, base - 3, base))
    z = td.sr_zones(bars, 100.0)
    for k, v in z.items():
        if k.startswith("R"):
            assert v["mid"] >= 100
        if k.startswith("S"):
            assert v["mid"] <= 100


def test_volume_strength_proxy_buyer_on_up_candles():
    # all up candles → buyer strength 100%
    bars = [_c(100 + i, 101 + i, 99 + i, 100.5 + i, v=100) for i in range(30)]
    vs = td.volume_strength("NEPSE", "X", bars)
    assert "proxy" in vs["method"]
    today = next(p for p in vs["periods"] if p["period"] == "Today")
    assert today["buyer"] == 100.0 and today["seller"] == 0.0


def test_volume_strength_seller_on_down_candles():
    bars = [_c(100 - i, 101 - i, 98 - i, 99.5 - i, v=100) for i in range(30)]
    vs = td.volume_strength("NEPSE", "X", bars)
    wk = next(p for p in vs["periods"] if p["period"] == "1 Week")
    assert wk["seller"] == 100.0


def test_cluster_merges_near_levels():
    zones = td._cluster([100, 100.5, 108, 108.3], 0.02)
    assert len(zones) == 2
    assert zones[0]["low"] == 100 and zones[0]["high"] == 100.5
