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
    "Content for pielts.web.app — a free IELTS practice app. The face of the brand is "
    "MR. YETI: a warm, funny, wise professor-yeti from the Himalayas (glasses, tweed "
    "jacket, pointer at a whiteboard) who teaches IELTS. Audience: Nepali and South-Asian "
    "students preparing for IELTS and planning to study/move abroad, but content must be "
    "fun and simple enough for ALL ages. Mr. Yeti is the narrator and speaks in FIRST "
    "PERSON as the yeti (never 'it's Ajay'). Personality: cheerful, encouraging, a little "
    "playful, big-hearted teacher. Always work in a natural mention of pielts.web.app.")

# The repeatable viral structure every short script must follow.
# Formula locked in from the Growth Hacker plan (Jun 2026): proven hooks + content
# pillars that maximise saves/shares and the swipe-to-subscribe motion.
VIRAL_RULES = (
    "Write tiktok_script as MR. YETI speaking, 15-35 seconds (about 45-90 words):\n"
    "1) HOOK in the FIRST 2 SECONDS — the only thing that matters. Use ONE proven formula: "
    "loss-aversion ('This one word is killing your Speaking band'), number-promise ('3 linkers "
    "that instantly sound Band 8'), direct call-out ('If you say nowadays in your essay, stop'), "
    "curiosity-gap ('Examiners never tell you this about Part 2…'), or contrast ('Band 5 says "
    "this. Band 8 says this'). Say the hook AND show it as on-screen text. Then his signature "
    "'Namaste! Yeti here!' AFTER the hook (never before — no slow intro).\n"
    "2) Pick ONE content PILLAR for the lesson: (a) Quick Win / one trick, (b) Mistake or myth "
    "to fix, (c) Band 5 vs Band 8 transformation, or (d) study-abroad-dream motivation. ONE tiny "
    "idea only — not a lecture.\n"
    "3) A concrete before/after example.\n"
    "4) Warm CTA to practise free on pielts.web.app (link in bio) PLUS one comment-bait "
    "question (e.g. 'What's your target band? Comment below!'). Loop the last line back to the "
    "hook so it replays.\n"
    "Simple, upbeat, wholesome for all ages, captions-on (most watch muted). Add light stage "
    "directions in (brackets), e.g. (shocked face), (thumbs up), (points to whiteboard).")


def generate_content_pack(topic: str = "") -> dict:
    """Create today's full content pack. If topic is empty, Baadar picks one."""
    from ..agent import SaathiAgent
    agent = SaathiAgent()
    ask_topic = topic or "pick one fresh, specific IELTS / study-abroad topic for today"
    system = (
        "You are Baadar, running the Mr. Yeti social media for pielts.web.app. " + NICHE + "\n\n"
        + VIRAL_RULES + "\n\n"
        "Produce ONE day's content as STRICT JSON with these keys:\n"
        '{"topic": "...", '
        '"tiktok_script": "Mr. Yeti short script following the viral rules above", '
        '"linkedin": "professional 120-180 word post in Mr. Yeti / teacher voice, 2-3 hashtags", '
        '"facebook": "warm casual 60-100 word post for students (Mr. Yeti voice)", '
        '"instagram": "punchy caption with 1-2 emojis", '
        '"youtube_title": "click-worthy YouTube Shorts title with the key benefit", '
        '"hashtags": "10-15 relevant hashtags as one string", '
        '"video_caption": "short punchy on-screen title for the video"}\n'
        "Return ONLY the JSON, no markdown fences.")
    raw = agent.complete(system, f"Topic: {ask_topic}", max_tokens=900)
    pack = _parse_json(raw)
    if not pack:
        return {"error": "could not generate content, try again", "raw": raw[:200]}
    pack["date"] = dt.date.today().isoformat()
    _save(pack)
    return pack


# FIXED character + voice — identical in EVERY video for brand consistency.
MR_YETI_LOOK = ("fluffy white yeti professor, round black glasses, brown tweed blazer, "
                "light-blue collared shirt, navy polka-dot tie, tan trousers, Pixar 3D cartoon style")
MR_YETI_VOICE = ("a warm, friendly, middle-aged male voice with a clear American accent, "
                 "cheerful and encouraging")

FLOW_SCENE_RULES = (
    "Break the lesson into 6-8 short SCENE PROMPTS for Google Flow (Veo 3). MR YETI is a FIXED, "
    "consistent saved character — ALWAYS the same: " + MR_YETI_LOOK + ". "
    "Each scene = ONE ~8-second shot. ONLY Mr Yeti's look and voice stay fixed — the SETTING, "
    "background, props, camera angle and his actions should CHANGE to fit the topic and keep it "
    "visually interesting (e.g. a café for speaking practice, a desk with papers for writing, a "
    "library for reading, an airport for travel vocab). Vary the scenes; don't repeat the same room. "
    "For each scene write: a camera/shot + Mr Yeti's action and expression, then his spoken line "
    "in double quotes (Veo voices it with matching lip-sync — keep each line short, ~1 sentence). "
    "CRITICAL — SAME VOICE EVERY TIME: in EVERY scene Mr Yeti must speak in the SAME voice — "
    + MR_YETI_VOICE + ". Include this exact voice description in every single scene so the voice "
    "is identical across all videos. "
    "End every scene with 'Pixar 3D cartoon style, smooth animation.' Scene 1 must open with him "
    "waving and saying \"Namaste! I'm Mr Yeti, your IELTS coach.\" The LAST scene is a warm CTA: "
    "tell viewers to practise free on 'P-IELTS dot web dot app' plus one comment-bait question. "
    "Do NOT add any separate narration — only the in-scene dialogue (Veo generates the audio).")


def make_flow_prompts(topic: str = "") -> dict:
    """Generate ready-to-paste Google Flow (Veo) SCENE PROMPTS for a Mr Yeti video.
    Each scene has the shot + Mr Yeti's action + his spoken line (Veo voices it, lips synced).
    Ajay pastes each into Flow with the saved Mr Yeti character, then stitches + captions in CapCut."""
    from ..agent import SaathiAgent
    agent = SaathiAgent()
    ask = topic or "pick one fresh, specific, high-value IELTS tip for today"
    system = (
        "You are Baadar, scripting a Mr Yeti IELTS short video for Google Flow (Veo 3). " + NICHE
        + "\n\n" + FLOW_SCENE_RULES + "\n\n"
        "Return ONLY STRICT JSON (no markdown):\n"
        '{"topic": "...", "youtube_title": "click-worthy title", '
        '"caption": "short post caption with 1-2 emojis", '
        '"hashtags": "10-15 hashtags as one string", '
        '"scenes": ["full scene 1 prompt", "full scene 2 prompt", "..."]}')
    raw = agent.complete(system, f"Topic: {ask}", max_tokens=1600)
    pack = _parse_json(raw)
    if not pack or not pack.get("scenes"):
        return {"error": "could not generate Flow prompts, try again", "raw": raw[:200]}
    pack["date"] = dt.date.today().isoformat()
    pack["tool"] = "google-flow-veo"
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    (CONTENT_DIR / f"flow-{pack['date']}.json").write_text(
        json.dumps(pack, ensure_ascii=False, indent=2))
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

    # 0. strip (stage directions) / labels so they're neither spoken nor shown on screen
    script = _clean_for_speech(script)

    # 1. voiceover — best available: ElevenLabs > OmniVoice professor > built-in
    audio, mime = _voiceover(script)
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
    script = _clean_for_speech(script)

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

def make_talking_yeti(script: str = "", image_path: str = "") -> dict:
    """FREE local animated talking Mr. Yeti: cloned OmniVoice voice -> Wav2Lip lip-sync.
    No API keys, no cost. Needs the Wav2Lip repo + checkpoint (WAV2LIP_DIR) and the
    OmniVoice backend running (for the cloned voice)."""
    import subprocess
    import tempfile
    from pathlib import Path as _P

    if not script:
        script = todays_content().get("tiktok_script", "")
    if not script:
        return {"error": "no script — generate content first"}
    script = _clean_for_speech(script)

    w2l = _P(os.getenv("WAV2LIP_DIR", "")) if os.getenv("WAV2LIP_DIR") else \
        _P("~/Downloads/talkingyeti/Wav2Lip").expanduser()
    py = w2l / ".venv" / "bin" / "python"
    ckpt = w2l / "checkpoints" / "wav2lip_gan.pth"
    if not py.exists() or not ckpt.exists():
        return {"setup_needed": True,
                "message": f"Wav2Lip not set up at {w2l}. Need the repo + .venv + "
                           "checkpoints/wav2lip_gan.pth."}

    if not image_path:
        for cand in ("~/Downloads/Yeti 1.jpeg", "~/Downloads/Yeti.jpeg"):
            if _P(cand).expanduser().exists():
                image_path = str(_P(cand).expanduser())
                break
    if not image_path:
        return {"error": "Yeti image not found in ~/Downloads"}

    # 1) cloned Mr. Yeti voiceover
    audio, mime = _voiceover(script)
    work = _P(tempfile.mkdtemp())
    aud = work / ("voice" + (".mp3" if "mpeg" in mime else ".wav"))
    aud.write_bytes(audio)

    # 2) lip-sync with Wav2Lip (runs in its OWN venv)
    out_dir = CONTENT_DIR / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"yeti-talking-{dt.date.today().isoformat()}.mp4"
    cmd = [str(py), "inference.py", "--checkpoint_path", str(ckpt),
           "--face", str(_P(image_path).expanduser()), "--audio", str(aud),
           "--outfile", str(out), "--pads", "0", "20", "0", "0", "--nosmooth"]
    p = subprocess.run(cmd, cwd=str(w2l), capture_output=True, text=True, timeout=900)
    if not out.exists():
        return {"error": "Wav2Lip render failed",
                "detail": (p.stderr or p.stdout or "")[-400:]}
    return {"video": str(out), "engine": "wav2lip (free, local)",
            "note": f"Animated talking Mr. Yeti ready at {out.name}. AirDrop to your "
                    "phone and post to @pieltsapp."}


def _clean_for_speech(text: str) -> str:
    """Strip (stage directions) and Hook:/Tip: labels so they aren't spoken or shown."""
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\b(Hook|Tip|CTA|Call to action|Lesson|Example)\s*:\s*", "", text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).strip()


def _voiceover(text: str) -> tuple[bytes, str]:
    """Best available voice for videos: ElevenLabs (expressive) > OmniVoice professor
    (free, local) > built-in. Returns (audio_bytes, mime)."""
    # 1) ElevenLabs — premium, expressive (uses ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID)
    key = os.getenv("ELEVENLABS_API_KEY", "")
    if key:
        try:
            import httpx
            vid = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
            r = httpx.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
                headers={"xi-api-key": key, "accept": "audio/mpeg"},
                json={"text": text, "model_id": "eleven_multilingual_v2",
                      "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.55}},
                timeout=120)
            if r.status_code == 200 and r.content:
                return r.content, "audio/mpeg"
        except Exception:
            pass
    # 2) OmniVoice — free local Mr. Yeti voice. Prefer the fixed CLONE profile
    #    (consistent voice every time); fall back to voice-design traits.
    try:
        import httpx
        base = os.getenv("OMNIVOICE_TTS_URL") or "http://127.0.0.1:3900"
        profile = os.getenv("YETI_VOICE_PROFILE", "")
        fields = {"text": text, "language": "English", "num_step": "28", "speed": "0.98"}
        if profile:
            fields["profile_id"] = profile           # exact cloned Mr. Yeti voice
        else:
            fields["instruct"] = "male, middle-aged, low pitch, american accent"
        r = httpx.post(f"{base}/generate", data=fields, timeout=240)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("audio"):
            return r.content, "audio/wav"
    except Exception:
        pass
    # 3) built-in fallback (macOS say)
    from .. import voice
    return voice.synthesize(text, "en")


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


def deploy_ielts_site() -> dict:
    """Rebuild (sitemap + prerender) and publish pielts.web.app. Run this after a new
    blog post is published so Google + AI search engines pick it up. PRIVILEGED."""
    import os
    import subprocess
    app = os.path.expanduser("~/Downloads/ielts-practice-app")
    if not os.path.isdir(app):
        return {"status": "error", "error": f"app dir not found: {app}"}
    # login shell so Homebrew's npm/firebase are on PATH even under launchd
    env = dict(os.environ, PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin")
    try:
        r = subprocess.run(["npm", "run", "deploy"], cwd=app, env=env,
                           capture_output=True, text=True, timeout=900)
        ok = r.returncode == 0
        tail = (r.stdout + "\n" + r.stderr).strip()[-500:]
        return {"status": "deployed" if ok else "failed", "ok": ok,
                "url": "https://pielts.web.app", "log_tail": tail}
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "deploy timed out (15 min)"}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


def publish_to_youtube(video_path: str, title: str, description: str = "", tags: str = "") -> dict:
    """Upload a video to the PIELTS YouTube channel via the connected n8n webhook.
    PRIVILEGED — only call after Ajay approves the exact video + title."""
    import os
    import httpx
    from .. import connections
    cfg = connections.get_all().get("youtube", {})
    url = cfg.get("webhook")
    if not cfg.get("connected") or not url:
        return {"status": "not_connected",
                "message": "YouTube isn't connected yet — set the n8n webhook in Connections."}
    import shutil
    p = os.path.expanduser(video_path)
    if not os.path.exists(p):
        return {"status": "error", "error": f"video not found: {p}"}
    # n8n's file node only reads from ~/.n8n-files — stage the video there first
    stage_dir = os.path.expanduser("~/.n8n-files")
    os.makedirs(stage_dir, exist_ok=True)
    staged = os.path.join(stage_dir, os.path.basename(p))
    try:
        shutil.copy2(p, staged)
    except Exception as e:
        return {"status": "error", "error": f"could not stage video: {e}"}
    try:
        r = httpx.post(url, json={"title": title, "description": description,
                                  "tags": tags, "videoPath": staged}, timeout=900)
        ok = r.status_code < 400
        if ok:
            try:
                vid = (r.json() or {}).get("uploadId", "")
                from .. import pielts
                pielts.log_upload(vid, title)
            except Exception:
                pass
            # clean up storage: remove the temp staged copy; move the original to Trash
            # (recoverable). Only runs after a CONFIRMED upload so nothing is lost on failure.
            try:
                os.remove(staged)
            except Exception:
                pass
            try:
                import time
                trash = os.path.expanduser("~/.Trash")
                if os.path.isdir(trash) and os.path.exists(p):
                    dest = os.path.join(trash, os.path.basename(p))
                    if os.path.exists(dest):
                        dest = f"{dest}.{int(time.time())}"
                    shutil.move(p, dest)
            except Exception:
                pass
        return {"status": "published" if ok else "failed", "http": r.status_code,
                "channel": "@pieltsapp", "response": r.text[:300]}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


def queue_video(video_path: str, title: str, description: str = "",
                tags: str = "", caption: str = "") -> dict:
    """Add a finished video to the daily 8pm auto-post queue (YouTube + FB/IG).
    PRIVILEGED. Baadar posts one queued video per day automatically."""
    import os
    from .. import autopost
    p = os.path.expanduser(video_path)
    if not os.path.exists(p):
        return {"status": "error", "error": f"video not found: {p}"}
    n = autopost.add(p, title, description, tags, caption)
    return {"status": "queued", "pending_in_queue": n, "title": title}
