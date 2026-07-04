"""
Flow 10 — Comment Miner

Pulls YouTube comments → LLM finds top questions/pain points → turns them into video ideas.
The audience literally writes your next script.
"""

import json
import os
from pathlib import Path

from .. import config
from ._llm_helper import ask_llm, extract_json

_IDEAS_FILE = config.ROOT / "data" / "comment_video_ideas.json"


def pull_youtube_comments(max_results: int = 200) -> list[dict]:
    """Pull recent comments from all Mr. Yeti videos via YouTube Data API."""
    api_key    = os.environ.get("YOUTUBE_API_KEY", "")
    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID", "")
    if not api_key or not channel_id:
        return []

    try:
        from saathi.infrastructure.connectors import default_registry
        reg = default_registry()

        # Get recent video IDs
        search_r = reg.execute(capability="search", connector_id="youtube",
                               channelId=channel_id, part="id", type="video",
                               order="date", maxResults=10)
        video_ids = [i["id"]["videoId"] for i in search_r.get("items", [])
                     if i.get("id", {}).get("videoId")]

        comments = []
        for vid in video_ids[:5]:  # top 5 most recent
            cr = reg.execute(capability="list_comments", connector_id="youtube",
                             videoId=vid, part="snippet", maxResults=40, order="relevance")
            for item in cr.get("items", []):
                text = item["snippet"]["topLevelComment"]["snippet"].get("textDisplay", "")
                likes = item["snippet"]["topLevelComment"]["snippet"].get("likeCount", 0)
                comments.append({"video_id": vid, "text": text, "likes": likes})

        return sorted(comments, key=lambda c: c["likes"], reverse=True)[:max_results]
    except Exception:
        return []


def mine_video_ideas(comments: list[dict]) -> list[dict]:
    """LLM reads comments → extracts top questions → formats as Mr. Yeti video ideas."""
    if not comments:
        return []

    comment_block = "\n".join(
        f"- {c['text'][:200]}" for c in comments[:80]
    )

    prompt = f"""You are Mr. Yeti's content strategist. Read these YouTube comments from IELTS students.

COMMENTS:
{comment_block}

Find the TOP 10 most common questions, confusions, or pain points.
For each, create a Mr. Yeti video idea using this format:

{{
  "ideas": [
    {{
      "comment_theme": "what students are asking about",
      "video_title": "Mr. Yeti hook-style title",
      "hook_line": "first 3 seconds of the video",
      "content_type": "mistake|quiz|before_after|secret|horror_story",
      "estimated_demand": "high|medium|low"
    }}
  ]
}}

Rules:
- Video titles must be dramatic and scroll-stopping
- Hook lines must create immediate tension or curiosity
- Prioritize ideas that appear in 3+ comments
- Only return JSON, no explanation"""

    try:
        raw = ask_llm(prompt, system="You are a viral content strategist. Reply ONLY with valid JSON.")
        data = extract_json(raw)
        return data.get("ideas", [])
    except Exception:
        return []


def save_ideas(ideas: list[dict]):
    existing = []
    try:
        if _IDEAS_FILE.exists():
            existing = json.loads(_IDEAS_FILE.read_text())
    except Exception:
        pass
    # Prepend new ideas, dedupe by title, keep 100
    titles = {i.get("video_title") for i in existing}
    new = [i for i in ideas if i.get("video_title") not in titles]
    combined = (new + existing)[:100]
    _IDEAS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _IDEAS_FILE.write_text(json.dumps(combined, indent=2, ensure_ascii=False))


def get_top_ideas(n: int = 5) -> list[dict]:
    """Returns top N high-demand video ideas for use in topic generation."""
    try:
        if _IDEAS_FILE.exists():
            ideas = json.loads(_IDEAS_FILE.read_text())
            high = [i for i in ideas if i.get("estimated_demand") == "high"]
            return (high or ideas)[:n]
    except Exception:
        pass
    return []


def run_comment_miner() -> dict:
    """Full pass: pull comments → mine ideas → save. Called nightly."""
    comments = pull_youtube_comments()
    if not comments:
        return {"ok": True, "note": "No comments yet — channel too new or API not configured"}

    ideas = mine_video_ideas(comments)
    save_ideas(ideas)

    return {
        "ok":           True,
        "comments_read": len(comments),
        "ideas_generated": len(ideas),
        "top_ideas":    ideas[:3],
    }
