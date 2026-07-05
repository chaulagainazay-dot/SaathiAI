"""365-Day Curriculum + Mr. Yeti Bible."""
from saathi import curriculum
from saathi.curriculum import lesson_for_day, today


def test_every_day_has_a_lesson():
    for d in range(1, 366):
        les = lesson_for_day(d)
        assert les.topic and les.phase and les.skill
        assert les.day == d


def test_phases_map_to_expected_skills():
    assert lesson_for_day(1).skill == "grammar"
    assert lesson_for_day(120).skill == "vocabulary"
    assert lesson_for_day(200).skill == "speaking"
    assert lesson_for_day(260).skill == "writing-task1"
    assert lesson_for_day(330).skill == "exam-strategy"


def test_deterministic_and_wraps():
    assert lesson_for_day(10).topic == lesson_for_day(10).topic     # deterministic
    assert lesson_for_day(366).day == 1                             # wraps into the year


def test_curriculum_start_anchor(monkeypatch):
    monkeypatch.setenv("SAATHI_CURRICULUM_START", "2026-07-05")
    import time
    # first program day = start date
    les = today(now=time.mktime(time.strptime("2026-07-05", "%Y-%m-%d")))
    assert les.day == 1 and les.skill == "grammar"


def test_bible_visual_prefix_is_consistent():
    from saathi.character import visual_prefix, scene_prompt, BIBLE
    p = visual_prefix()
    assert BIBLE["palette"]["primary"] in p and "Mr. Yeti" in p
    sp = scene_prompt("chalkboard explanation")
    assert "chalkboard explanation" in sp and "No on-screen text" in sp
