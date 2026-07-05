"""Client Intake — "Create New Project".

Capture everything about a company (via an in-app form, a shareable smart-form
link, or the Telegram bot), then AI-researches it and produces a strategy +
direction, organized into a project workspace.

    store = default_store()
    p = store.create({"company": {"name": "WanderOn Travels"}})   # → id + share token
    store.update(p["id"], {"goals": "...", "audience": "..."})
    research, strategy = research_project(store.get(p["id"]))       # AI research + plan
    store.set_output(p["id"], research, strategy)                  # status → ready

Flow: Capture → AI Research → Analyse (opportunities/gaps) → Strategy → Ready.
Reuses the Model Router; the research prompt is versioned in the AI Lab
(`agency.research`). SQLite; provider-gated with a deterministic fallback so it
never hard-fails.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import time
import uuid
from pathlib import Path

# the 7 capture steps (mirrors the wizard)
STEPS = ["company", "goals", "audience", "services", "budget", "uploads", "review"]
STATUSES = ("draft", "submitted", "researching", "ready")


class IntakeStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "client_projects.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        c = sqlite3.connect(str(self.db_path)); c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS projects(
                id TEXT PRIMARY KEY, token TEXT UNIQUE, name TEXT, status TEXT,
                data TEXT, research TEXT, strategy TEXT, created REAL, updated REAL)""")

    def _row(self, r) -> dict:
        return {"id": r["id"], "token": r["token"], "name": r["name"], "status": r["status"],
                "created": r["created"], "updated": r["updated"],
                "data": json.loads(r["data"] or "{}"),
                "research": json.loads(r["research"] or "null"),
                "strategy": json.loads(r["strategy"] or "null")}

    def create(self, data: dict | None = None) -> dict:
        pid = uuid.uuid4().hex[:10]
        token = secrets.token_urlsafe(9)
        data = data or {}
        name = ((data.get("company") or {}).get("name")) or "Untitled Project"
        now = time.time()
        with self._conn() as c:
            c.execute("""INSERT INTO projects(id,token,name,status,data,research,strategy,created,updated)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (pid, token, name, "draft", json.dumps(data), None, None, now, now))
        return self.get(pid)

    def get(self, pid: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return self._row(r) if r else None

    def get_by_token(self, token: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM projects WHERE token=?", (token,)).fetchone()
        return self._row(r) if r else None

    def list(self, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM projects ORDER BY updated DESC LIMIT ?", (limit,)).fetchall()
        return [self._row(r) for r in rows]

    def update(self, pid: str, patch: dict, *, status: str | None = None) -> dict | None:
        cur = self.get(pid)
        if not cur:
            return None
        data = {**cur["data"], **(patch or {})}
        name = ((data.get("company") or {}).get("name")) or cur["name"]
        st = status or cur["status"]
        with self._conn() as c:
            c.execute("UPDATE projects SET data=?, name=?, status=?, updated=? WHERE id=?",
                      (json.dumps(data), name, st, time.time(), pid))
        return self.get(pid)

    def set_output(self, pid: str, research: dict, strategy: dict) -> dict | None:
        with self._conn() as c:
            c.execute("UPDATE projects SET research=?, strategy=?, status='ready', updated=? WHERE id=?",
                      (json.dumps(research), json.dumps(strategy), time.time(), pid))
        return self.get(pid)

    def set_status(self, pid: str, status: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE projects SET status=?, updated=? WHERE id=?", (status, time.time(), pid))


# ── AI research + strategy ────────────────────────────────────────────────────
def _brief(data: dict) -> str:
    co = data.get("company") or {}
    parts = [f"Company: {co.get('name','?')}", f"Website: {co.get('website','')}",
             f"Industry: {co.get('industry','')}", f"About: {co.get('description','')}",
             f"Location: {co.get('location','')}", f"Goals: {data.get('goals','')}",
             f"Target audience: {data.get('audience','')}", f"Services: {data.get('services','')}",
             f"Budget/timeline: {data.get('budget','')}"]
    return " | ".join(p for p in parts if p.rsplit(": ", 1)[-1])


def research_project(project: dict) -> tuple[dict, dict]:
    """Return (research, strategy). Tries the Model Router with the versioned
    `agency.research` prompt; falls back to a deterministic plan."""
    data = project.get("data") or {}
    brief = _brief(data)
    co = (data.get("company") or {}).get("name", "the company")
    try:
        from saathi.infrastructure.llm import generate
        from saathi.infrastructure.model_router import ModelLabel
        try:
            from saathi.ai_lab import default_registry
            prompt = default_registry().render("agency.research", brief=brief)
        except Exception:
            prompt = (f"You are an agency strategist. Research this company and produce a plan.\n{brief}\n"
                      'Reply ONLY as JSON: {"research":{"summary","industry_overview",'
                      '"opportunities":[],"gaps":[],"competitors":[],"positioning"},'
                      '"strategy":{"direction","content_ideas":[],"marketing_plan","next_steps":[]}}')
        out = generate(ModelLabel.STANDARD, prompt, "Reply with ONLY JSON.", max_tokens=900).text
        obj = json.loads(out.strip().strip("`").replace("json", "", 1))
        r, s = obj.get("research") or {}, obj.get("strategy") or {}
        if r and s:
            return _shape_research(r), _shape_strategy(s)
    except Exception:
        pass
    return _fallback(co, brief)


def _shape_research(r: dict) -> dict:
    L = lambda k: r.get(k) if isinstance(r.get(k), list) else ([r[k]] if r.get(k) else [])
    return {"summary": r.get("summary", ""), "industry_overview": r.get("industry_overview", ""),
            "opportunities": L("opportunities"), "gaps": L("gaps"),
            "competitors": L("competitors"), "positioning": r.get("positioning", "")}


def _shape_strategy(s: dict) -> dict:
    L = lambda k: s.get(k) if isinstance(s.get(k), list) else ([s[k]] if s.get(k) else [])
    return {"direction": s.get("direction", ""), "content_ideas": L("content_ideas"),
            "marketing_plan": s.get("marketing_plan", ""), "next_steps": L("next_steps")}


def _fallback(name: str, brief: str) -> tuple[dict, dict]:
    research = {"summary": f"Intake captured for {name}. Configure an LLM provider for deep research.",
                "industry_overview": "", "opportunities": ["Build a consistent content presence",
                "Clarify the target audience", "Differentiate from competitors"],
                "gaps": ["No documented strategy yet"], "competitors": [], "positioning": ""}
    strategy = {"direction": f"Establish {name}'s positioning and a repeatable content engine.",
                "content_ideas": ["Founder story", "Customer results", "Educational how-to series"],
                "marketing_plan": "Start with one channel, publish consistently, measure, expand.",
                "next_steps": ["Confirm goals & audience", "Approve a content calendar", "Launch week 1"]}
    return research, strategy


_default = None
def default_store() -> IntakeStore:
    global _default
    if _default is None:
        _default = IntakeStore()
    return _default
