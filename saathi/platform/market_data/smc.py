"""Smart Money Concepts / ICT structure detection — deterministic, from real OHLC.

Detects, with transparent rules, the price-action structures ICT/SMC traders draw:
  * market structure swing points (fractals)
  * BOS (break of structure) / CHoCH (change of character)
  * order blocks (last opposing candle before an impulsive break)
  * fair value gaps / imbalance (3-candle gaps), flagged filled/unfilled
  * liquidity (equal highs = buy-side, equal lows = sell-side)
  * premium / discount zones (dealing range + 0.5 equilibrium)

Every output is a real observed price level — nothing projected or invented. This is
descriptive market-structure research, NOT financial advice and never an execution.
"""
from __future__ import annotations

from typing import Any

DISCLAIMER = ("Market-structure research (ICT/SMC) from third-party OHLC — descriptive only, "
              "not financial advice, not a signal, never an execution.")


def _f(xs):
    out = []
    for x in xs:
        try:
            out.append(None if x is None else float(x))
        except (TypeError, ValueError):
            out.append(None)
    return out


def _rnd(v, dp=2):
    return None if v is None else round(float(v), dp)


def _swings(highs, lows, k=2):
    """Fractal swing points: a high with k lower highs on each side (mirror for lows)."""
    n = len(highs)
    sh, sl = [], []
    for i in range(k, n - k):
        hw = highs[i - k:i + k + 1]
        lw = lows[i - k:i + k + 1]
        if highs[i] is not None and all(h is not None for h in hw) and highs[i] == max(hw) and hw.count(highs[i]) == 1:
            sh.append({"i": i, "price": highs[i]})
        if lows[i] is not None and all(l is not None for l in lw) and lows[i] == min(lw) and lw.count(lows[i]) == 1:
            sl.append({"i": i, "price": lows[i]})
    return sh, sl


def _trend(sh, sl):
    up = len(sh) >= 2 and len(sl) >= 2 and sh[-1]["price"] > sh[-2]["price"] and sl[-1]["price"] > sl[-2]["price"]
    down = len(sh) >= 2 and len(sl) >= 2 and sh[-1]["price"] < sh[-2]["price"] and sl[-1]["price"] < sl[-2]["price"]
    return "UP" if up else "DOWN" if down else "RANGE"


def _structure_break(closes, sh, sl, trend):
    """Most recent close beyond the last swing → BOS (with trend) or CHoCH (against)."""
    if not closes:
        return None
    last_close = closes[-1]
    last_sh = sh[-1]["price"] if sh else None
    last_sl = sl[-1]["price"] if sl else None
    if last_sh is not None and last_close > last_sh:
        kind = "BOS" if trend == "UP" else "CHoCH"
        return {"type": kind, "dir": "bullish", "price": last_sh}
    if last_sl is not None and last_close < last_sl:
        kind = "BOS" if trend == "DOWN" else "CHoCH"
        return {"type": kind, "dir": "bearish", "price": last_sl}
    return None


def _fvgs(opens, highs, lows, closes, limit=3):
    """3-candle fair value gaps; unfilled = price has not traded back through the gap."""
    n = len(closes)
    bull, bear = [], []
    for i in range(2, n):
        if None in (highs[i - 2], lows[i], highs[i], lows[i - 2]):
            continue
        if lows[i] > highs[i - 2]:  # bullish imbalance
            bottom, top = highs[i - 2], lows[i]
            filled = any(lows[j] is not None and lows[j] <= bottom for j in range(i + 1, n))
            bull.append({"dir": "bullish", "top": top, "bottom": bottom, "i": i, "filled": filled})
        if highs[i] < lows[i - 2]:  # bearish imbalance
            bottom, top = highs[i], lows[i - 2]
            filled = any(highs[j] is not None and highs[j] >= top for j in range(i + 1, n))
            bear.append({"dir": "bearish", "top": top, "bottom": bottom, "i": i, "filled": filled})
    unfilled = [g for g in (bull + bear) if not g["filled"]]
    unfilled.sort(key=lambda g: g["i"], reverse=True)
    return unfilled[:limit]


def _order_blocks(opens, highs, lows, closes, brk):
    """Last opposing candle before the impulsive break = order block (one per side seen recently)."""
    n = len(closes)
    obs = []
    # bullish OB: last down-close candle in the final third before now
    start = max(0, n - 30)
    last_down = None
    last_up = None
    for j in range(start, n):
        if None in (opens[j], closes[j]):
            continue
        if closes[j] < opens[j]:
            last_down = j
        elif closes[j] > opens[j]:
            last_up = j
    if last_down is not None:
        obs.append({"dir": "bullish", "top": highs[last_down], "bottom": lows[last_down], "i": last_down})
    if last_up is not None:
        obs.append({"dir": "bearish", "top": highs[last_up], "bottom": lows[last_up], "i": last_up})
    return obs


def _liquidity(sh, sl, tol=0.003):
    """Equal highs (buy-side) / equal lows (sell-side) within tolerance = resting liquidity."""
    liq = []
    def eqs(points, side):
        for a in range(len(points) - 1, 0, -1):
            for b in range(a - 1, -1, -1):
                p1, p2 = points[a]["price"], points[b]["price"]
                if p1 and abs(p1 - p2) / p1 <= tol:
                    return {"side": side, "price": (p1 + p2) / 2}
        return None
    bsl = eqs(sh, "buy")
    ssl = eqs(sl, "sell")
    if bsl:
        liq.append(bsl)
    if ssl:
        liq.append(ssl)
    return liq


def _inducement(sh, sl, last, trend, brk):
    """Potential IDM (inducement): the minor opposing liquidity likely swept before the real
    move — for a bullish bias, the nearest swing low BELOW price (sell-side liquidity that gets
    grabbed before an up leg); for bearish, the nearest swing high ABOVE price."""
    bull_bias = trend == "UP" or (brk and brk["dir"] == "bullish")
    bear_bias = trend == "DOWN" or (brk and brk["dir"] == "bearish")
    if bull_bias and last is not None:
        below = [s["price"] for s in sl if s["price"] is not None and s["price"] < last]
        if below:
            return {"price": max(below), "side": "sell-side", "bias": "bullish"}
    if bear_bias and last is not None:
        above = [s["price"] for s in sh if s["price"] is not None and s["price"] > last]
        if above:
            return {"price": min(above), "side": "buy-side", "bias": "bearish"}
    return None


def _premium_discount(highs, lows, last, window=40):
    hs = [h for h in highs[-window:] if h is not None]
    ls = [l for l in lows[-window:] if l is not None]
    if not hs or not ls:
        return None
    hi, lo = max(hs), min(ls)
    eq = (hi + lo) / 2
    zone = "premium" if last is not None and last > eq else "discount"
    return {"high": hi, "low": lo, "equilibrium": eq, "current_zone": zone}


def detect(ohlc: list[dict]) -> dict[str, Any] | None:
    if not ohlc or len(ohlc) < 10:
        return None
    opens = _f([p.get("open") for p in ohlc])
    highs = _f([p.get("high") for p in ohlc])
    lows = _f([p.get("low") for p in ohlc])
    closes = _f([p.get("close") for p in ohlc])
    sh, sl = _swings(highs, lows)
    trend = _trend(sh, sl)
    brk = _structure_break(closes, sh, sl, trend)
    fvg = _fvgs(opens, highs, lows, closes)
    obs = _order_blocks(opens, highs, lows, closes, brk)
    liq = _liquidity(sh, sl)
    pd = _premium_discount(highs, lows, closes[-1] if closes else None)
    idm = _inducement(sh, sl, closes[-1] if closes else None, trend, brk)

    return {
        "trend": trend,
        "swing_highs": [{"i": s["i"], "price": _rnd(s["price"])} for s in sh[-4:]],
        "swing_lows": [{"i": s["i"], "price": _rnd(s["price"])} for s in sl[-4:]],
        "structure_break": ({"type": brk["type"], "dir": brk["dir"], "price": _rnd(brk["price"])} if brk else None),
        "order_blocks": [{"dir": o["dir"], "top": _rnd(o["top"]), "bottom": _rnd(o["bottom"]), "i": o["i"]} for o in obs],
        "fair_value_gaps": [{"dir": g["dir"], "top": _rnd(g["top"]), "bottom": _rnd(g["bottom"]), "i": g["i"], "filled": g["filled"]} for g in fvg],
        "liquidity": [{"side": q["side"], "price": _rnd(q["price"])} for q in liq],
        "premium_discount": ({k: _rnd(v) if k != "current_zone" else v for k, v in pd.items()} if pd else None),
        "inducement": ({"price": _rnd(idm["price"]), "side": idm["side"], "bias": idm["bias"]} if idm else None),
    }


def summarize(smc: dict) -> str:
    """Compact ICT/SMC evidence text for the analyst agent."""
    if not smc:
        return "No SMC structure detected."
    lines = [f"- market structure trend: {smc['trend']}"]
    b = smc.get("structure_break")
    if b:
        lines.append(f"- latest structure event: {b['type']} {b['dir']} at {b['price']}")
    for g in smc.get("fair_value_gaps", [])[:2]:
        lines.append(f"- unfilled {g['dir']} FVG: {g['bottom']}–{g['top']}")
    for o in smc.get("order_blocks", []):
        lines.append(f"- {o['dir']} order block: {o['bottom']}–{o['top']}")
    for q in smc.get("liquidity", []):
        lines.append(f"- {q['side']}-side liquidity at {q['price']}")
    idm = smc.get("inducement")
    if idm:
        lines.append(f"- potential IDM (inducement): {idm['side']} liquidity at {idm['price']} likely swept before the {idm['bias']} move")
    pd = smc.get("premium_discount")
    if pd:
        lines.append(f"- dealing range {pd['low']}–{pd['high']}, equilibrium {pd['equilibrium']} (price in {pd['current_zone']})")
    return "\n".join(lines)


def analyze(market: str, symbol: str) -> dict[str, Any]:
    """Structure detection over the symbol's OHLC (no agent — pure, fast, drawable)."""
    from saathi.platform.market_data.technical_analysis import signals_only
    base = signals_only(market, symbol)
    if not base.get("available"):
        return {"available": False, "market": base.get("market"), "symbol": base.get("symbol"),
                "error": base.get("error"), "disclaimer": DISCLAIMER}
    smc = detect(base.get("ohlc") or [])
    if smc is None:
        return {"available": False, "market": base["market"], "symbol": base["symbol"],
                "error": "INSUFFICIENT_HISTORY", "disclaimer": DISCLAIMER}
    return {"available": True, "market": base["market"], "symbol": base["symbol"],
            "smc": smc, "source": base.get("source"), "authority": "OBSERVATION_ONLY",
            "advice": False, "disclaimer": DISCLAIMER}
