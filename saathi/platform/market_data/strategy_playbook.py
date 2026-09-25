"""Pro Trading Strategy Playbook.

Ported from the owner's crypto-signal-bot (`layers/strategies.py`) — the pro-trader
strategy catalog he built long ago (Michael van de Poppe, Pentoshi, Plan B, etc.).
Here it runs deterministically against SaathiOS's own technical-analysis evidence
for BOTH NEPSE and crypto. Research/education only — never advice or an order.

Each strategy is a named rule set evaluated over deterministic indicators
(EMA21/50/200, RSI, ATR, ADX, MACD histogram, VWAP). A match reports a score
(fraction of confluences met), the reasons that fired, and a structural
entry/stop/target derived from the same indicators.
"""
from __future__ import annotations

from typing import Any

from saathi.platform.market_data.technical_analysis import signals_only

AUTHORITY = {
    "authority": "research_only",
    "disclaimer": "Deterministic strategy scan over real OHLC — research/education only, not advice, never an order. Paper-trade first; risk ≤2% per idea.",
}

# ── Strategy catalog (metadata) ──────────────────────────────────────────────
STRATEGIES: list[dict[str, Any]] = [
    {
        "id": "ema_pullback", "name": "EMA21 Pullback", "trader": "Michael van de Poppe",
        "style": "Swing", "tf": "1h/1d",
        "desc": "Price pulls back to EMA21 in an uptrend (EMA21 > EMA50 > EMA200); buy the dip on RSI reset.",
        "rules": {"trend": "EMA21 > EMA50 > EMA200", "entry": "Price within ~1.2% of EMA21",
                  "confirm": "RSI 38–62, MACD hist > 0", "sl": "Below EMA50", "tp": "2× ATR above entry"},
    },
    {
        "id": "support_flip", "name": "Support Flip", "trader": "Michael van de Poppe",
        "style": "Breakout", "tf": "4h/1d",
        "desc": "Former resistance flips to support after a clean breakout; enter on the retest.",
        "rules": {"trend": "Above EMA200", "entry": "Retest of EMA50 as support (~1%)",
                  "confirm": "RSI > 48, MACD hist > 0", "sl": "Below EMA200", "tp": "2× ATR / measured move"},
    },
    {
        "id": "macd_momentum", "name": "MACD Momentum Cross", "trader": "Pentoshi",
        "style": "Momentum", "tf": "1h",
        "desc": "MACD histogram turns positive above EMA200 — catch early momentum before the crowd.",
        "rules": {"trend": "Above EMA200", "entry": "MACD histogram positive",
                  "confirm": "RSI 48–68", "sl": "1.2× ATR below entry", "tp": "1.8× ATR"},
    },
    {
        "id": "rsi_oversold_bounce", "name": "RSI Oversold Bounce", "trader": "Crypto Rover / DCA Mindset",
        "style": "Counter-trend", "tf": "1h/1d",
        "desc": "Deeply oversold RSI (<34) inside a long-term uptrend, price reclaiming EMA21 — bounce.",
        "rules": {"trend": "Above EMA200", "entry": "RSI < 34",
                  "confirm": "Price reclaiming EMA21", "sl": "1× ATR below entry", "tp": "EMA21"},
    },
    {
        "id": "vwap_reclaim", "name": "VWAP Reclaim", "trader": "Institutional / Smart Money",
        "style": "Intraday", "tf": "1h",
        "desc": "Price reclaims and holds above VWAP — the institutional line of control.",
        "rules": {"trend": "Above VWAP", "entry": "Within ~0.8% of VWAP (fresh reclaim)",
                  "confirm": "RSI > 44, MACD hist > 0", "sl": "Just below VWAP", "tp": "1.5× ATR"},
    },
    {
        "id": "ema_squeeze_breakout", "name": "EMA Squeeze Breakout", "trader": "Plan B / Trend Followers",
        "style": "Breakout", "tf": "4h/1d",
        "desc": "EMAs coil into a tight squeeze, then price breaks above the cluster — expansion.",
        "rules": {"trend": "EMA spread < 3% (coil)", "entry": "Price breaks above EMA cluster",
                  "confirm": "RSI > 52, MACD hist > 0", "sl": "Below EMA cluster", "tp": "3× ATR"},
    },
    {
        "id": "adx_trend_ride", "name": "ADX Strong Trend Ride", "trader": "Professional Momentum Traders",
        "style": "Trend-following", "tf": "1h/1d",
        "desc": "ADX > 25 confirms a strong trend; ride pullbacks to EMA21 while EMA50 holds.",
        "rules": {"trend": "ADX > 25, price > EMA50", "entry": "Pullback to EMA21 (~1.5%)",
                  "confirm": "MACD hist > 0", "sl": "Below EMA50", "tp": "2× ATR"},
    },
    {
        "id": "fear_contrarian", "name": "Extreme Fear Contrarian Buy", "trader": "Warren Buffett (adapted)",
        "style": "Macro / DCA", "tf": "Daily",
        "desc": "Accumulate when the crowd panics (extreme fear). Needs the live Fear & Greed index — reference only here.",
        "rules": {"trend": "Macro uptrend intact", "entry": "Fear & Greed in Extreme Fear",
                  "confirm": "Manual macro check", "sl": "Wide / DCA", "tp": "Mean reversion to trend"},
        "manual": True,  # not machine-scanned: depends on an external sentiment index
    },
]
_BY_ID = {s["id"]: s for s in STRATEGIES}


def catalog() -> dict[str, Any]:
    return {"count": len(STRATEGIES), "strategies": STRATEGIES, **AUTHORITY}


def _grade(score: float) -> str:
    return "A" if score >= 0.85 else "B" if score >= 0.70 else "C"


def _round(v: float | None, dp: int = 2) -> float | None:
    return None if v is None else round(v, dp)


def _evaluate(sig: dict[str, Any]) -> list[dict[str, Any]]:
    """Faithful port of the bot's rule evaluators, reading deterministic evidence."""
    p = sig.get("last")
    e21, e50, e200 = sig.get("ema21"), sig.get("ema50"), sig.get("ema200")
    rsi = sig.get("rsi14")
    atr = sig.get("atr14")
    adx = sig.get("adx")
    mh = sig.get("macd_hist")
    vwap = sig.get("vwap")
    if p is None:
        return []
    macd_pos = mh is not None and mh > 0
    out: list[dict[str, Any]] = []

    def add(sid, side, checks, entry, sl, tp):
        score = sum(1 for _, ok in checks if ok) / len(checks)
        reasons = [txt for txt, ok in checks if ok]
        thr = _THRESH[sid]
        gate = thr["gate"](checks)
        if score >= thr["min"] and gate:
            out.append({
                "id": sid, "name": _BY_ID[sid]["name"], "trader": _BY_ID[sid]["trader"],
                "style": _BY_ID[sid]["style"], "side": side, "score": round(score, 2),
                "grade": _grade(score), "reasons": reasons,
                "entry": _round(entry), "stop": _round(sl), "target": _round(tp),
            })

    # ema_pullback
    if None not in (e21, e50, e200) and rsi is not None and atr is not None:
        trend_ok = e21 > e50 > e200
        near = abs(p - e21) / e21 < 0.012
        rsi_ok = 38 <= rsi <= 62
        add("ema_pullback", "LONG", [
            (f"EMA21>{'>'.join(str(x) for x in [e50, e200])} uptrend", trend_ok),
            (f"Price {p} near EMA21 ({abs(p - e21) / e21 * 100:.1f}% away)", near),
            (f"RSI {rsi:.0f} in reset zone 38–62", rsi_ok),
            ("MACD histogram positive", macd_pos),
        ], p, e50 * 0.995, p + 2 * atr)

    # macd_momentum
    if e200 is not None and rsi is not None and atr is not None:
        above = p > e200
        rsi_ok = 48 <= rsi <= 68
        add("macd_momentum", "LONG", [
            (f"Price above EMA200 ({e200})", above),
            (f"MACD histogram positive ({mh})", macd_pos),
            (f"RSI {rsi:.0f} in momentum zone", rsi_ok),
        ], p, p - 1.2 * atr, p + 1.8 * atr)

    # rsi_oversold_bounce
    if e200 is not None and e21 is not None and rsi is not None and atr is not None:
        above = p > e200
        oversold = rsi < 34
        bouncing = rsi > 28 and p > e21
        add("rsi_oversold_bounce", "LONG", [
            (f"Long-term uptrend intact (above EMA200 {e200})", above),
            (f"RSI {rsi:.0f} deeply oversold", oversold),
            ("Price reclaimed EMA21 — bounce forming", bouncing),
        ], p, p - atr, e21)

    # vwap_reclaim
    if vwap is not None and rsi is not None and atr is not None:
        above = p > vwap
        close = abs(p - vwap) / vwap < 0.008
        rsi_ok = rsi > 44
        add("vwap_reclaim", "LONG", [
            (f"Price {p} above VWAP {vwap}", above),
            ("Close to VWAP — fresh reclaim zone", close),
            (f"RSI {rsi:.0f} positive bias", rsi_ok),
            ("MACD positive", macd_pos),
        ], p, vwap * 0.997, p + 1.5 * atr)

    # ema_squeeze_breakout
    if None not in (e21, e50, e200) and rsi is not None and atr is not None:
        spread = (max(e21, e50, e200) - min(e21, e50, e200)) / e200
        squeeze = spread < 0.03
        breakout = p > max(e21, e50, e200)
        add("ema_squeeze_breakout", "LONG", [
            (f"EMA squeeze ({spread * 100:.1f}% spread) — coil building", squeeze),
            ("Price breaking above EMA cluster", breakout),
            (f"RSI {rsi:.0f} confirming breakout", rsi > 52),
            ("MACD positive", macd_pos),
        ], p, min(e21, e50, e200) * 0.995, p + 3 * atr)

    # adx_trend_ride
    if e21 is not None and e50 is not None and atr is not None:
        strong = adx is not None and adx > 25
        near = abs(p - e21) / e21 < 0.015
        intact = p > e50
        add("adx_trend_ride", "LONG", [
            (f"ADX {adx:.0f} — strong trend confirmed" if adx is not None else "ADX n/a", strong),
            (f"Pullback to EMA21 ({e21})", near),
            ("EMA50 support intact", intact),
            ("MACD positive", macd_pos),
        ], p, e50 * 0.993, p + 2 * atr)

    # support_flip
    if e50 is not None and e200 is not None and rsi is not None and atr is not None:
        retest = abs(p - e50) / e50 < 0.01
        above = p > e200
        rsi_ok = rsi > 48
        add("support_flip", "LONG", [
            ("Price above EMA200 (trend intact)", above),
            (f"Retesting EMA50 ({e50}) as support", retest),
            (f"RSI {rsi:.0f} bullish", rsi_ok),
            ("MACD positive", macd_pos),
        ], p, e200 * 0.995, p + 2 * atr)

    out.sort(key=lambda m: m["score"], reverse=True)
    return out


# Per-strategy acceptance gate — mirrors the bot's score cutoffs + hard conditions.
_THRESH = {
    "ema_pullback": {"min": 0.75, "gate": lambda c: True},
    "macd_momentum": {"min": 0.66, "gate": lambda c: True},
    "rsi_oversold_bounce": {"min": 0.5, "gate": lambda c: c[1][1]},   # requires oversold
    "vwap_reclaim": {"min": 0.5, "gate": lambda c: c[0][1] and c[1][1]},  # above + close to VWAP
    "ema_squeeze_breakout": {"min": 0.75, "gate": lambda c: True},
    "adx_trend_ride": {"min": 0.75, "gate": lambda c: True},
    "support_flip": {"min": 0.75, "gate": lambda c: True},
}


def scan(market: str, symbol: str, timeframe: str = "1d") -> dict[str, Any]:
    """Evaluate every machine-scannable strategy against one symbol's live evidence."""
    sig = signals_only(market, symbol, timeframe)
    if not sig.get("available"):
        return {"available": False, "market": market, "symbol": symbol,
                "error": sig.get("error") or "no data", "matches": [], **AUTHORITY}
    ev = sig.get("evidence") or {}
    matches = _evaluate(ev)
    return {
        "available": True, "market": market, "symbol": symbol,
        "evidence": ev, "matches": matches, "match_count": len(matches),
        "scanned": len(_THRESH), "manual_only": [s["id"] for s in STRATEGIES if s.get("manual")],
        **AUTHORITY,
    }
