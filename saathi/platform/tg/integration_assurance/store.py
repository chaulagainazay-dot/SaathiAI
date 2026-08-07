"""SQLite store for M232–M239 integration assurance. Planning only."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from saathi.platform.tg.integration_assurance.models import ENGINE_VERSION, SCHEMA_VERSION
from saathi.platform.tg.integration_assurance.schema import IA_SCHEMA_SQL


def _uid(prefix: str = "ia") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def evidence_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def file_fingerprint(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class AssuranceStore:
    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            root = Path(__file__).resolve().parents[4] / "data" / "platform"
            root.mkdir(parents=True, exist_ok=True)
            db_path = root / "integration_assurance.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def migrate(self) -> None:
        self._conn.executescript(IA_SCHEMA_SQL)
        now = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO ia_meta(key, value, updated_at) VALUES(?,?,?)",
            ("schema_version", SCHEMA_VERSION, now),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO ia_meta(key, value, updated_at) VALUES(?,?,?)",
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
        self.execute(
            """INSERT INTO ia_audit_events(id, kind, actor, subject, detail_json, evidence_hash, created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (
                eid, kind, actor, subject,
                json.dumps(detail), evidence_hash(detail), time.time(),
            ),
        )
        return eid

    def list_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.fetchall(
            "SELECT * FROM ia_audit_events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        for r in rows:
            r["detail"] = json.loads(r.pop("detail_json") or "{}")
        return rows


__all__ = ["AssuranceStore", "_uid", "evidence_hash", "file_fingerprint"]
