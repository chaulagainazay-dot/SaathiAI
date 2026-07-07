"""Skill Library — reusable skills any Director can find and call.

A Skill is a named, versioned capability (SEO Audit, Competitor Research, Band
Predictor) with a defined interface: inputs → outputs, a prompt template, examples,
tools, and an owner Director. Unlike a Research Library source (a document to learn
from), a Skill is an executable recipe — but this registry STORES and SEARCHES
skills; execution wires in later (Stage 2 rule: import → consume, not import →
execute). Directors query `by_director` / `search` to find the right skill, then
call it.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

_COLUMNS = ["id", "slug", "name", "owner_director", "category", "description", "inputs",
            "outputs", "prompt_template", "examples", "tools", "evaluation",
            "related_directors", "trust", "version", "status", "created"]
_JSON = {"inputs", "outputs", "examples", "tools", "related_directors"}
STATUSES = ("draft", "active", "deprecated")


class SkillStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "skills_library.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            cols = ", ".join(f"{col} {'INTEGER' if col in ('trust', 'version') else 'REAL' if col == 'created' else 'TEXT'}"
                             for col in _COLUMNS)
            c.execute(f"CREATE TABLE IF NOT EXISTS skill({cols}, PRIMARY KEY(id))")
            c.execute("CREATE INDEX IF NOT EXISTS idx_skill_slug ON skill(slug, version)")

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def register(self, *, slug: str, name: str, owner_director: str = "", category: str = "",
                 description: str = "", inputs: list | None = None, outputs: list | None = None,
                 prompt_template: str = "", examples: list | None = None, tools: list | None = None,
                 evaluation: str = "", related_directors: list | None = None, trust: int = 4) -> dict:
        with self._conn() as c:
            prev = c.execute("SELECT MAX(version) FROM skill WHERE slug=?", (slug,)).fetchone()[0]
            version = (prev or 0) + 1
            sid = uuid.uuid4().hex[:16]
            row = (sid, slug, name, owner_director, category, description,
                   json.dumps(inputs or []), json.dumps(outputs or []), prompt_template,
                   json.dumps(examples or []), json.dumps(tools or []), evaluation,
                   json.dumps(related_directors or ([owner_director] if owner_director else [])),
                   int(trust), version, "active", time.time())
            c.execute(f"INSERT INTO skill({','.join(_COLUMNS)}) VALUES({','.join('?'*len(_COLUMNS))})", row)
        return self.get(sid)

    def get(self, sid: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT " + ",".join(_COLUMNS) + " FROM skill WHERE id=?", (sid,)).fetchone()
        return _row(r) if r else None

    def get_by_slug(self, slug: str) -> dict | None:
        """Latest version of a skill by slug (what a Director calls)."""
        with self._conn() as c:
            r = c.execute("SELECT " + ",".join(_COLUMNS) + " FROM skill WHERE slug=? "
                          "ORDER BY version DESC LIMIT 1", (slug,)).fetchone()
        return _row(r) if r else None

    def list(self, *, category: str = "") -> list[dict]:
        # one row per slug (latest version)
        with self._conn() as c:
            slugs = [r[0] for r in c.execute(
                "SELECT slug FROM skill" + (" WHERE category=?" if category else "") +
                " GROUP BY slug ORDER BY name", ([category] if category else [])).fetchall()]
        return [self.get_by_slug(s) for s in slugs]

    def by_director(self, director: str) -> list[dict]:
        """Skills a Director owns or can call."""
        return [s for s in self.list()
                if s and (s["owner_director"] == director or director in s["related_directors"])]

    def search(self, query: str = "", *, director: str = "", category: str = "", limit: int = 30) -> list[dict]:
        q = (query or "").lower()
        out = []
        for s in self.list():
            if not s:
                continue
            if category and s["category"] != category:
                continue
            if director and s["owner_director"] != director and director not in s["related_directors"]:
                continue
            hay = " ".join([s["name"], s["description"], s["category"], " ".join(s["inputs"]),
                            " ".join(s["outputs"])]).lower()
            score = sum(hay.count(w) for w in q.split()) if q else 1
            if score > 0:
                out.append((score, s))
        out.sort(key=lambda x: (-x[0], -(x[1].get("trust") or 0)))
        return [s for _, s in out[:limit]]

    def categories(self) -> dict:
        with self._conn() as c:
            rows = c.execute("SELECT category, COUNT(DISTINCT slug) FROM skill GROUP BY category").fetchall()
        return {(cat or "Uncategorised"): n for cat, n in rows}


def _row(r) -> dict:
    d = dict(zip(_COLUMNS, r))
    for c in _JSON:
        try:
            d[c] = json.loads(d[c]) if d[c] else []
        except Exception:
            d[c] = []
    return d


_default = None
def default_store() -> SkillStore:
    global _default
    if _default is None:
        _default = SkillStore()
    return _default
