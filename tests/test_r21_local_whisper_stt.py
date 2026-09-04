"""R2.1 — local whisper.cpp STT provider invariants.

These are contract tests, not accuracy tests. They prove the bounded
behaviour the voice architecture depends on: input bounds are enforced before
the engine runs, temporary audio never survives any exit path, failures carry
a bounded category, and the provider never invents a transcript.
"""
from __future__ import annotations

import glob
import os
import struct
import subprocess

import pytest

from saathi.voice_os import local_whisper as lw
from saathi.voice_os.local_whisper import (
    LocalSttError,
    WhisperCppSTT,
    enforce_bounds,
    probe_wav,
)


def make_wav(seconds: float = 0.5, rate: int = 16000, channels: int = 1,
             bits: int = 16) -> bytes:
    frames = int(seconds * rate)
    payload = b"\x00\x00" * frames * channels
    block = channels * bits // 8
    fmt = struct.pack("<4sIHHIIHH4sI", b"fmt ", 16, 1, channels, rate,
                      rate * block, block, bits, b"data", len(payload))
    body = b"WAVE" + fmt + payload
    return b"RIFF" + struct.pack("<I", len(body)) + body


@pytest.fixture()
def artifact_dir(tmp_path, monkeypatch):
    d = tmp_path / "artifacts"
    monkeypatch.setenv("SAATHI_VOICE_ARTIFACT_DIR", str(d))
    return d


# ── WAV contract ────────────────────────────────────────────────────────────

def test_probe_wav_reads_rate_channels_and_duration():
    rate, channels, duration = probe_wav(make_wav(seconds=1.5))
    assert (rate, channels) == (16000, 1)
    assert duration == pytest.approx(1.5, abs=0.01)


@pytest.mark.parametrize("payload", [b"", b"not a wav at all", b"RIFF" + b"\x00" * 60])
def test_non_pcm_wav_payloads_are_rejected_unread(payload):
    with pytest.raises(LocalSttError) as exc:
        enforce_bounds(payload)
    assert exc.value.category in {"unsupported", "resource"}


def test_non_pcm_encoding_is_rejected():
    wav = bytearray(make_wav())
    wav[20:22] = struct.pack("<H", 3)  # IEEE float, not PCM
    with pytest.raises(LocalSttError) as exc:
        probe_wav(bytes(wav))
    assert exc.value.category == "unsupported"


# ── bounds ──────────────────────────────────────────────────────────────────

def test_byte_cap_is_enforced_before_the_wav_is_parsed():
    with pytest.raises(LocalSttError) as exc:
        enforce_bounds(b"RIFF" + b"x" * (lw.MAX_AUDIO_BYTES + 1))
    assert exc.value.category == "resource"


def test_duration_cap_is_enforced():
    with pytest.raises(LocalSttError) as exc:
        enforce_bounds(make_wav(seconds=lw.MAX_AUDIO_SECONDS + 1))
    assert exc.value.category == "resource"


def test_audio_inside_both_bounds_is_accepted():
    assert enforce_bounds(make_wav(seconds=2.0)) == pytest.approx(2.0, abs=0.01)


# ── health is read-only ─────────────────────────────────────────────────────

def test_health_reports_unavailable_without_starting_an_engine(monkeypatch, artifact_dir):
    monkeypatch.setenv("SAATHI_WHISPER_CPP_BIN", "/nonexistent/whisper-cli")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("health ran the engine"))
    health = WhisperCppSTT().health()
    assert health["state"] == "UNAVAILABLE"
    assert health["available"] is False
    assert health["reason"]


def test_health_declares_local_privacy_and_bounds(monkeypatch, tmp_path, artifact_dir):
    model = tmp_path / "ggml-base.bin"
    model.write_bytes(b"stub")
    monkeypatch.setenv("SAATHI_WHISPER_CPP_BIN", "/bin/echo")
    monkeypatch.setenv("SAATHI_WHISPER_CPP_MODEL", str(model))
    health = WhisperCppSTT().health()
    assert health["state"] == "READY"
    assert health["privacy_class"] == "LOCAL_CONFIRMED"
    assert health["max_audio_bytes"] == lw.MAX_AUDIO_BYTES
    assert health["max_audio_seconds"] == lw.MAX_AUDIO_SECONDS


def test_capabilities_never_claim_partial_support(monkeypatch, tmp_path, artifact_dir):
    model = tmp_path / "ggml-base.bin"
    model.write_bytes(b"stub")
    monkeypatch.setenv("SAATHI_WHISPER_CPP_BIN", "/bin/echo")
    monkeypatch.setenv("SAATHI_WHISPER_CPP_MODEL", str(model))
    caps = WhisperCppSTT().capabilities()
    assert caps["supportsPartial"] is False
    assert caps["supportsFinal"] is True
    assert caps["privacyClass"] == "LOCAL_CONFIRMED"


# ── temporary audio never survives ──────────────────────────────────────────

def _stub_engine(monkeypatch, tmp_path, *, returncode=0, stdout="hello", stderr="",
                 raises=None):
    model = tmp_path / "ggml-base.bin"
    model.write_bytes(b"stub")
    monkeypatch.setenv("SAATHI_WHISPER_CPP_BIN", "/bin/echo")
    monkeypatch.setenv("SAATHI_WHISPER_CPP_MODEL", str(model))

    def fake_run(argv, **kwargs):
        # The audio file must still exist while the engine runs...
        path = argv[argv.index("-f") + 1]
        assert os.path.isfile(path)
        assert oct(os.stat(path).st_mode & 0o777) == "0o600"
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_temporary_audio_is_removed_after_success(monkeypatch, tmp_path, artifact_dir):
    _stub_engine(monkeypatch, tmp_path, stdout="show my missions")
    result = WhisperCppSTT().transcribe_wav(make_wav())
    assert result.text == "show my missions"
    assert glob.glob(str(artifact_dir / "*")) == []


def test_temporary_audio_is_removed_after_engine_failure(monkeypatch, tmp_path, artifact_dir):
    _stub_engine(monkeypatch, tmp_path, returncode=1, stderr="ggml: load failed")
    with pytest.raises(LocalSttError) as exc:
        WhisperCppSTT().transcribe_wav(make_wav())
    assert exc.value.category == "recognition"
    assert glob.glob(str(artifact_dir / "*")) == []


def test_temporary_audio_is_removed_after_timeout(monkeypatch, tmp_path, artifact_dir):
    _stub_engine(monkeypatch, tmp_path,
                 raises=subprocess.TimeoutExpired(cmd="whisper-cli", timeout=1))
    with pytest.raises(LocalSttError) as exc:
        WhisperCppSTT().transcribe_wav(make_wav())
    assert exc.value.category == "resource"
    assert glob.glob(str(artifact_dir / "*")) == []


def test_temporary_audio_is_removed_after_cancellation(monkeypatch, tmp_path, artifact_dir):
    _stub_engine(monkeypatch, tmp_path, raises=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        WhisperCppSTT().transcribe_wav(make_wav())
    assert glob.glob(str(artifact_dir / "*")) == []


def test_artifact_directory_is_owner_only(monkeypatch, tmp_path, artifact_dir):
    _stub_engine(monkeypatch, tmp_path)
    WhisperCppSTT().transcribe_wav(make_wav())
    assert oct(os.stat(artifact_dir).st_mode & 0o777) == "0o700"


# ── the provider never invents a transcript ─────────────────────────────────

def test_out_of_bounds_audio_never_reaches_the_engine(monkeypatch, tmp_path, artifact_dir):
    model = tmp_path / "ggml-base.bin"
    model.write_bytes(b"stub")
    monkeypatch.setenv("SAATHI_WHISPER_CPP_BIN", "/bin/echo")
    monkeypatch.setenv("SAATHI_WHISPER_CPP_MODEL", str(model))
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: pytest.fail("engine ran on out-of-bounds audio"))
    with pytest.raises(LocalSttError):
        WhisperCppSTT().transcribe_wav(make_wav(seconds=lw.MAX_AUDIO_SECONDS + 5))


def test_unsupported_detected_language_yields_no_transcript(monkeypatch, tmp_path, artifact_dir):
    _stub_engine(monkeypatch, tmp_path, stdout="你好世界",
                 stderr="auto-detected language: zh")
    result = WhisperCppSTT().transcribe_wav(make_wav())
    assert result.text == ""
    assert result.confidence == 0.0


def test_silence_yields_an_empty_transcript_not_a_guess(monkeypatch, tmp_path, artifact_dir):
    _stub_engine(monkeypatch, tmp_path, stdout="[BLANK_AUDIO]\n")
    result = WhisperCppSTT().transcribe_wav(make_wav())
    assert result.text == ""


def test_missing_binary_reports_unsupported_not_a_transcript(monkeypatch, artifact_dir):
    monkeypatch.setenv("SAATHI_WHISPER_CPP_BIN", "/nonexistent/whisper-cli")
    with pytest.raises(LocalSttError) as exc:
        WhisperCppSTT().transcribe_wav(make_wav())
    assert exc.value.category == "unsupported"


def test_array_transcription_is_refused_so_callers_use_the_bounded_path():
    import numpy as np
    with pytest.raises(NotImplementedError):
        WhisperCppSTT().transcribe(np.zeros(16000, dtype="float32"))
