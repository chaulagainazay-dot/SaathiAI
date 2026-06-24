"""
Extract short clips from a long Mr. Yeti HyperFrames video for Shorts/Reels/TikTok.

Strategy: divide the long video into n evenly-spaced 58-second clips.
Each clip is a self-contained tip that works as a standalone Short/Reel.

Slots: "7am", "12pm", "5pm", "8pm"
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


_SLOTS = ["7am", "12pm", "5pm", "8pm"]


def _get_duration(video_path: str) -> float:
    """Return video duration in seconds via ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", str(video_path)],
            capture_output=True, text=True, timeout=15,
        )
        return float(json.loads(r.stdout).get("format", {}).get("duration", 0))
    except Exception:
        return 0.0


def extract_clips(
    long_video_path: str,
    out_dir: str | None = None,
    n_clips: int = 4,
    clip_duration: float = 58.0,
) -> list[dict]:
    """
    Extract n_clips evenly-spaced clips (each clip_duration seconds) from a long video.

    Returns list of:
      {"path": str, "start": float, "duration": float, "slot": str, "ok": bool}

    Slots are assigned in order: "7am", "12pm", "5pm", "8pm".
    Uses re-encode (libx264/aac) so each clip is a standalone keyframe-aligned file.
    """
    src = Path(long_video_path)
    if not src.exists():
        return [{"ok": False, "error": f"Source not found: {long_video_path}", "slot": s}
                for s in _SLOTS[:n_clips]]

    total_dur = _get_duration(long_video_path)
    if total_dur < clip_duration:
        # Video is already shorter than one clip — just return it as clip 0
        return [{"path": long_video_path, "start": 0.0,
                 "duration": total_dur, "slot": _SLOTS[0], "ok": True}]

    dest = Path(out_dir) if out_dir else src.parent
    dest.mkdir(parents=True, exist_ok=True)

    # Evenly distribute clip start times so we never go past end of video
    usable = total_dur - clip_duration   # last valid start point
    if n_clips == 1:
        start_times = [0.0]
    else:
        step = usable / (n_clips - 1)
        start_times = [round(i * step, 2) for i in range(n_clips)]

    results = []
    for i, start in enumerate(start_times):
        slot = _SLOTS[i] if i < len(_SLOTS) else f"clip{i}"
        out_path = dest / f"clip_{slot}_{src.stem}.mp4"

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", str(src),
            "-t", str(clip_duration),
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            str(out_path),
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=180, check=True)
        except subprocess.CalledProcessError as e:
            print(f"  clip_extractor: {slot} ffmpeg failed: {e.stderr.decode()[:200]}")
            results.append({"ok": False, "slot": slot, "start": start,
                            "error": e.stderr.decode()[:200]})
            continue
        except subprocess.TimeoutExpired:
            print(f"  clip_extractor: {slot} ffmpeg timed out")
            results.append({"ok": False, "slot": slot, "start": start, "error": "timeout"})
            continue

        if out_path.exists() and out_path.stat().st_size > 10 * 1024:
            print(f"  clip_extractor: ✅ {slot} clip → {out_path.name} (start={start}s)")
            results.append({
                "ok": True,
                "path": str(out_path),
                "start": start,
                "duration": clip_duration,
                "slot": slot,
            })
        else:
            print(f"  clip_extractor: ❌ {slot} output missing or too small")
            results.append({"ok": False, "slot": slot, "start": start,
                            "error": "output missing or too small"})

    return results
