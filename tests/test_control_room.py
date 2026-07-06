"""AI Studio OS — Control Room report assembler."""
from saathi.studio_control_room import report, STAGES, _confidence, _director_health


def test_report_has_full_pipeline_spine():
    r = report()
    names = [s["stage"] for s in r["stages"]]
    assert names == STAGES                              # every stage present, in order
    assert r["episode"] and "topic" in r


def test_confidence_is_completeness_not_fabricated():
    # all required script fields filled → 1.0; half filled → 0.5
    full = {"hook": "h", "scenes": [1], "cta": "c", "seo": {"title": "t"}}
    half = {"hook": "h", "scenes": [1]}
    assert _confidence("script", full) == 1.0
    assert _confidence("script", half) == 0.5
    assert _confidence("script", {}) == 0.0


def test_director_health_roster():
    d = _director_health()
    assert d["total"] == 7
    names = {x["name"] for x in d["roster"]}
    assert {"research", "creative", "script", "storyboard", "render", "publishing"} <= names
    # built-in directors route → healthy
    assert d["healthy"] >= 6


def test_report_rolls_up_cost_and_confidence():
    r = report()
    assert r["cost_total"] >= 0
    assert 0.0 <= r["confidence_overall"] <= 1.0
    assert r["health"]["directors"].endswith("/7")
    assert "episodes" in r["health"]


def test_publish_targets_surface():
    r = report()
    # ready episodes carry a publishing package; targets is a (possibly empty) list
    assert isinstance(r["publish_targets"], list)
    assert isinstance(r["memory"]["recent"], list)
