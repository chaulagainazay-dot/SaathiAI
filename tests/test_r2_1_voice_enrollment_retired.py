"""R2.1-S4 — voice enrollment is retired, and says so truthfully.

``/api/v1/voice/enroll`` was documented as the step that "unlocks owner
actions". That is the exact claim the authority repair removed, so the
capability is retired rather than re-gated: a speaker profile is not a
credential, and an endpoint that mints one invites the belief that it is.

The endpoint must not pretend to succeed, must not read the audio it is sent,
and must not touch a profile that already exists on disk.
"""
import inspect
import io

import pytest
from fastapi.testclient import TestClient

from saathi import config, server, voice


@pytest.fixture(autouse=True)
def _active_installation(tmp_path, monkeypatch):
    """D14: an authenticated caller needs an ACTIVE installation to exist."""
    import sys, pathlib as _pl
    sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
    from saathi.security import store as store_mod
    from support.auth_state import make_active

    monkeypatch.setenv("SAATHI_STATE_ROOT", str(tmp_path / "state"))
    store_mod.close_store()
    store_mod._default_store = None
    fresh = store_mod.SecurityStore(db_path=tmp_path / "security.db")
    store_mod._default_store = fresh
    make_active(fresh)
    yield fresh
    fresh.close()
    store_mod.close_store()
    store_mod._default_store = None


@pytest.fixture
def client():
    return TestClient(server.app)


@pytest.fixture
def authed():
    # D14: a real session. ``_session_token()`` is gone -- it was a constant
    # derived from a process global an ACTIVE system no longer sets.
    from saathi import sessions
    return {"x-baadar-session": sessions.create(ua="pytest", ip="127.0.0.1",
                                                kind="password")}


def _upload(content=b"\x1a\x45\xdf\xa3fake-webm"):
    return {"file": ("enroll.webm", io.BytesIO(content), "audio/webm")}


def test_anonymous_enrollment_is_rejected(client):
    r = client.post("/api/v1/voice/enroll", files=_upload())
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"


def test_authenticated_enrollment_reports_unavailable(client, authed):
    r = client.post("/api/v1/voice/enroll", files=_upload(), headers=authed)
    assert r.status_code == 410
    body = r.json()
    assert body["error"] == "voice_enrollment_unavailable"
    assert body["deprecated"] is True
    assert "status" not in body and "enrolled" not in r.text


def test_endpoint_never_enrolls(client, authed, monkeypatch):
    """No profile is written, whatever the caller sends."""
    calls = []
    monkeypatch.setattr(voice, "enroll", lambda *a, **kw: calls.append(a))
    monkeypatch.setattr(voice, "_decode",
                        lambda *a, **kw: pytest.fail("audio was decoded"))
    client.post("/api/v1/voice/enroll", files=_upload(b"x" * 100_000), headers=authed)
    assert calls == []


def test_existing_profile_is_preserved(client, authed, tmp_path, monkeypatch):
    profile = tmp_path / "voice_profile.npy"
    profile.write_bytes(b"original-profile")
    monkeypatch.setattr(config, "VOICE_PROFILE_PATH", profile)
    client.post("/api/v1/voice/enroll", files=_upload(), headers=authed)
    assert profile.read_bytes() == b"original-profile"


def test_endpoint_declares_no_upload_parameter():
    """Declaring an UploadFile would make the framework spool the body first."""
    params = inspect.signature(server.enroll_voice).parameters
    assert list(params) == ["request"], (
        "a body parameter would be parsed before the handler can refuse"
    )


def test_attempt_is_audited_without_content(client, authed, monkeypatch):
    recorded = {}

    def fake_audit(event, **kw):
        recorded["event"] = event
        recorded["kw"] = kw

    from saathi import authsec
    monkeypatch.setattr(authsec, "audit", fake_audit)
    client.post("/api/v1/voice/enroll", files=_upload(b"SECRETAUDIO"), headers=authed)
    assert recorded["event"] == "voice_enroll_attempt"
    assert recorded["kw"]["ok"] is False
    assert "SECRETAUDIO" not in repr(recorded)


def test_retired_endpoint_grants_no_authority(client, authed):
    """The response cannot be mistaken for a credential."""
    r = client.post("/api/v1/voice/enroll", files=_upload(), headers=authed)
    blob = r.text
    for claim in ("token", "session", "approval", "identity", "admin", "role"):
        assert claim not in blob.lower()
