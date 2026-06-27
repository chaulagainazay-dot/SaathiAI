"""Auto Video Editor — Stage 6 + Full Pipeline.

Legacy: static image + gTTS voice cards (create_short_video, create_landscape_video)
New:    full FFmpeg pipeline for Veo scene clips:
          stitch_scenes → transcribe_audio (Whisper) → burn_captions
          → add_intro_outro → add_background_music → extract_shorts
          → extract_thumbnail_frame → run_full_edit_pipeline
"""
import json
import os
import shutil
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

    # Upload short video to R2
    final_video_path = str(output_path)
    try:
        from .r2_storage import upload_file as _r2_upload, is_configured as _r2_ok
        if _r2_ok() and output_path.exists():
            r2_url = _r2_upload(output_path, f"mr_yeti/{output_path.name}", "video/mp4")
            try:
                output_path.unlink()
            except Exception:
                pass
            final_video_path = r2_url
    except Exception as r2e:
        print(f"⚠️  R2 short video upload failed ({r2e}) — keeping local")

    return {
        "ok": True,
        "video_path": final_video_path,
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

    # Upload landscape video to R2
    final_video_path = str(output_path)
    try:
        from .r2_storage import upload_file as _r2_upload, is_configured as _r2_ok
        if _r2_ok() and output_path.exists():
            r2_url = _r2_upload(output_path, f"mr_yeti/{output_path.name}", "video/mp4")
            try:
                output_path.unlink()
            except Exception:
                pass
            final_video_path = r2_url
    except Exception as r2e:
        print(f"⚠️  R2 landscape video upload failed ({r2e}) — keeping local")

    return {
        "ok": True,
        "video_path": final_video_path,
        "format": "1920x1080_landscape",
        "title": script.get("title",""),
    }


# ══════════════════════════════════════════════════════════════════════════════
# FULL FFMPEG PIPELINE — for Veo/Google Flow scene clips
# ══════════════════════════════════════════════════════════════════════════════

from .. import config as _config

_ASSETS   = _config.ROOT / "data" / "assets"
_BGM_DIR  = _ASSETS / "bgm"
_SFX_DIR  = _ASSETS / "sfx"
_INTRO_DIR = _ASSETS / "intro"
_OUTRO_DIR = _ASSETS / "outro"

_INTRO_VIDEO = _INTRO_DIR / "mr_yeti_intro.mp4"
_OUTRO_VIDEO = _OUTRO_DIR / "mr_yeti_outro.mp4"
_DEFAULT_BGM = _BGM_DIR   / "upbeat_bg.mp3"

_VIDEOS_DIR = _config.ROOT / "data" / "mr_yeti_videos"
_SHORTS_DIR = _config.ROOT / "data" / "mr_yeti_shorts"
_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
_SHORTS_DIR.mkdir(parents=True, exist_ok=True)

_FFMPEG  = shutil.which("ffmpeg")  or "/opt/homebrew/bin/ffmpeg"
_FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"

_SHORTS_SPEC = [
    # (name,        start_sec, end_sec, overlay_text)
    ("hook",         0,   45,  "🔥 WATCH TILL END"),
    ("mistake",     45,   90,  "❌ Don't say this!"),
    ("quiz",        90,  135,  "🧠 Can you answer?"),
    ("funny",      135,  180,  "😂 Mr. Yeti reacts"),
    ("vocabulary", 180,  225,  "📚 Band 7 phrase"),
    ("success",    225,  270,  "✅ Band 5 → Band 7"),
]


def _ffrun(cmd: list, timeout: int = 600) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stderr + r.stdout


def _ffprobe(video_path: str) -> dict:
    cmd = [_FFPROBE, "-v", "quiet", "-print_format", "json",
           "-show_streams", "-show_format", video_path]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return {"duration": 0, "width": 1080, "height": 1920, "has_audio": False}
    data = json.loads(r.stdout or "{}")
    streams = data.get("streams", [])
    vid = next((s for s in streams if s.get("codec_type") == "video"), {})
    aud = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})
    return {
        "duration": float(fmt.get("duration", 0)),
        "width":    int(vid.get("width", 1080)),
        "height":   int(vid.get("height", 1920)),
        "has_audio": aud is not None,
    }


def _ensure_9_16(src: str, dst: str) -> str:
    cmd = [
        _FFMPEG, "-y", "-i", src,
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
               "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy", "-movflags", "+faststart", dst,
    ]
    _ffrun(cmd)
    return dst if Path(dst).exists() else src


def stitch_scenes(clip_paths: list, output_path: str) -> dict:
    """Concatenate scene MP4 clips (all normalised to 1080×1920) → master video."""
    valid = [p for p in clip_paths if p and Path(p).exists()]
    if not valid:
        return {"ok": False, "error": "No valid clips found"}

    # Normalise to 9:16
    norm = []
    for p in valid:
        dst = p.replace(".mp4", "_n.mp4")
        norm.append(_ensure_9_16(p, dst))

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for p in norm:
            f.write(f"file '{p}'\n")
        lst = f.name

    rc, err = _ffrun([
        _FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", lst,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        output_path,
    ])
    os.unlink(lst)

    if rc != 0 or not Path(output_path).exists():
        return {"ok": False, "error": err[:500]}
    info = _ffprobe(output_path)
    return {"ok": True, "path": output_path, "duration": info["duration"]}


def transcribe_audio(video_path: str, model_size: str = "base") -> dict:
    """
    Whisper transcription → SRT subtitle file.
    Tries OpenAI API first, falls back to local whisper model.
    """
    srt_path = Path(video_path).with_suffix(".srt")

    # OpenAI Whisper API (fast, accurate)
    key = os.environ.get("OPENAI_API_KEY", "")
    if key and not key.startswith("YOUR"):
        try:
            with open(video_path, "rb") as fh:
                r = httpx.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {key}"},
                    data={"model": "whisper-1", "response_format": "srt", "language": "en"},
                    files={"file": (Path(video_path).name, fh, "video/mp4")},
                    timeout=120,
                )
            r.raise_for_status()
            srt_path.write_text(r.text)
            return {"ok": True, "srt_path": str(srt_path)}
        except Exception as e:
            print(f"  OpenAI Whisper API failed ({e}), using local model")

    # Local whisper
    try:
        import whisper as _whisper
        model = _whisper.load_model(model_size)
        result = model.transcribe(video_path, language="en", word_timestamps=True)
        lines = []
        for i, seg in enumerate(result["segments"], 1):
            def _t(s):
                h, m = int(s//3600), int((s%3600)//60)
                return f"{h:02d}:{m:02d}:{int(s%60):02d},{int((s%1)*1000):03d}"
            lines.append(f"{i}\n{_t(seg['start'])} --> {_t(seg['end'])}\n{seg['text'].strip()}\n")
        srt_path.write_text("\n".join(lines))
        return {"ok": True, "srt_path": str(srt_path)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def burn_captions(video_path: str, srt_path: str, output_path: str) -> dict:
    """Hardcode subtitles into video — TikTok style (large, bold, centered)."""
    if not Path(srt_path).exists():
        return {"ok": False, "error": "SRT file not found"}

    srt_esc = srt_path.replace("\\", "\\\\").replace(":", "\\:")
    subtitle_filter = (
        f"subtitles='{srt_esc}':"
        "force_style='FontName=Arial,FontSize=22,Bold=1,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BackColour=&H80000000,BorderStyle=4,Outline=2,"
        "Shadow=1,Alignment=2,MarginV=80'"
    )
    rc, err = _ffrun([
        _FFMPEG, "-y", "-i", video_path,
        "-vf", subtitle_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy", "-movflags", "+faststart",
        output_path,
    ], timeout=300)

    if rc != 0 or not Path(output_path).exists():
        return {"ok": False, "error": err[:400]}
    return {"ok": True, "path": output_path}


def add_background_music(video_path: str, output_path: str,
                         bgm_path: str = None, volume: float = 0.18) -> dict:
    """Mix royalty-free BGM under voice at low volume (default 18%)."""
    bgm = bgm_path or str(_DEFAULT_BGM)
    if not Path(bgm).exists():
        shutil.copy2(video_path, output_path)
        return {"ok": True, "path": output_path, "note": "no BGM file — original copied"}

    info = _ffprobe(video_path)
    dur  = info["duration"]
    rc, err = _ffrun([
        _FFMPEG, "-y",
        "-i", video_path,
        "-stream_loop", "-1", "-i", bgm,
        "-filter_complex",
        f"[1:a]volume={volume},atrim=0:{dur},afade=t=out:st={max(0,dur-2)}:d=2[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_path,
    ], timeout=300)

    if rc != 0 or not Path(output_path).exists():
        shutil.copy2(video_path, output_path)
        return {"ok": True, "path": output_path, "note": "music mix failed — original kept"}
    return {"ok": True, "path": output_path}


def _make_text_card(text: str, duration: float, hex_color: str, out_path: str) -> str | None:
    """Generate a simple colored title card with FFmpeg."""
    safe = text.replace("'", "\\'").replace(":", "\\:")
    rc, _ = _ffrun([
        _FFMPEG, "-y",
        "-f", "lavfi",
        "-i", f"color=c={hex_color}:size=1080x1920:duration={duration}:rate=30",
        "-vf", (f"drawtext=text='{safe}':fontcolor=white:fontsize=56:"
                "x=(w-tw)/2:y=(h-th)/2:font=Arial:line_spacing=20:"
                "fontfile=/System/Library/Fonts/Helvetica.ttc"),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        out_path,
    ])
    return out_path if rc == 0 and Path(out_path).exists() else None


def add_intro_outro(video_path: str, output_path: str,
                    add_intro: bool = True, add_outro: bool = True) -> dict:
    """Prepend Mr. Yeti branded intro and append pielts.web.app CTA outro."""
    clips = []

    if add_intro:
        if _INTRO_VIDEO.exists():
            clips.append(str(_INTRO_VIDEO))
        else:
            card = _make_text_card("MR. YETI\n🎓 IELTS Teacher",
                                   2.5, "0x6C3FCF",
                                   str(_VIDEOS_DIR / "_intro_card.mp4"))
            if card:
                clips.append(card)

    clips.append(video_path)

    if add_outro:
        if _OUTRO_VIDEO.exists():
            clips.append(str(_OUTRO_VIDEO))
        else:
            card = _make_text_card("FREE Band 7 Practice\npielts.web.app",
                                   4.0, "0x00BFA5",
                                   str(_VIDEOS_DIR / "_outro_card.mp4"))
            if card:
                clips.append(card)

    if len(clips) == 1:
        shutil.copy2(video_path, output_path)
        return {"ok": True, "path": output_path, "note": "no intro/outro assets"}

    return stitch_scenes(clips, output_path)


def _add_text_overlay(video_path: str, text: str, output_path: str,
                      y_expr: str = "50", start: float = 0, end: float = 3,
                      font_size: int = 48) -> dict:
    safe = text.replace("'", "\\'").replace(":", "\\:")
    draw = (
        f"drawtext=text='{safe}':fontcolor=white:fontsize={font_size}:"
        f"x=(w-tw)/2:y={y_expr}:font=Arial:"
        f"box=1:boxcolor=black@0.5:boxborderw=12:"
        f"enable='between(t,{start},{end})'"
    )
    rc, err = _ffrun([
        _FFMPEG, "-y", "-i", video_path,
        "-vf", draw,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy", output_path,
    ], timeout=120)
    if rc != 0 or not Path(output_path).exists():
        return {"ok": False, "error": err[:300]}
    return {"ok": True, "path": output_path}


def extract_shorts(master_path: str, slug: str,
                   add_music: bool = True) -> list[dict]:
    """
    Cut master video into 6 Shorts clips per _SHORTS_SPEC.
    Each clip gets an emoji overlay (top) + pielts.web.app CTA (bottom last 4s).
    """
    info   = _ffprobe(master_path)
    master_dur = info["duration"]
    results = []

    for name, start, end, overlay in _SHORTS_SPEC:
        if start >= master_dur:
            continue
        actual_end = min(end, master_dur)
        dur = actual_end - start
        if dur < 5:
            continue

        out = str(_SHORTS_DIR / f"{slug}_{name}.mp4")

        # Cut
        rc, _ = _ffrun([
            _FFMPEG, "-y",
            "-ss", str(start), "-to", str(actual_end),
            "-i", master_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            out,
        ])
        if rc != 0 or not Path(out).exists():
            continue

        # Top overlay (first 2.5s)
        ov_out = out.replace(".mp4", "_ov.mp4")
        r = _add_text_overlay(out, overlay, ov_out, y_expr="60",
                               start=0, end=2.5, font_size=44)
        if r.get("ok"):
            shutil.move(ov_out, out)

        # CTA overlay (last 4s)
        cta_out = out.replace(".mp4", "_cta.mp4")
        r = _add_text_overlay(out, "FREE practice → pielts.web.app", cta_out,
                               y_expr="h-th-80",
                               start=max(0, dur - 4), end=dur, font_size=34)
        if r.get("ok"):
            shutil.move(cta_out, out)

        # Background music
        if add_music and _DEFAULT_BGM.exists():
            m_out = out.replace(".mp4", "_m.mp4")
            m = add_background_music(out, m_out, volume=0.12)
            if m.get("ok") and Path(m_out).exists():
                shutil.move(m_out, out)

        clip_info = _ffprobe(out)
        results.append({"name": name, "path": out,
                         "duration": clip_info["duration"], "overlay": overlay})

    return results


def extract_thumbnail_frame(video_path: str, timestamp: float = 3.0) -> dict:
    """Extract a JPEG still frame at `timestamp` seconds for thumbnail use."""
    out = str(Path(video_path).with_suffix(".jpg").parent /
              (Path(video_path).stem + "_thumb.jpg"))
    rc, err = _ffrun([
        _FFMPEG, "-y", "-ss", str(timestamp), "-i", video_path,
        "-vframes", "1", "-q:v", "2", "-vf", "scale=1080:1920", out,
    ])
    if rc != 0 or not Path(out).exists():
        return {"ok": False, "error": err[:300]}
    return {"ok": True, "path": out}


def run_full_edit_pipeline(scene_clips: list, slug: str,
                            srt_path: str = None) -> dict:
    """
    Full editing pipeline from raw Veo clips → finished master + 6 Shorts.

    Steps:
      1. Stitch scenes → master.mp4
      2. Transcribe audio → .srt (Whisper)
      3. Burn captions → master_captioned.mp4
      4. Add intro/outro → master_full.mp4
      5. Mix background music → master_final.mp4 (publish-ready)
      6. Extract 6 Shorts from captioned master
      7. Extract thumbnail frame
    """
    result = {"ok": False, "slug": slug}

    print(f"[{slug}] ① Stitching {len(scene_clips)} scenes...")
    master = str(_VIDEOS_DIR / f"{slug}_master.mp4")
    r = stitch_scenes(scene_clips, master)
    if not r.get("ok"):
        return {"ok": False, "error": f"Stitch: {r.get('error')}"}
    result.update({"master": master, "duration": r["duration"]})
    working = master

    print(f"[{slug}] ② Transcribing audio (Whisper)...")
    srt = srt_path
    if not srt or not Path(srt).exists():
        tr = transcribe_audio(master)
        srt = tr.get("srt_path") if tr.get("ok") else None
    if srt:
        result["srt"] = srt

        print(f"[{slug}] ③ Burning captions...")
        captioned = str(_VIDEOS_DIR / f"{slug}_captioned.mp4")
        cr = burn_captions(working, srt, captioned)
        if cr.get("ok"):
            working = captioned
            result["captioned"] = captioned
    else:
        print(f"[{slug}] ③ Skipping captions — no transcript")
        result["captioned"] = working

    print(f"[{slug}] ④ Adding intro/outro...")
    full = str(_VIDEOS_DIR / f"{slug}_full.mp4")
    ir = add_intro_outro(working, full)
    if ir.get("ok"):
        working = full
        result["full"] = full

    print(f"[{slug}] ⑤ Mixing background music...")
    final = str(_VIDEOS_DIR / f"{slug}_final.mp4")
    mr = add_background_music(working, final)
    if mr.get("ok"):
        working = final
        result["final"] = final

    result["ready_to_publish"] = working

    print(f"[{slug}] ⑥ Extracting Shorts...")
    shorts_source = result.get("captioned", master)
    shorts = extract_shorts(shorts_source, slug=slug, add_music=True)
    result["shorts"] = shorts
    print(f"  → {len(shorts)} shorts extracted")

    print(f"[{slug}] ⑦ Extracting thumbnail...")
    thumb = extract_thumbnail_frame(master)
    if thumb.get("ok"):
        result["thumbnail"] = thumb["path"]

    result["ok"] = True

    # Upload final pipeline output to R2
    try:
        from .r2_storage import upload_file as _r2_upload, is_configured as _r2_ok
        if _r2_ok() and working and Path(working).exists():
            r2_url = _r2_upload(working, f"mr_yeti/{Path(working).name}", "video/mp4")
            try:
                Path(working).unlink()
            except Exception:
                pass
            result["ready_to_publish"] = r2_url
            working = r2_url
    except Exception as r2e:
        print(f"⚠️  R2 final video upload failed ({r2e}) — keeping local")

    print(f"[{slug}] ✅ Done → {working}")
    return result


def download_free_bgm() -> dict:
    """Download a CC0 royalty-free background track to data/assets/bgm/."""
    if _DEFAULT_BGM.exists():
        return {"ok": True, "path": str(_DEFAULT_BGM), "note": "already exists"}
    try:
        url = "https://cdn.pixabay.com/audio/2024/03/13/audio_3c1b9f67af.mp3"
        r = httpx.get(url, timeout=60, follow_redirects=True)
        if r.status_code == 200:
            _BGM_DIR.mkdir(parents=True, exist_ok=True)
            _DEFAULT_BGM.write_bytes(r.content)
            return {"ok": True, "path": str(_DEFAULT_BGM)}
        return {"ok": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def asset_status() -> dict:
    """Check which pipeline assets are available."""
    return {
        "ffmpeg":      bool(_FFMPEG),
        "ffprobe":     bool(_FFPROBE),
        "intro_video": _INTRO_VIDEO.exists(),
        "outro_video": _OUTRO_VIDEO.exists(),
        "bgm":         _DEFAULT_BGM.exists(),
        "bgm_path":    str(_DEFAULT_BGM),
    }
