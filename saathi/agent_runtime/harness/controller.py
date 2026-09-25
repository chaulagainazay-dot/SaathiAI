"""HarnessSessionController — trusted platform mediator (FM-I1 / FM-I2).

Owns: session↔run bind, lifecycle validation, event normalization, ToolIntent
construction, approval-required pause, cancel propagation, resource checks,
audit correlation, protocol quarantine.

Does **not** own: authN, RBAC source of truth, approval issuance, credentials,
provider secrets, direct tool execution, gateway replacement, Trading Guardian.

FM-I2 routes ToolIntent through the real ExecutionGateway via
``RealExecutionGatewayAdapter`` (local no-op/echo handlers only).
``GatewayTestDouble`` remains available for isolated unit tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple, Union
import hashlib
import re
import threading
import time
import uuid

from saathi.agent_runtime.harness.audit import HarnessAuditLog
from saathi.agent_runtime.harness.durable_store import HarnessDurableStore
from saathi.agent_runtime.harness.errors import HarnessError, HarnessErrorCode
from saathi.agent_runtime.harness.fake import FakeInMemoryHarness
from saathi.agent_runtime.harness.gateway_bridge import RealExecutionGatewayAdapter
from saathi.agent_runtime.harness.governance import (
    AdmissionRequest,
    HarnessSessionGovernor,
)
from saathi.agent_runtime.harness.governance_policy import (
    AdmissionDecision,
    HarnessResourcePolicy,
)
from saathi.agent_runtime.harness.mapping import project_harness_to_run_state
from saathi.agent_runtime.harness.persistence import (
    DurableSessionRecord,
    RecoveryDisposition,
    RecoveryResult,
    RetentionClass,
    TerminalOutcome,
    map_run_state_snapshot,
    map_terminal_outcome,
)
from saathi.agent_runtime.harness.protocol import AgentHarness
from saathi.agent_runtime.harness.types import (
    ApprovalRefState,
    CancelAck,
    CancelAckStatus,
    EventClassification,
    EventRedactionState,
    HarnessBudget,
    HarnessCapabilityId,
    HarnessEvent,
    HarnessEventType,
    HarnessResourceUsage,
    HarnessSessionHandle,
    HarnessSessionStartRequest,
    HarnessSessionState,
    HarnessTurnHandle,
    HarnessTurnSubmitRequest,
    ProtocolViolationKind,
    SessionCloseResult,
    ToolProposal,
    ToolProposalDisposition,
    is_terminal_harness_state,
    new_id,
)
from saathi.agent_runtime.models import RunState

from saathi.execution.toolintent import (
    ActorType,
    ApprovalLevel,
    BusinessUnit,
    Priority,
    RiskLevel,
    ToolIntent,
)


# Tools the harness proof allows the controller to map into ToolIntent.
# connector_id=local + family=local → EG default safe local handler (echo/noop).
KNOWN_FAKE_TOOLS: Mapping[str, Mapping[str, Any]] = {
    "fake.echo": {
        "capability": "diagnostics",
        "connector_id": "local",
        "operation": "echo",
        "risk_level": RiskLevel.LOW,
        "approval_level": ApprovalLevel.L1,
        "requires_approval": False,
        "family": "local",
    },
    "fake.sensitive_read": {
        "capability": "diagnostics",
        "connector_id": "local",
        # After approval, only the safe local no-op runs (no FS/network).
        "operation": "noop",
        "risk_level": RiskLevel.HIGH,
        "approval_level": ApprovalLevel.L4,
        "requires_approval": True,
        "family": "local",
    },
}

GatewayLike = Union[RealExecutionGatewayAdapter, "GatewayTestDouble", Any]


@dataclass
class MediatedToolResult:
    disposition: ToolProposalDisposition
    proposal_id: str
    tool_intent: Optional[ToolIntent] = None
    redacted_result: Optional[Mapping[str, Any]] = None
    reason: str = ""
    approval_state: ApprovalRefState = ApprovalRefState.NONE
    approval_ref: Optional[str] = None


@dataclass
class _BoundSession:
    session_id: str
    run_id: str
    mission_id: str
    actor_id: str
    organization_id: Optional[str]
    workspace_id: Optional[str]
    authority_class: str
    allowed_tools: Tuple[str, ...]
    budget: HarnessBudget
    projected_run_state: RunState = RunState.CREATED
    last_terminal_run_state: Optional[RunState] = None
    last_seq: int = 0
    seen_event_ids: Set[str] = field(default_factory=set)
    quarantined: bool = False
    quarantine_reason: str = ""
    normalized_events: List[HarnessEvent] = field(default_factory=list)
    approval_refs: Dict[str, ApprovalRefState] = field(default_factory=dict)
    consumed_idempotency_keys: Set[str] = field(default_factory=set)
    pending_proposal_id: Optional[str] = None
    pending_proposal: Optional[ToolProposal] = None
    pending_tool_intent: Optional[ToolIntent] = None
    pending_execution_id: Optional[str] = None
    closed: bool = False


class GatewayTestDouble:
    """Narrow ExecutionGateway test double for isolated unit tests (FM-I1).

    Retained for unit isolation. Production-shaped harness proofs use
    ``RealExecutionGatewayAdapter`` (default since FM-I2).
    Not a shadow production gateway.
    """

    is_real_gateway = False

    def __init__(self) -> None:
        self.submitted: List[ToolIntent] = []
        self.cancelled_intent_ids: List[str] = []
        self.approved_execution_ids: List[str] = []
        self._results_by_idem: Dict[str, Mapping[str, Any]] = {}
        self.deny_all: bool = False
        self.execute: bool = True
        self.raise_on_submit: bool = False

    def submit(
        self,
        intent: ToolIntent,
        *,
        approval_id: str = "",
        execute: Optional[bool] = None,
    ) -> Mapping[str, Any]:
        """Accept a trusted ToolIntent; return redacted synthetic result."""
        _ = approval_id
        if self.raise_on_submit:
            raise RuntimeError("gateway test double failure (injected)")
        errors = intent.validate()
        if errors:
            raise HarnessError(
                HarnessErrorCode.MALFORMED_PROPOSAL,
                f"invalid ToolIntent: {errors[0]}",
                details={"errors": errors},
            )
        if self.deny_all:
            return {
                "ok": False,
                "status": "denied",
                "summary": "gateway test double denied execution",
                "path": "GatewayTestDouble",
                "executed": False,
            }
        # Idempotent replay
        if intent.idempotency_key in self._results_by_idem:
            return dict(self._results_by_idem[intent.idempotency_key])
        self.submitted.append(intent)
        do_execute = self.execute if execute is None else execute
        # Simulated L4 / HIGH risk approval gate (mirrors EG needs_approval)
        needs = intent.approval_level in (ApprovalLevel.L3, ApprovalLevel.L4) or intent.risk_level in (
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        )
        if needs and not approval_id:
            result = {
                "ok": False,
                "status": "approval_required",
                "summary": "awaiting approval (test double)",
                "execution_id": f"td-{intent.intent_id[:8]}",
                "path": "GatewayTestDouble",
                "executed": False,
            }
            return result
        if not do_execute:
            result = {
                "ok": False,
                "status": "not_executed",
                "summary": "execution disabled on test double",
                "path": "GatewayTestDouble",
                "executed": False,
            }
        else:
            result = {
                "ok": True,
                "status": "succeeded",
                "summary": f"fake result for {intent.operation}",
                "echo": dict(intent.parameters),
                "executed": False,  # honesty: no real side effect on double
                "path": "GatewayTestDouble",
                "execution_id": f"td-{intent.intent_id[:8]}",
            }
        self._results_by_idem[intent.idempotency_key] = result
        return dict(result)

    def approve(
        self,
        execution_id: str,
        *,
        intent: ToolIntent,
        approval_id: str = "",
        execute: bool = True,
    ) -> Mapping[str, Any]:
        self.approved_execution_ids.append(execution_id)
        if not execute:
            return {
                "ok": False,
                "status": "approved_pending",
                "summary": "approved but not executed",
                "execution_id": execution_id,
                "path": "GatewayTestDouble",
                "executed": False,
            }
        result = {
            "ok": True,
            "status": "succeeded",
            "summary": f"fake approved result for {intent.operation}",
            "execution_id": execution_id,
            "path": "GatewayTestDouble",
            "executed": False,
            "approval_id": approval_id,
        }
        if intent.idempotency_key:
            self._results_by_idem[intent.idempotency_key] = result
        return result

    def cancel(self, intent_id: str, *, reason: str = "cancelled") -> None:
        _ = reason
        self.cancelled_intent_ids.append(intent_id)

    def cancel_session(self, session_id: str, *, reason: str = "session_cancelled") -> List[str]:
        _ = session_id, reason
        return list(self.cancelled_intent_ids)


class HarnessSessionController:
    """Trusted controller binding AgentHarness sessions to platform run scope."""

    def __init__(
        self,
        harness: AgentHarness,
        *,
        gateway: Optional[GatewayLike] = None,
        audit: Optional[HarnessAuditLog] = None,
        known_tools: Optional[Mapping[str, Mapping[str, Any]]] = None,
        max_sessions: int = 4,
        use_real_gateway: bool = True,
        durable_store: Optional[HarnessDurableStore] = None,
        require_durable_store: bool = False,
        governor: Optional[HarnessSessionGovernor] = None,
        resource_policy: Optional[HarnessResourcePolicy] = None,
        enable_governance: bool = True,
    ) -> None:
        self._harness = harness
        if gateway is not None:
            self._gateway = gateway
        elif use_real_gateway:
            self._gateway = RealExecutionGatewayAdapter(isolated=True)
        else:
            self._gateway = GatewayTestDouble()
        self._audit = audit if audit is not None else HarnessAuditLog()
        self._known_tools = dict(known_tools or KNOWN_FAKE_TOOLS)
        self._max_sessions = max_sessions
        self._sessions: Dict[str, _BoundSession] = {}
        self._lock = threading.RLock()
        self._store = durable_store
        if require_durable_store and durable_store is None:
            raise HarnessError(
                HarnessErrorCode.INVALID_REQUEST,
                "durable_store required but not provided",
            )
        self._governance_enabled = enable_governance
        if governor is not None:
            self._governor = governor
        elif enable_governance:
            from dataclasses import replace as _replace

            from saathi.agent_runtime.harness.governance_policy import (
                HarnessAdmissionPolicy,
                HarnessQueuePolicy,
            )

            # Scale admission/queue with controller max_sessions so unit tests
            # that raise max_sessions keep working under governance.
            base = resource_policy or HarnessResourcePolicy.default()
            adm = HarnessAdmissionPolicy(
                max_active_sessions_global=max(1, max_sessions),
                max_active_sessions_per_org=max(
                    1, min(base.admission.max_active_sessions_per_org, max_sessions)
                    if max_sessions <= 8
                    else max_sessions
                ),
                max_active_sessions_per_workspace=max(
                    1, min(base.admission.max_active_sessions_per_workspace, max_sessions)
                    if max_sessions <= 8
                    else max_sessions
                ),
                max_active_sessions_per_harness=max(1, max_sessions),
                allow_multiple_sessions_per_run=base.admission.allow_multiple_sessions_per_run,
            )
            # Concurrent stress tests use distinct run_ids; allow multi-run.
            if max_sessions > 8:
                adm = _replace(adm, allow_multiple_sessions_per_run=True)
            q = HarnessQueuePolicy(
                max_queued_sessions_global=max(32, max_sessions * 2),
                max_queued_sessions_per_org=max(8, max_sessions),
                max_queued_sessions_per_workspace=max(4, max_sessions),
                age_promotion_seconds=base.queue.age_promotion_seconds,
                priority_ceiling=base.queue.priority_ceiling,
                default_fairness_weight=base.queue.default_fairness_weight,
            )
            pol = _replace(
                base,
                admission=adm,
                queue=q,
                # Keep session-level counters high enough for stress/multi-turn tests
                max_turns_per_session=max(base.max_turns_per_session, 64),
                max_events_per_session=max(base.max_events_per_session, 512),
                max_tool_proposals_per_session=max(base.max_tool_proposals_per_session, 64),
            )
            self._governor = HarnessSessionGovernor(pol)
        else:
            self._governor = None

    @property
    def audit(self) -> HarnessAuditLog:
        return self._audit

    @property
    def gateway(self) -> GatewayLike:
        return self._gateway

    @property
    def durable_store(self) -> Optional[HarnessDurableStore]:
        return self._store

    @property
    def uses_real_gateway(self) -> bool:
        return bool(getattr(self._gateway, "is_real_gateway", False))

    @property
    def governor(self) -> Optional[HarnessSessionGovernor]:
        return self._governor

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def start_session(
        self,
        *,
        run_id: str,
        actor_id: str,
        correlation_id: str,
        mission_id: str = "",
        organization_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        authority_class: str = "READ_ONLY",
        allowed_tool_names: Tuple[str, ...] = ("fake.echo",),
        budget: Optional[HarnessBudget] = None,
        session_id: Optional[str] = None,
        priority: int = 0,
        run_state: Optional[str] = None,
        queue_if_busy: bool = False,
    ) -> HarnessSessionHandle:
        with self._lock:
            return self._start_session_locked(
                run_id=run_id,
                actor_id=actor_id,
                correlation_id=correlation_id,
                mission_id=mission_id,
                organization_id=organization_id,
                workspace_id=workspace_id,
                authority_class=authority_class,
                allowed_tool_names=allowed_tool_names,
                budget=budget,
                session_id=session_id,
                priority=priority,
                run_state=run_state,
                queue_if_busy=queue_if_busy,
            )

    def _start_session_locked(
        self,
        *,
        run_id: str,
        actor_id: str,
        correlation_id: str,
        mission_id: str = "",
        organization_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        authority_class: str = "READ_ONLY",
        allowed_tool_names: Tuple[str, ...] = ("fake.echo",),
        budget: Optional[HarnessBudget] = None,
        session_id: Optional[str] = None,
        priority: int = 0,
        run_state: Optional[str] = None,
        queue_if_busy: bool = False,
    ) -> HarnessSessionHandle:
        if authority_class == "FINANCIAL_EXECUTION":
            raise HarnessError(
                HarnessErrorCode.INVALID_REQUEST,
                "FINANCIAL_EXECUTION is prohibited on harness path",
            )
        if not run_id or not actor_id or not correlation_id:
            raise HarnessError(
                HarnessErrorCode.INVALID_REQUEST,
                "run_id, actor_id, correlation_id required",
            )
        # Capability declaration never grants permission — still require health
        health = self._harness.health()
        if health.status.value == "unhealthy":
            raise HarnessError(
                HarnessErrorCode.INTERNAL,
                "harness unhealthy",
            )
        profile = self._harness.describe_capabilities()
        # Capabilities are descriptive: declaring MULTI_TURN does not open tools
        if not profile.declares(HarnessCapabilityId.SESSION_LIFECYCLE):
            raise HarnessError(
                HarnessErrorCode.INVALID_REQUEST,
                "adapter missing required session_lifecycle capability declaration",
            )

        active = sum(1 for s in self._sessions.values() if not s.closed and not s.quarantined)
        bud = budget or HarnessBudget()
        if active >= min(self._max_sessions, bud.max_concurrent_sessions):
            raise HarnessError(
                HarnessErrorCode.RESOURCE_EXHAUSTED,
                "concurrent session limit reached",
                details={"limit": "max_concurrent_sessions"},
            )

        sid = session_id or new_id("hs-")
        # FM-I4 admission / queue (does not grant tool execution authority)
        if self._governor is not None:
            areq = AdmissionRequest(
                session_id=sid,
                run_id=run_id,
                mission_id=mission_id or run_id,
                organization_id=organization_id or "",
                workspace_id=workspace_id or "",
                actor_id=actor_id,
                harness_id=profile.harness_id,
                correlation_id=correlation_id,
                priority=priority,
                harness_healthy=health.status.value != "unhealthy",
                harness_quarantined=False,
                run_state=run_state,
                # Session budgets may only tighten policy; do not reject for
                # lower session limits. Raise-attempts checked separately if set.
                requested_max_turns=None,
            )
            ares = self._governor.admit(areq)
            # Admission audit is best-effort until session exists; re-recorded after start.
            _admission_detail = {
                "decision": ares.decision,
                "reason": ares.reason,
                "queue_entry_id": ares.queue_entry_id,
                "reservation_id": ares.reservation_id,
            }
            if ares.decision == AdmissionDecision.QUEUE:
                if not queue_if_busy:
                    # Default: reject capacity rather than return half-started session
                    raise HarnessError(
                        HarnessErrorCode.RESOURCE_EXHAUSTED,
                        f"admission queued (capacity): {ares.reason}",
                        session_id=sid,
                        details={
                            "decision": ares.decision,
                            "queue_entry_id": ares.queue_entry_id,
                        },
                    )
                raise HarnessError(
                    HarnessErrorCode.RESOURCE_EXHAUSTED,
                    f"session queued: {ares.queue_entry_id}",
                    session_id=sid,
                    details={
                        "decision": ares.decision,
                        "queue_entry_id": ares.queue_entry_id,
                    },
                )
            if ares.decision != AdmissionDecision.ADMIT_NOW:
                raise HarnessError(
                    HarnessErrorCode.RESOURCE_EXHAUSTED
                    if ares.decision == AdmissionDecision.REJECT_CAPACITY
                    else HarnessErrorCode.INVALID_REQUEST,
                    f"admission rejected: {ares.decision}: {ares.reason}",
                    session_id=sid,
                    details={"decision": ares.decision, "reason": ares.reason},
                )
        # Scope isolation: session_id cannot move across org/workspace
        if sid in self._sessions:
            bound = self._sessions[sid]
            if (
                bound.organization_id != organization_id
                or bound.workspace_id != workspace_id
                or bound.actor_id != actor_id
            ):
                self._quarantine(sid, ProtocolViolationKind.SCOPE_MISMATCH, "scope rebind denied")
                raise HarnessError(
                    HarnessErrorCode.SCOPE_MISMATCH,
                    "session_id cannot move across organization/workspace scope",
                    session_id=sid,
                )
            # Idempotent re-start
            return self._harness_handle_for(sid)

        req = HarnessSessionStartRequest(
            session_id=sid,
            actor_id=actor_id,
            correlation_id=correlation_id,
            run_id=run_id,
            mission_id=mission_id or run_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            authority_class=authority_class,
            allowed_tool_names=tuple(allowed_tool_names),
            budget=bud,
        )
        handle = self._harness.start_session(req)
        projected = project_harness_to_run_state(handle.state)
        bound = _BoundSession(
            session_id=sid,
            run_id=run_id,
            mission_id=mission_id or run_id,
            actor_id=actor_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            authority_class=authority_class,
            allowed_tools=tuple(allowed_tool_names),
            budget=bud,
            projected_run_state=projected,
        )
        self._sessions[sid] = bound
        # Durable session create (fail closed if store present and write fails)
        if self._store is not None:
            try:
                drec = DurableSessionRecord(
                    session_id=sid,
                    harness_id=handle.harness_id,
                    run_id=run_id,
                    mission_id=mission_id or run_id,
                    organization_id=organization_id or "",
                    workspace_id=workspace_id or "",
                    actor_id=actor_id,
                    projected_harness_state=handle.state.value,
                    authoritative_run_state_snapshot=map_run_state_snapshot(projected),
                    retention_class=RetentionClass.ACTIVE.value,
                )
                self._store.create_session(drec)
            except HarnessError:
                # Remove in-memory bind on durable failure
                self._sessions.pop(sid, None)
                raise
            except Exception as exc:  # noqa: BLE001
                self._sessions.pop(sid, None)
                raise HarnessError(
                    HarnessErrorCode.INTERNAL,
                    f"durable session create failed: {exc}",
                    session_id=sid,
                ) from exc
        self._ingest_events(sid)
        try:
            if self._governor is not None:
                self._audit.record(
                    "harness.admission",
                    session_id=sid,
                    run_id=run_id,
                    correlation_id=correlation_id,
                    detail=locals().get("_admission_detail") or {"decision": "ADMIT_NOW"},
                )
            self._audit.record(
                "harness.session_started",
                session_id=sid,
                run_id=run_id,
                correlation_id=correlation_id,
                detail={"authority_class": authority_class, "org": organization_id},
            )
        except RuntimeError as exc:
            # Audit failure must not leave a live untracked session: quarantine fail-closed
            bound.quarantined = True
            bound.quarantine_reason = f"audit_write_failed: {exc}"
            if self._governor is not None:
                self._governor.release(sid, reason="audit_write_failed")
            self._persist_quarantine(sid, bound.quarantine_reason)
            raise HarnessError(
                HarnessErrorCode.INTERNAL,
                "audit write failed; session quarantined",
                session_id=sid,
            ) from exc
        return handle

    def submit_turn(
        self,
        session_id: str,
        *,
        input_text: str,
        correlation_id: str,
        turn_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> HarnessTurnHandle:
        with self._lock:
            return self._submit_turn_locked(
                session_id,
                input_text=input_text,
                correlation_id=correlation_id,
                turn_id=turn_id,
                causation_id=causation_id,
            )

    def _submit_turn_locked(
        self,
        session_id: str,
        *,
        input_text: str,
        correlation_id: str,
        turn_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> HarnessTurnHandle:
        bound = self._require_bound(session_id)
        if bound.quarantined:
            raise HarnessError(
                HarnessErrorCode.QUARANTINED,
                bound.quarantine_reason or "session quarantined",
                session_id=session_id,
            )
        if bound.closed:
            raise HarnessError(
                HarnessErrorCode.TERMINAL_SESSION,
                "session closed",
                session_id=session_id,
            )
        # Resource: turn budget at controller layer too
        usage = self._harness.resource_usage(session_id)
        if usage.turns >= bound.budget.max_turns:
            self._project_terminal(bound, HarnessSessionState.FAILED)
            raise HarnessError(
                HarnessErrorCode.RESOURCE_EXHAUSTED,
                "max_turns exceeded",
                session_id=session_id,
                details={"limit": "max_turns"},
            )

        tid = turn_id or new_id("ht-")
        req = HarnessTurnSubmitRequest(
            session_id=session_id,
            turn_id=tid,
            input_text=input_text,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        handle = self._harness.submit_turn(req)
        self._ingest_events(session_id)
        # FM-I4 live resource accounting + timeout enforcement
        if self._governor is not None:
            usage = self._harness.resource_usage(session_id)
            viol = self._governor.record_activity(
                session_id,
                turns=usage.turns,
                events=usage.events,
                output_chars=usage.output_chars,
                logical_tokens=usage.fake_tokens,
                tool_proposals=usage.tool_proposals,
                absolute=True,
            )
            if viol:
                self._audit.record(
                    "harness.resource_limit",
                    session_id=session_id,
                    run_id=bound.run_id,
                    detail={"limit": viol},
                )
                try:
                    self.request_cancel(session_id, reason=f"resource_limit:{viol}")
                except HarnessError:
                    pass
                raise HarnessError(
                    HarnessErrorCode.RESOURCE_EXHAUSTED,
                    f"resource limit: {viol}",
                    session_id=session_id,
                    details={"limit": viol},
                )
        self._audit.record(
            "harness.turn_submitted",
            session_id=session_id,
            run_id=bound.run_id,
            correlation_id=correlation_id,
            detail={"turn_id": tid},
        )
        # Auto-mediate any tool proposals emitted
        self._mediate_pending_proposals(session_id)
        return handle

    def request_cancel(self, session_id: str, reason: str = "run_cancelled") -> CancelAck:
        with self._lock:
            bound = self._require_bound(session_id)
            # Cancel pending gateway work via real EG (or double)
            if hasattr(self._gateway, "cancel_session"):
                self._gateway.cancel_session(session_id, reason=reason)
            else:
                for intent in list(getattr(self._gateway, "submitted", [])):
                    if (intent.metadata or {}).get("session_id") == session_id:
                        eid = getattr(intent, "intent_id", "")
                        self._gateway.cancel(eid, reason=reason)
            if bound.pending_execution_id:
                try:
                    self._gateway.cancel(bound.pending_execution_id, reason=reason)
                except Exception:
                    pass
                bound.pending_execution_id = None

            if self._governor is not None:
                self._governor.mark_cancel_requested(session_id)
                self._governor.cancel_queued(session_id, reason=reason)

            try:
                ack = self._harness.request_cancel(session_id, reason)
            except HarnessError as exc:
                # Fail-closed: mark cancelled projection even if ack fails
                bound.projected_run_state = RunState.FAILED
                bound.last_terminal_run_state = RunState.FAILED
                try:
                    self._audit.record(
                        "harness.cancellation_failed_closed",
                        session_id=session_id,
                        run_id=bound.run_id,
                        detail={"error": exc.code, "reason": reason},
                    )
                except RuntimeError:
                    pass
                raise

            self._ingest_events(session_id)
            if ack.status in (CancelAckStatus.ACKNOWLEDGED, CancelAckStatus.ALREADY_TERMINAL):
                bound.projected_run_state = RunState.CANCELLED
                bound.last_terminal_run_state = RunState.CANCELLED
                if self._governor is not None:
                    self._governor.release(session_id, reason=reason or "cancelled")
                if self._store is not None:
                    try:
                        self._persist_session_fields(
                            bound,
                            projected_harness_state=HarnessSessionState.CANCELLED.value,
                            authoritative_run_state_snapshot=RunState.CANCELLED.value,
                            terminal_outcome=TerminalOutcome.CANCELLED.value,
                            retention_class=RetentionClass.CANCELLED.value,
                            cancellation_requested_at=time.time(),
                            cancellation_acknowledged_at=time.time(),
                            pending_execution_id="",
                            pending_approval_reference="",
                            pending_tool_proposal_id="",
                        )
                    except HarnessError:
                        pass
            try:
                self._audit.record(
                    "harness.cancellation",
                    session_id=session_id,
                    run_id=bound.run_id,
                    detail={"status": ack.status.value, "reason": reason},
                )
            except RuntimeError:
                # Cancel already applied; audit failure is recorded as quarantine risk
                bound.quarantined = True
                bound.quarantine_reason = "audit_write_failed_after_cancel"
                self._persist_quarantine(session_id, bound.quarantine_reason)
            return ack

    def close_session(self, session_id: str, reason: str = "closed") -> SessionCloseResult:
        with self._lock:
            bound = self._require_bound(session_id)
            result = self._harness.close_session(session_id, reason)
            bound.closed = True
            self._ingest_events(session_id)
            bound.projected_run_state = project_harness_to_run_state(
                HarnessSessionState.CLOSED,
                prior_terminal_run=bound.last_terminal_run_state,
            )
            if self._governor is not None:
                self._governor.release(session_id, reason=reason or "closed")
            if self._store is not None:
                try:
                    term = (
                        map_terminal_outcome(
                            HarnessSessionState.CANCELLED
                            if bound.last_terminal_run_state is RunState.CANCELLED
                            else HarnessSessionState.COMPLETED
                        ).value
                    )
                    if bound.last_terminal_run_state is RunState.FAILED:
                        term = TerminalOutcome.FAILED.value
                    elif bound.last_terminal_run_state is RunState.TIMED_OUT:
                        term = TerminalOutcome.TIMED_OUT.value
                    self._persist_session_fields(
                        bound,
                        closed=True,
                        projected_harness_state=HarnessSessionState.CLOSED.value,
                        authoritative_run_state_snapshot=map_run_state_snapshot(
                            bound.projected_run_state
                        ),
                        terminal_outcome=term,
                        retention_class=(
                            RetentionClass.CANCELLED.value
                            if term == TerminalOutcome.CANCELLED.value
                            else RetentionClass.COMPLETED.value
                        ),
                    )
                except HarnessError:
                    pass
            try:
                self._audit.record(
                    "harness.session_closed",
                    session_id=session_id,
                    run_id=bound.run_id,
                    detail={"reason": reason, "already_closed": result.already_closed},
                )
            except RuntimeError:
                bound.quarantined = True
                bound.quarantine_reason = "audit_write_failed_after_close"
                self._persist_quarantine(session_id, bound.quarantine_reason)
            return result

    def poll_events(self, session_id: str, after_seq: int = 0) -> List[HarnessEvent]:
        with self._lock:
            self._ingest_events(session_id)
            bound = self._require_bound(session_id)
            return [e for e in bound.normalized_events if e.sequence_number > after_seq]

    def projected_run_state(self, session_id: str) -> RunState:
        return self._require_bound(session_id).projected_run_state

    def harness_state(self, session_id: str) -> HarnessSessionState:
        if isinstance(self._harness, FakeInMemoryHarness):
            return self._harness.get_state(session_id)
        # Fall back to last projected
        events = self.poll_events(session_id)
        if not events:
            return HarnessSessionState.CREATED
        last = events[-1]
        mapping = {
            HarnessEventType.SESSION_READY: HarnessSessionState.READY,
            HarnessEventType.TURN_ACCEPTED: HarnessSessionState.RUNNING,
            HarnessEventType.TOOL_PROPOSAL: HarnessSessionState.WAITING_FOR_TOOL,
            HarnessEventType.APPROVAL_REQUIRED: HarnessSessionState.WAITING_FOR_APPROVAL,
            HarnessEventType.SESSION_COMPLETED: HarnessSessionState.COMPLETED,
            HarnessEventType.SESSION_FAILED: HarnessSessionState.FAILED,
            HarnessEventType.SESSION_TIMED_OUT: HarnessSessionState.TIMED_OUT,
            HarnessEventType.CANCELLATION_ACKNOWLEDGED: HarnessSessionState.CANCELLED,
            HarnessEventType.SESSION_CLOSED: HarnessSessionState.CLOSED,
        }
        return mapping.get(last.event_type, HarnessSessionState.RUNNING)

    def is_quarantined(self, session_id: str) -> bool:
        return self._require_bound(session_id).quarantined

    def resource_usage(self, session_id: str) -> HarnessResourceUsage:
        return self._harness.resource_usage(session_id)

    def resolve_approval(
        self,
        session_id: str,
        approval_ref: str,
        *,
        decision: ApprovalRefState,
    ) -> None:
        """Apply an external approval decision (controller does not issue approvals)."""
        bound = self._require_bound(session_id)
        current = bound.approval_refs.get(approval_ref, ApprovalRefState.NONE)
        if current is ApprovalRefState.CONSUMED:
            raise HarnessError(
                HarnessErrorCode.APPROVAL_INVALID,
                "approval already consumed",
                session_id=session_id,
            )
        if decision not in (
            ApprovalRefState.APPROVED,
            ApprovalRefState.DENIED,
            ApprovalRefState.EXPIRED,
            ApprovalRefState.REVOKED,
        ):
            raise HarnessError(
                HarnessErrorCode.APPROVAL_INVALID,
                f"invalid decision {decision}",
                session_id=session_id,
            )
        bound.approval_refs[approval_ref] = decision
        self._audit.record(
            "harness.approval_resolved",
            session_id=session_id,
            run_id=bound.run_id,
            detail={"approval_ref": approval_ref, "decision": decision.value},
        )
        if decision is ApprovalRefState.APPROVED and bound.pending_proposal is not None:
            proposal = bound.pending_proposal
            intent = bound.pending_tool_intent
            execution_id = bound.pending_execution_id or ""
            bound.approval_refs[approval_ref] = ApprovalRefState.APPROVED
            if intent is not None and execution_id and hasattr(self._gateway, "approve"):
                try:
                    result = self._gateway.approve(
                        execution_id,
                        intent=intent,
                        approval_id=approval_ref,
                        execute=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    result = {
                        "ok": False,
                        "status": "failed",
                        "summary": f"approval apply failed: {exc}",
                        "executed": False,
                    }
                if result.get("ok"):
                    if isinstance(self._harness, FakeInMemoryHarness):
                        try:
                            self._harness.deliver_tool_result(
                                session_id,
                                turn_id=proposal.turn_id,
                                correlation_id=proposal.correlation_id,
                                result=result,
                                denied=False,
                            )
                            self._ingest_events(session_id)
                        except HarnessError:
                            pass
                else:
                    if isinstance(self._harness, FakeInMemoryHarness):
                        try:
                            self._harness.deliver_tool_result(
                                session_id,
                                turn_id=proposal.turn_id,
                                correlation_id=proposal.correlation_id,
                                result=result,
                                denied=True,
                            )
                            self._ingest_events(session_id)
                        except HarnessError:
                            pass
            else:
                # Fallback: re-mediate with double-style path
                mediated = self.mediate_proposal(proposal)
                if mediated.disposition is ToolProposalDisposition.ACCEPTED:
                    if isinstance(self._harness, FakeInMemoryHarness):
                        try:
                            self._harness.deliver_tool_result(
                                session_id,
                                turn_id=proposal.turn_id,
                                correlation_id=proposal.correlation_id,
                                result=mediated.redacted_result or {"summary": "approved"},
                                denied=False,
                            )
                            self._ingest_events(session_id)
                        except HarnessError:
                            pass
            bound.approval_refs[approval_ref] = ApprovalRefState.CONSUMED
            bound.pending_proposal = None
            bound.pending_proposal_id = None
            bound.pending_tool_intent = None
            bound.pending_execution_id = None
        elif decision in (
            ApprovalRefState.DENIED,
            ApprovalRefState.EXPIRED,
            ApprovalRefState.REVOKED,
        ):
            proposal = bound.pending_proposal
            if bound.pending_execution_id:
                try:
                    self._gateway.cancel(
                        bound.pending_execution_id,
                        reason=f"approval_{decision.value}",
                    )
                except Exception:
                    pass
            if isinstance(self._harness, FakeInMemoryHarness) and proposal is not None:
                try:
                    self._harness.deliver_tool_result(
                        session_id,
                        turn_id=proposal.turn_id,
                        correlation_id=proposal.correlation_id,
                        result={"summary": f"approval {decision.value}"},
                        denied=True,
                    )
                    self._ingest_events(session_id)
                except HarnessError:
                    pass
            bound.pending_proposal = None
            bound.pending_proposal_id = None
            bound.pending_tool_intent = None
            bound.pending_execution_id = None

    # ── Tool mediation ──────────────────────────────────────────────────────

    def mediate_proposal(self, proposal: ToolProposal) -> MediatedToolResult:
        """Validate proposal and build ToolIntent; never let harness authorize."""
        with self._lock:
            return self._mediate_proposal_locked(proposal)

    def _mediate_proposal_locked(self, proposal: ToolProposal) -> MediatedToolResult:
        bound = self._require_bound(proposal.session_id)
        if bound.quarantined:
            return MediatedToolResult(
                disposition=ToolProposalDisposition.QUARANTINED,
                proposal_id=proposal.proposal_id,
                reason="session quarantined",
            )
        if bound.closed or bound.projected_run_state in (
            RunState.CANCELLED,
            RunState.FAILED,
            RunState.TIMED_OUT,
            RunState.COMPLETED,
        ):
            return MediatedToolResult(
                disposition=ToolProposalDisposition.CANCELLED,
                proposal_id=proposal.proposal_id,
                reason="session terminal",
            )

        # Correlation required
        if not proposal.correlation_id:
            self._quarantine(
                proposal.session_id,
                ProtocolViolationKind.MISSING_CORRELATION,
                "missing correlation_id on proposal",
            )
            return MediatedToolResult(
                disposition=ToolProposalDisposition.QUARANTINED,
                proposal_id=proposal.proposal_id,
                reason="missing correlation_id",
            )

        # Malformed
        if not proposal.tool_name or not isinstance(proposal.parameters, Mapping):
            self._audit.record(
                "harness.tool_proposal_denied",
                session_id=proposal.session_id,
                run_id=bound.run_id,
                correlation_id=proposal.correlation_id,
                detail={"reason": "malformed", "tool": proposal.tool_name},
            )
            return MediatedToolResult(
                disposition=ToolProposalDisposition.DENIED,
                proposal_id=proposal.proposal_id,
                reason="malformed proposal",
            )

        # Scope
        if (
            proposal.organization_id != bound.organization_id
            or proposal.workspace_id != bound.workspace_id
        ):
            self._quarantine(
                proposal.session_id,
                ProtocolViolationKind.SCOPE_MISMATCH,
                "proposal scope mismatch",
            )
            return MediatedToolResult(
                disposition=ToolProposalDisposition.QUARANTINED,
                proposal_id=proposal.proposal_id,
                reason="scope mismatch",
            )

        # Unknown / not allowlisted
        if proposal.tool_name not in self._known_tools:
            self._audit.record(
                "harness.tool_proposal_denied",
                session_id=proposal.session_id,
                run_id=bound.run_id,
                correlation_id=proposal.correlation_id,
                detail={"reason": "unknown_tool", "tool": proposal.tool_name},
            )
            return MediatedToolResult(
                disposition=ToolProposalDisposition.DENIED,
                proposal_id=proposal.proposal_id,
                reason="unknown tool",
            )
        if proposal.tool_name not in bound.allowed_tools:
            self._audit.record(
                "harness.tool_proposal_denied",
                session_id=proposal.session_id,
                run_id=bound.run_id,
                correlation_id=proposal.correlation_id,
                detail={"reason": "not_allowlisted", "tool": proposal.tool_name},
            )
            return MediatedToolResult(
                disposition=ToolProposalDisposition.DENIED,
                proposal_id=proposal.proposal_id,
                reason="tool not allowlisted",
            )

        tool_meta = self._known_tools[proposal.tool_name]
        idem = proposal.idempotency_key or ToolIntent.compute_idempotency_key(
            {
                "session_id": proposal.session_id,
                "turn_id": proposal.turn_id,
                "tool": proposal.tool_name,
                "params": dict(proposal.parameters),
            }
        )
        if len(idem) != 64:
            idem = hashlib.sha256(idem.encode()).hexdigest()

        # Trusted ToolIntent construction (controller only — never the harness)
        try:
            corr = proposal.correlation_id
            try:
                uuid.UUID(corr, version=4)
            except (ValueError, TypeError):
                corr = str(uuid.uuid4())

            intent = ToolIntent(
                actor_id=bound.actor_id,
                actor_type=ActorType.AGENT,
                mission_id=bound.mission_id or bound.run_id,
                capability=str(tool_meta["capability"]),
                connector_id=str(tool_meta["connector_id"]),
                operation=str(tool_meta["operation"]),
                parameters=dict(proposal.parameters),
                reason=f"harness proposal {proposal.proposal_id}",
                risk_level=tool_meta["risk_level"],
                approval_level=tool_meta["approval_level"],
                idempotency_key=idem,
                priority=Priority.NORMAL,
                business_unit=BusinessUnit.MR_YETI,
                correlation_id=corr,
                timeout=30,
                metadata={
                    "session_id": proposal.session_id,
                    "turn_id": proposal.turn_id,
                    "run_id": bound.run_id,
                    "mission_id": bound.mission_id,
                    "organization_id": bound.organization_id,
                    "workspace_id": bound.workspace_id,
                    "proposal_id": proposal.proposal_id,
                    "harness_id": "fake-in-memory",
                    "source": "HarnessSessionController",
                    "family": str(tool_meta.get("family") or "local"),
                },
            )
        except Exception as exc:  # noqa: BLE001 — fail closed
            return MediatedToolResult(
                disposition=ToolProposalDisposition.DENIED,
                proposal_id=proposal.proposal_id,
                reason=f"toolintent construction failed: {exc}",
            )

        errors = intent.validate()
        if errors:
            return MediatedToolResult(
                disposition=ToolProposalDisposition.DENIED,
                proposal_id=proposal.proposal_id,
                reason=f"invalid intent: {errors[0]}",
            )

        # Idempotent retry: same key must not double-execute side effects
        if idem in bound.consumed_idempotency_keys:
            existing = self._gateway.submit(intent)
            return MediatedToolResult(
                disposition=ToolProposalDisposition.ACCEPTED
                if existing.get("ok")
                else ToolProposalDisposition.DENIED,
                proposal_id=proposal.proposal_id,
                tool_intent=intent,
                redacted_result=existing,
                reason="idempotent replay",
            )

        try:
            result = self._gateway.submit(intent)
        except Exception as exc:  # noqa: BLE001 — gateway double / seam failure
            self._audit.record(
                "harness.gateway_failure",
                session_id=proposal.session_id,
                run_id=bound.run_id,
                correlation_id=proposal.correlation_id,
                detail={"error": str(exc)[:200]},
            )
            return MediatedToolResult(
                disposition=ToolProposalDisposition.DENIED,
                proposal_id=proposal.proposal_id,
                reason=f"gateway failure: {exc}",
            )

        # Real EG (or double) requested human approval — harness must not self-approve
        if result.get("status") == "approval_required":
            approval_ref = f"apr-{proposal.proposal_id}"
            bound.approval_refs[approval_ref] = ApprovalRefState.PENDING
            bound.pending_proposal_id = proposal.proposal_id
            bound.pending_proposal = proposal
            bound.pending_tool_intent = intent
            bound.pending_execution_id = str(result.get("execution_id") or "")
            bound.projected_run_state = RunState.AWAITING_APPROVAL
            self._audit.record(
                "harness.approval_required",
                session_id=proposal.session_id,
                run_id=bound.run_id,
                correlation_id=proposal.correlation_id,
                detail={
                    "approval_ref": approval_ref,
                    "tool": proposal.tool_name,
                    "proposal_id": proposal.proposal_id,
                    "execution_id": bound.pending_execution_id,
                    "gateway_path": result.get("path"),
                },
            )
            if self._store is not None:
                try:
                    self._persist_session_fields(
                        bound,
                        projected_harness_state=HarnessSessionState.WAITING_FOR_APPROVAL.value,
                        authoritative_run_state_snapshot=RunState.AWAITING_APPROVAL.value,
                        pending_execution_id=bound.pending_execution_id or "",
                        pending_approval_reference=approval_ref,
                        pending_tool_proposal_id=proposal.proposal_id,
                    )
                except HarnessError:
                    raise
            return MediatedToolResult(
                disposition=ToolProposalDisposition.APPROVAL_REQUIRED,
                proposal_id=proposal.proposal_id,
                tool_intent=intent,
                redacted_result=result,
                reason="approval required",
                approval_state=ApprovalRefState.PENDING,
                approval_ref=approval_ref,
            )

        if result.get("ok"):
            bound.consumed_idempotency_keys.add(idem)
            disposition = ToolProposalDisposition.ACCEPTED
        else:
            disposition = ToolProposalDisposition.DENIED
            if result.get("status") in ("succeeded",):
                disposition = ToolProposalDisposition.ACCEPTED
                bound.consumed_idempotency_keys.add(idem)

        self._audit.record(
            "harness.tool_mediated",
            session_id=proposal.session_id,
            run_id=bound.run_id,
            correlation_id=proposal.correlation_id,
            detail={
                "proposal_id": proposal.proposal_id,
                "tool": proposal.tool_name,
                "disposition": disposition.value,
                "intent_id": intent.intent_id,
                "execution_id": result.get("execution_id"),
                "gateway_path": result.get("path"),
                "gateway_status": result.get("status"),
                "executed": bool(result.get("executed")),
            },
        )
        return MediatedToolResult(
            disposition=disposition,
            proposal_id=proposal.proposal_id,
            tool_intent=intent,
            redacted_result=result,
            reason="mediated",
            approval_state=ApprovalRefState.NONE,
        )

    def _mediate_pending_proposals(
        self,
        session_id: str,
        *,
        approved_ref: Optional[str] = None,
    ) -> List[MediatedToolResult]:
        results: List[MediatedToolResult] = []
        if not isinstance(self._harness, FakeInMemoryHarness):
            return results
        while True:
            proposal = self._harness.pop_pending_proposal(session_id)
            if proposal is None:
                break
            # If approval was just granted, mark APPROVED before mediate
            if approved_ref and proposal.tool_name == "fake.sensitive_read":
                bound = self._sessions[session_id]
                bound.approval_refs[approved_ref] = ApprovalRefState.APPROVED
            mediated = self.mediate_proposal(proposal)
            results.append(mediated)
            bound = self._sessions[session_id]
            if mediated.disposition is ToolProposalDisposition.APPROVAL_REQUIRED:
                bound.pending_proposal_id = proposal.proposal_id
                bound.pending_proposal = proposal
                break
            if mediated.disposition is ToolProposalDisposition.DENIED:
                try:
                    self._harness.deliver_tool_result(
                        session_id,
                        turn_id=proposal.turn_id,
                        correlation_id=proposal.correlation_id,
                        result=mediated.redacted_result or {"summary": mediated.reason},
                        denied=True,
                    )
                except HarnessError:
                    pass
                self._ingest_events(session_id)
            elif mediated.disposition is ToolProposalDisposition.ACCEPTED:
                try:
                    self._harness.deliver_tool_result(
                        session_id,
                        turn_id=proposal.turn_id,
                        correlation_id=proposal.correlation_id,
                        result=mediated.redacted_result or {"summary": "ok"},
                        denied=False,
                    )
                except HarnessError:
                    pass
                self._ingest_events(session_id)
            elif mediated.disposition is ToolProposalDisposition.QUARANTINED:
                break
        return results

    # ── Event normalization ─────────────────────────────────────────────────

    def _ingest_events(self, session_id: str) -> None:
        bound = self._require_bound(session_id)
        if bound.quarantined:
            return
        # Full stream scan so injected regression/duplicate events with
        # sequence_number <= watermark are still observed and fail-closed.
        raw = list(self._harness.poll_events(session_id, after_seq=0))
        seen_in_stream: Set[str] = set()
        for ev in raw:
            if ev.event_id in seen_in_stream:
                self._quarantine(
                    bound.session_id,
                    ProtocolViolationKind.DUPLICATE_EVENT_ID,
                    f"duplicate event_id in stream {ev.event_id}",
                )
                return
            seen_in_stream.add(ev.event_id)
            if ev.event_id in bound.seen_event_ids:
                # Already accepted on a prior ingest pass.
                continue
            if self._validate_event(bound, ev):
                bound.normalized_events.append(ev)
                bound.last_seq = max(bound.last_seq, ev.sequence_number)
                bound.seen_event_ids.add(ev.event_id)
                self._update_projection_from_event(bound, ev)
                # Durable append must succeed before event is considered committed
                # for recovery/replay (fail closed if store present).
                self._persist_event(bound, ev)
            else:
                # Quarantine already applied inside _validate_event
                return

    def _validate_event(self, bound: _BoundSession, ev: HarnessEvent) -> bool:
        # Post-close events (except the close event itself) → quarantine
        if bound.closed and ev.event_type is not HarnessEventType.SESSION_CLOSED:
            if any(
                e.event_type is HarnessEventType.SESSION_CLOSED
                for e in bound.normalized_events
            ):
                self._quarantine(
                    bound.session_id,
                    ProtocolViolationKind.EVENT_AFTER_CLOSE,
                    f"event {ev.event_id} after close",
                )
                return False

        # Post-terminal non-terminal events fail closed (except close/cancel ack/fail reports)
        terminal_projected = bound.last_terminal_run_state is not None
        if terminal_projected and ev.event_type in (
            HarnessEventType.TURN_ACCEPTED,
            HarnessEventType.TEXT_DELTA,
            HarnessEventType.TOOL_PROPOSAL,
        ):
            self._quarantine(
                bound.session_id,
                ProtocolViolationKind.LATE_EVENT,
                f"active event {ev.event_type.value} after terminal projection",
            )
            return False

        if ev.event_id in bound.seen_event_ids:
            self._quarantine(
                bound.session_id,
                ProtocolViolationKind.DUPLICATE_EVENT_ID,
                f"duplicate event_id {ev.event_id}",
            )
            return False
        if ev.sequence_number <= bound.last_seq:
            self._quarantine(
                bound.session_id,
                ProtocolViolationKind.SEQUENCE_REGRESSION,
                f"seq {ev.sequence_number} <= {bound.last_seq}",
            )
            return False
        # Sequence gaps are forbidden for the fake/controller protocol (fail closed).
        if bound.last_seq and ev.sequence_number > bound.last_seq + 1:
            self._quarantine(
                bound.session_id,
                ProtocolViolationKind.SEQUENCE_GAP,
                f"seq gap {bound.last_seq} → {ev.sequence_number}",
            )
            return False
        if ev.session_id != bound.session_id:
            self._quarantine(
                bound.session_id,
                ProtocolViolationKind.FORGED_EVENT,
                "session_id mismatch on event",
            )
            return False
        if ev.run_id is not None and bound.run_id and ev.run_id != bound.run_id:
            self._quarantine(
                bound.session_id,
                ProtocolViolationKind.FORGED_EVENT,
                "run_id mismatch on event",
            )
            return False
        if (
            ev.mission_id is not None
            and bound.mission_id
            and ev.mission_id != bound.mission_id
        ):
            self._quarantine(
                bound.session_id,
                ProtocolViolationKind.FORGED_EVENT,
                "mission_id mismatch on event",
            )
            return False
        if (
            ev.organization_id is not None
            and bound.organization_id is not None
            and ev.organization_id != bound.organization_id
        ):
            self._quarantine(
                bound.session_id,
                ProtocolViolationKind.SCOPE_MISMATCH,
                "event organization mismatch",
            )
            return False
        if (
            ev.workspace_id is not None
            and bound.workspace_id is not None
            and ev.workspace_id != bound.workspace_id
        ):
            self._quarantine(
                bound.session_id,
                ProtocolViolationKind.SCOPE_MISMATCH,
                "event workspace mismatch",
            )
            return False

        payload = dict(ev.payload)
        # Reject secret-shaped payload keys fail-closed (not merely strip).
        # Use whole-key / boundary patterns so resource counters like
        # ``fake_tokens`` are not false positives.
        secret_re = re.compile(
            r"^(password|secret|api[_-]?key|private[_-]?key|token|access_token|"
            r"refresh_token|id_token|authorization|bearer|auth_token)$",
            re.IGNORECASE,
        )
        for key in payload:
            if secret_re.match(str(key)):
                self._quarantine(
                    bound.session_id,
                    ProtocolViolationKind.SECRET_PAYLOAD,
                    f"secret-shaped payload key: {key}",
                )
                return False
        for banned in ("chain_of_thought", "private_cot", "hidden_reasoning", "raw_cot"):
            if banned in payload:
                self._audit.record(
                    "harness.cot_stripped",
                    session_id=bound.session_id,
                    run_id=bound.run_id,
                    detail={"key": banned, "event_id": ev.event_id},
                )
                # Strip is not enough for controller-normalized path: refuse event
                self._quarantine(
                    bound.session_id,
                    ProtocolViolationKind.FORGED_EVENT,
                    f"private reasoning key present: {banned}",
                )
                return False
        return True

    def _update_projection_from_event(self, bound: _BoundSession, ev: HarnessEvent) -> None:
        if bound.quarantined:
            return
        mapping = {
            HarnessEventType.SESSION_STARTED: RunState.RUNNING,
            HarnessEventType.SESSION_READY: RunState.RUNNING,
            HarnessEventType.TURN_ACCEPTED: RunState.RUNNING,
            HarnessEventType.TEXT_DELTA: RunState.RUNNING,
            HarnessEventType.TOOL_PROPOSAL: RunState.RUNNING,
            HarnessEventType.APPROVAL_REQUIRED: RunState.AWAITING_APPROVAL,
            HarnessEventType.SESSION_COMPLETED: RunState.COMPLETED,
            HarnessEventType.SESSION_FAILED: RunState.FAILED,
            HarnessEventType.SESSION_TIMED_OUT: RunState.TIMED_OUT,
            HarnessEventType.CANCELLATION_ACKNOWLEDGED: RunState.CANCELLED,
            HarnessEventType.SESSION_CLOSED: bound.last_terminal_run_state or RunState.COMPLETED,
        }
        if ev.event_type in mapping:
            new_state = mapping[ev.event_type]
            bound.projected_run_state = new_state
            if new_state in (
                RunState.COMPLETED,
                RunState.FAILED,
                RunState.CANCELLED,
                RunState.TIMED_OUT,
            ):
                bound.last_terminal_run_state = new_state

    def _append_controller_event(
        self,
        bound: _BoundSession,
        event_type: HarnessEventType,
        payload: Mapping[str, Any],
        *,
        turn_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        bound.last_seq += 1
        ev = HarnessEvent(
            event_id=str(uuid.uuid4()),
            session_id=bound.session_id,
            sequence_number=bound.last_seq,
            event_type=event_type,
            harness_id="controller",
            timestamp=time.time(),
            payload=dict(payload),
            turn_id=turn_id,
            run_id=bound.run_id,
            mission_id=bound.mission_id,
            organization_id=bound.organization_id,
            workspace_id=bound.workspace_id,
            correlation_id=correlation_id,
            classification=EventClassification.INTERNAL,
            redaction_state=EventRedactionState.NONE,
        )
        bound.normalized_events.append(ev)
        bound.seen_event_ids.add(ev.event_id)
        self._update_projection_from_event(bound, ev)

    def _quarantine(
        self,
        session_id: str,
        kind: ProtocolViolationKind,
        reason: str,
    ) -> None:
        bound = self._sessions.get(session_id)
        if bound is None:
            return
        bound.quarantined = True
        bound.quarantine_reason = f"{kind.value}: {reason}"
        try:
            self._audit.record(
                "harness.protocol_violation",
                session_id=session_id,
                run_id=bound.run_id,
                detail={"kind": kind.value, "reason": reason},
            )
        except RuntimeError:
            pass
        self._persist_quarantine(session_id, bound.quarantine_reason)

    def _persist_event(self, bound: _BoundSession, ev: HarnessEvent) -> None:
        if self._store is None:
            return
        try:
            hstate = self.harness_state(bound.session_id)
            term = map_terminal_outcome(hstate)
            usage = {}
            try:
                ru = self._harness.resource_usage(bound.session_id)
                usage = {
                    "turns": ru.turns,
                    "events": ru.events,
                    "fake_tokens": ru.fake_tokens,
                    "tool_proposals": ru.tool_proposals,
                    "output_chars": ru.output_chars,
                    "logical_time_ms": ru.logical_time_ms,
                }
            except Exception:
                usage = {}
            d_ev = self._store.event_from_harness_event(ev)
            kwargs: Dict[str, Any] = {
                "projected_harness_state": hstate.value,
                "authoritative_run_state_snapshot": map_run_state_snapshot(
                    bound.projected_run_state
                ),
                "resource_usage_snapshot": usage,
                "pending_execution_id": bound.pending_execution_id or "",
                "pending_approval_reference": "",
                "pending_tool_proposal_id": bound.pending_proposal_id or "",
            }
            # Preserve approval ref if pending
            if bound.pending_proposal_id:
                for ref, st in bound.approval_refs.items():
                    if st is ApprovalRefState.PENDING:
                        kwargs["pending_approval_reference"] = ref
                        break
            if term is not TerminalOutcome.NONE:
                kwargs["terminal_outcome"] = term.value
                if term is TerminalOutcome.COMPLETED:
                    kwargs["retention_class"] = RetentionClass.COMPLETED.value
                elif term is TerminalOutcome.FAILED:
                    kwargs["retention_class"] = RetentionClass.FAILED.value
                elif term is TerminalOutcome.CANCELLED:
                    kwargs["retention_class"] = RetentionClass.CANCELLED.value
            if bound.closed:
                kwargs["closed"] = True
            if bound.quarantined:
                kwargs["quarantined"] = True
                kwargs["quarantine_reason"] = bound.quarantine_reason
            self._store.append_event(bound.session_id, d_ev, **kwargs)
        except HarnessError:
            # Fail closed: quarantine session and re-raise
            bound.quarantined = True
            bound.quarantine_reason = "durable_append_failed"
            try:
                if self._store is not None:
                    self._store.mark_quarantine(bound.session_id, bound.quarantine_reason)
            except Exception:
                pass
            raise
        except Exception as exc:  # noqa: BLE001
            bound.quarantined = True
            bound.quarantine_reason = f"durable_append_failed: {exc}"
            try:
                if self._store is not None:
                    self._store.mark_quarantine(bound.session_id, bound.quarantine_reason)
            except Exception:
                pass
            raise HarnessError(
                HarnessErrorCode.INTERNAL,
                bound.quarantine_reason,
                session_id=bound.session_id,
            ) from exc

    def _persist_quarantine(self, session_id: str, reason: str) -> None:
        if self._store is None:
            return
        try:
            self._store.mark_quarantine(session_id, reason)
        except Exception:
            pass

    def _persist_session_fields(self, bound: _BoundSession, **fields: Any) -> None:
        if self._store is None:
            return
        rec = self._store.get_session(bound.session_id)
        if rec is None:
            raise HarnessError(
                HarnessErrorCode.INTERNAL,
                "durable session missing during update",
                session_id=bound.session_id,
            )
        for k, v in fields.items():
            if hasattr(rec, k):
                setattr(rec, k, v)
        try:
            self._store.update_session(rec)
        except HarnessError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HarnessError(
                HarnessErrorCode.INTERNAL,
                f"durable session update failed: {exc}",
                session_id=bound.session_id,
            ) from exc

    # ── Recovery / replay (inspection) ──────────────────────────────────────

    def recover_session(
        self,
        session_id: str,
        *,
        authoritative_run_state: Optional[str] = None,
        execution_exists: Optional[bool] = None,
        approval_valid: Optional[bool] = None,
    ) -> RecoveryResult:
        """Reload durable state after restart. Never auto-resumes tool work."""
        if self._store is None:
            raise HarnessError(
                HarnessErrorCode.INVALID_REQUEST,
                "durable_store required for recovery",
                session_id=session_id,
            )
        result = self._store.recover_session(
            session_id,
            authoritative_run_state=authoritative_run_state,
            execution_exists=execution_exists,
            approval_valid=approval_valid,
        )
        # Apply quarantine dispositions into memory if rebound later
        if result.session and result.disposition in (
            RecoveryDisposition.QUARANTINE_STALE,
            RecoveryDisposition.QUARANTINE_CORRUPT,
            RecoveryDisposition.QUARANTINE_AUTHORITY_CONFLICT,
        ):
            try:
                self._store.mark_quarantine(
                    session_id, result.reason or result.disposition.value
                )
            except Exception:
                pass
        self._audit.record(
            "harness.recovery",
            session_id=session_id,
            run_id=(result.session.run_id if result.session else ""),
            detail={
                "disposition": result.disposition.value,
                "reason": result.reason,
                "can_continue": result.can_continue,
                "events_count": result.events_count,
            },
        )
        return result

    def rebind_recovered_session(
        self,
        session_id: str,
        *,
        allowed_tool_names: Tuple[str, ...] = ("fake.echo", "fake.sensitive_read"),
    ) -> DurableSessionRecord:
        """Load durable session into controller memory for inspection only.

        Does not restart the driver or execute tools. Continuation requires
        a separate explicit operator action outside FM-I3.
        """
        if self._store is None:
            raise HarnessError(
                HarnessErrorCode.INVALID_REQUEST,
                "durable_store required for rebind",
                session_id=session_id,
            )
        rec = self._store.get_session(session_id)
        if rec is None:
            raise HarnessError(
                HarnessErrorCode.UNKNOWN_SESSION,
                f"unknown durable session {session_id}",
                session_id=session_id,
            )
        if rec.quarantined or rec.closed:
            raise HarnessError(
                HarnessErrorCode.QUARANTINED if rec.quarantined else HarnessErrorCode.TERMINAL_SESSION,
                rec.quarantine_reason or "session closed",
                session_id=session_id,
            )
        recovery = self._store.recover_session(session_id)
        if recovery.disposition in (
            RecoveryDisposition.QUARANTINE_STALE,
            RecoveryDisposition.QUARANTINE_CORRUPT,
            RecoveryDisposition.QUARANTINE_AUTHORITY_CONFLICT,
            RecoveryDisposition.ABANDON_ORPHANED,
        ):
            raise HarnessError(
                HarnessErrorCode.QUARANTINED,
                recovery.reason or recovery.disposition.value,
                session_id=session_id,
            )
        # Cancelled / terminal: bind read-only projection, no turns
        events = self._store.list_events(session_id)
        try:
            rs = RunState(rec.authoritative_run_state_snapshot)
        except Exception:
            rs = RunState.RUNNING
        bound = _BoundSession(
            session_id=session_id,
            run_id=rec.run_id,
            mission_id=rec.mission_id,
            actor_id=rec.actor_id,
            organization_id=rec.organization_id or None,
            workspace_id=rec.workspace_id or None,
            authority_class="READ_ONLY",
            allowed_tools=tuple(allowed_tool_names),
            budget=HarnessBudget(),
            projected_run_state=rs,
            last_seq=rec.last_event_sequence,
            seen_event_ids={e.event_id for e in events},
            quarantined=rec.quarantined,
            quarantine_reason=rec.quarantine_reason,
            pending_proposal_id=rec.pending_tool_proposal_id or None,
            pending_execution_id=rec.pending_execution_id or None,
            closed=rec.closed,
        )
        if rec.pending_approval_reference:
            bound.approval_refs[rec.pending_approval_reference] = ApprovalRefState.PENDING
        # Reconstruct normalized event list (inspection)
        for e in events:
            try:
                et = HarnessEventType(e.event_type)
            except ValueError:
                et = HarnessEventType.WARNING
            bound.normalized_events.append(
                HarnessEvent(
                    event_id=e.event_id,
                    session_id=e.session_id,
                    sequence_number=e.sequence_number,
                    event_type=et,
                    harness_id=e.harness_id,
                    timestamp=e.timestamp,
                    payload=dict(e.payload),
                    turn_id=e.turn_id or None,
                    run_id=e.run_id or None,
                    mission_id=e.mission_id or None,
                    organization_id=e.organization_id or None,
                    workspace_id=e.workspace_id or None,
                    correlation_id=e.correlation_id or None,
                    causation_id=e.causation_id or None,
                )
            )
        if rec.terminal_outcome not in (TerminalOutcome.NONE.value, ""):
            bound.last_terminal_run_state = rs
        self._sessions[session_id] = bound
        return rec

    def replay_session(self, session_id: str) -> Dict[str, Any]:
        """Inspection-only replay from durable events (no tool execution)."""
        if self._store is None:
            raise HarnessError(
                HarnessErrorCode.INVALID_REQUEST,
                "durable_store required for replay",
                session_id=session_id,
            )
        timeline = self._store.replay_timeline(session_id)
        self._audit.record(
            "harness.replay_inspection",
            session_id=session_id,
            detail={
                "ok": timeline.get("ok"),
                "event_count": timeline.get("event_count"),
                "can_execute": False,
            },
        )
        return timeline

    def _project_terminal(self, bound: _BoundSession, hstate: HarnessSessionState) -> None:
        rs = project_harness_to_run_state(hstate)
        bound.projected_run_state = rs
        if rs in (RunState.FAILED, RunState.CANCELLED, RunState.TIMED_OUT, RunState.COMPLETED):
            bound.last_terminal_run_state = rs

    def _require_bound(self, session_id: str) -> _BoundSession:
        bound = self._sessions.get(session_id)
        if bound is None:
            raise HarnessError(
                HarnessErrorCode.UNKNOWN_SESSION,
                f"unknown session {session_id}",
                session_id=session_id,
            )
        return bound

    def _harness_handle_for(self, session_id: str) -> HarnessSessionHandle:
        bound = self._require_bound(session_id)
        profile = self._harness.describe_capabilities()
        state = self.harness_state(session_id)
        return HarnessSessionHandle(
            session_id=session_id,
            state=state,
            harness_id=profile.harness_id,
            capabilities=profile,
            run_id=bound.run_id,
            organization_id=bound.organization_id,
            workspace_id=bound.workspace_id,
        )

    # ── Capability non-grant proof helper ───────────────────────────────────

    def capability_grants_permission(self, capability_id: HarnessCapabilityId) -> bool:
        """Capabilities are descriptive only — always False for permission grants."""
        _ = capability_id
        return False
