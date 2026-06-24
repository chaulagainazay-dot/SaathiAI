"""
Text-to-Speech for Mr. Yeti pipeline.
Primary:  Gemini TTS — Charon voice with emotional delivery
Fallback: en-GB-RyanNeural via edge-tts

Usage:
    from .tts import speak, speak_script
    audio_path = speak("Score Band 7 with this one trick")
    audio_path = speak_script(script_dict)   # full scene narration merged
"""

from __future__ import annotations

import os
import struct
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

from .. import config

OUT_DIR = config.ROOT / "data" / "tts_cache"
OUT_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_VOICE   = "Charon"
FALLBACK_VOICE = "en-GB-RyanNeural"
_VENV_EDGE     = config.ROOT / ".venv" / "bin" / "edge-tts"

# Emotion map — injected based on scene position / keyword
_EMOTION_PROMPTS = {
    "hook":    "Say this with high excitement and energy, like you just discovered something amazing: ",
    "tip":     "Say this in a warm, encouraging, happy tone like you are helping a close friend: ",
    "problem": "Say this with genuine concern and a slightly sad tone, like you feel their struggle: ",
    "result":  "Say this with pure excitement and joy, like celebrating a big win: ",
    "cta":     "Say this enthusiastically and confidently, like you really want them to take action: ",
    "default": "Say this in a friendly, engaging, and expressive tone with natural emotion: ",
}


# ── Gemini TTS ────────────────────────────────────────────────────────────────

def _gemini_speak(text: str, emotion: str = "default", slug: str = "") -> str:
    """Generate speech via Gemini TTS (Charon voice) with emotion. Returns WAV path."""
    slug = slug or datetime.now().strftime("%Y%m%d_%H%M%S")
    out  = OUT_DIR / f"tts_{slug}.wav"

    prompt = _EMOTION_PROMPTS.get(emotion, _EMOTION_PROMPTS["default"]) + text

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=GEMINI_VOICE
                        )
                    )
                ),
            ),
        )
        audio_data = response.candidates[0].content.parts[0].inline_data.data
        _write_wav(out, audio_data)
        return str(out)
    except Exception as e:
        print(f"⚠️  Gemini TTS failed ({e}) — falling back to edge-tts")
        return ""


def _write_wav(path: Path, pcm_data: bytes, sample_rate: int = 24000):
    """Write raw PCM bytes as a proper WAV file."""
    with open(path, "wb") as f:
        data_size = len(pcm_data)
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate,
                            sample_rate * 2, 2, 16))
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(pcm_data)


# ── Edge-TTS fallback ─────────────────────────────────────────────────────────

def _edge_speak(text: str, slug: str = "") -> str:
    slug = slug or datetime.now().strftime("%Y%m%d_%H%M%S")
    out  = OUT_DIR / f"tts_{slug}.mp3"
    try:
        r = subprocess.run(
            [str(_VENV_EDGE), "--voice", FALLBACK_VOICE,
             "--text", text, "--write-media", str(out)],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0 and out.exists():
            return str(out)
    except Exception:
        pass
    # Last resort: macOS say
    out_aiff = OUT_DIR / f"tts_{slug}.aiff"
    subprocess.run(["say", "-o", str(out_aiff), text], timeout=30)
    subprocess.run(["ffmpeg", "-i", str(out_aiff), str(out), "-y", "-loglevel", "quiet"])
    return str(out)


# ── Public API ────────────────────────────────────────────────────────────────

def speak(text: str, emotion: str = "default", slug: str = "") -> str:
    """Generate TTS — Gemini Charon with emotion, falls back to edge-tts."""
    slug = slug or datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _gemini_speak(text, emotion=emotion, slug=slug)
    if not path:
        path = _edge_speak(text, slug=slug)
    return path


def speak_script(script: dict, slug: str = "") -> str:
    """
    Generate full voiced narration for a Mr. Yeti script dict.
    Assigns emotions per scene position: hook=excited, middle=tip/sad, end=cta.
    Returns path to merged audio file.
    """
    slug   = slug or datetime.now().strftime("%Y%m%d_%H%M%S")
    scenes = script.get("scenes", [])
    hook   = script.get("hook", "")
    parts: list[str] = []

    if hook:
        p = speak(hook, emotion="hook", slug=f"{slug}_hook")
        if p: parts.append(p)

    total = len(scenes)
    for i, s in enumerate(scenes):
        text = s.get("speech", "")
        if not text:
            continue
        # Assign emotion by position
        if i == 0:
            emotion = "tip"
        elif i == total - 1:
            emotion = "cta"
        elif "struggle" in text.lower() or "hard" in text.lower() or "fail" in text.lower():
            emotion = "problem"
        elif "score" in text.lower() or "band" in text.lower() or "pass" in text.lower():
            emotion = "result"
        else:
            emotion = "tip"
        p = speak(text, emotion=emotion, slug=f"{slug}_s{i}")
        if p: parts.append(p)

    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return _concat_mp3(parts, OUT_DIR / f"tts_{slug}_full.wav")


def add_voiceover(video_path: str, audio_path: str, output_path: str = "") -> str:
    """
    Mix TTS audio onto a video file.
    - If video has no audio: just mux
    - If video has audio: mix (TTS louder, bg quieter)
    Returns output video path.
    """
    video_path  = Path(video_path)
    audio_path  = Path(audio_path)
    output_path = Path(output_path) if output_path else \
                  video_path.parent / f"{video_path.stem}_voiced{video_path.suffix}"

    # Check if video has audio stream
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True
    )
    has_audio = bool(probe.stdout.strip())

    # Always replace existing audio with TTS voice (strip original audio)
    cmd = [
        "ffmpeg", "-i", str(video_path), "-i", str(audio_path),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-shortest",
        str(output_path), "-y", "-loglevel", "quiet"
    ]

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode == 0 and output_path.exists():
        return str(output_path)
    raise RuntimeError(f"ffmpeg voiceover failed: {r.stderr[-300:]}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _concat_mp3(paths: list[str], out: Path) -> str:
    """Concatenate multiple MP3s into one using ffmpeg concat."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for p in paths:
            f.write(f"file '{p}'\n")
        list_file = f.name

    subprocess.run(
        ["ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file,
         "-c", "copy", str(out), "-y", "-loglevel", "quiet"],
        timeout=60
    )
    return str(out)
