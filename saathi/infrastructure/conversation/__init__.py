"""Conversation Engine (Phase 1.4) — one brain, many channels.

Voice is one adapter, not the layer. Every surface — Telegram, mobile, desktop,
API, voice — shares the same engine:

    audio→STT → message → command? → Command Router
                                   └→ Executive Intelligence
                         → response → (speak?→TTS) → Reply

    from saathi.infrastructure.conversation import ConversationEngine, ApiAdapter
    engine = ConversationEngine()
    reply = ApiAdapter(engine).handle("web:42", "Today's revenue?")
"""
from .engine import ConversationEngine, Reply, Brain
from .session import ConversationSession, SessionStore
from .events import ConversationEvent, VoiceEvent
from .adapters import KeyboardAdapter, ApiAdapter, TelegramAdapter, VoiceAdapter
from . import diagnostics


def default_engine(*, bus=None, voice=None) -> ConversationEngine:
    """Engine wired to the platform brain + command layer + Event Fabric."""
    if bus is None:
        try:
            from saathi.events import bus as bus
        except Exception:
            bus = None
    return ConversationEngine(bus=bus, voice=voice)


__all__ = [
    "ConversationEngine", "Reply", "Brain", "ConversationSession", "SessionStore",
    "ConversationEvent", "VoiceEvent", "KeyboardAdapter", "ApiAdapter",
    "TelegramAdapter", "VoiceAdapter", "diagnostics", "default_engine",
]
