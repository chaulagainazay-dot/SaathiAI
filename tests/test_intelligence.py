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
