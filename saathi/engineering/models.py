"""M20.0 — Engineering backlog and task models.

Structured engineering work items for the governed Engineering Orchestrator.
Statuses and fields are deliberate; no free-form second mission engine.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ItemStatus(str, Enum):
    PROPOSED = "proposed"
    READY = "ready"
    BLOCKED = "blocked"
    SELECTED = "selected"
    IN_PROGRESS = "in_progress"
    VALIDATING = "validating"
    REPAIR_REQUIRED = "repair_required"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    STOPPED = "stopped"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset({
    ItemStatus.COMPLETED,
    ItemStatus.PARTIAL,
    ItemStatus.FAILED,
    ItemStatus.STOPPED,
    ItemStatus.CANCELLED,
})

ALLOWED_TRANSITIONS: dict[ItemStatus, frozenset[ItemStatus]] = {
    ItemStatus.PROPOSED: frozenset({
        ItemStatus.READY, ItemStatus.BLOCKED, ItemStatus.CANCELLED,
    }),
    ItemStatus.READY: frozenset({
        ItemStatus.SELECTED, ItemStatus.BLOCKED, ItemStatus.AWAITING_APPROVAL,
        ItemStatus.CANCELLED,
    }),
    ItemStatus.BLOCKED: frozenset({
        ItemStatus.READY, ItemStatus.CANCELLED, ItemStatus.FAILED,
    }),
    ItemStatus.SELECTED: frozenset({
        ItemStatus.IN_PROGRESS, ItemStatus.AWAITING_APPROVAL, ItemStatus.BLOCKED,
        ItemStatus.CANCELLED,
    }),
    ItemStatus.IN_PROGRESS: frozenset({
        ItemStatus.VALIDATING, ItemStatus.REPAIR_REQUIRED,
        ItemStatus.AWAITING_APPROVAL, ItemStatus.STOPPED, ItemStatus.FAILED,
        ItemStatus.PARTIAL, ItemStatus.COMPLETED,
    }),
    ItemStatus.VALIDATING: frozenset({
        ItemStatus.COMPLETED, ItemStatus.PARTIAL, ItemStatus.REPAIR_REQUIRED,
        ItemStatus.FAILED, ItemStatus.STOPPED, ItemStatus.AWAITING_APPROVAL,
    }),
    ItemStatus.REPAIR_REQUIRED: frozenset({
        ItemStatus.IN_PROGRESS, ItemStatus.FAILED, ItemStatus.STOPPED,
        ItemStatus.AWAITING_APPROVAL, ItemStatus.CANCELLED,
    }),
    ItemStatus.AWAITING_APPROVAL: frozenset({
        ItemStatus.READY, ItemStatus.SELECTED, ItemStatus.IN_PROGRESS,
        ItemStatus.CANCELLED, ItemStatus.STOPPED, ItemStatus.FAILED,
    }),
    ItemStatus.COMPLETED: frozenset(),
    ItemStatus.PARTIAL: frozenset({ItemStatus.READY, ItemStatus.CANCELLED}),
    ItemStatus.FAILED: frozenset({ItemStatus.READY, ItemStatus.CANCELLED}),
    ItemStatus.STOPPED: frozenset({ItemStatus.READY, ItemStatus.CANCELLED}),
    ItemStatus.CANCELLED: frozenset(),
}


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Priority(str, Enum):
    P0 = "p0"  # critical security / CI break
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"
    P4 = "p4"


class SessionPhase(str, Enum):
    INTAKE = "intake_complete"
    ARCHITECTURE_AUDIT = "architecture_audit_complete"
    IMPLEMENTATION_PLAN = "implementation_plan_complete"
    FIRST_CODE_SLICE = "first_code_slice_complete"
    FOCUSED_TESTS = "focused_tests_complete"
    SECURITY_TESTS = "security_tests_complete"
    BROAD_VALIDATION = "broad_validation_complete"
    COMMIT_CREATED = "commit_created"
    PUSH_VERIFIED = "push_verified"
    HANDOFF_UPDATED = "handoff_updated"


class SessionStatus(str, Enum):
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    STALLED = "stalled"
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    CRASHED = "crashed"
    STOPPED = "stopped"
    FAILED = "failed"
    USAGE_LIMIT = "usage_limit"
    AWAITING_APPROVAL = "awaiting_approval"
    # M20.4 supervised lifecycle outcomes
    PAUSED = "paused"
    BLOCKED = "blocked"
    TERMINATED = "terminated"
    QUARANTINED = "quarantined"


class ReadinessState(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"
    REQUIRES_APPROVAL = "requires_approval"
    DEGRADED = "degraded"
    UNSAFE = "unsafe"


class StopMode(str, Enum):
    GRACEFUL = "graceful_stop"
    PAUSE_APPROVAL = "pause_for_approval"
    TERMINATE = "terminate"
    QUARANTINE = "quarantine_result"
    MARK_BLOCKED = "mark_blocked"
    MARK_FAILED = "mark_failed"


class Verdict(str, Enum):
    READY = "ready"
    PILOT_READY = "pilot_ready"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"
    VALIDATION_PENDING = "validation_pending"


# Recoverable failure categories for retry policy
RECOVERABLE_FAILURES = frozenset({
    "transient_test_runner",
    "provider_timeout",
    "network_timeout",
    "temporary_file_lock",
    "flaky_ci_step",
    "optional_service_unavailable",
})

NON_RECOVERABLE_FAILURES = frozenset({
    "permission_denial",
    "secret_exposure",
    "destructive_action",
    "invalid_architecture",
    "security_test_failure",
    "branch_divergence",
    "trading_guardian_isolation_failure",
    "merge_conflict",
    "production_access_required",
    "licence_ambiguity",
    "repeated_identical_failure",
    "policy_violation",
    "force_push_attempt",
    "merge_attempt",
    "deploy_attempt",
    "live_trading_attempt",
})


def _now() -> float:
    return time.time()


def new_id(prefix: str = "eng") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class EngineeringBacklogItem:
    """One governed engineering work item."""

    item_id: str
    milestone_id: str
    title: str
    description: str = ""
    repository_id: str = "saathiai"
    branch_policy: str = "milestone/*"
    priority: str = Priority.P2.value
    status: str = ItemStatus.PROPOSED.value
    dependencies: list[str] = field(default_factory=list)
    risk_level: str = RiskLevel.LOW.value
    source_of_authority: str = "roadmap"
    acceptance_criteria: list[str] = field(default_factory=list)
    required_validations: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    approval_requirement: bool = False
    retry_limit: int = 3
    estimated_complexity: str = "small"
    capability_requirements: list[str] = field(default_factory=list)
    environment_requirements: list[str] = field(default_factory=list)
    rollback_requirement: str = "git revert"
    stop_conditions: list[str] = field(default_factory=list)
    evidence_references: list[str] = field(default_factory=list)
    is_security_issue: bool = False
    is_ci_regression: bool = False
    user_value: int = 5  # 0-10
    revenue_impact: int = 0  # 0-10
    architecture_reuse: int = 8  # 0-10
    unresolved_blockers: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)

    def fingerprint(self) -> str:
        raw = f"{self.item_id}|{self.milestone_id}|{self.title}|{self.repository_id}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EngineeringBacklogItem":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class EngineeringTask:
    """Runtime task derived from a backlog item for one orchestration cycle."""

    task_id: str
    item_id: str
    objective: str
    scope: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    starting_commit: str = ""
    branch: str = ""
    repository_root: str = ""
    validation_plan: list[str] = field(default_factory=list)
    status: str = ItemStatus.SELECTED.value
    created_at: float = field(default_factory=_now)

    def fingerprint(self) -> str:
        raw = f"{self.task_id}|{self.item_id}|{self.objective}|{self.starting_commit}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Checkpoint:
    task_id: str
    session_id: str
    phase: str
    timestamp: float = field(default_factory=_now)
    head: str = ""
    changed_files: list[str] = field(default_factory=list)
    test_state: str = ""
    warnings: list[str] = field(default_factory=list)
    blocker_state: str = ""
    next_action: str = ""
    rollback_point: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationResult:
    name: str
    command: str
    start_time: float
    end_time: float
    exit_status: int
    summary: str
    evidence_ref: str = ""
    required: bool = True
    outcome: str = "pass"  # pass | fail | blocked | skipped

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentSessionResult:
    session_id: str
    status: str
    process_id: int | None = None
    adapter: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    exit_code: int | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    usage_note: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def can_transition(current: str | ItemStatus, new: str | ItemStatus) -> bool:
    cur = ItemStatus(current) if not isinstance(current, ItemStatus) else current
    nxt = ItemStatus(new) if not isinstance(new, ItemStatus) else new
    if cur == nxt:
        return True
    return nxt in ALLOWED_TRANSITIONS.get(cur, frozenset())
