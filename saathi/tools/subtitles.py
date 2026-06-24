"""
Auto-subtitle burner for Mr. Yeti videos.
Uses faster-whisper to transcribe → burns word-by-word captions using Pillow + ffmpeg.
Style: large bold white text centered at bottom (TikTok/Shorts viral style).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
from .. import config

OUT_DIR = config.ROOT / "data" / "subtitled"
OUT_DIR.mkdir(parents=True, exist_ok=True)

_FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Arial.ttf",
]


def _get_font(size: int = 72):
    for fp in _FONT_PATHS:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _get_video_info(video_path: str) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", video_path],
        capture_output=True, text=True
    )
    data = json.loads(r.stdout)
    w, h, fps, dur = 1080, 1920, 30.0, 0.0
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            w = s.get("width", w)
            h = s.get("height", h)
            fps_str = s.get("r_frame_rate", "30/1")
            try:
                num, den = fps_str.split("/")
                fps = float(num) / float(den)
            except Exception:
                fps = 30.0
    dur = float(data.get("format", {}).get("duration", 0))
    return {"width": w, "height": h, "fps": fps, "duration": dur}


def transcribe(video_path: str) -> list[dict]:
    """Transcribe video → word-level timestamps."""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(video_path, word_timestamps=True, language="en")
        words = []
        for seg in segments:
            if seg.words:
                for w in seg.words:
                    words.append({"word": w.word.strip(), "start": w.start, "end": w.end})
        return words
    except Exception as e:
        print(f"⚠️  Transcription failed: {e}")
        return []


def _draw_subtitle_frame(frame: Image.Image, text: str, width: int, height: int) -> Image.Image:
    """Draw bold white subtitle text with black border at bottom of frame."""
    draw = ImageDraw.Draw(frame)
    font = _get_font(size=max(48, width // 15))

    # Word wrap
    words = text.split()
    lines, line = [], []
    for word in words:
        test = " ".join(line + [word])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > width - 80 and line:
            lines.append(" ".join(line))
            line = [word]
        else:
            line.append(word)
    if line:
        lines.append(" ".join(line))

    line_h = draw.textbbox((0, 0), "Ag", font=font)[3] + 10
    total_h = line_h * len(lines)
    y = height - total_h - 120

    for line_text in lines:
        bbox = draw.textbbox((0, 0), line_text, font=font)
        text_w = bbox[2] - bbox[0]
        x = (width - text_w) // 2

        # Black border (outline)
        for dx, dy in [(-3,0),(3,0),(0,-3),(0,3),(-3,-3),(3,-3),(-3,3),(3,3)]:
            draw.text((x+dx, y+dy), line_text, font=font, fill=(0, 0, 0))
        # White text
        draw.text((x, y), line_text, font=font, fill=(255, 255, 255))
        y += line_h

    return frame


def burn_subtitles(video_path: str, output_path: str = "") -> str:
    """
    Transcribe + burn subtitles onto video using frame-by-frame Pillow rendering.
    Returns path to subtitled video.
    """
    video_path = str(video_path)
    out = Path(output_path) if output_path else \
          OUT_DIR / f"{Path(video_path).stem}_subbed.mp4"

    print("📝 Transcribing for subtitles...")
    words = transcribe(video_path)
    if not words:
        print("⚠️  No words — skipping subtitles")
        return video_path

    info = _get_video_info(video_path)
    W, H, FPS = info["width"], info["height"], info["fps"]
    total_frames = int(info["duration"] * FPS)

    # Build frame→text map
    frame_text: dict[int, str] = {}
    i = 0
    while i < len(words):
        chunk = words[i:i+4]
        start_f = int(chunk[0]["start"] * FPS)
        end_f   = int(chunk[-1]["end"] * FPS)
        text    = " ".join(w["word"] for w in chunk).upper()
        for f in range(start_f, end_f + 1):
            frame_text[f] = text
        i += 4

    with tempfile.TemporaryDirectory(prefix="subs_") as tmp:
        tmp = Path(tmp)
        frames_dir = tmp / "frames"
        frames_dir.mkdir()

        # Extract all frames
        print(f"🎞️  Extracting {total_frames} frames...")
        subprocess.run([
            "ffmpeg", "-i", video_path,
            "-q:v", "2", f"{frames_dir}/%06d.jpg",
            "-loglevel", "quiet", "-y"
        ], timeout=120)

        # Overlay subtitles on frames that need them
        print(f"🔥 Burning subtitles on {len(frame_text)} frames...")
        frame_files = sorted(frames_dir.glob("*.jpg"))
        for idx, fpath in enumerate(frame_files):
            fnum = idx + 1
            if fnum in frame_text:
                img = Image.open(fpath).convert("RGB")
                img = _draw_subtitle_frame(img, frame_text[fnum], W, H)
                img.save(fpath, "JPEG", quality=95)

        # Reassemble video
        print("🎬 Reassembling video with subtitles...")
        subprocess.run([
            "ffmpeg", "-framerate", str(FPS),
            "-i", f"{frames_dir}/%06d.jpg",
            "-i", video_path,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-crf", "20", "-preset", "fast",
            "-c:a", "copy", "-shortest",
            str(out), "-y", "-loglevel", "quiet"
        ], timeout=300)

    if out.exists():
        print(f"✅ Subtitles burned → {out}")
        return str(out)

    print("❌ Subtitle burn failed — returning original")
    return video_path
