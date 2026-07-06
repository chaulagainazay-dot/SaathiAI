"""Content Memory — the studio remembers what it already made.

Fixes the blueprint's biggest weakness ("treats every video independently, no
memory"): records every published piece (topic, skill, curriculum day, vocab,
grammar) so the Planner and Script Writer avoid repetition and build on prior
lessons. SQLite; deterministic; feeds the Learning Engine later.
"""
from __future__ import annotations

import re
import sqlite3
import time
import uuid
from pathlib import Path


def _norm(topic: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", (topic or "").lower())).strip()


class ContentMemory:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "content_memory.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        c = sqlite3.connect(str(self.db_path)); c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS content(
                id TEXT PRIMARY KEY, topic TEXT, topic_norm TEXT, skill TEXT, day INTEGER,
                project_id TEXT, run_id TEXT, video_url TEXT, vocab TEXT, grammar TEXT, created REAL)""")

    def record(self, *, topic: str, skill: str = "", day: int = 0, project_id: str = "",
               run_id: str = "", video_url: str = "", vocab: list | None = None,
               grammar: list | None = None) -> str:
        import json
        rid = uuid.uuid4().hex[:12]
        with self._conn() as c:
            c.execute("""INSERT INTO content(id,topic,topic_norm,skill,day,project_id,run_id,video_url,vocab,grammar,created)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (rid, topic, _norm(topic), skill, int(day or 0), project_id, run_id, video_url,
                 json.dumps(vocab or []), json.dumps(grammar or []), time.time()))
        return rid

    def is_covered(self, topic: str) -> bool:
        n = _norm(topic)
        if not n:
            return False
        with self._conn() as c:
            return c.execute("SELECT 1 FROM content WHERE topic_norm=? LIMIT 1", (n,)).fetchone() is not None

    def recent_topics(self, limit: int = 20) -> list[str]:
        with self._conn() as c:
            return [r["topic"] for r in c.execute(
                "SELECT topic FROM content ORDER BY created DESC LIMIT ?", (limit,)).fetchall()]

    def skills_this_week(self, now: float | None = None) -> dict:
        now = now or time.time()
        with self._conn() as c:
            rows = c.execute("SELECT skill, COUNT(*) n FROM content WHERE created>=? GROUP BY skill",
                             (now - 7 * 86400,)).fetchall()
        return {r["skill"]: r["n"] for r in rows if r["skill"]}

    def count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) n FROM content").fetchone()["n"]


_default = None
def default_memory() -> ContentMemory:
    global _default
    if _default is None:
        _default = ContentMemory()
    return _default
