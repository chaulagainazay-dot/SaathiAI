"""ConversationEngine — one brain for every channel.

    reply = engine.handle(session, message="Cafeteria sold NPR 18,400 today.")
    reply = engine.handle(session, audio=wav_bytes, speak=True)

Same pipeline regardless of adapter:

    (audio → STT) → message → command? ─yes→ Command Router
                                       └no→ Executive Intelligence (LLM brain)
                              → response → (speak? → TTS) → Reply

Deterministic core with injected side-effects (brain, commands, voice, bus), so
the whole flow is testable with fakes — no model, no audio, no network.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .commands import default_commands
from .events import ConversationEvent, emit
from .session import ConversationSession, SessionStore


@dataclass
class Reply:
    text: str
    intent: str = "chat"                   # "command" | "chat"
    command: str | None = None
    speech: bytes | None = None            # set when speak=True and a voice adapter exists
    ui_events: list = field(default_factory=list)
    session_id: str = ""


# brain: (message, session) -> reply text
Brain = Callable[[str, ConversationSession], str]


def _default_brain(message: str, session: ConversationSession) -> str:
    """Executive Intelligence via the platform agent (lazy; heavy import)."""
    from saathi.agent import SaathiAgent
    agent = SaathiAgent()
    return agent.respond(message, session_id=session.session_id, speaker_verified=True)


class ConversationEngine:
    def __init__(self, *, brain: Brain | None = None, commands=None, voice=None,
                 bus=None, sessions: SessionStore | None = None):
        self._brain = brain or _default_brain
        self._commands = commands if commands is not None else default_commands
        self._voice = voice
        self._bus = bus
        self.sessions = sessions or SessionStore()

    def session(self, session_id: str, **defaults) -> ConversationSession:
        return self.sessions.get_or_create(session_id, **defaults)

    def handle(self, session: ConversationSession, *, message: str | None = None,
               audio=None, speak: bool = False) -> Reply:
        emit(self._bus, ConversationEvent.STARTED,
             {"session": session.session_id, "device": session.device})
        try:
            if audio is not None:
                if self._voice is None:
                    raise RuntimeError("no voice adapter configured for audio input")
                message = self._voice.listen(audio, locale=session.locale)
            if not message:
                raise ValueError("empty message")

            session.add("user", message)

            # 1. deterministic command layer first
            cmd_reply = self._commands(message, session) if self._commands else None
            if cmd_reply is not None:
                intent, command = "command", message.strip().split()[0]
                session.last_command = command
                text = cmd_reply
            else:
                # 2. fall through to Executive Intelligence
                emit(self._bus, ConversationEvent.INTENT,
                     {"session": session.session_id, "intent": "chat"})
                intent, command = "chat", None
                text = self._brain(message, session)

            session.add("assistant", text)
            speech = None
            if speak and self._voice is not None:
                speech = self._voice.speak(text, locale=session.locale)

            emit(self._bus, ConversationEvent.COMPLETED,
                 {"session": session.session_id, "intent": intent})
            return Reply(text=text, intent=intent, command=command,
                         speech=speech, session_id=session.session_id)
        except Exception as e:
            emit(self._bus, ConversationEvent.FAILED,
                 {"session": session.session_id, "error": str(e)})
            raise
