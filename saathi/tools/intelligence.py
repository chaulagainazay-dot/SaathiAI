"""
intelligence.py — Retention Analyzer, Viral Pattern DB, Competitor Intel,
Comment Intel, Hook Lab helpers, CEO Dashboard aggregation.
"""
import json, os, sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .. import config
from ._llm_helper import ask_llm, extract_json

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


def score_retention(completion_pct: float) -> str:
    """A=>=70%, B=>=50%, C=>=30%, D=<30%."""
    if completion_pct >= 70:
        return "A"
    if completion_pct >= 50:
        return "B"
    if completion_pct >= 30:
        return "C"
    return "D"


def upsert_retention(video_id: str, platform: str, ret_3s: float, ret_10s: float,
                     ret_30s: float, avg_watch_sec: float, completion_pct: float) -> dict:
    """Store/update retention data for a video."""
    grade = score_retention(completion_pct)
    with _conn() as c:
        c.execute("""
            INSERT INTO video_retention
                (video_id, platform, ret_3s, ret_10s, ret_30s, avg_watch_sec, completion_pct, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id, platform) DO UPDATE SET
                ret_3s=excluded.ret_3s, ret_10s=excluded.ret_10s,
                ret_30s=excluded.ret_30s, avg_watch_sec=excluded.avg_watch_sec,
                completion_pct=excluded.completion_pct, score=excluded.score,
                recorded_at=datetime('now')
        """, (video_id, platform, ret_3s, ret_10s, ret_30s, avg_watch_sec, completion_pct, grade))
    return {"video_id": video_id, "platform": platform, "score": grade,
            "completion_pct": completion_pct}


def get_retention(video_id: str, platform: str) -> "dict | None":
    """Fetch retention record for a video."""
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM video_retention WHERE video_id=? AND platform=?",
            (video_id, platform)
        ).fetchone()
    return dict(row) if row else None


def get_killed_formats() -> list:
    """Return format_types that have >=3 D-scored videos — suppress these in pipeline."""
    with _conn() as c:
        rows = c.execute("""
            SELECT vp.format_type
            FROM viral_patterns vp
            JOIN video_retention vr ON vp.hook = vr.video_id
            WHERE vr.score = 'D'
            GROUP BY vp.format_type
            HAVING COUNT(*) >= 3
        """).fetchall()
    return [r["format_type"] for r in rows]


def get_all_retention(platform: str = None) -> list:
    """Fetch all retention records, optionally filtered by platform."""
    with _conn() as c:
        if platform:
            rows = c.execute(
                "SELECT * FROM video_retention WHERE platform=? ORDER BY recorded_at DESC",
                (platform,)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM video_retention ORDER BY recorded_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def save_viral_pattern(hook: str, topic: str, format_type: str, retention_pct: float,
                       views: int, shares: int, saves: int, platform: str):
    """Save a viral pattern data point to the database."""
    with _conn() as c:
        c.execute("""
            INSERT INTO viral_patterns (hook, topic, format_type, retention_pct, views, shares, saves, platform)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (hook, topic, format_type, retention_pct, views, shares, saves, platform))


def get_format_avg_retention() -> dict:
    """Return avg retention per format_type (only formats with >=1 data points)."""
    with _conn() as c:
        rows = c.execute("""
            SELECT format_type, AVG(retention_pct) as avg_ret, COUNT(*) as cnt
            FROM viral_patterns
            GROUP BY format_type
            HAVING cnt >= 1
            ORDER BY avg_ret DESC
        """).fetchall()
    return {r["format_type"]: round(r["avg_ret"], 1) for r in rows}


def get_top_formats(n: int = 3) -> list:
    """Return format_types sorted by avg retention descending."""
    avgs = get_format_avg_retention()
    return sorted(avgs, key=lambda k: avgs[k], reverse=True)[:n]


def classify_comments(comments: list) -> list:
    """Use LLM to classify comments and extract video ideas."""
    if not comments:
        return []
    batch = [{"comment_text": c.get("text", c.get("comment_text", "")),
              "video_id": c.get("video_id", "")} for c in comments[:50]]
    prompt = f"""Classify each of these YouTube/TikTok comments from an IELTS channel.
For each comment, assign:
- category: one of "question", "pain_point", "request", "praise", "other"
- video_idea: a short title for a video that answers this comment (or "" if not applicable)

Comments:
{json.dumps(batch, ensure_ascii=False)}

Return ONLY valid JSON:
{{"results": [{{"comment_text": "...", "category": "...", "video_idea": "..."}}]}}"""
    raw = ask_llm(prompt, system="You classify social media comments. Reply ONLY with valid JSON.")
    data = extract_json(raw)
    results = data.get("results", [])
    # Save to DB
    with _conn() as c:
        for item in results:
            c.execute("""
                INSERT INTO comment_intelligence (platform, comment_text, category, video_idea, source_video_id)
                VALUES (?, ?, ?, ?, ?)
            """, ("youtube", item.get("comment_text", ""), item.get("category", "other"),
                  item.get("video_idea", ""), item.get("video_id", "")))
    return results


def get_video_ideas_from_comments(n: int = 10) -> list:
    """Return top video ideas from comments, ranked by frequency."""
    with _conn() as c:
        rows = c.execute("""
            SELECT video_idea, COUNT(*) as freq, category
            FROM comment_intelligence
            WHERE video_idea != ''
            GROUP BY video_idea
            ORDER BY freq DESC
            LIMIT ?
        """, (n,)).fetchall()
    return [dict(r) for r in rows]
