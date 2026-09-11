"""Structured AgentHarness errors (fail-closed, no secrets)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


class HarnessErrorCode:
    INVALID_REQUEST = "INVALID_REQUEST"
    UNKNOWN_SESSION = "UNKNOWN_SESSION"
    INVALID_STATE = "INVALID_STATE"
    TERMINAL_SESSION = "TERMINAL_SESSION"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    PROTOCOL_VIOLATION = "PROTOCOL_VIOLATION"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    MALFORMED_PROPOSAL = "MALFORMED_PROPOSAL"
    MISSING_CORRELATION = "MISSING_CORRELATION"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVAL_DENIED = "APPROVAL_DENIED"
    APPROVAL_INVALID = "APPROVAL_INVALID"
    QUARANTINED = "QUARANTINED"
    CAPABILITY_NOT_GRANTED = "CAPABILITY_NOT_GRANTED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INTERNAL = "INTERNAL"


@dataclass
class HarnessError(Exception):
    """Fail-closed harness / controller error. Never carries secrets."""

    code: str
    message: str
    session_id: str = ""
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def to_dict(self) -> dict:
        return {
            "ok": False,
            "error": self.code,
            "message": self.message,
            "session_id": self.session_id or None,
            "details": dict(self.details),
        }
