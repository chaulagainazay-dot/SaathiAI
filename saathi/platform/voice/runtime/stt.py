"""Provider-neutral speech recognition (STT) for Voice Runtime.

Never auto-installs Whisper models. Never uses shell=True. No public listeners.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import wave
from typing import Any, Protocol, Sequence


@dataclass
class TranscriptResult:
    text: str
    confidence: float
    language: str
    is_final: bool
    provider: str
    duration_ms: float = 0.0
    streaming: bool = False
    partial: bool = False
    health_state: str = "ready"
    error_category: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "language": self.language,
            "is_final": self.is_final,
            "provider": self.provider,
            "duration_ms": self.duration_ms,
            "streaming": self.streaming,
            "partial": self.partial,
            "health_state": self.health_state,
            "error_category": self.error_category,
        }


class SpeechRecognitionProvider(Protocol):
    provider_id: str

    def available(self) -> bool: ...

    def health(self) -> dict[str, Any]: ...

    def cancel(self) -> None: ...

    def transcribe(
        self,
        audio: Sequence[float] | bytes,
        *,
        sample_rate: int = 16_000,
        language: str = "en",
        timeout_seconds: float = 30.0,
    ) -> TranscriptResult: ...


class UnavailableSpeechRecognitionProvider:
    provider_id = "unavailable"

    def available(self) -> bool:
        return False

    def health(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "state": "unavailable",
            "configured": True,
            "installed": False,
            "streaming": False,
            "runtime_verified": False,
            "auto_install": False,
        }

    def cancel(self) -> None:
        return None

    def transcribe(
        self,
        audio: Sequence[float] | bytes,
        *,
        sample_rate: int = 16_000,
        language: str = "en",
        timeout_seconds: float = 30.0,
    ) -> TranscriptResult:
        return TranscriptResult(
            text="",
            confidence=0.0,
            language=language,
            is_final=True,
            provider=self.provider_id,
            health_state="unavailable",
            error_category="provider_unavailable",
        )


class BrowserPassthroughSpeechRecognitionProvider:
    """Accepts browser Web Speech API transcripts (streaming partials + finals)."""

    provider_id = "browser"

    def __init__(self) -> None:
        self._cancelled = False

    def available(self) -> bool:
        return True

    def health(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "state": "ready",
            "configured": True,
            "installed": True,
            "streaming": True,
            "runtime_verified": True,
            "auto_install": False,
            "note": "Browser performs recognition; server carries the transcript.",
        }

    def cancel(self) -> None:
        self._cancelled = True

    def accept_text(
        self,
        text: str,
        *,
        language: str = "en",
        confidence: float = 0.85,
        is_final: bool = True,
        partial: bool = False,
    ) -> TranscriptResult:
        if self._cancelled:
            return TranscriptResult(
                text="",
                confidence=0.0,
                language=language,
                is_final=True,
                provider=self.provider_id,
                error_category="cancelled",
            )
        cleaned = (text or "").strip()
        return TranscriptResult(
            text=cleaned,
            confidence=max(0.0, min(1.0, float(confidence))),
            language=language,
            is_final=is_final,
            provider=self.provider_id,
            streaming=partial or not is_final,
            partial=partial or not is_final,
        )

    def transcribe(
        self,
        audio: Sequence[float] | bytes,
        *,
        sample_rate: int = 16_000,
        language: str = "en",
        timeout_seconds: float = 30.0,
    ) -> TranscriptResult:
        raise NotImplementedError(
            "browser provider carries text; use accept_text for transcripts"
        )


class MacOSSpeechRecognitionProvider:
    """Best-effort macOS local recognition using dictation-friendly tools.

    Preferred when a local speech recognition binary is available. Falls back
    to unavailable health without installing anything.
    """

    provider_id = "macos_speech"

    def __init__(self) -> None:
        self._cancelled = False

    def available(self) -> bool:
        # Prefer explicit helper if present; otherwise no silent install path.
        return bool(shutil.which("say")) and self._dictation_probe_ok()

    def _dictation_probe_ok(self) -> bool:
        # macOS Speech framework is not exposed as a simple CLI. We certify the
        # provider as installed only when a dedicated local helper exists.
        helper = Path.home() / "Library" / "Application Support" / "SaathiOS" / "stt-helper"
        return helper.exists() and helper.is_file()

    def health(self) -> dict[str, Any]:
        ready = self.available()
        return {
            "provider_id": self.provider_id,
            "state": "ready" if ready else "unavailable",
            "configured": True,
            "installed": ready,
            "streaming": False,
            "runtime_verified": ready,
            "auto_install": False,
            "note": (
                "Requires local SaathiOS STT helper; no automatic install."
                if not ready
                else "Local macOS STT helper present."
            ),
        }

    def cancel(self) -> None:
        self._cancelled = True

    def transcribe(
        self,
        audio: Sequence[float] | bytes,
        *,
        sample_rate: int = 16_000,
        language: str = "en",
        timeout_seconds: float = 30.0,
    ) -> TranscriptResult:
        t0 = time.monotonic()
        if self._cancelled:
            return TranscriptResult(
                text="",
                confidence=0.0,
                language=language,
                is_final=True,
                provider=self.provider_id,
                error_category="cancelled",
            )
        if not self.available():
            return TranscriptResult(
                text="",
                confidence=0.0,
                language=language,
                is_final=True,
                provider=self.provider_id,
                health_state="unavailable",
                error_category="provider_unavailable",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        helper = Path.home() / "Library" / "Application Support" / "SaathiOS" / "stt-helper"
        wav_path = self._write_temp_wav(audio, sample_rate=sample_rate)
        try:
            if self._cancelled:
                return TranscriptResult(
                    text="",
                    confidence=0.0,
                    language=language,
                    is_final=True,
                    provider=self.provider_id,
                    error_category="cancelled",
                )
            # Argument array only — never shell=True.
            completed = subprocess.run(
                [str(helper), "--file", str(wav_path), "--lang", language],
                capture_output=True,
                text=True,
                timeout=max(1.0, min(float(timeout_seconds), 60.0)),
                check=False,
            )
            text = (completed.stdout or "").strip()
            ok = completed.returncode == 0 and bool(text)
            return TranscriptResult(
                text=text if ok else "",
                confidence=0.8 if ok else 0.0,
                language=language,
                is_final=True,
                provider=self.provider_id,
                duration_ms=(time.monotonic() - t0) * 1000,
                health_state="ready" if ok else "failed",
                error_category="" if ok else "recognition_failed",
            )
        except subprocess.TimeoutExpired:
            return TranscriptResult(
                text="",
                confidence=0.0,
                language=language,
                is_final=True,
                provider=self.provider_id,
                duration_ms=(time.monotonic() - t0) * 1000,
                error_category="timeout",
            )
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass

    @staticmethod
    def _write_temp_wav(
        audio: Sequence[float] | bytes, *, sample_rate: int
    ) -> Path:
        fd, name = tempfile.mkstemp(prefix="saathi_stt_", suffix=".wav")
        path = Path(name)
        try:
            if isinstance(audio, (bytes, bytearray)):
                path.write_bytes(bytes(audio))
                return path
            import array
            import math
            import os

            os.close(fd)
            pcm = array.array("h")
            for sample in audio:
                value = max(-1.0, min(1.0, float(sample)))
                pcm.append(int(value * 32767.0))
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(int(sample_rate))
                handle.writeframes(pcm.tobytes())
            return path
        except Exception:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            raise


class WhisperCompatibleSpeechRecognitionProvider:
    """Adapter for a Whisper-compatible local runtime if already installed.

    Does not download models. Does not install packages.
    """

    provider_id = "whisper_compatible"

    def __init__(self, model_size: str = "tiny") -> None:
        self.model_size = model_size
        self._model = None
        self._cancelled = False

    def available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401

            return True
        except Exception:
            return False

    def health(self) -> dict[str, Any]:
        ready = self.available()
        return {
            "provider_id": self.provider_id,
            "state": "ready" if ready else "unavailable",
            "configured": True,
            "installed": ready,
            "model_size": self.model_size,
            "streaming": False,
            "runtime_verified": ready,
            "auto_install": False,
            "note": (
                "Uses already-installed faster_whisper only; never auto-downloads."
            ),
        }

    def cancel(self) -> None:
        self._cancelled = True

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            # int8/cpu is the low-RAM path for M2/8 GB hosts.
            self._model = WhisperModel(
                self.model_size, device="cpu", compute_type="int8"
            )
        return self._model

    def transcribe(
        self,
        audio: Sequence[float] | bytes,
        *,
        sample_rate: int = 16_000,
        language: str = "en",
        timeout_seconds: float = 30.0,
    ) -> TranscriptResult:
        t0 = time.monotonic()
        if self._cancelled:
            return TranscriptResult(
                text="",
                confidence=0.0,
                language=language,
                is_final=True,
                provider=self.provider_id,
                error_category="cancelled",
            )
        if not self.available():
            return TranscriptResult(
                text="",
                confidence=0.0,
                language=language,
                is_final=True,
                provider=self.provider_id,
                health_state="unavailable",
                error_category="provider_unavailable",
            )
        try:
            import numpy as np

            if isinstance(audio, (bytes, bytearray)):
                # Expect float32 PCM if raw bytes of samples are not provided.
                samples = np.frombuffer(bytes(audio), dtype=np.int16).astype(np.float32)
                samples = samples / 32768.0
            else:
                samples = np.asarray(list(audio), dtype=np.float32)
            if self._cancelled:
                return TranscriptResult(
                    text="",
                    confidence=0.0,
                    language=language,
                    is_final=True,
                    provider=self.provider_id,
                    error_category="cancelled",
                )
            model = self._load()
            segments, info = model.transcribe(
                samples,
                language=language.split("-")[0],
                beam_size=1,
                vad_filter=False,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            conf = float(getattr(info, "language_probability", 0.5) or 0.5)
            return TranscriptResult(
                text=text,
                confidence=conf,
                language=getattr(info, "language", language) or language,
                is_final=True,
                provider=self.provider_id,
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception:
            return TranscriptResult(
                text="",
                confidence=0.0,
                language=language,
                is_final=True,
                provider=self.provider_id,
                duration_ms=(time.monotonic() - t0) * 1000,
                error_category="recognition_failed",
            )


def default_stt_providers() -> list[SpeechRecognitionProvider]:
    return [
        MacOSSpeechRecognitionProvider(),
        WhisperCompatibleSpeechRecognitionProvider(),
        BrowserPassthroughSpeechRecognitionProvider(),
        UnavailableSpeechRecognitionProvider(),
    ]


def discover_stt_providers(
    providers: list[SpeechRecognitionProvider] | None = None,
) -> list[dict[str, Any]]:
    out = []
    for provider in providers or default_stt_providers():
        health = provider.health()
        out.append(
            {
                **health,
                "available": bool(provider.available()),
            }
        )
    return out


def select_stt_provider(
    prefer: str = "auto",
    providers: list[SpeechRecognitionProvider] | None = None,
) -> SpeechRecognitionProvider:
    catalog = providers or default_stt_providers()
    by_id = {p.provider_id: p for p in catalog}
    if prefer and prefer != "auto":
        chosen = by_id.get(prefer)
        if chosen and chosen.available():
            return chosen
        return by_id.get("unavailable") or UnavailableSpeechRecognitionProvider()
    for provider_id in ("macos_speech", "whisper_compatible", "browser"):
        provider = by_id.get(provider_id)
        if provider and provider.available():
            return provider
    return by_id.get("unavailable") or UnavailableSpeechRecognitionProvider()
