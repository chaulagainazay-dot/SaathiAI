"""AI Lab — Production Intelligence, starting with the Prompt Registry.

The missing piece the CTO identified: prompts change, then nobody knows why or
whether they got better. This makes every prompt a versioned, measurable,
rollback-able asset — a shared service every project (HCG, PIELTS, Mr. Yeti,
Saathi itself) plugs into, instead of prompts living untracked in code.

    reg = default_registry()
    reg.register("studio.metadata", template, purpose="Video title+desc+SEO",
                 author="Claude Code", project="mr-yeti")     # → version N (active)
    text = reg.render("studio.metadata", topic="past perfect")  # active version, formatted
    reg.record_eval("studio.metadata", N, score=0.82, latency_ms=2400, cost=0.003, failures=12)
    reg.rollback("studio.metadata", 11)                        # redeploy an older version

Native: no external service. SQLite at ~/.saathi/ai_lab.db. Feeds /os and the
Executive dashboard. Next Production Intelligence services (Evaluation Center,
Dataset Manager, Workflow Editor) build on this substrate.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PromptVersion:
    name: str
    version: int
    template: str
    purpose: str = ""
    author: str = ""
    project: str = ""
    notes: str = ""
    active: bool = False
    created: float = 0.0
    # latest evaluation (if any)
    score: float | None = None
    latency_ms: int | None = None
    cost: float | None = None
    failures: int | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class PromptRegistry:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "ai_lab.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        c = sqlite3.connect(str(self.db_path)); c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS prompts(
                name TEXT, version INTEGER, template TEXT, purpose TEXT, author TEXT,
                project TEXT, notes TEXT, active INTEGER DEFAULT 0, created REAL,
                PRIMARY KEY(name, version))""")
            c.execute("""CREATE TABLE IF NOT EXISTS evals(
                name TEXT, version INTEGER, score REAL, latency_ms INTEGER, cost REAL,
                failures INTEGER, notes TEXT, created REAL)""")

    # ── write ──
    def register(self, name: str, template: str, *, purpose: str = "", author: str = "",
                 project: str = "", notes: str = "") -> int:
        """Create the next version of a prompt and make it the active one."""
        with self._conn() as c:
            row = c.execute("SELECT MAX(version) m FROM prompts WHERE name=?", (name,)).fetchone()
            version = (row["m"] or 0) + 1
            c.execute("UPDATE prompts SET active=0 WHERE name=?", (name,))
            c.execute("""INSERT INTO prompts(name,version,template,purpose,author,project,notes,active,created)
                VALUES(?,?,?,?,?,?,?,1,?)""",
                (name, version, template, purpose, author, project, notes, time.time()))
        return version

    def record_eval(self, name: str, version: int, *, score: float, latency_ms: int = 0,
                    cost: float = 0.0, failures: int = 0, notes: str = "") -> None:
        with self._conn() as c:
            c.execute("""INSERT INTO evals(name,version,score,latency_ms,cost,failures,notes,created)
                VALUES(?,?,?,?,?,?,?,?)""",
                (name, version, score, latency_ms, cost, failures, notes, time.time()))

    def rollback(self, name: str, version: int) -> bool:
        with self._conn() as c:
            hit = c.execute("SELECT 1 FROM prompts WHERE name=? AND version=?", (name, version)).fetchone()
            if not hit:
                return False
            c.execute("UPDATE prompts SET active=0 WHERE name=?", (name,))
            c.execute("UPDATE prompts SET active=1 WHERE name=? AND version=?", (name, version))
        return True

    # ── read ──
    def _latest_eval(self, c, name: str, version: int) -> dict | None:
        r = c.execute("""SELECT score,latency_ms,cost,failures FROM evals
            WHERE name=? AND version=? ORDER BY created DESC LIMIT 1""", (name, version)).fetchone()
        return dict(r) if r else None

    def _hydrate(self, c, row) -> PromptVersion:
        pv = PromptVersion(name=row["name"], version=row["version"], template=row["template"],
                           purpose=row["purpose"], author=row["author"], project=row["project"],
                           notes=row["notes"], active=bool(row["active"]), created=row["created"])
        ev = self._latest_eval(c, pv.name, pv.version)
        if ev:
            pv.score, pv.latency_ms, pv.cost, pv.failures = (
                ev["score"], ev["latency_ms"], ev["cost"], ev["failures"])
        return pv

    def get(self, name: str, version: int | None = None) -> PromptVersion | None:
        with self._conn() as c:
            if version is None:
                row = c.execute("SELECT * FROM prompts WHERE name=? AND active=1", (name,)).fetchone()
            else:
                row = c.execute("SELECT * FROM prompts WHERE name=? AND version=?", (name, version)).fetchone()
            return self._hydrate(c, row) if row else None

    def active(self, name: str) -> PromptVersion | None:
        return self.get(name)

    def render(self, name: str, /, **vars) -> str:
        """Fetch the ACTIVE version and format it — so every use goes through the
        registry and is therefore versioned + measurable. `name` is positional-only
        so a template variable may itself be called {name}."""
        pv = self.active(name)
        if not pv:
            raise KeyError(f"no active prompt named {name!r}")
        return pv.template.format(**vars)

    def versions(self, name: str) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM prompts WHERE name=? ORDER BY version DESC", (name,)).fetchall()
            return [self._hydrate(c, r).as_dict() for r in rows]

    def leaderboard(self, name: str) -> list[dict]:
        """Versions ranked by latest eval score (unscored last)."""
        vs = self.versions(name)
        return sorted(vs, key=lambda v: (v["score"] is not None, v["score"] or 0), reverse=True)

    def catalog(self) -> list[dict]:
        """One row per prompt name: active version + best score — the dashboard view."""
        with self._conn() as c:
            names = [r["name"] for r in c.execute("SELECT DISTINCT name FROM prompts").fetchall()]
        out = []
        for n in names:
            act = self.active(n)
            vs = self.versions(n)
            scored = [v["score"] for v in vs if v["score"] is not None]
            out.append({"name": n, "project": act.project if act else "",
                        "active_version": act.version if act else None,
                        "versions": len(vs),
                        "active_score": act.score if act else None,
                        "best_score": max(scored) if scored else None})
        return sorted(out, key=lambda r: r["name"])


    def register_if_absent(self, name: str, template: str, **meta) -> int | None:
        """Idempotent seed — register only if this prompt name has no versions yet."""
        with self._conn() as c:
            if c.execute("SELECT 1 FROM prompts WHERE name=?", (name,)).fetchone():
                return None
        return self.register(name, template, **meta)

    def register_or_update(self, name: str, template: str, **meta) -> int | None:
        """Register a new version only if the active template differs — so updating
        a seeded prompt's text bumps the version, but restarts don't churn."""
        cur = self.active(name)
        if cur and cur.template == template:
            return None
        return self.register(name, template, **meta)


# real prompts already living in the codebase, brought under version control so
# every project starts with a populated, cross-project Prompt Library.
_SEED = [
    ("mr-yeti.metadata", "mr-yeti", "Video title + description + SEO from a topic",
     'Create a Mr. Yeti IELTS video plan for: {topic}. Reply ONLY as JSON: '
     '{{"title","description","seo_tags":[],"hook","teaching":[],"examples","cta"}}'),
    ("mr-yeti.creative-director", "mr-yeti", "Topic+script → directed scene brief",
     "You are the creative director for a Mr. Yeti IELTS explainer about '{topic}'. "
     'Reply ONLY as JSON with style, voice_tone, music_mood, camera, and 4-6 scenes.'),
    ("pielts.writing-eval", "pielts", "Band prediction + feedback for a Task 2 essay",
     "Evaluate this IELTS Task 2 essay for band score (grammar, vocabulary, coherence, "
     "task response). Essay: {essay}. Reply with band + specific feedback."),
    ("hcg.signal", "hcg", "Detect swing opportunities from market data",
     "Analyse this market data for a swing-trade signal (signals only, no auto-trading): "
     "{market}. Reply with signal, confidence, and reasoning."),
    ("agency.research", "agency", "Research a client company → full strategy + roadmap",
     "You are a senior agency strategist. Research this company and produce a complete "
     "plan.\n{brief}\nReply ONLY as JSON with this exact shape:\n"
     '{{"research":{{"company_overview","strengths":[],"areas_to_improve":[],'
     '"competitors":[],"market_opportunity":[],"positioning"}},'
     '"strategy":{{"direction","content_ideas":[],"marketing_plan","next_steps":[],'
     '"channels":[{{"name","why"}}],'
     '"roadmap":[{{"phase","focus","timeframe","items":[]}}]}}}}\n'
     "Give 3-5 strengths, 3-5 areas_to_improve, 4-5 competitors, 3-5 market_opportunity, "
     "5-7 channels, and a 5-phase roadmap (Foundation, Visibility, Engagement, Growth, Scaling)."),
]


def seed_defaults(reg: "PromptRegistry | None" = None) -> int:
    reg = reg or default_registry()
    n = 0
    for name, project, purpose, template in _SEED:
        if reg.register_or_update(name, template, purpose=purpose, author="Claude Code",
                                  project=project) is not None:
            n += 1
    return n


_default = None
def default_registry() -> PromptRegistry:
    global _default
    if _default is None:
        _default = PromptRegistry()
    return _default
