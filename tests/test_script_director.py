"""Script Director — structured brief → structured episode document."""
from saathi.script_director import build_brief, write_script, ScriptDoc


def _plan():
    return {"day": 4, "topic": "Past Perfect Tense", "skill": "grammar",
            "phase": "Grammar Fundamentals", "episode": "EP-004",
            "objective": "Understand completed actions before another past event.",
            "avoid": ["Present Simple"], "character": {"name": "Mr. Yeti"}, "voice_tone": "friendly"}


def test_build_brief_from_plan():
    b = build_brief(_plan())
    assert b["topic"] == "Past Perfect Tense" and b["cefr"] == "B1"   # grammar → B1
    assert b["episode"] == "EP-004" and b["avoid"] == ["Present Simple"]
    assert b["platform"] == "youtube" and b["target_seconds"] > 0
    assert b["character"]["name"] == "Mr. Yeti"


def test_write_script_produces_structured_doc():
    doc = write_script(build_brief(_plan()))     # no LLM key in test → deterministic fallback
    assert isinstance(doc, ScriptDoc)
    assert doc.hook and doc.learning_goal and doc.cta
    assert len(doc.scenes) >= 4
    for s in doc.scenes:
        assert s["narration"] and s["visual"] and s["seconds"] > 0
    assert doc.seo["title"] and isinstance(doc.seo["tags"], list)
    assert doc.est_seconds == sum(s["seconds"] for s in doc.scenes)
    assert doc.thumbnail_ideas


def test_to_pipeline_script_shape():
    doc = write_script(build_brief(_plan()))
    ps = doc.to_pipeline_script()
    assert ps["hook"] and isinstance(ps["teaching"], list) and ps["cta"]
