"""M74 provider-neutral speech service, providers, authority, and safety."""
from __future__ import annotations

from pathlib import Path
import json
import secrets
from types import SimpleNamespace
import threading
import time

import pytest

from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformPermission, PlatformRole, role_has_permission
from saathi.platform.service import reset_platform_for_tests
from saathi.platform.voice.models import MAX_QUEUE_DEPTH, SpeechRequest, SpeechState
from saathi.platform.voice.providers import (
    MacOSSystemSpeechProvider,
    ProviderCancelled,
    ProviderError,
    SpeechProvider,
    UnavailableSpeechProvider,
    VoxCPMConfig,
    VoxCPMSpeechProvider,
)
from saathi.platform.voice.service import SpeechService


class FakeProvider(SpeechProvider):
    def __init__(
        self,
        provider_id: str = "macos_system",
        *,
        heavy: bool = False,
        state: str = "ready",
        error: str = "",
        block: bool = False,
    ):
        self.provider_id = provider_id
        self.heavy = heavy
        self.state = state
        self.error = error
        self.block = block
        self.release = threading.Event()
        self.started = threading.Event()
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()
        self.argv_requests: list[SpeechRequest] = []

    def capabilities(self):
        return {
            "provider_id": self.provider_id,
            "synthesis": self.state == "ready",
            "streaming": False,
            "cancellation": True,
            "languages": ["en-US"],
            "certified_languages": ["en"],
            "cloning": False,
            "local_only": True,
        }

    def health(self):
        return {
            "provider_id": self.provider_id,
            "state": self.state,
            "configured": True,
            "installed": self.state == "ready",
            "model_available": False,
            "runtime_verified": self.state == "ready",
        }

    def synthesize(self, request, output_path, *, cancel_check):
        self.argv_requests.append(request)
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        self.started.set()
        try:
            if self.error:
                raise ProviderError(self.error, "safe fixture failure")
            while self.block and not self.release.wait(0.01):
                if cancel_check():
                    raise ProviderCancelled()
            if cancel_check():
                raise ProviderCancelled()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"FORM\x00\x00\x00\x04AIFF")
            return SimpleNamespace(
                provider=self.provider_id,
                output_format=request.output_format,
                sample_rate=22_050,
                artifact_bytes=12,
                duration_seconds=0.01,
                first_audio_ms=5.0,
                total_ms=10.0,
                streaming_state="artifact_ready",
            )
        finally:
            with self.lock:
                self.active -= 1

    def cancel(self, operation_id):
        return True

    def shutdown(self):
        self.release.set()


@pytest.fixture()
def platform_ctx(tmp_path):
    platform = reset_platform_for_tests(tmp_path / "voice.db")
    boot = platform.bootstrap_owner_secure(
        email="voice-owner@local",
        name="Voice Owner",
        password="VoiceOwnerPass1!",
    )
    return platform, platform.require_context(boot["token"])


def speech_service(platform, tmp_path, providers, **kwargs):
    return SpeechService(
        platform.store,
        providers=providers,
        artifact_root=tmp_path / "voice-artifacts",
        **kwargs,
    )


def test_request_validation_and_persisted_metadata_excludes_text(platform_ctx):
    platform, ctx = platform_ctx
    request = SpeechRequest.from_payload(
        ctx,
        {
            "text": "**Hello** [source](https://example.invalid).",
            "speaking_rate": 1.2,
            "language": "en-US",
        },
    )
    assert request.text == "Hello source."
    assert "text" not in request.persisted_metadata()
    with pytest.raises(Exception, match="4000"):
        SpeechRequest.from_payload(ctx, {"text": "x" * 4_001})
    with pytest.raises(Exception, match="credential"):
        SpeechRequest.from_payload(ctx, {"text": "Authorization: Bearer secret"})


def test_lifecycle_idempotency_artifact_evidence_and_audit(platform_ctx, tmp_path):
    platform, ctx = platform_ctx
    provider = FakeProvider()
    service = speech_service(platform, tmp_path, [provider])
    first = service.create_speech(
        ctx, {"text": "A bounded English fixture.", "idempotency_key": "same-1"}
    )
    replay = service.create_speech(
        ctx, {"text": "A bounded English fixture.", "idempotency_key": "same-1"}
    )
    assert replay["operation_id"] == first["operation_id"]
    completed = service.wait(first["operation_id"])
    assert completed.state == SpeechState.COMPLETED.value
    assert completed.provider == "macos_system"
    public = completed.to_public()
    assert "artifact_name" not in public
    assert "text_sha256" not in public
    operation, path = service.artifact(ctx, completed.operation_id)
    assert operation.artifact_id.startswith("voice-artifact:")
    assert path.parent == (tmp_path / "voice-artifacts").resolve()
    assert service.evidence(ctx)
    audits = platform.store.list_audit(org_id=ctx.org_id)
    assert any(item["event"] == "voice.speech.completed" for item in audits)
    row = platform.store._conn.execute(
        "SELECT request_json FROM voice_speech_operations WHERE operation_id=?",
        (completed.operation_id,),
    ).fetchone()
    assert "A bounded English fixture." not in row["request_json"]
    assert "A bounded English fixture." not in json.dumps(audits)
    service.shutdown()


def test_unavailable_timeout_failure_and_system_fallback(platform_ctx, tmp_path):
    platform, ctx = platform_ctx
    unavailable_service = speech_service(
        platform, tmp_path / "u", [UnavailableSpeechProvider()]
    )
    missing = unavailable_service.create_speech(ctx, {"text": "No provider."})
    assert unavailable_service.wait(missing["operation_id"]).state == "unavailable"
    unavailable_service.shutdown()

    timeout_provider = FakeProvider(error="timeout")
    timeout_service = speech_service(platform, tmp_path / "t", [timeout_provider])
    timed = timeout_service.create_speech(
        ctx, {"text": "Timeout fixture.", "provider": "macos_system"}
    )
    timed_result = timeout_service.wait(timed["operation_id"])
    assert timed_result.state == "failed"
    assert timed_result.error_category == "timeout"
    timeout_service.shutdown()

    vox = FakeProvider("voxcpm", heavy=True, error="provider_failed")
    system = FakeProvider("macos_system")
    fallback_service = speech_service(platform, tmp_path / "f", [vox, system])
    fallback = fallback_service.create_speech(
        ctx, {"text": "Fallback fixture.", "provider": "voxcpm"}
    )
    fallback_result = fallback_service.wait(fallback["operation_id"])
    assert fallback_result.state == "completed"
    assert fallback_result.provider == "macos_system"
    assert fallback_result.fallback_used is True
    assert fallback_result.fallback_reason == "voxcpm_unavailable"
    fallback_service.shutdown()


def test_cancellation_acknowledged_and_artifact_removed(platform_ctx, tmp_path):
    platform, ctx = platform_ctx
    provider = FakeProvider(block=True)
    service = speech_service(platform, tmp_path, [provider])
    created = service.create_speech(ctx, {"text": "Cancel this speech."})
    assert provider.started.wait(1)
    started = time.monotonic()
    service.cancel(ctx, created["operation_id"])
    result = service.wait(created["operation_id"])
    assert result.state == "cancelled"
    assert time.monotonic() - started < 0.5
    assert not list((tmp_path / "voice-artifacts").glob("*"))
    service.shutdown()


def test_queue_depth_and_heavy_provider_concurrency_are_bounded(
    platform_ctx, tmp_path
):
    platform, ctx = platform_ctx
    queued_service = speech_service(
        platform,
        tmp_path / "queue",
        [FakeProvider()],
        start_workers=False,
        queue_depth=MAX_QUEUE_DEPTH,
    )
    for index in range(MAX_QUEUE_DEPTH):
        queued_service.create_speech(ctx, {"text": f"Queued fixture {index}."})
    with pytest.raises(PlatformContextError) as error:
        queued_service.create_speech(ctx, {"text": "One request too many."})
    assert error.value.code == "RESOURCE_BUDGET_EXHAUSTED"
    queued_service.shutdown()

    heavy = FakeProvider("voxcpm", heavy=True, block=True)
    concurrent = speech_service(
        platform, tmp_path / "heavy", [heavy], worker_count=2
    )
    first = concurrent.create_speech(
        ctx, {"text": "Heavy one.", "provider": "voxcpm"}
    )
    second = concurrent.create_speech(
        ctx, {"text": "Heavy two.", "provider": "voxcpm"}
    )
    assert heavy.started.wait(1)
    time.sleep(0.05)
    assert heavy.max_active == 1
    heavy.release.set()
    assert concurrent.wait(first["operation_id"]).state == "completed"
    assert concurrent.wait(second["operation_id"]).state == "completed"
    assert heavy.max_active == 1
    concurrent.shutdown()


def test_restart_reconciliation_and_expiry_cleanup(platform_ctx, tmp_path):
    platform, ctx = platform_ctx
    service = speech_service(
        platform,
        tmp_path,
        [FakeProvider()],
        start_workers=False,
        retention_seconds=60,
    )
    queued = service.create_speech(ctx, {"text": "Interrupted fixture."})
    recovered = speech_service(platform, tmp_path, [FakeProvider()])
    operation = recovered.repo.get_operation_unscoped(queued["operation_id"])
    assert recovered.reconciled_operations == 1
    assert operation and operation.state == "unavailable"
    recovered.shutdown()
    service.shutdown()


def test_profiles_yeti_and_cloning_remain_provider_neutral_and_disabled(
    platform_ctx, tmp_path
):
    platform, ctx = platform_ctx
    service = speech_service(platform, tmp_path, [FakeProvider()])
    profiles = service.list_profiles(ctx)
    yeti = next(item for item in profiles if item["profile_id"] == "yeti_teacher")
    assert yeti["provider"] == "auto"
    assert "VoxCPM" not in yeti["style"]
    custom = service.create_profile(
        ctx,
        {
            "display_name": "Accessible English",
            "provider": "macos_system",
            "language": "en-US",
            "rate": 0.9,
            "accessibility_rate": 0.8,
        },
    )
    assert custom["owner_id"] == ctx.user_id
    with pytest.raises(PlatformContextError) as error:
        service.create_profile(
            ctx,
            {
                "display_name": "Forbidden clone",
                "reference_artifact_id": "artifact_voice_ref",
                "cloning_consent_state": "approved",
            },
        )
    assert error.value.code == "VALIDATION_FAILED"
    assert service.health(ctx)["cloning_state"] == "CAPABILITY_DISABLED"
    service.shutdown()


def test_rbac_registration_ownership_tenant_and_workspace_isolation(
    platform_ctx, tmp_path
):
    platform, owner_ctx = platform_ctx
    unregistered = platform.store.create_user(email="plain@local", name="Plain")
    assert platform.store.list_orgs_for_user(unregistered.user_id) == []

    org = platform.store.list_orgs_for_user(owner_ctx.user_id)[0]
    workspace = platform.store.list_workspaces(org.org_id)[0]
    viewers = []
    for index in range(2):
        user = platform.store.create_user(email=f"viewer{index}@local", name="Viewer")
        platform.store.add_member(org.org_id, user.user_id, PlatformRole.VIEWER.value)
        token = secrets.token_urlsafe(18)
        platform.store.create_session(
            user.user_id,
            token,
            org_id=org.org_id,
            workspace_id=workspace.workspace_id,
            role=PlatformRole.VIEWER.value,
        )
        viewers.append(platform.require_context(token))
    assert role_has_permission(PlatformRole.VIEWER, PlatformPermission.VOICE_SPEAK)
    assert not role_has_permission(
        PlatformRole.VIEWER, PlatformPermission.VOICE_PROFILE_MANAGE
    )

    service = speech_service(platform, tmp_path, [FakeProvider()])
    created = service.create_speech(viewers[0], {"text": "Private owner fixture."})
    service.wait(created["operation_id"])
    with pytest.raises(PlatformContextError) as hidden:
        service.get_operation(viewers[1], created["operation_id"])
    assert hidden.value.code == "NOT_FOUND"
    with pytest.raises(PlatformContextError) as denied:
        service.create_profile(viewers[0], {"display_name": "Not authorized"})
    assert denied.value.code == "PERMISSION_DENIED"

    second_workspace = platform.store.create_workspace(
        org.org_id, "Second Workspace", owner_ctx.user_id
    )
    workspace_token = secrets.token_urlsafe(18)
    platform.store.create_session(
        owner_ctx.user_id,
        workspace_token,
        org_id=org.org_id,
        workspace_id=second_workspace.workspace_id,
        role=PlatformRole.OWNER.value,
    )
    workspace_ctx = platform.require_context(workspace_token)
    with pytest.raises(PlatformContextError) as workspace_hidden:
        service.get_operation(workspace_ctx, created["operation_id"])
    assert workspace_hidden.value.code == "NOT_FOUND"

    foreign_org = platform.store.create_org("Foreign", owner_ctx.user_id)
    foreign_workspace = platform.store.create_workspace(
        foreign_org.org_id, "Foreign Workspace", owner_ctx.user_id
    )
    foreign_token = secrets.token_urlsafe(18)
    platform.store.create_session(
        owner_ctx.user_id,
        foreign_token,
        org_id=foreign_org.org_id,
        workspace_id=foreign_workspace.workspace_id,
        role=PlatformRole.OWNER.value,
    )
    foreign_ctx = platform.require_context(foreign_token)
    with pytest.raises(PlatformContextError) as tenant_hidden:
        service.get_operation(foreign_ctx, created["operation_id"])
    assert tenant_hidden.value.code == "NOT_FOUND"
    service.shutdown()


def test_macos_provider_uses_safe_argv_and_voxcpm_is_explicit_and_offline(
    platform_ctx, tmp_path, monkeypatch
):
    _, ctx = platform_ctx
    say = tmp_path / "say"
    say.write_text("#!/bin/sh\n")
    say.chmod(0o755)
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[-1] == "?":
            return SimpleNamespace(ok=True, stdout="Daniel en_GB # fixture\n")
        output = Path(argv[argv.index("-o") + 1])
        output.write_bytes(b"FORM\x00\x00\x00\x04AIFF")
        return SimpleNamespace(
            ok=True,
            stdout="",
            stderr="",
            cancellation_confirmed=False,
            timeout_detected=False,
        )

    system = MacOSSystemSpeechProvider(
        executable=say, runner=runner, system_name="Darwin"
    )
    request = SpeechRequest.from_payload(
        ctx,
        {
            "text": 'Hello; touch "/tmp/not-created"',
            "voice_id": "Daniel",
            "provider": "macos_system",
        },
    )
    result = system.synthesize(
        request, tmp_path / "speech_fixture.aiff", cancel_check=lambda: False
    )
    assert result.artifact_bytes == 12
    synthesis_argv = calls[-1][0]
    assert synthesis_argv[0] == str(say)
    assert synthesis_argv[-1] == request.text
    assert all("shell" not in kwargs for _, kwargs in calls)

    monkeypatch.setenv("SAATHI_VOXCPM_STARTUP_TIMEOUT", "not-a-number")
    config = VoxCPMConfig.from_env()
    assert config.enabled is False
    vox = VoxCPMSpeechProvider(config)
    assert vox.health()["state"] == "disabled"
    assert vox.capabilities()["cloning_state"] == "CAPABILITY_DISABLED"
    assert "ne" not in vox.capabilities()["languages"]


def test_voxcpm_gguf_adapter_uses_explicit_paths_and_maps_style_locally(
    platform_ctx, tmp_path
):
    _, ctx = platform_ctx
    executable = tmp_path / "voxcpm2-cli"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    base = tmp_path / "base.gguf"
    acoustic = tmp_path / "acoustic.gguf"
    base.write_bytes(b"fixture")
    acoustic.write_bytes(b"fixture")
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        output = Path(argv[argv.index("-o") + 1])
        output.write_bytes(b"RIFF\x04\x00\x00\x00WAVE")
        return SimpleNamespace(
            ok=True,
            cancellation_confirmed=False,
            timeout_detected=False,
        )

    provider = VoxCPMSpeechProvider(
        VoxCPMConfig(
            enabled=True,
            mode="gguf_metal",
            executable=str(executable),
            base_model_path=str(base),
            acoustic_model_path=str(acoustic),
        ),
        runner=runner,
    )
    request = SpeechRequest.from_payload(
        ctx,
        {
            "text": "Good morning.",
            "output_format": "wav",
            "style": "Warm and calm.",
            "provider": "voxcpm",
        },
    )
    result = provider.synthesize(
        request, tmp_path / "vox_fixture.wav", cancel_check=lambda: False
    )
    assert result.provider == "voxcpm"
    assert provider.health()["state"] == "ready_unverified"
    argv = calls[0][0]
    assert argv[0] == str(executable)
    assert "(Warm and calm.)Good morning." in argv
    assert str(base) in argv and str(acoustic) in argv
    assert calls[0][1].get("timeout_sec") == 180.0
