"""Standardized conversation + voice events (published to the Event Fabric).

Every interaction becomes learning data — the Learning Runtime consumes these.
"""
from __future__ import annotations

from enum import Enum


class ConversationEvent(str, Enum):
    STARTED = "conversation.started"
    INTENT = "conversation.intent"
    COMPLETED = "conversation.completed"
    FAILED = "conversation.failed"


class VoiceEvent(str, Enum):
    STARTED = "voice.started"
    FINISHED = "voice.finished"
    FAILED = "voice.failed"
    INTERRUPTED = "voice.interrupted"


def emit(bus, event, payload: dict | None = None) -> None:
    """Publish to an injected Event Fabric; never let telemetry break a call."""
    if bus is None:
        return
    try:
        bus.publish_sync(event.value, payload or {})
    except Exception:
        pass
