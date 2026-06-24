"""
backup_video.py — Reliability layer for video generation.

When Google Flow/Veo fails (quota, outage, API error), this module tries
backup generators in priority order:
  1. Runway ML (Gen-3 Alpha)
  2. Kling AI
  3. MiniMax / Hailuo
  4. Pika Labs
  5. Static FFmpeg fallback (always works — no API needed)
"""

import os
import time
import json
import logging
import requests
import subprocess
import tempfile
from pathlib import Path

from .. import config

log = logging.getLogger(__name__)

# ── Priority chain ─────────────────────────────────────────────────────────────
GENERATORS = ["runway", "kling", "minimax", "pika", "static"]

OUT_DIR = config.ROOT / "data" / "video_cache"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Env key names ──────────────────────────────────────────────────────────────
_KEYS = {
    "runway":  ["RUNWAY_API_KEY"],
    "kling":   ["KLING_API_KEY", "KLING_ACCESS_KEY"],
    "minimax": ["MINIMAX_API_KEY"],
    "pika":    ["PIKA_API_KEY"],
    "static":  [],          # no key required
}


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def generate_with_fallback(
    scene: dict,
    slug: str,
    preferred: str = "veo",
) -> dict:
    """
    Try each generator in GENERATORS until one succeeds.

    Args:
        scene:     {veo_prompt, speech, duration, yeti_pose}
        slug:      unique identifier for output filename
        preferred: hint for the caller's first-choice generator
                   (not used here — we always follow GENERATORS order)

    Returns:
        {"ok": bool, "path": str, "method": str, "error": str}
    """
    last_error = ""
    for name in GENERATORS:
        try:
            log.info("backup_video: trying generator '%s' for slug=%s", name, slug)
            fn = _GENERATOR_FN[name]
            result = fn(scene, slug)
            if result.get("ok"):
                result["method"] = name
                result.setdefault("error", "")
                log.info("backup_video: succeeded with '%s' → %s", name, result["path"])
                return result
            last_error = result.get("error", "unknown error")
            log.warning("backup_video: '%s' returned ok=False: %s", name, last_error)
        except Exception as exc:
            last_error = str(exc)
            log.warning("backup_video: '%s' raised: %s", name, last_error)

    return {"ok": False, "path": "", "method": "none", "error": last_error}


def get_available_generators() -> list[str]:
    """Return list of configured generators that have all required API keys."""
    available = []
    for name in GENERATORS:
        keys = _KEYS[name]
        if all(os.environ.get(k) for k in keys):
            available.append(name)
    return available


def generator_status() -> dict:
    """Check which generators are configured (have all required env vars)."""
    status = {}
    for name in GENERATORS:
        keys = _KEYS[name]
        if not keys:
            status[name] = {"configured": True, "keys": []}
        else:
            missing = [k for k in keys if not os.environ.get(k)]
            status[name] = {
                "configured": len(missing) == 0,
                "keys": keys,
                "missing": missing if missing else [],
            }
    return status


# ══════════════════════════════════════════════════════════════════════════════
#  RUNWAY ML
# ══════════════════════════════════════════════════════════════════════════════

def generate_runway(scene: dict, slug: str) -> dict:
    """
    Runway Gen-3 Alpha — image_to_video endpoint.
    Polls for completion (up to 3 minutes).
    """
    api_key = os.environ.get("RUNWAY_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "RUNWAY_API_KEY not set"}

    prompt = scene.get("veo_prompt", scene.get("speech", ""))
    duration = int(scene.get("duration", 5))

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Runway-Version": "2024-11-06",
    }

    # Find a seed image (yeti pose) if available
    image_url = _get_yeti_image_url(scene)

    payload: dict = {
        "model": "gen3a_turbo",
        "promptText": prompt,
        "duration": min(duration, 10),
        "ratio": "720:1280",  # vertical
    }
    if image_url:
        payload["promptImage"] = image_url

    try:
        resp = requests.post(
            "https://api.dev.runwayml.com/v1/image_to_video",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        task_id = resp.json().get("id")
        if not task_id:
            return {"ok": False, "error": f"No task id in response: {resp.text}"}

        # Poll up to 3 min
        out_path = str(OUT_DIR / f"{slug}_runway.mp4")
        return _runway_poll(task_id, headers, out_path)

    except requests.HTTPError as e:
        return {"ok": False, "error": f"Runway HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _runway_poll(task_id: str, headers: dict, out_path: str) -> dict:
    deadline = time.time() + 180
    while time.time() < deadline:
        time.sleep(8)
        try:
            r = requests.get(
                f"https://api.dev.runwayml.com/v1/tasks/{task_id}",
                headers=headers,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            status = data.get("status", "")
            if status == "SUCCEEDED":
                video_url = (data.get("output") or [None])[0]
                if not video_url:
                    return {"ok": False, "error": "No output URL from Runway"}
                return _download_video(video_url, out_path)
            elif status in ("FAILED", "CANCELLED"):
                return {"ok": False, "error": f"Runway task {status}: {data.get('failure', '')}"}
        except Exception as e:
            log.debug("Runway poll error: %s", e)
    return {"ok": False, "error": "Runway polling timed out after 3 min"}


# ══════════════════════════════════════════════════════════════════════════════
#  KLING AI
# ══════════════════════════════════════════════════════════════════════════════

def generate_kling(scene: dict, slug: str) -> dict:
    """
    Kling AI text-to-video / image-to-video API.
    Requires KLING_API_KEY and KLING_ACCESS_KEY.
    """
    api_key = os.environ.get("KLING_API_KEY", "")
    access_key = os.environ.get("KLING_ACCESS_KEY", "")
    if not api_key or not access_key:
        return {"ok": False, "error": "KLING_API_KEY or KLING_ACCESS_KEY not set"}

    prompt = scene.get("veo_prompt", scene.get("speech", ""))
    duration = int(scene.get("duration", 5))

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Access-Key": access_key,
        "Content-Type": "application/json",
    }

    payload = {
        "model_name": "kling-v1",
        "prompt": prompt,
        "duration": min(duration, 10),
        "aspect_ratio": "9:16",
        "mode": "std",
    }

    try:
        resp = requests.post(
            "https://api.klingai.com/v1/videos/text2video",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        task_id = (body.get("data") or {}).get("task_id")
        if not task_id:
            return {"ok": False, "error": f"No task_id: {resp.text[:200]}"}

        out_path = str(OUT_DIR / f"{slug}_kling.mp4")
        return _kling_poll(task_id, headers, out_path)

    except requests.HTTPError as e:
        return {"ok": False, "error": f"Kling HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _kling_poll(task_id: str, headers: dict, out_path: str) -> dict:
    deadline = time.time() + 180
    while time.time() < deadline:
        time.sleep(10)
        try:
            r = requests.get(
                f"https://api.klingai.com/v1/videos/text2video/{task_id}",
                headers=headers,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json().get("data", {})
            status = data.get("task_status", "")
            if status == "succeed":
                works = data.get("task_result", {}).get("videos", [])
                if works:
                    return _download_video(works[0]["url"], out_path)
                return {"ok": False, "error": "Kling: no video URLs in result"}
            elif status == "failed":
                return {"ok": False, "error": f"Kling task failed: {data.get('task_status_msg', '')}"}
        except Exception as e:
            log.debug("Kling poll error: %s", e)
    return {"ok": False, "error": "Kling polling timed out after 3 min"}


# ══════════════════════════════════════════════════════════════════════════════
#  MINIMAX / HAILUO
# ══════════════════════════════════════════════════════════════════════════════

def generate_minimax(scene: dict, slug: str) -> dict:
    """
    MiniMax Hailuo video generation.
    POST https://api.minimax.chat/v1/video_generation
    """
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "MINIMAX_API_KEY not set"}

    prompt = scene.get("veo_prompt", scene.get("speech", ""))

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "video-01",
        "prompt": prompt,
    }

    try:
        resp = requests.post(
            "https://api.minimax.chat/v1/video_generation",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        task_id = body.get("task_id")
        if not task_id:
            return {"ok": False, "error": f"No task_id: {resp.text[:200]}"}

        out_path = str(OUT_DIR / f"{slug}_minimax.mp4")
        return _minimax_poll(task_id, headers, out_path)

    except requests.HTTPError as e:
        return {"ok": False, "error": f"MiniMax HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _minimax_poll(task_id: str, headers: dict, out_path: str) -> dict:
    deadline = time.time() + 180
    while time.time() < deadline:
        time.sleep(8)
        try:
            r = requests.get(
                f"https://api.minimax.chat/v1/query/video_generation?task_id={task_id}",
                headers=headers,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            status = data.get("status", "")
            if status == "Success":
                file_id = data.get("file_id", "")
                if not file_id:
                    return {"ok": False, "error": "MiniMax: no file_id"}
                # Fetch download URL
                fr = requests.get(
                    f"https://api.minimax.chat/v1/files/retrieve?file_id={file_id}",
                    headers=headers,
                    timeout=20,
                )
                fr.raise_for_status()
                dl_url = fr.json().get("file", {}).get("download_url", "")
                if not dl_url:
                    return {"ok": False, "error": "MiniMax: no download_url"}
                return _download_video(dl_url, out_path)
            elif status == "Fail":
                return {"ok": False, "error": f"MiniMax task failed: {data.get('err_msg', '')}"}
        except Exception as e:
            log.debug("MiniMax poll error: %s", e)
    return {"ok": False, "error": "MiniMax polling timed out after 3 min"}


# ══════════════════════════════════════════════════════════════════════════════
#  PIKA LABS
# ══════════════════════════════════════════════════════════════════════════════

def generate_pika(scene: dict, slug: str) -> dict:
    """
    Pika Labs video generation.
    Requires PIKA_API_KEY.
    """
    api_key = os.environ.get("PIKA_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "PIKA_API_KEY not set"}

    prompt = scene.get("veo_prompt", scene.get("speech", ""))
    duration = int(scene.get("duration", 3))

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "promptText": prompt,
        "aspectRatio": "9:16",
        "duration": min(duration, 5),
    }

    try:
        resp = requests.post(
            "https://api.pika.art/v1/generate",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        task_id = body.get("id") or body.get("task_id")
        if not task_id:
            return {"ok": False, "error": f"No task id from Pika: {resp.text[:200]}"}

        out_path = str(OUT_DIR / f"{slug}_pika.mp4")
        return _pika_poll(task_id, headers, out_path)

    except requests.HTTPError as e:
        return {"ok": False, "error": f"Pika HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _pika_poll(task_id: str, headers: dict, out_path: str) -> dict:
    deadline = time.time() + 180
    while time.time() < deadline:
        time.sleep(8)
        try:
            r = requests.get(
                f"https://api.pika.art/v1/task/{task_id}",
                headers=headers,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            status = data.get("status", "")
            if status in ("completed", "finished", "succeeded"):
                video_url = (
                    data.get("resultUrl")
                    or data.get("video_url")
                    or (data.get("videos") or [{}])[0].get("url", "")
                )
                if video_url:
                    return _download_video(video_url, out_path)
                return {"ok": False, "error": "Pika: no video URL in result"}
            elif status in ("failed", "error"):
                return {"ok": False, "error": f"Pika task failed: {data.get('error', '')}"}
        except Exception as e:
            log.debug("Pika poll error: %s", e)
    return {"ok": False, "error": "Pika polling timed out after 3 min"}


# ══════════════════════════════════════════════════════════════════════════════
#  STATIC FALLBACK — FFmpeg (always works)
# ══════════════════════════════════════════════════════════════════════════════

def generate_static_fallback(scene: dict, slug: str) -> dict:
    """
    Static fallback — no API required.

    Steps:
      1. Find Mr. Yeti image (or generate a purple lavfi background)
      2. Generate TTS voice for scene["speech"] using the project's speak()
      3. FFmpeg: loop image + audio + animated text overlay → 1080×1920 MP4
    """
    from .tts import speak

    speech = scene.get("speech", "")
    out_path = str(OUT_DIR / f"{slug}_static.mp4")

    # ── 1. Find Yeti image ────────────────────────────────────────────────────
    yeti_image = _find_yeti_image()

    # ── 2. TTS audio ──────────────────────────────────────────────────────────
    audio_path = ""
    if speech:
        try:
            audio_path = speak(speech, slug=f"{slug}_static")
        except Exception as e:
            log.warning("Static fallback TTS failed: %s", e)

    # ── 3. Build FFmpeg command ───────────────────────────────────────────────
    safe_text = speech.replace("'", "\\'").replace(":", "\\:")[:120]

    drawtext = (
        f"drawtext=text='{safe_text}':"
        "fontcolor=white:"
        "fontsize=40:"
        "fontfile=/System/Library/Fonts/Helvetica.ttc:"
        "x=(w-text_w)/2:"
        "y=h*0.75:"
        "box=1:"
        "boxcolor=black@0.5:"
        "boxborderw=10:"
        # Animate: fade in, then static
        "alpha='if(lt(t,0.5),t/0.5,1)'"
    )

    if yeti_image:
        video_input = ["-loop", "1", "-i", yeti_image]
        video_filter = f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,{drawtext}"
    else:
        # Pure lavfi purple background
        video_input = [
            "-f", "lavfi",
            "-i", "color=c=0x6B21A8:size=1080x1920:rate=30",
        ]
        video_filter = drawtext

    duration = int(scene.get("duration", 5))

    cmd = ["ffmpeg", "-y"]
    cmd += video_input

    if audio_path and Path(audio_path).exists():
        cmd += ["-i", audio_path]
        cmd += [
            "-vf", video_filter,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-shortest",
            "-pix_fmt", "yuv420p",
            out_path,
        ]
    else:
        cmd += [
            "-vf", video_filter,
            "-c:v", "libx264",
            "-t", str(duration),
            "-pix_fmt", "yuv420p",
            "-an",
            out_path,
        ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return {"ok": False, "error": f"FFmpeg error: {result.stderr[-300:]}"}
        return {"ok": True, "path": out_path}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "FFmpeg timed out"}
    except FileNotFoundError:
        return {"ok": False, "error": "FFmpeg not found — install with: brew install ffmpeg"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _find_yeti_image() -> str:
    """Return path to the best available Mr. Yeti image, or '' if none found."""
    candidates = [
        config.ROOT / "data" / "assets" / "yeti_teaching.jpg",
        config.ROOT / "client" / "assets" / "yeti_teaching.png",
        config.ROOT / "client" / "assets" / "yeti_pointing.png",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return ""


def _get_yeti_image_url(scene: dict) -> str:
    """
    Return a public URL for the yeti image if we can serve it,
    otherwise empty string (API will do text-only generation).
    """
    # If scene carries an explicit image URL, use it
    return scene.get("image_url", "")


def _download_video(url: str, out_path: str) -> dict:
    """Download a video URL to out_path."""
    try:
        r = requests.get(url, timeout=120, stream=True)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
        return {"ok": True, "path": out_path}
    except Exception as e:
        return {"ok": False, "error": f"Download failed: {e}"}


# ── Dispatch table (must be after all generate_* functions) ───────────────────
_GENERATOR_FN = {
    "runway":  generate_runway,
    "kling":   generate_kling,
    "minimax": generate_minimax,
    "pika":    generate_pika,
    "static":  generate_static_fallback,
}
