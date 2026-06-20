"""Script Writing Agent — Stage 2.
Takes a topic/idea and generates a full YouTube script with hook, lesson, CTA.
Saves to local Firebase cache. Designed for 30-sec Shorts AND 4-5 min long videos.
"""
import json
from datetime import datetime
from pathlib import Path

import httpx

_SCRIPTS_DIR = Path.home() / "SaathiAI" / "scripts_cache"
_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)


def _get_token() -> str:
    import os
    from pathlib import Path as _Path
    try:
        for line in (_Path.home() / "SaathiAI" / ".env").read_text().splitlines():
            if line.startswith("SAATHI_TOKEN="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return os.getenv("SAATHI_TOKEN", "")


_SHORT_PROMPT = """You are Mr. Yeti, an enthusiastic IELTS teacher. Write a YouTube SHORT script (max 60 sec / ~150 words).

Topic: {topic}
Content type: {content_type}

FORMAT (strict JSON):
{{
  "title": "Engaging YouTube title with keyword",
  "hook": "Opening 10 seconds — shocking fact, question, or bold statement that stops the scroll",
  "lesson": "Core 40-second lesson — clear, simple, actionable. Use 1 example sentence.",
  "cta": "Final 10 seconds — 'Follow for daily IELTS tips! Practice free at pielts.web.app'",
  "overlay_text": "3-line text for video overlay (word/tip/hook)",
  "thumbnail_text": "Bold 4-word thumbnail text",
  "tags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8"],
  "hashtags": "#IELTS #IELTSTips #Shorts",
  "difficulty": "beginner|intermediate|advanced",
  "duration_sec": 45
}}"""

_LONG_PROMPT = """You are Mr. Yeti, expert IELTS teacher. Write a full YouTube video script (4-5 minutes / ~700 words).

Topic: {topic}
Content type: {content_type}

FORMAT (strict JSON):
{{
  "title": "SEO-optimized YouTube title",
  "hook": "Opening 30 seconds — powerful question or shocking statistic. End with 'Stay till the end...'",
  "intro": "30-second intro — who you are, what they'll learn today",
  "lesson_sections": [
    {{"heading": "Section 1 title", "script": "90-second detailed explanation with example"}},
    {{"heading": "Section 2 title", "script": "90-second detailed explanation with example"}},
    {{"heading": "Section 3 title", "script": "60-second actionable practice tip"}}
  ],
  "summary": "30-second recap of key points",
  "cta": "30-second CTA — subscribe, practice at pielts.web.app, comment their answer",
  "thumbnail_text": "Bold 4-word thumbnail text",
  "description": "Full YouTube description (300 words) with timestamps, keywords, links",
  "tags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8","tag9","tag10"],
  "hashtags": "#IELTS #IELTSTips #LearnEnglish",
  "difficulty": "beginner|intermediate|advanced",
  "duration_min": 4.5
}}"""


def generate_script(topic: str, content_type: str = "tip", format: str = "short") -> dict:
    """
    Generate a complete YouTube script.
    format: 'short' (60 sec) | 'long' (4-5 min)
    content_type: 'vocab' | 'tip' | 'mistake' | 'strategy' | 'speaking' | 'writing'
    """
    prompt_template = _SHORT_PROMPT if format == "short" else _LONG_PROMPT
    prompt = prompt_template.format(topic=topic, content_type=content_type)

    try:
        from ._llm_helper import ask_llm
        reply = ask_llm(prompt, timeout=60)

        import re
        match = re.search(r'\{.*\}', reply, re.DOTALL)
        if match:
            raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', match.group(0))
            script = json.loads(raw)
        else:
            script = {"raw": reply, "title": topic}

        script["topic"] = topic
        script["content_type"] = content_type
        script["format"] = format
        script["generated_at"] = datetime.now().isoformat()

        # Save to cache
        slug = topic.lower().replace(" ", "_")[:40]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        cache_file = _SCRIPTS_DIR / f"script_{ts}_{slug}.json"
        cache_file.write_text(json.dumps(script, indent=2, ensure_ascii=False))
        (_SCRIPTS_DIR / "latest.json").write_text(json.dumps(script, indent=2, ensure_ascii=False))

        return {"ok": True, **script, "cache_path": str(cache_file)}

    except Exception as e:
        return {"ok": False, "error": str(e), "topic": topic}


def get_latest_script() -> dict:
    latest = _SCRIPTS_DIR / "latest.json"
    if latest.exists():
        return json.loads(latest.read_text())
    return {"error": "No scripts yet"}
