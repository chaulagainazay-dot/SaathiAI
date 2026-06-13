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


def make_video(script: str = "", handle: str = "@pieltsapp",
               image_path: str = "") -> dict:
    """Create a vertical (1080x1920) captioned TikTok/Reel video with voiceover —
    free and local. Uses the Mr. Yeti mascot image as a header if given/available."""
    import subprocess
    import tempfile
    import textwrap
    from pathlib import Path as _P

    from PIL import Image, ImageDraw, ImageFont
    from .. import voice

    if not script:
        script = todays_content().get("tiktok_script", "")
    if not script:
        return {"error": "no script — generate content first"}

    # default to the Mr. Yeti mascot if present
    if not image_path:
        for cand in ("~/Downloads/Yeti.jpeg", "~/Downloads/Yeti 1.jpeg"):
            if _P(cand).expanduser().exists():
                image_path = str(_P(cand).expanduser())
                break
    mascot = None
    if image_path and _P(image_path).expanduser().exists():
        mascot = Image.open(_P(image_path).expanduser()).convert("RGB")

    out_dir = CONTENT_DIR / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    work = _P(tempfile.mkdtemp())
    ff = voice._ffmpeg()
    font_path = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"

    # 1. voiceover (cloned voice if enabled, else built-in)
    audio, mime = voice.synthesize(script, "en")
    aud_ext = ".mp3" if mime == "audio/mpeg" else ".wav"
    aud = work / f"voice{aud_ext}"
    aud.write_bytes(audio)
    dur = float(subprocess.run(
        [ff.replace("ffmpeg", "ffprobe"), "-v", "quiet", "-show_entries",
         "format=duration", "-of", "csv=p=0", str(aud)],
        capture_output=True, text=True).stdout.strip() or "30")

    # 2. split script into caption slides (~12 words each)
    words = script.replace("\n", " ").split()
    slides = [" ".join(words[i:i + 12]) for i in range(0, len(words), 12)] or [script]
    per = max(dur / len(slides), 1.0)

    # 3. render each slide as a 1080x1920 PNG
    W, H = 1080, 1920
    big = ImageFont.truetype(font_path, 60)
    small = ImageFont.truetype(font_path, 44)
    brand = ImageFont.truetype(font_path, 40)
    # pre-fit the mascot into a top banner (square crop, centered)
    banner = None
    if mascot is not None:
        side = min(mascot.size)
        sq = mascot.crop(((mascot.width - side) // 2, 0,
                          (mascot.width + side) // 2, side))
        banner = sq.resize((W, W))  # 1080x1080 top square

    for idx, text in enumerate(slides):
        img = Image.new("RGB", (W, H), (15, 15, 35))
        if banner is not None:
            img.paste(banner, (0, 80))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 14], fill=(124, 58, 237))
        wrapped = textwrap.fill(text, width=24)
        cy = 1380 if banner is not None else H // 2  # text below the mascot
        # dark caption band for readability
        bbox = d.multiline_textbbox((0, 0), wrapped, font=big, spacing=16)
        bh = bbox[3] - bbox[1]
        d.rectangle([0, cy - bh / 2 - 40, W, cy + bh / 2 + 40], fill=(15, 15, 35))
        d.multiline_text((W / 2, cy), wrapped, font=big, fill="white",
                         anchor="mm", align="center", spacing=16)
        d.text((W / 2, H - 210), "pielts.web.app", font=small,
               fill=(167, 139, 250), anchor="mm")
        d.text((W / 2, H - 140), handle, font=brand, fill=(160, 160, 170), anchor="mm")
        img.save(work / f"s{idx:03d}.png")

    # 4. concat slides + audio into an MP4
    listf = work / "list.txt"
    lines = []
    for idx in range(len(slides)):
        lines.append(f"file 's{idx:03d}.png'")
        lines.append(f"duration {per:.2f}")
    lines.append(f"file 's{len(slides) - 1:03d}.png'")  # last frame held
    listf.write_text("\n".join(lines))

    ts = dt.date.today().isoformat()
    out = out_dir / f"pielts-{ts}.mp4"
    cmd = [ff, "-y", "-f", "concat", "-safe", "0", "-i", str(listf),
           "-i", str(aud), "-pix_fmt", "yuv420p", "-vf", "fps=30",
           "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if p.returncode != 0 or not out.exists():
        return {"error": "video build failed", "detail": p.stderr[-300:]}
    return {"video": str(out), "duration_sec": round(dur, 1), "slides": len(slides),
            "note": f"Faceless captioned video ready at {out.name}. AirDrop it to your "
                    "phone and post to TikTok @pieltsapp, or ask me to open it."}


def send_today_video(path: str = "", caption: str = "") -> dict:
    """Send today's (or a given) video to Ajay's phone via Telegram."""
    from . import n8n_tools
    import datetime as _dt
    if not path:
        path = str(CONTENT_DIR / "videos" / f"pielts-{_dt.date.today().isoformat()}.mp4")
    return n8n_tools.send_video(path, caption or "Your pielts video — ready for TikTok @pieltsapp 🎯")


def elevenlabs_voiceover(text: str, out_path: str = "") -> dict:
    """Generate a premium natural voiceover with ElevenLabs. Returns the audio path."""
    import httpx
    key = os.getenv("ELEVENLABS_API_KEY", "")
    if not key:
        return {"setup_needed": True,
                "message": "Add ELEVENLABS_API_KEY to .env (free tier at elevenlabs.io)."}
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # 'Rachel' default
    out = out_path or str(CONTENT_DIR / "audio" /
                          f"vo-{dt.date.today().isoformat()}.mp3")
    from pathlib import Path as _P
    _P(out).parent.mkdir(parents=True, exist_ok=True)
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": key, "accept": "audio/mpeg"},
        json={"text": text, "model_id": "eleven_multilingual_v2",
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
        timeout=120)
    if r.status_code != 200:
        return {"error": f"ElevenLabs {r.status_code}", "detail": r.text[:200]}
    _P(out).write_bytes(r.content)
    return {"audio": out, "bytes": len(r.content)}


def make_animated_video(script: str = "", image_path: str = "") -> dict:
    """Full animated talking-Mr.Yeti video: ElevenLabs voiceover + HeyGen avatar.

    Needs ELEVENLABS_API_KEY and HEYGEN_API_KEY (+ a HeyGen talking-photo id for the
    Yeti, set as HEYGEN_TALKING_PHOTO_ID). Returns a HeyGen video job to poll.
    """
    import httpx
    if not script:
        script = todays_content().get("tiktok_script", "")
    if not script:
        return {"error": "no script — generate content first"}

    hk = os.getenv("HEYGEN_API_KEY", "")
    if not hk:
        return {"setup_needed": True,
                "message": "Animated video needs HeyGen. Add HEYGEN_API_KEY (and "
                           "HEYGEN_TALKING_PHOTO_ID for the Mr. Yeti avatar) to .env. "
                           "HeyGen API requires a paid plan (~$29/mo). The script + "
                           "ElevenLabs voiceover are ready meanwhile."}

    talking_photo_id = os.getenv("HEYGEN_TALKING_PHOTO_ID", "")
    if not talking_photo_id:
        return {"setup_needed": True,
                "message": "Upload the Mr. Yeti image to HeyGen as a Talking Photo, then "
                           "put its id in HEYGEN_TALKING_PHOTO_ID in .env."}

    # voiceover first (ElevenLabs) — fall back to HeyGen's own voice if not set
    voice_payload = {"type": "text", "input_text": script,
                     "voice_id": os.getenv("HEYGEN_VOICE_ID", "1bd001e7e50f421d891986aad5158bc8")}

    body = {
        "video_inputs": [{
            "character": {"type": "talking_photo", "talking_photo_id": talking_photo_id},
            "voice": voice_payload,
        }],
        "dimension": {"width": 720, "height": 1280},  # vertical for TikTok
    }
    r = httpx.post("https://api.heygen.com/v2/video/generate",
                   headers={"X-Api-Key": hk, "Content-Type": "application/json"},
                   json=body, timeout=60)
    if r.status_code not in (200, 201):
        return {"error": f"HeyGen {r.status_code}", "detail": r.text[:300]}
    vid = r.json().get("data", {}).get("video_id")
    return {"status": "rendering", "video_id": vid,
            "note": "HeyGen is animating Mr. Yeti. Ask me to 'check the animated video' "
                    "in a minute, or check your HeyGen dashboard."}


def check_heygen_video(video_id: str) -> dict:
    """Poll a HeyGen video job; when done, download it to the videos folder."""
    import httpx
    hk = os.getenv("HEYGEN_API_KEY", "")
    if not hk:
        return {"error": "HEYGEN_API_KEY not set"}
    r = httpx.get("https://api.heygen.com/v1/video_status.get",
                  headers={"X-Api-Key": hk}, params={"video_id": video_id}, timeout=30)
    data = r.json().get("data", {})
    status = data.get("status")
    if status != "completed":
        return {"status": status, "video_id": video_id}
    url = data.get("video_url")
    out = CONTENT_DIR / "videos" / f"pielts-animated-{dt.date.today().isoformat()}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(httpx.get(url, timeout=180).content)
    return {"status": "completed", "video": str(out)}


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
