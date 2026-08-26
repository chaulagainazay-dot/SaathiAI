"""D16 — the local speech engine is reachable, and only by the right principal.

``/api/v1/voice/stt/health`` and ``/api/v1/voice/stt/transcribe`` were guarded by

    def _stt_authenticated(request) -> bool:
        return bool(getattr(request.state, "user_id", None))

and nothing in the application ever assigned ``request.state.user_id``. No
commit in the history of ``saathi/server.py`` sets it. So the gate returned
False for every caller and both endpoints answered 401 to everyone, including
the owner — the local whisper.cpp engine has been unreachable since it was
introduced. The shell's ``resolveLocalStt()`` probes health, gets 401, and
resolves *no local engine*; with the browser fallback correctly disabled the
voice pipeline then reports "unavailable" and can never produce a transcript.

The repair deliberately does **not** populate ``request.state.user_id`` in the
middleware. Two other routers read it as
``getattr(request.state, "user_id", None) or "ajay"``, so filling it globally
would silently re-attribute connector and control-centre actions from a
hardcoded string to the real owner id. Instead the STT router binds to the
credential its client already sends: the D15-derived ``X-Platform-Token``,
validated by the same ``require_context`` that guards every other platform
surface.
"""
from __future__ import annotations

import io
import math
import struct
import wave

import pytest
from fastapi.testclient import TestClient

LOOPBACK = ("127.0.0.1", 51234)
CANONICAL_PASSWORD = "T3st!LocalStt#Pw"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    import sys, pathlib as _pl
    sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))

    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SAATHI_STATE_ROOT", str(state))
    monkeypatch.setenv("SAATHI_LOAD_DOTENV", "false")
    monkeypatch.setenv("SAATHI_PLATFORM_DB", str(tmp_path / "platform.db"))
    monkeypatch.setenv("SAATHI_VOICE_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    # The real local engine, pointed at the pinned model. The audio is generated
    # in-process; no microphone is involved at any point.
    monkeypatch.setenv("SAATHI_WHISPER_CPP_BIN", "/opt/homebrew/bin/whisper-cli")
    monkeypatch.setenv(
        "SAATHI_WHISPER_CPP_MODEL",
        "/Users/macbookpro/.saathi/stt-models/whisper-cpp/ggml-base.bin")
    for var in ("BAADAR_PASSWORD", "SAATHI_BOOTSTRAP_ENABLED"):
        monkeypatch.delenv(var, raising=False)

    from saathi.security import store as store_mod
    from saathi.security.registry import close_registry
    from saathi.security.timeline import close_timeline
    from saathi.platform import service as platform_service

    store_mod.close_store()
    store_mod._default_store = None
    close_registry()
    close_timeline()
    sec = store_mod.SecurityStore(db_path=tmp_path / "security.db")
    store_mod._default_store = sec
    platform_service.reset_platform_for_tests(tmp_path / "platform.db")

    import saathi.server as svr
    monkeypatch.setattr(svr, "_PASSWORD_HASH", "", raising=False)
    monkeypatch.setattr(svr, "ACCESS_TOKEN", "", raising=False)

    yield sec

    platform_service.reset_platform_for_tests(tmp_path / "platform-teardown.db")
    sec.close()
    store_mod.close_store()
    store_mod._default_store = None
    close_registry()
    close_timeline()


@pytest.fixture
def client():
    from saathi.server import app
    return TestClient(app, client=LOOPBACK)


def platform_headers(client, store):
    from support.platform_auth import platform_token
    return {"X-Platform-Token": platform_token(client, store)}


def synthetic_wav(seconds: float = 0.4, rate: int = 16000, freq: float = 220.0) -> bytes:
    """A generated mono 16-bit PCM tone. No microphone, no recorded audio."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(int(rate * seconds)):
            v = int(12000 * math.sin(2 * math.pi * freq * (i / rate)))
            frames += struct.pack("<h", v)
        w.writeframes(bytes(frames))
    return buf.getvalue()


# ── reachability: the defect itself ─────────────────────────────────────────

def test_01_authenticated_principal_gets_health_200(client, isolated):
    r = client.get("/api/v1/voice/stt/health", headers=platform_headers(client, isolated))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "available" in body and "state" in body


def test_02_anonymous_health_denied(client):
    assert client.get("/api/v1/voice/stt/health").status_code == 401


def test_03_anonymous_transcribe_denied(client):
    r = client.post("/api/v1/voice/stt/transcribe",
                    files={"file": ("a.wav", synthetic_wav(0.1), "audio/wav")})
    assert r.status_code == 401


@pytest.mark.parametrize("headers", [
    {"X-Platform-Token": "not-a-real-token"},
    {"Authorization": "Bearer not-a-real-token"},
    {"X-Platform-Token": ""},
])
def test_04_malformed_or_unknown_credential_denied(client, headers):
    assert client.get("/api/v1/voice/stt/health", headers=headers).status_code == 401


def test_05_wrong_credential_class_denied(client, isolated):
    """A canonical session is not a platform session; this boundary takes one."""
    from saathi import sessions
    from support.auth_state import make_active

    make_active(isolated, password=CANONICAL_PASSWORD)
    canonical = sessions.create(ua="pytest", ip="127.0.0.1", kind="password")
    r = client.get("/api/v1/voice/stt/health", headers={"x-baadar-session": canonical})
    assert r.status_code == 401


def test_06_revoked_platform_session_denied(client, isolated):
    headers = platform_headers(client, isolated)
    from saathi.platform.service import default_platform
    svc = default_platform()
    sess = svc.store.session_by_token(headers["X-Platform-Token"])
    svc.store.revoke_session(sess.session_id)
    assert client.get("/api/v1/voice/stt/health", headers=headers).status_code == 401


def test_07_expired_platform_session_denied(client, isolated):
    import time
    headers = platform_headers(client, isolated)
    from saathi.platform.service import default_platform
    svc = default_platform()
    sess = svc.store.session_by_token(headers["X-Platform-Token"])
    svc.store._conn.execute("UPDATE sessions SET expires_at=? WHERE session_id=?",
                            (time.time() - 60, sess.session_id))
    svc.store._conn.commit()
    assert client.get("/api/v1/voice/stt/health", headers=headers).status_code == 401


# ── transcription, on generated audio only ──────────────────────────────────

def test_08_valid_principal_can_transcribe_a_synthetic_fixture(client, isolated):
    headers = platform_headers(client, isolated)
    health = client.get("/api/v1/voice/stt/health", headers=headers).json()
    if not health.get("available"):
        pytest.skip(f"local engine unavailable in this environment: {health.get('reason')}")

    r = client.post("/api/v1/voice/stt/transcribe", headers=headers,
                    files={"file": ("tone.wav", synthetic_wav(), "audio/wav")},
                    data={"language": "en"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["isFinal"] is True
    assert body["privacyClass"] == "LOCAL_CONFIRMED"
    assert body["authority"] == "none"
    assert isinstance(body["text"], str)


def test_09_transcript_is_attributed_to_the_validated_principal(client, isolated):
    headers = platform_headers(client, isolated)
    health = client.get("/api/v1/voice/stt/health", headers=headers).json()
    if not health.get("available"):
        pytest.skip("local engine unavailable")

    from saathi.platform.service import default_platform
    expected = default_platform().store.session_by_token(headers["X-Platform-Token"]).user_id
    r = client.post("/api/v1/voice/stt/transcribe", headers=headers,
                    files={"file": ("tone.wav", synthetic_wav(0.2), "audio/wav")})
    assert r.status_code == 200
    assert r.json()["principal"] == expected


def test_10_caller_cannot_choose_another_user(client, isolated):
    """Attribution is read from the session, never from the request."""
    import ast
    import inspect
    from saathi.voice_os import api

    src = inspect.getsource(api.stt_transcribe)
    tree = ast.parse(src.strip())
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in ("user_id", "principal"):
            assert not isinstance(node.value, ast.Constant)
    assert "ctx.user_id" in src
    assert "request.query_params" not in src

    health = client.get("/api/v1/voice/stt/health",
                        headers=platform_headers(client, isolated)).json()
    if not health.get("available"):
        pytest.skip("local engine unavailable")
    headers = platform_headers(client, isolated)
    from saathi.platform.service import default_platform
    real = default_platform().store.session_by_token(headers["X-Platform-Token"]).user_id
    r = client.post("/api/v1/voice/stt/transcribe?user_id=somebody-else", headers=headers,
                    files={"file": ("tone.wav", synthetic_wav(0.2), "audio/wav")},
                    data={"principal": "somebody-else", "user_id": "somebody-else"})
    if r.status_code == 200:
        assert r.json()["principal"] == real


# ── bounds, cleanup, and what must not change ───────────────────────────────

def test_11_health_decodes_nothing_and_writes_nothing(client, isolated, tmp_path):
    artifacts = tmp_path / "artifacts"
    before = sorted(p.name for p in artifacts.glob("**/*")) if artifacts.exists() else []
    r = client.get("/api/v1/voice/stt/health", headers=platform_headers(client, isolated))
    assert r.status_code == 200
    after = sorted(p.name for p in artifacts.glob("**/*")) if artifacts.exists() else []
    assert before == after


def test_12_input_bounds_still_enforced(client, isolated):
    from saathi.voice_os import local_whisper
    headers = platform_headers(client, isolated)

    bad_type = client.post("/api/v1/voice/stt/transcribe", headers=headers,
                           files={"file": ("a.mp3", b"nope", "audio/mpeg")})
    assert bad_type.status_code == 415

    oversized = b"\x00" * (local_whisper.MAX_AUDIO_BYTES + 1024)
    too_big = client.post("/api/v1/voice/stt/transcribe", headers=headers,
                          files={"file": ("a.wav", oversized, "audio/wav")})
    assert too_big.status_code == 413

    garbage = client.post("/api/v1/voice/stt/transcribe", headers=headers,
                          files={"file": ("a.wav", b"not-a-riff-stream", "audio/wav")})
    assert garbage.status_code in (415, 503)


def test_13_no_raw_audio_is_retained_on_any_terminal_path(client, isolated, tmp_path):
    """Success, decode failure and oversize alike must leave nothing behind."""
    headers = platform_headers(client, isolated)
    artifacts = tmp_path / "artifacts"

    for payload, mime in ((synthetic_wav(0.2), "audio/wav"),
                          (b"not-a-riff-stream", "audio/wav")):
        client.post("/api/v1/voice/stt/transcribe", headers=headers,
                    files={"file": ("a.wav", payload, mime)})

    leftovers = [p for p in artifacts.glob("**/*") if p.is_file()] if artifacts.exists() else []
    assert leftovers == [], leftovers


def test_14_engine_removes_its_temporary_file_in_a_finally(client):
    import ast
    import inspect
    from saathi.voice_os import local_whisper

    src = inspect.getsource(local_whisper)
    assert "finally:" in src and "unlink" in src
    tree = ast.parse(src)
    unlink_in_finally = any(
        isinstance(node, ast.Try) and node.finalbody and
        any("unlink" in ast.dump(n) for n in node.finalbody)
        for node in ast.walk(tree)
    )
    assert unlink_in_finally, "temporary audio must be removed in a finally"


def test_15_no_browser_fallback_or_external_speech_route_is_enabled():
    import ast
    import inspect
    from saathi.voice_os import api

    # Executable statements only. The module docstring *describes* the browser
    # APIs it deliberately does not use, and a check that reads prose would fail
    # on the explanation rather than on the behaviour.
    tree = ast.parse(inspect.getsource(api))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            node.value = ast.Constant(value="")
    code = ast.dump(tree)
    for banned in ("SpeechRecognition", "webkitSpeechRecognition",
                   "speech.googleapis.com", "api.openai.com"):
        assert banned not in code


def test_16_voice_authority_remains_none(client, isolated):
    headers = platform_headers(client, isolated)
    health = client.get("/api/v1/voice/stt/health", headers=headers).json()
    if not health.get("available"):
        pytest.skip("local engine unavailable")
    r = client.post("/api/v1/voice/stt/transcribe", headers=headers,
                    files={"file": ("tone.wav", synthetic_wav(0.2), "audio/wav")})
    assert r.status_code == 200
    assert r.json()["authority"] == "none"
    assert "executable" not in r.json()


def test_17_no_global_request_state_user_id_is_introduced():
    """The blast radius that made the obvious fix the wrong one.

    Two routers read this attribute as ``... or "ajay"``. Assigning it in the
    middleware would re-attribute their actions from that hardcoded string to
    the real owner, silently, as a side effect of repairing a voice endpoint.
    """
    import pathlib
    repo = pathlib.Path(__file__).resolve().parent.parent
    server = (repo / "saathi" / "server.py").read_text()
    assert "state.user_id" not in server
    assert "request.state.user_id" not in server

    import ast
    import inspect
    from saathi.voice_os import api

    # Again: statements, not the docstring that explains why the attribute is
    # not read.
    fn = ast.parse(inspect.getsource(api._stt_principal).strip()).body[0]
    body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr)
                           and isinstance(fn.body[0].value, ast.Constant)) else fn.body
    assert "user_id" not in "\n".join(ast.dump(n) for n in body)


def test_18_unrelated_routers_did_not_become_reachable(client):
    """The middleware change is two exact paths, not a prefix."""
    import inspect
    import saathi.server as svr

    src = inspect.getsource(svr._auth)
    assert "_PLATFORM_CREDENTIAL_PATHS" in src
    assert 'path.startswith("/api/v1/voice' not in src

    for path in ("/api/v1/voice/command", "/api/v1/voice/sessions",
                 "/api/v1/events/recent", "/api/v1/tokens"):
        r = client.get(path, headers={"X-Platform-Token": "anything"})
        assert r.status_code in (401, 404, 405, 409, 422), (path, r.status_code)


def test_19_execution_and_trading_boundaries_unchanged():
    from saathi.tools.registry import execute_tool
    from saathi.platform.tg import LIVE_TRADING_AUTHORIZED

    out = execute_tool("send_email", {"to": "a@b.c", "subject": "s", "body": "b"})
    assert out.get("blocked") or out.get("error")
    assert LIVE_TRADING_AUTHORIZED is False


def test_20_cookies_are_not_accepted_so_no_csrf_surface_exists():
    """A header credential cannot be attached by a cross-site page."""
    import inspect
    from saathi.voice_os import api

    src = inspect.getsource(api._stt_principal)
    assert "cookies" not in src
    assert "x-platform-token" in src.lower()


def test_21_transcribe_authenticates_in_its_own_body_before_decoding():
    """The handler's own gate, which no request-level test can reach.

    Anonymous callers are rejected by the middleware first, so removing the
    check inside the handler changes no status code — until the day the
    allowlist regresses, which is a thing that has happened twice in this
    codebase. The gate is therefore asserted directly, and asserted to come
    before anything reads the upload: authenticate, then bound, then decode.
    """
    import ast
    import inspect
    from saathi.voice_os import api

    fn = ast.parse(inspect.getsource(api.stt_transcribe).strip()).body[0]
    calls = sorted((n.lineno, n.func.id) for n in ast.walk(fn)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Name))
    names = [n for _, n in calls]
    assert "_stt_principal" in names, "stt_transcribe no longer authenticates"

    # The refusal must be guarded by the resolved principal, not merely present.
    # `if False: return 401` leaves an identical 401 return in the tree while
    # authenticating nobody, so the *condition* is what gets asserted.
    guards = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        if "401" not in ast.dump(ast.Module(body=node.body, type_ignores=[])):
            continue
        test = ast.dump(node.test)
        if isinstance(node.test, ast.Constant):
            continue                      # `if False:` and friends do not count
        if "ctx" in test or "_stt_principal" in test:
            guards.append(node)
    assert guards, "the 401 must be guarded by the resolved principal"

    gate_line = min(l for l, n in calls if n == "_stt_principal")
    refusal = min(g.lineno for g in guards)
    assert refusal >= gate_line
    assert refusal < max(
        (n.lineno for n in ast.walk(fn)
         if isinstance(n, ast.Attribute) and n.attr in ("read", "transcribe_wav")),
        default=10**6,
    ), "the refusal must precede reading or decoding the upload"
