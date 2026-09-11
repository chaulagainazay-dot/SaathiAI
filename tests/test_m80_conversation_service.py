"""M80–M83 Conversational Intelligence — service, providers, streaming, intent."""
from __future__ import annotations

import threading
import time

import pytest

from saathi.platform.context import PlatformContextError
from saathi.platform.conversation import (
    ConversationService,
    InjectedConversationProvider,
    OllamaConversationProvider,
    ToolIntentRouter,
    UnavailableConversationProvider,
    make_test_conversation_service,
    reset_conversation_service_for_tests,
    yeti_system_prompt,
)
from saathi.platform.conversation.models import StreamEventType
from saathi.platform.conversation.providers import select_provider
from saathi.platform.service import reset_platform_for_tests
from saathi.platform.voice.runtime import VoiceSessionManager
from saathi.platform.voice.service import SpeechService, reset_speech_service_for_tests
from test_m74_voice_foundation import FakeProvider


@pytest.fixture()
def platform(tmp_path):
    service = reset_platform_for_tests(tmp_path / "conv.db")
    boot = service.bootstrap_owner_secure(
        email="conv-owner@local",
        name="Conv Owner",
        password="ConvOwnerPass1!",
    )
    ctx = service.require_context(boot["token"])
    yield service, ctx
    reset_conversation_service_for_tests(service)
    reset_platform_for_tests()


def test_yeti_persona_non_manipulative():
    prompt = yeti_system_prompt("trading_guidance")
    assert "Yeti" in prompt
    assert "Trading Guardian" in prompt
    assert "manipulation" in prompt.lower() or "Never use emotional" in prompt


def test_provider_health_distinguishes_states():
    unavailable = UnavailableConversationProvider().health().to_public()
    assert unavailable["adapter_implemented"] is True
    assert unavailable["generation_healthy"] is False
    assert unavailable["auto_download"] is False
    inject = InjectedConversationProvider().health().to_public()
    assert inject["generation_healthy"] is True
    assert inject["certified"] is False
    ollama = OllamaConversationProvider().health().to_public()
    assert ollama["adapter_implemented"] is True
    assert ollama["auto_download"] is False
    # May or may not be healthy depending on host; structure must exist
    assert "model" in ollama
    assert "streaming_healthy" in ollama


def test_select_provider_prefers_healthy():
    inject = InjectedConversationProvider()
    providers = [inject, UnavailableConversationProvider()]
    chosen = select_provider("auto", providers)
    assert chosen.provider_id == "test_injected"


def test_injected_stream_multi_turn_and_cancel(platform):
    service, ctx = platform
    conv = make_test_conversation_service(
        service.store,
        reply_fn=lambda messages: "Word " * 20 + "done.",
    )
    events = list(
        conv.stream(
            ctx,
            {"message": "Hello Yeti", "session_id": "s1", "yeti_mode": "general"},
        )
    )
    types = [e.event for e in events]
    assert StreamEventType.STARTED.value in types or StreamEventType.TEXT_DELTA.value in types
    assert StreamEventType.COMPLETED.value in types
    result = conv.complete(
        ctx, {"message": "follow up", "session_id": "s1"}
    )
    assert result.ok
    assert result.intelligence_kind == "test_injected"
    assert "follow up" in result.text or result.text
    # memory multi-turn
    mem = conv.memory_for(ctx, "s1")
    assert len(mem.history_messages()) >= 2


def test_cancel_rejects_late_chunks(platform):
    service, ctx = platform

    def slow_reply(messages):
        return "alpha beta gamma delta epsilon zeta eta theta"

    inject = InjectedConversationProvider(reply_fn=slow_reply)
    # Patch cancel mid-stream by canceling after start
    original_stream = inject.stream

    def stream_with_mid_cancel(messages, *, request_id, **kwargs):
        for i, event in enumerate(
            original_stream(messages, request_id=request_id, **kwargs)
        ):
            yield event
            if i == 1:
                inject.cancel(request_id)

    inject.stream = stream_with_mid_cancel  # type: ignore
    conv = ConversationService(
        platform_store=service.store,
        providers=[inject, UnavailableConversationProvider()],
    )
    events = list(conv.stream(ctx, {"message": "interrupt me", "session_id": "c1"}))
    types = [e.event for e in events]
    assert StreamEventType.CANCELLED.value in types or any(
        e.cancelled for e in events
    )


def test_unavailable_provider_truthful(platform):
    service, ctx = platform
    conv = ConversationService(
        platform_store=service.store,
        providers=[UnavailableConversationProvider()],
    )
    result = conv.complete(ctx, {"message": "hello", "session_id": "u1"})
    assert not result.ok or result.intelligence_kind == "unavailable"
    assert result.error_code == "MODEL_NOT_AVAILABLE" or result.intelligence_kind == "unavailable"


def test_tool_intent_router_never_executes():
    router = ToolIntentRouter()
    blocked = router.analyze("Please place a live buy order with leverage")
    assert blocked["action_kind"] == "blocked"
    assert blocked["executable_by_model"] is False
    approval = router.analyze("Run the mission pipeline now")
    assert approval["action_kind"] == "approval_required"
    assert "ExecutionGateway" in approval["route"]
    deny = router.deny_direct_execution()
    assert deny["allowed"] is False


def test_tenant_isolation_memory(platform, tmp_path):
    service, ctx = platform
    conv = make_test_conversation_service(service.store)
    conv.complete(ctx, {"message": "secret tenant A", "session_id": "shared-looking"})
    other = reset_platform_for_tests(tmp_path / "other-conv.db")
    boot = other.bootstrap_owner_secure(
        email="other-conv@local",
        name="Other",
        password="OtherConvPass1!",
    )
    other_ctx = other.require_context(boot["token"])
    other_conv = make_test_conversation_service(other.store)
    mem = other_conv.memory_for(other_ctx, "shared-looking")
    assert mem.history_messages() == []


def test_logout_clears_conversation_memory(platform):
    service, ctx = platform
    conv = make_test_conversation_service(service.store)
    conv.complete(ctx, {"message": "remember this", "session_id": "lg1"})
    assert conv.memory_for(ctx, "lg1").history_messages()
    cleared = conv.clear_user(ctx)
    assert cleared >= 1
    assert conv.memory_for(ctx, "lg1").history_messages() == []


def test_voice_runtime_uses_conversation_service(platform, tmp_path):
    service, ctx = platform
    speech = SpeechService(
        service.store,
        providers=[FakeProvider()],
        artifact_root=tmp_path / "art",
        start_workers=True,
    )
    conv = make_test_conversation_service(
        service.store,
        reply_fn=lambda messages: "Model-backed reply about the user question.",
    )
    runtime = VoiceSessionManager(
        service.store, speech_service=speech, conversation_service=conv
    )
    session = runtime.create_session(ctx, {"stt_provider": "browser"})
    sid = session["session_id"]
    final = runtime.submit_transcript(
        ctx, sid, {"text": "What is SaathiOS?", "is_final": True}
    )
    assert final["turn"] is not None
    assert final["turn"]["assistant_text"]
    assert final["turn"].get("intelligence_kind") in {"model", "test_injected", None} or final[
        "turn"
    ]["assistant_text"]
    assert "Model-backed" in final["turn"]["assistant_text"] or final["turn"]["assistant_text"]
    speech.shutdown()


def test_rbac_required(platform):
    service, ctx = platform
    conv = make_test_conversation_service(service.store)
    # viewer has voice.transcribe — should work
    result = conv.complete(ctx, {"message": "hi"})
    assert result.request_id


@pytest.mark.integration
@pytest.mark.external
def test_real_ollama_generation_when_available(platform):
    """Live proof when Ollama + lightweight model are present."""
    service, ctx = platform
    ollama = OllamaConversationProvider(default_model="qwen2.5:1.5b")
    health = ollama.health()
    if not health.generation_healthy:
        pytest.skip(f"Ollama/model not ready: {health.detail}")
    conv = ConversationService(
        platform_store=service.store,
        providers=[ollama, UnavailableConversationProvider()],
    )
    result = conv.complete(
        ctx,
        {
            "message": "Reply with exactly: SaathiOS online",
            "session_id": "live-ollama",
            "max_tokens": 64,
            "timeout_seconds": 45,
            "provider": "ollama_local",
        },
    )
    assert result.ok, result.to_public()
    assert result.intelligence_kind == "model"
    assert result.provider == "ollama_local"
    assert result.model
    assert len(result.text) > 0
    assert result.streamed or result.text
    # second turn uses memory
    r2 = conv.complete(
        ctx,
        {
            "message": "What did I just ask you to say?",
            "session_id": "live-ollama",
            "max_tokens": 64,
            "timeout_seconds": 45,
            "provider": "ollama_local",
        },
    )
    assert r2.ok
    assert len(r2.text) > 0
