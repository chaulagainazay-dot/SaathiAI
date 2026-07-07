"""Skill Library — reusable skill registry, versioning, Director lookup."""
import tempfile, os
from saathi.skills_library.store import SkillStore
from saathi.skills_library.seed import seed_skills


def _s():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return SkillStore(p)


def test_register_versions_per_slug():
    s = _s()
    v1 = s.register(slug="seo-audit", name="SEO Audit", owner_director="seo",
                    inputs=["website"], outputs=["score"])
    v2 = s.register(slug="seo-audit", name="SEO Audit", owner_director="seo", inputs=["website", "depth"])
    assert v1["version"] == 1 and v2["version"] == 2
    assert s.get_by_slug("seo-audit")["version"] == 2       # latest
    assert len(s.list()) == 1                                # one row per slug


def test_by_director_matches_owner_and_related():
    s = _s()
    s.register(slug="a", name="A", owner_director="seo", related_directors=["seo", "marketing"])
    s.register(slug="b", name="B", owner_director="research", related_directors=["research"])
    assert {x["slug"] for x in s.by_director("seo")} == {"a"}
    assert {x["slug"] for x in s.by_director("marketing")} == {"a"}   # related, not owner
    assert {x["slug"] for x in s.by_director("research")} == {"b"}


def test_search_by_query_and_facets():
    s = _s()
    s.register(slug="seo-audit", name="SEO Audit", owner_director="seo", category="Marketing",
               description="on-page seo score", inputs=["website"], trust=5)
    s.register(slug="band", name="Band Predictor", owner_director="writing_evaluator",
               category="IELTS", description="predict ielts band", trust=4)
    assert [x["slug"] for x in s.search("seo score")] == ["seo-audit"]
    assert len(s.search(category="IELTS")) == 1
    assert len(s.search(director="seo")) == 1


def test_seed_installs_reusable_skills():
    s = _s()
    assert seed_skills(s) >= 6
    assert seed_skills(s) == 0                               # idempotent
    slugs = {x["slug"] for x in s.list()}
    assert {"seo-audit", "competitor-research", "proposal-writing", "band-predictor"} <= slugs
    # a Director can find its skills
    seo_skills = s.by_director("seo")
    assert any(x["slug"] == "seo-audit" for x in seo_skills)
    assert s.categories()["IELTS"] >= 1
