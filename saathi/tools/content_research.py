"""Content Research Agent — Stage 1.
Fetches trending IELTS topics from Reddit, YouTube search, Google Trends.
Saves results to Firebase (if configured) or local JSON cache.
"""
import json
import time
from datetime import datetime
from pathlib import Path

import httpx

_CACHE_DIR = Path.home() / "SaathiAI" / "research_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ── Google Trends via pytrends ─────────────────────────────────────────────────
def _google_trends() -> list[dict]:
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=360)
        kw_list = ["IELTS", "IELTS speaking", "IELTS writing tips", "IELTS band 7", "IELTS vocabulary"]
        pt.build_payload(kw_list, timeframe="now 7-d", geo="")
        related = pt.related_queries()
        topics = []
        for kw in kw_list:
            df = related.get(kw, {}).get("top")
            if df is not None and not df.empty:
                for _, row in df.head(5).iterrows():
                    topics.append({"source": "google_trends", "query": row["query"], "value": int(row["value"]), "seed_kw": kw})
        return topics
    except Exception as e:
        return [{"source": "google_trends", "error": str(e)}]


# ── Reddit IELTS community ─────────────────────────────────────────────────────
def _reddit_ielts() -> list[dict]:
    try:
        headers = {"User-Agent": "BaadarBot/1.0 (pielts.web.app)"}
        r = httpx.get(
            "https://www.reddit.com/r/IELTS/hot.json?limit=25",
            headers=headers, timeout=15, follow_redirects=True
        )
        r.raise_for_status()
        posts = r.json()["data"]["children"]
        results = []
        for p in posts:
            d = p["data"]
            if d.get("score", 0) > 5:
                results.append({
                    "source": "reddit_ielts",
                    "title": d["title"],
                    "score": d["score"],
                    "comments": d["num_comments"],
                    "url": f"https://reddit.com{d['permalink']}",
                    "flair": d.get("link_flair_text", ""),
                })
        return results
    except Exception as e:
        return [{"source": "reddit", "error": str(e)}]


# ── YouTube trending IELTS search (via YouTube Data API or scrape) ─────────────
def _youtube_trending() -> list[dict]:
    try:
        # Use YouTube search via RapidAPI-free alternative
        r = httpx.get(
            "https://yt.lemnoslife.com/noKey/search",
            params={"q": "IELTS tips 2025", "part": "snippet", "type": "video", "maxResults": "10"},
            timeout=15
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        results = []
        for item in items:
            snip = item.get("snippet", {})
            results.append({
                "source": "youtube_trending",
                "title": snip.get("title", ""),
                "channel": snip.get("channelTitle", ""),
                "description": snip.get("description", "")[:200],
                "videoId": item.get("id", {}).get("videoId", ""),
            })
        return results
    except Exception as e:
        return [{"source": "youtube", "error": str(e)}]


# ── Baadar AI analysis ─────────────────────────────────────────────────────────
def _analyze_with_baadar(raw_topics: list[dict]) -> dict:
    """Send raw research to Baadar agent for content ideas extraction."""
    try:
        from ._llm_helper import ask_llm
        summary = json.dumps(raw_topics[:30], indent=2)
        prompt = (
            f"Analyze these trending IELTS topics from Reddit/YouTube/Google Trends "
            f"and extract the TOP 5 most engaging content ideas for short YouTube videos "
            f"(30-60 sec Shorts). Focus on: common mistakes, vocabulary, band score tips, "
            f"speaking/writing strategies. Return as JSON list with fields: "
            f"title, hook, content_type (vocab/tip/mistake/strategy), difficulty (beginner/intermediate/advanced), "
            f"estimated_views_potential (low/medium/high).\n\nData:\n{summary[:3000]}"
        )
        reply = ask_llm(prompt, system="Return ONLY a JSON array, no other text.", timeout=60)
        # Try to extract JSON from reply
        import re
        match = re.search(r'\[.*?\]', reply, re.DOTALL)
        if match:
            return {"ideas": json.loads(match.group(0))}
        return {"ideas": [], "raw": reply}
    except Exception as e:
        return {"ideas": [], "error": str(e)}


def _get_token() -> str:
    import os
    from dotenv import load_dotenv
    load_dotenv(Path.home() / "SaathiAI" / ".env")
    return os.getenv("SAATHI_TOKEN", "")


# ── Main entry point ───────────────────────────────────────────────────────────
def research_daily_topics() -> dict:
    """Run full content research pipeline. Called by n8n at 6 AM daily."""
    ts = datetime.now().strftime("%Y-%m-%d")

    trends   = _google_trends()
    reddit   = _reddit_ielts()
    youtube  = _youtube_trending()

    raw = trends + reddit + youtube
    analysis = _analyze_with_baadar(raw)

    result = {
        "date": ts,
        "google_trends": trends,
        "reddit": reddit,
        "youtube": youtube,
        "content_ideas": analysis.get("ideas", []),
        "total_signals": len(raw),
    }

    # Cache locally
    cache_file = _CACHE_DIR / f"research_{ts}.json"
    cache_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    # Also save latest
    (_CACHE_DIR / "latest.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))

    return result


def get_latest_research() -> dict:
    latest = _CACHE_DIR / "latest.json"
    if latest.exists():
        return json.loads(latest.read_text())
    return {"error": "No research yet — run research_daily_topics() first"}
