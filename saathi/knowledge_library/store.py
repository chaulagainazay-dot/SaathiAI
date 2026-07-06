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

SOURCE_TYPES = ("book", "github", "paper", "doc", "sop", "benchmark", "tutorial", "note",
                "gov", "blog", "youtube", "reddit", "ai_notes")
DIFFICULTY = ("beginner", "intermediate", "advanced")

# lifecycle: imported → parsed → summarized → extracted → reviewed → director_ready → archived
STATUSES = ("imported", "parsed", "summarized", "extracted", "reviewed", "director_ready", "archived")

# default trust (1-5 stars) by source type — not every source deserves equal trust
_DEFAULT_TRUST = {
    "doc": 5, "book": 5, "gov": 5, "paper": 5, "sop": 5, "benchmark": 4,
    "github": 4, "tutorial": 3, "blog": 3, "youtube": 3, "reddit": 2, "ai_notes": 1, "note": 2,
}


def default_trust(source_type: str) -> int:
    return _DEFAULT_TRUST.get(source_type, 3)


_COLUMNS = ["id", "title", "author", "url", "license", "category", "source_type", "difficulty",
            "summary", "tags", "related_directors", "key_lessons", "quality", "trust", "status",
            "director_ratings", "influence", "added", "updated"]
_JSON = {"tags", "related_directors", "key_lessons", "director_ratings"}


class LibraryStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "knowledge_library.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            def coltype(col):
                if col in ("added", "updated", "quality"):
                    return "REAL"
                if col in ("trust", "influence"):
                    return "INTEGER"
                return "TEXT"
            cols = ", ".join(f"{col} {coltype(col)}" for col in _COLUMNS)
            c.execute(f"CREATE TABLE IF NOT EXISTS source({cols}, PRIMARY KEY(id))")
            c.execute("CREATE INDEX IF NOT EXISTS idx_src_cat ON source(category)")
            # migrate older tables that predate trust/status/ratings/influence
            have = {r[1] for r in c.execute("PRAGMA table_info(source)").fetchall()}
            for col, dflt in (("trust", "3"), ("status", "'summarized'"),
                              ("director_ratings", "'{}'"), ("influence", "0")):
                if col not in have:
                    c.execute(f"ALTER TABLE source ADD COLUMN {col} {'INTEGER' if col in ('trust','influence') else 'TEXT'} DEFAULT {dflt}")

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def add(self, *, title: str, url: str = "", author: str = "", license: str = "",
            category: str = "", source_type: str = "note", difficulty: str = "intermediate",
            summary: str = "", tags: list | None = None, related_directors: list | None = None,
            key_lessons: list | None = None, quality: float = 0.0, trust: int = 0,
            status: str = "summarized", director_ratings: dict | None = None) -> dict:
        # dedupe by url (or title when no url); merge — re-import never erases data
        existing = self.find(url=url, title=title)
        sid = existing["id"] if existing else uuid.uuid4().hex[:16]
        added = existing["added"] if existing else time.time()
        stype = source_type if source_type in SOURCE_TYPES else "note"
        influence = existing["influence"] if existing else 0
        if existing:
            author = author or existing["author"]
            license = license or existing["license"]
            category = category or existing["category"]
            summary = summary or existing["summary"]
            tags = tags or existing["tags"]
            related_directors = related_directors or existing["related_directors"]
            key_lessons = key_lessons or existing["key_lessons"]
            quality = quality or existing["quality"]
            trust = trust or existing.get("trust") or default_trust(stype)
            status = status if status != "summarized" else existing.get("status", "summarized")
            director_ratings = director_ratings or existing.get("director_ratings") or {}
        else:
            trust = trust or default_trust(stype)
            director_ratings = director_ratings or {}
        row = (sid, title, author, url, license, category, stype,
               difficulty if difficulty in DIFFICULTY else "intermediate", summary,
               json.dumps(tags or []), json.dumps(related_directors or []),
               json.dumps(key_lessons or []), float(quality), int(trust),
               status if status in STATUSES else "summarized",
               json.dumps(director_ratings or {}), int(influence), added, time.time())
        with self._conn() as c:
            c.execute(f"INSERT OR REPLACE INTO source({','.join(_COLUMNS)}) "
                      f"VALUES({','.join('?'*len(_COLUMNS))})", row)
        return self.get(sid)

    def set_status(self, sid: str, status: str) -> bool:
        if status not in STATUSES:
            return False
        with self._conn() as c:
            return c.execute("UPDATE source SET status=?, updated=? WHERE id=?",
                             (status, time.time(), sid)).rowcount > 0

    def set_trust(self, sid: str, trust: int) -> bool:
        with self._conn() as c:
            return c.execute("UPDATE source SET trust=?, updated=? WHERE id=?",
                             (max(1, min(5, int(trust))), time.time(), sid)).rowcount > 0

    def rate_director(self, sid: str, director: str, stars: int) -> bool:
        s = self.get(sid)
        if not s:
            return False
        ratings = s["director_ratings"] if isinstance(s["director_ratings"], dict) else {}
        ratings[director] = max(1, min(5, int(stars)))
        with self._conn() as c:
            return c.execute("UPDATE source SET director_ratings=?, updated=? WHERE id=?",
                             (json.dumps(ratings), time.time(), sid)).rowcount > 0

    def record_influence(self, sid: str) -> int:
        """Bump the 'influenced N reports' counter — institutional memory."""
        with self._conn() as c:
            c.execute("UPDATE source SET influence=COALESCE(influence,0)+1 WHERE id=?", (sid,))
        s = self.get(sid)
        return s["influence"] if s else 0

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
        # rank by relevance, then trust — Directors cite higher-quality sources first
        out.sort(key=lambda x: (-x[0], -(x[1].get("trust") or 0)))
        return [s for _, s in out[:limit]]

    def consult(self, query: str, *, director: str = "", limit: int = 5,
                record: bool = True) -> list[dict]:
        """Manual retrieval — a Director deliberately consults the Library. Returns the
        top cited sources (with trust) and bumps their influence counter."""
        hits = self.search(query, director=director, limit=limit)
        if record:
            for s in hits:
                self.record_influence(s["id"])
            hits = [self.get(s["id"]) for s in hits]   # return fresh (post-increment influence)
        return hits

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
        blank = {} if c == "director_ratings" else []
        try:
            d[c] = json.loads(d[c]) if d[c] else blank
        except Exception:
            d[c] = blank
    return d


_default = None
def default_store() -> LibraryStore:
    global _default
    if _default is None:
        _default = LibraryStore()
    return _default
