"""Seed the Skill Library with the reusable skills SaathiOS's Directors call.

Each skill has a clear interface (inputs → outputs) and an owner Director, but is
callable by any related Director. These map to capabilities already in the platform
(SEO, competitor research, proposals, IELTS band prediction) so the registry is
real from day one, not empty scaffolding.
"""
from __future__ import annotations

_SKILLS = [
    dict(slug="seo-audit", name="SEO Audit", owner_director="seo", category="Marketing",
         description="On-page SEO audit of a website: title/meta/headings/HTTPS/content depth → score + issues.",
         inputs=["website_url"], outputs=["seo_score", "issues", "quick_wins"],
         related_directors=["seo", "marketing", "research"], trust=5,
         prompt_template="Audit {website_url} for on-page SEO. Report score/100, issues, quick wins.",
         examples=["surmount-travels.com → 50/100, missing meta description"],
         evaluation="Compare recommended fixes against measured ranking change."),
    dict(slug="competitor-research", name="Competitor Research", owner_director="research", category="Business",
         description="Identify top competitors, their positioning, pricing, strengths and gaps.",
         inputs=["industry", "location", "known_competitors?"], outputs=["competitors", "positioning", "gaps"],
         related_directors=["research", "marketing", "sales"], trust=4,
         prompt_template="Research competitors for a {industry} business in {location}. List 3-5 with strengths/weaknesses.",
         evaluation="Accuracy vs a human market map."),
    dict(slug="keyword-research", name="Keyword Research", owner_director="seo", category="Marketing",
         description="Find high-intent keywords + content gaps for a business/topic.",
         inputs=["topic", "audience"], outputs=["keywords", "content_gaps"],
         related_directors=["seo", "creative", "publishing"], trust=4),
    dict(slug="proposal-writing", name="Proposal Writing", owner_director="sales", category="Sales",
         description="Turn a Mission twin into a client proposal (problems/solutions/pricing/ROI).",
         inputs=["mission_twin"], outputs=["proposal_package"],
         related_directors=["sales", "marketing"], trust=5,
         evaluation="Proposal acceptance rate."),
    dict(slug="band-predictor", name="IELTS Band Predictor", owner_director="writing_evaluator", category="IELTS",
         description="Predict an IELTS band from an essay + name the top correction areas.",
         inputs=["essay", "task_type"], outputs=["band", "corrections", "topic_weaknesses"],
         related_directors=["writing_evaluator", "curriculum", "learning"], trust=4,
         evaluation="Predicted band vs examiner band."),
    dict(slug="hook-writer", name="Hook Writer", owner_director="creative", category="Writing",
         description="Write scroll-stopping hooks for a video/episode from its objective + audience.",
         inputs=["objective", "audience"], outputs=["hooks"],
         related_directors=["creative", "script", "publishing"], trust=4,
         evaluation="A/B retention on the first 3 seconds."),
    dict(slug="menu-engineering", name="Menu Engineering", owner_director="menu_planner", category="Hospitality",
         description="Optimise a cafeteria menu for margin + waste using sales/waste data.",
         inputs=["menu", "sales", "waste"], outputs=["recommendations", "prep_adjustments"],
         related_directors=["menu_planner"], trust=4),
]


def seed_skills(store=None) -> int:
    from saathi.skills_library.store import default_store
    st = store or default_store()
    existing = {s["slug"] for s in st.list() if s}
    n = 0
    for sk in _SKILLS:
        if sk["slug"] not in existing:
            st.register(**sk); n += 1
    return n
