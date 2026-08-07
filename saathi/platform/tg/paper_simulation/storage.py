"""SQLite store for institutional paper simulation."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from saathi.platform.tg.paper_simulation.models import ENGINE_VERSION, SCHEMA_VERSION

PS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ps_meta (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ps_audit (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, actor TEXT NOT NULL,
  subject TEXT NOT NULL DEFAULT '', detail_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ps_portfolios (
  portfolio_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  cash REAL NOT NULL,
  initial_cash REAL NOT NULL,
  state TEXT NOT NULL,
  margin_enabled INTEGER NOT NULL DEFAULT 0,
  max_leverage REAL NOT NULL DEFAULT 1.0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ps_positions (
  id TEXT PRIMARY KEY,
  portfolio_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  quantity REAL NOT NULL,
  avg_cost REAL NOT NULL,
  mark REAL NOT NULL,
  realized_pnl REAL NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL,
  UNIQUE(portfolio_id, symbol)
);
CREATE TABLE IF NOT EXISTS ps_orders (
  order_id TEXT PRIMARY KEY,
  portfolio_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL,
  order_type TEXT NOT NULL,
  quantity REAL NOT NULL,
  filled_qty REAL NOT NULL DEFAULT 0,
  limit_price REAL,
  stop_price REAL,
  tif TEXT NOT NULL DEFAULT 'DAY',
  status TEXT NOT NULL,
  reject_reason TEXT,
  latency_ms INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  accepted_at REAL,
  finished_at REAL
);
CREATE TABLE IF NOT EXISTS ps_fills (
  fill_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL,
  portfolio_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL,
  quantity REAL NOT NULL,
  price REAL NOT NULL,
  fee REAL NOT NULL,
  slippage_bps REAL NOT NULL,
  liquidity_flag TEXT NOT NULL DEFAULT 'SIMULATED',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ps_cash_ledger (
  entry_id TEXT PRIMARY KEY,
  portfolio_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  amount REAL NOT NULL,
  balance_after REAL NOT NULL,
  ref TEXT NOT NULL DEFAULT '',
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ps_book_levels (
  id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL,
  price REAL NOT NULL,
  size REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ps_ticks (
  id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  bid REAL NOT NULL,
  ask REAL NOT NULL,
  last REAL NOT NULL,
  volume REAL NOT NULL,
  session_state TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ps_sessions (
  symbol TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  open_ts REAL,
  close_ts REAL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ps_corporate_actions (
  id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  action_type TEXT NOT NULL,
  ratio REAL,
  amount REAL,
  ex_date TEXT NOT NULL,
  applied INTEGER NOT NULL DEFAULT 0,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ps_kill_switch (
  id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  scope_ref TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL,
  reason TEXT NOT NULL,
  activated_by TEXT NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ps_risk_events (
  id TEXT PRIMARY KEY,
  portfolio_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  severity TEXT NOT NULL,
  message TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ps_journal (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  refs_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ps_certifications (
  id TEXT PRIMARY KEY,
  verdict TEXT NOT NULL,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ps_orders_pf ON ps_orders(portfolio_id, status);
CREATE INDEX IF NOT EXISTS idx_ps_fills_order ON ps_fills(order_id);
CREATE INDEX IF NOT EXISTS idx_ps_cash_pf ON ps_cash_ledger(portfolio_id, created_at);
"""


def _uid(prefix: str = "ps") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def evidence_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class PaperSimStore:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            root = Path(__file__).resolve().parents[4] / "data" / "platform"
            root.mkdir(parents=True, exist_ok=True)
            db_path = root / "paper_simulation.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def migrate(self) -> None:
        self._conn.executescript(PS_SCHEMA_SQL)
        now = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO ps_meta(key, value, updated_at) VALUES(?,?,?)",
            ("schema_version", SCHEMA_VERSION, now),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO ps_meta(key, value, updated_at) VALUES(?,?,?)",
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

    def audit(self, kind: str, *, actor: str = "system", subject: str = "", detail: dict | None = None) -> str:
        eid = _uid("aud")
        detail = detail or {}
        eh = evidence_hash(detail)
        self.execute(
            "INSERT INTO ps_audit(id, kind, actor, subject, detail_json, evidence_hash, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (eid, kind, actor, subject, json.dumps(detail, sort_keys=True, default=str), eh, time.time()),
        )
        return eid
