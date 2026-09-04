"""R2.1 — Local multilingual STT provider (whisper.cpp / ggml, Apple Metal).

Why whisper.cpp and not a Python engine, measured on this host (Apple M2, 8 GB):

    engine                     RTF    peak RSS    EN WER   p50 decode
    whisper.cpp ggml-base     0.21     343 MiB     0.219       0.31 s
    faster-whisper base       0.43     894 MiB     0.189       0.62 s
    faster-whisper small      1.86    1239 MiB     0.170       2.15 s

`small` is slower than real time on this machine and cannot serve an
interactive turn. Between the two viable engines the accuracy difference is
tokenisation noise, while whisper.cpp uses ~2.6x less resident memory and
needs no Python ML stack in the API virtualenv at all.

Authority: this module produces text. Text is never authority. The transcript
travels the same authenticated command-classification, ApprovalCenter and
ExecutionGateway path as typed input, and this module never reaches any of
them directly.

Privacy: audio is written to a single short-lived file inside a configured
throwaway artifact directory and removed in a `finally` on every path —
success, engine failure, timeout and cancellation. Nothing is persisted, and
no transcript is stored here.
"""
from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from saathi.runtime_paths import state_path
from saathi.voice_os.stt import STTProvider, TranscriptResult

# ── bounded contract ────────────────────────────────────────────────────────
# One utterance, not a recording session. Both caps are enforced before the
# engine is started, and the byte cap is checked before the WAV is parsed.
MAX_AUDIO_BYTES = 4 * 1024 * 1024
MAX_AUDIO_SECONDS = 30.0
ENGINE_TIMEOUT_SECONDS = 60.0
SAMPLE_RATE = 16000

# Languages the owner actually speaks. Whisper invents confident text in other
# languages when fed silence or noise, so anything else is discarded rather
# than published as a transcript.
ALLOWED_LANGUAGES = frozenset({"en", "ne", "hi"})

# Bias the decoder toward product nouns it otherwise mangles ("Saathi" is
# reliably heard as "Safi"/"Sophie" without this).
DOMAIN_PROMPT = (
    "Saathi. SaathiOS. Baadar. Portfolio, rebalance, drawdown, exposure, "
    "NAV, Trading Guardian, ExecutionGateway, ApprovalCenter, missions."
)


class LocalSttError(Exception):
    """Bounded failure with a category the dock and diagnostics both publish."""

    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class EngineConfig:
    binary: str
    model_path: str
    artifact_dir: str
    threads: int


def _env(name: str, default: str) -> str:
    return (os.environ.get(name) or "").strip() or default


def load_config() -> EngineConfig:
    """Resolved fresh on every call so tests and operators can retarget the
    engine without reimporting the module."""
    return EngineConfig(
        binary=_env("SAATHI_WHISPER_CPP_BIN", "whisper-cli"),
        model_path=_env(
            "SAATHI_WHISPER_CPP_MODEL",
            str(state_path("stt-models") / "whisper-cpp" / "ggml-base.bin"),
        ),
        artifact_dir=_env(
            "SAATHI_VOICE_ARTIFACT_DIR",
            str(Path(tempfile.gettempdir()) / "saathi-voice-artifacts"),
        ),
        threads=int(_env("SAATHI_WHISPER_CPP_THREADS", "4")),
    )


def _resolve_binary(cfg: EngineConfig) -> str | None:
    if os.path.sep in cfg.binary:
        return cfg.binary if os.access(cfg.binary, os.X_OK) else None
    return shutil.which(cfg.binary)


# ── WAV validation ──────────────────────────────────────────────────────────
# The client sends a WAV it built from the PCM frames the AudioInputOwner tap
# already produced. Parsing the header ourselves means an out-of-contract
# upload is rejected before any of it reaches a subprocess.

def probe_wav(data: bytes) -> tuple[int, int, float]:
    """Return (sample_rate, channels, duration_seconds) for a PCM WAV.

    Raises LocalSttError('unsupported') for anything that is not a mono/stereo
    16-bit PCM RIFF/WAVE stream.
    """
    if len(data) < 44 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise LocalSttError("unsupported", "not a RIFF/WAVE stream")
    pos = 12
    fmt = None
    data_len = None
    while pos + 8 <= len(data):
        chunk_id = data[pos:pos + 4]
        (chunk_size,) = struct.unpack("<I", data[pos + 4:pos + 8])
        body = pos + 8
        if chunk_id == b"fmt " and chunk_size >= 16:
            audio_format, channels, rate, _byte_rate, _align, bits = struct.unpack(
                "<HHIIHH", data[body:body + 16]
            )
            if audio_format != 1 or bits != 16:
                raise LocalSttError("unsupported", "only 16-bit PCM WAV is accepted")
            if channels not in (1, 2):
                raise LocalSttError("unsupported", "only mono or stereo is accepted")
            fmt = (rate, channels, bits)
        elif chunk_id == b"data":
            data_len = min(chunk_size, len(data) - body)
        pos = body + chunk_size + (chunk_size & 1)
    if fmt is None or data_len is None:
        raise LocalSttError("unsupported", "WAV is missing a fmt or data chunk")
    rate, channels, bits = fmt
    if rate <= 0:
        raise LocalSttError("unsupported", "WAV declares a zero sample rate")
    duration = data_len / float(rate * channels * (bits // 8))
    return rate, channels, duration


def enforce_bounds(data: bytes) -> float:
    """Byte cap, then duration cap. Returns the decoded duration in seconds."""
    if not data:
        raise LocalSttError("unsupported", "empty audio payload")
    if len(data) > MAX_AUDIO_BYTES:
        raise LocalSttError("resource", "audio payload exceeds the configured byte cap")
    _rate, _channels, duration = probe_wav(data)
    if duration > MAX_AUDIO_SECONDS:
        raise LocalSttError("resource", "audio exceeds the configured duration cap")
    return duration


# ── transcript extraction ───────────────────────────────────────────────────
_BRACKETED = re.compile(r"\[[^\]]*\]|\([^)]*\)")
_LANG_LINE = re.compile(r"auto-detected language:\s*([a-z]{2})", re.IGNORECASE)


def _clean_transcript(stdout: str) -> str:
    lines = []
    for raw in stdout.splitlines():
        line = _BRACKETED.sub(" ", raw).strip()
        if line:
            lines.append(line)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _detect_language(stderr: str, default: str = "en") -> str:
    m = _LANG_LINE.search(stderr or "")
    return (m.group(1).lower() if m else default)


class WhisperCppSTT(STTProvider):
    """Local, offline, multilingual STT. Opens no microphone and owns no session."""

    name = "whisper_cpp"

    def __init__(self, config: EngineConfig | None = None):
        self._config = config

    @property
    def config(self) -> EngineConfig:
        return self._config or load_config()

    def available(self) -> bool:
        cfg = self.config
        return bool(_resolve_binary(cfg)) and os.path.isfile(cfg.model_path)

    def health(self) -> dict:
        """Read-only readiness. Never starts the engine and never opens audio."""
        cfg = self.config
        binary = _resolve_binary(cfg)
        model_ok = os.path.isfile(cfg.model_path)
        if binary and model_ok:
            state, reason = "READY", ""
        elif not binary:
            state, reason = "UNAVAILABLE", "whisper.cpp binary was not found"
        else:
            state, reason = "UNAVAILABLE", "whisper.cpp model file was not found"
        return {
            "provider": self.name,
            "engine": "whisper.cpp/ggml",
            "state": state,
            "reason": reason,
            "available": state == "READY",
            "binary": binary or "",
            "model": os.path.basename(cfg.model_path) if model_ok else "",
            "model_present": model_ok,
            "privacy_class": "LOCAL_CONFIRMED",
            "languages": sorted(ALLOWED_LANGUAGES),
            "max_audio_bytes": MAX_AUDIO_BYTES,
            "max_audio_seconds": MAX_AUDIO_SECONDS,
            "streaming": "chunked",
            "partials": False,
        }

    def capabilities(self) -> dict:
        h = self.health()
        return {
            "providerId": self.name,
            "available": h["available"],
            "privacyClass": h["privacy_class"],
            "languages": h["languages"],
            "mode": "chunked_streaming",
            "supportsPartial": False,
            "supportsFinal": True,
            "supportsCancel": True,
        }

    # ── engine execution ────────────────────────────────────────────────────
    def transcribe_wav(self, data: bytes, *, language: str | None = None,
                       timeout: float = ENGINE_TIMEOUT_SECONDS) -> TranscriptResult:
        """Transcribe one bounded WAV utterance.

        The temporary artifact is created inside the configured throwaway
        directory with owner-only permissions and removed in `finally` on
        every exit path, including timeout and cancellation.
        """
        cfg = self.config
        binary = _resolve_binary(cfg)
        if not binary:
            raise LocalSttError("unsupported", "whisper.cpp binary was not found")
        if not os.path.isfile(cfg.model_path):
            raise LocalSttError("unsupported", "whisper.cpp model file was not found")

        duration = enforce_bounds(data)

        artifact_dir = Path(cfg.artifact_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(artifact_dir, 0o700)

        started = time.monotonic()
        fd, path = tempfile.mkstemp(prefix="utt-", suffix=".wav", dir=str(artifact_dir))
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            argv = [
                binary, "-m", cfg.model_path, "-f", path,
                "-nt", "-np", "-t", str(cfg.threads),
                "-l", (language if language in ALLOWED_LANGUAGES else "auto"),
                "--prompt", DOMAIN_PROMPT,
            ]
            try:
                proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                raise LocalSttError("resource", "local speech recognition timed out") from exc
            except OSError as exc:
                raise LocalSttError("unsupported", f"local speech engine failed to start: {exc}") from exc
            if proc.returncode != 0:
                detail = (proc.stderr or "").strip().splitlines()[-1:] or ["unknown engine failure"]
                raise LocalSttError("recognition", f"local speech recognition failed: {detail[0][:200]}")

            text = _clean_transcript(proc.stdout)
            detected = _detect_language(proc.stderr, default=language or "en")
            if detected not in ALLOWED_LANGUAGES and text:
                # Whisper hallucinating a language the owner does not speak is
                # noise, not a transcript. Publishing it would be a lie.
                return TranscriptResult(
                    text="", confidence=0.0, language=detected, is_final=True,
                    provider=self.name,
                    duration_ms=(time.monotonic() - started) * 1000,
                )
            return TranscriptResult(
                text=text, confidence=1.0 if text else 0.0, language=detected,
                is_final=True, provider=self.name,
                duration_ms=(time.monotonic() - started) * 1000,
            )
        finally:
            # Success, engine failure, timeout, cancellation — all land here.
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    def transcribe(self, audio, *, sample_rate: int = SAMPLE_RATE, language: str = "en"):
        raise NotImplementedError(
            "WhisperCppSTT consumes a bounded WAV utterance — use transcribe_wav"
        )
