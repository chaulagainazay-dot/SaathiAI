"""Business Digital Twin — what the New Mission wizard actually builds.

A Mission is not a folder; it is an AI-managed representation of a real business.
On creation Saathi: (1) researches the live website, (2) stands up the departments
that business needs, (3) derives an honest Executive Briefing (health, strengths,
weaknesses, opportunities, ROI) from real signals — never invented numbers — and
(4) generates a 30-day roadmap. Every step is written to the Mission Timeline so
the business's history is captured from minute one.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from saathi.missions.templates import departments_for


# ── Twin artifact store (kept separate from the Mission row) ───────────────────
class TwinStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "mission_twin.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS twin(mission_id TEXT PRIMARY KEY, "
                      "departments TEXT, research TEXT, briefing TEXT, roadmap TEXT, updated REAL, "
                      "reports TEXT, confidence TEXT)")
            # migrate older tables that predate reports/confidence
            cols = {r[1] for r in c.execute("PRAGMA table_info(twin)").fetchall()}
            if "reports" not in cols:
                c.execute("ALTER TABLE twin ADD COLUMN reports TEXT")
            if "confidence" not in cols:
                c.execute("ALTER TABLE twin ADD COLUMN confidence TEXT")

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def save(self, mission_id: str, *, departments, research, briefing, roadmap,
             reports=None, confidence=None) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO twin(mission_id,departments,research,briefing,roadmap,"
                      "updated,reports,confidence) VALUES(?,?,?,?,?,?,?,?)",
                      (mission_id, json.dumps(departments), json.dumps(research),
                       json.dumps(briefing), json.dumps(roadmap), time.time(),
                       json.dumps(reports or {}), json.dumps(confidence or {})))

    def get(self, mission_id: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT departments,research,briefing,roadmap,updated,reports,confidence "
                          "FROM twin WHERE mission_id=?", (mission_id,)).fetchone()
        if not r:
            return None
        return {"departments": json.loads(r[0] or "[]"), "research": json.loads(r[1] or "{}"),
                "briefing": json.loads(r[2] or "{}"), "roadmap": json.loads(r[3] or "{}"),
                "updated": r[4], "reports": json.loads(r[5] or "{}") if len(r) > 5 else {},
                "confidence": json.loads(r[6] or "{}") if len(r) > 6 else {}}


_default = None
def default_store() -> TwinStore:
    global _default
    if _default is None:
        _default = TwinStore()
    return _default


# ── 30-day roadmap — driven by the briefing's weaknesses + template ───────────
def _roadmap(briefing: dict) -> dict:
    weak = briefing.get("weaknesses", [])
    w1 = ["Website audit", "Competitor research", "Connect accounts", "Brand review"]
    w2 = ["SEO fixes"] if any("SEO" in w or "meta" in w for w in weak) else ["Content plan"]
    w2 += ["Social calendar", "First AI content batch"]
    w3 = ["Automation setup", "CRM / enquiry capture", "Analytics wiring"]
    w4 = ["Optimise from evidence", "Evidence review", "Learning recommendations"]
    return {"Week 1": w1, "Week 2": w2, "Week 3": w3, "Week 4": w4}


def build(mission: dict, info: dict | None = None, *, research_timeout: float = 12.0) -> dict:
    """Create the digital twin for a Mission: research → departments → briefing → roadmap.
    Records timeline milestones. Returns the twin dict."""
    info = info or {}
    mid = mission.get("id", "")
    identity = mission.get("identity") or {}
    website = info.get("website") or identity.get("website", "")

    from saathi.missions.timeline import default_store as tl_store
    tl = tl_store()

    # 1. research the live site (real signals; safe if no site)
    research = {}
    if website:
        try:
            from saathi.tools.web_research import research_site
            research = research_site(website, timeout=research_timeout)
        except Exception as e:
            research = {"ok": False, "error": str(e)[:120]}
        tl.record(mid, "research", "Website research completed",
                  detail=research.get("title") or research.get("error", ""),
                  meta={"url": website, "ok": research.get("ok")})

    # 2. departments from the business type
    tpl, departments = departments_for(industry=info.get("industry") or identity.get("industry", ""),
                                       mission_type=mission.get("type", ""))
    tl.record(mid, "created", f"Departments provisioned ({tpl} template)",
              detail=", ".join(departments), meta={"template": tpl})

    # 3. Business Intelligence — Research 2.0 sub-directors + Executive Strategist
    info_full = dict(info)
    info_full.setdefault("name", mission.get("name", ""))
    info_full.setdefault("industry", info.get("industry") or identity.get("industry", ""))
    from saathi.missions.intel import analyze
    intel = analyze(info_full, research)
    briefing = intel["briefing"]
    conf = intel["confidence"]
    reports = intel["reports"]

    # 4. roadmap
    roadmap = {"30-day": _roadmap({"weaknesses": briefing.get("quick_wins", [])}),
               "90-day": briefing.get("plan_90", {})}

    tl.record(mid, "research", "Business intelligence completed",
              detail=f"SEO {reports['seo'].get('score', 0)}/100 · "
                     f"confidence {int(conf['overall']*100)}% · "
                     f"{len(briefing['top_opportunities'])} opportunities")
    tl.record(mid, "milestone", "Executive briefing generated",
              detail=f"Health {int(briefing['health']*100)}% · Confidence {int(conf['overall']*100)}%")

    twin = {"template": tpl, "departments": departments, "research": research,
            "briefing": briefing, "roadmap": roadmap, "reports": reports, "confidence": conf}
    default_store().save(mid, departments=departments, research=research, briefing=briefing,
                         roadmap=roadmap, reports=reports, confidence=conf)
    return twin
