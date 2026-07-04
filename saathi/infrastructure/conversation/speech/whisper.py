"""Whisper STT driver (guarded) — faster-whisper local, or GLM Speech cloud.

Never a hard dependency: `available()` is False unless faster-whisper is
installed. Real transcription wiring lives here and nowhere else.
"""
from __future__ import annotations

import os

from .base import SttDriver


class WhisperStt(SttDriver):
    name = "whisper"

    def __init__(self, model: str | None = None):
        self._model_name = model or os.getenv("WHISPER_MODEL", "base")
        self._model = None

    def available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except Exception:
            return False

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self._model_name)
        return self._model

    def transcribe(self, audio, *, locale: str = "en") -> str:
        # `audio` = path or file-like accepted by faster-whisper
        segments, _ = self._load().transcribe(audio, language=locale or None)
        return " ".join(s.text for s in segments).strip()
