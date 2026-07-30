"""Virtual exchange — sessions, ticks, and order-book levels (simulated)."""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.paper_simulation.models import AUTHORITY_VALUES, SessionState
from saathi.platform.tg.paper_simulation.storage import PaperSimStore, _uid


# Deterministic default symbols for offline simulation
DEFAULT_SYMBOLS = {
    "SPY": {"bid": 450.0, "ask": 450.05, "last": 450.02, "volume": 5_000_000},
    "AAPL": {"bid": 190.0, "ask": 190.08, "last": 190.04, "volume": 2_000_000},
    "MSFT": {"bid": 420.0, "ask": 420.10, "last": 420.05, "volume": 1_500_000},
    "BTCUSDT": {"bid": 65000.0, "ask": 65010.0, "last": 65005.0, "volume": 800.0},
}


class VirtualExchange:
    def __init__(self, store: PaperSimStore):
        self.store = store
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        now = time.time()
        for sym, q in DEFAULT_SYMBOLS.items():
            sess = self.store.fetchone("SELECT symbol FROM ps_sessions WHERE symbol=?", (sym,))
            if not sess:
                self.store.execute(
                    "INSERT INTO ps_sessions(symbol, state, open_ts, close_ts, updated_at) VALUES(?,?,?,?,?)",
                    (sym, SessionState.OPEN.value, now, None, now),
                )
            tick = self.store.fetchone(
                "SELECT id FROM ps_ticks WHERE symbol=? ORDER BY created_at DESC LIMIT 1", (sym,)
            )
            if not tick:
                self.publish_tick(sym, q["bid"], q["ask"], q["last"], q["volume"])
            # seed book levels
            levels = self.store.fetchall("SELECT id FROM ps_book_levels WHERE symbol=? LIMIT 1", (sym,))
            if not levels:
                self._seed_book(sym, q["bid"], q["ask"])

    def _seed_book(self, symbol: str, bid: float, ask: float) -> None:
        now = time.time()
        for i in range(5):
            self.store.execute(
                "INSERT INTO ps_book_levels(id, symbol, side, price, size, updated_at) VALUES(?,?,?,?,?,?)",
                (_uid("lvl"), symbol, "BID", round(bid - i * 0.05, 4), 1000.0 * (5 - i), now),
            )
            self.store.execute(
                "INSERT INTO ps_book_levels(id, symbol, side, price, size, updated_at) VALUES(?,?,?,?,?,?)",
                (_uid("lvl"), symbol, "ASK", round(ask + i * 0.05, 4), 1000.0 * (5 - i), now),
            )

    def set_session(self, symbol: str, state: str) -> dict[str, Any]:
        now = time.time()
        open_ts = now if state == SessionState.OPEN.value else None
        close_ts = now if state == SessionState.CLOSED.value else None
        existing = self.store.fetchone("SELECT symbol FROM ps_sessions WHERE symbol=?", (symbol,))
        if existing:
            self.store.execute(
                "UPDATE ps_sessions SET state=?, open_ts=COALESCE(?, open_ts), close_ts=?, updated_at=? WHERE symbol=?",
                (state, open_ts, close_ts, now, symbol),
            )
        else:
            self.store.execute(
                "INSERT INTO ps_sessions(symbol, state, open_ts, close_ts, updated_at) VALUES(?,?,?,?,?)",
                (symbol, state, open_ts, close_ts, now),
            )
        self.store.audit("session.set", subject=symbol, detail={"state": state})
        return {"ok": True, "symbol": symbol, "state": state, **AUTHORITY_VALUES}

    def get_session(self, symbol: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM ps_sessions WHERE symbol=?", (symbol.upper(),))
        if not row:
            return {"ok": False, "code": "SESSION_NOT_FOUND", "symbol": symbol, **AUTHORITY_VALUES}
        return {"ok": True, **row, **AUTHORITY_VALUES}

    def publish_tick(
        self,
        symbol: str,
        bid: float,
        ask: float,
        last: float,
        volume: float = 1_000_000.0,
        *,
        session_state: str | None = None,
    ) -> dict[str, Any]:
        symbol = symbol.upper()
        sess = self.get_session(symbol)
        state = session_state or (sess.get("state") if sess.get("ok") else SessionState.OPEN.value)
        tid = _uid("tick")
        self.store.execute(
            "INSERT INTO ps_ticks(id, symbol, bid, ask, last, volume, session_state, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (tid, symbol, float(bid), float(ask), float(last), float(volume), state, time.time()),
        )
        return {
            "ok": True,
            "tick_id": tid,
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "last": last,
            "volume": volume,
            "session_state": state,
            "simulated": True,
            **AUTHORITY_VALUES,
        }

    def latest_tick(self, symbol: str) -> dict[str, Any] | None:
        return self.store.fetchone(
            "SELECT * FROM ps_ticks WHERE symbol=? ORDER BY created_at DESC LIMIT 1",
            (symbol.upper(),),
        )

    def order_book(self, symbol: str, depth: int = 5) -> dict[str, Any]:
        symbol = symbol.upper()
        bids = self.store.fetchall(
            "SELECT price, size FROM ps_book_levels WHERE symbol=? AND side='BID' "
            "ORDER BY price DESC LIMIT ?",
            (symbol, depth),
        )
        asks = self.store.fetchall(
            "SELECT price, size FROM ps_book_levels WHERE symbol=? AND side='ASK' "
            "ORDER BY price ASC LIMIT ?",
            (symbol, depth),
        )
        return {
            "ok": True,
            "symbol": symbol,
            "bids": bids,
            "asks": asks,
            "simulated": True,
            **AUTHORITY_VALUES,
        }

    def list_symbols(self) -> dict[str, Any]:
        rows = self.store.fetchall("SELECT symbol, state FROM ps_sessions ORDER BY symbol")
        return {"ok": True, "symbols": rows, "count": len(rows), **AUTHORITY_VALUES}

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "exchange": "VIRTUAL_PAPER_EXCHANGE",
            "real_exchange": False,
            "broker_connected": False,
            "symbols": self.list_symbols().get("symbols"),
            **AUTHORITY_VALUES,
        }
