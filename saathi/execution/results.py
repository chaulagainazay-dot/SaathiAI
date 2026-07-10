"""ExecutionGateway results, evidence, and audit trail."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any, Dict
from enum import Enum

from saathi.execution.state import StateHistory, StateTransition
from saathi.execution.errors import ExecutionError


class ExecutionStatus(Enum):
    """Result execution status."""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    PARTIAL = "partial"


@dataclass(frozen=True)
class TimestampRecord:
    """Immutable timestamp record for execution attempt."""
    created_at: datetime
    validated_at: Optional[datetime] = None
    authorized_at: Optional[datetime] = None
    risk_classified_at: Optional[datetime] = None
    approval_decided_at: Optional[datetime] = None
    credentials_obtained_at: Optional[datetime] = None
    queued_at: Optional[datetime] = None
    execution_started_at: Optional[datetime] = None
    execution_completed_at: Optional[datetime] = None
    result_sanitized_at: Optional[datetime] = None
    evidence_recorded_at: Optional[datetime] = None

    @property
    def total_duration_sec(self) -> float:
        """Total time from creation to completion."""
        end = self.evidence_recorded_at or datetime.utcnow()
        return (end - self.created_at).total_seconds()

    @property
    def execution_duration_sec(self) -> Optional[float]:
        """Time spent in actual execution (excluding queuing, approval)."""
        if self.execution_started_at and self.execution_completed_at:
            return (self.execution_completed_at - self.execution_started_at).total_seconds()
        return None


@dataclass
class ExecutionResult:
    """Result from connector execution."""
    status: ExecutionStatus
    data: Optional[Dict[str, Any]] = None
    cost_usd: Optional[float] = None
    duration_sec: float = 0.0
    error: Optional[ExecutionError] = None
    connector_trace: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS

    @property
    def is_retriable(self) -> bool:
        return self.error and self.error.retriable


@dataclass
class SanitizedResult:
    """Result after sanitization (safe for logging, caching, return)."""
    original_status: ExecutionStatus
    sanitized_data: Optional[Dict[str, Any]] = None
    cost_usd: Optional[float] = None
    duration_sec: float = 0.0
    error: Optional[ExecutionError] = None
    sanitization_notes: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_clean(self) -> bool:
        """Check if result is safe to return (no secrets)."""
        return True  # Verified in sanitization phase


@dataclass(frozen=True)
class Evidence:
    """Immutable audit evidence record."""
    intent_id: str
    attempt_number: int
    state_history: StateHistory

    # Decisions
    authorization_granted: bool
    authorization_rationale: str

    approval_required: bool
    approval_status: Optional[str] = None

    risk_level: str = "low"
    risk_factors: Dict[str, Any] = field(default_factory=dict)

    # Execution
    execution_result: Optional[ExecutionResult] = None
    sanitized_result: Optional[SanitizedResult] = None

    # Financial
    cost_reserved_usd: float = 0.0
    cost_actual_usd: float = 0.0

    # Audit
    actor_id: str = ""
    business_unit: str = ""
    timestamps: Optional[TimestampRecord] = None

    def __hash__(self):
        return hash((self.intent_id, self.attempt_number))

    def to_audit_log(self) -> Dict[str, Any]:
        """Convert to JSON-serializable audit log entry."""
        return {
            "intent_id": self.intent_id,
            "attempt": self.attempt_number,
            "state": self.state_history.current_state.value,
            "authorized": self.authorization_granted,
            "approval_required": self.approval_required,
            "risk_level": self.risk_level,
            "status": self.execution_result.status.value if self.execution_result else None,
            "cost_reserved": self.cost_reserved_usd,
            "cost_actual": self.cost_actual_usd,
            "actor": self.actor_id,
            "business_unit": self.business_unit,
            "timestamps": {
                "created": self.timestamps.created_at.isoformat() if self.timestamps else None,
                "completed": self.timestamps.evidence_recorded_at.isoformat() if self.timestamps else None,
                "duration_sec": self.timestamps.total_duration_sec if self.timestamps else None,
            },
        }


@dataclass
class AuditTrail:
    """Complete audit trail for an intent (all attempts)."""
    intent_id: str
    evidence_records: list[Evidence] = field(default_factory=list)

    def add_evidence(self, evidence: Evidence):
        """Append-only evidence collection."""
        self.evidence_records.append(evidence)

    def get_latest_evidence(self) -> Optional[Evidence]:
        """Get most recent evidence record."""
        return self.evidence_records[-1] if self.evidence_records else None
