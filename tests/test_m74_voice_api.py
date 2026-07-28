"""M74 authenticated speech API, isolation, audio range, and session tests."""
from __future__ import annotations

from fastapi.testclient import TestClient

from saathi.platform.service import reset_platform_for_tests
from saathi.platform.voice.service import SpeechService
from saathi.tool_runtime.registry import reset_registry_for_tests

from test_m74_voice_foundation import FakeProvider


def client_and_headers(tmp_path, monkeypatch):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "voice-api.db")
    import saathi.platform.api as api_module
    import saathi.platform.service as service_module

    monkeypatch.setattr(service_module, "_DEFAULT", platform)
    monkeypatch.setattr(api_module, "default_platform", lambda: platform)
    from saathi.server import app

    client = TestClient(app)
    boot = client.post(
        "/api/v1/platform/bootstrap",
        json={
            "email": "voice-api@local",
            "name": "Voice API",
            "password": "VoiceApiPass1!",
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
    return client, {"X-Platform-Token": token}, platform, speech


def test_voice_routes_require_authentication(tmp_path, monkeypatch):
    client, _, _, _ = client_and_headers(tmp_path, monkeypatch)
    for method, path, payload in (
        ("get", "/health", None),
        ("get", "/providers", None),
        ("get", "/profiles", None),
        ("get", "/speech", None),
        ("post", "/speech", {"text": "No anonymous synthesis."}),
        ("post", "/profiles", {"display_name": "No anonymous profile."}),
        ("get", "/evidence", None),
    ):
        kwargs = {"json": payload} if payload is not None else {}
        response = getattr(client, method)(
            f"/api/v1/platform/voice{path}", **kwargs
        )
        assert response.status_code == 401, path


def test_speech_api_health_lifecycle_idempotency_audio_and_range(
    tmp_path, monkeypatch
):
    client, headers, _, speech = client_and_headers(tmp_path, monkeypatch)
    health = client.get("/api/v1/platform/voice/health", headers=headers)
    assert health.status_code == 200
    assert health.json()["health"]["english_certified"] is True
    providers = client.get(
        "/api/v1/platform/voice/providers", headers=headers
    ).json()["providers"]
    assert providers[0]["provider_id"] == "macos_system"

    created = client.post(
        "/api/v1/platform/voice/speech",
        headers=headers,
        json={
            "text": "API English speech fixture.",
            "idempotency_key": "api-same",
        },
    )
    assert created.status_code == 200
    operation_id = created.json()["operation"]["operation_id"]
    replay = client.post(
        "/api/v1/platform/voice/speech",
        headers=headers,
        json={
            "text": "API English speech fixture.",
            "idempotency_key": "api-same",
        },
    )
    assert replay.json()["operation"]["operation_id"] == operation_id
    speech.wait(operation_id)
    inspected = client.get(
        f"/api/v1/platform/voice/speech/{operation_id}", headers=headers
    )
    assert inspected.json()["operation"]["state"] == "completed"
    assert "artifact_name" not in inspected.text
    assert "/Users/" not in inspected.text

    audio = client.get(
        f"/api/v1/platform/voice/speech/{operation_id}/audio", headers=headers
    )
    assert audio.status_code == 200
    assert audio.headers["cache-control"].startswith("private, no-store")
    assert audio.headers["content-type"].startswith("audio/aiff")
    ranged = client.get(
        f"/api/v1/platform/voice/speech/{operation_id}/audio",
        headers={**headers, "Range": "bytes=0-3"},
    )
    assert ranged.status_code == 206
    assert ranged.content == b"FORM"
    assert ranged.headers["content-range"] == "bytes 0-3/12"
    invalid = client.get(
        f"/api/v1/platform/voice/speech/{operation_id}/audio",
        headers={**headers, "Range": "bytes=100-200"},
    )
    assert invalid.status_code == 416


def test_api_validation_profile_crud_cloning_disabled_and_safe_404(
    tmp_path, monkeypatch
):
    client, headers, _, _ = client_and_headers(tmp_path, monkeypatch)
    oversized = client.post(
        "/api/v1/platform/voice/speech",
        headers=headers,
        json={"text": "x" * 4_001},
    )
    assert oversized.status_code == 422
    wrong_content = client.post(
        "/api/v1/platform/voice/speech",
        headers={**headers, "Content-Type": "text/plain"},
        content="not json",
    )
    assert wrong_content.status_code == 422
    extra = client.post(
        "/api/v1/platform/voice/speech",
        headers=headers,
        json={"text": "Safe.", "organization_id": "spoofed"},
    )
    assert extra.status_code == 422

    created = client.post(
        "/api/v1/platform/voice/profiles",
        headers=headers,
        json={
            "display_name": "Reading voice",
            "provider": "macos_system",
            "rate": 0.9,
        },
    )
    assert created.status_code == 200
    profile_id = created.json()["profile"]["profile_id"]
    updated = client.patch(
        f"/api/v1/platform/voice/profiles/{profile_id}",
        headers=headers,
        json={"accessibility_rate": 0.8},
    )
    assert updated.status_code == 200
    assert updated.json()["profile"]["accessibility_rate"] == 0.8
    clone = client.post(
        "/api/v1/platform/voice/profiles",
        headers=headers,
        json={
            "display_name": "Forbidden",
            "reference_artifact_id": "artifact_reference",
            "cloning_consent_state": "approved",
        },
    )
    assert clone.status_code in {400, 422}
    assert "clone" not in clone.text.lower() or "disabled" in clone.text.lower()
    deleted = client.delete(
        f"/api/v1/platform/voice/profiles/{profile_id}", headers=headers
    )
    assert deleted.json()["deleted"] is True
    missing = client.get(
        "/api/v1/platform/voice/speech/not-real", headers=headers
    )
    assert missing.status_code == 404
    assert "sqlite" not in missing.text.lower()
    assert "/users/" not in missing.text.lower()


def test_cancel_evidence_and_logout_revocation(tmp_path, monkeypatch):
    client, headers, _, speech = client_and_headers(tmp_path, monkeypatch)
    blocking = FakeProvider(block=True)
    speech.shutdown()
    replacement = SpeechService(
        speech.store,
        providers=[blocking],
        artifact_root=tmp_path / "cancel-artifacts",
    )
    import saathi.platform.api as api_module

    api_module._svc()._speech_service = replacement
    created = client.post(
        "/api/v1/platform/voice/speech",
        headers=headers,
        json={"text": "Cancel through API."},
    ).json()["operation"]
    assert blocking.started.wait(1)
    cancelled = client.post(
        f"/api/v1/platform/voice/speech/{created['operation_id']}/cancel",
        headers=headers,
    )
    assert cancelled.status_code == 200
    assert replacement.wait(created["operation_id"]).state == "cancelled"
    evidence = client.get(
        "/api/v1/platform/voice/evidence", headers=headers
    ).json()["evidence"]
    assert any(item["event_type"] == "speech.cancelled" for item in evidence)
    assert client.post(
        "/api/v1/platform/auth/logout", headers=headers
    ).status_code == 200
    assert client.get(
        "/api/v1/platform/voice/health", headers=headers
    ).status_code == 401
