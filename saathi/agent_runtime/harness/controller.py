"""HarnessSessionController — trusted platform mediator (FM-I1 proof).

Owns: session↔run bind, lifecycle validation, event normalization, ToolIntent
construction, approval-required pause, cancel propagation, resource checks,
audit correlation, protocol quarantine.

Does **not** own: authN, RBAC source of truth, approval issuance, credentials,
provider secrets, direct tool execution, gateway replacement, Trading Guardian.

FM-I1 forbids external process spawning, network clients, and browser drivers
in this package; tool side effects stay mediated via ToolIntent + test double.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple
import hashlib
import time
import uuid

from saathi.agent_runtime.harness.audit import HarnessAuditLog
from saathi.agent_runtime.harness.errors import HarnessError, HarnessErrorCode
from saathi.agent_runtime.harness.fake import FakeInMemoryHarness
from saathi.agent_runtime.harness.mapping import project_harness_to_run_state
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

# Import ToolIntent without pulling ExecutionGateway (env/py version safe).
from saathi.execution.toolintent import (
    ActorType,
    ApprovalLevel,
    BusinessUnit,
    Priority,
    RiskLevel,
    ToolIntent,
)


# Tools the FM-I1 proof allows the controller to map into ToolIntent.
KNOWN_FAKE_TOOLS: Mapping[str, Mapping[str, Any]] = {
    "fake.echo": {
        "capability": "diagnostics",
        "connector_id": "fake-in-memory",
        "operation": "echo",
        "risk_level": RiskLevel.LOW,
        "approval_level": ApprovalLevel.L1,
        "requires_approval": False,
    },
    "fake.sensitive_read": {
        "capability": "diagnostics",
        "connector_id": "fake-in-memory",
        "operation": "sensitive_read",
        "risk_level": RiskLevel.HIGH,
        "approval_level": ApprovalLevel.L4,
        "requires_approval": True,
    },
}


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
    closed: bool = False


class GatewayTestDouble:
    """Narrow ExecutionGateway test double for FM-I1 tool mediation proofs.

    Not a shadow production gateway. Records intents and returns redacted
    results without network, child processes, FS mutation, or credentials.
    """

    def __init__(self) -> None:
        self.submitted: List[ToolIntent] = []
        self.cancelled_intent_ids: List[str] = []
        self._results_by_idem: Dict[str, Mapping[str, Any]] = {}
        self.deny_all: bool = False
        self.execute: bool = True

    def submit(self, intent: ToolIntent) -> Mapping[str, Any]:
        """Accept a trusted ToolIntent; return redacted synthetic result."""
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
            }
        # Idempotent replay
        if intent.idempotency_key in self._results_by_idem:
            return dict(self._results_by_idem[intent.idempotency_key])
        self.submitted.append(intent)
        if not self.execute:
            result = {
                "ok": False,
                "status": "not_executed",
                "summary": "execution disabled on test double",
            }
        else:
            # Synthetic only — never pretends real external side effects
            result = {
                "ok": True,
                "status": "fake_success",
                "summary": f"fake result for {intent.operation}",
                "echo": dict(intent.parameters),
                "executed": False,  # honesty: no real side effect
                "path": "GatewayTestDouble",
            }
        self._results_by_idem[intent.idempotency_key] = result
        return dict(result)

    def cancel(self, intent_id: str) -> None:
        self.cancelled_intent_ids.append(intent_id)


class HarnessSessionController:
    """Trusted controller binding AgentHarness sessions to platform run scope."""

    def __init__(
        self,
        harness: AgentHarness,
        *,
        gateway: Optional[GatewayTestDouble] = None,
        audit: Optional[HarnessAuditLog] = None,
        known_tools: Optional[Mapping[str, Mapping[str, Any]]] = None,
        max_sessions: int = 4,
    ) -> None:
        self._harness = harness
        self._gateway = gateway if gateway is not None else GatewayTestDouble()
        self._audit = audit if audit is not None else HarnessAuditLog()
        self._known_tools = dict(known_tools or KNOWN_FAKE_TOOLS)
        self._max_sessions = max_sessions
        self._sessions: Dict[str, _BoundSession] = {}

    @property
    def audit(self) -> HarnessAuditLog:
        return self._audit

    @property
    def gateway(self) -> GatewayTestDouble:
        return self._gateway

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
            projected_run_state=project_harness_to_run_state(handle.state),
        )
        self._sessions[sid] = bound
        self._ingest_events(sid)
        self._audit.record(
            "harness.session_started",
            session_id=sid,
            run_id=run_id,
            correlation_id=correlation_id,
            detail={"authority_class": authority_class, "org": organization_id},
        )
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
        bound = self._require_bound(session_id)
        # Cancel pending gateway work
        for intent in list(self._gateway.submitted):
            if intent.metadata.get("session_id") == session_id:
                self._gateway.cancel(intent.intent_id)

        try:
            ack = self._harness.request_cancel(session_id, reason)
        except HarnessError as exc:
            # Fail-closed: mark cancelled projection even if ack fails
            bound.projected_run_state = RunState.FAILED
            bound.last_terminal_run_state = RunState.FAILED
            self._audit.record(
                "harness.cancellation_failed_closed",
                session_id=session_id,
                run_id=bound.run_id,
                detail={"error": exc.code, "reason": reason},
            )
            raise

        self._ingest_events(session_id)
        if ack.status in (CancelAckStatus.ACKNOWLEDGED, CancelAckStatus.ALREADY_TERMINAL):
            bound.projected_run_state = RunState.CANCELLED
            bound.last_terminal_run_state = RunState.CANCELLED
        self._audit.record(
            "harness.cancellation",
            session_id=session_id,
            run_id=bound.run_id,
            detail={"status": ack.status.value, "reason": reason},
        )
        # Idempotent second cancel
        return ack

    def close_session(self, session_id: str, reason: str = "closed") -> SessionCloseResult:
        bound = self._require_bound(session_id)
        result = self._harness.close_session(session_id, reason)
        bound.closed = True
        self._ingest_events(session_id)
        bound.projected_run_state = project_harness_to_run_state(
            HarnessSessionState.CLOSED,
            prior_terminal_run=bound.last_terminal_run_state,
        )
        self._audit.record(
            "harness.session_closed",
            session_id=session_id,
            run_id=bound.run_id,
            detail={"reason": reason, "already_closed": result.already_closed},
        )
        return result

    def poll_events(self, session_id: str, after_seq: int = 0) -> List[HarnessEvent]:
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
            bound.approval_refs[approval_ref] = ApprovalRefState.APPROVED
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
        elif decision in (
            ApprovalRefState.DENIED,
            ApprovalRefState.EXPIRED,
            ApprovalRefState.REVOKED,
        ):
            proposal = bound.pending_proposal
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

    # ── Tool mediation ──────────────────────────────────────────────────────

    def mediate_proposal(self, proposal: ToolProposal) -> MediatedToolResult:
        """Validate proposal and build ToolIntent; never let harness authorize."""
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

        # Approval-required path — controller surfaces wait; does not approve
        if tool_meta.get("requires_approval"):
            approval_ref = f"apr-{proposal.proposal_id}"
            state = bound.approval_refs.get(approval_ref, ApprovalRefState.NONE)
            if state is ApprovalRefState.NONE:
                bound.approval_refs[approval_ref] = ApprovalRefState.PENDING
                bound.pending_proposal_id = proposal.proposal_id
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
                    },
                )
                # Do not inject into harness sequence space (preserves monotonic seq).
                return MediatedToolResult(
                    disposition=ToolProposalDisposition.APPROVAL_REQUIRED,
                    proposal_id=proposal.proposal_id,
                    reason="approval required",
                    approval_state=ApprovalRefState.PENDING,
                    approval_ref=approval_ref,
                )
            if state is ApprovalRefState.PENDING:
                return MediatedToolResult(
                    disposition=ToolProposalDisposition.APPROVAL_REQUIRED,
                    proposal_id=proposal.proposal_id,
                    reason="approval still pending",
                    approval_state=ApprovalRefState.PENDING,
                    approval_ref=approval_ref,
                )
            if state in (
                ApprovalRefState.DENIED,
                ApprovalRefState.EXPIRED,
                ApprovalRefState.REVOKED,
            ):
                return MediatedToolResult(
                    disposition=ToolProposalDisposition.DENIED,
                    proposal_id=proposal.proposal_id,
                    reason=f"approval {state.value}",
                    approval_state=state,
                    approval_ref=approval_ref,
                )
            if state is ApprovalRefState.CONSUMED:
                return MediatedToolResult(
                    disposition=ToolProposalDisposition.DENIED,
                    proposal_id=proposal.proposal_id,
                    reason="approval already consumed",
                    approval_state=state,
                    approval_ref=approval_ref,
                )
            # APPROVED — fall through to construct intent (then mark consumed by caller)

        # Trusted ToolIntent construction (controller only)
        try:
            corr = proposal.correlation_id
            # correlation_id must be UUID4 for ToolIntent.validate
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
                    "proposal_id": proposal.proposal_id,
                    "harness_id": "fake-in-memory",
                    "source": "HarnessSessionController",
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
            existing = self._gateway.submit(intent)  # returns cached if any
            return MediatedToolResult(
                disposition=ToolProposalDisposition.ACCEPTED,
                proposal_id=proposal.proposal_id,
                tool_intent=intent,
                redacted_result=existing,
                reason="idempotent replay",
            )

        result = self._gateway.submit(intent)
        bound.consumed_idempotency_keys.add(idem)
        denied = not result.get("ok", False)
        disposition = (
            ToolProposalDisposition.DENIED
            if denied
            else ToolProposalDisposition.ACCEPTED
        )
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
                "executed": False,
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
        raw = list(self._harness.poll_events(session_id, after_seq=bound.last_seq))
        for ev in raw:
            if self._validate_event(bound, ev):
                bound.normalized_events.append(ev)
                bound.last_seq = max(bound.last_seq, ev.sequence_number)
                bound.seen_event_ids.add(ev.event_id)
                self._update_projection_from_event(bound, ev)

    def _validate_event(self, bound: _BoundSession, ev: HarnessEvent) -> bool:
        if bound.closed and ev.event_type is not HarnessEventType.SESSION_CLOSED:
            # Late events after close → quarantine
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
        if bound.last_seq and ev.sequence_number > bound.last_seq + 1:
            # gap — still accept but audit (deterministic fake should not gap)
            self._audit.record(
                "harness.sequence_gap",
                session_id=bound.session_id,
                run_id=bound.run_id,
                detail={"from": bound.last_seq, "to": ev.sequence_number},
            )
        if ev.session_id != bound.session_id:
            self._quarantine(
                bound.session_id,
                ProtocolViolationKind.FORGED_EVENT,
                "session_id mismatch on event",
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
        # Reject private CoT persistence
        payload = dict(ev.payload)
        for banned in ("chain_of_thought", "private_cot", "hidden_reasoning", "raw_cot"):
            if banned in payload:
                self._audit.record(
                    "harness.cot_stripped",
                    session_id=bound.session_id,
                    run_id=bound.run_id,
                    detail={"key": banned, "event_id": ev.event_id},
                )
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
        self._audit.record(
            "harness.protocol_violation",
            session_id=session_id,
            run_id=bound.run_id,
            detail={"kind": kind.value, "reason": reason},
        )

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
