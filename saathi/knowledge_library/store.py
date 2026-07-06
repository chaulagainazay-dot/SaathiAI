"""Knowledge Library — SaathiOS's permanent learning source.

Company-wide (not per-Mission): books, GitHub repos, research papers, docs, SOPs,
benchmarks. Each source is ingested once, given rich metadata, and reused by every
Director across every Mission. This teaches the Directors; it never becomes a
runtime dependency. Research/Creative/Script/Learning Directors query this store
instead of re-reading a repo each time.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

SOURCE_TYPES = ("book", "github", "paper", "doc", "sop", "benchmark", "tutorial", "note")
DIFFICULTY = ("beginner", "intermediate", "advanced")

_COLUMNS = ["id", "title", "author", "url", "license", "category", "source_type", "difficulty",
            "summary", "tags", "related_directors", "key_lessons", "quality", "added", "updated"]
_JSON = {"tags", "related_directors", "key_lessons"}


class LibraryStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "knowledge_library.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            cols = ", ".join(f"{col} {'REAL' if col in ('added', 'updated', 'quality') else 'TEXT'}"
                             for col in _COLUMNS)
            c.execute(f"CREATE TABLE IF NOT EXISTS source({cols}, PRIMARY KEY(id))")
            c.execute("CREATE INDEX IF NOT EXISTS idx_src_cat ON source(category)")

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def add(self, *, title: str, url: str = "", author: str = "", license: str = "",
            category: str = "", source_type: str = "note", difficulty: str = "intermediate",
            summary: str = "", tags: list | None = None, related_directors: list | None = None,
            key_lessons: list | None = None, quality: float = 0.0) -> dict:
        # dedupe by url (or title when no url); merge — re-import never erases data
        existing = self.find(url=url, title=title)
        sid = existing["id"] if existing else uuid.uuid4().hex[:16]
        added = existing["added"] if existing else time.time()
        if existing:
            author = author or existing["author"]
            license = license or existing["license"]
            category = category or existing["category"]
            summary = summary or existing["summary"]
            tags = tags or existing["tags"]
            related_directors = related_directors or existing["related_directors"]
            key_lessons = key_lessons or existing["key_lessons"]
            quality = quality or existing["quality"]
        row = (sid, title, author, url, license, category,
               source_type if source_type in SOURCE_TYPES else "note",
               difficulty if difficulty in DIFFICULTY else "intermediate", summary,
               json.dumps(tags or []), json.dumps(related_directors or []),
               json.dumps(key_lessons or []), float(quality), added, time.time())
        with self._conn() as c:
            c.execute(f"INSERT OR REPLACE INTO source({','.join(_COLUMNS)}) "
                      f"VALUES({','.join('?'*len(_COLUMNS))})", row)
        return self.get(sid)

    def get(self, sid: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT " + ",".join(_COLUMNS) + " FROM source WHERE id=?", (sid,)).fetchone()
        return _row(r) if r else None

    def find(self, *, url: str = "", title: str = "") -> dict | None:
        with self._conn() as c:
            if url:
                r = c.execute("SELECT " + ",".join(_COLUMNS) + " FROM source WHERE url=?", (url,)).fetchone()
                if r:
                    return _row(r)
            if title:
                r = c.execute("SELECT " + ",".join(_COLUMNS) + " FROM source WHERE title=?", (title,)).fetchone()
                if r:
                    return _row(r)
        return None

    def list(self, *, category: str = "", limit: int = 200) -> list[dict]:
        sql = "SELECT " + ",".join(_COLUMNS) + " FROM source"
        args = []
        if category:
            sql += " WHERE category=?"; args.append(category)
        sql += " ORDER BY updated DESC LIMIT ?"; args.append(limit)
        with self._conn() as c:
            return [_row(r) for r in c.execute(sql, args).fetchall()]

    def search(self, query: str = "", *, tag: str = "", director: str = "",
               category: str = "", limit: int = 50) -> list[dict]:
        """Simple ranked text search over title/summary/tags/lessons + facet filters.
        This is what a Director calls: 'find planning strategies for multi-agent systems'."""
        q = (query or "").lower()
        out = []
        for s in self.list(limit=500):
            if category and s["category"] != category:
                continue
            if tag and tag.lower() not in [t.lower() for t in s["tags"]]:
                continue
            if director and director.lower() not in [d.lower() for d in s["related_directors"]]:
                continue
            hay = " ".join([s["title"], s["summary"], " ".join(s["tags"]),
                            " ".join(s["key_lessons"]), s["category"]]).lower()
            score = sum(hay.count(w) for w in q.split()) if q else 1
            if score > 0:
                out.append((score, s))
        out.sort(key=lambda x: -x[0])
        return [s for _, s in out[:limit]]

    def categories(self) -> dict:
        with self._conn() as c:
            rows = c.execute("SELECT category, COUNT(*) FROM source GROUP BY category").fetchall()
        return {(cat or "Uncategorised"): n for cat, n in rows}

    def delete(self, sid: str) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM source WHERE id=?", (sid,)).rowcount > 0


def _row(r) -> dict:
    d = dict(zip(_COLUMNS, r))
    for c in _JSON:
        try:
            d[c] = json.loads(d[c]) if d[c] else []
        except Exception:
            d[c] = []
    return d


_default = None
def default_store() -> LibraryStore:
    global _default
    if _default is None:
        _default = LibraryStore()
    return _default
