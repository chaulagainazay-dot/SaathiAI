"""SEO Generator — Stage 8.
Takes a script/topic and generates full SEO package for YouTube, TikTok, Instagram, Facebook.
Self-improving: tracks which hashtags/titles perform and adapts.
"""
import json
from datetime import datetime
from pathlib import Path

import httpx

_SEO_DIR = Path.home() / "SaathiAI" / "seo_cache"
_SEO_DIR.mkdir(parents=True, exist_ok=True)

_PERFORMANCE_LOG = _SEO_DIR / "performance_log.json"


def _get_token() -> str:
    try:
        for line in (Path.home() / "SaathiAI" / ".env").read_text().splitlines():
            if line.startswith("SAATHI_TOKEN="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def _load_performance() -> dict:
    if _PERFORMANCE_LOG.exists():
        return json.loads(_PERFORMANCE_LOG.read_text())
    return {"top_hashtags": [], "top_titles": [], "avg_views": {}}


_SEO_PROMPT = """You are an expert YouTube/TikTok SEO specialist for IELTS education content.

Video topic: {topic}
Script hook: {hook}
Target audience: IELTS students (band 5-7 target), aged 18-35, South/Southeast Asia focus
Channel: @pieltsapp — Mr. Yeti IELTS teacher

Performance data from past videos: {perf_data}

Generate a complete SEO package. Return STRICT JSON:
{{
  "youtube": {{
    "title": "Keyword-rich title, max 70 chars, include IELTS + power word",
    "description": "Full 500-word description. Line 1: bold hook. Line 2-3: what they learn. Lines 4-10: timestamps. Line 11+: keywords naturally. End: links to pielts.web.app, social handles.",
    "tags": ["tag1"..."tag20"],
    "hashtags": "#IELTS #IELTSTips #Shorts — 5 hashtags",
    "category": "Education",
    "thumbnail_alt": "Alt text for thumbnail"
  }},
  "tiktok": {{
    "caption": "Hook first line (stops scroll), 3 lines max, 150 chars. Conversational.",
    "hashtags": "#IELTS #IELTSTips #LearnEnglish #Shorts #fyp #foryou — 10 tags"
  }},
  "instagram": {{
    "caption": "Strong opener + 3-5 value lines + CTA. 300 chars. Link in bio mention.",
    "hashtags": "#IELTS #IELTSPrep #EnglishLearning #StudyAbroad #IELTSVocabulary — 25 tags"
  }},
  "facebook": {{
    "caption": "Longer conversational post. 3 paragraphs. Ask a question at end. Tag @pieltsapp.",
    "hashtags": "#IELTS #IELTSTips #LearnEnglish"
  }},
  "self_improvement_note": "One sentence: what to try differently next time based on performance data"
}}"""


def generate_seo_package(topic: str, hook: str = "", script_path: str = "") -> dict:
    """Generate full cross-platform SEO package for a video."""
    perf = _load_performance()
    perf_summary = f"Top hashtags: {perf.get('top_hashtags', [])[:5]}. Avg views by type: {perf.get('avg_views', {})}"

    if script_path:
        try:
            script_data = json.loads(Path(script_path).read_text())
            hook = hook or script_data.get("hook", "")[:200]
            topic = topic or script_data.get("title", topic)
        except Exception:
            pass

    prompt = _SEO_PROMPT.format(topic=topic, hook=hook[:200], perf_data=perf_summary)

    try:
        from ._llm_helper import ask_llm
        reply = ask_llm(prompt, timeout=60)

        import re
        match = re.search(r'\{.*\}', reply, re.DOTALL)
        if match:
            raw = match.group(0)
            # Strip control chars that break JSON parsing
            raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw)
            seo = json.loads(raw)
        else:
            seo = {"raw": reply}

        seo["topic"] = topic
        seo["generated_at"] = datetime.now().isoformat()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        cache_file = _SEO_DIR / f"seo_{ts}.json"
        cache_file.write_text(json.dumps(seo, indent=2, ensure_ascii=False))
        (_SEO_DIR / "latest.json").write_text(json.dumps(seo, indent=2, ensure_ascii=False))

        return {"ok": True, **seo, "cache_path": str(cache_file)}

    except Exception as e:
        return {"ok": False, "error": str(e)}


def log_video_performance(video_id: str, platform: str, views: int, likes: int, hashtags: list[str]):
    """Call this after a video goes live to feed the self-improvement loop."""
    perf = _load_performance()

    # Track which hashtags correlate with higher views
    for tag in hashtags:
        existing = next((t for t in perf.get("top_hashtags", []) if t["tag"] == tag), None)
        if existing:
            existing["total_views"] = existing.get("total_views", 0) + views
            existing["uses"] = existing.get("uses", 0) + 1
            existing["avg"] = existing["total_views"] / existing["uses"]
        else:
            perf.setdefault("top_hashtags", []).append({
                "tag": tag, "total_views": views, "uses": 1, "avg": views
            })

    perf["top_hashtags"] = sorted(perf["top_hashtags"], key=lambda x: x.get("avg", 0), reverse=True)[:30]

    avg = perf.get("avg_views", {})
    avg[platform] = (avg.get(platform, 0) + views) / 2
    perf["avg_views"] = avg

    _PERFORMANCE_LOG.write_text(json.dumps(perf, indent=2))
    return perf
