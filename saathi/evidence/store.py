"""Evidence Service — the storage core behind the universal schema.

Native, no external service. SQLite at ~/.saathi/evidence.db. One table, one
shape, every department. The CEO and the Learning layer query THIS. Adapters
(see adapters.py) convert native events into Evidence before they land here.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from saathi.evidence.schema import Evidence, COLUMNS, row_to_dict


class EvidenceStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "evidence.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        c = sqlite3.connect(str(self.db_path))
        return c

    def _init(self):
        cols = ", ".join(f"{c} {'REAL' if c in ('timestamp','cost','latency_ms','confidence') else 'TEXT'}"
                         for c in COLUMNS)
        with self._conn() as c:
            c.execute(f"CREATE TABLE IF NOT EXISTS evidence({cols}, PRIMARY KEY(id))")
            c.execute("CREATE INDEX IF NOT EXISTS idx_dept ON evidence(department, timestamp)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_episode ON evidence(episode)")

    def record(self, ev: Evidence) -> str:
        ph = ",".join("?" * len(COLUMNS))
        with self._conn() as c:
            c.execute(f"INSERT OR REPLACE INTO evidence({','.join(COLUMNS)}) VALUES({ph})", ev.to_row())
        return ev.id

    def record_many(self, evs: list[Evidence]) -> list[str]:
        return [self.record(e) for e in evs]

    def query(self, *, department: str | None = None, project: str | None = None,
              episode: str | None = None, since: float | None = None, limit: int = 50) -> list[dict]:
        where, args = [], []
        if department:
            where.append("department=?"); args.append(department)
        if project:
            where.append("project=?"); args.append(project)
        if episode:
            where.append("episode=?"); args.append(episode)
        if since:
            where.append("timestamp>=?"); args.append(since)
        sql = "SELECT " + ",".join(COLUMNS) + " FROM evidence"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY timestamp DESC LIMIT ?"; args.append(limit)
        with self._conn() as c:
            return [row_to_dict(r) for r in c.execute(sql, args).fetchall()]

    def count(self, *, department: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM evidence"
        args = []
        if department:
            sql += " WHERE department=?"; args.append(department)
        with self._conn() as c:
            return c.execute(sql, args).fetchone()[0]

    def stats(self, *, since: float | None = None) -> dict:
        """CEO roll-up: per-department counts, cost, avg confidence."""
        since = since if since is not None else 0
        with self._conn() as c:
            rows = c.execute(
                "SELECT department, COUNT(*) n, COALESCE(SUM(cost),0) cost, COALESCE(AVG(confidence),0) conf "
                "FROM evidence WHERE timestamp>=? GROUP BY department", (since,)).fetchall()
        by = {r[0]: {"count": r[1], "cost": round(r[2], 4), "avg_confidence": round(r[3], 3)} for r in rows}
        total = sum(v["count"] for v in by.values())
        return {"total": total, "departments": by}

    def episodes(self, department: str, *, limit: int = 20) -> list[dict]:
        """Latest one row per episode for a department (the dashboard feed)."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT " + ",".join(COLUMNS) + " FROM evidence WHERE department=? "
                "GROUP BY episode ORDER BY timestamp DESC LIMIT ?", (department, limit)).fetchall()
        return [row_to_dict(r) for r in rows]

    def attach_recommendation(self, evidence_id: str, recommendation: str) -> bool:
        with self._conn() as c:
            cur = c.execute("UPDATE evidence SET recommendation=? WHERE id=?", (recommendation, evidence_id))
            return cur.rowcount > 0


_default = None
def default_store() -> EvidenceStore:
    global _default
    if _default is None:
        _default = EvidenceStore()
    return _default
