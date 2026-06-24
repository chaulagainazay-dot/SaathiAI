"""
A/B Hook Testing System

For every video:
  - Generate 10 title variants + 10 opening-line variants
  - Pick 2 best hooks (A and B) using LLM scoring
  - Post same video twice with different hooks (different time slots)
  - Track which gets more views in 48h
  - Winning patterns feed back into future hook generation

Also: Flow 12 Thumbnail Optimizer — generate 5 thumbnail prompts, score by predicted CTR.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .. import config
from ._llm_helper import ask_llm, extract_json
from .mr_yeti_strategy import HOOK_FORMULAS, AB_HOOKS_PER_VIDEO

_AB_LOG_FILE = config.ROOT / "data" / "ab_test_log.json"


# ── Hook generation ────────────────────────────────────────────────────────────

def generate_hooks(topic: str, clip_type: str, n: int = 10) -> dict:
    """
    Generate N title variants and N opening lines for a video topic.
    Returns {"titles": [...], "hooks": [...], "recommended_a": ..., "recommended_b": ...}
    """
    formula_examples = "\n".join(f"  - {f}" for f in HOOK_FORMULAS[:6])

    prompt = f"""You are a viral YouTube Shorts / TikTok hook writer for Mr. Yeti, an IELTS teacher Yeti character.

TOPIC: {topic}
CLIP TYPE: {clip_type}

Generate {n} different TITLE variants and {n} different OPENING LINE variants.
Titles must be scroll-stopping. Opening lines must hook within 3 seconds.

Example hook formulas:
{formula_examples}

Return JSON:
{{
  "titles": [
    {{"text": "title here", "formula": "which formula used", "score": 1-10}}
  ],
  "opening_lines": [
    {{"text": "opening 3 seconds here", "emotion": "shock|curiosity|fear|humor", "score": 1-10}}
  ],
  "recommended_a": {{"title": "best title", "opening": "best opening — highest predicted CTR"}},
  "recommended_b": {{"title": "second best title", "opening": "second best — different angle"}}
}}

Rules for Mr. Yeti style:
- Sarcastic but never mean
- Band 7 is sacred, Band 5 is dramatic tragedy
- Start with the problem, never the lesson
- Never say "today we will learn"
- Only return JSON"""

    try:
        raw = ask_llm(
            prompt,
            system="You are a viral content hook writer. Reply ONLY with valid JSON.",
            max_tokens=2000,
        )
        data = extract_json(raw)
        return data
    except Exception as e:
        return {"titles": [], "opening_lines": [], "error": str(e)[:200]}


# ── A/B test tracking ──────────────────────────────────────────────────────────

def record_ab_test(
    video_path: str,
    variant_a: dict,
    variant_b: dict,
    date: str = "",
) -> str:
    """Log an A/B test pair. Returns test_id."""
    test_id = f"ab_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    entry = {
        "test_id":    test_id,
        "video_path": video_path,
        "date":       date or datetime.now().strftime("%Y-%m-%d"),
        "variant_a":  variant_a,
        "variant_b":  variant_b,
        "result":     None,   # filled in after 48h analytics check
        "winner":     None,
    }
    log = _load_log()
    log.append(entry)
    _save_log(log)
    return test_id


def record_result(test_id: str, views_a: int, views_b: int):
    """After 48h, record which variant won."""
    log = _load_log()
    for entry in log:
        if entry["test_id"] == test_id:
            entry["result"] = {"views_a": views_a, "views_b": views_b}
            entry["winner"] = "a" if views_a >= views_b else "b"
            break
    _save_log(log)


def get_winning_patterns() -> dict:
    """
    Analyze all completed A/B tests.
    Returns patterns that consistently outperform.
    """
    log = _load_log()
    completed = [e for e in log if e.get("winner")]
    if not completed:
        return {"patterns": [], "note": "No completed A/B tests yet"}

    winning_titles   = []
    winning_formulas = []
    winning_emotions = []

    for entry in completed:
        winner_key = entry["winner"]
        variant = entry.get(f"variant_{winner_key}", {})
        title = variant.get("title", {})
        opening = variant.get("opening", {})

        if isinstance(title, dict):
            winning_titles.append(title.get("text", ""))
            winning_formulas.append(title.get("formula", ""))
        if isinstance(opening, dict):
            winning_emotions.append(opening.get("emotion", ""))

    # Count frequencies
    from collections import Counter
    formula_counts = Counter(winning_formulas)
    emotion_counts = Counter(winning_emotions)

    return {
        "total_tests":       len(completed),
        "top_formulas":      formula_counts.most_common(3),
        "top_emotions":      emotion_counts.most_common(3),
        "recent_winners":    winning_titles[-5:],
    }


# ── Thumbnail optimizer (Flow 12) ─────────────────────────────────────────────

def generate_thumbnail_variants(topic: str, video_title: str, n: int = 5) -> list[dict]:
    """
    Generate N thumbnail concepts. Each includes an image gen prompt + CTR prediction.
    Returns list sorted by predicted CTR.
    """
    prompt = f"""You are a YouTube thumbnail designer for Mr. Yeti (white fluffy Yeti, round glasses, tweed jacket).

TOPIC: {topic}
VIDEO TITLE: {video_title}

Generate {n} thumbnail concepts. Each must:
- Feature Mr. Yeti with a specific emotion/pose
- Have 3-5 word text overlay (big, bold, high contrast)
- Use a specific background that creates contrast
- Be optimized for mobile (large, simple, readable at small size)

Return JSON:
{{
  "thumbnails": [
    {{
      "concept": "one-line description",
      "yeti_emotion": "shocked|celebrating|facepalm|pointing|thinking",
      "text_overlay": "3-5 WORD OVERLAY",
      "background": "describe background",
      "color_scheme": "dominant colors",
      "image_gen_prompt": "detailed prompt for image AI (Midjourney/DALL-E)",
      "predicted_ctr_score": 1-10,
      "why_it_works": "one sentence"
    }}
  ]
}}

Only return JSON."""

    try:
        raw = ask_llm(
            prompt,
            system="You are a thumbnail CTR optimization expert. Reply ONLY with valid JSON.",
            max_tokens=2000,
        )
        data = extract_json(raw)
        thumbnails = data.get("thumbnails", [])
        return sorted(thumbnails, key=lambda t: t.get("predicted_ctr_score", 0), reverse=True)
    except Exception as e:
        return [{"error": str(e)[:200]}]


# ── Persistence ────────────────────────────────────────────────────────────────

def _load_log() -> list:
    try:
        if _AB_LOG_FILE.exists():
            return json.loads(_AB_LOG_FILE.read_text())
    except Exception:
        pass
    return []


def _save_log(log: list):
    _AB_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _AB_LOG_FILE.write_text(json.dumps(log[-200:], indent=2, ensure_ascii=False))
