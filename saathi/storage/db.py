"""Storage Database — SQLite state for Storage Intelligence (SES-019A Appendix A).

Only the tables M1 Step 1 needs are created here (watchdog events, jobs,
reports). The lifecycle-request and archive-log tables are added when their
owning components (Lifecycle Engine, Archive Manager) are built — per
Development Rule #1, we don't create schema ahead of the code that uses it.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS storage_watchdog_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,          -- notify, pause, emergency, resume
    disk_pct REAL NOT NULL,
    free_bytes INTEGER NOT NULL,
    triggered_at REAL NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS storage_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    product TEXT NOT NULL,
    status TEXT NOT NULL,              -- in_production, complete, failed, archived, postponed
    created_at REAL NOT NULL,
    completed_at REAL,
    predicted_peak_bytes INTEGER,
    actual_peak_bytes INTEGER,
    upload_verified INTEGER DEFAULT 0,
    cleanup_completed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS storage_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at REAL NOT NULL,
    ssd_free_bytes INTEGER,
    active_renders INTEGER,
    report_json TEXT
);

CREATE TABLE IF NOT EXISTS storage_cleanup_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_kind TEXT NOT NULL,            -- hourly, nightly, weekly, failed_job, manual
    started_at REAL NOT NULL,
    finished_at REAL,
    dry_run INTEGER DEFAULT 0,
    jobs_scanned INTEGER DEFAULT 0,
    files_deleted INTEGER DEFAULT 0,
    files_protected INTEGER DEFAULT 0,
    bytes_freed INTEGER DEFAULT 0,
    orphans_found INTEGER DEFAULT 0,
    bad_manifests INTEGER DEFAULT 0,
    ok INTEGER DEFAULT 1,
    detail_json TEXT
);
"""


class StorageDB:
    """Thin SQLite wrapper for storage state. Matches the codebase idiom
    (sqlite3.connect + executescript, cf. saathi/memory.py)."""

    def __init__(self, db_path: "str | Path"):
        self.path = str(db_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()

    # --- watchdog events -------------------------------------------------
    def record_watchdog_event(
        self, event_type: str, disk_pct: float, free_bytes: int, notes: str = ""
    ) -> int:
        cur = self.db.execute(
            "INSERT INTO storage_watchdog_events "
            "(event_type, disk_pct, free_bytes, triggered_at, notes) "
            "VALUES (?,?,?,?,?)",
            (event_type, disk_pct, free_bytes, time.time(), notes),
        )
        self.db.commit()
        return cur.lastrowid

    def recent_watchdog_events(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM storage_watchdog_events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def peak_disk_pct_since(self, since_ts: float) -> float:
        row = self.db.execute(
            "SELECT MAX(disk_pct) AS peak FROM storage_watchdog_events "
            "WHERE triggered_at >= ?",
            (since_ts,),
        ).fetchone()
        return row["peak"] if row and row["peak"] is not None else 0.0

    # --- cleanup audit log ----------------------------------------------
    def record_cleanup_run(self, **fields) -> int:
        cols = (
            "run_kind", "started_at", "finished_at", "dry_run", "jobs_scanned",
            "files_deleted", "files_protected", "bytes_freed", "orphans_found",
            "bad_manifests", "ok", "detail_json",
        )
        vals = [fields.get(c) for c in cols]
        placeholders = ",".join("?" for _ in cols)
        cur = self.db.execute(
            f"INSERT INTO storage_cleanup_log ({','.join(cols)}) VALUES ({placeholders})",
            vals,
        )
        self.db.commit()
        return cur.lastrowid

    def recent_cleanup_runs(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM storage_cleanup_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- jobs ------------------------------------------------------------
    def active_render_count(self) -> int:
        row = self.db.execute(
            "SELECT COUNT(*) AS n FROM storage_jobs WHERE status = 'in_production'"
        ).fetchone()
        return row["n"] if row else 0

    def close(self) -> None:
        self.db.close()
