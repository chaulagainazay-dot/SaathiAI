import sqlite3, os, pytest
os.environ.setdefault("BAADAR_DB", "/tmp/test_baadar.db")

from saathi.tools.intelligence import init_db, DB_PATH, score_retention, upsert_retention, get_retention

def test_init_db_creates_all_tables():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "video_retention" in tables
    assert "hook_performance" in tables
    assert "viral_patterns" in tables
    assert "competitor_data" in tables
    assert "comment_intelligence" in tables
    assert "referral_events" in tables


def test_score_retention_grades():
    assert score_retention(75.0) == "A"
    assert score_retention(60.0) == "B"
    assert score_retention(40.0) == "C"
    assert score_retention(25.0) == "D"
    assert score_retention(70.0) == "A"   # boundary: >=70 → A
    assert score_retention(50.0) == "B"   # boundary: >=50 → B
    assert score_retention(30.0) == "C"   # boundary: >=30 → C


def test_upsert_and_get_retention():
    init_db()
    result = upsert_retention("vid_test_1", "youtube", 85.0, 72.0, 55.0, 28.5, 68.0)
    assert result["score"] == "B"
    row = get_retention("vid_test_1", "youtube")
    assert row is not None
    assert row["completion_pct"] == 68.0
    assert row["score"] == "B"


# ── Task 3: Hook Laboratory ──────────────────────────────────────────────────
import json
import unittest.mock as mock

def test_generate_hooks_returns_top3():
    fake_llm_response = json.dumps({
        "hooks": [
            {"text": "Stop making this mistake.", "curiosity": 8, "urgency": 7, "specificity": 6},
            {"text": "97% of students fail because of this.", "curiosity": 9, "urgency": 9, "specificity": 8},
            {"text": "This one trick changed my IELTS score.", "curiosity": 7, "urgency": 6, "specificity": 7},
            {"text": "You are doing grammar wrong.", "curiosity": 6, "urgency": 5, "specificity": 5},
        ]
    })
    with mock.patch("saathi.tools.content_studio.ask_llm", return_value=fake_llm_response):
        from saathi.tools.content_studio import generate_hooks
        result = generate_hooks("Grammar Mistakes")
    assert "hooks" in result
    assert "top3" in result
    assert len(result["top3"]) == 3
    # top hook should be highest total score
    assert result["top3"][0] == "97% of students fail because of this."
