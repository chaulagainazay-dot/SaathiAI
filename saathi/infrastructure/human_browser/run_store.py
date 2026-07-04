"""RunStore — the browser flight recorder.

Every browser run (publish, test, login) is persisted: workflow, profile,
duration, outcome, the step timeline, and artifact references. This is the data
layer under Replay, the Automation Center timeline, and the health score — "if
YouTube changes tomorrow you don't guess, you replay yesterday."

SQLite-backed (persists across restarts); path injectable for tests.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path


class RunStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "automation_runs.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS runs(
                id TEXT PRIMARY KEY, workflow TEXT, profile TEXT, capability TEXT,
                title TEXT, ok INTEGER, error TEXT, video_url TEXT,
                duration_ms INTEGER, started REAL, created REAL,
                timeline TEXT, artifacts TEXT)""")
            c.execute("CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created)")

    def record(self, *, workflow: str = "", profile: str = "", capability: str = "",
               title: str = "", ok: bool = True, error: str = "", video_url: str = "",
               duration_ms: int = 0, started: float = 0.0,
               timeline: list | None = None, artifacts: dict | None = None) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._conn() as c:
            c.execute("""INSERT INTO runs(id,workflow,profile,capability,title,ok,error,
                         video_url,duration_ms,started,created,timeline,artifacts)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (run_id, workflow, profile, capability, title, 1 if ok else 0, error,
                       video_url, duration_ms, started or time.time(), time.time(),
                       json.dumps(timeline or []), json.dumps(artifacts or {})))
        return run_id

    def get(self, run_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["ok"] = bool(d["ok"])
        d["timeline"] = json.loads(d["timeline"] or "[]")
        d["artifacts"] = json.loads(d["artifacts"] or "{}")
        return d

    def list(self, limit: int = 20) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("""SELECT id,workflow,profile,capability,title,ok,error,
                                video_url,duration_ms,created FROM runs
                                ORDER BY created DESC LIMIT ?""", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["ok"] = bool(d["ok"]); out.append(d)
        return out

    def stats(self, *, window_hours: int = 24, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        since = now - window_hours * 3600
        with self._conn() as c:
            rows = c.execute("SELECT ok,duration_ms,created FROM runs WHERE created>=?",
                             (since,)).fetchall()
            last_ok = c.execute("SELECT MAX(created) FROM runs WHERE ok=1").fetchone()[0]
        runs = len(rows)
        successes = sum(1 for r in rows if r["ok"])
        durs = [r["duration_ms"] for r in rows if r["ok"] and r["duration_ms"]]
        return {
            "runs": runs, "successes": successes, "failures": runs - successes,
            "success_rate": (successes / runs) if runs else 1.0,
            "avg_duration_ms": round(sum(durs) / len(durs)) if durs else 0,
            "last_success": last_ok,
        }


# process-wide default store
_default = None
def default_store() -> RunStore:
    global _default
    if _default is None:
        _default = RunStore()
    return _default
