"""SQLite store for M280–M287 research orchestrator."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from saathi.platform.tg.research_orchestrator.models import ENGINE_VERSION, SCHEMA_VERSION

ORCH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS orch_meta (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orch_audit (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, actor TEXT NOT NULL,
  subject TEXT NOT NULL DEFAULT '', detail_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orch_jobs (
  job_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  template_id TEXT,
  state TEXT NOT NULL,
  priority INTEGER NOT NULL,
  priority_label TEXT NOT NULL,
  config_json TEXT NOT NULL,
  config_checksum TEXT NOT NULL,
  depends_on_json TEXT NOT NULL DEFAULT '[]',
  budget_units REAL NOT NULL DEFAULT 1,
  estimated_runtime_sec REAL NOT NULL DEFAULT 1,
  retry_count INTEGER NOT NULL DEFAULT 0,
  max_retries INTEGER NOT NULL DEFAULT 2,
  worker_id TEXT,
  result_json TEXT,
  error_json TEXT,
  evidence_hash TEXT,
  created_at REAL NOT NULL,
  queued_at REAL,
  started_at REAL,
  finished_at REAL,
  cancelled_at REAL,
  immutable INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS orch_workers (
  worker_id TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  current_job_id TEXT,
  jobs_completed INTEGER NOT NULL DEFAULT 0,
  jobs_failed INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orch_budget (
  id TEXT PRIMARY KEY,
  total_units REAL NOT NULL,
  reserved_units REAL NOT NULL DEFAULT 0,
  spent_units REAL NOT NULL DEFAULT 0,
  state TEXT NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orch_templates (
  template_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  body_json TEXT NOT NULL,
  checksum TEXT NOT NULL,
  promoted INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orch_models (
  model_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  meta_json TEXT NOT NULL,
  checksum TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orch_hypotheses (
  hypothesis_id TEXT PRIMARY KEY,
  statement TEXT NOT NULL,
  status TEXT NOT NULL,
  job_ids_json TEXT NOT NULL DEFAULT '[]',
  evidence_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orch_journal (
  entry_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  refs_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orch_timeline (
  event_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  subject TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orch_sessions (
  session_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  seed INTEGER NOT NULL,
  config_json TEXT NOT NULL,
  job_ids_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL,
  created_at REAL NOT NULL,
  closed_at REAL
);
CREATE TABLE IF NOT EXISTS orch_promotions (
  id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  state TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orch_certifications (
  id TEXT PRIMARY KEY,
  verdict TEXT NOT NULL,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orch_jobs_state ON orch_jobs(state);
CREATE INDEX IF NOT EXISTS idx_orch_jobs_priority ON orch_jobs(priority, created_at);
CREATE INDEX IF NOT EXISTS idx_orch_timeline ON orch_timeline(created_at);
"""


def _uid(prefix: str = "orch") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def evidence_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def config_checksum(config: dict) -> str:
    return evidence_hash(config)


class OrchestratorStore:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            root = Path(__file__).resolve().parents[4] / "data" / "platform"
            root.mkdir(parents=True, exist_ok=True)
            db_path = root / "research_orchestrator.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def migrate(self) -> None:
        self._conn.executescript(ORCH_SCHEMA_SQL)
        now = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO orch_meta(key, value, updated_at) VALUES(?,?,?)",
            ("schema_version", SCHEMA_VERSION, now),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO orch_meta(key, value, updated_at) VALUES(?,?,?)",
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
            "INSERT INTO orch_audit(id, kind, actor, subject, detail_json, evidence_hash, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (eid, kind, actor, subject, json.dumps(detail, sort_keys=True, default=str), eh, time.time()),
        )
        return eid

    def timeline(self, kind: str, subject: str, detail: dict | None = None) -> str:
        eid = _uid("evt")
        self.execute(
            "INSERT INTO orch_timeline(event_id, kind, subject, detail_json, created_at) VALUES(?,?,?,?,?)",
            (eid, kind, subject, json.dumps(detail or {}, sort_keys=True, default=str), time.time()),
        )
        return eid
