"""Daily content studio — Baadar runs Ajay's IELTS/study-abroad social operation.

Generates a full multi-platform content pack (TikTok/Reel script + LinkedIn +
Facebook + Instagram caption + hashtags) for pielts.web.app, saves it, and can
turn the script into an AI avatar video (D-ID, activates with DID_API_KEY).
"""
import datetime as dt
import json
import os
import re

from .. import config

CONTENT_DIR = config.ROOT / "data" / "content"

NICHE = (
    "Ajay is an IELTS teacher promoting his free IELTS practice app pielts.web.app. "
    "Audience: Nepali and South-Asian students preparing for IELTS and planning to "
    "study/move abroad. Tone: encouraging, practical, authentic, slightly personal "
    "(he's going abroad himself). Always work in a natural mention of pielts.web.app.")


def generate_content_pack(topic: str = "") -> dict:
    """Create today's full content pack. If topic is empty, Baadar picks one."""
    from ..agent import SaathiAgent
    agent = SaathiAgent()
    ask_topic = topic or "pick one fresh, specific IELTS / study-abroad topic for today"
    system = (
        "You are Baadar, running Ajay's daily social media. " + NICHE + "\n"
        "Produce ONE day's content as STRICT JSON with these keys:\n"
        '{"topic": "...", '
        '"tiktok_script": "60-90 sec spoken script with a 3-sec hook, one clear tip, '
        'and a call to action to pielts.web.app", '
        '"linkedin": "professional 120-180 word post, teacher voice, 2-3 hashtags", '
        '"facebook": "warm casual 60-100 word post for students", '
        '"instagram": "punchy caption", '
        '"hashtags": "10-15 relevant hashtags as one string", '
        '"video_caption": "short on-screen title for the video"}\n'
        "Return ONLY the JSON, no markdown fences.")
    raw = agent.complete(system, f"Topic: {ask_topic}", max_tokens=900)
    pack = _parse_json(raw)
    if not pack:
        return {"error": "could not generate content, try again", "raw": raw[:200]}
    pack["date"] = dt.date.today().isoformat()
    _save(pack)
    return pack


def todays_content() -> dict:
    """Return today's saved content pack (or note that none exists yet)."""
    path = CONTENT_DIR / f"{dt.date.today().isoformat()}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"note": "No content generated for today yet. Say 'Baadar, make today's "
                    "content' or give a topic."}


def make_avatar_video(script: str = "") -> dict:
    """Turn the script into an AI avatar talking-head video via D-ID."""
    import httpx
    key = os.getenv("DID_API_KEY", "")
    if not key:
        return {"setup_needed": True,
                "message": "Avatar video needs a D-ID API key (free trial at d-id.com). "
                           "Add DID_API_KEY to .env. Free tier is limited (few videos, "
                           "watermark); daily custom-avatar realistically needs a paid "
                           "plan. The script is ready to use meanwhile."}
    if not script:
        script = todays_content().get("tiktok_script", "")
    if not script:
        return {"error": "no script available — generate content first"}
    presenter = os.getenv("DID_PRESENTER_URL", "")  # Ajay's photo URL, optional
    try:
        body = {"script": {"type": "text", "input": script[:1500]}}
        if presenter:
            body["source_url"] = presenter
        r = httpx.post("https://api.d-id.com/talks",
                       headers={"Authorization": f"Basic {key}"}, json=body, timeout=60)
        r.raise_for_status()
        return {"status": "video_requested", "id": r.json().get("id"),
                "note": "Video is rendering at D-ID; check your D-ID dashboard / it "
                        "will be ready shortly."}
    except Exception as e:
        return {"error": str(e)[:200]}


# ---------- helpers ----------

def _save(pack: dict):
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    (CONTENT_DIR / f"{pack['date']}.json").write_text(
        json.dumps(pack, ensure_ascii=False, indent=2))


def _parse_json(raw: str) -> dict | None:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None
