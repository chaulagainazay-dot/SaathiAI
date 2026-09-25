"""Immutable proposal persistence (SQLite)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time as _time
from pathlib import Path
from typing import Any


_SCHEMA = """
CREATE TABLE IF NOT EXISTS pc_proposals (
    proposal_id TEXT PRIMARY KEY,
    fund_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    valid_until REAL,
    supersedes_proposal_id TEXT NOT NULL DEFAULT '',
    portfolio_snapshot_ref TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pc_fund ON pc_proposals(fund_id, created_at DESC);
CREATE TABLE IF NOT EXISTS pc_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    ts REAL NOT NULL
);
"""


class ProposalStore:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path) if path else ":memory:"
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def save(self, proposal_public: dict) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO pc_proposals(
                    proposal_id,fund_id,status,created_at,valid_until,supersedes_proposal_id,
                    portfolio_snapshot_ref,payload_json
                ) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    proposal_public["proposal_id"],
                    proposal_public["fund_id"],
                    proposal_public["status"],
                    proposal_public["created_at"],
                    proposal_public.get("expires_at"),
                    proposal_public.get("supersedes_proposal_id") or "",
                    proposal_public.get("portfolio_snapshot_ref") or "",
                    json.dumps(proposal_public, sort_keys=True, default=str),
                ),
            )
            self._conn.commit()

    def get(self, proposal_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM pc_proposals WHERE proposal_id=?", (proposal_id,)
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_for_fund(self, fund_id: str, *, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload_json FROM pc_proposals WHERE fund_id=? ORDER BY created_at DESC LIMIT ?",
                (fund_id, limit),
            ).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    def transition(self, proposal_id: str, from_status: str, to_status: str, reason: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO pc_transitions(proposal_id,from_status,to_status,reason,ts) VALUES(?,?,?,?,?)",
                (proposal_id, from_status, to_status, reason, _time.time()),
            )
            # update status in payload
            row = self._conn.execute(
                "SELECT payload_json FROM pc_proposals WHERE proposal_id=?", (proposal_id,)
            ).fetchone()
            if row:
                payload = json.loads(row["payload_json"])
                payload["status"] = to_status
                self._conn.execute(
                    "UPDATE pc_proposals SET status=?, payload_json=? WHERE proposal_id=?",
                    (to_status, json.dumps(payload, sort_keys=True, default=str), proposal_id),
                )
            self._conn.commit()
