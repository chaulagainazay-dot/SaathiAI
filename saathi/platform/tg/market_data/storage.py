"""Durable SQLite store for M256–M263 market-data research. No credentials."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from saathi.platform.tg.market_data.models import ENGINE_VERSION, SCHEMA_VERSION

MD_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS md_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS md_audit (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  actor TEXT NOT NULL,
  subject TEXT NOT NULL DEFAULT '',
  detail_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS md_datasets (
  dataset_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  provider TEXT NOT NULL DEFAULT '',
  source_type TEXT NOT NULL,
  source_ref TEXT NOT NULL DEFAULT '',
  retrieval_ts REAL,
  ingestion_ts REAL,
  market TEXT NOT NULL DEFAULT '',
  exchange TEXT NOT NULL DEFAULT '',
  asset_class TEXT NOT NULL DEFAULT '',
  instrument_type TEXT NOT NULL DEFAULT '',
  symbol_namespace TEXT NOT NULL DEFAULT '',
  coverage_start TEXT,
  coverage_end TEXT,
  frequency TEXT NOT NULL DEFAULT '',
  timezone TEXT NOT NULL DEFAULT 'UTC',
  currency TEXT NOT NULL DEFAULT 'USD',
  price_fields_json TEXT NOT NULL DEFAULT '[]',
  volume_fields_json TEXT NOT NULL DEFAULT '[]',
  corporate_action_coverage INTEGER NOT NULL DEFAULT 0,
  benchmark_coverage INTEGER NOT NULL DEFAULT 0,
  survivorship_json TEXT NOT NULL DEFAULT '{}',
  revision_policy TEXT NOT NULL DEFAULT '',
  licence_type TEXT NOT NULL DEFAULT '',
  redistribution_status TEXT NOT NULL DEFAULT '',
  commercial_use_status TEXT NOT NULL DEFAULT '',
  retention_restrictions TEXT NOT NULL DEFAULT '',
  citation_requirements TEXT NOT NULL DEFAULT '',
  checksum TEXT NOT NULL DEFAULT '',
  row_count INTEGER NOT NULL DEFAULT 0,
  file_size INTEGER NOT NULL DEFAULT 0,
  schema_version TEXT NOT NULL DEFAULT '',
  quality_status TEXT NOT NULL DEFAULT '',
  approval_status TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL,
  limitations_json TEXT NOT NULL DEFAULT '[]',
  evidence_refs_json TEXT NOT NULL DEFAULT '[]',
  parent_dataset_id TEXT,
  superseded_by TEXT,
  file_path TEXT NOT NULL DEFAULT '',
  is_synthetic INTEGER NOT NULL DEFAULT 0,
  meta_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  PRIMARY KEY (dataset_id, dataset_version)
);
CREATE TABLE IF NOT EXISTS md_licences (
  id TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  licence_name TEXT NOT NULL,
  licence_version TEXT NOT NULL DEFAULT '',
  official_source TEXT NOT NULL DEFAULT '',
  commercial_use TEXT NOT NULL DEFAULT 'unknown',
  redistribution TEXT NOT NULL DEFAULT 'unknown',
  modification TEXT NOT NULL DEFAULT 'unknown',
  attribution_required INTEGER NOT NULL DEFAULT 1,
  retention_limit TEXT NOT NULL DEFAULT '',
  geographic_restriction TEXT NOT NULL DEFAULT '',
  usage_restriction TEXT NOT NULL DEFAULT '',
  unknown_terms INTEGER NOT NULL DEFAULT 0,
  legal_review_required INTEGER NOT NULL DEFAULT 0,
  governance_class TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS md_provenance (
  id TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  original_publisher TEXT NOT NULL DEFAULT '',
  source_location TEXT NOT NULL DEFAULT '',
  retrieval_date TEXT NOT NULL DEFAULT '',
  retrieval_method TEXT NOT NULL DEFAULT '',
  transformation_history_json TEXT NOT NULL DEFAULT '[]',
  parent_dataset TEXT NOT NULL DEFAULT '',
  derived_lineage_json TEXT NOT NULL DEFAULT '[]',
  software_version TEXT NOT NULL DEFAULT '',
  processing_config_json TEXT NOT NULL DEFAULT '{}',
  operator TEXT NOT NULL DEFAULT 'system',
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS md_ingestion_jobs (
  id TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  source_checksum TEXT NOT NULL,
  input_row_count INTEGER NOT NULL DEFAULT 0,
  accepted_row_count INTEGER NOT NULL DEFAULT 0,
  rejected_row_count INTEGER NOT NULL DEFAULT 0,
  duplicate_count INTEGER NOT NULL DEFAULT 0,
  transformed_row_count INTEGER NOT NULL DEFAULT 0,
  output_checksum TEXT NOT NULL DEFAULT '',
  schema_version TEXT NOT NULL DEFAULT '',
  processing_duration_ms REAL NOT NULL DEFAULT 0,
  warning_summary_json TEXT NOT NULL DEFAULT '[]',
  error_summary_json TEXT NOT NULL DEFAULT '[]',
  rejected_samples_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL,
  manifest_json TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS md_bars (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  instrument_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  exchange TEXT NOT NULL DEFAULT '',
  asset_class TEXT NOT NULL DEFAULT '',
  timestamp TEXT NOT NULL,
  timezone TEXT NOT NULL DEFAULT 'UTC',
  interval TEXT NOT NULL DEFAULT '1d',
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  adjusted_close REAL,
  volume REAL,
  trade_count REAL,
  vwap REAL,
  currency TEXT NOT NULL DEFAULT 'USD',
  source_row_ref TEXT NOT NULL DEFAULT '',
  ingestion_version TEXT NOT NULL DEFAULT '',
  row_status TEXT NOT NULL DEFAULT 'NORMALIZED',
  UNIQUE(dataset_id, dataset_version, symbol, timestamp, interval)
);
CREATE TABLE IF NOT EXISTS md_quality_reports (
  id TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  classification TEXT NOT NULL,
  scores_json TEXT NOT NULL,
  findings_json TEXT NOT NULL,
  blocking_defects_json TEXT NOT NULL,
  report_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS md_corporate_actions (
  id TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  symbol TEXT NOT NULL,
  action_type TEXT NOT NULL,
  effective_date TEXT NOT NULL,
  availability_date TEXT NOT NULL,
  factor REAL NOT NULL DEFAULT 1.0,
  amount REAL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  provenance TEXT NOT NULL DEFAULT '',
  adjustment_version TEXT NOT NULL DEFAULT 'v1',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS md_calendars (
  id TEXT PRIMARY KEY,
  exchange TEXT NOT NULL,
  market TEXT NOT NULL DEFAULT '',
  asset_class TEXT NOT NULL DEFAULT 'equity',
  sessions_json TEXT NOT NULL,
  holidays_json TEXT NOT NULL DEFAULT '[]',
  early_closes_json TEXT NOT NULL DEFAULT '[]',
  timezone TEXT NOT NULL DEFAULT 'UTC',
  is_247 INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS md_bias_reports (
  id TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  report_json TEXT NOT NULL,
  invariants_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS md_splits (
  id TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  kind TEXT NOT NULL,
  config_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS md_features (
  feature_id TEXT NOT NULL,
  feature_version TEXT NOT NULL,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  formula TEXT NOT NULL,
  lookback INTEGER NOT NULL DEFAULT 0,
  timestamp_semantics TEXT NOT NULL DEFAULT 'bar_close',
  availability_rule TEXT NOT NULL DEFAULT 'same_bar_close',
  missing_data_policy TEXT NOT NULL DEFAULT 'propagate_null',
  normalization_policy TEXT NOT NULL DEFAULT 'none',
  input_dataset_versions_json TEXT NOT NULL DEFAULT '[]',
  output_checksum TEXT NOT NULL DEFAULT '',
  creator_version TEXT NOT NULL DEFAULT '',
  lineage_json TEXT NOT NULL DEFAULT '[]',
  limitations_json TEXT NOT NULL DEFAULT '[]',
  certified INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  PRIMARY KEY (feature_id, feature_version)
);
CREATE TABLE IF NOT EXISTS md_feature_values (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feature_id TEXT NOT NULL,
  feature_version TEXT NOT NULL,
  dataset_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  symbol TEXT NOT NULL,
  event_ts TEXT NOT NULL,
  availability_ts TEXT NOT NULL,
  processing_ts TEXT NOT NULL,
  value REAL,
  meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS md_validation_runs (
  id TEXT PRIMARY KEY,
  strategy_id TEXT NOT NULL,
  strategy_version TEXT NOT NULL DEFAULT 'v1',
  dataset_id TEXT NOT NULL,
  dataset_version TEXT NOT NULL,
  state TEXT NOT NULL,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS md_certifications (
  id TEXT PRIMARY KEY,
  verdict TEXT NOT NULL,
  result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_md_datasets_state ON md_datasets(state);
CREATE INDEX IF NOT EXISTS idx_md_bars_ds ON md_bars(dataset_id, dataset_version, symbol, timestamp);
CREATE INDEX IF NOT EXISTS idx_md_audit_created ON md_audit(created_at);
"""


def _uid(prefix: str = "md") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def evidence_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def file_checksum(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def content_checksum(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class MarketDataStore:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            root = Path(__file__).resolve().parents[4] / "data" / "platform"
            root.mkdir(parents=True, exist_ok=True)
            db_path = root / "market_data_research.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def migrate(self) -> None:
        self._conn.executescript(MD_SCHEMA_SQL)
        now = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO md_meta(key, value, updated_at) VALUES(?,?,?)",
            ("schema_version", SCHEMA_VERSION, now),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO md_meta(key, value, updated_at) VALUES(?,?,?)",
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

    def executemany(self, sql: str, seq: list) -> None:
        self._conn.executemany(sql, seq)
        self._conn.commit()

    def query(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        cur = self._conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def query_one(self, sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

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
            """INSERT INTO md_audit(id, kind, actor, subject, detail_json, evidence_hash, created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (eid, kind, actor, subject, json.dumps(detail, default=str), eh, time.time()),
        )
        return eid

    def upsert_dataset(self, rec: dict[str, Any]) -> None:
        now = time.time()
        fields = [
            "dataset_id", "dataset_version", "name", "description", "provider", "source_type",
            "source_ref", "retrieval_ts", "ingestion_ts", "market", "exchange", "asset_class",
            "instrument_type", "symbol_namespace", "coverage_start", "coverage_end", "frequency",
            "timezone", "currency", "price_fields_json", "volume_fields_json",
            "corporate_action_coverage", "benchmark_coverage", "survivorship_json",
            "revision_policy", "licence_type", "redistribution_status", "commercial_use_status",
            "retention_restrictions", "citation_requirements", "checksum", "row_count",
            "file_size", "schema_version", "quality_status", "approval_status", "state",
            "limitations_json", "evidence_refs_json", "parent_dataset_id", "superseded_by",
            "file_path", "is_synthetic", "meta_json",
        ]
        for k in ("price_fields_json", "volume_fields_json", "survivorship_json",
                  "limitations_json", "evidence_refs_json", "meta_json"):
            if k in rec and not isinstance(rec[k], str):
                rec[k] = json.dumps(rec[k], default=str)
        rec.setdefault("created_at", now)
        rec["updated_at"] = now
        cols = fields + ["created_at", "updated_at"]
        placeholders = ",".join("?" * len(cols))
        col_names = ",".join(cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("dataset_id", "dataset_version", "created_at"))
        values = [rec.get(c) for c in cols]
        self.execute(
            f"""INSERT INTO md_datasets({col_names}) VALUES({placeholders})
                ON CONFLICT(dataset_id, dataset_version) DO UPDATE SET {updates}""",
            values,
        )

    def get_dataset(self, dataset_id: str, version: str | None = None) -> dict[str, Any] | None:
        if version:
            return self.query_one(
                "SELECT * FROM md_datasets WHERE dataset_id=? AND dataset_version=?",
                (dataset_id, version),
            )
        return self.query_one(
            "SELECT * FROM md_datasets WHERE dataset_id=? ORDER BY updated_at DESC LIMIT 1",
            (dataset_id,),
        )

    def list_datasets(self, state: str | None = None) -> list[dict[str, Any]]:
        if state:
            return self.query(
                "SELECT * FROM md_datasets WHERE state=? ORDER BY updated_at DESC",
                (state,),
            )
        return self.query("SELECT * FROM md_datasets ORDER BY updated_at DESC")

    def list_versions(self, dataset_id: str) -> list[dict[str, Any]]:
        return self.query(
            "SELECT * FROM md_datasets WHERE dataset_id=? ORDER BY created_at ASC",
            (dataset_id,),
        )
