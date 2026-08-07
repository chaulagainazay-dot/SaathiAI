"""M79 real-time Voice Runtime — lifecycle, STT, interrupt, RBAC, isolation."""
from __future__ import annotations

import io
import math
import struct
import wave

import pytest

from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformPermission, PlatformRole, role_has_permission
from saathi.platform.service import reset_platform_for_tests
from saathi.platform.voice.runtime import (
    AudioPlaybackController,
    ConversationRuntime,
    ConversationState,
    VoiceActivityDetector,
    VoiceInputService,
    VoiceSessionManager,
    reset_voice_runtime_for_tests,
)
from saathi.platform.voice.runtime.models import ConversationSession
from saathi.platform.voice.runtime.stt import (
    BrowserPassthroughSpeechRecognitionProvider,
    UnavailableSpeechRecognitionProvider,
    WhisperCompatibleSpeechRecognitionProvider,
    discover_stt_providers,
    select_stt_provider,
)
from saathi.platform.conversation import make_test_conversation_service
from saathi.platform.voice.service import SpeechService, reset_speech_service_for_tests
from test_m74_voice_foundation import FakeProvider


@pytest.fixture()
def platform(tmp_path):
    service = reset_platform_for_tests(tmp_path / "voice-runtime.db")
    boot = service.bootstrap_owner_secure(
        email="voice-runtime@local",
        name="Voice Runtime Owner",
        password="VoiceRuntimePass1!",
    )
    ctx = service.require_context(boot["token"])
    speech = SpeechService(
        service.store,
        providers=[FakeProvider(provider_id="macos_system")],
        artifact_root=tmp_path / "voice-artifacts",
        start_workers=True,
    )
    service._speech_service = speech
    # Injected conversation intelligence — not presented as a real model provider
    conv = make_test_conversation_service(
        service.store,
        reply_fn=lambda messages: (
            "Following up with context. "
            + next(
                (m["content"] for m in reversed(messages) if m.get("role") == "user"),
                "hello",
            )
        ),
    )
    service._conversation_service = conv
    runtime = VoiceSessionManager(
        service.store, speech_service=speech, conversation_service=conv
    )
    service._voice_runtime = runtime
    yield service, ctx, runtime, boot["token"]
    speech.shutdown()
    reset_speech_service_for_tests(service)
    reset_voice_runtime_for_tests(service)
    reset_platform_for_tests()


def _sine_wav(seconds: float = 0.3, rate: int = 16000, freq: float = 440.0) -> bytes:
    n = int(rate * seconds)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            sample = int(12000 * math.sin(2 * math.pi * freq * (i / rate)))
            frames += struct.pack("<h", sample)
        handle.writeframes(bytes(frames))
    return buf.getvalue()


def test_rbac_permissions_exist():
    assert role_has_permission(PlatformRole.VIEWER, PlatformPermission.VOICE_LISTEN)
    assert role_has_permission(PlatformRole.VIEWER, PlatformPermission.VOICE_TRANSCRIBE)
    assert role_has_permission(PlatformRole.VIEWER, PlatformPermission.VOICE_SESSION_READ)
    assert role_has_permission(PlatformRole.VIEWER, PlatformPermission.VOICE_SPEAK)


def test_vad_speech_start_and_reset():
    vad = VoiceActivityDetector()
    silence = [0.0] * 320
    speech = [0.5] * 1600
    r_silence = vad.process(silence)
    assert r_silence.speech_started is False
    r_speech = vad.process(speech)
    assert r_speech.speech_started is True or r_speech.speech_ms > 0
    vad.reset()
    r_after = vad.process(silence)
    assert r_after.speech_started is False


def test_input_service_lifecycle_and_cancel():
    svc = VoiceInputService(max_recording_seconds=2.0)
    snap = svc.start("toggle", permission_granted=True)
    assert snap["state"] in {"listening", "recording"}
    assert snap["loopback_only"] is True
    assert snap["background_recording"] is False
    assert snap["hidden_activation"] is False
    svc.ingest_pcm([0.2] * 320)
    cancelled = svc.cancel()
    assert cancelled["state"] == "cancelled"
    recovered = svc.restart_recovery()
    assert recovered["state"] == "idle"


def test_input_requires_permission():
    svc = VoiceInputService()
    snap = svc.start("push_to_talk", permission_granted=False)
    assert snap["state"] == "error"
    assert "permission" in snap["error"]


def test_input_modes():
    svc = VoiceInputService()
    for mode in ("push_to_talk", "hold_to_talk", "toggle"):
        snap = svc.start(mode, permission_granted=True)
        assert snap["mode"] == mode
        svc.cancel()
        svc.restart_recovery()


def test_stt_providers_discovery_no_auto_install():
    providers = discover_stt_providers()
    ids = {p["provider_id"] for p in providers}
    assert "unavailable" in ids
    assert "browser" in ids
    assert "whisper_compatible" in ids
    assert "macos_speech" in ids
    for provider in providers:
        assert provider.get("auto_install") is False
    unavailable = select_stt_provider("unavailable")
    assert isinstance(unavailable, UnavailableSpeechRecognitionProvider)
    browser = BrowserPassthroughSpeechRecognitionProvider()
    result = browser.accept_text("hello yeti", is_final=True)
    assert result.text == "hello yeti"
    assert result.provider == "browser"
    browser.cancel()
    cancelled = browser.accept_text("should cancel")
    assert cancelled.error_category == "cancelled"


def test_playback_prevents_overlap_and_queue_limit():
    ctl = AudioPlaybackController(max_queue=2)
    a = ctl.play(text="one", speech_operation_id="op1")
    b = ctl.play(text="two", speech_operation_id="op2")
    assert a.playback_id != b.playback_id
    assert ctl.current().playback_id == b.playback_id
    ctl.queue(text="q1")
    ctl.queue(text="q2")
    with pytest.raises(RuntimeError, match="queue limit"):
        ctl.queue(text="q3")
    ctl.cancel()
    assert ctl.state == "idle"
    assert ctl.current() is None


def test_session_create_listen_transcript_interrupt(platform):
    _service, ctx, runtime, _token = platform
    session = runtime.create_session(
        ctx,
        {
            "input_mode": "toggle",
            "stt_provider": "browser",
            "yeti_mode": "general",
            "voice_profile_id": "yeti_teacher",
        },
    )
    sid = session["session_id"]
    assert session["state"] == "IDLE"

    listening = runtime.start_listening(ctx, sid, mode="toggle", permission_granted=True)
    assert listening["state"] == "LISTENING"

    partial = runtime.submit_transcript(
        ctx,
        sid,
        {"text": "hello", "is_final": False, "partial": True, "confidence": 0.7},
    )
    assert partial["session"]["partial_user_transcript"] == "hello"
    assert partial["turn"] is None

    final = runtime.submit_transcript(
        ctx,
        sid,
        {"text": "hello yeti", "is_final": True, "partial": False, "confidence": 0.9},
    )
    assert final["turn"] is not None
    assert "assistant_text" in final["turn"]
    assert final["session"]["transcript"]
    roles = {t["role"] for t in final["session"]["transcript"]}
    assert "user" in roles
    assert "assistant" in roles

    session_obj = runtime._get_owned(ctx, sid)
    session_obj.state = ConversationState.RESPONDING.value
    session_obj.partial_assistant_response = "I was saying something long"
    runtime.repo.save_session(session_obj)

    interrupted = runtime.interrupt(ctx, sid, reason="barge_in")
    assert interrupted["state"] == "LISTENING"
    assert interrupted["interruptions"]
    assert interrupted["playback_state"] in {"idle", "cancelled"}


def test_tenant_isolation(platform, tmp_path):
    _service, ctx, runtime, _token = platform
    session = runtime.create_session(ctx, {"yeti_mode": "ielts"})
    sid = session["session_id"]

    other = reset_platform_for_tests(tmp_path / "other-runtime.db")
    boot = other.bootstrap_owner_secure(
        email="other@local",
        name="Other",
        password="OtherVoicePass1!",
    )
    other_ctx = other.require_context(boot["token"])
    other_runtime = VoiceSessionManager(other.store, speech_service=None)
    with pytest.raises(PlatformContextError):
        other_runtime.get_session(other_ctx, sid)


def test_cancel_finish_and_logout_cleanup(platform):
    _service, ctx, runtime, _token = platform
    session = runtime.create_session(ctx, {})
    sid = session["session_id"]
    runtime.start_listening(ctx, sid, permission_granted=True)
    runtime.cancel_input(ctx, sid)
    finished = runtime.finish_session(ctx, sid)
    assert finished["state"] == "FINISHED"

    runtime.create_session(ctx, {})
    cleared = runtime.clear_user_sessions(ctx)
    assert cleared >= 1
    listed = runtime.list_sessions(ctx)
    active = [s for s in listed if s["state"] not in {"FINISHED", "FAILED"}]
    assert active == []


def test_transcript_persistence_and_history(platform):
    _service, ctx, runtime, _token = platform
    session = runtime.create_session(ctx, {"yeti_mode": "saathios_help"})
    sid = session["session_id"]
    runtime.submit_transcript(
        ctx, sid, {"text": "How do I open Mission Control?", "is_final": True}
    )
    got = runtime.get_session(ctx, sid)
    assert any(t["role"] == "user" for t in got["transcript"])
    assert any(t["role"] == "assistant" for t in got["transcript"])


def test_conversation_runtime_fail_closed_without_service():
    """Default path must not emit deterministic templates as intelligence."""
    conv = ConversationRuntime()
    session = ConversationSession(
        session_id="s",
        organization_id="o",
        workspace_id="w",
        user_id="u",
        yeti_mode="trading_guidance",
    )
    assert conv.generate_reply(session, "Should I leverage 10x?") == ""


def test_audio_upload_path_without_stt_text(platform):
    _service, ctx, runtime, _token = platform
    session = runtime.create_session(ctx, {"stt_provider": "unavailable"})
    sid = session["session_id"]
    result = runtime.submit_audio(
        ctx,
        sid,
        _sine_wav(),
        content_type="audio/wav",
        sample_rate=16000,
    )
    # Unavailable STT yields empty transcript path (failed or empty)
    assert result["transcript"]["provider"] in {
        "unavailable",
        "macos_speech",
        "whisper_compatible",
    }


def test_health_flags(platform):
    _service, ctx, runtime, _token = platform
    health = runtime.health(ctx)
    assert health["background_recording"] is False
    assert health["hidden_activation"] is False
    assert health["loopback_only"] is True
    assert health["public_listeners"] is False
    assert health["auto_model_download"] is False


def test_whisper_adapter_no_download_claim():
    provider = WhisperCompatibleSpeechRecognitionProvider()
    health = provider.health()
    assert health["auto_install"] is False
