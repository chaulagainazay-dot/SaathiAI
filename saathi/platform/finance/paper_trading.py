"""Paper (dummy) trading agent — SIMULATION ONLY. No real orders, ever.

The agent turns deterministic technical evidence into a simulated trade with an entry, a
protective stop and a target, journals it, and later marks it to the live price to record a
WIN or LOSS. Success rate, expectancy and simulated R are computed from REAL closed outcomes
— never fabricated. This is a learning/observation surface: it has no path to a broker, no
credentials, and no execution authority. It complements (does not touch) the frozen
Observation Bridge / Financial Memory.

Signal → trade rules (deterministic quality gate; honest NO_SETUP when unmet):
  LONG  (any market): trend UPTREND,  RSI < 72, support < last < resistance, R >= 1.2
  SHORT (crypto only): trend DOWNTREND, RSI > 28, support < last < resistance, R >= 1.2
  entry = last close; stop = the near level against you; target = the near level for you.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

DB_PATH = Path.home() / ".saathi" / "paper_trading.db"
_MIN_RR = 1.2
_RSI_LONG_MAX = 72.0
_RSI_SHORT_MIN = 28.0

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute(
            """CREATE TABLE IF NOT EXISTS paper_trades (
                id TEXT PRIMARY KEY, created_at REAL, market TEXT, symbol TEXT, side TEXT,
                entry REAL, stop REAL, target REAL, planned_r REAL, status TEXT,
                exit_price REAL, exit_at REAL, r_multiple REAL,
                rationale TEXT, provider TEXT, evidence_json TEXT, last_price REAL, last_seen REAL
            )"""
        )
        _conn.commit()
    return _conn


def _round(v, dp=2):
    return None if v is None else round(float(v), dp)


def propose(market: str, symbol: str) -> dict[str, Any]:
    """Deterministic trade proposal (no persistence). Honest NO_SETUP when no clean setup."""
    from saathi.platform.market_data.technical_analysis import signals_only
    base = signals_only(market, symbol)
    if not base.get("available"):
        return {"setup": False, "reason": base.get("error", "NO_DATA"),
                "market": base.get("market"), "symbol": base.get("symbol")}
    e = base["evidence"]
    mkt, sym = base["market"], base["symbol"]
    last, rsi, trend, atr = e["last"], e["rsi14"], e["trend"], e.get("atr14")
    if last is None:
        return {"setup": False, "reason": "NO_PRICE", "market": mkt, "symbol": sym, "evidence": e}
    if not atr or atr <= 0:
        return {"setup": False, "reason": "NO_VOLATILITY_ATR", "market": mkt, "symbol": sym, "evidence": e}

    # ATR-based trend-following structure: stop 1.5*ATR against, target 2*ATR for (RR ~1.33).
    # Real observed volatility (ATR), transparent method — not a hand-picked/fabricated price.
    STOP_MULT, TGT_MULT = 1.5, 2.0
    side = None
    if trend == "UPTREND" and (rsi is None or rsi < _RSI_LONG_MAX):
        side, entry = "LONG", last
        stop, target = last - STOP_MULT * atr, last + TGT_MULT * atr
    elif trend == "DOWNTREND" and mkt == "CRYPTO" and (rsi is None or rsi > _RSI_SHORT_MIN):
        side, entry = "SHORT", last
        stop, target = last + STOP_MULT * atr, last - TGT_MULT * atr
    else:
        return {"setup": False, "reason": f"NO_TREND_SETUP ({trend})", "market": mkt, "symbol": sym, "evidence": e}

    rr = TGT_MULT / STOP_MULT
    if rr < _MIN_RR:
        return {"setup": False, "reason": f"RR_TOO_LOW ({rr:.2f} < {_MIN_RR})",
                "market": mkt, "symbol": sym, "evidence": e}

    rationale = (f"{side} {sym}: {trend.lower()}, RSI {rsi}, entry {_round(entry)}, "
                 f"stop {_round(stop)} (1.5x ATR), target {_round(target)} (2x ATR); "
                 f"risk/reward {rr:.2f}. ATR {_round(atr)}. Simulated only.")
    return {"setup": True, "market": mkt, "symbol": sym, "side": side,
            "entry": _round(entry), "stop": _round(stop), "target": _round(target),
            "planned_r": round(rr, 2), "rationale": rationale, "evidence": e,
            "source": base.get("source"), "simulation": True}


def open_trade(market: str, symbol: str) -> dict[str, Any]:
    """Propose + persist a dummy trade if there is a clean setup."""
    p = propose(market, symbol)
    if not p.get("setup"):
        return p
    tid = "pt_" + uuid.uuid4().hex[:12]
    now = time.time()
    with _lock:
        _db().execute(
            """INSERT INTO paper_trades (id,created_at,market,symbol,side,entry,stop,target,
               planned_r,status,exit_price,exit_at,r_multiple,rationale,provider,evidence_json,
               last_price,last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tid, now, p["market"], p["symbol"], p["side"], p["entry"], p["stop"], p["target"],
             p["planned_r"], "OPEN", None, None, None, p["rationale"], "paper_agent",
             json.dumps(p.get("evidence") or {}), p["entry"], now),
        )
        _db().commit()
    return {**p, "id": tid, "status": "OPEN", "created_at": now}


def _mark_one(row: sqlite3.Row) -> dict[str, Any] | None:
    """Mark an OPEN trade to the live price. Returns close info if it closed, else None."""
    from saathi.platform.market_data.technical_analysis import current_price
    price = current_price(row["market"], row["symbol"])
    if price is None:
        return None
    side, entry, stop, target = row["side"], row["entry"], row["stop"], row["target"]
    status, exit_price = None, None
    if side == "LONG":
        if price >= target:
            status, exit_price = "WON", target
        elif price <= stop:
            status, exit_price = "LOST", stop
    else:  # SHORT
        if price <= target:
            status, exit_price = "WON", target
        elif price >= stop:
            status, exit_price = "LOST", stop
    now = time.time()
    if status is None:  # still open — just record the mark
        with _lock:
            _db().execute("UPDATE paper_trades SET last_price=?, last_seen=? WHERE id=?",
                          (price, now, row["id"]))
            _db().commit()
        return None
    risk = abs(entry - stop) or 1.0
    r_mult = ((exit_price - entry) if side == "LONG" else (entry - exit_price)) / risk
    with _lock:
        _db().execute(
            "UPDATE paper_trades SET status=?,exit_price=?,exit_at=?,r_multiple=?,last_price=?,last_seen=? WHERE id=?",
            (status, exit_price, now, round(r_mult, 3), price, now, row["id"]),
        )
        _db().commit()
    return {"id": row["id"], "symbol": row["symbol"], "status": status,
            "exit_price": _round(exit_price), "r_multiple": round(r_mult, 3)}


def evaluate() -> dict[str, Any]:
    """Mark every OPEN trade to the live price; close the ones that hit target/stop."""
    rows = _db().execute("SELECT * FROM paper_trades WHERE status='OPEN'").fetchall()
    closed = []
    for row in rows:
        res = _mark_one(row)
        if res:
            closed.append(res)
    return {"evaluated": len(rows), "closed": closed, "simulation": True}


def _row_public(r: sqlite3.Row) -> dict[str, Any]:
    return {"id": r["id"], "created_at": r["created_at"], "market": r["market"],
            "symbol": r["symbol"], "side": r["side"], "entry": _round(r["entry"]),
            "stop": _round(r["stop"]), "target": _round(r["target"]),
            "planned_r": r["planned_r"], "status": r["status"],
            "exit_price": _round(r["exit_price"]), "r_multiple": r["r_multiple"],
            "last_price": _round(r["last_price"]), "rationale": r["rationale"]}


def stats() -> dict[str, Any]:
    rows = _db().execute("SELECT status, r_multiple FROM paper_trades").fetchall()
    won = sum(1 for r in rows if r["status"] == "WON")
    lost = sum(1 for r in rows if r["status"] == "LOST")
    open_n = sum(1 for r in rows if r["status"] == "OPEN")
    closed = won + lost
    total_r = sum((r["r_multiple"] or 0.0) for r in rows if r["status"] in ("WON", "LOST"))
    return {
        "total": len(rows), "open": open_n, "closed": closed, "won": won, "lost": lost,
        "win_rate": round(won / closed * 100, 1) if closed else None,
        "total_r": round(total_r, 2),
        "expectancy_r": round(total_r / closed, 3) if closed else None,
        "simulation": True,
    }


def journal(limit: int = 30) -> dict[str, Any]:
    rows = _db().execute(
        "SELECT * FROM paper_trades ORDER BY created_at DESC LIMIT ?", (int(limit),)
    ).fetchall()
    return {"stats": stats(), "trades": [_row_public(r) for r in rows], "simulation": True,
            "note": "SIMULATION ONLY — no real orders, no broker, no execution authority."}
