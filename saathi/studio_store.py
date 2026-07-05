"""StudioStore + Production Queue — the content factory's bird's-eye view.

Persists every StudioRun (topic, mode, status, confidence, cost, time, url) and
answers `queue_counts()` for the dashboard: how many runs are awaiting approval,
published, blocked, etc. SQLite; path injectable.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path


class StudioStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "studio_runs.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        c = sqlite3.connect(str(self.db_path)); c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS studio_runs(
                id TEXT PRIMARY KEY, topic TEXT, mode TEXT, status TEXT,
                confidence REAL, cost REAL, duration_ms INTEGER, video_url TEXT,
                failure TEXT, created REAL)""")

    def record(self, sr) -> str:
        import json
        rid = uuid.uuid4().hex[:12]
        with self._conn() as c:
            c.execute("""INSERT INTO studio_runs
                (id,topic,mode,status,confidence,cost,duration_ms,video_url,failure,created)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (rid, sr.topic, sr.mode, sr.status, sr.overall_confidence, round(sr.cost_total, 3),
                 sr.duration_ms, sr.video_url, json.dumps(sr.failure) if sr.failure else "", time.time()))
        return rid

    def recent(self, limit: int = 15) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM studio_runs ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def queue_counts(self) -> dict:
        # map internal statuses → the operator's production-queue lanes
        lanes = {"awaiting_approval": 0, "published": 0, "blocked": 0, "in_progress": 0}
        blocked = {"script_blocked", "gate_blocked", "publish_failed"}
        with self._conn() as c:
            for r in c.execute("SELECT status, COUNT(*) n FROM studio_runs GROUP BY status").fetchall():
                s, n = r["status"], r["n"]
                if s == "awaiting_approval":
                    lanes["awaiting_approval"] += n
                elif s == "published":
                    lanes["published"] += n
                elif s in blocked:
                    lanes["blocked"] += n
                else:
                    lanes["in_progress"] += n
        return lanes


_default = None
def default_store() -> StudioStore:
    global _default
    if _default is None:
        _default = StudioStore()
    return _default
