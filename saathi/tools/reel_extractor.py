"""
Reel Extractor — cut a long Veo video into 3 reels via ffmpeg (free, no re-encode).

Long video structure (64 sec, 8 scenes × 8 sec):
  Scene 1-3 → Reel A (Hook reel)     [0:00-0:24]  → TikTok + Instagram
  Scene 4-6 → Reel B (Tip reel)      [0:24-0:48]  → YouTube Shorts
  Scene 1-8 → Reel C (Full story)    [0:00-1:04]  → Facebook (full video)

Uses stream copy (-c copy) — no quality loss, instant extraction.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def extract_reels(long_video_path: str, slug: str, out_dir: Path | str = None) -> dict:
    """
    Cut a long video into 3 reels using ffmpeg stream copy.

    Returns:
      {
        "ok": True,
        "reel_a": "/path/hook_reel.mp4",       # TikTok + Instagram
        "reel_b": "/path/tip_reel.mp4",         # YouTube Shorts
        "reel_c": "/path/full_story_reel.mp4",  # Facebook
      }
    """
    src = Path(long_video_path)
    if not src.exists():
        return {"ok": False, "error": f"Source not found: {long_video_path}"}

    out = Path(out_dir) if out_dir else src.parent
    out.mkdir(parents=True, exist_ok=True)

    # Verify source duration
    dur = _get_duration(src)
    print(f"📐 Source duration: {dur:.1f}s")

    reels = {
        "reel_a": {
            "path": out / f"reel_a_hook_{slug}.mp4",
            "start": "00:00:00", "end": "00:00:24",
            "label": "Hook reel (TikTok + Instagram)",
        },
        "reel_b": {
            "path": out / f"reel_b_tip_{slug}.mp4",
            "start": "00:00:24", "end": "00:00:48",
            "label": "Tip reel (YouTube Shorts)",
        },
        "reel_c": {
            "path": out / f"reel_c_full_{slug}.mp4",
            "start": "00:00:00", "end": None,   # None = to end of file
            "label": "Full story (Facebook)",
        },
    }

    MIN_REEL_BYTES = 10 * 1024  # 10 KB — anything smaller is a broken ffmpeg output

    result = {"ok": True}
    for key, cfg in reels.items():
        out_path = cfg["path"]
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src),
            "-ss", cfg["start"],
        ]
        if cfg["end"]:
            cmd += ["-to", cfg["end"]]
        cmd += [
            "-c", "copy",           # stream copy — no re-encode, no quality loss
            "-avoid_negative_ts", "make_zero",
            str(out_path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=120, check=True)
        except subprocess.CalledProcessError as e:
            print(f"  ❌ {key} ffmpeg failed: {e.stderr.decode()[:200]}")
            result[key] = None
            result["ok"] = False
            continue
        except subprocess.TimeoutExpired:
            print(f"  ❌ {key} ffmpeg timed out after 120s")
            result[key] = None
            result["ok"] = False
            continue

        # Verify output file actually exists and is large enough to be a real video
        if not out_path.exists():
            print(f"  ❌ {key} output file missing after ffmpeg: {out_path}")
            result[key] = None
            result["ok"] = False
            continue

        size_bytes = out_path.stat().st_size
        if size_bytes < MIN_REEL_BYTES:
            print(f"  ❌ {key} output too small ({size_bytes} bytes) — likely corrupt: {out_path.name}")
            result[key] = None
            result["ok"] = False
            continue

        size_kb = size_bytes // 1024
        print(f"  ✅ {cfg['label']} → {out_path.name} ({size_kb}KB)")
        result[key] = str(out_path)

    return result


def _get_duration(path: Path) -> float:
    try:
        import json
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        return float(json.loads(r.stdout).get("format", {}).get("duration", 0))
    except Exception:
        return 0.0
