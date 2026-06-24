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


# ── Task 4: Viral Pattern Database ──────────────────────────────────────────
def test_viral_pattern_avg_retention():
    init_db()
    from saathi.tools.intelligence import save_viral_pattern, get_format_avg_retention
    save_viral_pattern("Hook A", "Grammar", "quiz", 82.0, 1000, 50, 30, "youtube")
    save_viral_pattern("Hook B", "Grammar", "quiz", 78.0, 800, 40, 25, "youtube")
    save_viral_pattern("Hook C", "Vocab", "vocab", 40.0, 300, 10, 5, "youtube")
    avgs = get_format_avg_retention()
    assert "quiz" in avgs
    assert abs(avgs["quiz"] - 80.0) < 1.0
    assert "vocab" in avgs


def test_get_top_formats():
    init_db()
    from saathi.tools.intelligence import save_viral_pattern, get_top_formats
    save_viral_pattern("Hook X", "Topic", "quiz",  80.0, 1000, 0, 0, "youtube")
    save_viral_pattern("Hook Y", "Topic", "story", 65.0, 800, 0, 0, "youtube")
    save_viral_pattern("Hook Z", "Topic", "vocab", 40.0, 300, 0, 0, "youtube")
    tops = get_top_formats(2)
    assert tops[0] == "quiz"
    assert tops[1] == "story"


# ── Task 5: Mr. Yeti Character Engine ──────────────────────────────────────────
def test_persona_system_prompt_contains_traits():
    from saathi.tools.script_writer import persona_system_prompt
    prompt = persona_system_prompt()
    assert "funny" in prompt
    assert "Mr. Yeti" in prompt
    assert "forbidden" in prompt.lower() or "never say" in prompt.lower()


# ── Task 6: Comment Intelligence ────────────────────────────────────────────────
def test_classify_comments_adds_category():
    fake_response = json.dumps({
        "results": [
            {"comment_text": "What tense should I use in Task 2?",
             "category": "question", "video_idea": "IELTS Writing Task 2 tense guide"}
        ]
    })
    comments = [{"text": "What tense should I use in Task 2?", "video_id": "vid1"}]
    with mock.patch("saathi.tools.intelligence.ask_llm", return_value=fake_response):
        from saathi.tools.intelligence import classify_comments
        result = classify_comments(comments)
    assert result[0]["category"] == "question"
    assert "video_idea" in result[0]


# ── Task 7: Competitor Intelligence ─────────────────────────────────────────
def test_competitor_insights_returns_gaps():
    init_db()
    # Insert fake competitor data
    db = os.getenv("BAADAR_DB", str(os.path.dirname(__file__) + "/../data/baadar.db"))
    with sqlite3.connect(db) as c:
        c.execute("""INSERT INTO competitor_data
            (channel_name, channel_id, video_title, views, upload_date, topic_tags, scanned_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            ("E2 IELTS", "UC_xyz", "IELTS Reading Tips", 50000, "2026-06-01", '["reading","tips"]'))
        c.execute("""INSERT INTO competitor_data
            (channel_name, channel_id, video_title, views, upload_date, topic_tags, scanned_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            ("IELTS Liz", "UC_abc", "IELTS Writing Task 1", 30000, "2026-06-05", '["writing","task1"]'))
    from saathi.tools.intelligence import get_competitor_insights
    result = get_competitor_insights()
    assert "top_topics" in result
    assert "channels" in result
