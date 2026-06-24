"""Mr. Yeti Voice Generator — consistent TTS for every Mr. Yeti video.

Priority chain:
1. OpenAI TTS API  — "onyx" voice (deep, warm, authoritative)
2. gTTS            — British English fallback (free, no key)
3. macOS say       — system fallback (Daniel voice)
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

from .. import config

# ---------------------------------------------------------------------------
# Voice profile
# ---------------------------------------------------------------------------

VOICE_PROFILE = {
    "openai_voice": "onyx",    # deep, warm, authoritative
    "openai_speed": 0.95,
    "gtts_lang": "en",
    "gtts_tld": "co.uk",       # British accent
    "description": "Deep, warm, slightly dramatic British IELTS teacher",
}

_VOICES_DIR = config.ROOT / "data" / "mr_yeti_voices"


# ---------------------------------------------------------------------------
# Text enhancement
# ---------------------------------------------------------------------------

def enhance_script_for_voice(text: str) -> str:
    """Add Yeti personality to plain text before TTS.

    - Add "..." before dramatic reveals
    - Emphasise band scores in caps
    - Add pause markers for punchlines
    - Trim to 500 words (OpenAI TTS limit)
    """
    # Normalise whitespace
    text = text.strip()

    # Emphasise band scores: "band 7" / "band seven" / "Band 5" etc.
    text = re.sub(
        r'\b(band)\s+(seven|7)\b',
        r'BAND SEVEN',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'\b(band)\s+(five|5)\b',
        r'BAND FIVE',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'\b(band)\s+(six|6)\b',
        r'BAND SIX',
        text,
        flags=re.IGNORECASE,
    )

    # Add dramatic "..." before reveals — sentences that start with
    # "This", "Here", "Now", "The truth", "The secret", "The reason"
    text = re.sub(
        r'(?<=[.!?])\s+((?:This|Here|Now|The truth is|The secret is|The real reason)\b)',
        r' ... \1',
        text,
    )

    # Add a pause before the final sentence (punchline pattern)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) > 1:
        sentences[-1] = "... " + sentences[-1]
        text = " ".join(sentences)

    # Trim to 500 words
    words = text.split()
    if len(words) > 500:
        text = " ".join(words[:500]) + "..."

    return text


# ---------------------------------------------------------------------------
# TTS methods
# ---------------------------------------------------------------------------

def _try_openai(text: str, output_path: str) -> bool:
    """Generate audio via OpenAI TTS API. Returns True on success."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return False

    try:
        import urllib.request
        import json

        payload = json.dumps({
            "model": "tts-1",
            "voice": VOICE_PROFILE["openai_voice"],
            "input": text,
            "speed": VOICE_PROFILE["openai_speed"],
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/speech",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            audio_bytes = resp.read()

        Path(output_path).write_bytes(audio_bytes)
        return True

    except Exception as exc:  # noqa: BLE001
        print(f"[mr_yeti_voice] OpenAI TTS failed: {exc}")
        return False


def _try_gtts(text: str, output_path: str) -> bool:
    """Generate audio via gTTS. Returns True on success."""
    try:
        from gtts import gTTS  # type: ignore

        tts = gTTS(
            text=text,
            lang=VOICE_PROFILE["gtts_lang"],
            tld=VOICE_PROFILE["gtts_tld"],
            slow=False,
        )
        tts.save(output_path)
        return True

    except Exception as exc:  # noqa: BLE001
        print(f"[mr_yeti_voice] gTTS failed: {exc}")
        return False


def _try_macos_say(text: str, output_path: str) -> bool:
    """Generate audio via macOS `say` command. Returns True on success."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp:
            aiff_path = tmp.name

        result = subprocess.run(
            ["say", "-v", "Daniel", "-r", "150", "-o", aiff_path, text],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode())

        # Convert AIFF → MP3 via ffmpeg
        ffmpeg_result = subprocess.run(
            ["ffmpeg", "-y", "-i", aiff_path, output_path],
            capture_output=True,
            timeout=60,
        )
        Path(aiff_path).unlink(missing_ok=True)

        if ffmpeg_result.returncode != 0:
            raise RuntimeError(ffmpeg_result.stderr.decode())

        return True

    except Exception as exc:  # noqa: BLE001
        print(f"[mr_yeti_voice] macOS say fallback failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_voice(
    text: str,
    output_path: str,
    enhance_for_yeti: bool = True,
) -> dict:
    """Generate Mr. Yeti's voice for the given text.

    Args:
        text: The script text to synthesise.
        output_path: Where to save the MP3 file.
        enhance_for_yeti: If True, run enhance_script_for_voice() first.

    Returns:
        {"ok": bool, "path": str, "method": str}
    """
    if enhance_for_yeti:
        text = enhance_script_for_voice(text)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    for method_name, fn in [
        ("openai", _try_openai),
        ("gtts", _try_gtts),
        ("macos_say", _try_macos_say),
    ]:
        if fn(text, output_path):
            return {"ok": True, "path": output_path, "method": method_name}

    return {"ok": False, "path": output_path, "method": "none"}


def generate_scene_voices(scenes: list[dict], slug: str) -> list[dict]:
    """Generate voice audio for each scene in a script.

    Each scene dict must have a "speech" key.
    A "voice_path" key is added to each scene on success.

    Args:
        scenes: List of scene dicts with at least a "speech" field.
        slug: Unique identifier for this video (used as subfolder name).

    Returns:
        The same list with "voice_path" added to each scene.
    """
    out_dir = _VOICES_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    for idx, scene in enumerate(scenes):
        speech = scene.get("speech", "")
        if not speech:
            scene["voice_path"] = None
            continue

        output_path = str(out_dir / f"scene_{idx:03d}.mp3")
        result = generate_voice(speech, output_path)
        scene["voice_path"] = result["path"] if result["ok"] else None
        scene["voice_method"] = result.get("method")

    return scenes


def get_voice_status() -> dict:
    """Check which TTS methods are available."""
    status: dict = {}

    # OpenAI
    api_key = os.environ.get("OPENAI_API_KEY", "")
    status["openai"] = {
        "available": bool(api_key),
        "reason": "OPENAI_API_KEY set" if api_key else "OPENAI_API_KEY not set",
    }

    # gTTS
    try:
        import gtts  # noqa: F401
        status["gtts"] = {"available": True, "reason": "gtts package found"}
    except ImportError:
        status["gtts"] = {"available": False, "reason": "pip install gtts"}

    # macOS say
    try:
        say_check = subprocess.run(
            ["say", "--version"],
            capture_output=True,
            timeout=5,
        )
        ffmpeg_check = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
        )
        if say_check.returncode == 0 and ffmpeg_check.returncode == 0:
            status["macos_say"] = {"available": True, "reason": "say + ffmpeg found"}
        elif say_check.returncode == 0:
            status["macos_say"] = {
                "available": False,
                "reason": "say found but ffmpeg missing (brew install ffmpeg)",
            }
        else:
            status["macos_say"] = {"available": False, "reason": "say command not found"}
    except Exception as exc:  # noqa: BLE001
        status["macos_say"] = {"available": False, "reason": str(exc)}

    # Active method
    if status["openai"]["available"]:
        status["active_method"] = "openai"
    elif status["gtts"]["available"]:
        status["active_method"] = "gtts"
    elif status["macos_say"]["available"]:
        status["active_method"] = "macos_say"
    else:
        status["active_method"] = "none"

    status["voice_profile"] = VOICE_PROFILE

    return status
