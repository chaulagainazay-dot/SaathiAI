"""Business Intelligence — Research 2.0 sub-directors, Strategist, Confidence Score."""
from saathi.missions.intel import (website_audit, seo_report, competitor_report,
                                    social_report, confidence, strategist, analyze)


def _good_research():
    return {"ok": True, "url": "https://acme.com", "title": "Acme Travel",
            "description": "Best tours in Nepal", "headings": ["Tours", "About", "Contact"],
            "text": "x" * 900, "socials": {"instagram": "i", "facebook": "f"}}


def _bare_research():
    return {"ok": True, "url": "http://x.com", "title": "", "description": "",
            "headings": [], "text": "hi", "socials": {}}


def test_website_audit_scores_pass_rate():
    a = website_audit(_good_research())
    assert a["reachable"] and a["health"] > 0.8
    b = website_audit(_bare_research())
    assert b["health"] < a["health"]                      # bare site scores lower
    assert website_audit({"ok": False})["health"] == 0.0


def test_seo_report_is_onpage_and_deducts_for_gaps():
    good = seo_report(_good_research())
    assert good["gathered"] and good["score"] >= 80 and good["scope"] == "on-page"
    bad = seo_report(_bare_research())
    assert bad["score"] < good["score"]
    assert any("meta description" in i for i in bad["issues"])
    assert seo_report({"ok": False})["score"] == 0        # no signal → no fabricated score


def test_competitor_report_never_fabricates():
    r = competitor_report({"industry": "Travel"}, {})
    assert r["gathered"] is False and r["competitors"] == []   # honest: no source wired
    assert "not yet wired" in r["note"]
    named = competitor_report({"competitors": "A, B, C"}, {})
    assert named["count"] == 3 and named["gathered"]


def test_social_report_from_found_channels():
    s = social_report(_good_research())
    assert s["count"] == 2 and s["health"] > 0
    empty = social_report(_bare_research())
    assert empty["count"] == 0 and "instagram" in empty["missing"]


def test_confidence_measures_data_completeness_not_quality():
    good_reports = {"website": website_audit(_good_research()), "seo": seo_report(_good_research()),
                    "competitors": competitor_report({}, {}), "social": social_report(_good_research())}
    c1 = confidence(good_reports, {"industry": "Travel", "services": "tours", "goals": "grow", "target_market": "NP"})
    # a fresh client without docs/revenue/automation is NOT near 100% — honest
    assert c1["overall"] < 0.85
    assert c1["dimensions"]["documents"] == 0.0 and c1["dimensions"]["automation"] == 0.0
    assert c1["dimensions"]["website"] == 1.0
    # empty everything → very low confidence
    empty = {"website": website_audit({"ok": False}), "seo": seo_report({"ok": False}),
             "competitors": competitor_report({}, {}), "social": social_report({"ok": False})}
    assert confidence(empty, {})["overall"] < 0.15


def test_strategist_synthesizes_one_briefing():
    out = analyze({"name": "Acme", "industry": "Travel agency", "goals": "more bookings"}, _bare_research())
    b = out["briefing"]
    assert 0 <= b["health"] <= 1 and 0 <= b["confidence"] <= 1
    assert b["top_opportunities"] and b["quick_wins"]
    assert "Month 1" in b["plan_90"]
    assert "tour" in b["biggest_revenue_opportunity"].lower()
    assert set(out["reports"]) == {"company", "website", "seo", "competitors", "social"}
