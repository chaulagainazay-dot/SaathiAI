"""ExecutionGateway state machine."""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


class IntentState(Enum):
    """All possible ToolIntent execution states."""

    # Validation & detection
    RECEIVED = "received"              # Intent created, awaiting validation
    VALIDATED = "validated"            # Schema/syntax validation passed
    REJECTED = "rejected"              # Validation failed (permanent)
    DUPLICATE = "duplicate"            # Idempotency: exact duplicate detected
    CONFLICT = "conflict"              # Idempotency: partial duplicate (manual resolution)

    # Authorization & risk
    AUTHORIZED = "authorized"          # Authorization passed
    DENIED = "denied"                  # Authorization failed (permanent)
    RISK_CLASSIFIED = "risk_classified" # Risk level determined

    # Approval workflow
    AWAITING_APPROVAL = "awaiting_approval"  # Waiting for human approval
    APPROVED = "approved"              # Approval granted
    EXPIRED = "expired"                # Approval deadline passed

    # Execution
    QUEUED = "queued"                  # Durable queue, awaiting execution slot
    QUEUED_WITH_FALLBACK = "queued_with_fallback"  # Primary failed, using fallback
    RUNNING = "running"                # Connector invocation in progress
    SUCCEEDED = "succeeded"            # Completed successfully (terminal)
    FAILED_RETRYABLE = "failed_retryable"  # Failed, will retry
    FAILED_FINAL = "failed_final"      # Failed permanently (terminal)
    UNKNOWN_OUTCOME = "unknown_outcome" # Timeout/partial, reconciling state
    CANCELLED = "cancelled"            # User or system cancelled (terminal)


class RiskLevel(Enum):
    """Risk classification levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(Enum):
    """Approval workflow status."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class StateTransition:
    """Immutable state transition record."""
    from_state: IntentState
    to_state: IntentState
    timestamp: datetime
    reason: str
    metadata: dict = field(default_factory=dict)

    def __hash__(self):
        return hash((self.from_state, self.to_state, self.timestamp))


@dataclass
class StateHistory:
    """Complete state transition history for an intent."""
    intent_id: str
    transitions: List[StateTransition] = field(default_factory=list)
    current_state: IntentState = IntentState.RECEIVED

    def add_transition(self, to_state: IntentState, reason: str, metadata: dict = None):
        """Record state transition (append-only)."""
        transition = StateTransition(
            from_state=self.current_state,
            to_state=to_state,
            timestamp=datetime.utcnow(),
            reason=reason,
            metadata=metadata or {}
        )
        self.transitions.append(transition)
        self.current_state = to_state
        return transition

    def is_terminal(self) -> bool:
        """Check if current state is terminal (no more transitions)."""
        terminal_states = {
            IntentState.REJECTED,
            IntentState.DUPLICATE,
            IntentState.DENIED,
            IntentState.EXPIRED,
            IntentState.SUCCEEDED,
            IntentState.FAILED_FINAL,
            IntentState.CANCELLED,
        }
        return self.current_state in terminal_states
