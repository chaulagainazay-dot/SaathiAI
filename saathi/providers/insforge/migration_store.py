"""Idempotency + execution ledger for InsForge migrations (local SQLite)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

DEFAULT_DIR = Path.home() / ".saathi" / "insforge_migrations"


class MigrationLedger:
    """Single-use claim store for migration fingerprints."""

    def __init__(self, db_path: Path | str | None = None):
        self.path = Path(db_path) if db_path else (DEFAULT_DIR / "ledger.sqlite")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS migration_exec (
                  fingerprint TEXT PRIMARY KEY,
                  idempotency_key TEXT NOT NULL,
                  status TEXT NOT NULL,
                  approval_id TEXT DEFAULT '',
                  environment TEXT DEFAULT '',
                  project_id TEXT DEFAULT '',
                  result_json TEXT DEFAULT '',
                  created_at REAL,
                  updated_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_mig_idem ON migration_exec(idempotency_key);
                """
            )
            self._conn.commit()

    def get(self, fingerprint: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM migration_exec WHERE fingerprint=?", (fingerprint,),
            ).fetchone()
            return dict(row) if row else None

    def claim(
        self,
        *,
        fingerprint: str,
        idempotency_key: str,
        approval_id: str,
        environment: str,
        project_id: str,
    ) -> tuple[bool, dict | None]:
        """Atomic claim. Returns (claimed_new, existing_row)."""
        now = time.time()
        with self._lock:
            existing = self.get(fingerprint)
            if existing:
                return False, existing
            try:
                self._conn.execute(
                    "INSERT INTO migration_exec(fingerprint,idempotency_key,status,"
                    "approval_id,environment,project_id,result_json,created_at,updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        fingerprint, idempotency_key, "in_progress", approval_id,
                        environment, project_id, "", now, now,
                    ),
                )
                self._conn.commit()
                return True, self.get(fingerprint)
            except sqlite3.IntegrityError:
                return False, self.get(fingerprint)

    def complete(self, fingerprint: str, status: str, result: dict) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE migration_exec SET status=?, result_json=?, updated_at=? "
                "WHERE fingerprint=?",
                (status, json.dumps(result)[:50_000], time.time(), fingerprint),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
