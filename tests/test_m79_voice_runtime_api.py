"""M79 authenticated Voice Runtime API tests."""
from __future__ import annotations

from fastapi.testclient import TestClient

from saathi.platform.service import reset_platform_for_tests
from saathi.platform.conversation import make_test_conversation_service
from saathi.platform.voice.runtime import VoiceSessionManager, reset_voice_runtime_for_tests
from saathi.platform.voice.service import SpeechService, reset_speech_service_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests
from test_m74_voice_foundation import FakeProvider


def client_and_headers(tmp_path, monkeypatch):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "voice-runtime-api.db")
    import saathi.platform.api as api_module
    import saathi.platform.service as service_module

    monkeypatch.setattr(service_module, "_DEFAULT", platform)
    monkeypatch.setattr(api_module, "default_platform", lambda: platform)
    from saathi.server import app

    client = TestClient(app)
    boot = client.post(
        "/api/v1/platform/bootstrap",
        json={
            "email": "voice-rt-api@local",
            "name": "Voice RT API",
            "password": "VoiceRtApiPass1!",
        },
    )
    assert boot.status_code == 200
    token = boot.json()["token"]
    speech = SpeechService(
        platform.store,
        providers=[FakeProvider()],
        artifact_root=tmp_path / "api-artifacts",
    )
    platform._speech_service = speech
    conv = make_test_conversation_service(
        platform.store,
        reply_fn=lambda messages: "Hello from injected intelligence for API tests.",
    )
    platform._conversation_service = conv
    platform._voice_runtime = VoiceSessionManager(
        platform.store, speech_service=speech, conversation_service=conv
    )
    return client, {"X-Platform-Token": token}, platform, speech


def test_runtime_routes_require_auth(tmp_path, monkeypatch):
    client, _, platform, speech = client_and_headers(tmp_path, monkeypatch)
    try:
        for method, path, payload in (
            ("get", "/runtime/health", None),
            ("get", "/runtime/stt-providers", None),
            ("get", "/runtime/sessions", None),
            ("post", "/runtime/sessions", {"yeti_mode": "general"}),
        ):
            kwargs = {"json": payload} if payload is not None else {}
            response = getattr(client, method)(
                f"/api/v1/platform/voice{path}", **kwargs
            )
            assert response.status_code == 401, path
    finally:
        speech.shutdown()
        reset_speech_service_for_tests(platform)
        reset_voice_runtime_for_tests(platform)


def test_runtime_session_turn_interrupt_and_logout(tmp_path, monkeypatch):
    client, headers, platform, speech = client_and_headers(tmp_path, monkeypatch)
    try:
        health = client.get(
            "/api/v1/platform/voice/runtime/health", headers=headers
        )
        assert health.status_code == 200
        assert health.json()["health"]["loopback_only"] is True

        providers = client.get(
            "/api/v1/platform/voice/runtime/stt-providers", headers=headers
        )
        assert providers.status_code == 200
        assert any(
            p["provider_id"] == "browser" for p in providers.json()["providers"]
        )

        created = client.post(
            "/api/v1/platform/voice/runtime/sessions",
            headers=headers,
            json={
                "yeti_mode": "general",
                "stt_provider": "browser",
                "voice_profile_id": "yeti_teacher",
            },
        )
        assert created.status_code == 200, created.text
        sid = created.json()["session"]["session_id"]

        listen = client.post(
            f"/api/v1/platform/voice/runtime/sessions/{sid}/listen",
            headers=headers,
            json={"mode": "toggle", "permission_granted": True},
        )
        assert listen.status_code == 200
        assert listen.json()["session"]["state"] == "LISTENING"

        partial = client.post(
            f"/api/v1/platform/voice/runtime/sessions/{sid}/transcript",
            headers=headers,
            json={"text": "hi", "is_final": False, "partial": True},
        )
        assert partial.status_code == 200
        assert partial.json()["session"]["partial_user_transcript"] == "hi"

        final = client.post(
            f"/api/v1/platform/voice/runtime/sessions/{sid}/transcript",
            headers=headers,
            json={"text": "hello yeti", "is_final": True},
        )
        assert final.status_code == 200, final.text
        body = final.json()
        assert body["turn"]["assistant_text"]
        assert any(t["role"] == "user" for t in body["session"]["transcript"])

        # Force responding for interrupt
        runtime = platform._voice_runtime
        ctx = platform.require_context(headers["X-Platform-Token"])
        session = runtime._get_owned(ctx, sid)
        session.state = "RESPONDING"
        session.partial_assistant_response = "long partial reply"
        runtime.repo.save_session(session)

        interrupted = client.post(
            f"/api/v1/platform/voice/runtime/sessions/{sid}/interrupt",
            headers=headers,
        )
        assert interrupted.status_code == 200
        assert interrupted.json()["session"]["state"] == "LISTENING"
        assert interrupted.json()["session"]["interruptions"]

        listed = client.get(
            "/api/v1/platform/voice/runtime/sessions", headers=headers
        )
        assert listed.status_code == 200
        assert listed.json()["sessions"]

        logout = client.post("/api/v1/platform/auth/logout", headers=headers)
        assert logout.status_code == 200
        assert logout.json().get("ok") is True
        assert "voice_sessions_cleared" in logout.json()
    finally:
        speech.shutdown()
        reset_speech_service_for_tests(platform)
        reset_voice_runtime_for_tests(platform)
        reset_platform_for_tests()
