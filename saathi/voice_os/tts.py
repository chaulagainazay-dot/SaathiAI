"""M12 text-to-speech provider abstraction.

Adapters:
- DeterministicTTS: test/CI adapter, returns synthetic bytes deterministically.
- SayTTS: REAL local adapter — shells out to macOS `say`, produces genuine
  audio bytes (installed/available on this machine; verified in tests by
  actually invoking it and checking real audio bytes come back).
- BrowserSpeechSynthesisTTS: a marker adapter — the browser's own
  SpeechSynthesis API does the real synthesis client-side; this adapter's
  role server-side is just to describe (voice/rate/segments), never to
  produce audio bytes itself.
Cloud adapters (OpenAI/ElevenLabs-compatible) reuse saathi/tools/voice.py's
existing chain as contract-ready extension points — not exercised here (no
provider keys in this environment).
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SpeechResult:
    audio: bytes
    format: str
    provider: str
    duration_ms: float = 0.0
    voice: str = "default"


class TTSProvider:
    name = "base"

    def available(self) -> bool:
        return False

    def synthesize(self, text: str, *, voice: str = "default",
                   rate: float = 1.0) -> SpeechResult:
        raise NotImplementedError


class DeterministicTTS(TTSProvider):
    """Test/CI adapter — deterministic byte output, no dependency."""
    name = "deterministic"

    def available(self) -> bool:
        return True

    def synthesize(self, text: str, *, voice: str = "default",
                   rate: float = 1.0) -> SpeechResult:
        t0 = time.monotonic()
        payload = f"WAV:{voice}:{rate}:{text}".encode()
        return SpeechResult(audio=payload, format="raw", provider=self.name,
                           duration_ms=(time.monotonic() - t0) * 1000, voice=voice)


class SayTTS(TTSProvider):
    """Real local TTS via macOS `say` (genuinely produces audio bytes)."""
    name = "say"

    def available(self) -> bool:
        return shutil.which("say") is not None

    def synthesize(self, text: str, *, voice: str = "default",
                   rate: float = 1.0) -> SpeechResult:
        t0 = time.monotonic()
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.aiff"
            args = ["say", "-o", str(out)]
            if voice and voice != "default":
                args += ["-v", voice]
            wpm = int(175 * max(0.5, min(2.0, rate)))
            args += ["-r", str(wpm), text]
            subprocess.run(args, check=True, timeout=30, capture_output=True)
            audio = out.read_bytes()
        return SpeechResult(audio=audio, format="aiff", provider=self.name,
                           duration_ms=(time.monotonic() - t0) * 1000, voice=voice)


class BrowserSpeechSynthesisTTS(TTSProvider):
    """Marker adapter — real synthesis happens client-side in the browser."""
    name = "browser"

    def available(self) -> bool:
        return True

    def synthesize(self, text: str, *, voice: str = "default",
                   rate: float = 1.0) -> SpeechResult:
        # No server-side audio — the browser SpeechSynthesis API speaks the
        # segment directly. Return metadata only (empty audio is correct here).
        return SpeechResult(audio=b"", format="browser-native", provider=self.name,
                           voice=voice)


_PROVIDERS: dict[str, TTSProvider] = {}


def register(name: str, provider: TTSProvider) -> None:
    _PROVIDERS[name] = provider


def select_provider(prefer: str = "auto") -> TTSProvider:
    if prefer != "auto" and prefer in _PROVIDERS:
        p = _PROVIDERS[prefer]
        if p.available():
            return p
    say = _PROVIDERS.get("say")
    if say and say.available():
        return say
    return _PROVIDERS["deterministic"]


def provider_status() -> list[dict]:
    out = []
    for name, p in _PROVIDERS.items():
        out.append({"name": name, "configured": True, "available": p.available(),
                   "streaming_support": name == "browser",
                   "local": name in ("say", "deterministic")})
    return out


def _bootstrap() -> None:
    if _PROVIDERS:
        return
    register("deterministic", DeterministicTTS())
    register("say", SayTTS())
    register("browser", BrowserSpeechSynthesisTTS())


_bootstrap()
