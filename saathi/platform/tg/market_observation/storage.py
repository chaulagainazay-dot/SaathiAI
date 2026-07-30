"""SQLite store for read-only market observation (no credentials, no accounts)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from saathi.platform.tg.market_observation.models import ENGINE_VERSION, SCHEMA_VERSION

MO_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS mo_meta (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mo_audit (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, actor TEXT NOT NULL,
  subject TEXT NOT NULL DEFAULT '', detail_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mo_symbols (
  symbol TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  asset_class TEXT NOT NULL,
  exchange TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  tick_size REAL NOT NULL DEFAULT 0.01,
  lot_size REAL NOT NULL DEFAULT 1.0,
  meta_json TEXT NOT NULL DEFAULT '{}',
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mo_quotes (
  id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  bid REAL NOT NULL,
  ask REAL NOT NULL,
  last REAL NOT NULL,
  volume REAL NOT NULL,
  source TEXT NOT NULL,
  freshness TEXT NOT NULL,
  observed_at REAL NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mo_snapshots (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  source TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mo_bars (
  id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  ts REAL NOT NULL,
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume REAL NOT NULL,
  source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mo_exchange_status (
  exchange TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  session TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mo_corporate_actions (
  id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  action_type TEXT NOT NULL,
  ex_date TEXT NOT NULL,
  amount REAL,
  ratio REAL,
  source TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mo_benchmarks (
  id TEXT PRIMARY KEY,
  benchmark TEXT NOT NULL,
  as_of REAL NOT NULL,
  level REAL NOT NULL,
  change_pct REAL NOT NULL,
  source TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mo_certifications (
  id TEXT PRIMARY KEY,
  verdict TEXT NOT NULL,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mo_quotes_sym ON mo_quotes(symbol, observed_at);
CREATE INDEX IF NOT EXISTS idx_mo_bars_sym ON mo_bars(symbol, ts);
"""


def _uid(prefix: str = "mo") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def evidence_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class ObservationStore:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            root = Path(__file__).resolve().parents[4] / "data" / "platform"
            root.mkdir(parents=True, exist_ok=True)
            db_path = root / "market_observation.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.migrate()

    def migrate(self) -> None:
        self._conn.executescript(MO_SCHEMA_SQL)
        now = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO mo_meta(key, value, updated_at) VALUES(?,?,?)",
            ("schema_version", SCHEMA_VERSION, now),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO mo_meta(key, value, updated_at) VALUES(?,?,?)",
            ("engine_version", ENGINE_VERSION, now),
        )
        # Hard meta: never store credentials
        self._conn.execute(
            "INSERT OR REPLACE INTO mo_meta(key, value, updated_at) VALUES(?,?,?)",
            ("credentials_stored", "false", now),
        )
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        # Block accidental credential column attempts
        low = sql.lower()
        if any(x in low for x in ("api_key", "api_secret", "oauth", "password", "access_token")):
            raise ValueError("credential fields forbidden in market observation store")
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
        # strip any accidental secrets
        safe = {k: v for k, v in detail.items() if "key" not in k.lower() and "secret" not in k.lower() and "token" not in k.lower()}
        eh = evidence_hash(safe)
        self.execute(
            "INSERT INTO mo_audit(id, kind, actor, subject, detail_json, evidence_hash, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (eid, kind, actor, subject, json.dumps(safe, sort_keys=True, default=str), eh, time.time()),
        )
        return eid
