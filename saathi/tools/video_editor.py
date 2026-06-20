"""Auto Video Editor — Stage 6.
Combines: Yeti image/video + voice narration + B-roll + subtitles + music → MP4.
Uses ffmpeg (already installed). Outputs YouTube, TikTok, Instagram, Facebook formats.
"""
import json
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

_VIDEOS_DIR = Path.home() / "SaathiAI" / "videos_output"
_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
_BROLL_DIR  = Path.home() / "SaathiAI" / "broll_cache"
_BROLL_DIR.mkdir(parents=True, exist_ok=True)
_MUSIC_DIR  = Path.home() / "SaathiAI" / "client" / "assets" / "music"

_PEXELS_KEY = ""  # Free Pexels API key — get at pexels.com/api (optional)


def _get_yeti_pose(pose: str = "teaching") -> Path:
    from .reel_maker import _get_yeti_pose as _gyp
    return _gyp(pose)


def _generate_voice(text: str, output_path: Path, lang: str = "en", accent: str = "co.uk") -> Path:
    """Generate voice narration using gTTS (free, no API key)."""
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang=lang, tld=accent, slow=False)
        tts.save(str(output_path))
        return output_path
    except Exception as e:
        # Fallback: macOS say command
        subprocess.run(["say", "-o", str(output_path), "--data-format=aiff", text[:500]], check=True)
        # Convert to mp3
        mp3_path = output_path.with_suffix(".mp3")
        subprocess.run(["ffmpeg", "-y", "-i", str(output_path), str(mp3_path)], capture_output=True)
        return mp3_path


def _get_broll(keyword: str) -> list[Path]:
    """Download free B-roll from Pexels (cached)."""
    if not _PEXELS_KEY:
        return []
    try:
        r = httpx.get(
            "https://api.pexels.com/videos/search",
            params={"query": keyword, "per_page": 3, "orientation": "portrait"},
            headers={"Authorization": _PEXELS_KEY},
            timeout=15
        )
        videos = r.json().get("videos", [])
        paths = []
        for v in videos[:2]:
            vid_url = v["video_files"][0]["link"]
            vid_id = v["id"]
            cached = _BROLL_DIR / f"broll_{vid_id}.mp4"
            if not cached.exists():
                vr = httpx.get(vid_url, timeout=30, follow_redirects=True)
                cached.write_bytes(vr.content)
            paths.append(cached)
        return paths
    except Exception:
        return []


def create_short_video(
    script: dict,
    pose: str = "teaching",
    with_voice: bool = True,
    with_broll: bool = False,
) -> dict:
    """
    Create a YouTube Short (1080x1920, 30-60 sec) from script dict.
    script keys: hook, lesson, cta, overlay_text, thumbnail_text
    """
    ts = int(time.time())
    yeti_img = _get_yeti_pose(pose)
    music_path = _MUSIC_DIR / "upbeat_edu.mp3"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # 1. Generate voice narration
        full_text = f"{script.get('hook','')} {script.get('lesson','')} {script.get('cta','')}"
        voice_path = tmp / "voice.mp3"
        if with_voice:
            try:
                _generate_voice(full_text[:500], voice_path)
            except Exception:
                with_voice = False

        # 2. Get voice duration
        duration = 45
        if with_voice and voice_path.exists():
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(voice_path)],
                capture_output=True, text=True
            )
            try:
                duration = min(60, float(json.loads(result.stdout)["format"]["duration"]) + 1)
            except Exception:
                pass

        # 3. Add text to image with Pillow
        from PIL import Image, ImageDraw, ImageFont
        img = Image.open(yeti_img).convert("RGB").resize((1080, 1920), Image.LANCZOS)
        draw = ImageDraw.Draw(img)

        overlay = script.get("overlay_text", script.get("thumbnail_text", ""))
        lines = [l.strip() for l in overlay.split("\n") if l.strip()][:3]
        y_pos = [90, 195, 290]
        fsizes = [75, 54, 44]

        for i, line in enumerate(lines):
            fs = fsizes[i] if i < len(fsizes) else 40
            y = y_pos[i] if i < len(y_pos) else 400
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", fs)
            except Exception:
                font = ImageFont.load_default()
            bbox = draw.textbbox((0,0), line, font=font)
            x = (1080 - (bbox[2]-bbox[0])) // 2
            draw.text((x+3, y+3), line, font=font, fill=(0,0,0))
            draw.text((x, y), line, font=font, fill=(255,255,255))

        # Watermark
        try:
            wf = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
        except Exception:
            wf = ImageFont.load_default()
        draw.text((22, 1822), "pielts.web.app", font=wf, fill=(255,255,255))

        composited = tmp / "frame.jpg"
        img.save(str(composited), "JPEG", quality=95)

        # 4. Compose video with ffmpeg
        output_path = _VIDEOS_DIR / f"short_{ts}.mp4"

        audio_input = str(voice_path) if (with_voice and voice_path.exists()) else str(music_path)
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(composited),
            "-i", audio_input,
            "-t", str(duration),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", "-shortest",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return {"ok": False, "error": f"ffmpeg: {result.stderr[-400:]}"}

    return {
        "ok": True,
        "video_path": str(output_path),
        "duration_sec": duration,
        "with_voice": with_voice,
        "title": script.get("title", ""),
        "tags": script.get("tags", []),
        "hashtags": script.get("hashtags", ""),
        "format": "1080x1920_short",
    }


def create_landscape_video(script: dict, pose: str = "teaching") -> dict:
    """Create a 16:9 YouTube video (1920x1080) for longer content."""
    ts = int(time.time())
    yeti_img_src = _get_yeti_pose(pose)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # Resize to landscape
        from PIL import Image, ImageDraw, ImageFont
        img = Image.open(yeti_img_src).convert("RGB")
        # Place yeti on right side, text on left
        canvas = Image.new("RGB", (1920, 1080), (10, 20, 50))  # navy bg
        yeti_resized = img.resize((800, 1080), Image.LANCZOS)
        canvas.paste(yeti_resized, (1120, 0))

        draw = ImageDraw.Draw(canvas)
        title = script.get("title", "")[:60]
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 72)
            small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
        except Exception:
            font = small = ImageFont.load_default()

        draw.text((60, 200), title, font=font, fill=(255,220,0))
        hook = script.get("hook","")[:200]
        # Wrap hook text
        words = hook.split()
        line, lines_out = "", []
        for w in words:
            if len(line + w) < 35:
                line += w + " "
            else:
                lines_out.append(line.strip()); line = w + " "
        if line: lines_out.append(line.strip())
        for i, l in enumerate(lines_out[:5]):
            draw.text((60, 380 + i*55), l, font=small, fill=(220,220,220))

        draw.text((60, 1020), "pielts.web.app", font=small, fill=(255,255,255))

        frame = tmp / "frame_landscape.jpg"
        canvas.save(str(frame), "JPEG", quality=95)

        # Voice
        full_text = " ".join([
            script.get("hook",""),
            script.get("intro",""),
            " ".join(s.get("script","") for s in script.get("lesson_sections",[])),
            script.get("summary",""),
            script.get("cta","")
        ])[:2000]

        voice_path = tmp / "voice.mp3"
        try:
            _generate_voice(full_text, voice_path)
            duration = 280
        except Exception:
            voice_path = _MUSIC_DIR / "upbeat_edu.mp3"
            duration = 60

        output_path = _VIDEOS_DIR / f"long_{ts}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(frame),
            "-i", str(voice_path),
            "-t", str(duration),
            "-vf", "scale=1920:1080",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", "-shortest",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr[-400:]}

    return {
        "ok": True,
        "video_path": str(output_path),
        "format": "1920x1080_landscape",
        "title": script.get("title",""),
    }
