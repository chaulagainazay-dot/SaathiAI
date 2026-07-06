"""Proposal Director — Proposal Package from a Mission twin + store."""
import tempfile, os
from saathi.missions.proposal import build, ProposalStore


def _mission():
    return {"id": "MID", "name": "Grow Surmount Travels", "identity": {"industry": "Travel agency"}}


def _twin():
    return {
        "template": "travel",
        "departments": ["Executive", "Sales", "Marketing", "SEO", "Website", "Evidence", "Learning", "Finance"],
        "briefing": {"health": 0.5, "top_risks": ["Weak on-page SEO (score 50/100)", "No social presence found"],
                     "top_opportunities": ["Google Business", "Instagram Reels", "WhatsApp automation",
                                           "SEO blog", "Facebook Ads"],
                     "roi": {"SEO": 5, "Marketing": 5}, "biggest_revenue_opportunity": "International tour packages"},
        "reports": {"company": {"overview": "Tours in Nepal"},
                    "seo": {"score": 50, "issues": ["Missing meta description"]}},
        "confidence": {"overall": 0.45},
        "roadmap": {"30-day": {"Week 1": ["Audit"]}, "90-day": {"Month 1": ["Website + SEO"]}},
    }


def test_package_has_all_core_sections():
    pkg = build(_mission(), _twin())
    s = pkg["sections"]
    for key in ("executive_summary", "current_problems", "opportunities", "recommended_services",
                "deliverables", "timeline", "pricing", "roi", "kpis", "contract", "invoice", "next_meeting"):
        assert key in s
    assert pkg["client"] == "Grow Surmount Travels" and pkg["status"] == "draft"


def test_sections_are_derived_from_twin_not_invented():
    s = build(_mission(), _twin())["sections"]
    assert s["executive_summary"]["mission_confidence"] == 0.45
    assert any("SEO" in p for p in s["current_problems"])            # from real risks + issues
    assert "Sales" in s["recommended_services"]                       # from departments (ops only)
    assert "Evidence" not in s["recommended_services"]               # loop depts excluded
    assert s["pricing"]["currency"] == "NPR" and s["pricing"]["estimate"] is True
    assert len(s["pricing"]["tiers"]) == 3                            # Starter/Professional/Enterprise


def test_roi_is_labelled_projection_with_confidence():
    roi = build(_mission(), _twin())["sections"]["roi"]
    assert roi["projection"] is True
    assert roi["confidence_in_projection"] == 0.45
    assert "Projection only" in roi["caveat"]                         # honest, not a promise


def test_pricing_template_falls_back_to_generic():
    pkg = build({"id": "X", "name": "Widget Co", "identity": {}}, {"template": "unknown_biz",
                "departments": ["Sales"], "briefing": {}, "reports": {}, "confidence": {}, "roadmap": {}})
    assert pkg["sections"]["pricing"]["line_items"]                   # generic template used


def test_store_save_latest_and_status():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    st = ProposalStore(p)
    pkg = build(_mission(), _twin())
    st.save(pkg)
    got = st.latest("MID")
    assert got and got["id"] == pkg["id"]
    assert st.set_status(pkg["id"], "accepted") is True
    assert st.get(pkg["id"])["status"] == "accepted"
