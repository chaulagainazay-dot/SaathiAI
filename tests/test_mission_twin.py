"""Business Digital Twin — timeline, department templates, twin builder."""
import tempfile, os
from saathi.missions.timeline import TimelineStore
from saathi.missions.templates import departments_for, guess_type
from saathi.missions import twin as twin_mod


def test_timeline_appends_and_lists_in_order():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    tl = TimelineStore(p)
    tl.record("M1", "created", "Mission created", ts=100)
    tl.record("M1", "research", "Website research completed", ts=200)
    tl.record("M2", "created", "Other mission", ts=150)
    items = tl.list("M1")
    assert [i["title"] for i in items] == ["Website research completed", "Mission created"]  # desc
    assert tl.list("M1", kind="research")[0]["kind"] == "research"
    assert len(tl.list("M2")) == 1                       # isolated per mission


def test_templates_by_type_and_industry_guess():
    assert guess_type("Travel agency") == "travel"
    assert guess_type("hospital canteen") == "cafeteria"
    assert guess_type("IELTS academy") == "education"
    tpl, depts = departments_for(industry="Travel agency")
    assert tpl == "travel" and "Sales" in depts and depts[-2:] == ["Evidence", "Learning"]
    tpl2, depts2 = departments_for(industry="unknowable widget")
    assert tpl2 == "generic" and "Evidence" in depts2   # always has the loop


def test_twin_build_from_info_no_website(monkeypatch):
    # isolate twin + timeline stores
    import saathi.missions.twin as tw
    import saathi.missions.timeline as tlm
    fd, tp = tempfile.mkstemp(suffix=".db"); os.close(fd)
    fd2, lp = tempfile.mkstemp(suffix=".db"); os.close(fd2)
    monkeypatch.setattr(tw, "_default", tw.TwinStore(tp))
    monkeypatch.setattr(tlm, "_default", tlm.TimelineStore(lp))
    monkeypatch.setattr(tlm, "default_store", lambda: tlm._default)

    mission = {"id": "MX", "name": "Grow Surmount Travels", "type": "client",
               "identity": {"industry": "Travel agency"}}
    twin = twin_mod.build(mission, {"industry": "Travel agency", "goals": "more bookings"})
    assert twin["template"] == "travel"
    assert "Sales" in twin["departments"]
    b = twin["briefing"]
    assert 0.0 <= b["health"] <= 1.0 and b["roi"]["Automation"] == 5
    assert "Week 1" in twin["roadmap"] and len(twin["roadmap"]["Week 1"]) >= 3
    # timeline captured the build
    kinds = {t["kind"] for t in tlm._default.list("MX")}
    assert {"created", "milestone"} <= kinds


def test_twin_briefing_flags_missing_signals(monkeypatch):
    import saathi.missions.twin as tw
    import saathi.missions.timeline as tlm
    fd, tp = tempfile.mkstemp(suffix=".db"); os.close(fd)
    fd2, lp = tempfile.mkstemp(suffix=".db"); os.close(fd2)
    monkeypatch.setattr(tw, "_default", tw.TwinStore(tp))
    monkeypatch.setattr(tlm, "_default", tlm.TimelineStore(lp))
    monkeypatch.setattr(tlm, "default_store", lambda: tlm._default)
    # no website → briefing must honestly flag it and still produce a roadmap
    twin = tw.build({"id": "MY", "name": "X", "type": "business", "identity": {}}, {})
    assert any("not reachable" in w or "not provided" in w for w in twin["briefing"]["weaknesses"])
    assert tw.default_store().get("MY")["briefing"]["health"] >= 0
