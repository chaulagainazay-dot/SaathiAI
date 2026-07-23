"""M48.2 — structured agent-runtime error codes (safe, machine-readable)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class AgentRuntimeErrorCode:
    VALIDATION_FAILED = "VALIDATION_FAILED"
    UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
    AUTHORITY_DENIED = "AUTHORITY_DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_INVALID = "APPROVAL_INVALID"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_REVOKED = "APPROVAL_REVOKED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    CONFIGURATION_MISSING = "CONFIGURATION_MISSING"
    PROHIBITED_OPERATION = "PROHIBITED_OPERATION"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    RUNTIME_UNAVAILABLE = "RUNTIME_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Map M48.1 contract codes → public API codes
_CONTRACT_TO_PUBLIC = {
    "MISSING_OBJECTIVE": AgentRuntimeErrorCode.VALIDATION_FAILED,
    "MISSING_RUN_ID": AgentRuntimeErrorCode.VALIDATION_FAILED,
    "INVALID_REQUEST": AgentRuntimeErrorCode.VALIDATION_FAILED,
    "INVALID_TIMEOUT": AgentRuntimeErrorCode.VALIDATION_FAILED,
    "UNBOUNDED_RETRY": AgentRuntimeErrorCode.VALIDATION_FAILED,
    "SECRET_FIELD": AgentRuntimeErrorCode.VALIDATION_FAILED,
    "UNKNOWN_CAPABILITY": AgentRuntimeErrorCode.UNKNOWN_CAPABILITY,
    "UNKNOWN_AUTHORITY": AgentRuntimeErrorCode.AUTHORITY_DENIED,
    "FINANCIAL_EXECUTION_PROHIBITED": AgentRuntimeErrorCode.PROHIBITED_OPERATION,
    "MISSING_APPROVAL": AgentRuntimeErrorCode.APPROVAL_REQUIRED,
    "EXPIRED_APPROVAL": AgentRuntimeErrorCode.APPROVAL_EXPIRED,
    "REVOKED_APPROVAL": AgentRuntimeErrorCode.APPROVAL_REVOKED,
    "PROVIDER_UNAVAILABLE": AgentRuntimeErrorCode.PROVIDER_UNAVAILABLE,
    "INVALID_TRANSITION": AgentRuntimeErrorCode.INVALID_STATE_TRANSITION,
    "TERMINAL_RESTART": AgentRuntimeErrorCode.INVALID_STATE_TRANSITION,
}


def public_code_for_contract(code: str) -> str:
    return _CONTRACT_TO_PUBLIC.get(code, AgentRuntimeErrorCode.VALIDATION_FAILED)


@dataclass
class AgentRunError(Exception):
    """Fail-closed structured error. Never carries secrets."""

    code: str
    message: str
    violations: list[dict] = field(default_factory=list)
    run_id: str = ""
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": self.code,
            "message": self.message,
            "violations": self.violations,
            "run_id": self.run_id or None,
            "details": self.details,
        }
