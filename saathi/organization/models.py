"""SaathiOS AI Company — canonical organization domain model.

An ``AgentRole`` here is a *logical identity* (mandate, capabilities, authority,
evidence rules), NOT an LLM process. Roles are served on demand by the existing
runtimes (M10 ``saathi.agent_runtime`` and the platform mission runtime) through
a small bounded pool of inference jobs. Most roles are IDLE most of the time.

This module owns only vocabulary + validation. It never executes anything and
never grants tool authority: capability labels are descriptive, and every role's
execution authority is ``NONE`` unless a deterministic authority system (not an
agent) is involved. Financial execution is structurally impossible to declare.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── status ───────────────────────────────────────────────────────────────────
class AgentStatus(str, Enum):
    """Visible lifecycle state of a logical role. Derived, never invented."""

    OFFLINE = "OFFLINE"                  # runtime serving this role is down
    UNAVAILABLE = "UNAVAILABLE"          # role cannot run (tool/connector missing)
    UNKNOWN = "UNKNOWN"                  # state cannot be determined
    IDLE = "IDLE"                        # defined, not instantiated / no active work
    ASSIGNED = "ASSIGNED"                # work queued for this role
    RESEARCHING = "RESEARCHING"
    ANALYZING = "ANALYZING"
    WORKING = "WORKING"
    WAITING = "WAITING"                  # delegated / paused / dependency pending
    REVIEWING = "REVIEWING"
    CHALLENGING = "CHALLENGING"
    AWAITING_EVIDENCE = "AWAITING_EVIDENCE"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    BLOCKED = "BLOCKED"
    COMPLETE = "COMPLETE"                # recently finished (short-lived)
    ERROR = "ERROR"


BUSY_STATUSES = frozenset({
    AgentStatus.RESEARCHING, AgentStatus.ANALYZING, AgentStatus.WORKING,
    AgentStatus.REVIEWING, AgentStatus.CHALLENGING,
})
ACTIVE_STATUSES = BUSY_STATUSES | {AgentStatus.ASSIGNED}
REVIEW_STATUSES = frozenset({AgentStatus.REVIEWING, AgentStatus.CHALLENGING,
                             AgentStatus.AWAITING_APPROVAL})
ATTENTION_STATUSES = frozenset({AgentStatus.BLOCKED, AgentStatus.ERROR})
# States that require an accompanying human-readable reason.
REASON_REQUIRED = frozenset({AgentStatus.BLOCKED, AgentStatus.ERROR,
                             AgentStatus.UNAVAILABLE, AgentStatus.OFFLINE,
                             AgentStatus.AWAITING_EVIDENCE})

_S = AgentStatus
_WORK = {_S.RESEARCHING, _S.ANALYZING, _S.WORKING, _S.REVIEWING, _S.CHALLENGING}
_ANY_RUNNABLE = _WORK | {_S.ASSIGNED, _S.WAITING, _S.AWAITING_EVIDENCE,
                         _S.AWAITING_APPROVAL}
# Legal visible transitions. A derived snapshot may jump (e.g. IDLE→WORKING when
# a run started between two reads); ``validate_status_transition`` is used where
# the organization layer itself drives a role (mission simulation of steps it
# executes deterministically), and to test the model is coherent.
_STATUS_TRANSITIONS: dict[AgentStatus, set[AgentStatus]] = {
    _S.OFFLINE: {_S.IDLE, _S.UNKNOWN, _S.UNAVAILABLE},
    _S.UNAVAILABLE: {_S.IDLE, _S.OFFLINE, _S.UNKNOWN},
    _S.UNKNOWN: set(_S),
    _S.IDLE: {_S.ASSIGNED, _S.OFFLINE, _S.UNAVAILABLE, _S.UNKNOWN} | _WORK,
    _S.ASSIGNED: _ANY_RUNNABLE | {_S.BLOCKED, _S.ERROR, _S.IDLE, _S.COMPLETE},
    _S.RESEARCHING: _ANY_RUNNABLE | {_S.BLOCKED, _S.ERROR, _S.COMPLETE},
    _S.ANALYZING: _ANY_RUNNABLE | {_S.BLOCKED, _S.ERROR, _S.COMPLETE},
    _S.WORKING: _ANY_RUNNABLE | {_S.BLOCKED, _S.ERROR, _S.COMPLETE},
    _S.REVIEWING: _ANY_RUNNABLE | {_S.BLOCKED, _S.ERROR, _S.COMPLETE},
    _S.CHALLENGING: _ANY_RUNNABLE | {_S.BLOCKED, _S.ERROR, _S.COMPLETE},
    _S.WAITING: _ANY_RUNNABLE | {_S.BLOCKED, _S.ERROR, _S.IDLE},
    _S.AWAITING_EVIDENCE: _ANY_RUNNABLE | {_S.BLOCKED, _S.ERROR, _S.IDLE},
    _S.AWAITING_APPROVAL: _ANY_RUNNABLE | {_S.BLOCKED, _S.IDLE, _S.COMPLETE},
    _S.BLOCKED: _ANY_RUNNABLE | {_S.IDLE, _S.ERROR},
    _S.COMPLETE: {_S.IDLE, _S.ASSIGNED} | _WORK,
    _S.ERROR: {_S.IDLE, _S.ASSIGNED, _S.OFFLINE},
}


class IllegalStatusTransition(ValueError):
    pass


def can_transition(src: AgentStatus, dst: AgentStatus) -> bool:
    return src == dst or dst in _STATUS_TRANSITIONS.get(src, set())


def validate_status_transition(src: AgentStatus, dst: AgentStatus) -> None:
    if not can_transition(src, dst):
        raise IllegalStatusTransition(f"illegal status transition {src.value} → {dst.value}")


# ── authority ────────────────────────────────────────────────────────────────
class AuthorityLevel(str, Enum):
    """What a logical role may do with its *reasoning*. None of these levels
    confers tool, broker, exchange, deployment or credential access."""

    OBSERVE = "OBSERVE"            # read / summarize authorized data
    ADVISE = "ADVISE"              # analysis + recommendations
    PROPOSE = "PROPOSE"            # structured proposals for deterministic review
    CHALLENGE = "CHALLENGE"        # adversarial review of another role's output
    ORCHESTRATE = "ORCHESTRATE"    # decompose + delegate (Saathi) — not execute
    LOCAL_CHANGE = "LOCAL_CHANGE"  # propose reversible local changes behind approval


EXECUTION_AUTHORITY_NONE = "NONE"

# Capabilities no logical role may ever declare. Superset of the platform's
# FORBIDDEN_ALL (saathi.platform.orchestration.roles) plus finance-specific ones.
FORBIDDEN_CAPABILITIES = frozenset({
    "direct_tool_execution", "forge_approval", "bypass_rbac",
    "access_credentials", "mutate_production", "self_grant_permission",
    "disable_audit", "suppress_evidence", "trading_execution",
    "public_exposure",
    # finance-specific (explicit so the UI can state them)
    "place_order", "cancel_order", "call_execution_gateway",
    "override_trading_guardian", "modify_risk_limits", "self_approve",
    "move_funds", "withdraw_funds",
})

FINANCIAL_CANNOT = (
    "Place, modify or cancel orders on any broker or exchange",
    "Call the ExecutionGateway or any provider adapter",
    "Override Trading Guardian, Portfolio Risk or safety breakers",
    "Change deterministic risk limits",
    "Approve its own proposal or any approval request",
    "Move, deposit or withdraw funds",
)
UNIVERSAL_CANNOT = (
    "Read or reveal credentials, tokens or session secrets",
    "Bypass RBAC, approvals or audit",
    "Grant itself new permissions",
    "Fabricate evidence or suppress contrary evidence",
)


# ── structure ────────────────────────────────────────────────────────────────
class ActivityKind(str, Enum):
    """How a role's busy state is shown when its runtime reports RUNNING."""

    RESEARCH = "research"
    ANALYSIS = "analysis"
    WORK = "work"
    REVIEW = "review"
    CHALLENGE = "challenge"
    ORCHESTRATE = "orchestrate"


BUSY_STATUS_BY_ACTIVITY = {
    ActivityKind.RESEARCH: AgentStatus.RESEARCHING,
    ActivityKind.ANALYSIS: AgentStatus.ANALYZING,
    ActivityKind.WORK: AgentStatus.WORKING,
    ActivityKind.REVIEW: AgentStatus.REVIEWING,
    ActivityKind.CHALLENGE: AgentStatus.CHALLENGING,
    ActivityKind.ORCHESTRATE: AgentStatus.WORKING,
}


@dataclass(frozen=True)
class RuntimeBinding:
    """Which existing runtime identity serves this logical role.

    kind:
      * ``agent_runtime`` — M10 AgentDefinition id (``saathi.agent_runtime.registry``)
      * ``mission_agent`` — platform mission-runtime AgentType value
      * ``organization`` — served only by organization missions (deterministic steps)
      * ``logical`` — declared, no runtime yet (shown IDLE/UNAVAILABLE honestly)
    """

    kind: str
    ref: str = ""


@dataclass(frozen=True)
class AgentRole:
    role_id: str
    name: str
    office_id: str
    title: str                       # short label under the avatar
    mandate: str
    activity: ActivityKind
    authority: AuthorityLevel
    capabilities: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()      # descriptive tool names (no grants)
    evidence_requirements: tuple[str, ...] = ()
    escalates_to: str = ""           # role_id
    output_schema: str = "structured_result"
    binding: RuntimeBinding = field(default_factory=lambda: RuntimeBinding("logical"))
    financial: bool = False
    lead: bool = False
    requires: tuple[str, ...] = ()   # dependency keys (connectors, engines)
    can: tuple[str, ...] = ()        # human-readable CAN list
    tier: str = "specialist"         # specialist | mandate (strategy mandate)

    @property
    def execution_authority(self) -> str:
        return EXECUTION_AUTHORITY_NONE

    def cannot(self) -> tuple[str, ...]:
        extra = FINANCIAL_CANNOT if self.financial else ()
        return extra + UNIVERSAL_CANNOT

    def to_public(self) -> dict[str, Any]:
        return {
            "role_id": self.role_id,
            "name": self.name,
            "title": self.title,
            "office_id": self.office_id,
            "mandate": self.mandate,
            "activity": self.activity.value,
            "authority": self.authority.value,
            "execution_authority": self.execution_authority,
            "capabilities": list(self.capabilities),
            "tools": list(self.tools),
            "evidence_requirements": list(self.evidence_requirements),
            "escalates_to": self.escalates_to or None,
            "output_schema": self.output_schema,
            "binding": {"kind": self.binding.kind, "ref": self.binding.ref or None},
            "financial": self.financial,
            "lead": self.lead,
            "requires": list(self.requires),
            "can": list(self.can),
            "cannot": list(self.cannot()),
            "tier": self.tier,
        }


@dataclass(frozen=True)
class Office:
    office_id: str
    name: str
    department_id: str
    floor_id: str
    purpose: str
    lead_role_id: str = ""
    accent: str = "blue"             # design-token hue name, not a hex
    icon: str = "office"


@dataclass(frozen=True)
class Floor:
    floor_id: str
    number: int
    name: str
    tagline: str
    department_id: str


@dataclass(frozen=True)
class Department:
    department_id: str
    name: str
    head_role_id: str = ""


@dataclass(frozen=True)
class AuthoritySystem:
    """A deterministic (non-LLM) authority in the institutional chain."""

    system_id: str
    name: str
    order: int
    description: str
    deterministic: bool = True
