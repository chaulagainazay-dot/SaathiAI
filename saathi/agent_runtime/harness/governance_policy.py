"""FM-I4 — Immutable harness resource, admission, queue, and timeout policies.

Policies never grant execution permission. Capability declarations cannot raise limits.
Scope overrides may only tighten (never loosen) base policy unless explicitly constructed.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional
import time


POLICY_VERSION = "1.0"


def _pos_int(name: str, value: int, *, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be int")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value


def _nonneg_int(name: str, value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be int")
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}")
    return value


@dataclass(frozen=True)
class HarnessTimeoutPolicy:
    """Distinct timeout types — no ambiguous generic timeout field."""

    max_queue_wait_seconds: int = 60
    max_startup_seconds: int = 30
    max_turn_seconds: int = 120
    max_session_duration_seconds: int = 600
    max_idle_seconds: int = 120
    max_tool_proposal_wait_seconds: int = 60
    max_approval_wait_seconds: int = 300
    cancellation_grace_seconds: int = 10
    max_close_seconds: int = 30

    def __post_init__(self) -> None:
        for name in (
            "max_queue_wait_seconds",
            "max_startup_seconds",
            "max_turn_seconds",
            "max_session_duration_seconds",
            "max_idle_seconds",
            "max_tool_proposal_wait_seconds",
            "max_approval_wait_seconds",
            "cancellation_grace_seconds",
            "max_close_seconds",
        ):
            _pos_int(name, getattr(self, name))


@dataclass(frozen=True)
class HarnessQueuePolicy:
    """Bounded in-process queue policy with fairness parameters."""

    max_queued_sessions_global: int = 32
    max_queued_sessions_per_org: int = 8
    max_queued_sessions_per_workspace: int = 4
    # Fairness: round-robin by organization; age promotion after N seconds
    age_promotion_seconds: int = 30
    # Priority ceiling: operator priority cannot exceed this (0=normal, higher=more priority)
    priority_ceiling: int = 5
    # Weighted RR: higher fairness_weight means more share (bounded 1..10)
    default_fairness_weight: int = 1
    policy_version: str = POLICY_VERSION

    def __post_init__(self) -> None:
        _pos_int("max_queued_sessions_global", self.max_queued_sessions_global)
        _pos_int("max_queued_sessions_per_org", self.max_queued_sessions_per_org)
        _pos_int("max_queued_sessions_per_workspace", self.max_queued_sessions_per_workspace)
        _pos_int("age_promotion_seconds", self.age_promotion_seconds)
        _nonneg_int("priority_ceiling", self.priority_ceiling)
        _pos_int("default_fairness_weight", self.default_fairness_weight)
        if self.default_fairness_weight > 10:
            raise ValueError("default_fairness_weight must be <= 10")
        if self.priority_ceiling > 100:
            raise ValueError("priority_ceiling must be <= 100")


@dataclass(frozen=True)
class HarnessAdmissionPolicy:
    max_active_sessions_global: int = 8
    max_active_sessions_per_org: int = 4
    max_active_sessions_per_workspace: int = 2
    max_active_sessions_per_harness: int = 8
    # Multiple sessions per run allowed unless controller tightens policy
    allow_multiple_sessions_per_run: bool = True
    reject_unhealthy_harness: bool = True
    reject_quarantined_harness: bool = True
    policy_version: str = POLICY_VERSION

    def __post_init__(self) -> None:
        _pos_int("max_active_sessions_global", self.max_active_sessions_global)
        _pos_int("max_active_sessions_per_org", self.max_active_sessions_per_org)
        _pos_int("max_active_sessions_per_workspace", self.max_active_sessions_per_workspace)
        _pos_int("max_active_sessions_per_harness", self.max_active_sessions_per_harness)


@dataclass(frozen=True)
class HarnessResourcePolicy:
    """Combined resource governance policy for harness sessions (internal proof)."""

    admission: HarnessAdmissionPolicy = HarnessAdmissionPolicy()
    queue: HarnessQueuePolicy = HarnessQueuePolicy()
    timeouts: HarnessTimeoutPolicy = HarnessTimeoutPolicy()
    # Per-session budgets (session-level; cannot be raised by harness capabilities)
    max_turns_per_session: int = 8
    max_events_per_session: int = 256
    max_output_chars_per_session: int = 8192
    max_logical_tokens_per_session: int = 4096
    max_tool_proposals_per_session: int = 16
    max_retries_per_operation: int = 2
    stale_cleanup_interval_seconds: int = 60
    policy_version: str = POLICY_VERSION
    created_at: float = 0.0

    def __post_init__(self) -> None:
        _pos_int("max_turns_per_session", self.max_turns_per_session)
        _pos_int("max_events_per_session", self.max_events_per_session)
        _pos_int("max_output_chars_per_session", self.max_output_chars_per_session)
        _pos_int("max_logical_tokens_per_session", self.max_logical_tokens_per_session)
        _pos_int("max_tool_proposals_per_session", self.max_tool_proposals_per_session)
        _nonneg_int("max_retries_per_operation", self.max_retries_per_operation)
        _pos_int("stale_cleanup_interval_seconds", self.stale_cleanup_interval_seconds)
        if self.created_at == 0.0:
            object.__setattr__(self, "created_at", time.time())

    @staticmethod
    def default() -> "HarnessResourcePolicy":
        return HarnessResourcePolicy()

    def tightened(self, **kwargs: object) -> "HarnessResourcePolicy":
        """Return a policy that only tightens numeric limits (never loosens)."""
        base = self
        # Nested dataclasses handled by full replace of admission/queue/timeouts if provided
        new = replace(base, **kwargs)  # type: ignore[arg-type]
        # Validate tighten on scalar fields
        for field in (
            "max_turns_per_session",
            "max_events_per_session",
            "max_output_chars_per_session",
            "max_logical_tokens_per_session",
            "max_tool_proposals_per_session",
            "max_retries_per_operation",
        ):
            if getattr(new, field) > getattr(base, field):
                raise ValueError(f"policy override cannot loosen {field}")
        if new.admission.max_active_sessions_global > base.admission.max_active_sessions_global:
            raise ValueError("cannot loosen max_active_sessions_global")
        if new.queue.max_queued_sessions_global > base.queue.max_queued_sessions_global:
            raise ValueError("cannot loosen max_queued_sessions_global")
        return new


# ── Decision / state enums ──────────────────────────────────────────────────


class AdmissionDecision(str):
    ADMIT_NOW = "ADMIT_NOW"
    QUEUE = "QUEUE"
    REJECT_CAPACITY = "REJECT_CAPACITY"
    REJECT_POLICY = "REJECT_POLICY"
    REJECT_SCOPE = "REJECT_SCOPE"
    REJECT_RESOURCE_BUDGET = "REJECT_RESOURCE_BUDGET"
    REJECT_QUARANTINED_HARNESS = "REJECT_QUARANTINED_HARNESS"
    REJECT_TERMINAL_RUN = "REJECT_TERMINAL_RUN"
    REJECT_STALE_REQUEST = "REJECT_STALE_REQUEST"
    REJECT_UNHEALTHY = "REJECT_UNHEALTHY"
    REJECT_DUPLICATE_RUN = "REJECT_DUPLICATE_RUN"


class QueueEntryState(str):
    QUEUED = "QUEUED"
    ELIGIBLE = "ELIGIBLE"
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    QUARANTINED = "QUARANTINED"


class ReservationState(str):
    HELD = "HELD"
    RELEASED = "RELEASED"
    LEAKED_RECONCILED = "LEAKED_RECONCILED"


class LimitViolationKind(str):
    TURNS = "max_turns_per_session"
    EVENTS = "max_events_per_session"
    OUTPUT = "max_output_chars_per_session"
    TOKENS = "max_logical_tokens_per_session"
    TOOL_PROPOSALS = "max_tool_proposals_per_session"
    RETRIES = "max_retries_per_operation"
    SESSION_DURATION = "max_session_duration_seconds"
    IDLE = "max_idle_seconds"
    APPROVAL_WAIT = "max_approval_wait_seconds"
    QUEUE_WAIT = "max_queue_wait_seconds"
    CANCEL_ACK = "cancellation_grace_seconds"
