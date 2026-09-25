"""AI hedge-fund committee — role agents that each read REAL data, "meet" (post findings to a
shared transcript), and hand off to a CEO agent that issues a decision (SWING_TRADE / LONG_HOLD
/ ADD / TRIM / AVOID / WATCH).

Agents (deterministic, real data — free market source, tracker OHLC, SMC/ICT, trade desk,
fundamentals, research news, the owner's portfolio book):
  Research · News · Technical · Volume · Structure(ICT) · Setup · Portfolio · Risk
CEO synthesizes the meeting (LLM narrative when a brain is available) + a deterministic verdict.

Observation/research/simulation-only. No orders, no advice — the verdict is a research call the
owner acts on themselves. Transcript persisted so the owner can watch the discussion.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

DB_PATH = Path.home() / ".saathi" / "fund_committee.db"
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, symbol TEXT, market TEXT, created_at REAL,
            decision TEXT, horizon TEXT, reason TEXT)""")
        _conn.execute("""CREATE TABLE IF NOT EXISTS messages (
            session_id TEXT, seq INTEGER, agent TEXT, role TEXT, text TEXT, ts REAL)""")
        _conn.commit()
    return _conn


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _gather(market: str, symbol: str) -> dict:
    """Pull all real evidence once."""
    from saathi.platform.market_data.technical_analysis import signals_only
    from saathi.platform.market_data import smc as smcmod, trade_desk
    from saathi.platform.finance import paper_trading as pt
    ev = {}
    base = signals_only(market, symbol)
    ev["base"] = base
    if base.get("available"):
        ohlc = base.get("ohlc") or []
        ev["smc"] = smcmod.detect(ohlc)
        ev["volume"] = trade_desk.volume_strength(market, symbol, ohlc)
        ev["sr"] = trade_desk.sr_zones(ohlc, base["evidence"].get("last"))
    ev["setup"] = pt.propose(market, symbol)
    if market == "NEPSE":
        try:
            from saathi.platform.market_data import free_sources
            ev["fund"] = free_sources.nepse_fundamentals(symbol)
        except Exception:
            ev["fund"] = {}
    try:
        from saathi import research_surface
        ev["news"] = (research_surface.events(limit=80) or {}).get("events", [])
    except Exception:
        ev["news"] = []
    try:
        from saathi.platform.finance import portfolio_desk as pd
        ev["holdings"] = pd.list_holdings()
    except Exception:
        ev["holdings"] = []
    return ev


def _agents(symbol: str, market: str, ev: dict) -> list[dict]:
    msgs = []
    base = ev.get("base") or {}
    e = base.get("evidence") or {}
    avail = base.get("available")

    def add(agent, role, text):
        msgs.append({"agent": agent, "role": role, "text": text})

    if not avail:
        add("Data Desk", "data", f"No usable market data for {symbol} ({base.get('error')}). Meeting cannot proceed on evidence.")
        return msgs

    add("Technical Analyst", "technical",
        f"{symbol} is in a {e.get('trend')} on the {base.get('source','')[:24]} series. Last {e.get('last')} "
        f"({e.get('change_pct')}%), RSI {e.get('rsi14')}, MA20 {e.get('sma20')} vs MA50 {e.get('sma50')}. "
        f"Support {e.get('support')}, resistance {e.get('resistance')}.")

    smc = ev.get("smc") or {}
    if smc:
        idm = smc.get("inducement")
        add("Structure (ICT/SMC)", "structure",
            f"Market structure {smc.get('trend')}"
            + (f"; latest {smc['structure_break']['type']} {smc['structure_break']['dir']}." if smc.get("structure_break") else ".")
            + (f" {len(smc.get('fair_value_gaps') or [])} unfilled FVG, {len(smc.get('order_blocks') or [])} order blocks." )
            + (f" Potential IDM: {idm['side']} liquidity {idm['price']} before the {idm['bias']} move." if idm else ""))

    vs = ev.get("volume") or {}
    per = vs.get("periods") or []
    if per:
        vstr = ", ".join(f"{p['period']} {p['buyer']}/{p['seller']}" for p in per if p.get("buyer") is not None)
        add("Volume Desk", "volume", f"Buyer/seller strength — {vstr}. ({vs.get('method')})")

    fund = ev.get("fund") or {}
    if market == "NEPSE":
        if fund.get("available"):
            add("Research Analyst", "research",
                f"Fundamentals — EPS {fund.get('eps')}, P/E {fund.get('pe')}, P/B {fund.get('pb')}, "
                f"book value {fund.get('book_value')}. Valuation looks "
                + ("cheap" if _num(fund.get('pe')) and _num(fund.get('pe')) < 15 else "rich" if _num(fund.get('pe')) and _num(fund.get('pe')) > 30 else "fair") + ".")
        else:
            add("Research Analyst", "research", f"No fundamentals available for {symbol}.")
    else:
        add("Research Analyst", "research", f"{symbol} is crypto — driven by flow/structure, not earnings; leaning on technical + volume + structure.")

    news = ev.get("news") or []
    _CAT = re.compile(r"dividend|lock[- ]?in|promoter|bonus|right\s*share|book\s*close|agm|auction|delist", re.I)
    sym_news = [n for n in news if str(n.get("symbol") or "").upper() == symbol]
    if sym_news:
        catalysts = [n for n in sym_news if _CAT.search((n.get("headline") or "") + " " + str(n.get("event_type") or ""))]
        picked = (catalysts or sym_news)[:4]
        head = f"{symbol} news/catalysts: " + " | ".join((n.get("headline") or n.get("title") or "")[:80] for n in picked)
        if any(re.search(r"lock[- ]?in|promoter", (n.get("headline") or "") + str(n.get("event_type") or ""), re.I) for n in sym_news):
            head += "  ⚠ promoter lock-in/unlock event present — watch for supply."
        add("News Desk", "news", head)
    else:
        mkt_cat = [n for n in news if _CAT.search((n.get("headline") or "") + " " + str(n.get("event_type") or ""))][:3]
        if mkt_cat:
            add("News Desk", "news", f"No {symbol}-specific filings; market catalysts: " + " | ".join((n.get("headline") or "")[:70] for n in mkt_cat))
        else:
            add("News Desk", "news", f"No notable dividend/promoter/bonus/rights filings for {symbol} right now.")

    setup = ev.get("setup") or {}
    if setup.get("setup"):
        add("Setup Desk", "setup",
            f"Clean {setup['side']} setup: entry {setup['entry']}, stop {setup['stop']}, target {setup['target']}, "
            f"R:R 1:{setup['planned_r']}.")
    else:
        add("Setup Desk", "setup", f"No clean trade setup right now ({setup.get('reason')}).")

    holds = ev.get("holdings") or []
    held = next((h for h in holds if h["symbol"] == symbol), None)
    if held:
        add("Portfolio Manager", "portfolio", f"We already hold {symbol} ({held['qty']} @ {held['avg_cost']}). Any add must respect concentration limits.")
    else:
        add("Portfolio Manager", "portfolio", f"{symbol} is not in the book — a new position would add diversification.")

    # Risk
    atr = e.get("atr14")
    add("Risk Officer", "risk",
        f"Volatility ATR {atr}. " + ("Setup risk is defined by the stop; size to 1R." if setup.get("setup") else "No defined-risk entry; stand aside until structure gives one.")
        + (" RSI is stretched — chase risk." if _num(e.get("rsi14")) and _num(e.get("rsi14")) > 72 else ""))
    return msgs


def _decide(symbol: str, market: str, ev: dict) -> dict:
    base = ev.get("base") or {}
    e = base.get("evidence") or {}
    setup = ev.get("setup") or {}
    vs = ev.get("volume") or {}
    fund = ev.get("fund") or {}
    per = vs.get("periods") or []
    buyer_led = bool(per and (per[0].get("buyer") or 0) >= 50)
    trend = e.get("trend")
    rsi = _num(e.get("rsi14"))
    pe = _num(fund.get("pe"))

    if not base.get("available"):
        return {"decision": "NO_DATA", "horizon": "—", "reason": "No usable market data."}
    if trend == "UPTREND" and setup.get("setup") and setup.get("side") == "LONG" and (rsi is None or rsi < 72):
        cheap = pe is not None and pe < 20
        if cheap and buyer_led:
            return {"decision": "LONG_HOLD", "horizon": "weeks–months",
                    "reason": f"Uptrend, buyer-led volume, and reasonable valuation (P/E {pe}). Accumulate on strength; stop {setup['stop']}, first target {setup['target']}."}
        return {"decision": "SWING_TRADE", "horizon": "1–4 weeks",
                "reason": f"Uptrend with a clean long setup and {'buyer-led' if buyer_led else 'mixed'} volume. Entry {setup['entry']}, stop {setup['stop']}, target {setup['target']} (R:R 1:{setup['planned_r']})."}
    if trend == "DOWNTREND":
        return {"decision": "AVOID", "horizon": "—",
                "reason": "Downtrend — no long edge. Wait for a change of character before engaging."}
    if not setup.get("setup"):
        return {"decision": "WATCH", "horizon": "—",
                "reason": f"No clean setup ({setup.get('reason')}). Monitor {e.get('support')}/{e.get('resistance')} for a break."}
    return {"decision": "WATCH", "horizon": "—",
            "reason": "Mixed signals — sit on hands until trend, structure and volume align."}


def _ceo_narrative(symbol: str, market: str, msgs: list[dict], decision: dict) -> str:
    findings = "\n".join(f"- {m['agent']}: {m['text']}" for m in msgs)
    system = ("You are the CEO of a small research fund. Given your analysts' findings and the desk's "
              "deterministic verdict, write a 3-4 sentence decision memo: what the team concluded and why, "
              "and the plan for the verdict. Research/education only — never financial advice, never an order.")
    prompt = (f"Symbol: {market} {symbol}\nAnalyst findings:\n{findings}\n\n"
              f"Desk verdict: {decision['decision']} ({decision['horizon']}) — {decision['reason']}\n\nWrite the CEO memo.")
    try:
        from saathi.chat.api import default_engine, default_store
        st = default_store(); eng = default_engine()
        conv = st.create_conversation(title=f"Committee {symbol}")
        cid = conv.get("id") if isinstance(conv, dict) else getattr(conv, "id", None)
        res = eng.send(cid, prompt, system=system, agent="")
        txt = (res.message or {}).get("content", "") if res else ""
        if txt.strip():
            return txt.strip()
    except Exception:
        pass
    return decision["reason"]


def run_meeting(market: str, symbol: str) -> dict:
    market = (market or "NEPSE").upper()
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return {"ok": False, "error": "NO_SYMBOL"}
    ev = _gather(market, symbol)
    msgs = _agents(symbol, market, ev)
    decision = _decide(symbol, market, ev)
    ceo = _ceo_narrative(symbol, market, msgs, decision)
    msgs.append({"agent": "CEO", "role": "ceo",
                 "text": f"DECISION: {decision['decision']} ({decision['horizon']}).\n{ceo}"})
    sid = "fc_" + uuid.uuid4().hex[:10]
    now = time.time()
    with _lock:
        _db().execute("INSERT INTO sessions (id,symbol,market,created_at,decision,horizon,reason) VALUES (?,?,?,?,?,?,?)",
                      (sid, symbol, market, now, decision["decision"], decision["horizon"], decision["reason"]))
        for i, m in enumerate(msgs):
            _db().execute("INSERT INTO messages (session_id,seq,agent,role,text,ts) VALUES (?,?,?,?,?,?)",
                          (sid, i, m["agent"], m["role"], m["text"], now + i * 0.4))
        _db().commit()
    return {"ok": True, "session_id": sid, "symbol": symbol, "market": market,
            "decision": decision, "messages": msgs,
            "disclaimer": "Research/observation only — a research verdict, not financial advice or an order."}


def list_meetings(limit: int = 20) -> dict:
    rows = _db().execute("SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (int(limit),)).fetchall()
    return {"meetings": [dict(r) for r in rows]}


def get_meeting(sid: str) -> dict:
    s = _db().execute("SELECT * FROM sessions WHERE id=?", (str(sid),)).fetchone()
    if not s:
        return {"ok": False, "error": "NOT_FOUND"}
    msgs = _db().execute("SELECT agent,role,text,ts FROM messages WHERE session_id=? ORDER BY seq", (str(sid),)).fetchall()
    return {"ok": True, "session": dict(s), "messages": [dict(m) for m in msgs]}
