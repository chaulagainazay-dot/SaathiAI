"""
content_library.py — Central SQLite database for Mr. Yeti's content pipeline.

DB file: config.ROOT / "data" / "content_library.db"
"""

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path

from ..runtime_paths import content_library_path

#: Resolved per call, not once at import.
#:
#: This module used to compute ``config.ROOT / "data" / "content_library.db"``
#: and connect to it at import time, so merely importing it created and opened a
#: database inside the checkout -- including during an isolated boot, which D13
#: requires to write nothing repo-local. ``scoped_state_path`` keeps the
#: historical location when no isolation is configured, so production behaviour
#: is unchanged, and moves the store under SAATHI_STATE_ROOT when one is.
DB_PATH = content_library_path()

_conn = None


def _connection() -> sqlite3.Connection:
    """Open on first use, against the state root in force at that moment."""
    global _conn, DB_PATH
    if _conn is None:
        DB_PATH = content_library_path()
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        init_db()
    return _conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables if they don't exist. Called at import time."""
    cur = _connection().cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS videos (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            slug          TEXT UNIQUE,
            date          TEXT,
            topic         TEXT,
            pillar        TEXT,
            title         TEXT,
            hook          TEXT,
            script_json   TEXT,
            video_path    TEXT,
            duration_sec  REAL,
            method        TEXT,
            created_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS shorts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            video_slug    TEXT,
            clip_type     TEXT,
            path          TEXT,
            duration_sec  REAL,
            hook_variant  TEXT,
            posted_at     TEXT,
            platform      TEXT,
            post_url      TEXT
        );

        CREATE TABLE IF NOT EXISTS analytics (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            slug                TEXT,
            platform            TEXT,
            views               INTEGER DEFAULT 0,
            watch_time_minutes  REAL    DEFAULT 0,
            avg_view_percent    REAL    DEFAULT 0,
            likes               INTEGER DEFAULT 0,
            comments            INTEGER DEFAULT 0,
            shares              INTEGER DEFAULT 0,
            saves               INTEGER DEFAULT 0,
            follows             INTEGER DEFAULT 0,
            ctr_percent         REAL    DEFAULT 0,
            recorded_at         TEXT,
            days_since_post     INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS topics_used (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            topic             TEXT,
            pillar            TEXT,
            date_used         TEXT,
            performance_score REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS character_events (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_slug   TEXT,
            character_name TEXT,
            event          TEXT,
            band_score     TEXT,
            date           TEXT
        );
    """)
    _connection().commit()


# ---------------------------------------------------------------------------
# Video helpers
# ---------------------------------------------------------------------------

def save_video(
    slug: str,
    date: str,
    topic: str,
    pillar: str,
    title: str,
    hook: str,
    script_json: str,
    video_path: str,
    duration_sec: float,
    method: str,
) -> int:
    created_at = datetime.now(timezone.utc).isoformat()
    cur = _connection().execute(
        """
        INSERT INTO videos
            (slug, date, topic, pillar, title, hook, script_json,
             video_path, duration_sec, method, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (slug, date, topic, pillar, title, hook, script_json,
         video_path, duration_sec, method, created_at),
    )
    _connection().commit()
    return cur.lastrowid


def get_all_videos(limit: int = 100) -> list[dict]:
    rows = _connection().execute(
        "SELECT * FROM videos ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_videos_needing_analytics(days_old: int = 1) -> list[dict]:
    """Videos with no analytics row yet that are at least `days_old` days old."""
    rows = _connection().execute(
        """
        SELECT v.* FROM videos v
        WHERE NOT EXISTS (
            SELECT 1 FROM analytics a WHERE a.slug = v.slug
        )
        AND v.created_at <= datetime('now', ? || ' days')
        ORDER BY v.created_at
        """,
        (f"-{days_old}",),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Shorts helpers
# ---------------------------------------------------------------------------

def save_short(
    video_slug: str,
    clip_type: str,
    path: str,
    duration_sec: float,
) -> int:
    cur = _connection().execute(
        """
        INSERT INTO shorts (video_slug, clip_type, path, duration_sec)
        VALUES (?, ?, ?, ?)
        """,
        (video_slug, clip_type, path, duration_sec),
    )
    _connection().commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Analytics helpers
# ---------------------------------------------------------------------------

def save_analytics(
    slug: str,
    platform: str,
    views: int,
    likes: int,
    comments: int,
    shares: int,
    saves: int,
    watch_time_minutes: float = 0,
    avg_view_percent: float = 0,
    follows: int = 0,
    ctr_percent: float = 0,
    days_since_post: int = 0,
) -> None:
    recorded_at = datetime.now(timezone.utc).isoformat()
    _connection().execute(
        """
        INSERT INTO analytics
            (slug, platform, views, watch_time_minutes, avg_view_percent,
             likes, comments, shares, saves, follows, ctr_percent,
             recorded_at, days_since_post)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (slug, platform, views, watch_time_minutes, avg_view_percent,
         likes, comments, shares, saves, follows, ctr_percent,
         recorded_at, days_since_post),
    )
    _connection().commit()


# ---------------------------------------------------------------------------
# Topic deduplication
# ---------------------------------------------------------------------------

def save_topic_used(topic: str, pillar: str = "", performance_score: float = 0.0):
    """Record a topic as used to prevent repetition."""
    from datetime import datetime
    _connection().execute(
        "INSERT INTO topics_used (topic, pillar, date_used, performance_score) VALUES (?,?,?,?)",
        (topic, pillar, datetime.now().strftime("%Y-%m-%d"), performance_score),
    )
    _connection().commit()


def get_topics_used(days_back: int = 90) -> list[str]:
    rows = _connection().execute(
        """
        SELECT topic FROM topics_used
        WHERE date_used >= date('now', ? || ' days')
        """,
        (f"-{days_back}",),
    ).fetchall()
    return [r["topic"] for r in rows]


def is_duplicate_topic(topic: str, threshold: float = 0.7) -> bool:
    """
    Simple word-overlap check.
    Returns True if `topic` is too similar (>= threshold Jaccard) to any
    recent topic in topics_used (last 90 days).
    """
    recent = get_topics_used(days_back=90)
    words_new = set(topic.lower().split())
    for existing in recent:
        words_ex = set(existing.lower().split())
        union = words_new | words_ex
        if not union:
            continue
        jaccard = len(words_new & words_ex) / len(union)
        if jaccard >= threshold:
            return True
    return False


# ---------------------------------------------------------------------------
# Performance analytics
# ---------------------------------------------------------------------------

def _avg_score_query(group_col: str, table: str = "analytics") -> dict:
    rows = _connection().execute(
        f"""
        SELECT v.{group_col},
               AVG(score_video(a.views, a.likes, a.comments, a.shares,
                               a.saves, a.avg_view_percent)) AS avg_score
        FROM {table} a
        JOIN videos v ON v.slug = a.slug
        GROUP BY v.{group_col}
        """
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def score_video(
    views: int,
    likes: int,
    comments: int,
    shares: int,
    saves: int,
    avg_view_percent: float,
) -> float:
    """
    Composite engagement score:
        score = views * (1 + engage_rate) * (1 + retention_bonus)
    engage_rate  = (likes + comments*2 + shares*3 + saves*2) / max(views, 1)
    retention_bonus = avg_view_percent / 100
    """
    if views <= 0:
        return 0.0
    engage_rate = (likes + comments * 2 + shares * 3 + saves * 2) / views
    retention_bonus = avg_view_percent / 100.0
    return views * (1 + engage_rate) * (1 + retention_bonus)


def _register_score_fn() -> None:
    """Register score_video as a SQLite scalar function so it works in queries."""
    _connection().create_function(
        "score_video", 6,
        lambda v, l, c, s, sv, avp: score_video(v, l, c, s, sv, avp),
    )


def get_performance_by_pillar() -> dict:
    _register_score_fn()
    rows = _connection().execute(
        """
        SELECT v.pillar,
               AVG(score_video(a.views, a.likes, a.comments, a.shares,
                               a.saves, a.avg_view_percent)) AS avg_score
        FROM analytics a
        JOIN videos v ON v.slug = a.slug
        GROUP BY v.pillar
        """
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def get_performance_by_clip_type() -> dict:
    _register_score_fn()
    rows = _connection().execute(
        """
        SELECT s.clip_type,
               AVG(score_video(a.views, a.likes, a.comments, a.shares,
                               a.saves, a.avg_view_percent)) AS avg_score
        FROM analytics a
        JOIN shorts s ON s.video_slug = a.slug
        GROUP BY s.clip_type
        """
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def get_performance_by_posting_time() -> dict:
    """Returns {hour_int: avg_views}."""
    rows = _connection().execute(
        """
        SELECT CAST(strftime('%H', a.recorded_at) AS INTEGER) AS hour,
               AVG(a.views) AS avg_views
        FROM analytics a
        GROUP BY hour
        ORDER BY hour
        """
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def get_top_hooks(n: int = 10) -> list[dict]:
    _register_score_fn()
    rows = _connection().execute(
        """
        SELECT v.slug, v.hook, v.title,
               score_video(a.views, a.likes, a.comments, a.shares,
                           a.saves, a.avg_view_percent) AS score
        FROM videos v
        JOIN analytics a ON a.slug = v.slug
        ORDER BY score DESC
        LIMIT ?
        """,
        (n,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Character continuity
# ---------------------------------------------------------------------------

def save_character_event(
    episode_slug: str,
    character_name: str,
    event: str,
    band_score: str = "",
    date: str = "",
) -> None:
    if not date:
        date = datetime.now(timezone.utc).date().isoformat()
    _connection().execute(
        """
        INSERT INTO character_events
            (episode_slug, character_name, event, band_score, date)
        VALUES (?, ?, ?, ?, ?)
        """,
        (episode_slug, character_name, event, band_score, date),
    )
    _connection().commit()


def get_character_history(character_name: str) -> list[dict]:
    rows = _connection().execute(
        """
        SELECT * FROM character_events
        WHERE character_name = ?
        ORDER BY date ASC
        """,
        (character_name,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_all_characters() -> list[str]:
    rows = _connection().execute(
        "SELECT DISTINCT character_name FROM character_events ORDER BY character_name"
    ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------
#
# Deliberately not called at import. `init_db()` on import meant that merely
# importing this module created and wrote a SQLite file inside the checkout --
# during an isolated boot too, where D13 requires no repo-local write at all.
# `_connection()` opens on first real use instead, so the schema is created the
# first time the content pipeline is actually used, against whichever state root
# is in force then.
