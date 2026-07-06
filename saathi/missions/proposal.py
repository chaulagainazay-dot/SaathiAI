"""Proposal Director — turns a Mission's Digital Twin into a client engagement.

Not a PDF generator: it produces a structured Proposal Package (12 sections) from
intelligence already collected — executive summary, current problems, opportunities,
recommended services, deliverables, timeline, pricing, ROI, KPIs, contract, invoice,
next meeting. One artifact drives the PDF, the quotation, the contract and the client
portal. On approval the Mission moves into execution — SaathiOS stops analysing and
starts delivering.

Honesty: pricing is a template ESTIMATE (flagged), ROI is a labelled PROJECTION, and
every problem/opportunity comes from the real briefing — nothing invented.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path


# ── Pricing templates (NPR estimates, per business type) ──────────────────────
_PRICING = {
    "travel": [("Website redesign", 60000), ("SEO (3 mo)", 45000), ("Social media mgmt", 30000),
               ("Booking + WhatsApp automation", 40000), ("Content factory", 25000)],
    "cafeteria": [("Inventory + waste system", 40000), ("Menu + POS optimisation", 30000),
                  ("Supplier automation", 25000), ("Reporting dashboard", 20000)],
    "education": [("Content studio setup", 50000), ("SEO + website", 40000),
                  ("Publishing automation", 30000), ("Community + growth", 25000)],
    "crypto": [("Signal engine setup", 60000), ("Telegram bot + mini app", 45000),
               ("Subscription billing", 30000)],
    "generic": [("Website + SEO", 55000), ("Social media mgmt", 30000),
                ("Marketing automation", 35000), ("Analytics + reporting", 20000)],
}
_TIERS = [("Starter", 0.5, "Core setup, 1 channel"),
          ("Professional", 1.0, "Full package, all channels"),
          ("Enterprise", 1.8, "Full package + priority + custom automation")]
CURRENCY = "NPR"


def _pricing(template: str) -> dict:
    items = _PRICING.get(template, _PRICING["generic"])
    subtotal = sum(a for _, a in items)
    tiers = [{"name": n, "price": int(subtotal * mult), "note": note} for n, mult, note in _TIERS]
    return {"currency": CURRENCY, "estimate": True, "line_items": [{"item": i, "price": a} for i, a in items],
            "subtotal": subtotal, "tiers": tiers,
            "note": "Indicative estimate from template — finalise after scoping call."}


def _services_from_departments(departments: list) -> list:
    ops = [d for d in (departments or []) if d not in ("Evidence", "Learning", "Finance", "Executive")]
    return ops[:8]


def _roi(briefing: dict, confidence: dict) -> dict:
    opp = len(briefing.get("top_opportunities", []))
    conf = confidence.get("overall", 0.0)
    # honest projection: qualitative + a confidence-scaled range, clearly labelled
    strength = "high" if opp >= 5 else "moderate"
    return {"projection": True, "confidence_in_projection": conf,
            "expected_leads": f"{strength} uplift once SEO + social + capture are live",
            "expected_revenue": briefing.get("biggest_revenue_opportunity", ""),
            "payback_period": "1–3 months (typical for this scope)",
            "caveat": f"Projection only — Mission confidence {int(conf*100)}%. "
                      f"Refined once real events + analytics connect."}


def _kpis(template: str) -> list:
    base = ["Website visitors", "Leads", "Conversion rate", "Revenue"]
    extra = {"travel": ["Bookings", "Instagram followers"],
             "cafeteria": ["Sales", "Food waste %", "Repeat customers"],
             "education": ["Lessons completed", "Subscribers", "Band improvement"],
             "crypto": ["Win rate", "Subscribers", "PnL"]}.get(template, ["Followers", "Engagement"])
    return base + extra


def build(mission: dict, twin: dict, *, pricing_template: str = "") -> dict:
    """Mission + Twin → Proposal Package (all 12 sections)."""
    twin = twin or {}
    briefing = twin.get("briefing", {})
    reports = twin.get("reports", {})
    confidence = twin.get("confidence", {})
    template = pricing_template or twin.get("template", "generic")
    depts = twin.get("departments", [])

    problems = list(briefing.get("top_risks", []))
    for iss in (reports.get("seo", {}) or {}).get("issues", [])[:3]:
        problems.append(f"SEO: {iss}")

    package = {
        "id": uuid.uuid4().hex[:16],
        "mission_id": mission.get("id", ""),
        "client": mission.get("name", ""),
        "created": time.time(),
        "sections": {
            "executive_summary": {
                "client": mission.get("name", ""),
                "industry": (mission.get("identity") or {}).get("industry", ""),
                "business_health": briefing.get("health", 0.0),
                "mission_confidence": confidence.get("overall", 0.0),
                "market_position": (reports.get("company", {}) or {}).get("overview", ""),
            },
            "current_problems": problems[:8],
            "opportunities": briefing.get("top_opportunities", []),
            "opportunity_roi": briefing.get("roi", {}),
            "recommended_services": _services_from_departments(depts),
            "deliverables": twin.get("roadmap", {}).get("90-day", {}),
            "timeline": twin.get("roadmap", {}),
            "pricing": _pricing(template),
            "roi": _roi(briefing, confidence),
            "kpis": _kpis(template),
            "contract": {"template": True,
                         "terms": ["Scope per Deliverables section", "Monthly retainer or one-off per Pricing",
                                   "50% advance, 50% on delivery", "1 month post-launch support",
                                   "Either party may terminate with 30 days notice"]},
            "invoice": {"template": True, "currency": CURRENCY,
                        "advance_pct": 50, "note": "Generated on acceptance of a pricing tier."},
            "next_meeting": {"purpose": "Scoping + finalise pricing tier",
                             "suggested": "Within 3 business days"},
        },
        "status": "draft",
    }
    return package


# ── Store ─────────────────────────────────────────────────────────────────────
class ProposalStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "proposals.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS proposal(id TEXT PRIMARY KEY, mission_id TEXT, "
                      "created REAL, status TEXT, package TEXT)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_prop ON proposal(mission_id, created)")

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def save(self, package: dict) -> str:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO proposal VALUES(?,?,?,?,?)",
                      (package["id"], package["mission_id"], package["created"],
                       package.get("status", "draft"), json.dumps(package)))
        return package["id"]

    def latest(self, mission_id: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT package FROM proposal WHERE mission_id=? ORDER BY created DESC LIMIT 1",
                          (mission_id,)).fetchone()
        return json.loads(r[0]) if r else None

    def get(self, proposal_id: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT package FROM proposal WHERE id=?", (proposal_id,)).fetchone()
        return json.loads(r[0]) if r else None

    def set_status(self, proposal_id: str, status: str) -> bool:
        pkg = self.get(proposal_id)
        if not pkg:
            return False
        pkg["status"] = status
        self.save(pkg)
        return True


_default = None
def default_store() -> ProposalStore:
    global _default
    if _default is None:
        _default = ProposalStore()
    return _default
