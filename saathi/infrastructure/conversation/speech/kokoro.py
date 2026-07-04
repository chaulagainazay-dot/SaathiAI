"""Kokoro TTS driver (guarded) — local neural TTS; ElevenLabs is a premium peer.

Never a hard dependency: `available()` is False unless kokoro is installed.
"""
from __future__ import annotations

import os

from .base import TtsDriver


class KokoroTts(TtsDriver):
    name = "kokoro"

    def __init__(self, voice: str | None = None):
        self._voice = voice or os.getenv("KOKORO_VOICE", "af_heart")
        self._pipe = None

    def available(self) -> bool:
        try:
            import kokoro  # noqa: F401
            return True
        except Exception:
            return False

    def _pipeline(self):
        if self._pipe is None:
            from kokoro import KPipeline
            self._pipe = KPipeline(lang_code="a")
        return self._pipe

    def synthesize(self, text: str, *, locale: str = "en") -> bytes:
        import io
        import numpy as np
        import soundfile as sf
        chunks = [audio for _, _, audio in self._pipeline()(text, voice=self._voice)]
        wav = np.concatenate(chunks) if chunks else np.zeros(1, dtype="float32")
        buf = io.BytesIO()
        sf.write(buf, wav, 24000, format="WAV")
        return buf.getvalue()
