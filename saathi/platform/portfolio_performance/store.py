"""Persistent performance observations (SQLite). Idempotent by observation_id."""
from __future__ import annotations

import json
import sqlite3
import threading
import time as _time
from pathlib import Path
from typing import Any


_SCHEMA = """
CREATE TABLE IF NOT EXISTS perf_observations (
    observation_id TEXT PRIMARY KEY,
    fund_id TEXT NOT NULL,
    ts REAL NOT NULL,
    state_hash TEXT NOT NULL DEFAULT '',
    event_count INTEGER NOT NULL DEFAULT 0,
    nav TEXT NOT NULL,
    cash TEXT NOT NULL,
    market_value TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    unrealized_pnl TEXT NOT NULL,
    total_fees TEXT NOT NULL DEFAULT '0',
    external_flow TEXT NOT NULL DEFAULT '0',
    mark_stale INTEGER NOT NULL DEFAULT 0,
    stale_securities_json TEXT NOT NULL DEFAULT '[]',
    positions_json TEXT NOT NULL DEFAULT '[]',
    payload_json TEXT NOT NULL,
    UNIQUE (fund_id, state_hash)
);
CREATE INDEX IF NOT EXISTS idx_perf_fund_ts ON perf_observations(fund_id, ts ASC);
CREATE TABLE IF NOT EXISTS perf_decision_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_id TEXT NOT NULL,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    ref_id TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_perf_dec_fund ON perf_decision_links(fund_id, ts ASC);
"""


class PerformanceStore:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path) if path else ":memory:"
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def upsert_observation(self, obs: dict) -> dict:
        """Insert observation. Duplicate (fund_id, state_hash) is idempotent no-op."""
        with self._lock:
            try:
                self._conn.execute(
                    """INSERT INTO perf_observations(
                        observation_id,fund_id,ts,state_hash,event_count,nav,cash,market_value,
                        realized_pnl,unrealized_pnl,total_fees,external_flow,mark_stale,
                        stale_securities_json,positions_json,payload_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        obs["observation_id"],
                        obs["fund_id"],
                        float(obs["ts"]),
                        obs.get("state_hash") or "",
                        int(obs.get("event_count") or 0),
                        str(obs["nav"]),
                        str(obs["cash"]),
                        str(obs["market_value"]),
                        str(obs["realized_pnl"]),
                        str(obs["unrealized_pnl"]),
                        str(obs.get("total_fees") or "0"),
                        str(obs.get("external_flow") or "0"),
                        1 if obs.get("mark_stale") else 0,
                        json.dumps(obs.get("stale_securities") or [], default=str),
                        json.dumps(obs.get("positions") or [], default=str),
                        json.dumps(obs, sort_keys=True, default=str),
                    ),
                )
                self._conn.commit()
                return {"ok": True, "inserted": True, "observation_id": obs["observation_id"]}
            except sqlite3.IntegrityError:
                # unique state_hash or primary key — idempotent
                self._conn.rollback()
                return {"ok": True, "inserted": False, "observation_id": obs["observation_id"], "duplicate": True}

    def list_observations(self, fund_id: str, *, since: float | None = None, until: float | None = None) -> list[dict]:
        with self._lock:
            q = "SELECT payload_json FROM perf_observations WHERE fund_id=?"
            args: list[Any] = [fund_id]
            if since is not None:
                q += " AND ts>=?"
                args.append(float(since))
            if until is not None:
                q += " AND ts<=?"
                args.append(float(until))
            q += " ORDER BY ts ASC"
            rows = self._conn.execute(q, args).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    def count(self, fund_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM perf_observations WHERE fund_id=?", (fund_id,)
            ).fetchone()
        return int(row["c"] if row else 0)

    def add_decision_link(self, fund_id: str, kind: str, ref_id: str = "", note: str = "", payload: dict | None = None, ts: float | None = None) -> None:
        t = float(ts if ts is not None else _time.time())
        with self._lock:
            self._conn.execute(
                "INSERT INTO perf_decision_links(fund_id,ts,kind,ref_id,note,payload_json) VALUES(?,?,?,?,?,?)",
                (fund_id, t, kind, ref_id, note, json.dumps(payload or {}, default=str)),
            )
            self._conn.commit()

    def list_decision_links(self, fund_id: str, *, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts,kind,ref_id,note,payload_json FROM perf_decision_links WHERE fund_id=? ORDER BY ts ASC LIMIT ?",
                (fund_id, limit),
            ).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "ts": r["ts"],
                    "kind": r["kind"],
                    "ref_id": r["ref_id"],
                    "note": r["note"],
                    "payload": json.loads(r["payload_json"] or "{}"),
                    "association": "ASSOCIATED_WITH",  # never claim causation
                }
            )
        return out
