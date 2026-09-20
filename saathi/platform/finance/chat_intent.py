"""Finance chat brain — lets Ask Saathi answer market questions by routing them to the same
deterministic engines the Command Deck uses (technical analysis, ICT/SMC strategy, trade
setup + volume strength + S/R zones, fundamentals, quote, movers, and simulated paper trades).

Observation/research/simulation-only. It never places a real trade, gives no financial advice,
and answers honestly ("no data") when a source is unavailable. Only market-shaped messages are
handled; everything else falls through to the normal chat model.
"""
from __future__ import annotations

import re
from typing import Any

CRYPTO = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "MATIC",
          "LINK", "LTC", "TRX", "USDT", "USDC", "SHIB", "TON", "NEAR", "APT"}
DISCLAIMER = "Research/observation only — not financial advice, never an execution."

_STOP = {"THE", "A", "AN", "OF", "IS", "IN", "ON", "TO", "FOR", "AND", "OR", "MY", "ME",
         "WHAT", "HOW", "WHY", "DO", "GET", "RUN", "GIVE", "SHOW", "TELL", "PLEASE",
         "ANALYSE", "ANALYZE", "ANALYSIS", "TECHNICAL", "STRATEGY", "PLAN", "TRADE",
         "SETUP", "DESK", "PRICE", "QUOTE", "LTP", "FUNDAMENTAL", "FUNDAMENTALS", "EPS",
         "PE", "PB", "MOVERS", "GAINERS", "LOSERS", "MARKET", "TODAY", "PAPER", "DUMMY",
         "VOLUME", "STRENGTH", "SUPPORT", "RESISTANCE", "IDM", "ICT", "SMC", "NEPSE",
         "CRYPTO", "STOCK", "SHARE", "ABOUT", "LIKE", "NOW", "SAATHI"}


def _symbol(msg: str) -> str | None:
    for tok in re.findall(r"\b([A-Z][A-Z0-9]{1,9})\b", msg.upper()):
        if tok in CRYPTO:
            return tok
        if tok not in _STOP and 2 <= len(tok) <= 10:
            return tok
    return None


def _kw(msg: str, words) -> bool:
    m = msg.lower()
    return any(w in m for w in words)


def _fmt_num(v):
    return "—" if v is None else (f"{v:,.2f}" if isinstance(v, (int, float)) else str(v))


def handle_finance_chat(message: str) -> dict[str, Any] | None:
    """Return {handled, text, kind} for a market question, else None (fall through to the LLM)."""
    if not message or len(message) > 400:
        return None
    msg = message.strip()
    low = msg.lower()

    # market-wide (no symbol needed)
    if _kw(low, ["top gainers", "top losers", "movers", "market today", "how is the market",
                 "gainers", "losers", "nepse today"]):
        return _movers()

    sym = _symbol(msg)
    is_crypto = sym in CRYPTO if sym else False
    has_kw = _kw(low, ["analy", "technical", "strateg", "playbook", "ict", "idm", "setup",
                       "trade desk", "volume strength", "support", "resistance", "zone",
                       "fundamental", "eps", "p/e", "pe ratio", "p/b", "pb", "book value",
                       "market cap", "valuation", "price", "quote", "ltp", "trend", "rsi",
                       "paper trade", "dummy trade", "how is", "what about", "accumulat", "distribut"])
    # Only engage when we have a clear market message: a crypto symbol, or a NEPSE symbol + keyword.
    if not sym or (not is_crypto and not has_kw):
        return None
    market = "CRYPTO" if is_crypto else "NEPSE"

    if _kw(low, ["strateg", "playbook", "ict", "idm"]):
        return _strategy(market, sym)
    if _kw(low, ["fundamental", "eps", "p/e", "pe ratio", "p/b", " pb", "book value", "market cap", "valuation"]):
        return _fundamentals(market, sym)
    if _kw(low, ["paper trade", "dummy trade", "simulate"]):
        return _paper(market, sym)
    if _kw(low, ["setup", "trade desk", "volume strength", "support", "resistance", "zone", "accumulat", "distribut"]):
        return _desk(market, sym)
    if _kw(low, ["price", "quote", "ltp"]) and market == "NEPSE":
        return _quote(sym)
    # default → technical analysis
    return _technical(market, sym)


def _technical(market, sym):
    from saathi.platform.market_data.technical_analysis import analyze
    r = analyze(market, sym)
    if not r.get("available"):
        return {"handled": True, "kind": "technical", "text": f"No data for {sym} ({r.get('error')}). {DISCLAIMER}"}
    e = r["evidence"]
    head = (f"{market} {sym} — {e['trend']} · last {_fmt_num(e['last'])} ({_fmt_num(e['change_pct'])}%) · "
            f"RSI {e['rsi14']} · SMA20 {e['sma20']} / SMA50 {e['sma50']} · S {e['support']} / R {e['resistance']}")
    return {"handled": True, "kind": "technical",
            "text": f"{head}\n\n{r.get('analysis','').strip()}\n\nsource: {r.get('source')} · {DISCLAIMER}"}


def _strategy(market, sym):
    from saathi.platform.market_data.technical_analysis import strategy
    r = strategy(market, sym)
    if not r.get("available"):
        return {"handled": True, "kind": "strategy", "text": f"No data for {sym} ({r.get('error')}). {DISCLAIMER}"}
    idm = (r.get("smc") or {}).get("inducement")
    idm_s = f"\nPotential IDM: {idm['side']} liquidity at {idm['price']} ({idm['bias']})." if idm else ""
    return {"handled": True, "kind": "strategy",
            "text": f"{market} {sym} · ICT playbook ({r.get('timeframe')}):{idm_s}\n\n{r.get('strategy','').strip()}\n\n{DISCLAIMER}"}


def _desk(market, sym):
    from saathi.platform.market_data import trade_desk
    r = trade_desk.desk(market, sym)
    if not r.get("available"):
        return {"handled": True, "kind": "desk", "text": f"No data for {sym} ({r.get('error')}). {DISCLAIMER}"}
    ts = r.get("trade_setup") or {}
    setup = (f"Setup: {ts['side']} entry {ts['entry']} · stop {ts['stop']} · target {ts['target']} · "
             f"R:R 1:{ts['rr']} (−{ts['possible_loss_pct']}% / +{ts['possible_profit_pct']}%)."
             if ts.get("setup") else f"No clean setup ({ts.get('reason')}).")
    vs = r.get("volume_strength") or {}
    per = vs.get("periods") or []
    vstr = " · ".join(f"{p['period']}: {p['buyer']}/{p['seller']}" for p in per if p.get("buyer") is not None)
    zones = r.get("sr_zones") or {}
    zstr = " · ".join(f"{k} {v['low']}-{v['high']}" for k, v in zones.items())
    return {"handled": True, "kind": "desk",
            "text": f"{market} {sym} · trend {r.get('trend')} · last {_fmt_num(r.get('last'))}\n{setup}\n"
                    f"Volume strength (buyer/seller): {vstr or '—'}\nS/R zones: {zstr or '—'}\n\n{DISCLAIMER}"}


def _fundamentals(market, sym):
    if market != "NEPSE":
        return {"handled": True, "kind": "fundamentals", "text": f"Fundamentals are for NEPSE stocks; {sym} looks like crypto."}
    from saathi.platform.market_data import free_sources
    r = free_sources.nepse_fundamentals(sym)
    if not r.get("available"):
        return {"handled": True, "kind": "fundamentals", "text": f"No fundamentals for {sym} ({r.get('error')}). {DISCLAIMER}"}
    return {"handled": True, "kind": "fundamentals",
            "text": f"{sym} fundamentals — EPS {r.get('eps')} · P/E {r.get('pe')} · P/B {r.get('pb')} · "
                    f"book value {r.get('book_value')} · market cap {_fmt_num(r.get('market_cap'))}\nsource: {r.get('source')} · {DISCLAIMER}"}


def _quote(sym):
    from saathi.platform.market_data import free_sources
    r = free_sources.nepse_quote(sym)
    if not r.get("available"):
        return {"handled": True, "kind": "quote", "text": f"No live quote for {sym} ({r.get('error')}). {DISCLAIMER}"}
    q = r["quote"]
    return {"handled": True, "kind": "quote",
            "text": f"{sym} — LTP {q.get('ltp')} ({'+' if (q.get('percent_change') or 0) >= 0 else ''}{q.get('percent_change')}%) · "
                    f"open {q.get('open')} · high {q.get('high')} · low {q.get('low')} · vol {_fmt_num(q.get('volume'))}\n"
                    f"source: {r.get('source')} · {DISCLAIMER}"}


def _movers():
    from saathi.platform.market_data import free_sources
    r = free_sources.movers(5)
    if not r.get("available"):
        return {"handled": True, "kind": "movers", "text": f"Movers unavailable ({r.get('error')}). {DISCLAIMER}"}
    g = ", ".join(f"{x['symbol']} {'+' if (x.get('percent_change') or 0) >= 0 else ''}{x.get('percent_change')}%" for x in r.get("gainers", []))
    l = ", ".join(f"{x['symbol']} {x.get('percent_change')}%" for x in r.get("losers", []))
    return {"handled": True, "kind": "movers",
            "text": f"NEPSE movers (free live):\nTop gainers: {g or '—'}\nTop losers: {l or '—'}\nsource: {r.get('source')} · {DISCLAIMER}"}


def _paper(market, sym):
    from saathi.platform.finance import paper_trading as pt
    r = pt.open_trade(market, sym)
    if not r.get("setup"):
        return {"handled": True, "kind": "paper", "text": f"No clean paper-trade setup for {sym} ({r.get('reason')}). Nothing opened. {DISCLAIMER}"}
    return {"handled": True, "kind": "paper",
            "text": f"Opened a SIMULATED {r['side']} paper trade on {sym}: entry {r['entry']} · stop {r['stop']} · "
                    f"target {r['target']} · R:R 1:{r['planned_r']}. No real order placed. Track it in Trading Guardian. {DISCLAIMER}"}
