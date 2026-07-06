"""SaathiAI Studio — Content Memory + Director/Planner (first slice)."""
import saathi.content_memory as cmmod
from saathi.content_memory import ContentMemory


def test_content_memory_record_and_dedup(tmp_path):
    m = ContentMemory(db_path=str(tmp_path / "cm.db"))
    assert m.is_covered("Past Perfect Tense") is False
    m.record(topic="Past Perfect Tense", skill="grammar", day=4)
    assert m.is_covered("past perfect tense") is True     # normalized match
    assert m.is_covered("Past  Perfect, Tense!") is True  # punctuation-insensitive
    assert m.count() == 1
    assert "Past Perfect Tense" in m.recent_topics()
    assert m.skills_this_week().get("grammar") == 1


def test_planner_skips_covered_topics(tmp_path, monkeypatch):
    m = ContentMemory(db_path=str(tmp_path / "cm.db"))
    monkeypatch.setattr(cmmod, "default_memory", lambda: m)
    monkeypatch.setenv("SAATHI_CURRICULUM_START", "2026-07-06")
    import time
    from saathi.studio import plan_today
    day1 = time.mktime(time.strptime("2026-07-06", "%Y-%m-%d"))
    b1 = plan_today(now=day1)
    assert b1.day == 1 and b1.topic and b1.already_covered is False
    assert b1.character.get("name") == "Mr. Yeti"
    # after producing day 1's topic, the planner advances to an uncovered lesson
    m.record(topic=b1.topic, skill=b1.skill, day=b1.day)
    b2 = plan_today(now=day1)
    assert b2.topic != b1.topic and b2.day > b1.day       # skipped the covered one
    assert b1.topic in b2.avoid                            # and knows to avoid it
