"""Script Writing Agent — Stage 2.
Takes a topic/idea and generates a full YouTube script with hook, lesson, CTA.
Saves to local Firebase cache. Designed for 30-sec Shorts AND 4-5 min long videos.
"""
import json
from datetime import datetime
from pathlib import Path

import httpx
from .. import config

_SCRIPTS_DIR = Path.home() / "SaathiAI" / "scripts_cache"
_SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

_PERSONA_PATH = config.ROOT / "data" / "yeti_persona.json"


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


def load_persona() -> dict:
    """Load Mr. Yeti persona from yeti_persona.json."""
    try:
        return json.loads(_PERSONA_PATH.read_text())
    except Exception:
        return {}


def persona_system_prompt() -> str:
    """Format persona traits into a system prompt string."""
    p = load_persona()
    if not p:
        return "You are Mr. Yeti, a funny direct IELTS teacher."
    traits = ", ".join(p.get("traits", []))
    openers = "\n".join(f"  - {o}" for o in p.get("signature_openers", []))
    catchphrases = "\n".join(f"  - {c}" for c in p.get("catchphrases", []))
    forbidden = ", ".join(f'"{w}"' for w in p.get("forbidden_phrases", []))
    patterns = "\n".join(f"  - {s}" for s in p.get("speech_patterns", []))
    return f"""You are {p.get('name', 'Mr. Yeti')} — {p.get('tagline', '')}.
Personality traits: {traits}.
Tone: {p.get('tone', '')}
Speech patterns:
{patterns}
Signature openers (use one of these to start):
{openers}
Catchphrases (end with one of these):
{catchphrases}
NEVER say these words or phrases: {forbidden}.
Stay in character at all times. Short sentences. Speak to 'you' directly."""


_MR_YETI_SYSTEM = """You are a viral YouTube Shorts scriptwriter for Mr. Yeti — a funny, smart, brutally honest Pixar-style 3D animated Yeti who teaches IELTS.

Channel formula:
- Hook MUST stop the scroll in 3 seconds ("95% of IELTS students fail because of THIS")
- People click: "Why You Keep Getting Band 5", "The Mistake That Destroyed My Score", "Yeti Exposes IELTS Scam"
- People do NOT click: "IELTS Reading Tips", "IELTS Writing Lesson 12"
- Mr. Yeti's personality: funny + brutally honest. He reacts dramatically to mistakes.
- Always end with: "Practice free at pielts.web.app"
- Write for animation — include stage directions, Mr. Yeti reactions, sound effects in [brackets]

Content pillars:
1. HORROR STORIES — Mr. Yeti acts out student mistakes with dramatic reactions
2. BEFORE vs AFTER — Split screen Band 5 vs Band 8 difference
3. DON'T SAY THIS — Wrong word → Mr. Yeti reaction → Band 8 alternative
4. QUIZ CHALLENGE — Mr. Yeti asks question, 3-second countdown, huge retention
5. FUNNY INTERVIEWS — Mr. Yeti interviews unusual characters (zombie, alien, dragon) taking IELTS

Reply ONLY with valid JSON."""

_SHORT_PROMPT = """Write a Mr. Yeti YouTube SHORT script (max 60 sec / ~150 words).

Topic: {topic}
Content type: {content_type}
Pillar: {pillar}

FORMAT (strict JSON):
{{
  "title": "Viral YouTube title — emotionally charged, not generic",
  "hook": "First 3 seconds of narration — shocking/bold/question. Must stop the scroll.",
  "scene_directions": "Animation stage directions for the full video [Mr. Yeti reactions, sound effects, text overlays]",
  "narration": "Full word-for-word script with Mr. Yeti dialogue and reactions in [brackets]",
  "cta": "Last 3 seconds — 'Practice free at pielts.web.app'",
  "overlay_text": "3-line text for video overlay",
  "thumbnail_text": "Bold 4-word thumbnail text",
  "tags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8"],
  "hashtags": "#IELTS #IELTSTips #Shorts #MrYeti",
  "difficulty": "beginner|intermediate|advanced",
  "duration_sec": 45,
  "pillar": "{pillar}"
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


def generate_script(topic: str, content_type: str = "tip", format: str = "short",
                    pillar: str = "horror_story", persona: bool = True) -> dict:
    """
    Generate a Mr. Yeti YouTube script via ChatGPT (falls back to Groq/Gemini).
    format: 'short' (60 sec) | 'long' (4-5 min)
    content_type: 'vocab' | 'tip' | 'mistake' | 'strategy' | 'speaking' | 'writing'
    pillar: 'horror_story' | 'before_after' | 'dont_say' | 'quiz' | 'interview'
    persona: if True, inject loaded persona traits into system prompt
    """
    prompt_template = _SHORT_PROMPT if format == "short" else _LONG_PROMPT
    prompt = prompt_template.format(topic=topic, content_type=content_type, pillar=pillar)

    try:
        from ._llm_helper import ask_llm
        system = persona_system_prompt() if persona else _MR_YETI_SYSTEM
        reply = ask_llm(prompt, system=system, timeout=60)

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
        script["pillar"] = pillar
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
