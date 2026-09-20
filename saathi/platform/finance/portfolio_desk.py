"""Portfolio desk — add / track / analyse / recommend / research the owner's holdings.

A simple, owner-owned holdings book (SQLite) valued live from the free market source, with
deterministic analysis (value, P/L, weights, concentration), a NAV history for drawdown, and
recommendations that reuse the Trade Desk setup engine + an equal-weight rebalance read. This
is the portfolio layer over the fund engines (fund_ledger / portfolio_construction /
portfolio_risk_engine); observation-only — it never places orders or gives advice.
"""
from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

DB_PATH = Path.home() / ".saathi" / "portfolio.db"
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("""CREATE TABLE IF NOT EXISTS holdings (
            id TEXT PRIMARY KEY, symbol TEXT, market TEXT, qty REAL, avg_cost REAL, added_at REAL)""")
        _conn.execute("""CREATE TABLE IF NOT EXISTS nav_history (ts REAL, nav REAL)""")
        _conn.commit()
    return _conn


def _r(v, dp=2):
    return None if v is None else round(float(v), dp)


def _price(market: str, symbol: str):
    """Live price + day % for a holding, from the free source (NEPSE) or Binance (crypto)."""
    if market == "CRYPTO":
        from saathi.platform.market_data.technical_analysis import current_price
        return current_price("CRYPTO", symbol), None
    from saathi.platform.market_data import free_sources
    q = free_sources.nepse_quote(symbol)
    if q.get("available"):
        return q["quote"].get("ltp"), q["quote"].get("percent_change")
    return None, None


def add_holding(symbol: str, market: str, qty: float, avg_cost: float) -> dict:
    symbol = (symbol or "").strip().upper()
    market = (market or "NEPSE").strip().upper()
    if not symbol or qty is None:
        return {"ok": False, "error": "SYMBOL_AND_QTY_REQUIRED"}
    hid = "h_" + uuid.uuid4().hex[:10]
    with _lock:
        _db().execute("INSERT INTO holdings (id,symbol,market,qty,avg_cost,added_at) VALUES (?,?,?,?,?,?)",
                      (hid, symbol, market, float(qty), float(avg_cost or 0), time.time()))
        _db().commit()
    return {"ok": True, "id": hid}


def remove_holding(hid: str) -> dict:
    with _lock:
        _db().execute("DELETE FROM holdings WHERE id=?", (str(hid),))
        _db().commit()
    return {"ok": True}


def list_holdings() -> list[dict]:
    rows = _db().execute("SELECT * FROM holdings ORDER BY added_at").fetchall()
    return [dict(r) for r in rows]


def _record_nav(nav: float):
    with _lock:
        _db().execute("INSERT INTO nav_history (ts,nav) VALUES (?,?)", (time.time(), nav))
        # keep last 500 points
        _db().execute("DELETE FROM nav_history WHERE ts NOT IN (SELECT ts FROM nav_history ORDER BY ts DESC LIMIT 500)")
        _db().commit()


def _engine_risk(positions: list[dict], total_val: float, nav_rows: list) -> dict:
    """Real risk view via portfolio_risk_engine (concentration/exposure + drawdown)."""
    from decimal import Decimal
    try:
        from saathi.platform.portfolio_risk_engine.metrics import portfolio_metrics
        from saathi.platform.portfolio_risk_engine.drawdown import compute_drawdown
        state = {
            "nav": str(total_val), "cash": "0", "positions_value": str(total_val),
            "positions": [{"symbol": p["symbol"], "security_id": p["symbol"],
                           "market_value": str(p["value"] or 0), "quantity": str(p["qty"] or 0),
                           "weight": str((p["weight"] or 0) / 100)} for p in positions if p.get("value")],
        }
        m = portfolio_metrics(state)
        dd = compute_drawdown([(r["ts"], Decimal(str(r["nav"]))) for r in nav_rows]) if len(nav_rows) >= 2 else {}
        def f(v):
            try:
                return round(float(v), 2)
            except (TypeError, ValueError):
                return None
        return {
            "largest_position_pct": f(_pctval(m.get("largest_position_pct"))),
            "top3_pct": f(_pctval(m.get("top3_concentration_pct") or m.get("top3_pct"))),
            "top5_pct": f(_pctval(m.get("top5_concentration_pct") or m.get("top5_pct"))),
            "gross_exposure_pct": f(_pctval(m.get("gross_exposure_pct"))),
            "position_count": m.get("position_count"),
            "current_drawdown_pct": f(_pctval(dd.get("current_drawdown"))) if dd else None,
            "max_drawdown_pct": f(_pctval(dd.get("max_drawdown"))) if dd else None,
            "peak_nav": f(dd.get("peak_nav")) if dd else None,
            "engine": "portfolio_risk_engine",
        }
    except Exception as e:  # noqa: BLE001
        return {"engine_error": str(e)[:120]}


def _pctval(v):
    """Risk engine returns weights as fractions (0..1); render as %."""
    try:
        f = float(v)
        return f * 100 if abs(f) <= 1.5 else f
    except (TypeError, ValueError):
        return None


def _engine_rebalance(positions: list[dict], total_val: float, method: str = "equal_weight") -> dict:
    """Real rebalance proposal via portfolio_construction (target weights + BUY/SELL/HOLD trades)."""
    from decimal import Decimal
    import time as _t
    try:
        from saathi.platform.portfolio_construction.models import UniverseMember, UniverseStatus, MarkQuote
        from saathi.platform.portfolio_construction.construct import equal_weight_targets, signal_proportional_targets
        from saathi.platform.portfolio_construction.rebalance import build_trades
        invest = [p for p in positions if p.get("value") and p.get("price")]
        if not invest or total_val <= 0:
            return {"available": False, "reason": "NO_PRICED_HOLDINGS"}
        nav = Decimal(str(total_val))
        universe = [UniverseMember(security_id=p["symbol"], symbol=p["symbol"], status=UniverseStatus.ELIGIBLE) for p in invest]
        targets, cash_w, warns = equal_weight_targets(universe, nav=nav)
        now = _t.time()
        current = {p["symbol"]: {"security_id": p["symbol"], "symbol": p["symbol"],
                                 "quantity": Decimal(str(p["qty"] or 0)),
                                 "market_value": Decimal(str(p["value"])),
                                 "weight": Decimal(str((p["weight"] or 0) / 100))} for p in invest}
        marks = {p["symbol"]: MarkQuote(security_id=p["symbol"], symbol=p["symbol"],
                                        price=Decimal(str(p["price"])), source="free", timestamp=now) for p in invest}
        trades, tw, te = build_trades(current=current, targets=targets, cash_weight=cash_w, nav=nav, marks=marks)
        def f(v, dp=2):
            try:
                return round(float(v), dp)
            except (TypeError, ValueError):
                return None
        out = []
        for t in trades:
            out.append({"symbol": t.symbol, "action": t.action.value,
                        "current_weight": f(float(t.current_weight) * 100),
                        "target_weight": f(float(t.target_weight) * 100),
                        "weight_delta": f(float(t.weight_delta) * 100),
                        "notional_delta": f(t.notional_delta), "qty": f(t.estimated_quantity, 4)})
        out.sort(key=lambda x: abs(x.get("weight_delta") or 0), reverse=True)
        return {"available": True, "method": method, "cash_weight_pct": f(float(cash_w) * 100),
                "trades": out, "warnings": list(warns) + list(tw), "engine": "portfolio_construction"}
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"ENGINE_ERROR:{str(e)[:120]}"}


def analysis() -> dict[str, Any]:
    holdings = list_holdings()
    if not holdings:
        return {"available": True, "empty": True, "positions": [], "totals": {},
                "recommendations": [], "note": "No holdings yet. Add positions to track and analyse."}
    positions = []
    total_val = 0.0
    total_cost = 0.0
    for h in holdings:
        try:
            price, day = _price(h["market"], h["symbol"])
        except Exception:
            price, day = None, None
        qty, avg = h["qty"], h["avg_cost"]
        val = (price * qty) if price is not None else None
        cost = (avg * qty) if avg else None
        pl = (val - cost) if (val is not None and cost) else None
        plpct = (pl / cost * 100) if (pl is not None and cost) else None
        if val:
            total_val += val
        if cost:
            total_cost += cost
        positions.append({"id": h["id"], "symbol": h["symbol"], "market": h["market"],
                          "qty": qty, "avg_cost": _r(avg), "price": _r(price), "day_pct": day,
                          "value": _r(val), "cost": _r(cost), "pl": _r(pl), "pl_pct": _r(plpct)})
    for p in positions:
        p["weight"] = _r(p["value"] / total_val * 100) if (p["value"] and total_val) else None
    total_pl = total_val - total_cost if total_cost else None
    largest = max(positions, key=lambda p: p.get("weight") or 0, default=None)
    if total_val:
        _record_nav(total_val)
    nav_rows = [dict(r) for r in _db().execute("SELECT ts, nav FROM nav_history ORDER BY ts").fetchall()]

    risk = _engine_risk(positions, total_val, nav_rows)
    rebalance = _engine_rebalance(positions, total_val)
    totals = {
        "value": _r(total_val), "cost": _r(total_cost), "pl": _r(total_pl),
        "pl_pct": _r(total_pl / total_cost * 100) if total_cost else None,
        "positions": len(positions),
        "concentration": largest.get("weight") if largest else None,
        "top_name": largest.get("symbol") if largest else None,
        "max_drawdown_pct": risk.get("max_drawdown_pct"), "nav_points": len(nav_rows),
    }
    return {"available": True, "empty": False, "positions": positions, "totals": totals,
            "risk": risk, "rebalance": rebalance,
            "recommendations": _recommend(positions, total_val),
            "note": "Live valuation (free source) · risk + rebalance from the fund engines · observation-only, not advice."}


def _recommend(positions: list[dict], total_val: float) -> list[dict]:
    recs = []
    n = len([p for p in positions if p.get("value")]) or 1
    equal_w = 100.0 / n
    for p in positions:
        w = p.get("weight")
        # concentration
        if w is not None and w > 30:
            recs.append({"symbol": p["symbol"], "tag": "REVIEW · concentration",
                         "text": f"{p['symbol']} is {w:.0f}% of the book (equal-weight would be {equal_w:.0f}%) — a trim would rebalance risk."})
        # rebalance drift
        elif w is not None and w > equal_w * 1.6:
            recs.append({"symbol": p["symbol"], "tag": "OVERWEIGHT",
                         "text": f"{p['symbol']} at {w:.0f}% vs equal-weight {equal_w:.0f}% — overweight."})
        # loss review
        if p.get("pl_pct") is not None and p["pl_pct"] <= -10:
            recs.append({"symbol": p["symbol"], "tag": "RISK · drawdown",
                         "text": f"{p['symbol']} is {p['pl_pct']:.1f}% below cost — review your stop/thesis."})
        # technical setup (reuse trade desk)
        try:
            from saathi.platform.finance import paper_trading as pt
            prop = pt.propose(p["market"], p["symbol"])
            if prop.get("setup"):
                recs.append({"symbol": p["symbol"], "tag": f"OBSERVATION · {prop['side']} setup",
                             "text": f"{p['symbol']} shows a {prop['side']} trend setup (entry {prop['entry']}, stop {prop['stop']}, target {prop['target']}, R:R 1:{prop['planned_r']}). Research only."})
        except Exception:
            pass
    if not recs:
        recs.append({"symbol": "Portfolio", "tag": "BALANCED",
                     "text": "No concentration, drawdown or trend flags right now. Keep tracking."})
    return recs[:10]
