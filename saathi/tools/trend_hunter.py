"""
Flow 11 — Trend Hunter

Daily 5am scan:
  - Reddit r/IELTS top posts (what students are asking right now)
  - YouTube trending IELTS searches
  - TikTok trending hashtags (via public data)

Output: ranked list of trending topics → feeds into Flow 1 (topic generator)
"""

import json
import os
from pathlib import Path

from .. import config
from ._llm_helper import ask_llm, extract_json

_TRENDS_FILE = config.ROOT / "data" / "trending_topics.json"


# ── Reddit ─────────────────────────────────────────────────────────────────────

def scan_reddit_ielts(limit: int = 25) -> list[dict]:
    """Pull top posts from r/IELTS (no auth required for public JSON)."""
    try:
        import httpx
        r = httpx.get(
            "https://www.reddit.com/r/IELTS/hot.json",
            params={"limit": limit},
            headers={"User-Agent": "MrYetiBot/1.0"},
            timeout=15,
            follow_redirects=True,
        )
        if r.status_code != 200:
            return []
        posts = []
        for item in r.json().get("data", {}).get("children", []):
            d = item.get("data", {})
            posts.append({
                "title":  d.get("title", ""),
                "body":   d.get("selftext", "")[:300],
                "upvotes": d.get("ups", 0),
                "comments": d.get("num_comments", 0),
                "url":    f"https://reddit.com{d.get('permalink', '')}",
                "source": "reddit_ielts",
            })
        return sorted(posts, key=lambda p: p["upvotes"], reverse=True)
    except Exception:
        return []


def scan_youtube_trending_ielts() -> list[dict]:
    """Search YouTube for trending IELTS content uploaded this week."""
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        return []
    try:
        import httpx
        from datetime import datetime, timedelta, timezone
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        queries = ["IELTS speaking tips 2025", "IELTS writing task 2", "IELTS band 7 mistakes"]
        results = []
        for q in queries:
            r = httpx.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={"key": api_key, "q": q, "part": "snippet", "type": "video",
                        "order": "viewCount", "publishedAfter": week_ago, "maxResults": 5},
                timeout=15,
            )
            for item in r.json().get("items", []):
                sn = item.get("snippet", {})
                results.append({
                    "title":  sn.get("title", ""),
                    "channel": sn.get("channelTitle", ""),
                    "source": "youtube_trending",
                })
        return results
    except Exception:
        return []


# ── LLM: turn trends into Mr. Yeti video ideas ────────────────────────────────

def generate_trend_topics(reddit_posts: list, yt_videos: list) -> list[dict]:
    """Feed trending content to LLM → get 10 Mr. Yeti video ideas."""
    if not reddit_posts and not yt_videos:
        return []

    reddit_block = "\n".join(
        f"- [{p['upvotes']} upvotes] {p['title']}" for p in reddit_posts[:15]
    )
    yt_block = "\n".join(
        f"- {v['title']} ({v.get('channel','')})" for v in yt_videos[:10]
    )

    prompt = f"""You are Mr. Yeti's content strategist. Here are what IELTS students are talking about RIGHT NOW:

REDDIT (r/IELTS hot posts):
{reddit_block or "No data"}

TRENDING YOUTUBE IELTS VIDEOS THIS WEEK:
{yt_block or "No data"}

Create 10 Mr. Yeti video ideas that ride these exact trends.

Return JSON:
{{
  "topics": [
    {{
      "trend_source": "what reddit/youtube signal inspired this",
      "video_title": "dramatic hook-style title",
      "hook": "first 3 seconds of the video",
      "content_type": "mistake|quiz|horror_story|before_after|dont_say",
      "trending_score": 1-10,
      "why_trending": "one sentence explanation"
    }}
  ]
}}

Rules:
- Titles must be Mr. Yeti style: dramatic, slightly sarcastic, Band 7 obsessed
- Prioritize topics with 5+ upvotes or multiple similar posts
- Only return JSON"""

    try:
        raw = ask_llm(prompt, system="You are a viral content strategist. Reply ONLY with valid JSON.")
        data = extract_json(raw)
        topics = data.get("topics", [])
        return sorted(topics, key=lambda t: t.get("trending_score", 0), reverse=True)
    except Exception:
        return []


def run_trend_hunter() -> dict:
    """Full pass: scan → generate → save. Called daily at 5am before Flow 8."""
    reddit  = scan_reddit_ielts()
    yt      = scan_youtube_trending_ielts()
    topics  = generate_trend_topics(reddit, yt)

    if topics:
        existing = []
        try:
            if _TRENDS_FILE.exists():
                existing = json.loads(_TRENDS_FILE.read_text())
        except Exception:
            pass
        # Keep most recent 50 trends
        combined = (topics + existing)[:50]
        _TRENDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TRENDS_FILE.write_text(json.dumps(combined, indent=2, ensure_ascii=False))

    return {
        "ok":             True,
        "reddit_posts":   len(reddit),
        "yt_videos":      len(yt),
        "topics_generated": len(topics),
        "top_topics":     topics[:3],
    }


def get_trending_topics(n: int = 5) -> list[dict]:
    """Returns top N trending topics for Flow 1 to use."""
    try:
        if _TRENDS_FILE.exists():
            topics = json.loads(_TRENDS_FILE.read_text())
            return topics[:n]
    except Exception:
        pass
    return []
