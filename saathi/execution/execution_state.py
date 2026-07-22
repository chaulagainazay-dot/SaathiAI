"""M17.22 universal execution states — deterministic, terminal-immutable.

Minimum lifecycle for every external action that passes through ExecutionGateway:

    Requested → Validated → (Denied | Approval Required | Approved)
    Approval Required → (Approved | Denied | Expired | Cancelled)
    Approved → Queued → Running → (Succeeded | Failed | Cancelled)
    Any pre-terminal → Cancelled | Expired (where allowed)

Terminal states are immutable; invalid transitions raise StateException.
"""
from __future__ import annotations

from enum import Enum

from saathi.execution.errors import StateException


class ExecutionState(str, Enum):
    """Authoritative execution lifecycle states (M17.22)."""

    REQUESTED = "requested"
    VALIDATED = "validated"
    DENIED = "denied"
    APPROVAL_REQUIRED = "approval_required"
    APPROVED = "approved"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


TERMINAL_STATES: frozenset[ExecutionState] = frozenset({
    ExecutionState.DENIED,
    ExecutionState.SUCCEEDED,
    ExecutionState.FAILED,
    ExecutionState.CANCELLED,
    ExecutionState.EXPIRED,
})


# Explicit allow-list. Anything not listed is rejected (fail closed).
_VALID: dict[ExecutionState, frozenset[ExecutionState]] = {
    ExecutionState.REQUESTED: frozenset({
        ExecutionState.VALIDATED,
        ExecutionState.DENIED,
        ExecutionState.EXPIRED,
        ExecutionState.CANCELLED,
    }),
    ExecutionState.VALIDATED: frozenset({
        ExecutionState.DENIED,
        ExecutionState.APPROVAL_REQUIRED,
        ExecutionState.APPROVED,
        ExecutionState.EXPIRED,
        ExecutionState.CANCELLED,
    }),
    ExecutionState.APPROVAL_REQUIRED: frozenset({
        ExecutionState.APPROVED,
        ExecutionState.DENIED,
        ExecutionState.EXPIRED,
        ExecutionState.CANCELLED,
    }),
    ExecutionState.APPROVED: frozenset({
        ExecutionState.QUEUED,
        ExecutionState.CANCELLED,
        ExecutionState.EXPIRED,
    }),
    ExecutionState.QUEUED: frozenset({
        ExecutionState.RUNNING,
        ExecutionState.CANCELLED,
        ExecutionState.EXPIRED,
        ExecutionState.FAILED,
    }),
    ExecutionState.RUNNING: frozenset({
        ExecutionState.SUCCEEDED,
        ExecutionState.FAILED,
        ExecutionState.CANCELLED,
    }),
    # Terminals: no outbound edges
    ExecutionState.DENIED: frozenset(),
    ExecutionState.SUCCEEDED: frozenset(),
    ExecutionState.FAILED: frozenset(),
    ExecutionState.CANCELLED: frozenset(),
    ExecutionState.EXPIRED: frozenset(),
}


def is_terminal(state: ExecutionState | str) -> bool:
    s = ExecutionState(state) if not isinstance(state, ExecutionState) else state
    return s in TERMINAL_STATES


def can_transition(from_state: ExecutionState | str, to_state: ExecutionState | str) -> bool:
    src = ExecutionState(from_state) if not isinstance(from_state, ExecutionState) else from_state
    dst = ExecutionState(to_state) if not isinstance(to_state, ExecutionState) else to_state
    if src in TERMINAL_STATES:
        return False
    return dst in _VALID.get(src, frozenset())


def assert_transition(from_state: ExecutionState | str, to_state: ExecutionState | str) -> None:
    """Reject invalid or terminal-mutating transitions."""
    src = ExecutionState(from_state) if not isinstance(from_state, ExecutionState) else from_state
    dst = ExecutionState(to_state) if not isinstance(to_state, ExecutionState) else to_state
    if src in TERMINAL_STATES:
        raise StateException(
            f"terminal state {src.value} is immutable; cannot transition to {dst.value}"
        )
    if not can_transition(src, dst):
        raise StateException(
            f"invalid execution state transition {src.value} → {dst.value}"
        )


def allowed_targets(from_state: ExecutionState | str) -> frozenset[ExecutionState]:
    src = ExecutionState(from_state) if not isinstance(from_state, ExecutionState) else from_state
    return _VALID.get(src, frozenset())
