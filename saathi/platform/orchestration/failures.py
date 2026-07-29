"""Deterministic failure classification and bounded retry policy."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import (
    MAX_RETRIES_CEILING,
    MAX_RETRIES_DEFAULT,
    FailureAction,
    FailureClass,
)

# Failure classes that must never auto-retry
NO_AUTO_RETRY = frozenset(
    {
        FailureClass.AUTHORIZATION_FAILED,
        FailureClass.SECURITY_GATE,
        FailureClass.INVALID_PLAN,
        FailureClass.APPROVAL_DENIED,
        FailureClass.APPROVAL_EXPIRED,
        FailureClass.CERTIFICATION_FAILED,
        FailureClass.RECOVERY_MISMATCH,
    }
)

# Map error codes / messages to failure classes
_CODE_MAP: list[tuple[tuple[str, ...], FailureClass]] = [
    (("PERMISSION_DENIED", "ANONYMOUS", "MEMBERSHIP_REVOKED", "BINDING_"), FailureClass.AUTHORIZATION_FAILED),
    (("APPROVAL_DENIED", "APPROVAL_REJECTED"), FailureClass.APPROVAL_DENIED),
    (("APPROVAL_EXPIRED", "APPROVAL_REPLAY"), FailureClass.APPROVAL_EXPIRED),
    (("PROHIBITED", "FINANCIAL_EXECUTION", "SECURITY", "TRADING"), FailureClass.SECURITY_GATE),
    (("VALIDATION_FAILED", "INVALID_PLAN", "INVALID_STATE"), FailureClass.INVALID_PLAN),
    (("STALE", "CONTEXT_CONTRADICTORY"), FailureClass.STALE_CONTEXT),
    (("RECOVERY", "CHECKPOINT_MISMATCH"), FailureClass.RECOVERY_MISMATCH),
    (("RESOURCE", "BUDGET", "EXHAUSTED", "QUEUE"), FailureClass.RESOURCE_EXHAUSTED),
    (("TIMEOUT", "TIMED_OUT"), FailureClass.TIMEOUT),
    (("EVIDENCE",), FailureClass.EVIDENCE_MISSING),
    (("CERTIF",), FailureClass.CERTIFICATION_FAILED),
    (("PROVIDER", "MODEL_NOT", "UNAVAILABLE", "CONNECTION"), FailureClass.TRANSIENT_PROVIDER),
    (("TOOL_", "ADAPTER", "GATEWAY"), FailureClass.TRANSIENT_TOOL),
    (("DEPENDENCY", "BLOCKED_EXTERNAL"), FailureClass.EXTERNAL_INPUT_REQUIRED),
]


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = MAX_RETRIES_DEFAULT
    backoff_seconds: float = 1.0
    retryable_classes: tuple[str, ...] = (
        FailureClass.TRANSIENT_PROVIDER.value,
        FailureClass.TRANSIENT_TOOL.value,
        FailureClass.TIMEOUT.value,
    )
    cancel_on_non_retryable: bool = True
    evidence_per_attempt: bool = True
    terminal_on_exhaustion: str = "FAILED"

    def allows(self, failure_class: str | FailureClass) -> bool:
        fc = FailureClass(failure_class) if not isinstance(failure_class, FailureClass) else failure_class
        if fc in NO_AUTO_RETRY:
            return False
        return fc.value in self.retryable_classes

    def to_public(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "backoff_seconds": self.backoff_seconds,
            "retryable_classes": list(self.retryable_classes),
            "cancel_on_non_retryable": self.cancel_on_non_retryable,
            "evidence_per_attempt": self.evidence_per_attempt,
            "terminal_on_exhaustion": self.terminal_on_exhaustion,
            "infinite_retry": False,
        }


class FailureClassifier:
    def classify(
        self,
        *,
        error_code: str = "",
        message: str = "",
        outcome: str = "",
    ) -> FailureClass:
        blob = f"{error_code} {message} {outcome}".upper()
        if not blob.strip():
            return FailureClass.UNKNOWN
        for markers, fc in _CODE_MAP:
            if any(m in blob for m in markers):
                return fc
        return FailureClass.UNKNOWN

    def action_for(self, failure_class: FailureClass | str) -> FailureAction:
        fc = (
            FailureClass(failure_class)
            if not isinstance(failure_class, FailureClass)
            else failure_class
        )
        mapping = {
            FailureClass.TRANSIENT_PROVIDER: FailureAction.BACKOFF,
            FailureClass.TRANSIENT_TOOL: FailureAction.RETRY,
            FailureClass.TIMEOUT: FailureAction.RETRY,
            FailureClass.DEPENDENCY_FAILED: FailureAction.CANCEL_DEPENDENTS,
            FailureClass.APPROVAL_DENIED: FailureAction.FAIL_CLOSED,
            FailureClass.APPROVAL_EXPIRED: FailureAction.REQUEST_APPROVAL,
            FailureClass.AUTHORIZATION_FAILED: FailureAction.FAIL_CLOSED,
            FailureClass.INVALID_PLAN: FailureAction.FAIL_CLOSED,
            FailureClass.STALE_CONTEXT: FailureAction.REPLAN,
            FailureClass.RECOVERY_MISMATCH: FailureAction.FAIL_CLOSED,
            FailureClass.RESOURCE_EXHAUSTED: FailureAction.PAUSE,
            FailureClass.SECURITY_GATE: FailureAction.FAIL_CLOSED,
            FailureClass.EVIDENCE_MISSING: FailureAction.REQUEST_USER_INPUT,
            FailureClass.CERTIFICATION_FAILED: FailureAction.FAIL_CLOSED,
            FailureClass.EXTERNAL_INPUT_REQUIRED: FailureAction.REQUEST_USER_INPUT,
            FailureClass.UNKNOWN: FailureAction.ESCALATE,
        }
        return mapping.get(fc, FailureAction.FAIL_CLOSED)

    def default_retry_policy(self, max_attempts: int | None = None) -> RetryPolicy:
        n = max(0, min(int(max_attempts if max_attempts is not None else MAX_RETRIES_DEFAULT), MAX_RETRIES_CEILING))
        return RetryPolicy(max_attempts=n)
