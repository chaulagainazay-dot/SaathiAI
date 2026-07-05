"""Voice — narration synthesis. Local-first, provider chain, honest fallback.

Primary: Kokoro (local, free, deterministic, offline). Falls back through the
chain the platform already believes in: Kokoro → OpenAI TTS → ElevenLabs →
macOS `say` (always-available on this Mac). Returns WAV bytes, or None if every
provider is unavailable (the PAT then shows the voice stage ✗ honestly).

The pipeline never changes when providers change — only this module does.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

VOICE_CHAIN = ("kokoro", "openai", "elevenlabs", "say")


def synthesize(text: str, *, voice: str = "af_heart", chain=VOICE_CHAIN) -> bytes | None:
    text = (text or "").strip()
    if not text:
        return None
    for provider in chain:
        try:
            data = _PROVIDERS[provider](text, voice)
            if data:
                return data
        except Exception:
            continue
    return None


def _kokoro(text: str, voice: str) -> bytes | None:
    import importlib.util
    if importlib.util.find_spec("kokoro") is None:
        return None
    import io
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline
    pipe = KPipeline(lang_code="a")
    chunks = [audio for _, _, audio in pipe(text, voice=voice)]
    if not chunks:
        return None
    wav = np.concatenate(chunks)
    buf = io.BytesIO()
    sf.write(buf, wav, 24000, format="WAV")
    return buf.getvalue()


def _openai(text: str, voice: str) -> bytes | None:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    import httpx
    r = httpx.post("https://api.openai.com/v1/audio/speech",
                   headers={"Authorization": f"Bearer {key}"},
                   json={"model": "tts-1", "voice": "fable", "input": text,
                         "response_format": "wav"}, timeout=60)
    return r.content if r.status_code == 200 else None


def _elevenlabs(text: str, voice: str) -> bytes | None:
    key = os.getenv("ELEVENLABS_API_KEY")
    vid = os.getenv("ELEVENLABS_VOICE_ID")
    if not (key and vid):
        return None
    import httpx
    r = httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
                   headers={"xi-api-key": key},
                   json={"text": text, "model_id": "eleven_turbo_v2"}, timeout=60)
    if r.status_code != 200:
        return None
    return _to_wav_bytes(r.content, "mp3")


def _say(text: str, voice: str) -> bytes | None:
    """macOS system TTS — always available here, offline, zero cost."""
    import shutil
    if not shutil.which("say"):
        return None
    with tempfile.TemporaryDirectory() as d:
        aiff = Path(d) / "n.aiff"
        subprocess.run(["say", "-o", str(aiff), text], check=True, timeout=120)
        return _to_wav_bytes(aiff.read_bytes(), "aiff")


def _to_wav_bytes(data: bytes, in_fmt: str) -> bytes | None:
    import shutil
    if not shutil.which("ffmpeg"):
        return None
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d) / f"in.{in_fmt}", Path(d) / "out.wav"
        src.write_bytes(data)
        subprocess.run(["ffmpeg", "-y", "-i", str(src), "-ar", "24000", "-ac", "1", str(dst)],
                       check=True, capture_output=True, timeout=120)
        return dst.read_bytes()


_PROVIDERS = {"kokoro": _kokoro, "openai": _openai, "elevenlabs": _elevenlabs, "say": _say}
