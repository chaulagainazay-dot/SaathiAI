"""In-process / SQLite NAV history for drawdown and period P&L."""
from __future__ import annotations

import sqlite3
import threading
import time as _time
from decimal import Decimal
from pathlib import Path
from typing import Any

from saathi.platform.fund_ledger.money import D


class NavHistoryStore:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path) if path else ":memory:"
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS risk_nav_history (
                fund_id TEXT NOT NULL,
                ts REAL NOT NULL,
                nav TEXT NOT NULL,
                PRIMARY KEY (fund_id, ts)
            );
            CREATE TABLE IF NOT EXISTS risk_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                fund_id TEXT NOT NULL,
                ts REAL NOT NULL,
                payload_json TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def record_nav(self, fund_id: str, nav: Any, ts: float | None = None) -> None:
        t = float(ts if ts is not None else _time.time())
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO risk_nav_history(fund_id,ts,nav) VALUES(?,?,?)",
                (fund_id, t, str(D(nav))),
            )
            self._conn.commit()

    def series(self, fund_id: str) -> list[tuple[float, Decimal]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, nav FROM risk_nav_history WHERE fund_id=? ORDER BY ts ASC",
                (fund_id,),
            ).fetchall()
        return [(float(r["ts"]), D(r["nav"])) for r in rows]

    def save_snapshot(self, snapshot_id: str, fund_id: str, payload: dict, ts: float | None = None) -> None:
        import json

        t = float(ts if ts is not None else _time.time())
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO risk_snapshots(snapshot_id,fund_id,ts,payload_json) VALUES(?,?,?,?)",
                (snapshot_id, fund_id, t, json.dumps(payload, sort_keys=True, default=str)),
            )
            self._conn.commit()
