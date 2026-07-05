"""IELTS Mastery — versioned learning program + Mr. Yeti Bible."""
import time

from saathi.curriculum import (lesson_for_day, today, program, program_day,
                               learner_day)


def test_every_day_has_a_rich_lesson():
    for d in range(1, 366):
        les = lesson_for_day(d)
        assert les.topic and les.phase and les.skill and les.objective
        assert les.difficulty and les.estimated_minutes > 0
        assert les.youtube_title and les.seo_keywords
        assert les.day == d


def test_phases_map_to_expected_skills():
    assert lesson_for_day(1).skill == "grammar"
    assert lesson_for_day(120).skill == "vocabulary"
    assert lesson_for_day(200).skill == "speaking"
    assert lesson_for_day(260).skill == "writing-task1"
    assert lesson_for_day(330).skill == "exam-strategy"


def test_grammar_difficulty_deepens():
    assert lesson_for_day(1).difficulty == "B1"
    assert lesson_for_day(60).difficulty == "B2"      # later grammar is B2


def test_episode_numbering_separate_from_topic():
    les = lesson_for_day(41)
    assert les.episode == "EP-041" and les.youtube_number == "Mr. Yeti #41"
    assert les.prerequisites == [39, 40]


def test_program_versioned_with_start(monkeypatch):
    monkeypatch.setenv("SAATHI_CURRICULUM_START", "2026-07-06")
    p = program()
    assert p.title == "IELTS Mastery v1" and p.start_date == "2026-07-06"
    # program day 1 on the start date
    day0 = time.mktime(time.strptime("2026-07-06", "%Y-%m-%d"))
    assert program_day(now=day0) == 1
    assert today(now=day0).skill == "grammar"
    # a week later → day 8
    day7 = time.mktime(time.strptime("2026-07-13", "%Y-%m-%d"))
    assert program_day(now=day7) == 8


def test_program_day_clamps_before_launch(monkeypatch):
    monkeypatch.setenv("SAATHI_CURRICULUM_START", "2026-07-06")
    before = time.mktime(time.strptime("2026-07-01", "%Y-%m-%d"))
    assert program_day(now=before) == 1               # never 0/negative


def test_learner_starts_at_day_one():
    # a learner enrolling today is on Day 1, not dropped into the middle
    now = time.mktime(time.strptime("2027-01-15", "%Y-%m-%d"))
    assert learner_day("2027-01-15", now=now) == 1
    later = time.mktime(time.strptime("2027-01-20", "%Y-%m-%d"))
    assert learner_day("2027-01-15", now=later) == 6


def test_bible_visual_prefix_is_consistent():
    from saathi.character import visual_prefix, scene_prompt, BIBLE
    p = visual_prefix()
    assert BIBLE["palette"]["primary"] in p and "Mr. Yeti" in p
    sp = scene_prompt("chalkboard explanation")
    assert "chalkboard explanation" in sp and "No on-screen text" in sp
