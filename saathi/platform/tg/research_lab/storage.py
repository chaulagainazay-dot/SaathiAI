"""SQLite durable store for M272–M279 research lab.

RESEARCH ONLY. No credentials, broker accounts, orders, or live positions.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from saathi.platform.tg.research_lab.models import ENGINE_VERSION, SCHEMA_VERSION

RL_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS rl_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rl_audit_events (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  actor TEXT NOT NULL,
  subject TEXT NOT NULL DEFAULT '',
  detail_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rl_experiments (
  experiment_id TEXT NOT NULL,
  experiment_version TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  config_json TEXT NOT NULL,
  config_checksum TEXT NOT NULL,
  parent_id TEXT,
  parent_version TEXT,
  actor TEXT NOT NULL,
  created_at REAL NOT NULL,
  execution_at REAL,
  result_json TEXT,
  evidence_hash TEXT,
  immutable INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (experiment_id, experiment_version)
);
CREATE TABLE IF NOT EXISTS rl_comparisons (
  id TEXT PRIMARY KEY,
  experiment_id TEXT,
  experiment_version TEXT,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rl_robustness (
  id TEXT PRIMARY KEY,
  experiment_id TEXT,
  experiment_version TEXT,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rl_regimes (
  id TEXT PRIMARY KEY,
  definition_json TEXT NOT NULL,
  version TEXT NOT NULL,
  checksum TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rl_regime_classifications (
  id TEXT PRIMARY KEY,
  regime_def_id TEXT NOT NULL,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rl_portfolios (
  id TEXT PRIMARY KEY,
  method TEXT NOT NULL,
  config_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rl_ensembles (
  id TEXT PRIMARY KEY,
  method TEXT NOT NULL,
  config_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rl_stress (
  id TEXT PRIMARY KEY,
  portfolio_id TEXT,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rl_candidates (
  id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  state TEXT NOT NULL,
  gates_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  human_review_status TEXT NOT NULL DEFAULT 'REQUIRED',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rl_certifications (
  id TEXT PRIMARY KEY,
  verdict TEXT NOT NULL,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS rl_lineage (
  id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  parent_id TEXT,
  edge TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rl_exp_status ON rl_experiments(status);
CREATE INDEX IF NOT EXISTS idx_rl_audit_created ON rl_audit_events(created_at);
CREATE INDEX IF NOT EXISTS idx_rl_cand_state ON rl_candidates(state);
"""


def _uid(prefix: str = "rl") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def evidence_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def config_checksum(config: dict) -> str:
    """Deterministic configuration hash (sorted keys)."""
    return evidence_hash(config)


def deterministic_experiment_id(name: str, config: dict) -> str:
    """Deterministic experiment identity from name + config checksum."""
    cs = config_checksum(config)
    digest = hashlib.sha256(f"{name}|{cs}".encode("utf-8")).hexdigest()[:16]
    return f"exp_{digest}"


class ResearchLabStore:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            root = Path(__file__).resolve().parents[4] / "data" / "platform"
            root.mkdir(parents=True, exist_ok=True)
            db_path = root / "research_lab.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def migrate(self) -> None:
        self._conn.executescript(RL_SCHEMA_SQL)
        now = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO rl_meta(key, value, updated_at) VALUES(?,?,?)",
            ("schema_version", SCHEMA_VERSION, now),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO rl_meta(key, value, updated_at) VALUES(?,?,?)",
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
            "INSERT INTO rl_audit_events(id, kind, actor, subject, detail_json, evidence_hash, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (eid, kind, actor, subject, json.dumps(detail, sort_keys=True, default=str), eh, time.time()),
        )
        return eid

    def set_meta(self, key: str, value: str) -> None:
        self.execute(
            "INSERT OR REPLACE INTO rl_meta(key, value, updated_at) VALUES(?,?,?)",
            (key, value, time.time()),
        )

    def get_meta(self, key: str) -> str | None:
        row = self.fetchone("SELECT value FROM rl_meta WHERE key=?", (key,))
        return row["value"] if row else None
