"""Distributed worker fleet domain model (M103+).

Extends M56 abstractions; does not replace ClusterCoordinator, leases, or
PlatformAgentRuntime. Capabilities never grant authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import time
from typing import Any


class WorkerTrustState(str, Enum):
    UNREGISTERED = "UNREGISTERED"
    PENDING_ADMISSION = "PENDING_ADMISSION"
    TRUSTED_LOCAL = "TRUSTED_LOCAL"
    QUARANTINED = "QUARANTINED"
    DRAINING = "DRAINING"
    REVOKED = "REVOKED"
    UNHEALTHY = "UNHEALTHY"
    OFFLINE = "OFFLINE"


class WorkerHealthState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    STALE = "STALE"
    OFFLINE = "OFFLINE"
    QUARANTINED = "QUARANTINED"
    DRAINING = "DRAINING"


class AdmissionState(str, Enum):
    NOT_APPLIED = "NOT_APPLIED"
    PENDING = "PENDING"
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


class LeaseState(str, Enum):
    HELD = "HELD"
    RENEWED = "RENEWED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    RELEASED = "RELEASED"


class ReconciliationOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_WARNINGS = "ACCEPTED_WITH_WARNINGS"
    REJECTED_STALE = "REJECTED_STALE"
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"
    REJECTED_UNAUTHORIZED = "REJECTED_UNAUTHORIZED"
    REJECTED_INVALID_OUTPUT = "REJECTED_INVALID_OUTPUT"
    REJECTED_CANCELLED = "REJECTED_CANCELLED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    REQUIRES_RETRY = "REQUIRES_RETRY"
    REQUIRES_REPLAN = "REQUIRES_REPLAN"


class ExecutionEventType(str, Enum):
    ACCEPTED = "accepted"
    STARTED = "started"
    PROGRESS = "progress"
    CHECKPOINT = "checkpoint"
    EVIDENCE = "evidence"
    WARNING = "warning"
    RETRYABLE_FAILURE = "retryable_failure"
    TERMINAL_FAILURE = "terminal_failure"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class ArtifactClass(str, Enum):
    PROGRESS_METADATA = "progress_metadata"
    EVIDENCE = "evidence"
    PROPOSED_PATCH = "proposed_patch"
    TEST_RESULT = "test_result"
    BROWSER_RESULT = "browser_result"
    REPORT = "report"
    CHECKPOINT = "checkpoint"
    ARTIFACT_REFERENCE = "artifact_reference"
    TERMINAL_RESULT = "terminal_result"


# Trust states that may receive executable leases
LEASE_ELIGIBLE_TRUST = frozenset({WorkerTrustState.TRUSTED_LOCAL.value})
# Health states that may receive or renew leases
LEASE_ELIGIBLE_HEALTH = frozenset(
    {WorkerHealthState.HEALTHY.value, WorkerHealthState.DEGRADED.value}
)


@dataclass
class ResourceLimits:
    max_cpu_percent: float = 50.0
    max_memory_mb: int = 512
    max_active_leases: int = 2
    max_queue_depth: int = 8
    allow_browser: bool = False
    allow_model: bool = False
    allow_mutation: bool = False

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkerIdentity:
    """Control-plane validated worker identity. Worker-reported fields are not
    authoritative until admission succeeds."""

    worker_id: str
    node_id: str = "node-local"
    runtime_version: str = ""
    protocol_version: str = ""
    process_instance_id: str = ""
    startup_timestamp: float = 0.0
    platform: str = "darwin"
    architecture: str = "arm64"
    capability_set: list[str] = field(default_factory=list)
    resource_limits: dict[str, Any] = field(default_factory=dict)
    workspace_eligibility: list[str] = field(default_factory=list)
    tenant_eligibility: list[str] = field(default_factory=list)
    trust_state: str = WorkerTrustState.UNREGISTERED.value
    health_state: str = WorkerHealthState.OFFLINE.value
    admission_state: str = AdmissionState.NOT_APPLIED.value
    last_heartbeat: float = 0.0
    active_lease_count: int = 0
    bind_host: str = "127.0.0.1"
    quarantine_reason: str = ""
    admission_reasons: list[str] = field(default_factory=list)
    org_id: str = ""
    workspace_id: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_public(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "node_id": self.node_id,
            "runtime_version": self.runtime_version,
            "protocol_version": self.protocol_version,
            "process_instance_id": self.process_instance_id,
            "startup_timestamp": self.startup_timestamp,
            "platform": self.platform,
            "architecture": self.architecture,
            "capability_set": sorted(self.capability_set),
            "resource_limits": dict(self.resource_limits),
            "workspace_eligibility": sorted(self.workspace_eligibility),
            "tenant_eligibility": sorted(self.tenant_eligibility),
            "trust_state": self.trust_state,
            "health_state": self.health_state,
            "admission_state": self.admission_state,
            "last_heartbeat": self.last_heartbeat,
            "active_lease_count": self.active_lease_count,
            "bind_host": self.bind_host,
            "quarantine_reason": self.quarantine_reason,
            "admission_reasons": list(self.admission_reasons),
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "labels": dict(self.labels),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "WorkerIdentity":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass
class WorkLease:
    """Durable fenced lease for a work-graph node. One active lease per exclusive node."""

    lease_id: str
    work_node_id: str
    mission_id: str = ""
    orchestration_id: str = ""
    worker_id: str = ""
    attempt: int = 1
    issued_at: float = 0.0
    starts_at: float = 0.0
    expires_at: float = 0.0
    heartbeat_deadline: float = 0.0
    fencing_token: int = 0
    idempotency_key: str = ""
    authority_snapshot: dict[str, Any] = field(default_factory=dict)
    approval_reference: str = ""
    cancellation_state: str = "NONE"  # NONE | REQUESTED | CANCELLED
    completion_state: str = "OPEN"  # OPEN | COMPLETED | FAILED | CANCELLED
    state: str = LeaseState.HELD.value
    org_id: str = ""
    workspace_id: str = ""
    role: str = ""
    required_capabilities: list[str] = field(default_factory=list)
    renewals: int = 0
    plan_version: str = ""
    resource_budget: dict[str, Any] = field(default_factory=dict)
    m56_execution_id: str = ""  # optional link to M56 execution lease
    last_event_seq: int = 0
    result_hash: str = ""

    def is_active(self, now: float) -> bool:
        return (
            self.state in (LeaseState.HELD.value, LeaseState.RENEWED.value)
            and self.completion_state == "OPEN"
            and self.cancellation_state != "CANCELLED"
            and self.expires_at > now
        )

    def to_public(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "work_node_id": self.work_node_id,
            "mission_id": self.mission_id,
            "orchestration_id": self.orchestration_id,
            "worker_id": self.worker_id,
            "attempt": self.attempt,
            "issued_at": self.issued_at,
            "starts_at": self.starts_at,
            "expires_at": self.expires_at,
            "heartbeat_deadline": self.heartbeat_deadline,
            "fencing_token": self.fencing_token,
            "idempotency_key": self.idempotency_key,
            "approval_reference": self.approval_reference,
            "cancellation_state": self.cancellation_state,
            "completion_state": self.completion_state,
            "state": self.state,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "role": self.role,
            "required_capabilities": sorted(self.required_capabilities),
            "renewals": self.renewals,
            "plan_version": self.plan_version,
            "resource_budget": dict(self.resource_budget),
            "m56_execution_id": self.m56_execution_id,
            "last_event_seq": self.last_event_seq,
            "result_hash": self.result_hash,
            "authority_snapshot": dict(self.authority_snapshot),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "WorkLease":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass
class WorkerHeartbeat:
    worker_id: str
    at: float
    protocol_version: str
    active_leases: int = 0
    queue_depth: int = 0
    cpu_pressure: float = 0.0
    memory_pressure: float = 0.0
    disk_pressure: float = 0.0
    model_status: str = "unavailable"
    browser_availability: bool = False
    error_state: str = ""
    last_successful_action: str = ""
    sequence: int = 0

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionEvent:
    event_type: str
    worker_id: str
    lease_id: str
    fencing_token: int
    mission_id: str
    work_node_id: str
    attempt: int
    sequence: int
    at: float
    payload: dict[str, Any] = field(default_factory=dict)
    org_id: str = ""
    workspace_id: str = ""

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SchedulingDecision:
    work_node_id: str
    selected_worker_id: str = ""
    candidates: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    tie_breaking_rule: str = "lexicographic_worker_id"
    authority_checks: list[str] = field(default_factory=list)
    resource_checks: list[str] = field(default_factory=list)
    lease_result: str = ""
    reason: str = ""
    at: float = 0.0
    seed: str = ""

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReconciliationRecord:
    outcome: str
    lease_id: str
    work_node_id: str
    worker_id: str
    fencing_token: int
    reason: str = ""
    content_hash: str = ""
    at: float = 0.0
    advances_graph: bool = False
    audit_kept: bool = True

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


def content_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def now_ts() -> float:
    return time.time()
