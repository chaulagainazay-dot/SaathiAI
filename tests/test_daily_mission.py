"""Daily IELTS Mission — morning mission from the curriculum + study streak."""
import time

import saathi.daily_mission as dm


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "_path", lambda: tmp_path / "study.json")
    monkeypatch.setenv("SAATHI_CURRICULUM_START", "2026-07-06")


def test_mission_reflects_todays_lesson(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    now = time.mktime(time.strptime("2026-07-06", "%Y-%m-%d"))
    m = dm.mission(now=now)
    assert m["day"] == 1 and m["episode"] == "EP-001"
    assert m["topic"] and m["total"] == 4 and m["completed"] == 0
    assert m["program"] == "IELTS Mastery v1"


def test_marking_items_updates_completion(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    now = time.mktime(time.strptime("2026-07-06", "%Y-%m-%d"))
    dm.mark("lesson", True, now=now)
    dm.mark("speaking", True, now=now)
    m = dm.mission(now=now)
    assert m["completed"] == 2
    assert [c["done"] for c in m["checklist"] if c["key"] == "lesson"] == [True]


def test_streak_counts_consecutive_lesson_days(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    d2 = time.mktime(time.strptime("2026-07-07", "%Y-%m-%d"))
    d3 = time.mktime(time.strptime("2026-07-08", "%Y-%m-%d"))
    dm.mark("lesson", True, now=d2)
    dm.mark("lesson", True, now=d3)
    assert dm.streak(now=d3) == 2
    # a gap breaks the streak
    d5 = time.mktime(time.strptime("2026-07-10", "%Y-%m-%d"))
    assert dm.streak(now=d5) == 0


def test_briefing_and_review_render(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    now = time.mktime(time.strptime("2026-07-06", "%Y-%m-%d"))
    lines = dm.briefing_lines(now=now)
    assert any("IELTS Mastery v1" in ln for ln in lines)
    assert any("Today's Mission" in ln for ln in lines)
    dm.mark("lesson", True, now=now)
    assert "Daily Review" in dm.review(now=now)
