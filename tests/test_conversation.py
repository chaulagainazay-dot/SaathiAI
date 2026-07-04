"""Conversation Engine (Phase 1.4) — flow, commands, interruption, adapters."""
import pytest

from saathi.infrastructure.conversation import (
    ConversationEngine, ConversationSession, SessionStore,
    ConversationEvent, VoiceEvent, KeyboardAdapter, ApiAdapter, TelegramAdapter,
    VoiceAdapter, diagnostics,
)
from saathi.infrastructure.conversation.speech import EchoStt, SilentTts


class FakeBus:
    def __init__(self): self.events = []
    def publish_sync(self, name, payload): self.events.append((name, payload))


def brain(message, session):
    return f"brain:{message}"


def commands(message, session):
    return "CMD_OK" if message.startswith("/brief") else None


def _engine(**kw):
    kw.setdefault("brain", brain)
    kw.setdefault("commands", commands)
    return ConversationEngine(**kw)


# ── core flow ────────────────────────────────────────────────────────────────
def test_chat_routes_to_brain_and_records_history():
    bus = FakeBus()
    eng = _engine(bus=bus)
    s = eng.session("web:1", device="api")
    reply = eng.handle(s, message="Today's revenue?")
    assert reply.text == "brain:Today's revenue?" and reply.intent == "chat"
    assert [h["role"] for h in s.history] == ["user", "assistant"]
    names = [e[0] for e in bus.events]
    assert ConversationEvent.STARTED.value in names
    assert ConversationEvent.INTENT.value in names
    assert ConversationEvent.COMPLETED.value in names


def test_command_routes_to_command_layer_not_brain():
    calls = []
    eng = _engine(brain=lambda m, s: calls.append(m) or "brain")
    s = eng.session("web:2")
    reply = eng.handle(s, message="/brief")
    assert reply.text == "CMD_OK" and reply.intent == "command"
    assert reply.command == "/brief" and s.last_command == "/brief"
    assert calls == []                              # brain never invoked


def test_empty_message_raises_and_emits_failed():
    bus = FakeBus()
    eng = _engine(bus=bus)
    s = eng.session("web:3")
    with pytest.raises(ValueError):
        eng.handle(s, message="")
    assert ConversationEvent.FAILED.value in [e[0] for e in bus.events]


def test_session_persists_across_turns():
    eng = _engine()
    s1 = eng.session("web:4")
    eng.handle(s1, message="hello")
    s2 = eng.session("web:4")                        # same id → same session
    assert s2 is s1 and len(s2.history) == 2


# ── voice pipeline ───────────────────────────────────────────────────────────
def test_audio_input_transcribes_then_routes():
    bus = FakeBus()
    voice = VoiceAdapter(stt=EchoStt(), tts=SilentTts(), bus=bus)
    eng = _engine(voice=voice, bus=bus)
    s = eng.session("voice:1", device="voice")
    reply = eng.handle(s, audio="what is my revenue")   # EchoStt echoes the text
    assert reply.text == "brain:what is my revenue"
    assert VoiceEvent.STARTED.value in [e[0] for e in bus.events]
    assert VoiceEvent.FINISHED.value in [e[0] for e in bus.events]


def test_speak_returns_synthesized_bytes():
    voice = VoiceAdapter(stt=EchoStt(), tts=SilentTts())
    eng = _engine(voice=voice)
    s = eng.session("voice:2", device="voice")
    reply = eng.handle(s, message="hi there", speak=True)
    assert reply.speech == b"brain:hi there"           # SilentTts encodes text


def test_audio_without_voice_adapter_fails():
    eng = _engine()                                    # no voice
    with pytest.raises(Exception):
        eng.handle(eng.session("x"), audio="hello")


def test_voice_interrupt_sets_flag_and_emits():
    bus = FakeBus()
    voice = VoiceAdapter(stt=EchoStt(), tts=SilentTts(), bus=bus)
    voice.interrupt()
    assert voice.interrupted is True
    assert VoiceEvent.INTERRUPTED.value in [e[0] for e in bus.events]


# ── adapters ─────────────────────────────────────────────────────────────────
def test_keyboard_adapter():
    eng = _engine()
    kb = KeyboardAdapter(eng)
    reply = kb.send("desk:1", "status?")
    assert reply.text == "brain:status?"
    assert eng.sessions.get("desk:1").device == "desktop"


def test_api_adapter_returns_dict():
    eng = _engine()
    out = ApiAdapter(eng).handle("mob:1", "hello", device="mobile")
    assert out["text"] == "brain:hello" and out["intent"] == "chat"
    assert out["session_id"] == "mob:1"


class FakeRegistry:
    def __init__(self): self.sent = []
    def execute(self, *, capability, connector_id, **payload):
        self.sent.append((capability, connector_id, payload)); return {"ok": True}


def test_telegram_adapter_delivers_via_registry():
    eng = _engine()
    reg = FakeRegistry()
    tg = TelegramAdapter(eng, registry=reg, trusted_chat="999")
    reply = tg.handle_update({"message": {"chat": {"id": 999}, "text": "hey"}})
    assert reply.text == "brain:hey"
    assert reg.sent[0][0] == "send_text" and reg.sent[0][2]["chat_id"] == "999"


def test_telegram_adapter_ignores_untrusted_chat():
    eng = _engine()
    reg = FakeRegistry()
    tg = TelegramAdapter(eng, registry=reg, trusted_chat="999")
    assert tg.handle_update({"message": {"chat": {"id": 111}, "text": "hi"}}) is None
    assert reg.sent == []                              # nothing delivered


# ── diagnostics ──────────────────────────────────────────────────────────────
def test_conversation_diagnostics_section():
    eng = _engine()
    eng.handle(eng.session("web:d"), message="x")
    voice = VoiceAdapter(stt=EchoStt(), tts=SilentTts())
    snap = diagnostics.snapshot(engine=eng, voice=voice)
    assert set(snap) >= {"voice", "stt", "tts", "wakeword", "sessions"}
    assert snap["stt"]["available"] is True and snap["sessions"] == 1
