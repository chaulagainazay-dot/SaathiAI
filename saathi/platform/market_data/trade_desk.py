"""Trade Desk — Smart-Charts-style read for a symbol, all deterministic + observation-only.

Bundles three things a trader wants at a glance, computed from real OHLC:
  * TRADE SETUP: the current ATR trend setup (entry/stop/target/RR) plus possible loss% and
    possible profit% — the same gate the paper agent uses. No orders, no advice.
  * VOLUME STRENGTH: buyer vs seller strength by period. Crypto uses Binance taker-buy volume
    (real aggressor split); NEPSE uses an up/down-candle volume proxy (labelled as a proxy).
  * S/R ZONES: support/resistance clustered into zones (S1/S2/R1/R2) from swing extrema.

Nothing here is financial advice or an execution — descriptive research only.
"""
from __future__ import annotations

from typing import Any

_STRENGTH_PERIODS = [("Today", 1), ("3 Days", 3), ("1 Week", 7), ("1 Month", 30)]


def _rnd(v, dp=2):
    return None if v is None else round(float(v), dp)


def _cluster(levels: list[float], tol_frac: float) -> list[dict]:
    """Group nearby levels into zones [low, high, mid]. tol_frac relative to level size."""
    if not levels:
        return []
    levels = sorted(levels)
    zones, group = [], [levels[0]]
    for v in levels[1:]:
        if abs(v - group[-1]) <= tol_frac * group[-1]:
            group.append(v)
        else:
            zones.append(group); group = [v]
    zones.append(group)
    return [{"low": _rnd(min(g)), "high": _rnd(max(g)), "mid": _rnd(sum(g) / len(g))} for g in zones]


def sr_zones(ohlc: list[dict], last: float) -> dict[str, Any]:
    """Support zones below price (S1 nearest), resistance zones above (R1 nearest)."""
    from saathi.platform.market_data.smc import _swings, _f
    highs = _f([p.get("high") for p in ohlc])
    lows = _f([p.get("low") for p in ohlc])
    sh, sl = _swings(highs, lows)
    res_levels = [s["price"] for s in sh if s["price"] and s["price"] > last]
    sup_levels = [s["price"] for s in sl if s["price"] and s["price"] < last]
    res = _cluster(res_levels, 0.015)
    sup = _cluster(sup_levels, 0.015)
    res.sort(key=lambda z: z["mid"])                     # nearest resistance first (just above)
    sup.sort(key=lambda z: z["mid"], reverse=True)       # nearest support first (just below)
    out = {}
    for i, z in enumerate(res[:3], 1):
        out[f"R{i}"] = z
    for i, z in enumerate(sup[:3], 1):
        out[f"S{i}"] = z
    return out


def _crypto_strength(symbol: str) -> list[dict] | None:
    from saathi.platform.market_data.technical_analysis import _crypto_pair
    try:
        import httpx
        r = httpx.get("https://data-api.binance.vision/api/v3/klines",
                      params={"symbol": _crypto_pair(symbol), "interval": "1d", "limit": "31"}, timeout=20)
        r.raise_for_status()
        rows = r.json()
        # each: [.., vol(5), .., .., taker_buy_base(9), ..]
        return [{"vol": float(k[5]), "buy": float(k[9])} for k in rows]
    except Exception:
        return None


def volume_strength(market: str, symbol: str, ohlc: list[dict]) -> dict[str, Any]:
    """Buyer vs seller strength (%) per period. Real taker split for crypto; proxy for NEPSE."""
    rows, method = None, ""
    if market == "CRYPTO":
        cr = _crypto_strength(symbol)
        if cr:
            rows = cr
            method = "Binance taker-buy volume (real aggressor split)"
    if rows is None:
        # NEPSE / fallback proxy: up-candle volume = buyer, down-candle = seller
        rows = []
        for p in ohlc:
            try:
                o, c, v = float(p["open"]), float(p["close"]), float(p.get("volume") or 0)
            except (TypeError, ValueError, KeyError):
                continue
            rows.append({"vol": v, "buy": v if c >= o else 0.0})
        method = "up/down-candle volume proxy (no aggressor data)"
    periods = []
    for label, days in _STRENGTH_PERIODS:
        win = rows[-days:] if len(rows) >= days else rows
        tot = sum(x["vol"] for x in win)
        buy = sum(x["buy"] for x in win)
        if tot <= 0:
            periods.append({"period": label, "buyer": None, "seller": None})
            continue
        b = round(buy / tot * 100, 0)
        periods.append({"period": label, "buyer": b, "seller": round(100 - b, 0),
                        "winner": "buyer" if b >= 50 else "seller"})
    return {"method": method, "periods": periods}


def trade_setup(market: str, symbol: str) -> dict[str, Any]:
    """Current setup with possible loss%/profit% (from the paper-agent ATR gate)."""
    from saathi.platform.finance import paper_trading as pt
    p = pt.propose(market, symbol)
    if not p.get("setup"):
        return {"setup": False, "reason": p.get("reason"), "market": p.get("market"), "symbol": p.get("symbol")}
    entry, stop, target = p["entry"], p["stop"], p["target"]
    loss_pct = abs(entry - stop) / entry * 100 if entry else None
    profit_pct = abs(target - entry) / entry * 100 if entry else None
    return {"setup": True, "market": p["market"], "symbol": p["symbol"], "side": p["side"],
            "entry": entry, "stop": stop, "target": target, "rr": p["planned_r"],
            "possible_loss_pct": _rnd(loss_pct), "possible_profit_pct": _rnd(profit_pct),
            "strategy": "ATR trend-following (breakout/continuation)", "rationale": p["rationale"]}


def desk(market: str, symbol: str) -> dict[str, Any]:
    from saathi.platform.market_data.technical_analysis import signals_only
    base = signals_only(market, symbol)
    if not base.get("available"):
        return {"available": False, "market": base.get("market"), "symbol": base.get("symbol"),
                "error": base.get("error")}
    ev = base["evidence"]
    ohlc = base.get("ohlc") or []
    return {
        "available": True, "market": base["market"], "symbol": base["symbol"],
        "last": ev.get("last"), "trend": ev.get("trend"), "source": base.get("source"),
        "trade_setup": trade_setup(base["market"], base["symbol"]),
        "volume_strength": volume_strength(base["market"], base["symbol"], ohlc),
        "sr_zones": sr_zones(ohlc, ev.get("last")),
        "authority": "OBSERVATION_ONLY", "advice": False,
        "disclaimer": "Descriptive research only — not financial advice, never an execution.",
    }
