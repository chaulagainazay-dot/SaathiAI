"""R2.1-S4 — the legacy audio endpoint is bounded and leaves nothing behind.

``/api/v1/voice/command`` read an unbounded body, handed any container to
ffmpeg, and — whenever that conversion failed — left both the uploaded file and
its half-written conversion in the system temporary directory. A caller could
fill the disk with other people's audio without ever completing a turn.

The limits here are the existing voice runtime contract
(``MAX_AUDIO_UPLOAD_BYTES``, ``MAX_RECORDING_SECONDS``), not new numbers chosen
to keep the legacy path convenient.

Authentication and session scoping are covered in ``test_r2_1_endpoint_auth``.
"""
import asyncio
import io
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from saathi import server, voice


@pytest.fixture
def client():
    return TestClient(server.app)


@pytest.fixture
def authed():
    return {"x-baadar-session": server._session_token()}


def _upload(content=b"\x1a\x45\xdf\xa3fake-webm", name="speech.webm", mime="audio/webm"):
    return {"file": (name, io.BytesIO(content), mime)}


class Tripwire:
    def __init__(self, label):
        self.label = label
        self.calls = 0

    def __call__(self, *a, **kw):
        self.calls += 1
        raise AssertionError(f"{self.label} ran for a request that must be rejected")


@pytest.fixture
def tripwires(monkeypatch):
    """Fail loudly if a rejected request reaches decode, STT, LLM, or TTS."""
    wires = {
        "decode": Tripwire("audio decode"),
        "transcribe": Tripwire("transcription"),
        "verify": Tripwire("speaker verification"),
        "synthesize": Tripwire("TTS"),
    }
    monkeypatch.setattr(voice, "decode_16k", wires["decode"])
    monkeypatch.setattr(voice, "transcribe_array", wires["transcribe"])
    monkeypatch.setattr(voice, "verify_array", wires["verify"])
    monkeypatch.setattr(voice, "synthesize", wires["synthesize"])

    class NoBrain:
        def respond(self, *a, **kw):
            raise AssertionError("the agent ran for a request that must be rejected")

    monkeypatch.setattr(server, "agent", NoBrain())
    return wires


@pytest.fixture
def working_pipeline(monkeypatch):
    monkeypatch.setattr(voice, "decode_16k",
                        lambda *a, **kw: np.zeros(16000, dtype=np.float32))
    monkeypatch.setattr(voice, "transcribe_array",
                        lambda *a, **kw: {"text": "hello", "language": "en"})
    monkeypatch.setattr(voice, "verify_array",
                        lambda *a, **kw: {"verified": True, "similarity": 0.9})
    monkeypatch.setattr(voice, "synthesize", Tripwire("TTS"))

    class Brain:
        def respond(self, *a, **kw):
            return "ok"

    monkeypatch.setattr(server, "agent", Brain())


# ── Media type ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name,mime", [
    ("payload.exe", "application/x-msdownload"),
    ("payload.pdf", "application/pdf"),
    ("payload.txt", "text/plain"),
    ("payload.mkv", "video/x-matroska"),
    ("payload", "application/octet-stream"),
])
def test_unsupported_media_type_is_rejected(client, authed, tripwires, name, mime):
    r = client.post("/api/v1/voice/command", files=_upload(b"x" * 64, name, mime),
                    headers=authed, data={"session_id": "web"})
    assert r.status_code == 415
    assert r.json()["error"] == "unsupported_media_type"
    assert all(w.calls == 0 for w in tripwires.values())


def test_supported_media_types_are_accepted(client, authed, working_pipeline):
    for name, mime in [("a.webm", "audio/webm"), ("a.wav", "audio/wav"),
                       ("a.m4a", "audio/mp4"), ("a.ogg", "audio/ogg")]:
        r = client.post("/api/v1/voice/command", files=_upload(b"x" * 64, name, mime),
                        headers=authed, data={"session_id": "web", "speak_reply": "false"})
        assert r.status_code == 200, f"{mime} was rejected"


# ── Size and duration ────────────────────────────────────────────────────────


def test_oversized_upload_is_rejected(client, authed, tripwires):
    big = b"\x00" * (server.VOICE_MAX_UPLOAD_BYTES + 1024)
    r = client.post("/api/v1/voice/command", files=_upload(big), headers=authed,
                    data={"session_id": "web"})
    assert r.status_code == 413
    assert r.json()["error"] == "payload_too_large"
    assert all(w.calls == 0 for w in tripwires.values())


def test_empty_upload_is_rejected(client, authed, tripwires):
    r = client.post("/api/v1/voice/command", files=_upload(b""), headers=authed,
                    data={"session_id": "web"})
    assert r.status_code == 400
    assert r.json()["error"] == "empty_upload"


def test_excessive_duration_is_rejected(client, authed, monkeypatch):
    """Longer than the recording contract allows — rejected before the LLM."""
    too_long = np.zeros(int((server.VOICE_MAX_SECONDS + 5) * 16000), dtype=np.float32)
    monkeypatch.setattr(voice, "_decode", lambda *a, **kw: (too_long, 16000))
    monkeypatch.setattr(voice, "transcribe_array", Tripwire("transcription"))

    class NoBrain:
        def respond(self, *a, **kw):
            raise AssertionError("the agent ran for an over-long recording")

    monkeypatch.setattr(server, "agent", NoBrain())
    r = client.post("/api/v1/voice/command", files=_upload(), headers=authed,
                    data={"session_id": "web"})
    assert r.status_code == 413
    assert r.json()["error"] == "audio_too_long"


def test_duration_bound_comes_from_the_voice_contract():
    from saathi.platform.voice.runtime import models as contract
    assert server.VOICE_MAX_SECONDS == contract.MAX_RECORDING_SECONDS
    assert server.VOICE_MAX_UPLOAD_BYTES == contract.MAX_AUDIO_UPLOAD_BYTES


# ── Bounded errors, no leakage ───────────────────────────────────────────────


def test_undecodable_audio_is_rejected_with_a_bounded_code(client, authed, monkeypatch):
    monkeypatch.setattr(
        voice, "_decode",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("ffmpeg: /tmp/secret")))
    r = client.post("/api/v1/voice/command", files=_upload(), headers=authed,
                    data={"session_id": "web"})
    assert r.status_code == 400
    assert r.json() == {"error": "audio_undecodable"}
    assert "ffmpeg" not in r.text and "/tmp" not in r.text


def test_error_body_carries_no_audio_or_transcript(client, authed, tripwires):
    r = client.post("/api/v1/voice/command",
                    files=_upload(b"SECRETAUDIOBYTES", "a.exe", "application/x-msdownload"),
                    headers=authed, data={"session_id": "web"})
    assert "SECRETAUDIOBYTES" not in r.text
    assert set(r.json()) == {"error"}


def test_tts_failure_reports_a_bounded_code(client, authed, monkeypatch, working_pipeline):
    def boom(*a, **kw):
        raise RuntimeError("gTTS key sk-live-secret leaked")

    monkeypatch.setattr(voice, "synthesize", boom)
    r = client.post("/api/v1/voice/command", files=_upload(), headers=authed,
                    data={"session_id": "web", "speak_reply": "true"})
    assert r.json()["tts_error"] == "tts_unavailable"
    assert "sk-live-secret" not in r.text


# ── Temporary files never survive the turn ───────────────────────────────────


@pytest.fixture
def temp_sandbox(monkeypatch, tmp_path):
    """Point tempfile at an empty directory so leaks are visible."""
    sandbox = tmp_path / "audio-tmp"
    sandbox.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(sandbox))
    return sandbox


def _raising(exc):
    def _fn(*a, **kw):
        raise exc
    return _fn


def _force_ffmpeg_path(monkeypatch):
    """Make soundfile fail so _decode takes the ffmpeg conversion branch."""
    import soundfile as sf
    monkeypatch.setattr(sf, "read", _raising(RuntimeError("not a wav")))


def _fake_ffmpeg(cmd, **kw):
    Path(cmd[-1]).write_bytes(b"converted")   # ffmpeg's output path
    return subprocess.CompletedProcess(cmd, 0)


def test_ffmpeg_failure_leaves_no_temporary_files(temp_sandbox, monkeypatch):
    _force_ffmpeg_path(monkeypatch)
    monkeypatch.setattr(voice, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(subprocess, "run",
                        _raising(subprocess.CalledProcessError(1, "ffmpeg")))
    with pytest.raises(subprocess.CalledProcessError):
        voice._decode(b"not-audio", "speech.webm")
    assert list(temp_sandbox.iterdir()) == []


def test_ffmpeg_timeout_leaves_no_temporary_files(temp_sandbox, monkeypatch):
    _force_ffmpeg_path(monkeypatch)
    monkeypatch.setattr(voice, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(subprocess, "run",
                        _raising(subprocess.TimeoutExpired("ffmpeg", 60)))
    with pytest.raises(subprocess.TimeoutExpired):
        voice._decode(b"not-audio", "speech.webm")
    assert list(temp_sandbox.iterdir()) == []


def test_decoder_failure_leaves_no_temporary_files(temp_sandbox, monkeypatch):
    """ffmpeg succeeds, reading its output fails — both files still go."""
    import soundfile as sf
    monkeypatch.setattr(sf, "read", _raising(RuntimeError("corrupt")))
    monkeypatch.setattr(voice, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(subprocess, "run", _fake_ffmpeg)
    with pytest.raises(RuntimeError):
        voice._decode(b"not-audio", "speech.webm")
    assert list(temp_sandbox.iterdir()) == []


def test_cancellation_leaves_no_temporary_files(temp_sandbox, monkeypatch):
    """A cancelled request is not an excuse to leave audio on disk."""
    _force_ffmpeg_path(monkeypatch)
    monkeypatch.setattr(voice, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(subprocess, "run", _raising(asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        voice._decode(b"not-audio", "speech.webm")
    assert list(temp_sandbox.iterdir()) == []


def test_successful_decode_leaves_no_temporary_files(temp_sandbox, monkeypatch):
    import soundfile as sf
    calls = {"n": 0}

    def read(target, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("not a wav")   # force the ffmpeg branch
        return np.zeros(16000, dtype=np.float32), 16000

    monkeypatch.setattr(sf, "read", read)
    monkeypatch.setattr(voice, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(subprocess, "run", _fake_ffmpeg)
    wav, sr = voice._decode(b"not-audio", "speech.webm")
    assert sr == 16000
    assert list(temp_sandbox.iterdir()) == [], "temporary files survived a successful decode"


def test_decode_16k_rejects_empty_audio(monkeypatch):
    monkeypatch.setattr(voice, "_decode",
                        lambda *a, **kw: (np.zeros(0, dtype=np.float32), 16000))
    with pytest.raises(voice.AudioUndecodable):
        voice.decode_16k(b"", "a.webm", max_seconds=60)
