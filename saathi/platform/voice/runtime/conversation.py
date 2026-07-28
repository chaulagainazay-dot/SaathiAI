"""ConversationRuntime — durable turn state for live voice sessions."""
from __future__ import annotations

from typing import Any, Callable

from saathi.platform.models import new_id
from saathi.platform.voice.models import VoiceValidationError

from .models import (
    CONVERSATION_TRANSITIONS,
    ConversationSession,
    ConversationState,
    InterruptionRecord,
    TranscriptEntry,
    TranscriptRole,
    yeti_system_preamble,
)


class ConversationRuntime:
    """Maintains ConversationSession lifecycle and transcript history.

    Chat generation is injected so production can use ChatEngine while tests
    stay deterministic. Never owns identity, RBAC, or SpeechService.
    """

    def __init__(
        self,
        *,
        chat_fn: Callable[[ConversationSession, str], str] | None = None,
        stream_fn: Callable[[ConversationSession, str], Any] | None = None,
    ):
        self._chat_fn = chat_fn
        self._stream_fn = stream_fn

    def transition(
        self, session: ConversationSession, target: ConversationState
    ) -> ConversationSession:
        current = ConversationState(session.state)
        if target == current:
            return session
        allowed = CONVERSATION_TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            raise VoiceValidationError(
                f"illegal conversation transition {current.value} -> {target.value}"
            )
        session.state = target.value
        if target is ConversationState.FAILED:
            session.error_category = session.error_category or "conversation_failed"
        if target is ConversationState.FINISHED:
            session.input_state = "idle"
            session.playback_state = "idle"
        return session

    def append_user(
        self,
        session: ConversationSession,
        text: str,
        *,
        provider: str = "",
        confidence: float = 0.0,
        partial: bool = False,
        now: float,
    ) -> TranscriptEntry:
        entry = TranscriptEntry(
            entry_id=new_id("vt_"),
            role=TranscriptRole.USER.value,
            text=text,
            is_partial=partial,
            is_final=not partial,
            provider=provider,
            confidence=confidence,
            created_at=now,
        )
        if partial:
            session.partial_user_transcript = text
        else:
            session.partial_user_transcript = ""
            session.transcript.append(entry)
        return entry

    def append_assistant(
        self,
        session: ConversationSession,
        text: str,
        *,
        partial: bool = False,
        speech_operation_id: str = "",
        now: float,
        interrupted: bool = False,
    ) -> TranscriptEntry:
        entry = TranscriptEntry(
            entry_id=new_id("vt_"),
            role=TranscriptRole.ASSISTANT.value,
            text=text,
            is_partial=partial,
            is_final=not partial,
            speech_operation_id=speech_operation_id,
            created_at=now,
            interrupted=interrupted,
        )
        if partial:
            session.partial_assistant_response = text
        else:
            session.partial_assistant_response = ""
            session.transcript.append(entry)
        return entry

    def record_interruption(
        self,
        session: ConversationSession,
        *,
        reason: str,
        from_state: str,
        to_state: str,
        preserved_text: str,
        now: float,
    ) -> InterruptionRecord:
        record = InterruptionRecord(
            interruption_id=new_id("vint_"),
            reason=reason[:80],
            from_state=from_state,
            to_state=to_state,
            preserved_text=(preserved_text or "")[:2000],
            created_at=now,
        )
        session.interruptions.append(record)
        return record

    def generate_reply(self, session: ConversationSession, user_text: str) -> str:
        if self._chat_fn is not None:
            return (self._chat_fn(session, user_text) or "").strip()
        return self._default_yeti_reply(session, user_text)

    def stream_reply(self, session: ConversationSession, user_text: str):
        if self._stream_fn is not None:
            yield from self._stream_fn(session, user_text)
            return
        # Deterministic chunked fallback for tests / offline hosts.
        full = self.generate_reply(session, user_text)
        if not full:
            return
        words = full.split()
        buf: list[str] = []
        for word in words:
            buf.append(word)
            if len(buf) >= 6 or word[-1:] in ".!?":
                yield " ".join(buf)
                buf = []
        if buf:
            yield " ".join(buf)

    @staticmethod
    def _default_yeti_reply(session: ConversationSession, user_text: str) -> str:
        mode = session.yeti_mode or "general"
        text = (user_text or "").strip()
        lowered = text.lower()
        if not text:
            return "I'm listening. What would you like to talk about?"
        if any(g in lowered for g in ("hello", "hi yeti", "hey yeti", "good morning")):
            return (
                "Hi, I'm Yeti. I'm here with you in this conversation. "
                "How can I help?"
            )
        if mode == "ielts":
            return (
                f"For IELTS practice, I heard: {text}. "
                "Let's keep the answer clear and structured. "
                "Would you like band tips for fluency or vocabulary next?"
            )
        if mode == "saathios_help":
            return (
                f"About SaathiOS: {text}. I can guide you through shell modules, "
                "approvals, and local workflows. What should we open first?"
            )
        if mode == "hcg":
            return (
                f"On HCG: {text}. I'll keep this practical and local-first. "
                "What outcome do you want next?"
            )
        if mode == "trading_guidance":
            return (
                f"Trading guidance only — not an order. You said: {text}. "
                "I can discuss risk education and process, but live trading stays "
                "under Trading Guardian with human approval."
            )
        # Include mode preamble influence without emotional manipulation.
        _ = yeti_system_preamble(mode)
        return (
            f"I heard you: {text}. I'm staying with this conversation and can "
            "continue naturally. What should we do next?"
        )
