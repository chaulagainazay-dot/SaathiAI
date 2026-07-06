"""Mission Knowledge Graph — Business Memory: nodes, coverage, populate from twin."""
import tempfile, os
from saathi.missions.knowledge import KnowledgeGraph, populate_from_twin, NODE_TYPES


def _g():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return KnowledgeGraph(p)


def _twin():
    return {"template": "travel",
            "research": {"ok": True, "url": "https://acme.com", "title": "Acme",
                         "socials": {"instagram": "i", "facebook": "f"}},
            "reports": {"company": {"overview": "tours"}, "seo": {"score": 50},
                        "competitors": {"competitors": ["Rival A", "Rival B"]}},
            "briefing": {"top_opportunities": ["SEO", "Reels"], "top_risks": ["Weak SEO"]}}


def test_upsert_is_deduped_per_type_key():
    g = _g()
    g.upsert("M1", "company", "company", label="Acme", data={"industry": "travel"})
    g.upsert("M1", "company", "company", label="Acme Inc", data={"industry": "travel", "country": "NP"})
    comps = g.nodes("M1", node_type="company")
    assert len(comps) == 1                               # same type+key → one node
    assert comps[0]["data"]["country"] == "NP" and comps[0]["label"] == "Acme Inc"


def test_unknown_type_falls_back_and_context_groups():
    g = _g()
    g.upsert("M1", "not_a_type", "x", data={"a": 1})
    assert g.nodes("M1", node_type="asset")              # coerced to asset
    g.upsert("M1", "website", "website", data={"url": "u"})
    ctx = g.context("M1", ["website", "asset"])
    assert ctx["website"] and ctx["asset"]


def test_coverage_reflects_what_we_hold():
    g = _g()
    empty = g.coverage("M1")
    assert empty["overall"] == 0.0 and empty["node_count"] == 0
    g.upsert("M1", "company", "company", data={"industry": "x"})
    g.upsert("M1", "website", "website", data={"url": "u"})
    cov = g.coverage("M1")
    assert cov["categories"]["company"] == 1.0 and cov["categories"]["website"] == 1.0
    assert cov["categories"]["revenue"] == 0.0          # not held yet → honest
    assert 0 < cov["overall"] < 1.0


def test_thin_node_scores_half():
    g = _g()
    g.upsert("M1", "company", "company", data={})        # present but no data
    assert g.coverage("M1")["categories"]["company"] == 0.5


def test_populate_from_twin_writes_memory():
    g = _g()
    mission = {"id": "MID", "name": "Acme Travel", "type": "client",
               "identity": {"industry": "Travel agency", "website": "https://acme.com"}}
    n = populate_from_twin(mission, _twin(), graph=g)
    assert n >= 6
    assert g.nodes("MID", node_type="company")
    assert len(g.nodes("MID", node_type="social_channel")) == 2
    assert len(g.nodes("MID", node_type="competitor")) == 2   # real competitors written
    cov = g.coverage("MID")
    assert cov["categories"]["company"] == 1.0 and cov["categories"]["competitor"] == 1.0
    assert cov["overall"] > 0.3
