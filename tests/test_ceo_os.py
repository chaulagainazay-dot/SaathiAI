"""Today's Operating System BFF — one aggregated, honest snapshot."""
from saathi.ceo_os import snapshot


def test_snapshot_has_all_sections():
    m = snapshot()
    assert set(m) == {"greeting", "dream", "rule", "automation", "learning", "revenue", "needs_you"}


def test_sections_are_well_formed():
    m = snapshot()
    assert m["greeting"].startswith("Good ")
    assert "score" in m["rule"] and m["rule"]["of"] == 4
    for k in ("health", "runs_today", "workflows", "agent_online"):
        assert k in m["automation"]
    for k in ("knowledge_added", "verified_improvements", "episodes_today"):
        assert k in m["learning"]
    assert isinstance(m["needs_you"], list)
    assert isinstance(m["revenue"], dict)


def test_never_crashes_with_empty_platform():
    # every source is wrapped; a snapshot must always return numbers, never raise
    m = snapshot()
    assert isinstance(m["automation"]["health"], int)
    assert isinstance(m["rule"]["score"], int)
