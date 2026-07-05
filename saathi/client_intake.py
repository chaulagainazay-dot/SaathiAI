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
    """Return (research, strategy). Crawls the client's real website first (Stage 2),
    then the Model Router with the versioned `agency.research` prompt; deterministic
    fallback. The crawled site is attached to research['website']."""
    data = project.get("data") or {}
    brief = _brief(data)
    co = (data.get("company") or {}).get("name", "the company")

    # Stage 2 — live website + social research (grounds the report in the real site)
    site = None
    website = (data.get("company") or {}).get("website", "")
    if website:
        try:
            from saathi.tools.web_research import research_site, summarize
            site = research_site(website)
            brief = brief + "\n\n" + summarize(site)
        except Exception:
            site = None

    def _attach(research: dict) -> dict:
        if site is not None:
            research = {**research, "website": site,
                        "socials_found": list((site.get("socials") or {}).keys())}
        return research

    try:
        from saathi.infrastructure.llm import generate
        from saathi.infrastructure.model_router import ModelLabel
        try:
            from saathi.ai_lab import default_registry
            prompt = default_registry().render("agency.research", brief=brief)
        except Exception:
            prompt = (f"You are a senior agency strategist. Research this company.\n{brief}\n"
                      'Reply ONLY as JSON: {"research":{"company_overview","strengths":[],'
                      '"areas_to_improve":[],"competitors":[],"market_opportunity":[],"positioning"},'
                      '"strategy":{"direction","content_ideas":[],"marketing_plan","next_steps":[],'
                      '"channels":[{"name","why"}],"roadmap":[{"phase","focus","items":[]}]}}')
        out = generate(ModelLabel.STANDARD, prompt, "Reply with ONLY JSON.", max_tokens=900).text
        obj = json.loads(out.strip().strip("`").replace("json", "", 1))
        r, s = obj.get("research") or {}, obj.get("strategy") or {}
        if r and s:
            return _attach(_shape_research(r)), _shape_strategy(s)
    except Exception:
        pass
    fr, fs = _fallback(co, brief)
    return _attach(fr), fs


def _L(d: dict, k: str) -> list:
    v = d.get(k)
    return v if isinstance(v, list) else ([v] if v else [])


def _shape_research(r: dict) -> dict:
    overview = r.get("company_overview") or r.get("summary", "")
    return {"company_overview": overview, "summary": overview,
            "strengths": _L(r, "strengths"), "areas_to_improve": _L(r, "areas_to_improve"),
            "competitors": _L(r, "competitors"), "market_opportunity": _L(r, "market_opportunity"),
            "opportunities": _L(r, "opportunities") or _L(r, "market_opportunity"),
            "gaps": _L(r, "gaps") or _L(r, "areas_to_improve"),
            "positioning": r.get("positioning", "")}


def _shape_strategy(s: dict) -> dict:
    return {"direction": s.get("direction", ""), "content_ideas": _L(s, "content_ideas"),
            "marketing_plan": s.get("marketing_plan", ""), "next_steps": _L(s, "next_steps"),
            "channels": _L(s, "channels"), "roadmap": _L(s, "roadmap")}


def _fallback(name: str, brief: str) -> tuple[dict, dict]:
    research = _shape_research({
        "company_overview": f"Intake captured for {name}. Configure an LLM provider for deep research.",
        "strengths": ["Clear service offering", "Established contact details"],
        "areas_to_improve": ["Website SEO", "Content consistency", "Social engagement"],
        "competitors": ["Direct local competitors", "Larger national players", "Online marketplaces"],
        "market_opportunity": ["Under-served niche audiences", "Content-led demand", "Referral growth"],
        "positioning": ""})
    strategy = _shape_strategy({
        "direction": f"Establish {name}'s positioning and a repeatable content engine.",
        "content_ideas": ["Founder story", "Customer results", "Educational how-to series",
                          "Behind the scenes", "FAQ / myth-busting"],
        "marketing_plan": "Start with one channel, publish consistently, measure, expand.",
        "next_steps": ["Confirm goals & audience", "Approve a content calendar", "Launch week 1"],
        "channels": [{"name": "Instagram", "why": "Visual storytelling"},
                     {"name": "Facebook", "why": "Community & offers"},
                     {"name": "YouTube", "why": "Depth & discovery"},
                     {"name": "Google", "why": "High-intent search"}],
        "roadmap": [
            {"phase": "Foundation", "focus": "Weeks 1-2", "items": ["Website audit", "Branding consistency"]},
            {"phase": "Visibility", "focus": "Weeks 3-6", "items": ["SEO", "Content & blogging"]},
            {"phase": "Engagement", "focus": "Weeks 7-12", "items": ["Social campaigns", "Email setup"]},
            {"phase": "Growth", "focus": "Months 4-6", "items": ["Paid ads", "Retargeting", "CRM"]},
            {"phase": "Scaling", "focus": "Months 6+", "items": ["Conversion optimization", "New markets"]}]})
    return research, strategy


def studio_topics(project: dict) -> dict:
    """Turn a project's strategy into AI Studio input: content ideas → topics,
    tagged to the client, with the strategy direction as the guiding brief.
    This is the wire from Client Intake → AI Studio content production."""
    strat = project.get("strategy") or {}
    data = project.get("data") or {}
    co = (data.get("company") or {}).get("name") or project.get("name") or "Client"
    topics = [t for t in (strat.get("content_ideas") or []) if isinstance(t, str) and t.strip()]
    if not topics:  # no strategy yet — fall back to the company/services
        base = data.get("services") or data.get("goals") or co
        topics = [f"{co}: {base}"]
    return {"project_id": project.get("id"), "project": co,
            "direction": strat.get("direction", ""), "topics": topics}


_default = None
def default_store() -> IntakeStore:
    global _default
    if _default is None:
        _default = IntakeStore()
    return _default
