"""FM-I3 persistence models, integrity, recovery dispositions, source-of-truth map.

This module defines *what* is durable and who owns authority.
It does not replace RunStore, ExecutionStore, Approval, or Audit systems.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional
import hashlib
import json
import time

from saathi.agent_runtime.harness.types import HarnessSessionState
from saathi.agent_runtime.models import RunState

# Schema version for harness durable records (explicit; migrations tested).
SCHEMA_VERSION = "1.0"
SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0"})

# Private / secret keys never persisted in event payloads.
BANNED_PAYLOAD_KEYS = frozenset({
    "chain_of_thought",
    "private_cot",
    "hidden_reasoning",
    "raw_cot",
    "password",
    "secret",
    "api_key",
    "access_token",
    "refresh_token",
    "authorization",
    "bearer",
    "auth_token",
    "private_key",
})


class RetentionClass(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    QUARANTINED = "quarantined"
    AUDIT_SENSITIVE = "audit_sensitive"
    CERTIFICATION_EVIDENCE = "certification_evidence"


class RecoveryDisposition(str, Enum):
    RECOVER_READY = "RECOVER_READY"
    RECOVER_RUNNING_AS_PAUSED = "RECOVER_RUNNING_AS_PAUSED"
    RECOVER_WAITING_FOR_APPROVAL = "RECOVER_WAITING_FOR_APPROVAL"
    RECOVER_CANCELLED = "RECOVER_CANCELLED"
    RECOVER_TERMINAL = "RECOVER_TERMINAL"
    QUARANTINE_STALE = "QUARANTINE_STALE"
    QUARANTINE_CORRUPT = "QUARANTINE_CORRUPT"
    QUARANTINE_AUTHORITY_CONFLICT = "QUARANTINE_AUTHORITY_CONFLICT"
    ABANDON_ORPHANED = "ABANDON_ORPHANED"


class TerminalOutcome(str, Enum):
    NONE = "none"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    QUARANTINED = "quarantined"
    ABANDONED = "abandoned"


# ── Source-of-truth matrix (authoritative documentation + runtime reference) ─

SOURCE_OF_TRUTH: Mapping[str, Mapping[str, str]] = {
    "run_lifecycle": {
        "owner": "agent_runtime.RunState / RunStore",
        "fm_i3": "projection snapshot only",
        "conflict": "RunState wins; quarantine on irreconcilable conflict",
    },
    "harness_session_projection": {
        "owner": "HarnessSessionController (projection)",
        "fm_i3": "durable copy of projection",
        "conflict": "rebuild from events when possible; else quarantine",
    },
    "mission_identity": {
        "owner": "platform / mission layer",
        "fm_i3": "reference (mission_id string)",
        "conflict": "missing mission → orphan/quarantine",
    },
    "organization_workspace_scope": {
        "owner": "platform RBAC / tenancy",
        "fm_i3": "bound identifiers (immutable for session)",
        "conflict": "scope mismatch → quarantine",
    },
    "normalized_harness_events": {
        "owner": "HarnessSessionController normalized stream",
        "fm_i3": "durable immutable append log",
        "conflict": "integrity fail → quarantine",
    },
    "event_sequence_watermark": {
        "owner": "harness durable store (with events)",
        "fm_i3": "transactional with last event",
        "conflict": "watermark/event divergence → quarantine",
    },
    "tool_intent": {
        "owner": "controller construction; EG execution path",
        "fm_i3": "nothing (no ToolIntent body stored)",
        "conflict": "N/A",
    },
    "execution_record": {
        "owner": "ExecutionGateway / ExecutionStore",
        "fm_i3": "pending_execution_id reference only",
        "conflict": "missing/conflict → quarantine or reconcile to terminal",
    },
    "approval_status": {
        "owner": "existing approval system / EG approval bindings",
        "fm_i3": "pending_approval_reference only",
        "conflict": "missing/conflict → quarantine or fail closed",
    },
    "cancellation": {
        "owner": "RunLifecycle + controller + harness ack",
        "fm_i3": "request/ack timestamps + projected CANCELLED",
        "conflict": "cancelled sessions never resume",
    },
    "resource_usage": {
        "owner": "harness resource accounting (projection)",
        "fm_i3": "JSON snapshot",
        "conflict": "snapshot is advisory for recovery display",
    },
    "quarantine_status": {
        "owner": "HarnessSessionController",
        "fm_i3": "durable flag + reason",
        "conflict": "quarantine always wins over continuation",
    },
    "terminal_outcome": {
        "owner": "controller projection of harness terminal",
        "fm_i3": "durable terminal_outcome",
        "conflict": "no resurrection",
    },
    "audit_record": {
        "owner": "HarnessAuditLog / platform audit",
        "fm_i3": "nothing (no second audit store)",
        "conflict": "N/A",
    },
    "evidence_record": {
        "owner": "ExecutionGateway evidence / platform evidence",
        "fm_i3": "nothing (references only via execution_id)",
        "conflict": "N/A",
    },
    "certification_status": {
        "owner": "platform certification",
        "fm_i3": "nothing",
        "conflict": "N/A",
    },
}


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def sanitize_payload(payload: Mapping[str, Any] | None) -> Dict[str, Any]:
    """Strip banned keys; fail closed by raising if secret-shaped keys remain."""
    if not payload:
        return {}
    out: Dict[str, Any] = {}
    for k, v in dict(payload).items():
        key = str(k)
        low = key.lower()
        if key in BANNED_PAYLOAD_KEYS or low in BANNED_PAYLOAD_KEYS:
            raise ValueError(f"banned payload key: {key}")
        if low in ("token", "password", "secret") or low.endswith("_token"):
            raise ValueError(f"secret-shaped payload key: {key}")
        out[key] = v
    return out


@dataclass
class DurableSessionRecord:
    session_id: str
    harness_id: str
    run_id: str
    mission_id: str
    organization_id: str
    workspace_id: str
    actor_id: str
    projected_harness_state: str
    authoritative_run_state_snapshot: str
    schema_version: str = SCHEMA_VERSION
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_event_sequence: int = 0
    last_event_id: str = ""
    pending_tool_proposal_id: str = ""
    pending_execution_id: str = ""
    pending_approval_reference: str = ""
    cancellation_requested_at: float = 0.0
    cancellation_acknowledged_at: float = 0.0
    quarantine_reason: str = ""
    quarantined: bool = False
    resource_usage_snapshot: Dict[str, Any] = field(default_factory=dict)
    terminal_outcome: str = TerminalOutcome.NONE.value
    retention_class: str = RetentionClass.ACTIVE.value
    expires_at: float = 0.0
    closed: bool = False
    integrity_hash: str = ""

    def compute_integrity(self) -> str:
        body = {
            "session_id": self.session_id,
            "harness_id": self.harness_id,
            "run_id": self.run_id,
            "mission_id": self.mission_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "actor_id": self.actor_id,
            "projected_harness_state": self.projected_harness_state,
            "authoritative_run_state_snapshot": self.authoritative_run_state_snapshot,
            "schema_version": self.schema_version,
            "last_event_sequence": self.last_event_sequence,
            "last_event_id": self.last_event_id,
            "pending_tool_proposal_id": self.pending_tool_proposal_id,
            "pending_execution_id": self.pending_execution_id,
            "pending_approval_reference": self.pending_approval_reference,
            "cancellation_requested_at": self.cancellation_requested_at,
            "cancellation_acknowledged_at": self.cancellation_acknowledged_at,
            "quarantine_reason": self.quarantine_reason,
            "quarantined": self.quarantined,
            "resource_usage_snapshot": self.resource_usage_snapshot,
            "terminal_outcome": self.terminal_outcome,
            "retention_class": self.retention_class,
            "closed": self.closed,
        }
        return content_hash(body)

    def seal(self) -> "DurableSessionRecord":
        self.integrity_hash = self.compute_integrity()
        return self

    def verify_integrity(self) -> bool:
        if not self.integrity_hash:
            return False
        return self.integrity_hash == self.compute_integrity()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DurableEventRecord:
    event_id: str
    session_id: str
    sequence_number: int
    event_type: str
    harness_id: str
    timestamp: float
    payload: Dict[str, Any] = field(default_factory=dict)
    turn_id: str = ""
    run_id: str = ""
    mission_id: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    correlation_id: str = ""
    causation_id: str = ""
    classification: str = "INTERNAL"
    redaction_state: str = "NONE"
    schema_version: str = SCHEMA_VERSION
    integrity_hash: str = ""

    def compute_integrity(self) -> str:
        body = {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "sequence_number": self.sequence_number,
            "event_type": self.event_type,
            "harness_id": self.harness_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "turn_id": self.turn_id,
            "run_id": self.run_id,
            "mission_id": self.mission_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "classification": self.classification,
            "redaction_state": self.redaction_state,
            "schema_version": self.schema_version,
        }
        return content_hash(body)

    def seal(self) -> "DurableEventRecord":
        self.integrity_hash = self.compute_integrity()
        return self

    def verify_integrity(self) -> bool:
        if not self.integrity_hash:
            return False
        return self.integrity_hash == self.compute_integrity()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RecoveryResult:
    disposition: RecoveryDisposition
    session: Optional[DurableSessionRecord] = None
    reason: str = ""
    events_count: int = 0
    can_continue: bool = False


def default_retention_seconds(retention: RetentionClass) -> float:
    """Bounded retention for isolated test / internal stores (seconds)."""
    return {
        RetentionClass.ACTIVE: 7 * 86400,
        RetentionClass.COMPLETED: 30 * 86400,
        RetentionClass.FAILED: 30 * 86400,
        RetentionClass.CANCELLED: 14 * 86400,
        RetentionClass.QUARANTINED: 90 * 86400,
        RetentionClass.AUDIT_SENSITIVE: 180 * 86400,
        RetentionClass.CERTIFICATION_EVIDENCE: 365 * 86400,
    }[retention]


def map_terminal_outcome(state: HarnessSessionState | str) -> TerminalOutcome:
    s = state.value if isinstance(state, HarnessSessionState) else str(state)
    return {
        "COMPLETED": TerminalOutcome.COMPLETED,
        "FAILED": TerminalOutcome.FAILED,
        "CANCELLED": TerminalOutcome.CANCELLED,
        "TIMED_OUT": TerminalOutcome.TIMED_OUT,
        "CLOSED": TerminalOutcome.COMPLETED,
    }.get(s, TerminalOutcome.NONE)


def map_run_state_snapshot(rs: RunState | str) -> str:
    if isinstance(rs, RunState):
        return rs.value
    return str(rs)
