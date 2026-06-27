"""Auto-reel maker for YouTube Shorts — 2x daily Mr. Yeti IELTS reels.

Morning: Vocab word of the day (6 AM)
Evening: IELTS tip / idea (6 PM)

Pipeline:
  1. Generate content (vocab/tip) via LLM
  2. Generate Mr. Yeti image via Pollinations AI
  3. Download royalty-free background music
  4. Compose 6-sec vertical video (1080x1920) with ffmpeg
  5. Return video path + YouTube metadata
"""

import hashlib
import json
import os
import random
import subprocess
import tempfile
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import httpx

# ── Directories ────────────────────────────────────────────────────────────────
_BASE = Path(__file__).resolve().parents[2]
_ASSETS = _BASE / "client" / "assets"
_MUSIC_DIR = _ASSETS / "music"
_REELS_DIR = _BASE / "reels_output"
_REELS_DIR.mkdir(exist_ok=True)
_MUSIC_DIR.mkdir(parents=True, exist_ok=True)

_YETI_REF   = _ASSETS / "mr_yeti_reference.jpeg"
_POSES_DIR  = _ASSETS / "yeti_poses"
_POSES_DIR.mkdir(parents=True, exist_ok=True)

# ── Locked Yeti character description (NEVER change this) ─────────────────────
_YETI_BASE = (
    "Mr. Yeti IELTS teacher character — EXACT consistent look: "
    "large broad-shouldered yeti, fluffy shaggy white/off-white fur, "
    "wide warm smile showing teeth, large dark-brown eyes, "
    "round black-rimmed glasses on a broad flat nose, "
    "brown herringbone tweed blazer, light-blue oxford shirt, navy polka-dot tie. "
    "Pixar/DreamWorks photorealistic 3D cinematic render. "
    "Warm studio lighting. Same character EVERY time. "
)

# ── Pre-defined poses with FIXED seeds (generates once, reused forever) ───────
_YETI_POSES = {
    "teaching": {
        "seed": 11111,
        "prompt": _YETI_BASE + "Standing at a chalkboard, pointing with one hand, holding a book with the other. Confident teacher pose. Navy blue classroom background.",
    },
    "excited": {
        "seed": 22222,
        "prompt": _YETI_BASE + "Wide shocked/excited expression, both arms raised in celebration. Bright orange gradient background. Very expressive face.",
    },
    "pointing": {
        "seed": 33333,
        "prompt": _YETI_BASE + "Pointing directly at the camera/viewer with one finger, slight smile. Dark navy background with subtle glow.",
    },
    "flashcard": {
        "seed": 44444,
        "prompt": _YETI_BASE + "Holding a large white flashcard/signboard in both hands. Friendly smile. Clean white and navy background.",
    },
    "thinking": {
        "seed": 55555,
        "prompt": _YETI_BASE + "Thoughtful pose, one hand on chin, looking slightly upward. Soft warm background with floating question marks.",
    },
    "thumbsup": {
        "seed": 66666,
        "prompt": _YETI_BASE + "Big confident thumbs up, broad smile, looking at camera. Green accent background conveying success.",
    },
}

def _get_yeti_pose(pose_name: str = "teaching") -> Path:
    """Return cached Yeti pose — generates ONCE with fixed seed, reused forever."""
    cached = _POSES_DIR / f"{pose_name}.jpg"
    if cached.exists() and cached.stat().st_size > 10_000:
        return cached
    pose = _YETI_POSES.get(pose_name, _YETI_POSES["teaching"])
    encoded = urllib.parse.quote(pose["prompt"])
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=1080&height=1920&model=flux&nologo=true&seed={pose['seed']}"
    )
    for attempt in range(3):
        try:
            r = httpx.get(url, timeout=90, follow_redirects=True)
            r.raise_for_status()
            cached.write_bytes(r.content)
            return cached
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"Pose generation failed: {e}")
            time.sleep(5)
    return cached

# ── Free royalty-free music clips (Pixabay CDN, CC0) ──────────────────────────
_MUSIC_TRACKS = [
    {
        "name": "upbeat_edu",
        "url": "https://cdn.pixabay.com/download/audio/2022/03/15/audio_8cb749f591.mp3",
        "mood": "upbeat",
    },
    {
        "name": "motivational",
        "url": "https://cdn.pixabay.com/download/audio/2022/01/18/audio_d0a13f69d2.mp3",
        "mood": "motivational",
    },
    {
        "name": "bright_morning",
        "url": "https://cdn.pixabay.com/download/audio/2021/08/09/audio_dc39bde808.mp3",
        "mood": "morning",
    },
]

# ── Hashtag bank ───────────────────────────────────────────────────────────────
_HASHTAGS_VOCAB = [
    "#IELTS", "#IELTSVocabulary", "#EnglishWords", "#LearnEnglish",
    "#IELTSPrep", "#EnglishVocabulary", "#WordOfTheDay", "#IELTSTips",
    "#EnglishLearning", "#IELTSBand7", "#IELTSBand8", "#StudyEnglish",
    "#MrYeti", "#pielts", "#IELTSOnline", "#EnglishWithYeti",
    "#IELTSWriting", "#IELTSSpeaking", "#Shorts", "#YouTubeShorts",
]

_HASHTAGS_TIP = [
    "#IELTS", "#IELTSTips", "#IELTSPrep", "#IELTSStrategy",
    "#EnglishLearning", "#IELTSBand7", "#IELTSCoach", "#StudyAbroad",
    "#IELTSWriting", "#IELTSSpeaking", "#IELTSReading", "#IELTSListening",
    "#MrYeti", "#pielts", "#LearnEnglish", "#IELTSOnline",
    "#Shorts", "#YouTubeShorts", "#EnglishTips", "#IELTSSuccess",
]

_MENTIONS = "@pieltsapp"

# ── Content generation ─────────────────────────────────────────────────────────

_VOCAB_WORDS = [
    ("Meticulous", "adj", "showing great attention to detail", "She was meticulous in her IELTS preparation."),
    ("Proliferate", "v", "to increase rapidly in number", "Social media has proliferated worldwide."),
    ("Arduous", "adj", "involving a lot of effort and difficulty", "The IELTS exam can be arduous without practice."),
    ("Substantiate", "v", "to provide evidence to support a claim", "You must substantiate your arguments in Writing Task 2."),
    ("Ubiquitous", "adj", "present everywhere at the same time", "Smartphones are now ubiquitous in modern society."),
    ("Eloquent", "adj", "fluent and persuasive in speaking/writing", "An eloquent response impresses IELTS examiners."),
    ("Mitigate", "v", "to make something less severe", "Governments must mitigate the effects of climate change."),
    ("Phenomenon", "n", "a fact or event that is observed", "Migration is a global phenomenon."),
    ("Advocate", "v/n", "to publicly support / a supporter", "Many experts advocate for renewable energy."),
    ("Detrimental", "adj", "causing harm or damage", "Stress can be detrimental to academic performance."),
    ("Imperative", "adj/n", "of vital importance / an essential thing", "It is imperative to manage your time in IELTS."),
    ("Coherent", "adj", "logical and consistent", "A coherent argument earns higher IELTS band scores."),
    ("Albeit", "conj", "although / even though", "The task was difficult, albeit manageable with practice."),
    ("Concede", "v", "to admit something is true reluctantly", "The candidate conceded that urbanisation has drawbacks."),
    ("Robust", "adj", "strong and effective", "A robust vocabulary is key to IELTS band 7+."),
]

_IELTS_TIPS = [
    ("Paraphrase the question!", "Never copy the IELTS question word for word. Rephrase it using synonyms. Examiners reward original language. Practice paraphrasing every day! 🎯"),
    ("Use 'however' wisely!", "In Writing Task 2, 'however' signals contrast. Place it at the START of a sentence for maximum impact. However, overusing it reduces your score. Balance is key! ✍️"),
    ("The 4-part Speaking answer!", "Use IDEA → REASON → EXAMPLE → LINK back. This structure keeps your answer focused and earns Band 7+. Practice it daily! 💬"),
    ("Collocations beat big words!", "Don't just learn vocabulary — learn word PAIRS. 'Make progress', 'raise awareness', 'take measures'. Collocations sound natural to examiners. 📚"),
    ("Time management in Reading!", "Spend max 20 mins per passage. If stuck on a question, SKIP and return. Losing time on 1 question can cost you 3 others! ⏱️"),
    ("Signposting words boost band!", "Use discourse markers: 'Furthermore', 'In contrast', 'As a result', 'Consequently'. They show logical thinking and improve coherence score! 🔗"),
    ("Active voice in Writing!", "Passive voice is fine sometimes, but active voice is clearer and stronger. 'Companies pollute rivers' beats 'Rivers are polluted by companies'. 💪"),
    ("Extend your Speaking answers!", "Short answers = low band. Always add WHY or an EXAMPLE. 'I love reading — it expands my vocabulary, which is vital for IELTS.' Extend every answer! 🗣️"),
    ("Band 7 Writing formula!", "Introduction (2 sentences) → Body 1 → Body 2 → Conclusion. Each body paragraph: Point → Explanation → Example → Link. Master this structure! 📝"),
    ("Predict before you listen!", "Before each IELTS Listening section, READ the questions first. This tells your brain what to expect. Prediction = better focus! 👂"),
]


def _get_content(slot: str) -> dict:
    """slot = 'morning' (vocab) or 'evening' (tip)."""
    day_seed = int(datetime.now().strftime("%Y%j"))
    rng = random.Random(day_seed + (0 if slot == "morning" else 1000))

    if slot == "morning":
        word, pos, definition, example = rng.choice(_VOCAB_WORDS)
        title = f"IELTS Word: {word} 📚 | Mr. Yeti"
        overlay_text = f"{word}\n({pos})\n{definition}"
        description_body = (
            f"📖 Word of the Day: {word}\n"
            f"🏷️ Part of Speech: {pos}\n"
            f"📝 Meaning: {definition}\n"
            f"💬 Example: {example}\n\n"
            f"Master IELTS vocabulary with Mr. Yeti! 🎓\n"
            f"👉 Practice free at https://pielts.web.app\n\n"
        )
        hashtags = " ".join(rng.sample(_HASHTAGS_VOCAB, 15))
        image_prompt = (
            f"Mr. Yeti IELTS teacher holding a large flashcard showing the word '{word}'. "
            f"Vertical 9:16 portrait format. Bold white text overlay: '{word}' at top, "
            f"'{definition}' in the middle. Navy blue background with orange accents. "
            f"Warm educational atmosphere. pielts.web.app logo at bottom. "
            f"Cinematic 3D Pixar-style render."
        )
    else:
        tip_title, tip_body = rng.choice(_IELTS_TIPS)
        title = f"IELTS Tip: {tip_title} | Mr. Yeti 🎯"
        overlay_text = f"IELTS TIP\n{tip_title}"
        description_body = (
            f"🎯 Today's IELTS Tip: {tip_title}\n\n"
            f"{tip_body}\n\n"
            f"👉 Practice free at https://pielts.web.app\n\n"
        )
        hashtags = " ".join(rng.sample(_HASHTAGS_TIP, 15))
        image_prompt = (
            f"Mr. Yeti IELTS coach with an excited expression, pointing at text '{tip_title}'. "
            f"Vertical 9:16 portrait format. Bold white text overlay at top. "
            f"Bright energetic background — orange gradient. pielts.web.app at bottom. "
            f"Cinematic 3D Pixar-style render."
        )

    full_description = (
        description_body +
        f"{_MENTIONS}\n\n" +
        hashtags
    )

    return {
        "title": title,
        "description": full_description,
        "overlay_text": overlay_text,
        "image_prompt": image_prompt,
        "hashtags": hashtags,
        "slot": slot,
    }


# ── Image generation via Pollinations AI (kept for thumbnails/custom) ─────────

def _generate_yeti_image(prompt: str, output_path: Path, seed: int = 0) -> Path:
    encoded = urllib.parse.quote(prompt)
    s = seed if seed else int(time.time())
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=1080&height=1920&model=flux&nologo=true&seed={s}"
    )
    for attempt in range(3):
        try:
            r = httpx.get(url, timeout=90, follow_redirects=True)
            r.raise_for_status()
            output_path.write_bytes(r.content)
            return output_path
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"Image generation failed: {e}")
            time.sleep(5)


# ── Music download ─────────────────────────────────────────────────────────────

def _get_music(slot: str) -> Path:
    """Return path to a cached music clip, download if missing."""
    track = _MUSIC_TRACKS[0] if slot == "morning" else _MUSIC_TRACKS[1]
    cached = _MUSIC_DIR / f"{track['name']}.mp3"
    if not cached.exists():
        try:
            r = httpx.get(track["url"], timeout=30, follow_redirects=True)
            r.raise_for_status()
            cached.write_bytes(r.content)
        except Exception:
            # fallback: generate 6 sec of silence
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", "6", str(cached)
            ], check=True, capture_output=True)
    return cached


# ── Text overlay via Pillow (ffmpeg drawtext needs libfreetype, not always available) ──

def _add_text_overlay(image_path: Path, overlay_text: str, output_path: Path) -> Path:
    """Burn text onto image using Pillow — no ffmpeg font dependency."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(image_path).convert("RGB")
    # Resize to 1080x1920 (vertical Short format)
    img = img.resize((1080, 1920), Image.LANCZOS)
    draw = ImageDraw.Draw(img)

    lines = [l for l in overlay_text.split("\n") if l.strip()]
    font_sizes = [80, 56, 46]
    y_positions = [100, 210, 300]

    # Semi-transparent black bar at top for text readability
    overlay = Image.new("RGBA", (1080, 420), (0, 0, 0, 160))
    img.paste(Image.fromarray(
        __import__("numpy").array(overlay)[:, :, :3], "RGB"
    ), (0, 60), mask=Image.fromarray(
        __import__("numpy").array(overlay)[:, :, 3], "L"
    )) if False else None  # skip numpy dep

    for i, line in enumerate(lines[:3]):
        fs = font_sizes[i] if i < len(font_sizes) else 40
        y = y_positions[i] if i < len(y_positions) else 400 + i * 80
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", fs)
        except Exception:
            font = ImageFont.load_default()

        # Draw shadow
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (1080 - tw) // 2
        draw.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0, 200))
        # Draw text
        draw.text((x, y), line, font=font, fill=(255, 255, 255))

    # Watermark at bottom
    try:
        wm_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 38)
    except Exception:
        wm_font = ImageFont.load_default()
    wm = "pielts.web.app"
    bbox = draw.textbbox((0, 0), wm, font=wm_font)
    wx = (1080 - (bbox[2] - bbox[0])) // 2
    draw.text((wx + 2, 1822), wm, font=wm_font, fill=(0, 0, 0, 180))
    draw.text((wx, 1820), wm, font=wm_font, fill=(255, 255, 255, 220))

    img.save(str(output_path), "JPEG", quality=95)
    return output_path


# ── Video composition with ffmpeg ─────────────────────────────────────────────

def _make_video(image_path: Path, music_path: Path, overlay_text: str, output_path: Path) -> Path:
    """Compose 6-sec 1080x1920 YouTube Short: Pillow text overlay + ffmpeg encode."""
    with tempfile.TemporaryDirectory() as tmp:
        composited = Path(tmp) / "composited.jpg"
        _add_text_overlay(image_path, overlay_text, composited)

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(composited),
            "-i", str(music_path),
            "-t", "6",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            "-shortest",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr[-600:]}")
    return output_path


# ── Main entry point ───────────────────────────────────────────────────────────

def make_daily_reel(slot: str = "auto") -> dict:
    """
    Generate a complete YouTube Short reel for the given slot.
    slot: 'morning' | 'evening' | 'auto' (auto-detects from current hour)
    Returns dict with video_path, title, description, etc.
    """
    if slot == "auto":
        hour = datetime.now().hour
        slot = "morning" if hour < 14 else "evening"

    content = _get_content(slot)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Pick pose: morning=flashcard (vocab), evening=pointing (tip)
    pose_map = {"morning": "flashcard", "evening": "pointing"}
    img_path = _get_yeti_pose(pose_map.get(slot, "teaching"))

    with tempfile.TemporaryDirectory() as tmp:
        music_path = _get_music(slot)

        video_path = _REELS_DIR / f"reel_{slot}_{ts}.mp4"
        _make_video(img_path, music_path, content["overlay_text"], video_path)

    # Upload reel to R2 and remove local copy
    final_video_path = str(video_path)
    try:
        from .r2_storage import upload_file as _r2_upload, is_configured as _r2_ok
        if _r2_ok() and video_path.exists():
            r2_url = _r2_upload(video_path, f"reels/{video_path.name}", "video/mp4")
            try:
                video_path.unlink()
            except Exception:
                pass
            final_video_path = r2_url
    except Exception as r2e:
        print(f"⚠️  R2 reel upload failed ({r2e}) — keeping local")

    return {
        "ok": True,
        "video_path": final_video_path,
        "slot": slot,
        "title": content["title"],
        "description": content["description"],
        "tags": "IELTS,English,Vocabulary,IELTSTips,MrYeti,pielts,Shorts",
        "category": "27",  # Education
        "privacy": "public",
    }
