"""Bounded local speech providers.

VoxCPM is always out-of-process. This module never imports the VoxCPM package or
loads model weights into the SaathiOS API process.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import math
import os
from pathlib import Path
import platform
import threading
import time
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
import soundfile as sf

from saathi.tool_runtime.subprocess_exec import run_bounded

from .models import MAX_AUDIO_BYTES, ProviderSynthesis, SpeechRequest


DOCUMENTED_VOXCPM2_LANGUAGES = (
    "ar",
    "my",
    "zh",
    "da",
    "nl",
    "en",
    "fi",
    "fr",
    "de",
    "el",
    "he",
    "hi",
    "id",
    "it",
    "ja",
    "km",
    "ko",
    "lo",
    "ms",
    "no",
    "pl",
    "pt",
    "ru",
    "es",
    "sw",
    "sv",
    "tl",
    "th",
    "tr",
    "vi",
)


class ProviderError(RuntimeError):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


class ProviderCancelled(ProviderError):
    def __init__(self):
        super().__init__("cancelled", "speech synthesis was cancelled")


def _audio_metadata(path: Path, fallback_rate: int) -> tuple[int, float]:
    try:
        info = sf.info(path)
        return int(info.samplerate), float(info.duration)
    except Exception:
        return fallback_rate, 0.0


class SpeechProvider(ABC):
    provider_id = "base"
    heavy = False

    @abstractmethod
    def capabilities(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def synthesize(
        self,
        request: SpeechRequest,
        output_path: Path,
        *,
        cancel_check: Callable[[], bool],
    ) -> ProviderSynthesis:
        raise NotImplementedError

    @abstractmethod
    def cancel(self, operation_id: str) -> bool:
        raise NotImplementedError

    def shutdown(self) -> None:
        return None


class UnavailableSpeechProvider(SpeechProvider):
    provider_id = "unavailable"

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "synthesis": False,
            "streaming": False,
            "cancellation": True,
            "languages": [],
            "certified_languages": [],
            "cloning": False,
            "voice_design": False,
            "local_only": True,
        }

    def health(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "state": "unavailable",
            "configured": True,
            "installed": True,
            "model_available": False,
            "runtime_verified": True,
            "detail": "No speech backend is currently available.",
        }

    def synthesize(
        self,
        request: SpeechRequest,
        output_path: Path,
        *,
        cancel_check: Callable[[], bool],
    ) -> ProviderSynthesis:
        raise ProviderError("provider_unavailable", "speech provider is unavailable")

    def cancel(self, operation_id: str) -> bool:
        return True


class MacOSSystemSpeechProvider(SpeechProvider):
    provider_id = "macos_system"
    _AFCONVERT = Path("/usr/bin/afconvert")

    def __init__(
        self,
        *,
        executable: Path | str = "/usr/bin/say",
        runner: Callable[..., Any] = run_bounded,
        system_name: str | None = None,
        converter: Path | str | None = None,
    ):
        self.executable = Path(executable)
        self.converter = Path(converter) if converter else self._AFCONVERT
        self.runner = runner
        self.system_name = system_name or platform.system()
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._voice_cache: tuple[dict[str, Any], ...] | None = None
        self._voice_discovery_failed = False

    def _valid_executable(self) -> bool:
        return (
            self.executable.is_absolute()
            and self.executable.name == "say"
            and self.executable.is_file()
            and os.access(self.executable, os.X_OK)
        )

    def _valid_converter(self) -> bool:
        return (
            self.converter.is_absolute()
            and self.converter.name == "afconvert"
            and self.converter.is_file()
            and os.access(self.converter, os.X_OK)
        )

    def _voices(self) -> tuple[dict[str, Any], ...]:
        # Single-flight discovery under lock. Never permanently cache a failed
        # empty probe — concurrent shell mounts can race `say -v ?` under load.
        with self._lock:
            if self._voice_cache is not None:
                return self._voice_cache
            if self.system_name != "Darwin" or not self._valid_executable():
                self._voice_cache = ()
                return self._voice_cache
            result = self.runner(
                [str(self.executable), "-v", "?"],
                timeout_sec=5.0,
                max_stdout=64_000,
                max_stderr=1_000,
            )
            voices: list[dict[str, Any]] = []
            if result.ok:
                for line in result.stdout.splitlines():
                    head = line.split("#", 1)[0].rstrip()
                    if not head:
                        continue
                    parts = head.rsplit(None, 1)
                    if len(parts) != 2 or "_" not in parts[1]:
                        continue
                    name, locale = parts
                    voices.append(
                        {
                            "voice_id": name.strip(),
                            "language": locale.replace("_", "-"),
                            "installed": True,
                        }
                    )
            discovered = tuple(voices[:500])
            if discovered:
                self._voice_cache = discovered
                self._voice_discovery_failed = False
                return self._voice_cache
            # Transient empty/failed discovery: do not poison the cache.
            self._voice_discovery_failed = True
            return ()

    def capabilities(self) -> dict[str, Any]:
        voices = list(self._voices())
        languages = sorted({v["language"] for v in voices})
        return {
            "provider_id": self.provider_id,
            "synthesis": bool(voices),
            "streaming": False,
            "cancellation": True,
            "languages": languages,
            "certified_languages": ["en"] if any(x.startswith("en-") for x in languages) else [],
            "voices": voices,
            # WAV is preferred for authenticated browser playback; AIFF remains supported.
            "output_formats": ["wav", "aiff"],
            "cloning": False,
            "voice_design": False,
            "local_only": True,
            "process_isolated": True,
        }

    def health(self) -> dict[str, Any]:
        voices = self._voices()
        ready = (
            self.system_name == "Darwin"
            and self._valid_executable()
            and self._valid_converter()
            and bool(voices)
        )
        if (
            not ready
            and self.system_name == "Darwin"
            and self._valid_executable()
            and self._valid_converter()
            and self._voice_discovery_failed
        ):
            detail = "Native macOS speech voice discovery is temporarily unavailable."
            state = "unavailable"
        elif ready:
            detail = "Native local speech is ready."
            state = "ready"
        else:
            detail = "Native macOS speech is not available."
            state = "unavailable"
        return {
            "provider_id": self.provider_id,
            "state": state,
            "configured": True,
            "installed": self._valid_executable(),
            "model_available": False,
            "runtime_verified": ready,
            "voice_count": len(voices),
            "detail": detail,
        }

    def synthesize(
        self,
        request: SpeechRequest,
        output_path: Path,
        *,
        cancel_check: Callable[[], bool],
    ) -> ProviderSynthesis:
        if self.health()["state"] != "ready":
            raise ProviderError("provider_unavailable", "macOS system speech is unavailable")
        if request.output_format not in {"aiff", "wav"}:
            raise ProviderError(
                "format_unsupported", "macOS provider outputs AIFF or WAV"
            )
        available = {v["voice_id"]: v for v in self._voices()}
        if request.voice_id and request.voice_id not in available:
            raise ProviderError("voice_unavailable", "requested system voice is unavailable")
        operation_id = output_path.stem
        event = threading.Event()
        with self._lock:
            self._cancel[operation_id] = event
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # `say` always writes AIFF/AIFF-C; convert to browser-playable WAV when requested.
        aiff_path = (
            output_path
            if request.output_format == "aiff"
            else output_path.with_name(f".{operation_id}.aiff.tmp")
        )
        argv = [str(self.executable), "-o", str(aiff_path)]
        if request.voice_id:
            argv.extend(["-v", request.voice_id])
        argv.extend(["-r", str(int(175 * request.speaking_rate)), request.text])
        started = time.monotonic()
        try:
            result = self.runner(
                argv,
                timeout_sec=30.0,
                cancel_check=lambda: event.is_set() or cancel_check(),
                max_stdout=1_000,
                max_stderr=2_000,
            )
            if result.cancellation_confirmed or event.is_set() or cancel_check():
                raise ProviderCancelled()
            if result.timeout_detected:
                raise ProviderError("timeout", "system speech synthesis timed out")
            if not result.ok:
                raise ProviderError("provider_failed", "system speech synthesis failed")
            if not aiff_path.is_file():
                raise ProviderError("artifact_missing", "speech artifact was not produced")
            final_path = aiff_path
            final_format = "aiff"
            if request.output_format == "wav":
                convert = self.runner(
                    [
                        str(self.converter),
                        "-f",
                        "WAVE",
                        "-d",
                        "LEI16@22050",
                        str(aiff_path),
                        str(output_path),
                    ],
                    timeout_sec=10.0,
                    cancel_check=lambda: event.is_set() or cancel_check(),
                    max_stdout=1_000,
                    max_stderr=2_000,
                )
                if convert.cancellation_confirmed or event.is_set() or cancel_check():
                    raise ProviderCancelled()
                if convert.timeout_detected or not convert.ok or not output_path.is_file():
                    raise ProviderError(
                        "provider_failed", "system speech WAV conversion failed"
                    )
                final_path = output_path
                final_format = "wav"
            size = final_path.stat().st_size
            if size <= 0 or size > MAX_AUDIO_BYTES:
                raise ProviderError("output_limit", "speech artifact size is invalid")
            total_ms = (time.monotonic() - started) * 1000
            sample_rate, duration = _audio_metadata(final_path, 22_050)
            return ProviderSynthesis(
                provider=self.provider_id,
                output_format=final_format,
                sample_rate=sample_rate,
                artifact_bytes=size,
                duration_seconds=duration,
                first_audio_ms=total_ms,
                total_ms=total_ms,
            )
        except ProviderError:
            if output_path.is_file():
                output_path.unlink()
            if aiff_path != output_path and aiff_path.is_file():
                aiff_path.unlink()
            raise
        finally:
            if aiff_path != output_path and aiff_path.is_file():
                aiff_path.unlink()
            with self._lock:
                self._cancel.pop(operation_id, None)

    def cancel(self, operation_id: str) -> bool:
        with self._lock:
            event = self._cancel.get(operation_id)
            if not event:
                return False
            event.set()
            return True

    def shutdown(self) -> None:
        with self._lock:
            for event in self._cancel.values():
                event.set()


@dataclass(frozen=True)
class VoxCPMConfig:
    enabled: bool = False
    mode: str = ""
    endpoint: str = ""
    executable: str = ""
    base_model_path: str = ""
    acoustic_model_path: str = ""
    startup_timeout_sec: float = 30.0
    synthesis_timeout_sec: float = 180.0

    @classmethod
    def from_env(cls) -> "VoxCPMConfig":
        def bounded_float(name: str, default: float, low: float, high: float) -> float:
            try:
                value = float(os.environ.get(name, str(default)))
            except (TypeError, ValueError):
                value = default
            if not math.isfinite(value):
                value = default
            return min(high, max(low, value))

        return cls(
            enabled=os.environ.get("SAATHI_VOXCPM_ENABLED", "").lower()
            in {"1", "true", "yes"},
            mode=os.environ.get("SAATHI_VOXCPM_MODE", "").strip().lower(),
            endpoint=os.environ.get("SAATHI_VOXCPM_ENDPOINT", "").strip(),
            executable=os.environ.get("SAATHI_VOXCPM_EXECUTABLE", "").strip(),
            base_model_path=os.environ.get("SAATHI_VOXCPM_BASE_MODEL", "").strip(),
            acoustic_model_path=os.environ.get(
                "SAATHI_VOXCPM_ACOUSTIC_MODEL", ""
            ).strip(),
            startup_timeout_sec=bounded_float(
                "SAATHI_VOXCPM_STARTUP_TIMEOUT", 30.0, 1.0, 60.0
            ),
            synthesis_timeout_sec=bounded_float(
                "SAATHI_VOXCPM_SYNTH_TIMEOUT", 180.0, 5.0, 180.0
            ),
        )


class VoxCPMSpeechProvider(SpeechProvider):
    provider_id = "voxcpm"
    heavy = True

    def __init__(
        self,
        config: VoxCPMConfig | None = None,
        *,
        runner: Callable[..., Any] = run_bounded,
        client: httpx.Client | None = None,
    ):
        self.config = config or VoxCPMConfig.from_env()
        self.runner = runner
        self.client = client
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _loopback(endpoint: str) -> bool:
        parsed = urlparse(endpoint)
        return (
            parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            and parsed.username is None
            and parsed.password is None
        )

    @staticmethod
    def _model_file(path: str) -> bool:
        if not path:
            return False
        model = Path(path)
        return model.is_absolute() and model.is_file() and model.suffix == ".gguf"

    def _gguf_ready(self) -> bool:
        executable = Path(self.config.executable) if self.config.executable else Path()
        return (
            bool(self.config.executable)
            and executable.is_absolute()
            and executable.is_file()
            and os.access(executable, os.X_OK)
            and executable.name == "voxcpm2-cli"
            and self._model_file(self.config.base_model_path)
            and self._model_file(self.config.acoustic_model_path)
        )

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "synthesis": True,
            "streaming": False,
            "streaming_state": "evaluated_artifact_only",
            "cancellation": True,
            "cancellation_mode": (
                "process_group"
                if self.config.mode == "gguf_metal"
                else "request_abandon"
            ),
            "languages": list(DOCUMENTED_VOXCPM2_LANGUAGES),
            "certified_languages": [],
            "language_support_state": "upstream_documented_not_locally_verified",
            "output_formats": ["wav"],
            "cloning": False,
            "cloning_state": "CAPABILITY_DISABLED",
            "voice_design": True,
            "voice_design_state": "adapter_mapped_not_runtime_verified",
            "local_only": True,
            "process_isolated": True,
            "backend_mode": self.config.mode or "not_configured",
        }

    def health(self) -> dict[str, Any]:
        base = {
            "provider_id": self.provider_id,
            "configured": False,
            "installed": False,
            "model_available": False,
            "runtime_verified": False,
            "quality_reviewed": False,
            "certified": False,
            "backend_mode": self.config.mode or "not_configured",
        }
        if not self.config.enabled:
            return {
                **base,
                "state": "disabled",
                "detail": "VoxCPM is optional and disabled.",
            }
        if self.config.mode == "gguf_metal":
            ready = self._gguf_ready()
            return {
                **base,
                "state": "ready_unverified" if ready else "configured_not_installed",
                "configured": bool(
                    self.config.executable
                    and self.config.base_model_path
                    and self.config.acoustic_model_path
                ),
                "installed": ready,
                "model_available": ready,
                "detail": (
                    "Configured GGUF runtime is present but not SaathiOS-certified."
                    if ready
                    else "GGUF executable or explicit model files are unavailable."
                ),
            }
        if self.config.mode == "localhost_service":
            if not self._loopback(self.config.endpoint):
                return {
                    **base,
                    "state": "misconfigured",
                    "detail": "VoxCPM endpoint must be an explicit loopback HTTP URL.",
                }
            try:
                client = self.client or httpx.Client(
                    timeout=self.config.startup_timeout_sec, trust_env=False
                )
                response = client.get(f"{self.config.endpoint.rstrip('/')}/health")
                ready = response.status_code == 200
                if self.client is None:
                    client.close()
            except Exception:
                ready = False
            return {
                **base,
                "state": "ready_unverified" if ready else "configured_unavailable",
                "configured": True,
                "installed": ready,
                "model_available": ready,
                "detail": (
                    "Loopback VoxCPM service is reachable but not SaathiOS-certified."
                    if ready
                    else "Configured loopback VoxCPM service is unavailable."
                ),
            }
        return {
            **base,
            "state": "misconfigured",
            "detail": "VoxCPM mode must be gguf_metal or localhost_service.",
        }

    def synthesize(
        self,
        request: SpeechRequest,
        output_path: Path,
        *,
        cancel_check: Callable[[], bool],
    ) -> ProviderSynthesis:
        health = self.health()
        if health["state"] != "ready_unverified":
            raise ProviderError("provider_unavailable", "VoxCPM is not ready")
        if request.output_format != "wav":
            raise ProviderError("format_unsupported", "VoxCPM adapter outputs WAV")
        operation_id = output_path.stem
        event = threading.Event()
        with self._lock:
            self._cancel[operation_id] = event
        provider_text = f"({request.style}){request.text}" if request.style else request.text
        started = time.monotonic()
        try:
            if self.config.mode == "gguf_metal":
                argv = [
                    self.config.executable,
                    "-t",
                    provider_text,
                    "-o",
                    str(output_path),
                ]
                argv.extend(
                    [self.config.base_model_path, self.config.acoustic_model_path]
                )
                result = self.runner(
                    argv,
                    timeout_sec=self.config.synthesis_timeout_sec,
                    cancel_check=lambda: event.is_set() or cancel_check(),
                    max_stdout=2_000,
                    max_stderr=2_000,
                )
                if result.cancellation_confirmed or event.is_set() or cancel_check():
                    raise ProviderCancelled()
                if result.timeout_detected:
                    raise ProviderError("timeout", "VoxCPM synthesis timed out")
                if not result.ok:
                    raise ProviderError("provider_failed", "VoxCPM synthesis failed")
            else:
                if not self._loopback(self.config.endpoint):
                    raise ProviderError(
                        "unsafe_configuration", "VoxCPM endpoint is not loopback"
                    )
                owns_client = self.client is None
                client = self.client or httpx.Client(
                    timeout=self.config.synthesis_timeout_sec, trust_env=False
                )
                payload = {
                    "model": "explicit-local-model",
                    "input": provider_text,
                    "voice": request.voice_id or "default",
                    "response_format": "wav",
                    "stream": False,
                    "operation_id": operation_id,
                }
                content = bytearray()
                try:
                    with client.stream(
                        "POST",
                        f"{self.config.endpoint.rstrip('/')}/v1/audio/speech",
                        json=payload,
                    ) as response:
                        if response.status_code != 200:
                            raise ProviderError(
                                "provider_failed",
                                "VoxCPM service rejected synthesis",
                            )
                        for chunk in response.iter_bytes():
                            if event.is_set() or cancel_check():
                                raise ProviderCancelled()
                            content.extend(chunk)
                            if len(content) > MAX_AUDIO_BYTES:
                                raise ProviderError(
                                    "output_limit",
                                    "VoxCPM output exceeds limit",
                                )
                finally:
                    if owns_client:
                        client.close()
                if event.is_set() or cancel_check():
                    raise ProviderCancelled()
                output_path.write_bytes(content)
            if not output_path.is_file():
                raise ProviderError("artifact_missing", "VoxCPM artifact was not produced")
            size = output_path.stat().st_size
            if size <= 0 or size > MAX_AUDIO_BYTES:
                raise ProviderError("output_limit", "VoxCPM artifact size is invalid")
            total_ms = (time.monotonic() - started) * 1000
            sample_rate, duration = _audio_metadata(output_path, 48_000)
            return ProviderSynthesis(
                provider=self.provider_id,
                output_format="wav",
                sample_rate=sample_rate,
                artifact_bytes=size,
                duration_seconds=duration,
                first_audio_ms=total_ms,
                total_ms=total_ms,
                streaming_state=(
                    "requested_but_artifact_only"
                    if request.streaming
                    else "artifact_ready"
                ),
            )
        except httpx.TimeoutException as exc:
            raise ProviderError("timeout", "VoxCPM service timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("provider_unavailable", "VoxCPM service unavailable") from exc
        except ProviderError:
            if output_path.is_file():
                output_path.unlink()
            raise
        finally:
            with self._lock:
                self._cancel.pop(operation_id, None)

    def cancel(self, operation_id: str) -> bool:
        with self._lock:
            event = self._cancel.get(operation_id)
            if not event:
                return False
            event.set()
            return True

    def shutdown(self) -> None:
        with self._lock:
            for event in self._cancel.values():
                event.set()
