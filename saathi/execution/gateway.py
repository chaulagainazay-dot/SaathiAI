"""ExecutionGateway: Single authority for all external actions.

M17.22 Phase 1 completes the *universal* boundary:

    ToolIntent → Validation → Permission → Risk → Approval →
    ExecutionGateway.submit → Handler (connector/cli/local/mcp) →
    Evidence → Security Event → Run Ledger → CEO Metrics

Legacy step methods (receive_intent / validate_intent / …) remain for
backward-compatible governance passes. New callers should use ``submit``.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
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


def _current_requester() -> str:
    """The actor to attribute an otherwise-unattributed execution to.

    A bound session becomes `user:<id>`; nothing bound becomes the named system
    actor. It never returns a human identity that was not established, which is
    the whole point: an unattributed action recorded as a real person is worse
    than one recorded as the backend, because it is indistinguishable in the
    audit log from something that person actually did.
    """
    from saathi.execution.authorization_sources import current_actor_id

    return current_actor_id()


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

    M17.22: use :meth:`submit` for the durable universal boundary (connector,
    CLI, local, MCP). M17.23 adds browser family via GovernedBrowser.
    Trading Guardian / n8n / LLM remain future migration work.
    """

    def __init__(self, queue: ExecutionQueue | None = None, *, boundary=None):
        # queue may be None when only the M17.22 submit path is used
        if queue is None:
            from saathi.execution.queue.memory import MemoryQueue
            queue = MemoryQueue()
        self.queue = queue
        self.audit_trails: Dict[str, AuditTrail] = {}
        self._boundary = boundary  # lazy UniversalBoundary
        #: Last decision produced by :meth:`authorize`, for evidence. Not a
        #: capability: it is never consulted to permit anything, only recorded.
        self._last_decision = None

    # ── M17.22 universal boundary ─────────────────────────────────────────
    def _ub(self):
        if self._boundary is None:
            from saathi.execution.universal import default_boundary
            self._boundary = default_boundary()
        return self._boundary

    def submit(
        self,
        intent: ToolIntent,
        *,
        approval_id: str = "",
        handler: Optional[Callable] = None,
        execute: bool = True,
        force_new: bool = False,
    ):
        """Authoritative entry: ToolIntent → durable ExecutionRecord.

        All connector / CLI / local / MCP actions should enter here.
        """
        return self._ub().submit(
            intent,
            approval_id=approval_id,
            handler=handler,
            execute=execute,
            force_new=force_new,
        )

    def cancel_execution(self, execution_id: str, *, reason: str = "cancelled"):
        return self._ub().cancel(execution_id, reason=reason)

    def expire_execution(self, execution_id: str, *, reason: str = "expired"):
        return self._ub().expire(execution_id, reason=reason)

    def approve_execution(
        self,
        execution_id: str,
        *,
        approval_id: str = "",
        execute: bool = True,
        handler=None,
        intent: ToolIntent | None = None,
    ):
        return self._ub().approve(
            execution_id,
            approval_id=approval_id,
            execute=execute,
            handler=handler,
            intent=intent,
        )

    def retry_execution(self, execution_id: str, *, intent: ToolIntent, handler=None):
        return self._ub().retry(execution_id, intent=intent, handler=handler)

    def execution_metrics(self, **kwargs) -> dict:
        return self._ub().metrics(**kwargs)

    def ceo_execution_summary(self, **kwargs):
        return self._ub().ceo_summary(**kwargs)

    def recover_after_restart(self, **kwargs):
        return self._ub().recover_after_restart(**kwargs)

    def register_handler(self, family: str, handler) -> None:
        self._ub().register_handler(family, handler)

    def get_execution(self, execution_id: str):
        return self._ub().store.get(execution_id)

    def execute_registered_tool(
        self,
        *,
        tool_id: str,
        arguments: dict | None = None,
        run_id: str = "",
        requested_by: str = "",
        capability: str = "",
        tool_version: str = "",
        idempotency_key: str = "",
        approval_reference=None,
        deadline: float = 0.0,
        timeout_sec: float | None = None,
        cancel_check=None,
        event_recorder=None,
        attempt: int = 1,
        parent_task_id: str = "",
        trace_id: str = "",
        scratch: dict | None = None,
    ):
        """M49.1: route a registered tool through ToolExecutionService.

        Does not replace ``submit`` / universal boundary. Strengthens the
        gateway with a fail-closed manifest path for code-owned tools.
        Callers must not invoke adapters directly.
        """
        from saathi.tool_runtime.contracts import ToolExecutionRequest
        from saathi.tool_runtime.service import default_tool_service

        # Attribution, resolved rather than assumed. This defaulted to a
        # hardcoded human identity, so any caller that did not pass one acted as
        # that person -- including against their approvals. It now takes the
        # actor the authenticated boundary bound, and falls back to the named
        # system actor when there is no session: a caller with no identity is
        # recorded as the backend, never as somebody.
        requested_by = requested_by or _current_requester()

        req = ToolExecutionRequest(
            run_id=run_id or "gw",
            tool_id=tool_id,
            tool_version=tool_version,
            arguments=dict(arguments or {}),
            capability=capability,
            requested_by=requested_by,
            idempotency_key=idempotency_key,
            approval_reference=approval_reference,
            deadline=deadline,
            timeout_sec=timeout_sec,
            attempt=attempt,
            parent_task_id=parent_task_id,
            trace_id=trace_id or (getattr(arguments, "get", lambda *_: "")("trace_id") if False else ""),
        )
        svc = default_tool_service()
        result = svc.execute_tool(
            req,
            cancel_check=cancel_check,
            event_recorder=event_recorder,
            scratch=scratch,
        )
        logger.info(
            "execute_registered_tool %s → %s (%s)",
            tool_id,
            result.outcome_class.value,
            result.error_code or "ok",
        )
        return result

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

    def authorize(
        self,
        intent: ToolIntent,
        context: ExecutionContext,
        history: StateHistory,
        *,
        inputs=None,
    ) -> StateHistory:
        """Decide whether this one intent may proceed. Fails closed.

        Every gate that the action's class actually requires must return a
        current, correlated positive result; anything else -- a refusal, a
        missing verdict, an input that could not be read -- reaches DENIED. There
        is no branch that transitions to AUTHORIZED without
        :func:`~saathi.execution.authorization.authorize_intent` saying so.

        Deciding is all this does. It invokes no handler, touches no connector
        and produces no side effect beyond the audit record, so an authorized
        intent has still not executed: `submit`/`gateway_exec` do that, and
        re-evaluate the gates that can change in between.

        ``inputs`` exists for tests and for callers that have already resolved
        the authority inputs; when omitted they are resolved from their real
        sources. It is deliberately keyword-only and not reachable from any
        request payload -- a caller who could supply their own inputs could
        supply their own permission.
        """
        from saathi.execution.authorization import Decision, authorize_intent
        from saathi.execution.authorization_sources import resolve_inputs

        if inputs is None:
            inputs = resolve_inputs(intent, context)
        decision = authorize_intent(intent, inputs)
        self._last_decision = decision
        self._audit_decision(decision)

        if decision.decision is not Decision.AUTHORIZED:
            history.add_transition(
                IntentState.DENIED,
                f"authorization {decision.decision.value}: {decision.reason_code}",
                metadata={"reason_code": decision.reason_code,
                          "intent_digest": decision.intent_digest},
            )
            logger.info("Intent %s: %s (%s)", decision.decision.value,
                        intent.intent_id, decision.reason_code)
            raise AuthorizationException(decision.reason_code)

        history.add_transition(
            IntentState.AUTHORIZED,
            f"authorization granted: {decision.reason_code}",
            metadata={"reason_code": decision.reason_code,
                      "intent_digest": decision.intent_digest,
                      "authority_class": decision.authority_class,
                      "actor_user_id": decision.actor_user_id},
        )
        logger.info("Intent authorized: %s", intent.intent_id)
        return history

    def _audit_decision(self, decision) -> None:
        """Durable evidence for one authorization decision, refusals included.

        Identifiers, class and reason code only. Never parameters, never a
        credential, never the actor's session -- a decision log that carried the
        payload would leak exactly what the gateway exists to contain. Refusals
        are recorded as deliberately as grants: a refused authority attempt is
        what an audit log is for.
        """
        try:
            self._ub().store.record_decision(decision)
        except Exception:
            logger.debug("authorization decision store unavailable", exc_info=True)
        try:
            from saathi.security.store import get_store

            get_store().audit(
                f"gateway.authorize.{decision.decision.value.lower()}",
                ok=decision.authorized,
                user_id=decision.actor_user_id,
                detail=(f"{decision.reason_code} intent={decision.intent_id[:32]} "
                        f"digest={decision.intent_digest[:16]} "
                        f"class={decision.authority_class}")[:200],
            )
        except Exception:  # audit must never decide the decision
            logger.debug("authorization audit unavailable", exc_info=True)

    def inspect_decision(self, *, intent_id: str = "", digest: str = "") -> dict | None:
        """Read-only: the last decision recorded for one intent or action.

        Inspection, not a grant. It mutates nothing, and its answer confers
        nothing -- `submit`/`gateway_exec` re-evaluate at execution time, so a
        caller holding a positive decision has not thereby acquired permission.
        """
        try:
            return self._ub().store.latest_decision(intent_id=intent_id, digest=digest)
        except Exception:
            return None

    #: Action risk class → gateway RiskLevel. Deterministic and auditable: the
    #: class comes from the connector registry or the local action table, never
    #: from a heuristic and never from a model.
    _RISK_LEVEL_BY_CLASS = {
        0: RiskLevel.LOW,       # READ_ONLY
        1: RiskLevel.LOW,       # LOCAL_REVERSIBLE
        2: RiskLevel.MEDIUM,    # LOCAL_MUTATION
        3: RiskLevel.HIGH,      # EXTERNAL_SIDE_EFFECT
        4: RiskLevel.CRITICAL,  # HIGH_IMPACT
    }

    def classify_risk(self, intent: ToolIntent, context: ExecutionContext, history: StateHistory) -> tuple[StateHistory, RiskLevel]:
        """Classify execution risk from the action's registered class.

        Previously this returned ``RiskLevel.LOW`` unconditionally, which made
        the approval gate below it decorative -- every action auto-approved
        because every action was low risk. It now reads the same class the
        authorization gate used, so risk and authorization cannot disagree.

        An action this system cannot classify raises rather than defaulting.
        There is no "assume low" path: an unclassifiable action is exactly the
        one whose risk must not be guessed downward.
        """
        from saathi.execution.authorization import resolve_action
        from saathi.execution.authorization_sources import _connector_action

        action = resolve_action(
            str(getattr(intent, "operation", "") or ""),
            str(getattr(intent, "connector_id", "") or ""),
            str(getattr(intent, "capability", "") or ""),
            connector_action=_connector_action(intent),
        )
        if action is None:
            history.add_transition(
                IntentState.REJECTED,
                "risk classification failed: action.unknown",
                metadata={"reason_code": "risk.unknown"},
            )
            raise ExecutionGatewayException("risk.unknown")

        risk_level = self._RISK_LEVEL_BY_CLASS[int(action.risk)]
        history.add_transition(
            IntentState.RISK_CLASSIFIED,
            f"risk classified as {risk_level.value}",
            metadata={"authority_class": action.authority_class.value,
                      "risk_class": action.risk.name,
                      "source": action.source},
        )
        logger.info("Intent risk classified: %s (%s from %s)",
                    intent.intent_id, risk_level.value, action.source)
        return history, risk_level

    def check_approval(self, intent: ToolIntent, risk_level: RiskLevel, history: StateHistory) -> StateHistory:
        """Check if approval is required.

        Low-risk intents auto-approve.
        High-risk intents require human approval (max 1 hour).

        Transitions to APPROVED, or to AWAITING_APPROVAL *and raises*.

        Raising matters. This method previously recorded AWAITING_APPROVAL and
        returned normally, so a caller that did not inspect the history -- which
        is what :class:`~saathi.execution.integration.SaathiExecutionSystem`
        did -- queued and executed the action anyway. It went unnoticed because
        `classify_risk` returned LOW for everything, so the branch was
        unreachable; making risk real made it reachable, and a gate a caller can
        walk past is not a gate.

        Approval itself is decided once, by :meth:`authorize`, against an
        approval correlated to this intent's digest. This method reports that
        decision rather than forming a second opinion from the risk level alone,
        which would otherwise block a high-risk action that *does* hold a valid
        approval.
        """
        decision = self._last_decision
        approved_here = (decision is not None
                         and decision.authorized
                         and decision.intent_id == intent.intent_id)

        if approved_here:
            history.add_transition(
                IntentState.APPROVED,
                f"approval satisfied at authorization (risk={risk_level.value})",
                metadata={"reason_code": decision.reason_code},
            )
            logger.info("Intent approved: %s", intent.intent_id)
            return history

        if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            history.add_transition(
                IntentState.AWAITING_APPROVAL,
                f"approval required (risk={risk_level.value})",
                metadata={"reason_code": "approval.required"},
            )
            logger.info("Intent awaiting approval: %s", intent.intent_id)
            raise ApprovalException("approval.required")

        # Below the approval threshold and not separately authorized here: the
        # action needs no human decision, so this gate has nothing to withhold.
        history.add_transition(
            IntentState.APPROVED,
            f"no approval required (risk={risk_level.value})",
        )
        logger.info("Intent requires no approval: %s", intent.intent_id)
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
            # The machine-safe reason code from the real decision, not prose and
            # not a placeholder. Absent only when authorize() never ran.
            authorization_rationale=(
                self._last_decision.reason_code if self._last_decision
                else "authorization.not_evaluated"),
            approval_required=IntentState.AWAITING_APPROVAL in [
                t.to_state for t in history.transitions],
            sanitized_result=result,
        )

        # Append to audit trail
        if intent.intent_id not in self.audit_trails:
            self.audit_trails[intent.intent_id] = AuditTrail(intent.intent_id)

        self.audit_trails[intent.intent_id].add_evidence(evidence)
        logger.info(f"Evidence recorded: {intent.intent_id}")
        return evidence
