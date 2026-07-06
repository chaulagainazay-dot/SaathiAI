"""Business Intelligence — Research Director 2.0 + Executive Strategist.

The twin knows the company; this makes it understand the market. Specialized
sub-directors each produce a STRUCTURED report from real signals; the Executive
Strategist reads them all and writes one CEO briefing. Plus a Mission Confidence
Score — how complete our understanding of the business actually is (data
completeness, NOT business quality). A new client starts low and climbs as
research, documents, connected accounts, and real events accumulate.

Honesty rule (kept throughout SaathiOS): report only what real signals support.
We do not invent competitors or traffic numbers. When a dimension has no data
source yet, it says so and the Confidence Score reflects the gap.
"""
from __future__ import annotations


# ── Website Auditor ───────────────────────────────────────────────────────────
def website_audit(research: dict) -> dict:
    r = research or {}
    ok = bool(r.get("ok"))
    checks = []
    def chk(name, passed, note=""):
        checks.append({"check": name, "pass": bool(passed), "note": note})
    if ok:
        chk("Reachable", True)
        chk("Title tag", bool(r.get("title")), r.get("title", "")[:60])
        chk("Meta description", bool(r.get("description")))
        chk("Heading structure", len(r.get("headings") or []) >= 3,
            f"{len(r.get('headings') or [])} headings")
        chk("HTTPS", str(r.get("url", "")).startswith("https"))
        chk("Social links present", bool(r.get("socials")))
    else:
        chk("Reachable", False, r.get("error", "not provided"))
    passed = sum(1 for c in checks if c["pass"])
    total = len(checks) or 1
    return {"reachable": ok, "checks": checks, "passed": passed, "total": total,
            "health": round(passed / total, 2)}


# ── SEO Director (on-page only — labelled honestly) ───────────────────────────
def seo_report(research: dict) -> dict:
    r = research or {}
    if not r.get("ok"):
        return {"score": 0, "scope": "on-page", "gathered": False,
                "issues": ["Site not reachable — no SEO signal"], "wins": []}
    score, issues, wins = 100, [], []
    if not r.get("title"):
        score -= 20; issues.append("Missing <title>")
    if not r.get("description"):
        score -= 20; issues.append("Missing meta description")
    else:
        wins.append("Meta description present")
    if len(r.get("headings") or []) < 3:
        score -= 15; issues.append("Thin heading structure")
    else:
        wins.append("Structured headings")
    if not str(r.get("url", "")).startswith("https"):
        score -= 15; issues.append("Not served over HTTPS")
    if len((r.get("text") or "")) < 400:
        score -= 15; issues.append("Very little indexable text on homepage")
    return {"score": max(0, score), "scope": "on-page", "gathered": True,
            "issues": issues, "wins": wins}


# ── Competitor Director ───────────────────────────────────────────────────────
def competitor_report(info: dict, research: dict) -> dict:
    """Honest: no search API wired yet, so we do not invent competitors. We record
    what we CAN (industry + any competitors the client named) and flag the gap."""
    named = info.get("competitors") or []
    if isinstance(named, str):
        named = [c.strip() for c in named.split(",") if c.strip()]
    return {"gathered": bool(named), "competitors": named, "count": len(named),
            "industry": info.get("industry", ""),
            "note": "Client-provided only — automated competitor discovery not yet wired "
                    "(needs a search/SERP source)." if not named else "Client-provided competitors."}


# ── Social Media Director ─────────────────────────────────────────────────────
def social_report(research: dict) -> dict:
    socials = (research or {}).get("socials") or {}
    known = ("facebook", "instagram", "linkedin", "youtube", "tiktok", "twitter", "telegram")
    found = {k: v for k, v in socials.items() if k in known}
    health = round(len(found) / 3, 2) if found else 0.0   # ~3 active channels = healthy
    return {"gathered": bool(research and research.get("ok")), "channels": found,
            "count": len(found), "health": min(1.0, health),
            "missing": [c for c in ("facebook", "instagram") if c not in found]}


# ── Company Research ──────────────────────────────────────────────────────────
def company_report(info: dict, research: dict) -> dict:
    r = research or {}
    return {"name": info.get("name", ""), "industry": info.get("industry", ""),
            "country": info.get("country", ""), "target_market": info.get("target_market", ""),
            "overview": (r.get("description") or r.get("title") or "")[:240],
            "services": info.get("services", ""), "goals": info.get("goals", "")}


# ── Mission Confidence Score — how complete is our understanding? ──────────────
_WEIGHTS = {"website": 0.15, "seo": 0.15, "competitors": 0.15, "social": 0.15,
            "knowledge": 0.15, "documents": 0.10, "revenue": 0.075, "automation": 0.075}


def confidence(reports: dict, info: dict) -> dict:
    audit = reports.get("website", {})
    seo = reports.get("seo", {})
    comp = reports.get("competitors", {})
    social = reports.get("social", {})
    dims = {
        "website": 1.0 if audit.get("reachable") else 0.0,
        "seo": 1.0 if seo.get("gathered") else 0.0,
        "competitors": min(1.0, comp.get("count", 0) / 3) if comp.get("gathered") else 0.0,
        "social": 1.0 if social.get("gathered") and social.get("count") else (0.5 if social.get("gathered") else 0.0),
        "knowledge": round(sum(1 for k in ("industry", "services", "goals", "target_market")
                                if info.get(k)) / 4, 2),
        "documents": 0.0,                                  # none uploaded yet
        "revenue": 1.0 if info.get("monthly_revenue") or info.get("revenue") else 0.0,
        "automation": 0.0,                                 # none wired yet
    }
    overall = round(sum(dims[k] * _WEIGHTS[k] for k in _WEIGHTS), 2)
    return {"overall": overall, "dimensions": dims}


# ── Executive Strategist — reads every report, writes ONE CEO briefing ─────────
def strategist(reports: dict, info: dict, conf: dict) -> dict:
    audit = reports.get("website", {})
    seo = reports.get("seo", {})
    social = reports.get("social", {})

    risks, opportunities, quick_wins = [], [], []

    if not audit.get("reachable"):
        risks.append("No live website signal — the business is invisible to search")
    if seo.get("gathered") and seo.get("score", 100) < 60:
        risks.append(f"Weak on-page SEO (score {seo['score']}/100)")
    for issue in seo.get("issues", [])[:3]:
        quick_wins.append(f"Fix: {issue}")
    if social.get("gathered") and social.get("count", 0) == 0:
        risks.append("No social presence found — losing discovery + trust")
        opportunities.append("Launch Instagram/Facebook with a weekly content calendar")
    if social.get("missing"):
        opportunities.append(f"Activate: {', '.join(social['missing'])}")

    opportunities += ["Google Business Profile + reviews", "Reels/short-video content",
                      "WhatsApp/Telegram enquiry automation", "SEO blog for organic search"]

    # health = the website auditor's pass rate (real), separate from confidence
    health = audit.get("health", 0.0)

    # ROI stars weighted to biggest gaps
    roi = {
        "SEO": 5 if seo.get("score", 100) < 60 else 3,
        "Marketing": 5 if social.get("count", 0) == 0 else 4,
        "Google Business": 4,
        "Automation": 5,
        "Blog": 3,
    }
    plan_90 = {
        "Month 1": ["Website + SEO fixes", "Google Business + reviews", "Social calendar live"],
        "Month 2": ["Content factory (Reels + blog)", "Lead capture + CRM", "Analytics wired"],
        "Month 3": ["Automation of enquiries", "Evidence review", "Scale winning channels"],
    }
    return {
        "health": health,
        "confidence": conf.get("overall", 0.0),
        "top_risks": risks[:5],
        "top_opportunities": opportunities[:6],
        "quick_wins": quick_wins[:6],
        "roi": roi,
        "plan_90": plan_90,
        "biggest_revenue_opportunity": _revenue_bet(info),
    }


def _revenue_bet(info: dict) -> str:
    ind = (info.get("industry") or "").lower()
    if "travel" in ind:
        return "Higher-margin international / curated tour packages"
    if "canteen" in ind or "cafeteria" in ind or "food" in ind:
        return "Cut waste + introduce combo meals for higher per-cover profit"
    if "ielts" in ind or "education" in ind:
        return "Premium tier + cohort courses"
    if "crypto" in ind or "signal" in ind:
        return "Subscription tiers with proven win-rate reporting"
    return info.get("goals", "") or "Convert existing traffic into paid enquiries"


# ── Orchestrator: run all sub-directors → reports + confidence + briefing ─────
def analyze(info: dict, research: dict) -> dict:
    reports = {
        "company": company_report(info, research),
        "website": website_audit(research),
        "seo": seo_report(research),
        "competitors": competitor_report(info, research),
        "social": social_report(research),
    }
    conf = confidence(reports, info)
    briefing = strategist(reports, info, conf)
    return {"reports": reports, "confidence": conf, "briefing": briefing}
