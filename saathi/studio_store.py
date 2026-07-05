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


# statuses that count as a blocked lane (a stage failed and needs attention)
_BLOCKED = {"script_blocked", "voice_failed", "assets_failed", "render_failed",
            "gate_blocked", "publish_failed"}


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
                failure TEXT, created REAL, run_id TEXT, stage_flags TEXT)""")
            # migrate older DBs that predate run_id / stage_flags
            cols = {r[1] for r in c.execute("PRAGMA table_info(studio_runs)").fetchall()}
            if "run_id" not in cols:
                c.execute("ALTER TABLE studio_runs ADD COLUMN run_id TEXT")
            if "stage_flags" not in cols:
                c.execute("ALTER TABLE studio_runs ADD COLUMN stage_flags TEXT")
            if "project_id" not in cols:
                c.execute("ALTER TABLE studio_runs ADD COLUMN project_id TEXT")

    def record(self, sr) -> str:
        import json
        rid = uuid.uuid4().hex[:12]
        with self._conn() as c:
            c.execute("""INSERT INTO studio_runs
                (id,topic,mode,status,confidence,cost,duration_ms,video_url,failure,created,run_id,stage_flags,project_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rid, sr.topic, sr.mode, sr.status, sr.overall_confidence, round(sr.cost_total, 3),
                 sr.duration_ms, sr.video_url, json.dumps(sr.failure) if sr.failure else "", time.time(),
                 getattr(sr, "run_id", ""), json.dumps(getattr(sr, "stage_flags", {}) or {}),
                 getattr(sr, "project_id", "")))
        return rid

    def record_payload(self, d: dict) -> str:
        """Record a run from a StudioRun.as_dict() payload — used when the Mac
        worker reports its runs to the VM so one dashboard reflects everything."""
        import json
        rid = uuid.uuid4().hex[:12]
        with self._conn() as c:
            c.execute("""INSERT INTO studio_runs
                (id,topic,mode,status,confidence,cost,duration_ms,video_url,failure,created,run_id,stage_flags,project_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rid, d.get("topic", ""), d.get("mode", ""), d.get("status", ""),
                 float(d.get("overall_confidence", 0) or 0), float(d.get("cost_total", 0) or 0),
                 int(d.get("duration_ms", 0) or 0), d.get("video_url", ""),
                 json.dumps(d["failure"]) if d.get("failure") else "", time.time(),
                 d.get("run_id", ""), json.dumps(d.get("stage_flags", {}) or {}), d.get("project_id", "")))
        return rid

    def recent(self, limit: int = 15) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM studio_runs ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def factory_kpis(self, now: float | None = None) -> dict:
        """Today's Factory — one-glance health from real rows since local midnight.
        Averages are over today's runs only; 0/None-safe so the card never crashes."""
        import time as _t
        now = now or _t.time()
        lt = _t.localtime(now)
        midnight = now - (lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec)
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM studio_runs WHERE created >= ?", (midnight,)).fetchall()]
        runs = len(rows)
        published = sum(1 for r in rows if r["status"] == "published")
        waiting = sum(1 for r in rows if r["status"] == "awaiting_approval")
        blocked = sum(1 for r in rows if r["status"] in _BLOCKED)
        avg = lambda k: round(sum(r[k] or 0 for r in rows) / runs, 3) if runs else 0
        latest_stages = {}
        if rows:
            import json
            newest = max(rows, key=lambda r: r["created"])
            try:
                latest_stages = json.loads(newest["stage_flags"] or "{}")
            except (json.JSONDecodeError, TypeError):
                latest_stages = {}
        return {
            "runs": runs, "published": published, "waiting_approval": waiting, "blocked": blocked,
            "avg_confidence": avg("confidence"),
            "avg_cost": avg("cost"),
            "avg_runtime_ms": int(avg("duration_ms")),
            "latest_stages": latest_stages,
        }

    def queue_counts(self) -> dict:
        # map internal statuses → the operator's production-queue lanes
        lanes = {"awaiting_approval": 0, "published": 0, "blocked": 0, "in_progress": 0}
        blocked = _BLOCKED
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
