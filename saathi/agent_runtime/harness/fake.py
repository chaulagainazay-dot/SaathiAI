"""Deterministic in-process FakeInMemoryHarness (FM-I1).

No child processes, network, filesystem mutation, provider, credential, browser,
shell, or external service. Scripted scenarios only.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple
import copy
import hashlib
import threading
import time
import uuid

from saathi.agent_runtime.harness.errors import HarnessError, HarnessErrorCode
from saathi.agent_runtime.harness.types import (
    CancelAck,
    CancelAckStatus,
    EventClassification,
    EventRedactionState,
    HarnessBudget,
    HarnessCapability,
    HarnessCapabilityId,
    HarnessCapabilityProfile,
    HarnessEvent,
    HarnessEventType,
    HarnessHealth,
    HarnessHealthStatus,
    HarnessResourceUsage,
    HarnessSessionHandle,
    HarnessSessionStartRequest,
    HarnessSessionState,
    HarnessTurnHandle,
    HarnessTurnSubmitRequest,
    SessionCloseResult,
    ToolProposal,
    can_transition_harness,
    is_terminal_harness_state,
)


HARNESS_ID = "fake-in-memory"
HARNESS_VERSION = "0.1.0"
PROTOCOL_VERSION = "1.0"


class FakeScenario(str, Enum):
    """Deterministic scripted turn outcomes."""

    TEXT_COMPLETION = "text_completion"
    MULTI_TURN = "multi_turn"
    TOOL_PROPOSAL = "tool_proposal"
    APPROVAL_REQUIRED = "approval_required"
    DENIED_TOOL = "denied_tool"  # emits proposal; controller denies
    TOOL_THEN_CONTINUE = "tool_then_continue"
    TIMEOUT = "timeout"
    HARNESS_FAILURE = "harness_failure"
    RESOURCE_EXHAUST = "resource_exhaust"
    # controller-driven scenarios also covered: cancel before/during turn


@dataclass
class _Session:
    req: HarnessSessionStartRequest
    state: HarnessSessionState = HarnessSessionState.CREATED
    events: List[HarnessEvent] = field(default_factory=list)
    event_ids: set = field(default_factory=set)
    seq: int = 0
    turns: Dict[str, HarnessSessionState] = field(default_factory=dict)
    pending_proposals: List[ToolProposal] = field(default_factory=list)
    usage: HarnessResourceUsage = field(default_factory=HarnessResourceUsage)
    cancel_requested: bool = False
    terminal_reason: str = ""
    closed: bool = False
    logical_clock_ms: int = 0
    scenario_queue: List[FakeScenario] = field(default_factory=list)
    # tool result injection from controller (redacted)
    pending_tool_results: List[Mapping[str, Any]] = field(default_factory=list)
    awaiting_tool_result: bool = False
    force_fail_next: bool = False


class FakeInMemoryHarness:
    """Deterministic AgentHarness implementation for conformance proofs."""

    def __init__(
        self,
        *,
        default_scenario: FakeScenario = FakeScenario.TEXT_COMPLETION,
        scenario_by_turn: Optional[Mapping[str, FakeScenario]] = None,
        healthy: bool = True,
        fail_cancel_ack: bool = False,
    ) -> None:
        self._default_scenario = default_scenario
        self._scenario_by_turn = dict(scenario_by_turn or {})
        self._healthy = healthy
        self._fail_cancel_ack = fail_cancel_ack
        self._sessions: Dict[str, _Session] = {}
        self._lock = threading.RLock()
        self._profile = HarnessCapabilityProfile(
            harness_id=HARNESS_ID,
            harness_version=HARNESS_VERSION,
            protocol_version=PROTOCOL_VERSION,
            capabilities=(
                HarnessCapability(HarnessCapabilityId.SESSION_LIFECYCLE),
                HarnessCapability(HarnessCapabilityId.SUBMIT_TURN),
                HarnessCapability(HarnessCapabilityId.EVENT_STREAM),
                HarnessCapability(HarnessCapabilityId.COOPERATIVE_CANCEL),
                HarnessCapability(HarnessCapabilityId.TOOL_PROPOSALS),
                HarnessCapability(HarnessCapabilityId.HEALTH),
                HarnessCapability(HarnessCapabilityId.RESOURCE_USAGE_REPORT),
                HarnessCapability(HarnessCapabilityId.MULTI_TURN),
                HarnessCapability(HarnessCapabilityId.DETERMINISTIC_EVENTS),
                HarnessCapability(HarnessCapabilityId.HEALTH_REPORTING),
                HarnessCapability(HarnessCapabilityId.RESOURCE_REPORTING),
            ),
        )

    # ── Protocol ────────────────────────────────────────────────────────────

    def describe_capabilities(self) -> HarnessCapabilityProfile:
        return self._profile

    def health(self) -> HarnessHealth:
        with self._lock:
            n = sum(1 for s in self._sessions.values() if not s.closed)
            status = (
                HarnessHealthStatus.HEALTHY
                if self._healthy
                else HarnessHealthStatus.UNHEALTHY
            )
            return HarnessHealth(
                status=status,
                harness_id=HARNESS_ID,
                detail="ok" if self._healthy else "forced_unhealthy",
                active_sessions=n,
            )

    def start_session(self, req: HarnessSessionStartRequest) -> HarnessSessionHandle:
        with self._lock:
            if not req.session_id or not req.actor_id or not req.correlation_id:
                raise HarnessError(
                    HarnessErrorCode.INVALID_REQUEST,
                    "session_id, actor_id, and correlation_id are required",
                )
            existing = self._sessions.get(req.session_id)
            if existing is not None:
                # Idempotent start: same scope → return handle; different scope → conflict
                if (
                    existing.req.organization_id != req.organization_id
                    or existing.req.workspace_id != req.workspace_id
                    or existing.req.actor_id != req.actor_id
                ):
                    raise HarnessError(
                        HarnessErrorCode.IDEMPOTENCY_CONFLICT,
                        "session_id already exists with different scope",
                        session_id=req.session_id,
                    )
                return self._handle(existing)

            if not self._healthy:
                raise HarnessError(
                    HarnessErrorCode.INTERNAL,
                    "harness unhealthy; refusing new sessions",
                )

            sess = _Session(req=req, state=HarnessSessionState.CREATED)
            self._sessions[req.session_id] = sess
            self._transition(sess, HarnessSessionState.INITIALIZING)
            self._emit(
                sess,
                HarnessEventType.SESSION_STARTED,
                {"actor_id": req.actor_id},
                correlation_id=req.correlation_id,
            )
            self._transition(sess, HarnessSessionState.READY)
            self._emit(
                sess,
                HarnessEventType.SESSION_READY,
                {},
                correlation_id=req.correlation_id,
            )
            return self._handle(sess)

    def submit_turn(self, req: HarnessTurnSubmitRequest) -> HarnessTurnHandle:
        with self._lock:
            sess = self._require_session(req.session_id)
            if sess.closed or sess.state is HarnessSessionState.CLOSED:
                raise HarnessError(
                    HarnessErrorCode.TERMINAL_SESSION,
                    "session is closed",
                    session_id=req.session_id,
                )
            if is_terminal_harness_state(sess.state) or sess.cancel_requested:
                raise HarnessError(
                    HarnessErrorCode.CANCELLED
                    if sess.cancel_requested or sess.state is HarnessSessionState.CANCELLED
                    else HarnessErrorCode.TERMINAL_SESSION,
                    f"cannot accept turns in state {sess.state.value}",
                    session_id=req.session_id,
                )
            if sess.state not in (
                HarnessSessionState.READY,
                HarnessSessionState.WAITING_FOR_TOOL,
            ):
                # After tool result, controller may leave us READY; WAITING_FOR_TOOL
                # accepts only via deliver_tool_result then continue.
                if sess.state is HarnessSessionState.WAITING_FOR_APPROVAL:
                    raise HarnessError(
                        HarnessErrorCode.APPROVAL_PENDING,
                        "session waiting for approval",
                        session_id=req.session_id,
                    )
                raise HarnessError(
                    HarnessErrorCode.INVALID_STATE,
                    f"cannot submit_turn from {sess.state.value}",
                    session_id=req.session_id,
                )
            if not req.turn_id or not req.correlation_id:
                raise HarnessError(
                    HarnessErrorCode.INVALID_REQUEST,
                    "turn_id and correlation_id required",
                    session_id=req.session_id,
                )
            if req.turn_id in sess.turns:
                # Idempotent: same turn_id returns prior handle without re-running
                return HarnessTurnHandle(
                    turn_id=req.turn_id,
                    session_id=req.session_id,
                    state=sess.state,
                    accepted=True,
                )

            # Resource: turn limit
            budget = sess.req.budget
            next_turns = sess.usage.turns + 1
            if next_turns > budget.max_turns:
                self._fail_resource(sess, "max_turns", req.correlation_id)
                raise HarnessError(
                    HarnessErrorCode.RESOURCE_EXHAUSTED,
                    "max_turns exceeded",
                    session_id=req.session_id,
                    details={"limit": "max_turns"},
                )

            self._transition(sess, HarnessSessionState.RUNNING)
            sess.turns[req.turn_id] = HarnessSessionState.RUNNING
            sess.usage = replace(
                sess.usage,
                turns=next_turns,
                logical_time_ms=sess.usage.logical_time_ms + 10,
            )
            self._emit(
                sess,
                HarnessEventType.TURN_ACCEPTED,
                {"input_chars": len(req.input_text or "")},
                turn_id=req.turn_id,
                correlation_id=req.correlation_id,
                causation_id=req.causation_id,
            )

            scenario = self._scenario_for(req.turn_id, sess)
            self._run_scenario(sess, req, scenario)
            return HarnessTurnHandle(
                turn_id=req.turn_id,
                session_id=req.session_id,
                state=sess.state,
                accepted=True,
            )

    def stream_events(self, session_id: str, after_seq: int = 0) -> Iterator[HarnessEvent]:
        for ev in self.poll_events(session_id, after_seq=after_seq):
            yield ev

    def poll_events(self, session_id: str, after_seq: int = 0) -> List[HarnessEvent]:
        with self._lock:
            sess = self._require_session(session_id)
            return [e for e in sess.events if e.sequence_number > after_seq]

    def request_cancel(self, session_id: str, reason: str = "") -> CancelAck:
        with self._lock:
            sess = self._require_session(session_id)
            if sess.closed or sess.state is HarnessSessionState.CLOSED:
                return CancelAck(
                    session_id=session_id,
                    status=CancelAckStatus.ALREADY_TERMINAL,
                    reason=reason or "already_closed",
                )
            if is_terminal_harness_state(sess.state) and sess.state is not HarnessSessionState.CANCELLING:
                return CancelAck(
                    session_id=session_id,
                    status=CancelAckStatus.ALREADY_TERMINAL,
                    reason=reason or sess.terminal_reason or sess.state.value,
                )

            if self._fail_cancel_ack:
                # Simulate cancel failure path → controller must fail-closed
                raise HarnessError(
                    HarnessErrorCode.INTERNAL,
                    "cancel acknowledgement failed (forced)",
                    session_id=session_id,
                )

            sess.cancel_requested = True
            if sess.state is not HarnessSessionState.CANCELLING:
                if can_transition_harness(sess.state, HarnessSessionState.CANCELLING):
                    self._transition(sess, HarnessSessionState.CANCELLING)
                else:
                    # From terminal-ish states force CANCELLED if possible
                    pass
            self._emit(
                sess,
                HarnessEventType.CANCELLATION_REQUESTED,
                {"reason": reason},
            )
            # Clear pending proposals — no new tool work after cancel
            sess.pending_proposals.clear()
            sess.awaiting_tool_result = False
            if can_transition_harness(sess.state, HarnessSessionState.CANCELLED):
                self._transition(sess, HarnessSessionState.CANCELLED)
            elif sess.state is HarnessSessionState.CANCELLING:
                self._transition(sess, HarnessSessionState.CANCELLED)
            sess.terminal_reason = reason or "cancelled"
            self._emit(
                sess,
                HarnessEventType.CANCELLATION_ACKNOWLEDGED,
                {"reason": sess.terminal_reason},
            )
            return CancelAck(
                session_id=session_id,
                status=CancelAckStatus.ACKNOWLEDGED,
                reason=sess.terminal_reason,
            )

    def close_session(self, session_id: str, reason: str = "") -> SessionCloseResult:
        with self._lock:
            sess = self._require_session(session_id)
            if sess.closed or sess.state is HarnessSessionState.CLOSED:
                return SessionCloseResult(
                    session_id=session_id,
                    state=HarnessSessionState.CLOSED,
                    already_closed=True,
                    reason=reason or "already_closed",
                )
            # Force terminal if still open
            if not is_terminal_harness_state(sess.state):
                if can_transition_harness(sess.state, HarnessSessionState.CANCELLED):
                    if can_transition_harness(sess.state, HarnessSessionState.CANCELLING):
                        self._transition(sess, HarnessSessionState.CANCELLING)
                    self._transition(sess, HarnessSessionState.CANCELLED)
                elif can_transition_harness(sess.state, HarnessSessionState.COMPLETED):
                    self._transition(sess, HarnessSessionState.COMPLETED)
                else:
                    # last resort: mark failed then close
                    if can_transition_harness(sess.state, HarnessSessionState.FAILED):
                        self._transition(sess, HarnessSessionState.FAILED)
            if can_transition_harness(sess.state, HarnessSessionState.CLOSED):
                self._transition(sess, HarnessSessionState.CLOSED)
            sess.closed = True
            self._emit(
                sess,
                HarnessEventType.SESSION_CLOSED,
                {"reason": reason or "closed"},
            )
            return SessionCloseResult(
                session_id=session_id,
                state=HarnessSessionState.CLOSED,
                already_closed=False,
                reason=reason or "closed",
            )

    def resource_usage(self, session_id: str) -> HarnessResourceUsage:
        with self._lock:
            sess = self._require_session(session_id)
            active = sum(1 for s in self._sessions.values() if not s.closed)
            return replace(sess.usage, concurrent_sessions=active)

    # ── Controller-facing helpers (not part of untrusted external surface) ──

    def deliver_tool_result(
        self,
        session_id: str,
        *,
        turn_id: str,
        correlation_id: str,
        result: Mapping[str, Any],
        denied: bool = False,
    ) -> None:
        """Receive redacted tool result from the trusted controller only."""
        with self._lock:
            sess = self._require_session(session_id)
            if sess.cancel_requested or is_terminal_harness_state(sess.state):
                raise HarnessError(
                    HarnessErrorCode.TERMINAL_SESSION,
                    "cannot deliver tool result to terminal/cancelled session",
                    session_id=session_id,
                )
            if sess.state is not HarnessSessionState.WAITING_FOR_TOOL:
                raise HarnessError(
                    HarnessErrorCode.INVALID_STATE,
                    f"expected WAITING_FOR_TOOL, got {sess.state.value}",
                    session_id=session_id,
                )
            # Redacted safe result only
            safe = {
                k: v
                for k, v in dict(result).items()
                if k not in ("chain_of_thought", "private_cot", "secret", "password", "token")
            }
            self._emit(
                sess,
                HarnessEventType.TOOL_RESULT_DELIVERED,
                {"denied": denied, "result": safe},
                turn_id=turn_id,
                correlation_id=correlation_id,
            )
            sess.awaiting_tool_result = False
            if denied:
                self._transition(sess, HarnessSessionState.READY)
                self._emit(
                    sess,
                    HarnessEventType.TEXT_DELTA,
                    {"text": "[tool denied — continuing with summary only]"},
                    turn_id=turn_id,
                    correlation_id=correlation_id,
                )
                self._complete(sess, turn_id, correlation_id, text="completed after deny")
                return
            self._transition(sess, HarnessSessionState.RUNNING)
            self._emit(
                sess,
                HarnessEventType.TEXT_DELTA,
                {"text": f"[tool result applied: {safe.get('summary', 'ok')}]"},
                turn_id=turn_id,
                correlation_id=correlation_id,
            )
            self._complete(sess, turn_id, correlation_id, text="completed after tool")

    def force_protocol_event(
        self,
        session_id: str,
        event: HarnessEvent,
    ) -> None:
        """Test-only injection of a raw event (used to prove controller quarantine)."""
        with self._lock:
            sess = self._require_session(session_id)
            # Bypass sequencing intentionally for protocol tests
            sess.events.append(event)
            if event.event_id:
                sess.event_ids.add(event.event_id)

    def get_state(self, session_id: str) -> HarnessSessionState:
        with self._lock:
            return self._require_session(session_id).state

    def list_session_ids(self) -> List[str]:
        with self._lock:
            return list(self._sessions.keys())

    # ── Internals ───────────────────────────────────────────────────────────

    def _handle(self, sess: _Session) -> HarnessSessionHandle:
        return HarnessSessionHandle(
            session_id=sess.req.session_id,
            state=sess.state,
            harness_id=HARNESS_ID,
            capabilities=self._profile,
            run_id=sess.req.run_id,
            organization_id=sess.req.organization_id,
            workspace_id=sess.req.workspace_id,
        )

    def _require_session(self, session_id: str) -> _Session:
        sess = self._sessions.get(session_id)
        if sess is None:
            raise HarnessError(
                HarnessErrorCode.UNKNOWN_SESSION,
                f"unknown session {session_id}",
                session_id=session_id,
            )
        return sess

    def _transition(self, sess: _Session, dst: HarnessSessionState) -> None:
        if sess.state is dst:
            return
        if not can_transition_harness(sess.state, dst):
            raise HarnessError(
                HarnessErrorCode.INVALID_STATE,
                f"illegal transition {sess.state.value} → {dst.value}",
                session_id=sess.req.session_id,
                details={"from": sess.state.value, "to": dst.value},
            )
        sess.state = dst

    def _emit(
        self,
        sess: _Session,
        event_type: HarnessEventType,
        payload: Mapping[str, Any],
        *,
        turn_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> HarnessEvent:
        if sess.closed and event_type is not HarnessEventType.SESSION_CLOSED:
            # No events after terminal closure (allow the close event itself)
            if any(e.event_type is HarnessEventType.SESSION_CLOSED for e in sess.events):
                raise HarnessError(
                    HarnessErrorCode.PROTOCOL_VIOLATION,
                    "event after session closed",
                    session_id=sess.req.session_id,
                )

        budget = sess.req.budget
        next_events = sess.usage.events + 1
        if next_events > budget.max_events:
            # Resource fail-closed
            if not is_terminal_harness_state(sess.state):
                try:
                    self._transition(sess, HarnessSessionState.FAILED)
                except HarnessError:
                    pass
            raise HarnessError(
                HarnessErrorCode.RESOURCE_EXHAUSTED,
                "max_events exceeded",
                session_id=sess.req.session_id,
                details={"limit": "max_events"},
            )

        # Strip private CoT from payloads
        safe_payload = {
            k: v
            for k, v in dict(payload).items()
            if k not in ("chain_of_thought", "private_cot", "hidden_reasoning", "raw_cot")
        }
        text = safe_payload.get("text")
        out_chars = sess.usage.output_chars + (len(text) if isinstance(text, str) else 0)
        if out_chars > budget.max_output_chars:
            if not is_terminal_harness_state(sess.state):
                try:
                    self._transition(sess, HarnessSessionState.FAILED)
                except HarnessError:
                    pass
            raise HarnessError(
                HarnessErrorCode.RESOURCE_EXHAUSTED,
                "max_output_chars exceeded",
                session_id=sess.req.session_id,
                details={"limit": "max_output_chars"},
            )

        sess.seq += 1
        event_id = str(uuid.uuid4())
        if event_id in sess.event_ids:
            # astronomically unlikely; still fail-closed
            event_id = str(uuid.uuid4())
        sess.event_ids.add(event_id)
        tokens = int(safe_payload.get("fake_tokens", 0) or 0)
        sess.usage = replace(
            sess.usage,
            events=next_events,
            output_chars=out_chars,
            fake_tokens=sess.usage.fake_tokens + tokens,
            logical_time_ms=sess.usage.logical_time_ms + 1,
        )
        # Token budget check after accounting
        if sess.usage.fake_tokens > budget.max_fake_tokens:
            if not is_terminal_harness_state(sess.state):
                try:
                    self._transition(sess, HarnessSessionState.FAILED)
                except HarnessError:
                    pass
            raise HarnessError(
                HarnessErrorCode.RESOURCE_EXHAUSTED,
                "max_fake_tokens exceeded",
                session_id=sess.req.session_id,
                details={"limit": "max_fake_tokens"},
            )

        ev = HarnessEvent(
            event_id=event_id,
            session_id=sess.req.session_id,
            sequence_number=sess.seq,
            event_type=event_type,
            harness_id=HARNESS_ID,
            timestamp=time.time(),
            payload=safe_payload,
            turn_id=turn_id,
            run_id=sess.req.run_id,
            mission_id=sess.req.mission_id,
            organization_id=sess.req.organization_id,
            workspace_id=sess.req.workspace_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            classification=EventClassification.INTERNAL,
            redaction_state=EventRedactionState.NONE,
        )
        sess.events.append(ev)
        return ev

    def _scenario_for(self, turn_id: str, sess: _Session) -> FakeScenario:
        if turn_id in self._scenario_by_turn:
            return self._scenario_by_turn[turn_id]
        if sess.scenario_queue:
            return sess.scenario_queue.pop(0)
        return self._default_scenario

    def set_scenario_queue(self, session_id: str, scenarios: List[FakeScenario]) -> None:
        with self._lock:
            sess = self._require_session(session_id)
            sess.scenario_queue = list(scenarios)

    def _run_scenario(
        self,
        sess: _Session,
        req: HarnessTurnSubmitRequest,
        scenario: FakeScenario,
    ) -> None:
        if sess.cancel_requested:
            return

        if scenario is FakeScenario.TIMEOUT:
            self._transition(sess, HarnessSessionState.TIMED_OUT)
            sess.terminal_reason = "timeout"
            self._emit(
                sess,
                HarnessEventType.SESSION_TIMED_OUT,
                {"reason": "timeout"},
                turn_id=req.turn_id,
                correlation_id=req.correlation_id,
            )
            return

        if scenario is FakeScenario.HARNESS_FAILURE:
            self._transition(sess, HarnessSessionState.FAILED)
            sess.terminal_reason = "harness_failure"
            self._emit(
                sess,
                HarnessEventType.ERROR,
                {"message": "forced harness failure"},
                turn_id=req.turn_id,
                correlation_id=req.correlation_id,
            )
            self._emit(
                sess,
                HarnessEventType.SESSION_FAILED,
                {"reason": "harness_failure"},
                turn_id=req.turn_id,
                correlation_id=req.correlation_id,
            )
            return

        if scenario is FakeScenario.RESOURCE_EXHAUST:
            # Push usage over max_fake_tokens via report then fail closed.
            budget = sess.req.budget
            sess.usage = replace(
                sess.usage,
                fake_tokens=budget.max_fake_tokens + 1,
            )
            self._fail_resource(sess, "max_fake_tokens", req.correlation_id)
            raise HarnessError(
                HarnessErrorCode.RESOURCE_EXHAUSTED,
                "max_fake_tokens exceeded",
                session_id=sess.req.session_id,
                details={"limit": "max_fake_tokens"},
            )

        if scenario in (
            FakeScenario.TOOL_PROPOSAL,
            FakeScenario.DENIED_TOOL,
            FakeScenario.TOOL_THEN_CONTINUE,
            FakeScenario.APPROVAL_REQUIRED,
        ):
            self._emit(
                sess,
                HarnessEventType.TEXT_DELTA,
                {"text": "planning tool use", "fake_tokens": 3},
                turn_id=req.turn_id,
                correlation_id=req.correlation_id,
            )
            tool_name = "fake.echo"
            if scenario is FakeScenario.APPROVAL_REQUIRED:
                tool_name = "fake.sensitive_read"
            params = {"message": req.input_text or "ping", "scenario": scenario.value}
            proposal_id = str(uuid.uuid4())
            idem = hashlib.sha256(
                f"{sess.req.session_id}:{req.turn_id}:{tool_name}:{params}".encode()
            ).hexdigest()
            proposal = ToolProposal(
                proposal_id=proposal_id,
                session_id=sess.req.session_id,
                turn_id=req.turn_id,
                tool_name=tool_name,
                parameters=params,
                correlation_id=req.correlation_id,
                causation_id=req.causation_id,
                idempotency_key=idem,
                organization_id=sess.req.organization_id,
                workspace_id=sess.req.workspace_id,
            )
            # Resource: tool proposals
            next_props = sess.usage.tool_proposals + 1
            if next_props > sess.req.budget.max_tool_proposals:
                self._fail_resource(sess, "max_tool_proposals", req.correlation_id)
                return
            sess.usage = replace(sess.usage, tool_proposals=next_props)
            sess.pending_proposals.append(proposal)
            self._transition(sess, HarnessSessionState.WAITING_FOR_TOOL)
            self._emit(
                sess,
                HarnessEventType.TOOL_PROPOSAL,
                {
                    "proposal_id": proposal.proposal_id,
                    "tool_name": proposal.tool_name,
                    "parameters": dict(proposal.parameters),
                    "idempotency_key": proposal.idempotency_key,
                    "requires_approval": scenario is FakeScenario.APPROVAL_REQUIRED,
                },
                turn_id=req.turn_id,
                correlation_id=req.correlation_id,
            )
            sess.awaiting_tool_result = True
            return

        # TEXT_COMPLETION / MULTI_TURN
        self._emit(
            sess,
            HarnessEventType.TEXT_DELTA,
            {
                "text": f"fake response to: {(req.input_text or '')[:80]}",
                "fake_tokens": 5,
            },
            turn_id=req.turn_id,
            correlation_id=req.correlation_id,
        )
        if scenario is FakeScenario.MULTI_TURN:
            # Leave READY for more turns rather than completing session
            self._transition(sess, HarnessSessionState.READY)
            self._emit(
                sess,
                HarnessEventType.RESOURCE_USAGE,
                {"turns": sess.usage.turns, "events": sess.usage.events},
                turn_id=req.turn_id,
                correlation_id=req.correlation_id,
            )
            return
        self._complete(sess, req.turn_id, req.correlation_id, text="done")

    def _complete(
        self,
        sess: _Session,
        turn_id: str,
        correlation_id: str,
        *,
        text: str,
    ) -> None:
        if is_terminal_harness_state(sess.state) or sess.closed:
            return
        self._transition(sess, HarnessSessionState.COMPLETED)
        sess.terminal_reason = text
        self._emit(
            sess,
            HarnessEventType.SESSION_COMPLETED,
            {"summary": text},
            turn_id=turn_id,
            correlation_id=correlation_id,
        )

    def _fail_resource(self, sess: _Session, limit: str, correlation_id: str) -> None:
        if not is_terminal_harness_state(sess.state):
            if can_transition_harness(sess.state, HarnessSessionState.FAILED):
                self._transition(sess, HarnessSessionState.FAILED)
            elif can_transition_harness(sess.state, HarnessSessionState.CANCELLING):
                self._transition(sess, HarnessSessionState.CANCELLING)
                self._transition(sess, HarnessSessionState.FAILED)
        sess.terminal_reason = f"resource:{limit}"
        # Emit terminal events without re-applying the exhausted resource counters.
        for event_type, payload in (
            (
                HarnessEventType.ERROR,
                {"message": f"resource exhausted: {limit}", "limit": limit},
            ),
            (
                HarnessEventType.SESSION_FAILED,
                {"reason": f"resource:{limit}"},
            ),
        ):
            sess.seq += 1
            event_id = str(uuid.uuid4())
            sess.event_ids.add(event_id)
            sess.usage = replace(sess.usage, events=sess.usage.events + 1)
            sess.events.append(
                HarnessEvent(
                    event_id=event_id,
                    session_id=sess.req.session_id,
                    sequence_number=sess.seq,
                    event_type=event_type,
                    harness_id=HARNESS_ID,
                    timestamp=time.time(),
                    payload=payload,
                    run_id=sess.req.run_id,
                    mission_id=sess.req.mission_id,
                    organization_id=sess.req.organization_id,
                    workspace_id=sess.req.workspace_id,
                    correlation_id=correlation_id,
                    classification=EventClassification.INTERNAL,
                    redaction_state=EventRedactionState.NONE,
                )
            )

    def pop_pending_proposal(self, session_id: str) -> Optional[ToolProposal]:
        with self._lock:
            sess = self._require_session(session_id)
            if not sess.pending_proposals:
                return None
            return sess.pending_proposals.pop(0)
