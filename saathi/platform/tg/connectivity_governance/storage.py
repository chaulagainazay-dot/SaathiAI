"""Durable storage for connectivity governance — no credentials, no accounts, no orders."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from saathi.platform.tg.connectivity_governance.models import (
    ENGINE_VERSION,
    FORBIDDEN_SECRET_FIELDS,
    SCHEMA_VERSION,
)

CG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cg_meta (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cg_audit (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, actor TEXT NOT NULL,
  subject TEXT NOT NULL DEFAULT '', detail_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cg_charter (
  id TEXT PRIMARY KEY, version TEXT NOT NULL, payload_json TEXT NOT NULL,
  finalized INTEGER NOT NULL DEFAULT 1, evidence_hash TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cg_providers (
  provider_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL,
  governance_status TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cg_approvals (
  approval_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL,
  status TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cg_credential_refs (
  reference_id TEXT PRIMARY KEY, reference TEXT NOT NULL,
  state TEXT NOT NULL, payload_json TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cg_revocations (
  revocation_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cg_incidents (
  incident_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL,
  state TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cg_emergency (
  id TEXT PRIMARY KEY, active INTEGER NOT NULL, payload_json TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cg_threats (
  threat_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, severity TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cg_maturity (
  id TEXT PRIMARY KEY, state TEXT NOT NULL, payload_json TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cg_certifications (
  id TEXT PRIMARY KEY, verdict TEXT NOT NULL, result_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cg_authority_decisions (
  id TEXT PRIMARY KEY, capability TEXT NOT NULL, state TEXT NOT NULL,
  payload_json TEXT NOT NULL, created_at REAL NOT NULL
);
"""

# Columns that must never appear
FORBIDDEN_COLUMN_NAMES = FORBIDDEN_SECRET_FIELDS | frozenset({
    "api_key", "api_secret", "password", "secret", "token", "private_key",
    "access_token", "refresh_token", "oauth_code", "balance", "position",
    "order_id", "fill_id",
})


def evidence_hash(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _uid(prefix: str = "cg") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class GovernanceStore:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            root = Path(__file__).resolve().parents[4]
            data = root / "data" / "platform"
            data.mkdir(parents=True, exist_ok=True)
            db_path = data / "connectivity_governance.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(CG_SCHEMA_SQL)
        self._conn.execute(
            "INSERT OR REPLACE INTO cg_meta(key, value, updated_at) VALUES(?,?,?)",
            ("schema_version", SCHEMA_VERSION, time.time()),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO cg_meta(key, value, updated_at) VALUES(?,?,?)",
            ("engine_version", ENGINE_VERSION, time.time()),
        )
        self._conn.commit()

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        # Block credential-like column/field usage in SQL
        low = sql.lower()
        for bad in FORBIDDEN_COLUMN_NAMES:
            if bad in low and bad not in ("token",):  # allow 'token' only if not access_token etc.
                # more precise: reject if used as column assignment target for secrets
                if any(f in low for f in (
                    "api_key", "api_secret", "password", "private_key",
                    "access_token", "refresh_token", "bearer_token",
                    "client_secret", "secret_key",
                )):
                    raise ValueError(f"CREDENTIAL_FIELD_BLOCKED: {bad}")
        # Explicit block for known bad patterns
        for pattern in (
            "api_key", "api_secret", "password", "private_key",
            "access_token", "refresh_token", "oauth_code", "broker_password",
        ):
            if pattern in low:
                raise ValueError(f"CREDENTIAL_FIELD_BLOCKED: {pattern}")
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur

    def audit(self, kind: str, actor: str, subject: str = "", detail: dict | None = None) -> str:
        detail = detail or {}
        # never store secrets in audit
        for k in list(detail.keys()):
            if k.lower() in FORBIDDEN_SECRET_FIELDS:
                detail[k] = "[REDACTED]"
        aid = _uid("audit")
        eh = evidence_hash(detail)
        self.execute(
            "INSERT INTO cg_audit(id, kind, actor, subject, detail_json, evidence_hash, created_at) VALUES(?,?,?,?,?,?,?)",
            (aid, kind, actor, subject, json.dumps(detail, sort_keys=True, default=str), eh, time.time()),
        )
        return aid

    def save_json(self, table: str, id_col: str, id_val: str, payload: dict, **extra_cols) -> None:
        cols = [id_col, "payload_json"]
        vals: list[Any] = [id_val, json.dumps(payload, sort_keys=True, default=str)]
        placeholders = ["?", "?"]
        for k, v in extra_cols.items():
            cols.append(k)
            vals.append(v)
            placeholders.append("?")
        # upsert-style replace
        sql = f"INSERT OR REPLACE INTO {table}({', '.join(cols)}) VALUES({', '.join(placeholders)})"
        self.execute(sql, tuple(vals))

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        cur = self.execute(
            "SELECT id, kind, actor, subject, detail_json, evidence_hash, created_at FROM cg_audit ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = []
        for r in cur.fetchall():
            rows.append({
                "id": r["id"], "kind": r["kind"], "actor": r["actor"],
                "subject": r["subject"], "detail": json.loads(r["detail_json"]),
                "evidence_hash": r["evidence_hash"], "created_at": r["created_at"],
            })
        return rows

    def schema_scan(self) -> dict[str, Any]:
        cur = self.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
        tables = []
        bad = []
        for r in cur.fetchall():
            name, sql = r["name"], r["sql"] or ""
            tables.append(name)
            low = sql.lower()
            for f in ("api_key", "api_secret", "password", "private_key", "access_token", "refresh_token", "balance", "position"):
                if f in low and f" {f} " in f" {low} ":
                    bad.append({"table": name, "field": f})
        return {
            "ok": len(bad) == 0,
            "tables": tables,
            "forbidden_fields_found": bad,
            "raw_credentials_forbidden": True,
        }

    def close(self) -> None:
        self._conn.close()
