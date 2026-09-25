"""Agent-assisted technical analysis for NEPSE equities and crypto.

Two-stage, grounded, research-only:
  1. DETERMINISTIC evidence from real OHLC (NEPSE tracker series / CoinGecko public OHLC):
     last, change, SMA20/50, RSI(14), trend, and nearest support/resistance.
  2. An AGENT (the governed chat engine — local Ollama or a cloud key) synthesizes a
     plain-language readout FROM that evidence only.

STRICT: research / education only, never financial advice, never a buy/sell directive, never
an execution. Crypto prices are third-party (CoinGecko); NEPSE is the third-party tracker
series — neither is canonical MD-1. Failures are reported honestly, never fabricated.
"""
from __future__ import annotations

import math
from typing import Any

DISCLAIMER = ("Research and education only — descriptive analytics from third-party data, "
              "not financial advice, not a buy/sell signal, and never an execution.")

ANALYST_SYSTEM = (
    "You are the SaathiOS Technical Analysis desk — a small team (Trend, Momentum, Levels, "
    "Structure/ICT, Risk). You are given DETERMINISTIC indicators AND Smart Money Concepts / "
    "ICT structure (market-structure trend, BOS/CHoCH, order blocks, fair value gaps, "
    "liquidity, premium/discount) already computed from real price history. Explain what they "
    "describe in clear, plain language a beginner can follow — briefly define each ICT term you "
    "use. Rules: use ONLY the numbers provided; never invent prices, targets, or news; be "
    "concise (150-220 words); output labelled sections — Trend, Momentum, Key levels, "
    "Structure (ICT/SMC), Risk. This is research and education, NOT financial advice: never say "
    "buy/sell/hold as an instruction, never promise outcomes. End with one line starting "
    "'Watch:' naming the level or event to monitor next."
)


def _f(xs: list) -> list[float]:
    out = []
    for x in xs:
        try:
            if x is None:
                continue
            out.append(float(x))
        except (TypeError, ValueError):
            continue
    return out


def _sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag = gains / period
    al = losses / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + max(d, 0.0)) / period
        al = (al * (period - 1) + max(-d, 0.0)) / period
    if al == 0:
        return 100.0
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)


def _levels(highs: list[float], lows: list[float], last: float) -> tuple[float | None, float | None]:
    """Nearest support (below) and resistance (above) from recent swing extremes."""
    win_h = highs[-40:] if highs else []
    win_l = lows[-40:] if lows else []
    res = min([h for h in win_h if h > last], default=None)
    sup = max([l for l in win_l if l < last], default=None)
    if res is None and win_h:
        res = max(win_h)
    if sup is None and win_l:
        sup = min(win_l)
    return sup, res


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    n = min(len(highs), len(lows), len(closes))
    if n < period + 1:
        return None
    trs = []
    for i in range(1, n):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def _ema_series(values: list[float], period: int) -> list[float]:
    """Exponential moving average series (Wilder-style seed = SMA of first `period`)."""
    if len(values) < period or period < 1:
        return []
    k = 2.0 / (period + 1.0)
    seed = sum(values[:period]) / period
    out = [seed]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1.0 - k))
    return out


def _ema(values: list[float], period: int) -> float | None:
    s = _ema_series(values, period)
    return s[-1] if s else None


def _macd_hist(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> float | None:
    """MACD histogram = (EMA_fast - EMA_slow) - signal EMA of that line. Last value only."""
    if len(closes) < slow + signal:
        return None
    ef = _ema_series(closes, fast)
    es = _ema_series(closes, slow)
    n = min(len(ef), len(es))
    if n == 0:
        return None
    macd_line = [ef[-n + i] - es[-n + i] for i in range(n)]
    sig = _ema_series(macd_line, signal)
    if not sig:
        return None
    return macd_line[-1] - sig[-1]


def _adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    """Average Directional Index (Wilder). Returns last ADX value."""
    n = min(len(highs), len(lows), len(closes))
    if n < period * 2 + 1:
        return None
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > dn and up > 0) else 0.0)
        minus_dm.append(dn if (dn > up and dn > 0) else 0.0)
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    if len(trs) < period:
        return None

    def _wilder_smooth(xs: list[float]) -> list[float]:
        sm = [sum(xs[:period])]
        for x in xs[period:]:
            sm.append(sm[-1] - sm[-1] / period + x)
        return sm

    atr_s = _wilder_smooth(trs)
    pdm_s = _wilder_smooth(plus_dm)
    mdm_s = _wilder_smooth(minus_dm)
    dxs = []
    for i in range(len(atr_s)):
        atr = atr_s[i]
        if atr == 0:
            continue
        pdi = 100.0 * pdm_s[i] / atr
        mdi = 100.0 * mdm_s[i] / atr
        denom = pdi + mdi
        if denom == 0:
            continue
        dxs.append(100.0 * abs(pdi - mdi) / denom)
    if len(dxs) < period:
        return None
    return sum(dxs[-period:]) / period


def _vwap(highs: list[float], lows: list[float], closes: list[float], vols: list[float], window: int = 20) -> float | None:
    """Rolling volume-weighted average price over the last `window` bars."""
    n = min(len(highs), len(lows), len(closes), len(vols))
    if n < 3:
        return None
    w = min(window, n)
    num = 0.0
    den = 0.0
    for i in range(n - w, n):
        tp = (highs[i] + lows[i] + closes[i]) / 3.0
        num += tp * vols[i]
        den += vols[i]
    if den <= 0:
        return None
    return num / den


def compute_signals(ohlc: list[dict]) -> dict[str, Any] | None:
    """ohlc: list of {open,high,low,close} (strings or numbers). Returns deterministic evidence."""
    closes = _f([p.get("close") for p in ohlc])
    highs = _f([p.get("high") or p.get("close") for p in ohlc])
    lows = _f([p.get("low") or p.get("close") for p in ohlc])
    vols = _f([p.get("volume") or p.get("vol") or 0 for p in ohlc])
    if len(closes) < 5:
        return None
    last = closes[-1]
    prev = closes[-2]
    change_pct = ((last - prev) / prev * 100.0) if prev else None
    s20 = _sma(closes, 20)
    s50 = _sma(closes, 50)
    rsi = _rsi(closes)
    if s20 is not None and s50 is not None:
        trend = ("UPTREND" if last > s20 and s20 >= s50
                 else "DOWNTREND" if last < s20 and s20 <= s50 else "SIDEWAYS")
    else:
        trend = "INSUFFICIENT_HISTORY"
    sup, res = _levels(highs, lows, last)
    # Swing levels for trade structure (real observed extrema, never projected/fabricated):
    swing_low = min(lows[-10:]) if len(lows) >= 3 else None      # recent protective low
    swing_high = max(highs[-10:]) if len(highs) >= 3 else None   # recent protective high
    range_low = min(lows[-40:]) if lows else None                # range floor
    range_high = max(highs[-40:]) if highs else None             # range ceiling

    def r(v, dp=2):
        return None if v is None else round(v, dp)

    return {
        "n_points": len(closes), "last": r(last), "change_pct": r(change_pct),
        "sma20": r(s20), "sma50": r(s50), "rsi14": r(rsi, 1),
        "ema21": r(_ema(closes, 21)), "ema50": r(_ema(closes, 50)), "ema200": r(_ema(closes, 200)),
        "macd_hist": r(_macd_hist(closes), 4), "adx": r(_adx(highs, lows, closes), 1),
        "vwap": r(_vwap(highs, lows, closes, vols)),
        "trend": trend, "support": r(sup), "resistance": r(res),
        "swing_low": r(swing_low), "swing_high": r(swing_high),
        "range_low": r(range_low), "range_high": r(range_high),
        "atr14": r(_atr(highs, lows, closes)),
    }


def _evidence_text(market: str, symbol: str, sig: dict) -> str:
    parts = [f"{market} {symbol} technical evidence (deterministic, from real OHLC):",
             f"- last: {sig['last']}", f"- 1-bar change %: {sig['change_pct']}",
             f"- SMA20: {sig['sma20']}  SMA50: {sig['sma50']}",
             f"- RSI(14): {sig['rsi14']}", f"- trend classification: {sig['trend']}",
             f"- nearest support: {sig['support']}  nearest resistance: {sig['resistance']}",
             f"- data points: {sig['n_points']}"]
    return "\n".join(parts)


def _fetch_nepse_ohlc(symbol: str) -> tuple[list[dict] | None, str]:
    try:
        from saathi.platform.market_data.tracker.chart import build_chart_model
        m = build_chart_model(symbol, "1Y", include_fundamentals=False, include_dividends=False)
        if not m.get("available"):
            return None, m.get("status") or "TRACKER_UNAVAILABLE"
        return m.get("ohlc") or [], "NEPSE_PORTFOLIO_TRACKER · third-party historical"
    except Exception as e:  # noqa: BLE001
        return None, f"TRACKER_ERROR:{str(e)[:80]}"


def _crypto_pair(symbol: str) -> str:
    """Normalize a ticker to a Binance USDT spot pair (BTC → BTCUSDT, BTC/USDT → BTCUSDT)."""
    s = symbol.upper().replace("/", "").replace("-", "").strip()
    if s.endswith("USDT") or s.endswith("USDC") or s.endswith("BUSD"):
        return s
    if s.endswith("USD"):
        return s[:-3] + "USDT"
    return s + "USDT"


_TF_INTERVAL = {"1m": ("1m", "300"), "5m": ("5m", "300"), "15m": ("15m", "300"),
                "1h": ("1h", "300"), "4h": ("4h", "300"),
                "1d": ("1d", "300"), "1w": ("1w", "120")}


def _fetch_crypto_ohlc(symbol: str, timeframe: str = "1d") -> tuple[list[dict] | None, str]:
    """Binance public market-data mirror (keyless, no account). Interval per timeframe."""
    pair = _crypto_pair(symbol)
    interval, limit = _TF_INTERVAL.get(timeframe, ("1d", "60"))
    try:
        import httpx
        r = httpx.get(
            "https://data-api.binance.vision/api/v3/klines",
            params={"symbol": pair, "interval": interval, "limit": limit}, timeout=20,
        )
        if r.status_code == 400:
            return None, f"UNKNOWN_CRYPTO_PAIR:{pair}"
        r.raise_for_status()
        rows = r.json()  # [[openTime, open, high, low, close, volume, ...], ...]
        ohlc = [{"open": k[1], "high": k[2], "low": k[3], "close": k[4], "volume": k[5]} for k in rows]
        if len(ohlc) < 5:
            return None, "CRYPTO_SERIES_TOO_SHORT"
        return ohlc, f"Binance public market data · {pair} {interval} (third-party)"
    except Exception as e:  # noqa: BLE001
        return None, f"CRYPTO_FEED_UNAVAILABLE:{str(e)[:80]}"


def _run_agent(market: str, symbol: str, sig: dict, smc_text: str = "") -> tuple[str, str]:
    """Return (analysis_text, provider). Agent failure yields a deterministic fallback."""
    try:
        from saathi.chat.api import default_engine, default_store
        st = default_store()
        eng = default_engine()
        conv = st.create_conversation(title=f"TA {market} {symbol}")
        cid = conv.get("id") if isinstance(conv, dict) else getattr(conv, "id", None)
        smc_block = (f"\n\nSmart Money Concepts / ICT structure:\n{smc_text}" if smc_text else "")
        prompt = (_evidence_text(market, symbol, sig) + smc_block +
                  "\n\nWrite the technical read now (research only, not advice).")
        res = eng.send(cid, prompt, system=ANALYST_SYSTEM, agent="")
        text = (res.message or {}).get("content", "") if res else ""
        provider = (res.execution or {}).get("provider", "") if res else ""
        if not text.strip():
            return _fallback_text(sig), provider or "none"
        return text.strip(), provider or "unknown"
    except Exception as e:  # noqa: BLE001
        return _fallback_text(sig), f"agent_error:{type(e).__name__}"


def _fallback_text(sig: dict) -> str:
    """Deterministic readout when no agent is available — never fabricated."""
    return (
        f"Trend: {sig['trend']} (last {sig['last']} vs SMA20 {sig['sma20']}, SMA50 {sig['sma50']}).\n"
        f"Momentum: RSI(14) {sig['rsi14']}"
        + (" — stretched" if (sig['rsi14'] or 0) > 70 else " — weak" if (sig['rsi14'] or 100) < 30 else " — neutral")
        + f".\nKey levels: support {sig['support']}, resistance {sig['resistance']}.\n"
        "Risk: descriptive only; no agent brain was reachable, so this is the raw indicator read.\n"
        f"Watch: a close beyond {sig['resistance']} or {sig['support']}."
    )


# NEPSE index + sub-indices (tracker index_id). "NEPSE" is the whole-market index.
INDEX_IDS = {
    "NEPSE": 58, "SENSITIVE": 57, "FLOAT": 62, "SENSITIVE_FLOAT": 63,
    "BANKING": 51, "HOTELS": 52, "HOTELS_AND_TOURISM": 52, "OTHERS": 53,
    "HYDROPOWER": 54, "HYDRO": 54, "DEVELOPMENT_BANK": 55, "DEVBANK": 55,
    "MANUFACTURING": 56, "NON_LIFE_INSURANCE": 59, "FINANCE": 60, "TRADING": 61,
    "MICROFINANCE": 64, "LIFE_INSURANCE": 65, "MUTUAL_FUND": 66, "INVESTMENT": 67,
}


def _fetch_index_ohlc(symbol: str, range_: str = "1Y") -> tuple[list[dict] | None, str]:
    """NEPSE index / sub-index daily OHLC from the tracker index-history feed."""
    key = (symbol or "NEPSE").upper().replace(" ", "_").replace("&", "AND")
    idx_id = INDEX_IDS.get(key)
    if idx_id is None:
        return None, f"UNKNOWN_INDEX:{symbol} (try NEPSE, SENSITIVE, BANKING, HYDROPOWER…)"
    try:
        import httpx
        r = httpx.get("https://nepseportfoliotracker.app/api/market/indices/history",
                      params={"index_id": idx_id, "range": range_},
                      headers={"user-agent": "SaathiOS NEPSE observer; research-only"}, timeout=25)
        if r.status_code != 200:
            return None, f"INDEX_HTTP_{r.status_code}"
        body = r.json()
        rows = body.get("data") if isinstance(body, dict) else body
        if isinstance(rows, dict):
            rows = rows.get("data") or rows.get("history") or []
        ohlc = [{"open": x.get("open_index"), "high": x.get("high_index"),
                 "low": x.get("low_index"), "close": x.get("closing_index"),
                 "volume": x.get("turnover_volume")} for x in (rows or [])]
        ohlc = [o for o in ohlc if o.get("close") is not None]
        if len(ohlc) < 5:
            return None, "INDEX_SERIES_TOO_SHORT"
        return ohlc, f"NEPSE index feed · {key} (nepseportfoliotracker.app)"
    except Exception as e:  # noqa: BLE001
        return None, f"INDEX_FEED_UNAVAILABLE:{str(e)[:80]}"


def _gather(market: str, symbol: str, timeframe: str = "1d") -> tuple[str, str, list[dict] | None, str]:
    """Return (market, symbol, ohlc, source_or_error). Pure fetch, no compute/agent.
    timeframe applies to crypto (Binance intraday); NEPSE is daily only."""
    market = (market or "").upper()
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return market, symbol, None, "NO_SYMBOL"
    if market == "INDEX":
        ohlc, source = _fetch_index_ohlc(symbol)
    elif market == "NEPSE":
        ohlc, source = _fetch_nepse_ohlc(symbol)
    elif market in ("CRYPTO", "BINANCE"):
        market = "CRYPTO"
        ohlc, source = _fetch_crypto_ohlc(symbol, timeframe)
    else:
        return market, symbol, None, f"UNKNOWN_MARKET:{market}"
    return market, symbol, ohlc, source


def signals_only(market: str, symbol: str, timeframe: str = "1d") -> dict[str, Any]:
    """Deterministic evidence with NO agent call (fast; reused by the paper trader).
    Also returns the recent OHLC window so callers can draw levels/trendlines."""
    market, symbol, ohlc, source = _gather(market, symbol, timeframe)
    if not ohlc:
        return {"available": False, "market": market, "symbol": symbol, "error": source,
                "disclaimer": DISCLAIMER}
    sig = compute_signals(ohlc)
    if sig is None:
        return {"available": False, "market": market, "symbol": symbol,
                "error": "INSUFFICIENT_HISTORY", "source": source, "disclaimer": DISCLAIMER}
    return {"available": True, "market": market, "symbol": symbol, "evidence": sig,
            "source": source, "ohlc": ohlc[-60:], "authority": "OBSERVATION_ONLY",
            "advice": False, "disclaimer": DISCLAIMER}


def current_price(market: str, symbol: str) -> float | None:
    """Latest close for the symbol (used to mark paper trades to market)."""
    _, _, ohlc, _ = _gather(market, symbol)
    if not ohlc:
        return None
    closes = _f([p.get("close") for p in ohlc])
    return closes[-1] if closes else None


STRATEGY_SYSTEM = (
    "You are the SaathiOS ICT/SMC strategy desk. Using ONLY the deterministic indicators and "
    "the Smart Money Concepts structure provided (market structure, BOS/CHoCH, order blocks, "
    "fair value gaps, liquidity, premium/discount, and the potential IDM/inducement), write a "
    "concise, beginner-clear trading PLAYBOOK for this timeframe. Structure it as: "
    "1) Bias (from structure); 2) Structure map (what the swings/BOS/CHoCH say); "
    "3) Inducement (IDM) — the liquidity likely swept first, and why; "
    "4) Entry idea — the order block or FVG to watch, in discount (for longs) or premium (for "
    "shorts); 5) Invalidation — where the idea is wrong (beyond structure/IDM); "
    "6) Target — the opposing liquidity. Briefly define each ICT term. 180-260 words. "
    "This is EDUCATION/RESEARCH, NOT financial advice: never a buy/sell instruction, never "
    "promise outcomes. End with 'Watch:' naming the single trigger to wait for."
)


def strategy(market: str, symbol: str, timeframe: str = "") -> dict[str, Any]:
    """ICT/SMC playbook with structure mapping + inducement. Crypto defaults to 15m; NEPSE daily."""
    market = (market or "").upper()
    tf = timeframe or ("15m" if market in ("CRYPTO", "BINANCE") else "1d")
    base = signals_only(market, symbol, tf)
    if not base.get("available"):
        return {**base, "timeframe": tf}
    sig = base["evidence"]
    smc_obj, smc_text = None, ""
    try:
        from saathi.platform.market_data import smc as _smc
        smc_obj = _smc.detect(base.get("ohlc") or [])
        smc_text = _smc.summarize(smc_obj) if smc_obj else ""
    except Exception:
        pass
    try:
        from saathi.chat.api import default_engine, default_store
        st = default_store()
        eng = default_engine()
        conv = st.create_conversation(title=f"Strategy {market} {symbol} {tf}")
        cid = conv.get("id") if isinstance(conv, dict) else getattr(conv, "id", None)
        prompt = (f"Timeframe: {tf}\n" + _evidence_text(base["market"], base["symbol"], sig) +
                  (f"\n\nSMC/ICT structure:\n{smc_text}" if smc_text else "") +
                  "\n\nWrite the ICT playbook now (research only, not advice).")
        res = eng.send(cid, prompt, system=STRATEGY_SYSTEM, agent="")
        text = (res.message or {}).get("content", "") if res else ""
        provider = (res.execution or {}).get("provider", "") if res else ""
    except Exception as e:  # noqa: BLE001
        text, provider = "", f"agent_error:{type(e).__name__}"
    if not (text or "").strip():
        text = ("Strategy engine needs the analysis brain (local Ollama or a cloud key). "
                "Structure evidence is available below; connect a model for the written playbook.")
    return {**base, "timeframe": tf, "smc": smc_obj, "strategy": text.strip(),
            "provider": provider or "unknown"}


def analyze(market: str, symbol: str) -> dict[str, Any]:
    base = signals_only(market, symbol)
    if not base.get("available"):
        return base
    sig = base["evidence"]
    # Attach ICT/SMC structure so the desk can explain market structure too.
    smc_obj, smc_text = None, ""
    try:
        from saathi.platform.market_data import smc as _smc
        smc_obj = _smc.detect(base.get("ohlc") or [])
        smc_text = _smc.summarize(smc_obj) if smc_obj else ""
    except Exception:
        pass
    analysis, provider = _run_agent(base["market"], base["symbol"], sig, smc_text)
    return {**base, "analysis": analysis, "provider": provider, "smc": smc_obj}
