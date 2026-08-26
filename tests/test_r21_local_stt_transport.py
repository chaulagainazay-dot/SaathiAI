"""R2.1 — /api/v1/voice/stt/* transport invariants.

The transport carries audio to the local engine and text back. It must not
carry authority, must reject anonymous callers before touching the engine,
and must enforce the bounded audio contract at the edge.
"""
from __future__ import annotations

import struct

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from saathi.voice_os import api as voice_api
from saathi.voice_os import local_whisper as lw
from saathi.voice_os.stt import TranscriptResult


def make_wav(seconds: float = 0.5, rate: int = 16000) -> bytes:
    frames = int(seconds * rate)
    payload = b"\x00\x00" * frames
    fmt = struct.pack("<4sIHHIIHH4sI", b"fmt ", 16, 1, 1, rate,
                      rate * 2, 2, 16, b"data", len(payload))
    body = b"WAVE" + fmt + payload
    return b"RIFF" + struct.pack("<I", len(body)) + body


class _StubContext:
    """The shape ``require_context`` returns: a resolved platform principal."""

    def __init__(self, user_id: str):
        self.user_id = user_id


def build_app(user_id: str | None, monkeypatch=None):
    """A client whose requests carry an authenticated principal, or none.

    D16: these endpoints used to be gated on ``request.state.user_id``, which
    nothing in the application ever assigned — so the gate refused every caller
    and the local engine was unreachable. Authentication now binds to the
    D15-derived platform session the local-STT client actually sends, resolved
    through ``require_context``. The principal is stubbed here so this suite
    stays about *transport* — bounds, media types, cleanup, authority — rather
    than re-testing platform session validation, which
    tests/test_d16_local_stt_auth.py covers against the real validator.
    """
    app = FastAPI()
    app.include_router(voice_api.router)
    ctx = _StubContext(user_id) if user_id else None
    target = monkeypatch or _module_monkeypatch()
    target.setattr(voice_api, "_stt_principal", lambda request: ctx)
    return TestClient(app)


def _module_monkeypatch():
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    _ACTIVE_PATCHES.append(mp)
    return mp


_ACTIVE_PATCHES: list = []


@pytest.fixture(autouse=True)
def _undo_principal_patches():
    yield
    while _ACTIVE_PATCHES:
        _ACTIVE_PATCHES.pop().undo()


@pytest.fixture()
def engine_calls(monkeypatch):
    calls = []

    def fake(data, *, language=None, timeout=lw.ENGINE_TIMEOUT_SECONDS):
        calls.append({"bytes": len(data), "language": language})
        return TranscriptResult(text="show my missions", confidence=1.0,
                                language="en", is_final=True,
                                provider="whisper_cpp", duration_ms=310.0)

    monkeypatch.setattr(voice_api._STT_PROVIDER, "transcribe_wav", fake)
    return calls


# ── authentication ──────────────────────────────────────────────────────────

def test_anonymous_transcribe_is_refused_before_the_engine_runs(engine_calls):
    client = build_app(None)
    r = client.post("/api/v1/voice/stt/transcribe",
                    files={"file": ("u.wav", make_wav(), "audio/wav")})
    assert r.status_code == 401
    assert engine_calls == []


def test_anonymous_health_is_refused(monkeypatch):
    monkeypatch.setattr(voice_api._STT_PROVIDER, "health",
                        lambda: pytest.fail("health served to an anonymous caller"))
    assert build_app(None).get("/api/v1/voice/stt/health").status_code == 401


def test_authenticated_health_is_read_only(monkeypatch):
    monkeypatch.setattr(voice_api._STT_PROVIDER, "health",
                        lambda: {"state": "READY", "available": True,
                                 "privacy_class": "LOCAL_CONFIRMED"})
    r = build_app("owner@localhost").get("/api/v1/voice/stt/health")
    assert r.status_code == 200
    assert r.json()["privacy_class"] == "LOCAL_CONFIRMED"


# ── bounded audio contract ──────────────────────────────────────────────────

def test_oversized_upload_is_rejected(engine_calls):
    client = build_app("owner@localhost")
    r = client.post("/api/v1/voice/stt/transcribe",
                    files={"file": ("u.wav", b"R" * (lw.MAX_AUDIO_BYTES + 10), "audio/wav")})
    assert r.status_code == 413
    assert engine_calls == []


def test_non_wav_media_type_is_rejected_unread(engine_calls):
    client = build_app("owner@localhost")
    r = client.post("/api/v1/voice/stt/transcribe",
                    files={"file": ("u.mp3", make_wav(), "audio/mpeg")})
    assert r.status_code == 415
    assert engine_calls == []


def test_engine_resource_failure_maps_to_a_bounded_category(monkeypatch):
    def boom(data, **kw):
        raise lw.LocalSttError("resource", "local speech recognition timed out")

    monkeypatch.setattr(voice_api._STT_PROVIDER, "transcribe_wav", boom)
    r = build_app("owner@localhost").post(
        "/api/v1/voice/stt/transcribe",
        files={"file": ("u.wav", make_wav(), "audio/wav")})
    assert r.status_code == 413
    assert r.json()["category"] == "resource"


def test_engine_unavailable_reports_service_unavailable_not_a_transcript(monkeypatch):
    def boom(data, **kw):
        raise lw.LocalSttError("unsupported", "whisper.cpp binary was not found")

    monkeypatch.setattr(voice_api._STT_PROVIDER, "transcribe_wav", boom)
    r = build_app("owner@localhost").post(
        "/api/v1/voice/stt/transcribe",
        files={"file": ("u.wav", make_wav(), "audio/wav")})
    assert r.status_code == 415
    assert "text" not in r.json()


# ── the response carries text, never authority ──────────────────────────────

def test_successful_transcript_declares_no_authority(engine_calls):
    r = build_app("owner@localhost").post(
        "/api/v1/voice/stt/transcribe",
        files={"file": ("u.wav", make_wav(), "audio/wav")})
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "show my missions"
    assert body["authority"] == "none"
    assert body["privacyClass"] == "LOCAL_CONFIRMED"
    assert body["isFinal"] is True


def test_response_never_carries_approval_or_role_fields(engine_calls):
    body = build_app("owner@localhost").post(
        "/api/v1/voice/stt/transcribe",
        files={"file": ("u.wav", make_wav(), "audio/wav")}).json()
    forbidden = {"approved", "approval", "role", "speaker", "verified",
                 "authorized", "confirmed", "token", "session"}
    assert forbidden.isdisjoint(body.keys())


def test_caller_cannot_force_an_unsupported_language(engine_calls):
    build_app("owner@localhost").post(
        "/api/v1/voice/stt/transcribe",
        files={"file": ("u.wav", make_wav(), "audio/wav")},
        data={"language": "zh"})
    assert engine_calls[0]["language"] is None


def test_supported_language_hint_is_passed_through(engine_calls):
    build_app("owner@localhost").post(
        "/api/v1/voice/stt/transcribe",
        files={"file": ("u.wav", make_wav(), "audio/wav")},
        data={"language": "ne"})
    assert engine_calls[0]["language"] == "ne"


# ── the transport is not on the anonymous bypass list ───────────────────────

def test_stt_paths_reach_their_validator_only_with_a_platform_credential():
    """D16: these paths are named in the middleware, but not exempted.

    They are listed so a request carrying a platform credential can reach the
    router that validates it — the local-STT client authenticates with
    ``X-Platform-Token``, not with a canonical session header, so a blanket
    rejection here made the engine unreachable. A caller presenting nothing
    still never reaches the handler, and no prefix is exempt.
    """
    import inspect
    import saathi.server as svr

    source = (__import__("pathlib").Path(__file__).resolve().parents[1]
              / "saathi" / "server.py").read_text()
    assert 'path.startswith("/api/v1/voice/stt' not in source, "no prefix exemption"

    gate = inspect.getsource(svr._auth)
    assert "_PLATFORM_CREDENTIAL_PATHS" in gate
    assert "_presents_platform_credential(request)" in gate
    # The paths live in the credential-gated set, never in the public one.
    assert "/api/v1/voice/stt/health" in svr._PLATFORM_CREDENTIAL_PATHS
    assert "/api/v1/voice/stt/transcribe" in svr._PLATFORM_CREDENTIAL_PATHS
    assert not (svr._PUBLIC_PLATFORM_PATHS & svr._PLATFORM_CREDENTIAL_PATHS)
