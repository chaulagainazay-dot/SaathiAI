"""
intelligence.py — Retention Analyzer, Viral Pattern DB, Competitor Intel,
Comment Intel, Hook Lab helpers, CEO Dashboard aggregation.
"""
import json, os, sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .. import config

DB_PATH = os.getenv("BAADAR_DB", str(config.ROOT / "data" / "baadar.db"))


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    """Create all intelligence tables if they don't exist."""
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS video_retention (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id      TEXT NOT NULL,
            platform      TEXT NOT NULL,
            ret_3s        REAL,
            ret_10s       REAL,
            ret_30s       REAL,
            avg_watch_sec REAL,
            completion_pct REAL,
            score         TEXT,
            recorded_at   TEXT DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_vr ON video_retention(video_id, platform);

        CREATE TABLE IF NOT EXISTS hook_performance (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            hook_text      TEXT NOT NULL,
            topic          TEXT,
            video_id       TEXT,
            views_48h      INTEGER DEFAULT 0,
            retention_score REAL DEFAULT 0,
            created_at     TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS viral_patterns (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            hook          TEXT,
            topic         TEXT,
            format_type   TEXT,
            retention_pct REAL DEFAULT 0,
            views         INTEGER DEFAULT 0,
            shares        INTEGER DEFAULT 0,
            saves         INTEGER DEFAULT 0,
            platform      TEXT,
            recorded_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS competitor_data (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_name  TEXT,
            channel_id    TEXT,
            video_title   TEXT,
            views         INTEGER DEFAULT 0,
            upload_date   TEXT,
            topic_tags    TEXT,
            scanned_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS comment_intelligence (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            platform      TEXT,
            comment_text  TEXT,
            category      TEXT,
            video_idea    TEXT,
            source_video_id TEXT,
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS referral_events (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            uid           TEXT NOT NULL,
            old_score     REAL,
            new_score     REAL,
            referral_code TEXT,
            sent_at       TEXT DEFAULT (datetime('now')),
            conversions   INTEGER DEFAULT 0
        );
        """)
