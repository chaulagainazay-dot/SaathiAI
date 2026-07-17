"""M23 — Canonical chat stream event model.

Provider SDK stream objects never escape. SSE/API layers map to these events.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterator, Optional


class ChatStreamEventType(str, Enum):
    STREAM_STARTED = "stream_started"
    TEXT_DELTA = "text_delta"
    TOOL_CALL_REQUESTED = "tool_call_requested"
    TOOL_RESULT_RECEIVED = "tool_result_received"
    USAGE_UPDATE = "usage_update"
    STREAM_COMPLETED = "stream_completed"
    STREAM_CANCELLED = "stream_cancelled"
    STREAM_FAILED = "stream_failed"
    # Compatibility aliases used by existing SSE surface
    START = "start"  # maps to stream_started for wire compat
    DELTA = "delta"  # maps to text_delta
    DONE = "done"  # maps to stream_completed
    ERROR = "error"  # maps to stream_failed


@dataclass(frozen=True)
class ChatStreamEvent:
    event: ChatStreamEventType
    request_id: str = ""
    conversation_id: str = ""
    text: str = ""
    partial: bool = False
    usage: dict[str, Any] = field(default_factory=dict)
    message: Optional[dict[str, Any]] = None
    execution: Optional[dict[str, Any]] = None
    citations: Optional[list] = None
    error_code: str = ""
    error_detail: str = ""
    sequence: int = 0
    ts: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        """SSE-compatible payload (legacy event names preserved for clients)."""
        wire_name = {
            ChatStreamEventType.STREAM_STARTED: "start",
            ChatStreamEventType.TEXT_DELTA: "delta",
            ChatStreamEventType.STREAM_COMPLETED: "done",
            ChatStreamEventType.STREAM_FAILED: "error",
            ChatStreamEventType.STREAM_CANCELLED: "error",
            ChatStreamEventType.USAGE_UPDATE: "usage",
            ChatStreamEventType.TOOL_CALL_REQUESTED: "tool_call",
            ChatStreamEventType.TOOL_RESULT_RECEIVED: "tool_result",
        }.get(self.event, self.event.value)

        out: dict[str, Any] = {"event": wire_name, "request_id": self.request_id}
        if self.conversation_id:
            out["conversation_id"] = self.conversation_id
        if self.event is ChatStreamEventType.TEXT_DELTA:
            out["text"] = self.text
            if self.partial:
                out["partial"] = True
        if self.event is ChatStreamEventType.STREAM_COMPLETED:
            if self.message is not None:
                out["message"] = self.message
            if self.citations is not None:
                out["citations"] = self.citations
            if self.execution is not None:
                out["execution"] = self.execution
            if self.usage:
                out["usage"] = dict(self.usage)
        if self.event in (
            ChatStreamEventType.STREAM_FAILED,
            ChatStreamEventType.STREAM_CANCELLED,
        ):
            # Safe detail only — no raw provider body
            out["detail"] = (self.error_detail or self.error_code or "stream_failed")[:300]
            if self.error_code:
                out["code"] = self.error_code
            if self.partial:
                out["partial"] = True
        if self.event is ChatStreamEventType.USAGE_UPDATE and self.usage:
            out["usage"] = dict(self.usage)
        out["sequence"] = self.sequence
        return out

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["event"] = self.event.value
        # Strip raw text from telemetry exports when large
        return d

    def safe_telemetry(self) -> dict[str, Any]:
        return {
            "schema": "m23.chat_stream_event.v1",
            "event": self.event.value,
            "request_id": self.request_id,
            "conversation_id": self.conversation_id,
            "sequence": self.sequence,
            "partial": self.partial,
            "text_chars": len(self.text or ""),
            "error_code": self.error_code,
            "has_usage": bool(self.usage),
            # no raw text / message content
        }


def iter_text_deltas(
    full_text: str,
    *,
    request_id: str,
    conversation_id: str = "",
    words_per_chunk: int = 8,
    start_sequence: int = 1,
) -> Iterator[ChatStreamEvent]:
    """Compatibility streaming: split a completed response into ordered deltas.

    Does not introduce provider-level streaming; used when the path completes
    then delivers incrementally (existing API behavior).
    """
    words = (full_text or "").split(" ")
    seq = start_sequence
    if not words or (len(words) == 1 and words[0] == ""):
        return
    for i in range(0, len(words), words_per_chunk):
        chunk = " ".join(words[i : i + words_per_chunk])
        if i + words_per_chunk < len(words):
            chunk += " "
        yield ChatStreamEvent(
            event=ChatStreamEventType.TEXT_DELTA,
            request_id=request_id,
            conversation_id=conversation_id,
            text=chunk,
            partial=True,
            sequence=seq,
        )
        seq += 1


def stream_lifecycle(
    *,
    request_id: str,
    conversation_id: str = "",
    full_text: str = "",
    message: Optional[dict[str, Any]] = None,
    execution: Optional[dict[str, Any]] = None,
    citations: Optional[list] = None,
    usage: Optional[dict[str, Any]] = None,
    error: Optional[Exception] = None,
    cancelled: bool = False,
    words_per_chunk: int = 8,
) -> Iterator[ChatStreamEvent]:
    """Emit a complete ordered stream lifecycle for one chat turn."""
    seq = 0
    yield ChatStreamEvent(
        event=ChatStreamEventType.STREAM_STARTED,
        request_id=request_id,
        conversation_id=conversation_id,
        sequence=seq,
    )
    seq += 1

    if cancelled:
        yield ChatStreamEvent(
            event=ChatStreamEventType.STREAM_CANCELLED,
            request_id=request_id,
            conversation_id=conversation_id,
            error_code="cancelled",
            error_detail="request cancelled",
            partial=bool(full_text),
            sequence=seq,
        )
        return

    if error is not None:
        code = getattr(error, "code", None) or type(error).__name__
        detail = str(error)[:300]
        yield ChatStreamEvent(
            event=ChatStreamEventType.STREAM_FAILED,
            request_id=request_id,
            conversation_id=conversation_id,
            error_code=str(code)[:64],
            error_detail=detail,
            partial=bool(full_text),
            sequence=seq,
        )
        return

    for ev in iter_text_deltas(
        full_text,
        request_id=request_id,
        conversation_id=conversation_id,
        words_per_chunk=words_per_chunk,
        start_sequence=seq,
    ):
        yield ev
        seq = ev.sequence + 1

    if usage:
        yield ChatStreamEvent(
            event=ChatStreamEventType.USAGE_UPDATE,
            request_id=request_id,
            conversation_id=conversation_id,
            usage=dict(usage),
            sequence=seq,
        )
        seq += 1

    yield ChatStreamEvent(
        event=ChatStreamEventType.STREAM_COMPLETED,
        request_id=request_id,
        conversation_id=conversation_id,
        message=message,
        execution=execution,
        citations=citations,
        usage=dict(usage or {}),
        partial=False,
        sequence=seq,
    )


STREAM_EVENT_AUTHORITY = "saathi.chat.stream_events.ChatStreamEvent"
