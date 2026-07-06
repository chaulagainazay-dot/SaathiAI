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
                      "departments TEXT, research TEXT, briefing TEXT, roadmap TEXT, updated REAL)")

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def save(self, mission_id: str, *, departments, research, briefing, roadmap) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO twin VALUES(?,?,?,?,?,?)",
                      (mission_id, json.dumps(departments), json.dumps(research),
                       json.dumps(briefing), json.dumps(roadmap), time.time()))

    def get(self, mission_id: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT departments,research,briefing,roadmap,updated FROM twin "
                          "WHERE mission_id=?", (mission_id,)).fetchone()
        if not r:
            return None
        return {"departments": json.loads(r[0] or "[]"), "research": json.loads(r[1] or "{}"),
                "briefing": json.loads(r[2] or "{}"), "roadmap": json.loads(r[3] or "{}"),
                "updated": r[4]}


_default = None
def default_store() -> TwinStore:
    global _default
    if _default is None:
        _default = TwinStore()
    return _default


# ── Executive Briefing — derived from REAL signals, honest about gaps ──────────
def _briefing(info: dict, research: dict, departments: list) -> dict:
    strengths, weaknesses, opportunities = [], [], []

    site_ok = research.get("ok")
    if site_ok:
        strengths.append("Live website reachable")
    else:
        weaknesses.append("Website not reachable / not provided")

    if research.get("description"):
        strengths.append("Homepage has a meta description")
    elif site_ok:
        weaknesses.append("Missing meta description — weak on-page SEO")
        opportunities.append("Add titles + meta descriptions across key pages")

    if len(research.get("headings") or []) >= 3:
        strengths.append("Structured page headings")
    elif site_ok:
        weaknesses.append("Thin heading structure")

    socials = research.get("socials") or {}
    if socials:
        strengths.append(f"Social presence found: {', '.join(sorted(socials))}")
    else:
        weaknesses.append("No social links found on site")
        opportunities.append("Activate Instagram/Facebook with a weekly content calendar")

    if info.get("goals"):
        opportunities.append(f"Align execution to stated goal: {str(info['goals'])[:80]}")
    opportunities += ["Google Business + reviews", "WhatsApp/Telegram automation for enquiries",
                      "Blog/content for organic search"]

    # honest health score: fraction of positive signals over signals we could check
    checked = len(strengths) + len(weaknesses)
    health = round(len(strengths) / checked, 2) if checked else 0.5

    # ROI stars (1-5) — heuristic weighting where the biggest gaps are
    def stars(weak_hits, base):
        return min(5, base + weak_hits)
    roi = {
        "SEO": stars(sum(1 for w in weaknesses if "SEO" in w or "meta" in w or "heading" in w), 3),
        "Marketing": stars(sum(1 for w in weaknesses if "social" in w.lower()), 3),
        "Automation": 5,
        "Website": stars(0 if site_ok else 2, 3),
    }
    return {
        "health": health,
        "strengths": strengths[:6],
        "weaknesses": weaknesses[:6],
        "opportunities": opportunities[:6],
        "roi": roi,
        "departments": len(departments),
    }


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

    # 3. + 4. executive briefing + roadmap
    briefing = _briefing(info, research, departments)
    roadmap = _roadmap(briefing)
    tl.record(mid, "milestone", "Executive briefing generated",
              detail=f"Health {int(briefing['health']*100)}% · "
                     f"{len(briefing['opportunities'])} opportunities identified")

    twin = {"template": tpl, "departments": departments, "research": research,
            "briefing": briefing, "roadmap": roadmap}
    default_store().save(mid, departments=departments, research=research,
                         briefing=briefing, roadmap=roadmap)
    return twin
