import sqlite3, os, pytest
os.environ.setdefault("BAADAR_DB", "/tmp/test_baadar.db")

from saathi.tools.intelligence import init_db, DB_PATH

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
