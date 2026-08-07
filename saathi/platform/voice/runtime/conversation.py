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
)


class ConversationRuntime:
    """Maintains ConversationSession lifecycle and transcript history.

    Intelligence is provided by ConversationService (preferred) or explicit
    inject hooks for tests. Deterministic templates are NOT used as model
    intelligence on the default production path.
    """

    def __init__(
        self,
        *,
        chat_fn: Callable[[ConversationSession, str], str] | None = None,
        stream_fn: Callable[[ConversationSession, str], Any] | None = None,
        conversation_service=None,
        platform_ctx_fn: Callable[[], Any] | None = None,
    ):
        self._chat_fn = chat_fn
        self._stream_fn = stream_fn
        self._conversation_service = conversation_service
        self._platform_ctx_fn = platform_ctx_fn
        self._active_request_ids: list[str] = []

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

    def bind_conversation_service(self, service, platform_ctx_fn=None) -> None:
        self._conversation_service = service
        if platform_ctx_fn is not None:
            self._platform_ctx_fn = platform_ctx_fn

    def cancel_active_generation(self) -> None:
        service = self._conversation_service
        if service is None:
            return
        for request_id in list(self._active_request_ids):
            try:
                service.cancel(request_id)
            except Exception:
                pass
        self._active_request_ids.clear()

    def generate_reply(self, session: ConversationSession, user_text: str) -> str:
        if self._chat_fn is not None:
            return (self._chat_fn(session, user_text) or "").strip()
        parts = list(self.stream_reply(session, user_text))
        return (parts[-1] if parts else "").strip()

    def stream_reply(self, session: ConversationSession, user_text: str):
        if self._stream_fn is not None:
            yield from self._stream_fn(session, user_text)
            return
        service = self._conversation_service
        if service is not None and self._platform_ctx_fn is not None:
            ctx = self._platform_ctx_fn()
            last = ""
            for assembled in service.stream_for_voice(ctx, session, user_text):
                if assembled and assembled != last:
                    last = assembled
                    yield assembled
            return
        # Fail closed — never present deterministic templates as model intelligence.
        return
