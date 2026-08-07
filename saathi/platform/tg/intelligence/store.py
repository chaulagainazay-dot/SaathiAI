"""SQLite store for M248–M255 institutional intelligence. Paper only."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from saathi.platform.tg.intelligence.models import ENGINE_VERSION, SCHEMA_VERSION

II_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ii_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ii_audit_events (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  actor TEXT NOT NULL,
  subject TEXT NOT NULL DEFAULT '',
  detail_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ii_decisions (
  id TEXT PRIMARY KEY,
  instrument TEXT NOT NULL,
  action TEXT NOT NULL,
  confidence REAL NOT NULL,
  explanation_json TEXT NOT NULL,
  committee_json TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ii_backtests (
  id TEXT PRIMARY KEY,
  strategy_id TEXT NOT NULL,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ii_simulations (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  seed INTEGER NOT NULL,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ii_walk_forwards (
  id TEXT PRIMARY KEY,
  strategy_id TEXT NOT NULL,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ii_watchlists (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  symbols_json TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ii_alerts (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  severity TEXT NOT NULL,
  message TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ii_certifications (
  id TEXT PRIMARY KEY,
  verdict TEXT NOT NULL,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ii_audit_created ON ii_audit_events(created_at);
CREATE INDEX IF NOT EXISTS idx_ii_decisions_created ON ii_decisions(created_at);
"""


def _uid(prefix: str = "ii") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def evidence_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class IntelligenceStore:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            root = Path(__file__).resolve().parents[4] / "data" / "platform"
            root.mkdir(parents=True, exist_ok=True)
            db_path = root / "institutional_intelligence.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def migrate(self) -> None:
        self._conn.executescript(II_SCHEMA_SQL)
        now = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO ii_meta(key, value, updated_at) VALUES(?,?,?)",
            ("schema_version", SCHEMA_VERSION, now),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO ii_meta(key, value, updated_at) VALUES(?,?,?)",
            ("engine_version", ENGINE_VERSION, now),
        )
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur

    def fetchone(self, sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
        row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetchall(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def audit(
        self,
        kind: str,
        *,
        actor: str = "system",
        subject: str = "",
        detail: dict | None = None,
    ) -> str:
        eid = _uid("aud")
        detail = detail or {}
        eh = evidence_hash(detail)
        self.execute(
            """INSERT INTO ii_audit_events(id, kind, actor, subject, detail_json, evidence_hash, created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (eid, kind, actor, subject, json.dumps(detail, default=str), eh, time.time()),
        )
        return eid

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.fetchall(
            "SELECT * FROM ii_audit_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        for r in rows:
            try:
                r["detail"] = json.loads(r.pop("detail_json", "{}"))
            except Exception:
                r["detail"] = {}
        return rows

    def save_decision(
        self,
        instrument: str,
        action: str,
        confidence: float,
        explanation: dict,
        committee: dict,
    ) -> str:
        did = _uid("dec")
        self.execute(
            """INSERT INTO ii_decisions(id, instrument, action, confidence, explanation_json, committee_json, created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (
                did,
                instrument,
                action,
                confidence,
                json.dumps(explanation, default=str),
                json.dumps(committee, default=str),
                time.time(),
            ),
        )
        return did

    def list_decisions(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.fetchall(
            "SELECT * FROM ii_decisions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        out = []
        for r in rows:
            try:
                r["explanation"] = json.loads(r.pop("explanation_json", "{}"))
            except Exception:
                r["explanation"] = {}
            try:
                r["committee"] = json.loads(r.pop("committee_json", "{}"))
            except Exception:
                r["committee"] = {}
            out.append(r)
        return out

    def save_run(self, table: str, **fields: Any) -> str:
        rid = fields.get("id") or _uid(table[:3])
        if table == "ii_backtests":
            self.execute(
                "INSERT INTO ii_backtests(id, strategy_id, result_json, evidence_hash, created_at) VALUES(?,?,?,?,?)",
                (rid, fields["strategy_id"], json.dumps(fields["result"], default=str),
                 fields.get("evidence_hash") or evidence_hash(fields["result"]), time.time()),
            )
        elif table == "ii_simulations":
            self.execute(
                "INSERT INTO ii_simulations(id, kind, seed, result_json, evidence_hash, created_at) VALUES(?,?,?,?,?,?)",
                (rid, fields["kind"], fields["seed"], json.dumps(fields["result"], default=str),
                 fields.get("evidence_hash") or evidence_hash(fields["result"]), time.time()),
            )
        elif table == "ii_walk_forwards":
            self.execute(
                "INSERT INTO ii_walk_forwards(id, strategy_id, result_json, evidence_hash, created_at) VALUES(?,?,?,?,?)",
                (rid, fields["strategy_id"], json.dumps(fields["result"], default=str),
                 fields.get("evidence_hash") or evidence_hash(fields["result"]), time.time()),
            )
        return rid

    def add_alert(self, kind: str, severity: str, message: str, detail: dict | None = None) -> str:
        aid = _uid("alr")
        self.execute(
            "INSERT INTO ii_alerts(id, kind, severity, message, detail_json, created_at) VALUES(?,?,?,?,?,?)",
            (aid, kind, severity, message, json.dumps(detail or {}, default=str), time.time()),
        )
        return aid

    def list_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.fetchall(
            "SELECT * FROM ii_alerts ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        for r in rows:
            try:
                r["detail"] = json.loads(r.pop("detail_json", "{}"))
            except Exception:
                r["detail"] = {}
        return rows

    def upsert_watchlist(self, name: str, symbols: list[str]) -> str:
        existing = self.fetchone("SELECT id FROM ii_watchlists WHERE name=?", (name,))
        if existing:
            self.execute(
                "UPDATE ii_watchlists SET symbols_json=? WHERE id=?",
                (json.dumps(symbols), existing["id"]),
            )
            return existing["id"]
        wid = _uid("wl")
        self.execute(
            "INSERT INTO ii_watchlists(id, name, symbols_json, created_at) VALUES(?,?,?,?)",
            (wid, name, json.dumps(symbols), time.time()),
        )
        return wid

    def list_watchlists(self) -> list[dict[str, Any]]:
        rows = self.fetchall("SELECT * FROM ii_watchlists ORDER BY created_at DESC")
        for r in rows:
            try:
                r["symbols"] = json.loads(r.pop("symbols_json", "[]"))
            except Exception:
                r["symbols"] = []
        return rows
