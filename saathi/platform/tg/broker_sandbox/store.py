"""SQLite store for broker sandbox architecture. PAPER ONLY."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from saathi.platform.tg.broker_sandbox.schema import SANDBOX_SCHEMA_SQL
from saathi.platform.tg.broker_sandbox.models import ENGINE_VERSION, SCHEMA_VERSION


def _uid(prefix: str = "bs") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class SandboxStore:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            root = Path(__file__).resolve().parents[4] / "data" / "platform"
            root.mkdir(parents=True, exist_ok=True)
            db_path = root / "broker_sandbox.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def migrate(self) -> None:
        self._conn.executescript(SANDBOX_SCHEMA_SQL)
        now = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO bs_meta(key, value, updated_at) VALUES(?,?,?)",
            ("schema_version", SCHEMA_VERSION, now),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO bs_meta(key, value, updated_at) VALUES(?,?,?)",
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
        self.execute(
            "INSERT INTO bs_audit_events(id, kind, actor, subject, detail_json, created_at) VALUES(?,?,?,?,?,?)",
            (eid, kind, actor, subject, json.dumps(detail or {}), time.time()),
        )
        return eid

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.fetchall(
            "SELECT * FROM bs_audit_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        for r in rows:
            r["detail"] = json.loads(r.pop("detail_json") or "{}")
        return rows


__all__ = ["SandboxStore", "_uid"]
