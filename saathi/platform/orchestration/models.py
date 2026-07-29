"""Agent Orchestration and Planning Runtime contracts (M95–M102).

This layer plans and supervises. Mission Runtime remains authoritative for
mission lifecycle, checkpoints, evidence, and certification. Tool execution
always goes through PlatformAgentRuntime → ExecutionGateway.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import re
import time
from typing import Any

# ── Resource bounds (M2 / 8 GB) ──────────────────────────────────────────────
MAX_OBJECTIVE_CHARS = 4_000
MAX_PLAN_NODES = 200
MAX_GRAPH_DEPTH = 12
MAX_GRAPH_WIDTH = 40
MAX_CONCURRENT_MISSIONS = 4
MAX_CONCURRENT_AGENT_RUNS = 4
MAX_CONCURRENT_MODEL_GEN = 2
MAX_RETRIES_DEFAULT = 2
MAX_RETRIES_CEILING = 5
MAX_PLAN_VERSIONS = 20
MAX_CHECKPOINTS_TRACKED = 50
MAX_EVIDENCE_PER_NODE = 20
TASK_TIMEOUT_DEFAULT_SEC = 120.0
MISSION_TIMEOUT_DEFAULT_SEC = 7_200.0
CONTEXT_TOKEN_BUDGET = 6_000
MAX_QUEUE_DEPTH = 32
ACTIVITY_RETENTION = 200
MAX_TEMPLATES = 32

ORCHESTRATION_VERSION = "m95.1.0"

READONLY_ANALYSIS_TOOL = "m49.echo_readonly"


class OrchestrationState(str, Enum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_DEPENDENCY = "WAITING_DEPENDENCY"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    PAUSED = "PAUSED"
    RETRYING = "RETRYING"
    RECOVERING = "RECOVERING"
    BLOCKED = "BLOCKED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    CERTIFYING = "CERTIFYING"
    CERTIFIED = "CERTIFIED"
    CERTIFIED_WITH_LIMITATIONS = "CERTIFIED_WITH_LIMITATIONS"


ORCHESTRATION_TRANSITIONS: dict[OrchestrationState, frozenset[OrchestrationState]] = {
    OrchestrationState.DRAFT: frozenset(
        {
            OrchestrationState.VALIDATING,
            OrchestrationState.CANCELLED,
        }
    ),
    OrchestrationState.VALIDATING: frozenset(
        {
            OrchestrationState.READY,
            OrchestrationState.DRAFT,
            OrchestrationState.FAILED,
            OrchestrationState.CANCELLED,
        }
    ),
    OrchestrationState.READY: frozenset(
        {
            OrchestrationState.RUNNING,
            OrchestrationState.PAUSED,
            OrchestrationState.CANCELLED,
        }
    ),
    OrchestrationState.RUNNING: frozenset(
        {
            OrchestrationState.WAITING_DEPENDENCY,
            OrchestrationState.WAITING_APPROVAL,
            OrchestrationState.PAUSED,
            OrchestrationState.RETRYING,
            OrchestrationState.RECOVERING,
            OrchestrationState.BLOCKED,
            OrchestrationState.CANCELLING,
            OrchestrationState.COMPLETED,
            OrchestrationState.FAILED,
            OrchestrationState.CANCELLED,
        }
    ),
    OrchestrationState.WAITING_DEPENDENCY: frozenset(
        {
            OrchestrationState.RUNNING,
            OrchestrationState.WAITING_APPROVAL,
            OrchestrationState.PAUSED,
            OrchestrationState.BLOCKED,
            OrchestrationState.CANCELLED,
            OrchestrationState.FAILED,
        }
    ),
    OrchestrationState.WAITING_APPROVAL: frozenset(
        {
            OrchestrationState.RUNNING,
            OrchestrationState.PAUSED,
            OrchestrationState.BLOCKED,
            OrchestrationState.CANCELLED,
            OrchestrationState.FAILED,
        }
    ),
    OrchestrationState.PAUSED: frozenset(
        {
            OrchestrationState.RUNNING,
            OrchestrationState.READY,
            OrchestrationState.RECOVERING,
            OrchestrationState.CANCELLED,
        }
    ),
    OrchestrationState.RETRYING: frozenset(
        {
            OrchestrationState.RUNNING,
            OrchestrationState.FAILED,
            OrchestrationState.PAUSED,
            OrchestrationState.CANCELLED,
        }
    ),
    OrchestrationState.RECOVERING: frozenset(
        {
            OrchestrationState.RUNNING,
            OrchestrationState.READY,
            OrchestrationState.PAUSED,
            OrchestrationState.FAILED,
            OrchestrationState.CANCELLED,
        }
    ),
    OrchestrationState.BLOCKED: frozenset(
        {
            OrchestrationState.RUNNING,
            OrchestrationState.PAUSED,
            OrchestrationState.FAILED,
            OrchestrationState.CANCELLED,
        }
    ),
    OrchestrationState.CANCELLING: frozenset({OrchestrationState.CANCELLED}),
    OrchestrationState.CANCELLED: frozenset(),
    OrchestrationState.FAILED: frozenset(),
    OrchestrationState.COMPLETED: frozenset(
        {
            OrchestrationState.CERTIFYING,
            OrchestrationState.CERTIFIED,
            OrchestrationState.CERTIFIED_WITH_LIMITATIONS,
        }
    ),
    OrchestrationState.CERTIFYING: frozenset(
        {
            OrchestrationState.CERTIFIED,
            OrchestrationState.CERTIFIED_WITH_LIMITATIONS,
            OrchestrationState.FAILED,
        }
    ),
    OrchestrationState.CERTIFIED: frozenset(),
    OrchestrationState.CERTIFIED_WITH_LIMITATIONS: frozenset(),
}

TERMINAL_ORCHESTRATION = frozenset(
    {
        OrchestrationState.CANCELLED,
        OrchestrationState.FAILED,
        OrchestrationState.CERTIFIED,
        OrchestrationState.CERTIFIED_WITH_LIMITATIONS,
    }
)


class FailureClass(str, Enum):
    TRANSIENT_PROVIDER = "TRANSIENT_PROVIDER"
    TRANSIENT_TOOL = "TRANSIENT_TOOL"
    TIMEOUT = "TIMEOUT"
    DEPENDENCY_FAILED = "DEPENDENCY_FAILED"
    APPROVAL_DENIED = "APPROVAL_DENIED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    INVALID_PLAN = "INVALID_PLAN"
    STALE_CONTEXT = "STALE_CONTEXT"
    RECOVERY_MISMATCH = "RECOVERY_MISMATCH"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    SECURITY_GATE = "SECURITY_GATE"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    CERTIFICATION_FAILED = "CERTIFICATION_FAILED"
    EXTERNAL_INPUT_REQUIRED = "EXTERNAL_INPUT_REQUIRED"
    UNKNOWN = "UNKNOWN"


class FailureAction(str, Enum):
    RETRY = "retry"
    BACKOFF = "backoff"
    REPLAN = "replan"
    PAUSE = "pause"
    REQUEST_APPROVAL = "request_approval"
    REQUEST_USER_INPUT = "request_user_input"
    CANCEL_DEPENDENTS = "cancel_dependents"
    ESCALATE = "escalate"
    FAIL_CLOSED = "fail_closed"


class ApprovalRequirement(str, Enum):
    NO_APPROVAL_REQUIRED = "NO_APPROVAL_REQUIRED"
    APPROVAL_REQUIRED_BEFORE_EXECUTION = "APPROVAL_REQUIRED_BEFORE_EXECUTION"
    APPROVAL_REQUIRED_BEFORE_MUTATION = "APPROVAL_REQUIRED_BEFORE_MUTATION"
    APPROVAL_REQUIRED_BEFORE_EXTERNAL_CALL = "APPROVAL_REQUIRED_BEFORE_EXTERNAL_CALL"
    APPROVAL_REQUIRED_BEFORE_PRODUCTION = "APPROVAL_REQUIRED_BEFORE_PRODUCTION"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ClaimKind(str, Enum):
    AUTHORITATIVE_FACT = "authoritative_fact"
    DERIVED_INFERENCE = "derived_inference"
    USER_REQUIREMENT = "user_requirement"
    MODEL_RECOMMENDATION = "model_recommendation"
    UNRESOLVED_UNCERTAINTY = "unresolved_uncertainty"


# Map mission runtime states into orchestration states for display.
MISSION_TO_ORCH: dict[str, str] = {
    "DRAFT": OrchestrationState.DRAFT.value,
    "PLANNED": OrchestrationState.READY.value,
    "QUEUED": OrchestrationState.READY.value,
    "RUNNING": OrchestrationState.RUNNING.value,
    "WAITING": OrchestrationState.WAITING_APPROVAL.value,
    "BLOCKED": OrchestrationState.BLOCKED.value,
    "PAUSED": OrchestrationState.PAUSED.value,
    "FAILED": OrchestrationState.FAILED.value,
    "COMPLETED": OrchestrationState.COMPLETED.value,
    "CANCELLED": OrchestrationState.CANCELLED.value,
    "CERTIFIED": OrchestrationState.CERTIFIED.value,
}


def validate_orchestration_transition(current: str, nxt: str) -> None:
    try:
        cur = OrchestrationState(current)
        nxt_s = OrchestrationState(nxt)
    except ValueError as exc:
        raise ValueError(f"unknown orchestration state transition {current}->{nxt}") from exc
    allowed = ORCHESTRATION_TRANSITIONS.get(cur, frozenset())
    if nxt_s not in allowed:
        raise ValueError(f"invalid orchestration transition {current} -> {nxt}")


@dataclass
class ObjectiveIntake:
    objective: str
    expected_outcome: str = ""
    scope: str = ""
    exclusions: str = ""
    project_id: str = ""
    mission_id: str = ""
    workspace_id: str = ""
    tenant_id: str = ""
    risk_level: str = RiskLevel.MEDIUM.value
    budget_constraints: str = ""
    time_constraints: str = ""
    production_impact: bool = False
    credential_requirements: bool = False
    external_dependencies: str = ""
    success_criteria: str = ""
    stop_conditions: str = ""
    domain: str = "engineering"
    template_id: str = ""
    ambiguities: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        return asdict(self)

    def is_ready(self) -> bool:
        return bool(self.objective.strip()) and not self.missing_required


@dataclass
class PlanValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    node_count: int = 0
    dependency_count: int = 0
    approval_gates: int = 0
    blocked_nodes: int = 0

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OrchestrationRecord:
    orchestration_id: str
    mission_id: str
    org_id: str
    workspace_id: str
    project_id: str
    user_id: str
    state: str = OrchestrationState.DRAFT.value
    objective: str = ""
    plan_version: int = 1
    template_id: str = ""
    domain: str = "engineering"
    risk_level: str = RiskLevel.MEDIUM.value
    production_impact: bool = False
    intake: dict[str, Any] = field(default_factory=dict)
    plan_definition: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    assignments: list[dict[str, Any]] = field(default_factory=list)
    activity: list[dict[str, Any]] = field(default_factory=list)
    failure_class: str = ""
    last_checkpoint_id: str = ""
    limitations: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    certification: dict[str, Any] = field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        return {
            "orchestration_id": self.orchestration_id,
            "mission_id": self.mission_id,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "state": self.state,
            "objective": self.objective[:MAX_OBJECTIVE_CHARS],
            "plan_version": self.plan_version,
            "template_id": self.template_id,
            "domain": self.domain,
            "risk_level": self.risk_level,
            "production_impact": self.production_impact,
            "intake": self.intake,
            "validation": self.validation,
            "assignments": list(self.assignments)[:100],
            "activity": list(self.activity)[-50:],
            "failure_class": self.failure_class,
            "last_checkpoint_id": self.last_checkpoint_id,
            "limitations": list(self.limitations)[:20],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "certification": self.certification,
            "production_authorized": False,
            "tools_executable_by_model": False,
            "orchestration_version": ORCHESTRATION_VERSION,
        }


def stable_id(*parts: str, prefix: str = "orch_") -> str:
    raw = "|".join(str(p or "") for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"{prefix}{digest}"


_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|password|secret|private[_-]?key|authorization:\s*bearer)"
)


def reject_secrets(text: str, *, field: str = "text") -> str:
    t = str(text or "")
    if _SECRET_RE.search(t):
        raise ValueError(f"{field} contains prohibited secret material")
    return t
