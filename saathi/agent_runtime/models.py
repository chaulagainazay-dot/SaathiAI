"""M10 canonical typed models — agent definition, run state machine, task,
delegation, risk, output contracts.

Risk 0–4 maps onto the gateway's RiskLevel L0–L4. State transitions are
explicit and validated; illegal transitions raise.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class RunState(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    QUEUED = "queued"
    RUNNING = "running"
    DELEGATED = "delegated"
    VERIFYING = "verifying"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    # control / failure
    PAUSED = "paused"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    BLOCKED = "blocked"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    PARTIALLY_COMPLETED = "partially_completed"


_TERMINAL = {RunState.COMPLETED, RunState.CANCELLED, RunState.FAILED,
             RunState.TIMED_OUT, RunState.ROLLED_BACK, RunState.PARTIALLY_COMPLETED}

# Legal transitions. Anything not listed is illegal.
_TRANSITIONS: dict[RunState, set[RunState]] = {
    RunState.CREATED: {RunState.PLANNING, RunState.QUEUED, RunState.CANCELLED,
                       RunState.TIMED_OUT, RunState.FAILED},
    RunState.PLANNING: {RunState.AWAITING_APPROVAL, RunState.QUEUED,
                        RunState.BLOCKED, RunState.CANCELLED, RunState.FAILED,
                        RunState.TIMED_OUT},
    RunState.AWAITING_APPROVAL: {RunState.APPROVED, RunState.BLOCKED,
                                 RunState.CANCELLED, RunState.TIMED_OUT},
    RunState.APPROVED: {RunState.QUEUED, RunState.RUNNING, RunState.CANCELLED,
                        RunState.TIMED_OUT},
    RunState.QUEUED: {RunState.RUNNING, RunState.CANCELLED, RunState.PAUSED,
                      RunState.TIMED_OUT, RunState.FAILED},
    RunState.RUNNING: {RunState.DELEGATED, RunState.VERIFYING, RunState.PAUSED,
                       RunState.AWAITING_APPROVAL, RunState.BLOCKED,
                       RunState.FAILED, RunState.TIMED_OUT, RunState.CANCELLED,
                       RunState.COMPLETED, RunState.PARTIALLY_COMPLETED},
    RunState.DELEGATED: {RunState.RUNNING, RunState.VERIFYING, RunState.FAILED,
                         RunState.CANCELLED, RunState.TIMED_OUT},
    RunState.VERIFYING: {RunState.REVIEWING, RunState.RUNNING, RunState.FAILED,
                         RunState.COMPLETED, RunState.PARTIALLY_COMPLETED,
                         RunState.CANCELLED, RunState.TIMED_OUT},
    RunState.REVIEWING: {RunState.RUNNING, RunState.COMPLETED, RunState.FAILED,
                         RunState.PARTIALLY_COMPLETED, RunState.CANCELLED,
                         RunState.TIMED_OUT},
    RunState.PAUSED: {RunState.RUNNING, RunState.QUEUED, RunState.CANCELLED,
                      RunState.TIMED_OUT},
    RunState.BLOCKED: {RunState.RUNNING, RunState.CANCELLED, RunState.FAILED,
                       RunState.TIMED_OUT},
    # terminal states have no outgoing edges
    **{s: set() for s in _TERMINAL},
}


def is_terminal(state: RunState) -> bool:
    return state in _TERMINAL


def can_transition(src: RunState, dst: RunState) -> bool:
    return dst in _TRANSITIONS.get(src, set())


class IllegalTransition(Exception):
    pass


def validate_transition(src: RunState, dst: RunState) -> None:
    if not can_transition(src, dst):
        raise IllegalTransition(f"illegal transition {src.value} → {dst.value}")


class RiskClass(int, Enum):
    READ_ONLY = 0          # inspect, retrieve, search
    LOCAL_REVERSIBLE = 1   # edit allowed files, create tests
    LOCAL_MUTATION = 2     # migrations, deps, deletes, big refactors
    EXTERNAL_SIDE_EFFECT = 3  # email, publish, push
    HIGH_IMPACT = 4        # deploy, payment, irreversible


# gateway RiskLevel string ↔ M10 RiskClass
def to_gateway_risk(risk: RiskClass) -> str:
    return {0: "L0", 1: "L1", 2: "L2", 3: "L3", 4: "L4"}[int(risk)]


# Risk ≥ this requires explicit user approval (never agent self-approval).
APPROVAL_THRESHOLD = RiskClass.LOCAL_MUTATION


@dataclass
class AgentDefinition:
    agent_id: str
    name: str
    role: str
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)
    memory_scopes: list[str] = field(default_factory=list)   # namespace prefixes
    project_access: list[str] = field(default_factory=list)  # [] = current only
    risk_ceiling: RiskClass = RiskClass.READ_ONLY
    model_policy: str = "auto"
    fallback_model_policy: str = "auto"
    max_steps: int = 12
    max_runtime_sec: float = 120.0
    max_retries: int = 2
    max_token_budget: int = 20_000
    requires_approval: bool = False        # even for its own ceiling
    can_self_approve: bool = False         # planner/ceo → False (enforced)
    can_delegate_to: list[str] = field(default_factory=list)
    output_contract: str = "generic"       # planner|builder|reviewer|generic
    verification: list[str] = field(default_factory=list)
    status: str = "active"
    version: int = 1
    prompt_version: str = "v1"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["risk_ceiling"] = int(self.risk_ceiling)
        return d


@dataclass
class Task:
    task_id: str
    objective: str
    agent: str
    dependencies: list[str] = field(default_factory=list)
    input_artifacts: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    memory_scope: list[str] = field(default_factory=list)
    token_budget: int = 8000
    time_budget_sec: float = 60.0
    retry_policy: str = "transient-only"
    risk_class: RiskClass = RiskClass.READ_ONLY
    requires_approval: bool = False
    verification: list[str] = field(default_factory=list)
    status: str = "pending"   # pending|ready|running|done|failed|skipped|blocked|cancelled

    def to_dict(self) -> dict:
        d = asdict(self)
        d["risk_class"] = int(self.risk_class)
        return d


class MessageType(str, Enum):
    TASK_REQUEST = "task_request"
    CLARIFICATION = "clarification"
    EVIDENCE = "evidence"
    RESULT = "result"
    CRITIQUE = "critique"
    REVISION_REQUEST = "revision_request"
    APPROVAL_REQUEST = "approval_request"
    APPROVAL_RESPONSE = "approval_response"
    FAILURE = "failure"
    STATUS = "status"
    CANCELLATION = "cancellation"
    HANDOFF = "handoff"


# ── output contracts (Phase 17) ─────────────────────────────────────────────
def validate_output(contract: str, data: dict) -> tuple[bool, list[str]]:
    """Validate an agent's structured output. Malformed output never crashes;
    it is reported and the run degrades."""
    if not isinstance(data, dict):
        return False, ["output is not an object"]
    required = {
        "planner": ["objective", "tasks", "acceptance_criteria"],
        "builder": ["status", "files_changed", "validation"],
        "reviewer": ["verdict", "findings"],
    }.get(contract, [])
    missing = [k for k in required if k not in data]
    if contract == "reviewer" and data.get("verdict") not in \
            (None, "approve", "revise", "block"):
        missing.append("verdict must be approve|revise|block")
    return (not missing), missing
