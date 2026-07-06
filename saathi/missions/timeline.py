"""Mission Timeline — the append-only historical memory of a Mission.

Records every important moment: mission created, website connected, research
completed, proposal sent, first video published, revenue milestone, major
decision. Never mutated — only appended. Years later this answers "show me
everything that happened for Surmount Travels between July and September" and
"what decisions led to the biggest SEO improvement". This is what turns a Mission
from a snapshot of current data into a continuously evolving business record.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

# milestone kinds — the vocabulary of a business's history
KINDS = ("created", "connected", "research", "meeting", "decision", "proposal",
         "launch", "publish", "milestone", "revenue", "learning", "note")

_COLUMNS = ["id", "mission_id", "timestamp", "kind", "title", "detail", "meta"]


class TimelineStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "mission_timeline.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def _init(self):
        cols = ", ".join(f"{c} {'REAL' if c == 'timestamp' else 'TEXT'}" for c in _COLUMNS)
        with self._conn() as c:
            c.execute(f"CREATE TABLE IF NOT EXISTS timeline({cols}, PRIMARY KEY(id))")
            c.execute("CREATE INDEX IF NOT EXISTS idx_tl ON timeline(mission_id, timestamp)")

    def record(self, mission_id: str, kind: str, title: str, *, detail: str = "",
               meta: dict | None = None, ts: float | None = None) -> str:
        rid = uuid.uuid4().hex[:16]
        with self._conn() as c:
            c.execute(f"INSERT INTO timeline({','.join(_COLUMNS)}) VALUES(?,?,?,?,?,?,?)",
                      (rid, mission_id, ts or time.time(), kind if kind in KINDS else "note",
                       title, detail, json.dumps(meta or {})))
        return rid

    def list(self, mission_id: str, *, since: float | None = None, until: float | None = None,
             kind: str | None = None, limit: int = 200) -> list[dict]:
        where, args = ["mission_id=?"], [mission_id]
        if since:
            where.append("timestamp>=?"); args.append(since)
        if until:
            where.append("timestamp<=?"); args.append(until)
        if kind:
            where.append("kind=?"); args.append(kind)
        sql = ("SELECT " + ",".join(_COLUMNS) + " FROM timeline WHERE " + " AND ".join(where)
               + " ORDER BY timestamp DESC LIMIT ?")
        args.append(limit)
        with self._conn() as c:
            rows = c.execute(sql, args).fetchall()
        out = []
        for r in rows:
            d = dict(zip(_COLUMNS, r))
            try:
                d["meta"] = json.loads(d["meta"]) if d["meta"] else {}
            except Exception:
                d["meta"] = {}
            out.append(d)
        return out


_default = None
def default_store() -> TimelineStore:
    global _default
    if _default is None:
        _default = TimelineStore()
    return _default
