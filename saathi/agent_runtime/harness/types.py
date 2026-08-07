"""FM-I1 AgentHarness contract types (internal, design-aligned with M385/FM-C2).

Capabilities are descriptive only — they never grant permission, credentials,
filesystem, network, provider, tool execution, or trading authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Sequence, Tuple
import time
import uuid


# ── Session state (projection only; RunState remains authoritative) ─────────


class HarnessSessionState(str, Enum):
    CREATED = "CREATED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_FOR_TOOL = "WAITING_FOR_TOOL"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CLOSED = "CLOSED"


TERMINAL_HARNESS_STATES = frozenset({
    HarnessSessionState.CANCELLED,
    HarnessSessionState.COMPLETED,
    HarnessSessionState.FAILED,
    HarnessSessionState.TIMED_OUT,
})

# Legal transitions (fail-closed: anything not listed is illegal).
HARNESS_TRANSITIONS: Mapping[HarnessSessionState, frozenset[HarnessSessionState]] = {
    HarnessSessionState.CREATED: frozenset({
        HarnessSessionState.INITIALIZING,
        HarnessSessionState.CANCELLED,
        HarnessSessionState.FAILED,
    }),
    HarnessSessionState.INITIALIZING: frozenset({
        HarnessSessionState.READY,
        HarnessSessionState.FAILED,
        HarnessSessionState.TIMED_OUT,
        HarnessSessionState.CANCELLED,
        HarnessSessionState.CANCELLING,
    }),
    HarnessSessionState.READY: frozenset({
        HarnessSessionState.RUNNING,
        HarnessSessionState.CANCELLING,
        HarnessSessionState.COMPLETED,
        HarnessSessionState.FAILED,
        HarnessSessionState.TIMED_OUT,
        HarnessSessionState.CLOSED,
    }),
    HarnessSessionState.RUNNING: frozenset({
        HarnessSessionState.WAITING_FOR_TOOL,
        HarnessSessionState.WAITING_FOR_APPROVAL,
        HarnessSessionState.READY,
        HarnessSessionState.CANCELLING,
        HarnessSessionState.COMPLETED,
        HarnessSessionState.FAILED,
        HarnessSessionState.TIMED_OUT,
    }),
    HarnessSessionState.WAITING_FOR_TOOL: frozenset({
        HarnessSessionState.RUNNING,
        HarnessSessionState.WAITING_FOR_APPROVAL,
        HarnessSessionState.READY,
        HarnessSessionState.CANCELLING,
        HarnessSessionState.FAILED,
        HarnessSessionState.TIMED_OUT,
        HarnessSessionState.CANCELLED,
    }),
    HarnessSessionState.WAITING_FOR_APPROVAL: frozenset({
        HarnessSessionState.RUNNING,
        HarnessSessionState.READY,
        HarnessSessionState.CANCELLING,
        HarnessSessionState.CANCELLED,
        HarnessSessionState.TIMED_OUT,
        HarnessSessionState.FAILED,
    }),
    HarnessSessionState.CANCELLING: frozenset({
        HarnessSessionState.CANCELLED,
        HarnessSessionState.FAILED,
    }),
    HarnessSessionState.CANCELLED: frozenset({HarnessSessionState.CLOSED}),
    HarnessSessionState.COMPLETED: frozenset({HarnessSessionState.CLOSED}),
    HarnessSessionState.FAILED: frozenset({HarnessSessionState.CLOSED}),
    HarnessSessionState.TIMED_OUT: frozenset({HarnessSessionState.CLOSED}),
    HarnessSessionState.CLOSED: frozenset(),
}


def is_terminal_harness_state(state: HarnessSessionState) -> bool:
    return state in TERMINAL_HARNESS_STATES or state is HarnessSessionState.CLOSED


def can_transition_harness(src: HarnessSessionState, dst: HarnessSessionState) -> bool:
    return dst in HARNESS_TRANSITIONS.get(src, frozenset())


# ── Capabilities (descriptive only) ─────────────────────────────────────────


class HarnessCapabilityId(str, Enum):
    SESSION_LIFECYCLE = "session_lifecycle"
    SUBMIT_TURN = "submit_turn"
    EVENT_STREAM = "event_stream"
    COOPERATIVE_CANCEL = "cooperative_cancel"
    TOOL_PROPOSALS = "tool_proposals"
    HEALTH = "health"
    RESOURCE_USAGE_REPORT = "resource_usage_report"
    # FM-I1 aliases used in mission vocabulary (mapped to required set)
    MULTI_TURN = "multi_turn"
    DETERMINISTIC_EVENTS = "deterministic_events"
    HEALTH_REPORTING = "health_reporting"
    RESOURCE_REPORTING = "resource_reporting"


REQUIRED_CAPABILITIES = frozenset({
    HarnessCapabilityId.SESSION_LIFECYCLE,
    HarnessCapabilityId.SUBMIT_TURN,
    HarnessCapabilityId.EVENT_STREAM,
    HarnessCapabilityId.COOPERATIVE_CANCEL,
    HarnessCapabilityId.TOOL_PROPOSALS,
    HarnessCapabilityId.HEALTH,
    HarnessCapabilityId.RESOURCE_USAGE_REPORT,
})


@dataclass(frozen=True)
class HarnessCapability:
    id: HarnessCapabilityId
    version: str = "1.0"
    notes: str = ""


@dataclass(frozen=True)
class HarnessCapabilityProfile:
    harness_id: str
    harness_version: str
    protocol_version: str
    capabilities: Tuple[HarnessCapability, ...]
    required_platform_protocol: str = ">=1.0,<2.0"

    def capability_ids(self) -> frozenset:
        return frozenset(c.id for c in self.capabilities)

    def declares(self, cap: HarnessCapabilityId) -> bool:
        return cap in self.capability_ids()


# ── Events ──────────────────────────────────────────────────────────────────


class HarnessEventType(str, Enum):
    SESSION_STARTED = "SESSION_STARTED"
    SESSION_READY = "SESSION_READY"
    TURN_ACCEPTED = "TURN_ACCEPTED"
    TEXT_DELTA = "TEXT_DELTA"
    TOOL_PROPOSAL = "TOOL_PROPOSAL"
    TOOL_REQUEST_ACCEPTED = "TOOL_REQUEST_ACCEPTED"
    TOOL_REQUEST_DENIED = "TOOL_REQUEST_DENIED"
    TOOL_RESULT_DELIVERED = "TOOL_RESULT_DELIVERED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_RESOLVED = "APPROVAL_RESOLVED"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    CANCELLATION_ACKNOWLEDGED = "CANCELLATION_ACKNOWLEDGED"
    RESOURCE_USAGE = "RESOURCE_USAGE"
    SESSION_COMPLETED = "SESSION_COMPLETED"
    SESSION_FAILED = "SESSION_FAILED"
    SESSION_TIMED_OUT = "SESSION_TIMED_OUT"
    SESSION_CLOSED = "SESSION_CLOSED"
    PROTOCOL_VIOLATION = "PROTOCOL_VIOLATION"


class EventClassification(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    SENSITIVE = "SENSITIVE"
    RESTRICTED = "RESTRICTED"


class EventRedactionState(str, Enum):
    NONE = "NONE"
    REDACTED = "REDACTED"
    REDACTION_FAILED = "REDACTION_FAILED"


@dataclass(frozen=True)
class HarnessEvent:
    event_id: str
    session_id: str
    sequence_number: int
    event_type: HarnessEventType
    harness_id: str
    timestamp: float
    payload: Mapping[str, Any] = field(default_factory=dict)
    turn_id: Optional[str] = None
    run_id: Optional[str] = None
    mission_id: Optional[str] = None
    organization_id: Optional[str] = None
    workspace_id: Optional[str] = None
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    classification: EventClassification = EventClassification.INTERNAL
    redaction_state: EventRedactionState = EventRedactionState.NONE

    def safe_payload(self) -> Mapping[str, Any]:
        """Return a shallow copy safe for audit (no private CoT keys)."""
        banned = {"chain_of_thought", "private_cot", "hidden_reasoning", "raw_cot"}
        return {k: v for k, v in dict(self.payload).items() if k not in banned}


# ── Budget / resources ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class HarnessBudget:
    max_turns: int = 8
    max_events: int = 256
    max_fake_tokens: int = 4096
    max_tool_proposals: int = 16
    max_retries: int = 2
    max_output_chars: int = 8192
    max_concurrent_sessions: int = 4
    max_logical_time_ms: int = 60_000
    cancel_ack_grace_ms: int = 1_000


@dataclass(frozen=True)
class HarnessResourceUsage:
    turns: int = 0
    events: int = 0
    fake_tokens: int = 0
    tool_proposals: int = 0
    retries: int = 0
    output_chars: int = 0
    logical_time_ms: int = 0
    concurrent_sessions: int = 0

    def exceeds(self, budget: HarnessBudget) -> Optional[str]:
        checks = (
            (self.turns > budget.max_turns, "max_turns"),
            (self.events > budget.max_events, "max_events"),
            (self.fake_tokens > budget.max_fake_tokens, "max_fake_tokens"),
            (self.tool_proposals > budget.max_tool_proposals, "max_tool_proposals"),
            (self.retries > budget.max_retries, "max_retries"),
            (self.output_chars > budget.max_output_chars, "max_output_chars"),
            (self.logical_time_ms > budget.max_logical_time_ms, "max_logical_time_ms"),
            (self.concurrent_sessions > budget.max_concurrent_sessions, "max_concurrent_sessions"),
        )
        for hit, name in checks:
            if hit:
                return name
        return None


# ── Requests / handles ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class HarnessSessionStartRequest:
    session_id: str
    actor_id: str
    correlation_id: str
    run_id: Optional[str] = None
    mission_id: Optional[str] = None
    organization_id: Optional[str] = None
    workspace_id: Optional[str] = None
    authority_class: str = "READ_ONLY"
    allowed_tool_names: Tuple[str, ...] = ()
    budget: HarnessBudget = field(default_factory=HarnessBudget)
    # Non-secret model prefs only
    model_prefs: Mapping[str, Any] = field(default_factory=dict)
    deadline_logical_ms: Optional[int] = None


@dataclass(frozen=True)
class HarnessSessionHandle:
    session_id: str
    state: HarnessSessionState
    harness_id: str
    capabilities: HarnessCapabilityProfile
    run_id: Optional[str] = None
    organization_id: Optional[str] = None
    workspace_id: Optional[str] = None


@dataclass(frozen=True)
class HarnessTurnSubmitRequest:
    session_id: str
    turn_id: str
    input_text: str
    correlation_id: str
    causation_id: Optional[str] = None
    # Attachment refs only (never raw secrets or absolute path authority)
    attachment_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class HarnessTurnHandle:
    turn_id: str
    session_id: str
    state: HarnessSessionState
    accepted: bool = True


class CancelAckStatus(str, Enum):
    REQUESTED = "requested"
    ACKNOWLEDGED = "acknowledged"
    ALREADY_TERMINAL = "already_terminal"


@dataclass(frozen=True)
class CancelAck:
    session_id: str
    status: CancelAckStatus
    reason: str = ""
    acknowledged_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class SessionCloseResult:
    session_id: str
    state: HarnessSessionState
    already_closed: bool = False
    reason: str = ""


class HarnessHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class HarnessHealth:
    status: HarnessHealthStatus
    harness_id: str
    detail: str = ""
    active_sessions: int = 0


# ── Tool proposal (untrusted driver output) ─────────────────────────────────


@dataclass(frozen=True)
class ToolProposal:
    """Untrusted proposal emitted by a harness. Never authoritative ToolIntent."""

    proposal_id: str
    session_id: str
    turn_id: str
    tool_name: str
    parameters: Mapping[str, Any]
    correlation_id: str
    causation_id: Optional[str] = None
    idempotency_key: Optional[str] = None  # optional; controller may mint if missing
    organization_id: Optional[str] = None
    workspace_id: Optional[str] = None


class ToolProposalDisposition(str, Enum):
    ACCEPTED = "accepted"
    DENIED = "denied"
    APPROVAL_REQUIRED = "approval_required"
    CANCELLED = "cancelled"
    QUARANTINED = "quarantined"


class ApprovalRefState(str, Enum):
    """Controller-side view of approval reference lifecycle (not a new system)."""

    NONE = "none"
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    REVOKED = "revoked"
    CONSUMED = "consumed"


class ProtocolViolationKind(str, Enum):
    INVALID_TRANSITION = "invalid_transition"
    DUPLICATE_EVENT_ID = "duplicate_event_id"
    SEQUENCE_GAP = "sequence_gap"
    SEQUENCE_REGRESSION = "sequence_regression"
    EVENT_AFTER_CLOSE = "event_after_close"
    SCOPE_MISMATCH = "scope_mismatch"
    UNKNOWN_TOOL = "unknown_tool"
    MALFORMED_PROPOSAL = "malformed_proposal"
    MISSING_CORRELATION = "missing_correlation"
    TERMINAL_RESURRECTION = "terminal_resurrection"
    FORGED_EVENT = "forged_event"
    RESOURCE_LIMIT = "resource_limit"
    LATE_EVENT = "late_event"
    CAPABILITY_CLAIM_ABUSE = "capability_claim_abuse"


def new_id(prefix: str = "") -> str:
    u = str(uuid.uuid4())
    return f"{prefix}{u}" if prefix else u
