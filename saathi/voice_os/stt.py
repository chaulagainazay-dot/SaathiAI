"""M12 speech-to-text provider abstraction.

Adapters:
- DeterministicSTT: test/CI adapter, no dependency, always available.
- FasterWhisperSTT: REAL local adapter (faster_whisper is installed in this
  environment) — genuinely transcribes audio, verified in tests against a
  synthetic tone (proves the call path works; not a claim about accuracy on
  real speech, which was not recorded in this session).
- BrowserPassthroughSTT: accepts a transcript the BROWSER already produced
  (webkitSpeechRecognition) — the browser did the real recognition; this
  adapter just carries it through the same contract so the pipeline is
  uniform whether transcription happened client-side or server-side.
Cloud adapters (OpenAI/Gemini-compatible) are contract-ready extension points
— not implemented without keys, never claimed as tested.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class TranscriptResult:
    text: str
    confidence: float
    language: str
    is_final: bool
    provider: str
    duration_ms: float = 0.0


class STTProvider:
    name = "base"

    def available(self) -> bool:
        return False

    def transcribe(self, audio: np.ndarray, *, sample_rate: int = 16000,
                   language: str = "en") -> TranscriptResult:
        raise NotImplementedError


class DeterministicSTT(STTProvider):
    """Test/CI adapter — maps a known synthetic signature to fixed text so
    the full pipeline is deterministically testable without real audio."""
    name = "deterministic"

    def __init__(self, fixed_text: str = "hello saathi"):
        self.fixed_text = fixed_text

    def available(self) -> bool:
        return True

    def transcribe(self, audio: np.ndarray, *, sample_rate: int = 16000,
                   language: str = "en") -> TranscriptResult:
        t0 = time.monotonic()
        text = self.fixed_text if len(audio) > 0 else ""
        return TranscriptResult(text=text, confidence=0.95 if text else 0.0,
                                language=language, is_final=True, provider=self.name,
                                duration_ms=(time.monotonic() - t0) * 1000)


class FasterWhisperSTT(STTProvider):
    """Real local STT via faster_whisper (installed in this environment)."""
    name = "faster_whisper"

    def __init__(self, model_size: str = "tiny"):
        self.model_size = model_size
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
            self._model = WhisperModel(self.model_size, device="cpu",
                                       compute_type="int8")
        return self._model

    def transcribe(self, audio: np.ndarray, *, sample_rate: int = 16000,
                   language: str = "en") -> TranscriptResult:
        t0 = time.monotonic()
        model = self._load()
        segments, info = model.transcribe(audio.astype(np.float32), language=language,
                                          beam_size=1, vad_filter=False)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        dt = (time.monotonic() - t0) * 1000
        return TranscriptResult(text=text, confidence=float(getattr(info, "language_probability", 0.5) or 0.5),
                                language=getattr(info, "language", language) or language,
                                is_final=True, provider=self.name, duration_ms=dt)


class BrowserPassthroughSTT(STTProvider):
    """Carries a transcript the browser's own SpeechRecognition produced."""
    name = "browser"

    def available(self) -> bool:
        return True

    def transcribe_text(self, text: str, *, confidence: float = 0.8,
                        language: str = "en", is_final: bool = True) -> TranscriptResult:
        return TranscriptResult(text=text, confidence=confidence, language=language,
                                is_final=is_final, provider=self.name)

    def transcribe(self, audio: np.ndarray, *, sample_rate: int = 16000,
                   language: str = "en") -> TranscriptResult:
        raise NotImplementedError("browser adapter carries text, not audio — use transcribe_text")


_PROVIDERS: dict[str, STTProvider] = {}


def register(name: str, provider: STTProvider) -> None:
    _PROVIDERS[name] = provider


def select_provider(prefer: str = "auto") -> STTProvider:
    """Local-first: faster_whisper if available, else deterministic. `browser`
    must be selected explicitly (it doesn't take raw audio)."""
    if prefer != "auto" and prefer in _PROVIDERS:
        p = _PROVIDERS[prefer]
        if p.available():
            return p
    fw = _PROVIDERS.get("faster_whisper")
    if fw and fw.available():
        return fw
    return _PROVIDERS["deterministic"]


def provider_status() -> list[dict]:
    """Health matrix — configured/available is NOT the same as tested."""
    out = []
    for name, p in _PROVIDERS.items():
        out.append({"name": name, "configured": True, "available": p.available(),
                   "streaming_support": name == "browser",
                   "local": name in ("faster_whisper", "deterministic")})
    return out


def _bootstrap() -> None:
    if _PROVIDERS:
        return
    register("deterministic", DeterministicSTT())
    register("faster_whisper", FasterWhisperSTT())
    register("browser", BrowserPassthroughSTT())


_bootstrap()
