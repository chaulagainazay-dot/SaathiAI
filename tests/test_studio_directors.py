"""AI Studio Departments/Directors — Research, Creative Brief, Studio Executive."""
from saathi.studio_directors import research_report, creative_brief, StudioExecutive, Production


def _plan():
    return {"day": 4, "topic": "Past Perfect Tense", "skill": "grammar",
            "phase": "Grammar Fundamentals", "episode": "EP-004",
            "objective": "Understand completed actions before another past event.",
            "avoid": [], "character": {"name": "Mr. Yeti", "style": "Pixar classroom"},
            "voice_tone": "friendly"}


def test_research_report_structured():          # no LLM key → deterministic fallback
    r = research_report(_plan())
    assert r["topic"] == "Past Perfect Tense" and r["summary"]
    assert r["key_facts"] and r["common_mistakes"] and r["examples"]
    assert r["competitor_angle"] and r["audience_questions"]


def test_creative_brief_structured():
    r = research_report(_plan())
    cb = creative_brief(_plan(), r)
    for k in ("target_audience", "teaching_style", "story_arc", "energy", "hook_style", "cta", "music_mood"):
        assert cb[k]
    assert cb["character_consistency"] == "Mr. Yeti"


def test_studio_executive_runs_full_pipeline(monkeypatch, tmp_path):
    import saathi.content_memory as cmmod
    from saathi.content_memory import ContentMemory
    monkeypatch.setattr(cmmod, "default_memory", lambda: ContentMemory(db_path=str(tmp_path / "cm.db")))
    monkeypatch.setenv("SAATHI_CURRICULUM_START", "2026-07-06")
    p = StudioExecutive().produce()
    assert isinstance(p, Production)
    assert p.plan and p.research and p.creative and p.script
    assert p.status in ("ready", "revision")
    assert p.status == "ready"                   # deterministic fallback yields a valid episode
    assert p.script["hook"] and len(p.script["scenes"]) >= 3 and p.est_seconds > 0
