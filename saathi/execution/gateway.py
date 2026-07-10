"""ExecutionGateway: Single authority for all external actions."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import asyncio
import concurrent.futures
import inspect
import logging

from saathi.execution.toolintent import ToolIntent
from saathi.execution.state import IntentState, StateHistory, RiskLevel
from saathi.execution.results import Evidence, AuditTrail, TimestampRecord, ExecutionResult, SanitizedResult
from saathi.execution.errors import (
    ExecutionGatewayException,
    ValidationException,
    AuthorizationException,
    ApprovalException,
    CredentialException,
    StateException,
)
from saathi.execution.queue.base import ExecutionQueue

logger = logging.getLogger(__name__)


def _run_coro(coro):
    """Run a coroutine to completion from synchronous gateway code.

    The ExecutionGateway pipeline is synchronous but the queue interface is
    async (durable queue lands in Phase 3.2). Before Repair 1 the gateway
    called ``self.queue.enqueue(intent)`` without awaiting, silently dropping
    the coroutine so the enqueue never happened — breaking idempotency /
    duplicate detection. This helper executes the coroutine correctly whether
    or not an event loop is already running in the current thread.
    """
    if not inspect.isawaitable(coro):
        return coro
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # A loop is already running in this thread; run the coroutine to completion
    # on a dedicated worker thread with its own loop.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


@dataclass
class ExecutionContext:
    """Environment context for execution decision."""
    actor_id: str
    business_unit: str
    timestamp: datetime
    current_time: datetime

    @property
    def business_hours(self) -> bool:
        """Check if current time is business hours (heuristic)."""
        hour = self.current_time.hour
        return 8 <= hour < 18  # 8am-6pm UTC


class ExecutionGateway:
    """Single authority for external action execution.

    Every consequential operation flows through this gateway:
    - Validation (schema, syntax)
    - Authorization (who can do what)
    - Risk classification (what could go wrong)
    - Approval workflow (human gates)
    - Credential management (secure secrets)
    - Execution (connector invocation)
    - Result sanitization (no secrets leak)
    - Audit trail (everything recorded)

    Hard invariants:
    1. No external action bypasses ExecutionGateway
    2. ToolIntent is never modified
    3. Credentials never appear in logs/results/events
    4. Authorization fails closed
    5. Approval fails closed
    6. Duplicate detection prevents duplicate side effects
    7. Unknown outcomes reconciled before retry
    8. Every attempt produces Evidence
    9. Connector output is untrusted
    10. Business-unit isolation mandatory
    """

    def __init__(self, queue: ExecutionQueue):
        self.queue = queue
        self.audit_trails: Dict[str, AuditTrail] = {}

    def receive_intent(self, intent: ToolIntent) -> StateHistory:
        """Receive new intent and begin execution flow.

        Returns StateHistory tracking all state transitions.
        """
        if not intent:
            raise ExecutionGatewayException("intent is required")

        history = StateHistory(intent_id=intent.intent_id)
        history.add_transition(
            IntentState.RECEIVED,
            "intent received by gateway"
        )

        logger.info(f"Intent received: {intent.intent_id} ({intent.operation})")
        return history

    def validate_intent(self, intent: ToolIntent, history: StateHistory) -> StateHistory:
        """Validate intent schema and syntax.

        Raises ValidationException if invalid.
        Transitions to VALIDATED or REJECTED.
        """
        try:
            # TODO: Implement actual validation
            # - Check ToolIntent schema
            # - Validate parameter types
            # - Verify required fields
            # - Reject malformed requests

            history.add_transition(
                IntentState.VALIDATED,
                "schema validation passed"
            )
            logger.info(f"Intent validated: {intent.intent_id}")
            return history

        except Exception as e:
            history.add_transition(
                IntentState.REJECTED,
                f"validation failed: {str(e)}"
            )
            raise ValidationException(str(e))

    def check_idempotency(self, intent: ToolIntent, history: StateHistory) -> StateHistory:
        """Check for duplicate intents (idempotency).

        Returns cached result if exact duplicate detected.
        Transitions to DUPLICATE or continues to authorization.
        """
        # TODO: Implement idempotency check
        # - Compute idempotency key
        # - Check if key seen before
        # - Return cached result if found
        # - Detect partial duplicates (CONFLICT state)

        return history

    def authorize(self, intent: ToolIntent, context: ExecutionContext, history: StateHistory) -> StateHistory:
        """Check authorization.

        Raises AuthorizationException if denied.
        Transitions to AUTHORIZED or DENIED.
        """
        try:
            # TODO: Implement authorization
            # - Check actor has permission for operation
            # - Check actor has access to business_unit
            # - Check actor's role permits this risk level
            # - Check actor's quota allows this

            history.add_transition(
                IntentState.AUTHORIZED,
                f"authorization granted for {context.actor_id}"
            )
            logger.info(f"Intent authorized: {intent.intent_id}")
            return history

        except Exception as e:
            history.add_transition(
                IntentState.DENIED,
                f"authorization denied: {str(e)}"
            )
            raise AuthorizationException(str(e))

    def classify_risk(self, intent: ToolIntent, context: ExecutionContext, history: StateHistory) -> tuple[StateHistory, RiskLevel]:
        """Classify execution risk.

        Returns (updated_history, risk_level).
        Transitions to RISK_CLASSIFIED.
        """
        # TODO: Implement risk classification
        # - Cost risk (exceeds budget?)
        # - Data risk (sensitive data?)
        # - Latency risk (deadline approaching?)
        # - Provider risk (provider unhealthy?)
        # - Fallback risk (fallback available?)

        risk_level = RiskLevel.LOW
        history.add_transition(
            IntentState.RISK_CLASSIFIED,
            f"risk classified as {risk_level.value}"
        )
        logger.info(f"Intent risk classified: {intent.intent_id} ({risk_level.value})")
        return history, risk_level

    def check_approval(self, intent: ToolIntent, risk_level: RiskLevel, history: StateHistory) -> StateHistory:
        """Check if approval is required.

        Low-risk intents auto-approve.
        High-risk intents require human approval (max 1 hour).

        Transitions to APPROVED or AWAITING_APPROVAL.
        """
        # TODO: Implement approval workflow
        # - Auto-approve if low-risk
        # - Create approval record if high-risk
        # - Wait for human decision or timeout
        # - Handle approval granted/rejected/expired

        approval_required = risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

        if approval_required:
            history.add_transition(
                IntentState.AWAITING_APPROVAL,
                f"approval required (risk={risk_level.value}), deadline in 1 hour"
            )
            logger.info(f"Intent awaiting approval: {intent.intent_id}")
        else:
            history.add_transition(
                IntentState.APPROVED,
                f"auto-approved (risk={risk_level.value})"
            )
            logger.info(f"Intent auto-approved: {intent.intent_id}")

        return history

    def enqueue_for_execution(self, intent: ToolIntent, history: StateHistory) -> StateHistory:
        """Add intent to durable execution queue.

        Transitions to QUEUED.
        """
        # TODO: Implement queueing
        # - Add intent to durable queue
        # - Return queue position and ETA

        try:
            _run_coro(self.queue.enqueue(intent))
            history.add_transition(
                IntentState.QUEUED,
                "added to execution queue"
            )
            logger.info(f"Intent queued: {intent.intent_id}")
            return history

        except Exception as e:
            history.add_transition(
                IntentState.FAILED_FINAL,
                f"queueing failed: {str(e)}"
            )
            raise ExecutionGatewayException(f"queue failure: {str(e)}")

    def execute(self, intent: ToolIntent, history: StateHistory) -> ExecutionResult:
        """Execute intent via connector.

        Handles retries for transient failures.
        Returns ExecutionResult.
        """
        # TODO: Implement execution
        # - Obtain credential lease
        # - Invoke connector
        # - Handle timeout/partial/failure
        # - Classify error as retriable or final
        # - Reconcile unknown outcomes

        return ExecutionResult(status=None)

    def sanitize_result(self, result: ExecutionResult, intent: ToolIntent) -> SanitizedResult:
        """Remove secrets and validate result.

        Raises ResultException if sanitization fails.
        """
        # TODO: Implement sanitization
        # - Strip bearer tokens
        # - Strip API keys
        # - Strip passwords
        # - Validate schema
        # - Check cost within reserved budget

        return SanitizedResult(original_status=result.status)

    def record_evidence(self, intent: ToolIntent, history: StateHistory, result: Optional[SanitizedResult]) -> Evidence:
        """Create immutable audit evidence.

        Evidence is append-only and permanent.
        """
        evidence = Evidence(
            intent_id=intent.intent_id,
            attempt_number=1,
            state_history=history,
            authorization_granted=IntentState.AUTHORIZED in [t.to_state for t in history.transitions],
            authorization_rationale="TODO",
            approval_required=False,
            sanitized_result=result,
        )

        # Append to audit trail
        if intent.intent_id not in self.audit_trails:
            self.audit_trails[intent.intent_id] = AuditTrail(intent.intent_id)

        self.audit_trails[intent.intent_id].add_evidence(evidence)
        logger.info(f"Evidence recorded: {intent.intent_id}")
        return evidence
