"""FM-I4 — In-process harness session governor (admission, queue, reservation, fairness).

This is NOT a general-purpose SaathiOS scheduler.
It does NOT execute tools, approve actions, or continue recovered drivers.
It composes under HarnessSessionController and never replaces ExecutionGateway.

Existing SaathiOS schedulers (MissionScheduler, TG research, platform cluster,
application_harness MonitorScheduler) remain separate owners of their domains.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Tuple
import threading
import time
import uuid

from saathi.agent_runtime.harness.errors import HarnessError, HarnessErrorCode
from saathi.agent_runtime.harness.governance_policy import (
    POLICY_VERSION,
    AdmissionDecision,
    HarnessResourcePolicy,
    LimitViolationKind,
    QueueEntryState,
    ReservationState,
)
from saathi.agent_runtime.harness.types import HarnessResourceUsage
from saathi.agent_runtime.models import RunState


def _new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:16]}"


@dataclass
class AdmissionRequest:
    session_id: str
    run_id: str
    mission_id: str
    organization_id: str
    workspace_id: str
    actor_id: str
    harness_id: str
    correlation_id: str
    priority: int = 0
    fairness_weight: int = 1
    harness_healthy: bool = True
    harness_quarantined: bool = False
    run_state: Optional[str] = None  # authoritative RunState value if known
    requested_at: float = field(default_factory=time.time)
    # Optional requested budget tighten (must not exceed policy)
    requested_max_turns: Optional[int] = None


@dataclass(frozen=True)
class AdmissionResult:
    decision: str
    reason: str
    queue_entry_id: str = ""
    reservation_id: str = ""
    policy_version: str = POLICY_VERSION
    detail: Mapping[str, Any] = field(default_factory=dict)

    @property
    def admitted(self) -> bool:
        return self.decision == AdmissionDecision.ADMIT_NOW

    @property
    def queued(self) -> bool:
        return self.decision == AdmissionDecision.QUEUE


@dataclass
class QueueEntry:
    queue_entry_id: str
    session_id: str
    run_id: str
    mission_id: str
    organization_id: str
    workspace_id: str
    harness_id: str
    correlation_id: str
    requested_at: float
    priority: int
    fairness_class: str  # usually organization_id
    fairness_weight: int
    policy_version: str
    queue_deadline: float
    state: str = QueueEntryState.QUEUED
    disposition_reason: str = ""
    integrity_token: str = ""

    def __post_init__(self) -> None:
        if not self.integrity_token:
            self.integrity_token = f"{self.queue_entry_id}:{self.session_id}:{self.run_id}"


@dataclass
class Reservation:
    reservation_id: str
    session_id: str
    organization_id: str
    workspace_id: str
    harness_id: str
    run_id: str
    held_at: float
    state: str = ReservationState.HELD
    released_at: float = 0.0
    release_reason: str = ""


@dataclass
class SessionUsageTracker:
    """Live enforcement counters for an admitted session."""

    session_id: str
    admitted_at: float
    last_activity_at: float
    approval_wait_started_at: float = 0.0
    cancel_requested_at: float = 0.0
    turns: int = 0
    events: int = 0
    output_chars: int = 0
    logical_tokens: int = 0
    tool_proposals: int = 0
    retries: int = 0
    terminated: bool = False
    termination_reason: str = ""


class HarnessSessionGovernor:
    """Bounded admission, queue, reservation, fairness, and live limit enforcement.

    Explicit cleanup only — no background threads or cron.
    """

    def __init__(
        self,
        policy: Optional[HarnessResourcePolicy] = None,
        *,
        clock=None,
    ) -> None:
        self.policy = policy or HarnessResourcePolicy.default()
        self._clock = clock or time.time
        self._lock = threading.RLock()
        # Active admitted sessions (session_id -> metadata)
        self._active: Dict[str, Dict[str, Any]] = {}
        self._reservations: Dict[str, Reservation] = {}
        self._reservations_by_session: Dict[str, str] = {}
        self._queue: Dict[str, QueueEntry] = {}  # queue_entry_id -> entry
        self._queue_by_session: Dict[str, str] = {}
        self._usage: Dict[str, SessionUsageTracker] = {}
        # Fairness: last served org order
        self._org_rr_cursor: int = 0
        self._org_order: List[str] = []
        # Metrics
        self.metrics: Dict[str, int] = {
            "admitted": 0,
            "queued": 0,
            "rejected": 0,
            "expired_queue": 0,
            "resource_limit_terminations": 0,
            "cancelled": 0,
            "reservations_released": 0,
            "cleanup_runs": 0,
        }
        self._audit_log: List[Dict[str, Any]] = []

    def now(self) -> float:
        return float(self._clock())

    def decisions_audit(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)

    def _audit(self, action: str, **detail: Any) -> None:
        self._audit_log.append(
            {"action": action, "ts": self.now(), **detail}
        )

    # ── Counts ──────────────────────────────────────────────────────────────

    def active_count(self) -> int:
        return len(self._active)

    def queued_count(self) -> int:
        return sum(
            1
            for e in self._queue.values()
            if e.state in (QueueEntryState.QUEUED, QueueEntryState.ELIGIBLE)
        )

    def active_for_org(self, org: str) -> int:
        return sum(1 for m in self._active.values() if m.get("organization_id") == org)

    def active_for_workspace(self, org: str, ws: str) -> int:
        return sum(
            1
            for m in self._active.values()
            if m.get("organization_id") == org and m.get("workspace_id") == ws
        )

    def active_for_harness(self, harness_id: str) -> int:
        return sum(1 for m in self._active.values() if m.get("harness_id") == harness_id)

    def active_for_run(self, run_id: str) -> int:
        return sum(1 for m in self._active.values() if m.get("run_id") == run_id)

    def queued_for_org(self, org: str) -> int:
        return sum(
            1
            for e in self._queue.values()
            if e.organization_id == org
            and e.state in (QueueEntryState.QUEUED, QueueEntryState.ELIGIBLE)
        )

    def queued_for_workspace(self, org: str, ws: str) -> int:
        return sum(
            1
            for e in self._queue.values()
            if e.organization_id == org
            and e.workspace_id == ws
            and e.state in (QueueEntryState.QUEUED, QueueEntryState.ELIGIBLE)
        )

    def snapshot_metrics(self) -> Dict[str, Any]:
        with self._lock:
            waits = [
                self.now() - e.requested_at
                for e in self._queue.values()
                if e.state in (QueueEntryState.QUEUED, QueueEntryState.ELIGIBLE)
            ]
            return {
                **self.metrics,
                "active_sessions": self.active_count(),
                "queued_sessions": self.queued_count(),
                "held_reservations": sum(
                    1 for r in self._reservations.values() if r.state == ReservationState.HELD
                ),
                "average_queue_wait": (sum(waits) / len(waits)) if waits else 0.0,
                "maximum_queue_wait": max(waits) if waits else 0.0,
                "policy_version": self.policy.policy_version,
            }

    # ── Admission ───────────────────────────────────────────────────────────

    def admit(self, req: AdmissionRequest) -> AdmissionResult:
        with self._lock:
            return self._admit_locked(req)

    def _admit_locked(self, req: AdmissionRequest) -> AdmissionResult:
        pol = self.policy
        # Scope
        if not req.organization_id or not req.workspace_id or not req.run_id:
            return self._reject(
                AdmissionDecision.REJECT_SCOPE,
                "missing organization_id, workspace_id, or run_id",
                req,
            )
        if not req.session_id or not req.actor_id or not req.correlation_id:
            return self._reject(
                AdmissionDecision.REJECT_SCOPE,
                "missing session_id, actor_id, or correlation_id",
                req,
            )
        # Terminal run
        if req.run_state in {
            RunState.CANCELLED.value,
            RunState.FAILED.value,
            RunState.COMPLETED.value,
            RunState.TIMED_OUT.value,
            RunState.ROLLED_BACK.value,
        }:
            return self._reject(
                AdmissionDecision.REJECT_TERMINAL_RUN,
                f"run is terminal: {req.run_state}",
                req,
            )
        # Health / quarantine
        if pol.admission.reject_unhealthy_harness and not req.harness_healthy:
            return self._reject(
                AdmissionDecision.REJECT_UNHEALTHY, "harness unhealthy", req
            )
        if pol.admission.reject_quarantined_harness and req.harness_quarantined:
            return self._reject(
                AdmissionDecision.REJECT_QUARANTINED_HARNESS,
                "harness quarantined",
                req,
            )
        # Budget request cannot exceed policy
        if req.requested_max_turns is not None:
            if req.requested_max_turns > pol.max_turns_per_session:
                return self._reject(
                    AdmissionDecision.REJECT_RESOURCE_BUDGET,
                    "requested turns exceed policy",
                    req,
                )
            if req.requested_max_turns < 1:
                return self._reject(
                    AdmissionDecision.REJECT_POLICY,
                    "requested turns must be >= 1",
                    req,
                )
        # Priority ceiling
        if req.priority > pol.queue.priority_ceiling:
            return self._reject(
                AdmissionDecision.REJECT_POLICY,
                f"priority {req.priority} exceeds ceiling {pol.queue.priority_ceiling}",
                req,
            )
        # Duplicate active session for run
        if (
            not pol.admission.allow_multiple_sessions_per_run
            and self.active_for_run(req.run_id) > 0
            and req.session_id not in self._active
        ):
            return self._reject(
                AdmissionDecision.REJECT_DUPLICATE_RUN,
                "active session already exists for run",
                req,
            )
        # Already active (idempotent)
        if req.session_id in self._active:
            rid = self._reservations_by_session.get(req.session_id, "")
            return AdmissionResult(
                decision=AdmissionDecision.ADMIT_NOW,
                reason="already_admitted",
                reservation_id=rid,
                detail={"idempotent": True},
            )
        # Capacity checks for immediate admit
        if self._has_capacity(req):
            res = self._reserve(req)
            self._activate(req, res.reservation_id)
            self.metrics["admitted"] += 1
            self._audit(
                "admit_now",
                session_id=req.session_id,
                org=req.organization_id,
                reservation_id=res.reservation_id,
            )
            return AdmissionResult(
                decision=AdmissionDecision.ADMIT_NOW,
                reason="capacity_available",
                reservation_id=res.reservation_id,
            )
        # Try queue
        if self._can_queue(req):
            entry = self._enqueue(req)
            self.metrics["queued"] += 1
            self._audit(
                "queued",
                session_id=req.session_id,
                queue_entry_id=entry.queue_entry_id,
                org=req.organization_id,
            )
            return AdmissionResult(
                decision=AdmissionDecision.QUEUE,
                reason="capacity_full_queued",
                queue_entry_id=entry.queue_entry_id,
            )
        self.metrics["rejected"] += 1
        return self._reject(
            AdmissionDecision.REJECT_CAPACITY,
            "no active or queue capacity",
            req,
        )

    def _has_capacity(self, req: AdmissionRequest) -> bool:
        pol = self.policy.admission
        if self.active_count() >= pol.max_active_sessions_global:
            return False
        if self.active_for_org(req.organization_id) >= pol.max_active_sessions_per_org:
            return False
        if (
            self.active_for_workspace(req.organization_id, req.workspace_id)
            >= pol.max_active_sessions_per_workspace
        ):
            return False
        if (
            self.active_for_harness(req.harness_id)
            >= pol.max_active_sessions_per_harness
        ):
            return False
        return True

    def _can_queue(self, req: AdmissionRequest) -> bool:
        q = self.policy.queue
        if self.queued_count() >= q.max_queued_sessions_global:
            return False
        if self.queued_for_org(req.organization_id) >= q.max_queued_sessions_per_org:
            return False
        if (
            self.queued_for_workspace(req.organization_id, req.workspace_id)
            >= q.max_queued_sessions_per_workspace
        ):
            return False
        if req.session_id in self._queue_by_session:
            return False
        return True

    def _reject(self, decision: str, reason: str, req: AdmissionRequest) -> AdmissionResult:
        self.metrics["rejected"] += 1
        self._audit(
            "reject",
            decision=decision,
            reason=reason,
            session_id=req.session_id,
            org=req.organization_id,
        )
        return AdmissionResult(decision=decision, reason=reason)

    def _reserve(self, req: AdmissionRequest) -> Reservation:
        rid = _new_id("rsv-")
        res = Reservation(
            reservation_id=rid,
            session_id=req.session_id,
            organization_id=req.organization_id,
            workspace_id=req.workspace_id,
            harness_id=req.harness_id,
            run_id=req.run_id,
            held_at=self.now(),
            state=ReservationState.HELD,
        )
        self._reservations[rid] = res
        self._reservations_by_session[req.session_id] = rid
        return res

    def _activate(self, req: AdmissionRequest, reservation_id: str) -> None:
        now = self.now()
        self._active[req.session_id] = {
            "session_id": req.session_id,
            "run_id": req.run_id,
            "mission_id": req.mission_id,
            "organization_id": req.organization_id,
            "workspace_id": req.workspace_id,
            "harness_id": req.harness_id,
            "actor_id": req.actor_id,
            "reservation_id": reservation_id,
            "admitted_at": now,
            "priority": req.priority,
        }
        self._usage[req.session_id] = SessionUsageTracker(
            session_id=req.session_id,
            admitted_at=now,
            last_activity_at=now,
        )
        if req.organization_id not in self._org_order:
            self._org_order.append(req.organization_id)

    def _enqueue(self, req: AdmissionRequest) -> QueueEntry:
        qid = _new_id("q-")
        weight = max(1, min(10, req.fairness_weight or self.policy.queue.default_fairness_weight))
        entry = QueueEntry(
            queue_entry_id=qid,
            session_id=req.session_id,
            run_id=req.run_id,
            mission_id=req.mission_id,
            organization_id=req.organization_id,
            workspace_id=req.workspace_id,
            harness_id=req.harness_id,
            correlation_id=req.correlation_id,
            requested_at=req.requested_at or self.now(),
            priority=min(req.priority, self.policy.queue.priority_ceiling),
            fairness_class=req.organization_id,
            fairness_weight=weight,
            policy_version=self.policy.policy_version,
            queue_deadline=self.now() + self.policy.timeouts.max_queue_wait_seconds,
            state=QueueEntryState.QUEUED,
        )
        self._queue[qid] = entry
        self._queue_by_session[req.session_id] = qid
        if req.organization_id not in self._org_order:
            self._org_order.append(req.organization_id)
        return entry

    # ── Fair scheduling (drain queue) ───────────────────────────────────────

    def schedule_next(self, *, max_admit: int = 1) -> List[AdmissionResult]:
        """Admit up to max_admit eligible queued sessions using fair org RR + age promotion."""
        with self._lock:
            admitted: List[AdmissionResult] = []
            self._expire_queue_locked()
            for _ in range(max_admit):
                entry = self._pick_next_locked()
                if entry is None:
                    break
                if not self._has_capacity_for_entry(entry):
                    break
                # Reserve + activate
                req = AdmissionRequest(
                    session_id=entry.session_id,
                    run_id=entry.run_id,
                    mission_id=entry.mission_id,
                    organization_id=entry.organization_id,
                    workspace_id=entry.workspace_id,
                    actor_id="scheduled",
                    harness_id=entry.harness_id,
                    correlation_id=entry.correlation_id,
                    priority=entry.priority,
                    fairness_weight=entry.fairness_weight,
                )
                res = self._reserve(req)
                self._activate(req, res.reservation_id)
                entry.state = QueueEntryState.ADMITTED
                entry.disposition_reason = "scheduled"
                self._queue_by_session.pop(entry.session_id, None)
                self.metrics["admitted"] += 1
                self._audit(
                    "schedule_admit",
                    session_id=entry.session_id,
                    queue_entry_id=entry.queue_entry_id,
                    reservation_id=res.reservation_id,
                )
                admitted.append(
                    AdmissionResult(
                        decision=AdmissionDecision.ADMIT_NOW,
                        reason="scheduled_from_queue",
                        queue_entry_id=entry.queue_entry_id,
                        reservation_id=res.reservation_id,
                    )
                )
            return admitted

    def _has_capacity_for_entry(self, entry: QueueEntry) -> bool:
        return self._has_capacity(
            AdmissionRequest(
                session_id=entry.session_id,
                run_id=entry.run_id,
                mission_id=entry.mission_id,
                organization_id=entry.organization_id,
                workspace_id=entry.workspace_id,
                actor_id="x",
                harness_id=entry.harness_id,
                correlation_id=entry.correlation_id,
            )
        )

    def _pick_next_locked(self) -> Optional[QueueEntry]:
        """Fair pick: age-promoted first, then org round-robin among eligible."""
        now = self.now()
        candidates = [
            e
            for e in self._queue.values()
            if e.state in (QueueEntryState.QUEUED, QueueEntryState.ELIGIBLE)
        ]
        if not candidates:
            return None
        # Age promotion
        aged = [
            e
            for e in candidates
            if (now - e.requested_at) >= self.policy.queue.age_promotion_seconds
        ]
        pool = aged if aged else candidates
        # Highest priority first within pool (bounded)
        pool.sort(key=lambda e: (-e.priority, e.requested_at, e.queue_entry_id))
        # Org RR among top priority tier
        top_pri = pool[0].priority
        top = [e for e in pool if e.priority == top_pri]
        if not self._org_order:
            return top[0]
        # Rotate through orgs
        n = len(self._org_order)
        for i in range(n):
            idx = (self._org_rr_cursor + i) % n
            org = self._org_order[idx]
            for e in top:
                if e.organization_id == org:
                    self._org_rr_cursor = (idx + 1) % n
                    return e
        return top[0]

    def _expire_queue_locked(self) -> None:
        now = self.now()
        for e in list(self._queue.values()):
            if e.state not in (QueueEntryState.QUEUED, QueueEntryState.ELIGIBLE):
                continue
            if now >= e.queue_deadline:
                e.state = QueueEntryState.EXPIRED
                e.disposition_reason = "queue_timeout"
                self._queue_by_session.pop(e.session_id, None)
                self.metrics["expired_queue"] += 1
                self._audit(
                    "queue_expired",
                    session_id=e.session_id,
                    queue_entry_id=e.queue_entry_id,
                )

    # ── Release / cancel ────────────────────────────────────────────────────

    def release(self, session_id: str, *, reason: str = "completed") -> None:
        """Idempotent capacity release for terminal sessions."""
        with self._lock:
            self._active.pop(session_id, None)
            usage = self._usage.get(session_id)
            if usage:
                usage.terminated = True
                usage.termination_reason = reason
            rid = self._reservations_by_session.pop(session_id, None)
            if rid and rid in self._reservations:
                res = self._reservations[rid]
                if res.state == ReservationState.HELD:
                    res.state = ReservationState.RELEASED
                    res.released_at = self.now()
                    res.release_reason = reason
                    self.metrics["reservations_released"] += 1
            qid = self._queue_by_session.pop(session_id, None)
            if qid and qid in self._queue:
                e = self._queue[qid]
                if e.state in (QueueEntryState.QUEUED, QueueEntryState.ELIGIBLE):
                    e.state = QueueEntryState.CANCELLED
                    e.disposition_reason = reason
            self._audit("release", session_id=session_id, reason=reason)

    def cancel_queued(self, session_id: str, *, reason: str = "cancelled") -> bool:
        with self._lock:
            qid = self._queue_by_session.get(session_id)
            if not qid:
                return False
            e = self._queue[qid]
            if e.state in (QueueEntryState.QUEUED, QueueEntryState.ELIGIBLE):
                e.state = QueueEntryState.CANCELLED
                e.disposition_reason = reason
                self._queue_by_session.pop(session_id, None)
                self.metrics["cancelled"] += 1
                self._audit("cancel_queued", session_id=session_id, reason=reason)
                return True
            return False

    def mark_cancel_requested(self, session_id: str) -> None:
        with self._lock:
            u = self._usage.get(session_id)
            if u and not u.cancel_requested_at:
                u.cancel_requested_at = self.now()

    # ── Live enforcement ────────────────────────────────────────────────────

    def record_activity(
        self,
        session_id: str,
        *,
        turns: int = 0,
        events: int = 0,
        output_chars: int = 0,
        logical_tokens: int = 0,
        tool_proposals: int = 0,
        retries: int = 0,
        approval_waiting: bool = False,
        absolute: bool = False,
    ) -> Optional[str]:
        """Update usage; return LimitViolationKind value if limit exceeded.

        When absolute=True, counters are set to the provided values (not added).
        """
        with self._lock:
            u = self._usage.get(session_id)
            if u is None or u.terminated:
                return None
            now = self.now()
            u.last_activity_at = now
            if absolute:
                u.turns = turns
                u.events = events
                u.output_chars = output_chars
                u.logical_tokens = logical_tokens
                u.tool_proposals = tool_proposals
                u.retries = retries
            else:
                u.turns += turns
                u.events += events
                u.output_chars += output_chars
                u.logical_tokens += logical_tokens
                u.tool_proposals += tool_proposals
                u.retries += retries
            if approval_waiting and not u.approval_wait_started_at:
                u.approval_wait_started_at = now
            if not approval_waiting:
                u.approval_wait_started_at = 0.0
            return self._check_limits_locked(u)

    def check_timeouts(self, session_id: str) -> Optional[str]:
        with self._lock:
            u = self._usage.get(session_id)
            if u is None or u.terminated:
                return None
            return self._check_limits_locked(u)

    def _check_limits_locked(self, u: SessionUsageTracker) -> Optional[str]:
        pol = self.policy
        now = self.now()
        checks = (
            (u.turns > pol.max_turns_per_session, LimitViolationKind.TURNS),
            (u.events > pol.max_events_per_session, LimitViolationKind.EVENTS),
            (u.output_chars > pol.max_output_chars_per_session, LimitViolationKind.OUTPUT),
            (u.logical_tokens > pol.max_logical_tokens_per_session, LimitViolationKind.TOKENS),
            (u.tool_proposals > pol.max_tool_proposals_per_session, LimitViolationKind.TOOL_PROPOSALS),
            (u.retries > pol.max_retries_per_operation, LimitViolationKind.RETRIES),
            (
                (now - u.admitted_at) > pol.timeouts.max_session_duration_seconds,
                LimitViolationKind.SESSION_DURATION,
            ),
            (
                (now - u.last_activity_at) > pol.timeouts.max_idle_seconds,
                LimitViolationKind.IDLE,
            ),
        )
        for hit, kind in checks:
            if hit:
                return self._terminate_limit(u, kind)
        if u.approval_wait_started_at:
            if (now - u.approval_wait_started_at) > pol.timeouts.max_approval_wait_seconds:
                return self._terminate_limit(u, LimitViolationKind.APPROVAL_WAIT)
        if u.cancel_requested_at:
            if (now - u.cancel_requested_at) > pol.timeouts.cancellation_grace_seconds:
                return self._terminate_limit(u, LimitViolationKind.CANCEL_ACK)
        return None

    def _terminate_limit(self, u: SessionUsageTracker, kind: str) -> str:
        u.terminated = True
        u.termination_reason = kind
        self.metrics["resource_limit_terminations"] += 1
        self._audit("limit_violation", session_id=u.session_id, kind=kind)
        # Release capacity
        self._active.pop(u.session_id, None)
        rid = self._reservations_by_session.pop(u.session_id, None)
        if rid and rid in self._reservations:
            res = self._reservations[rid]
            if res.state == ReservationState.HELD:
                res.state = ReservationState.RELEASED
                res.released_at = self.now()
                res.release_reason = kind
                self.metrics["reservations_released"] += 1
        return kind

    def usage_snapshot(self, session_id: str) -> Optional[Dict[str, Any]]:
        u = self._usage.get(session_id)
        if not u:
            return None
        return {
            "turns": u.turns,
            "events": u.events,
            "output_chars": u.output_chars,
            "logical_tokens": u.logical_tokens,
            "tool_proposals": u.tool_proposals,
            "retries": u.retries,
            "admitted_at": u.admitted_at,
            "last_activity_at": u.last_activity_at,
            "terminated": u.terminated,
            "termination_reason": u.termination_reason,
        }

    # ── Cleanup / reconciliation ────────────────────────────────────────────

    def cleanup(self) -> Dict[str, Any]:
        """Deterministic explicit cleanup — no background thread."""
        with self._lock:
            self.metrics["cleanup_runs"] += 1
            expired = 0
            self._expire_queue_locked()
            expired = sum(
                1 for e in self._queue.values() if e.state == QueueEntryState.EXPIRED
            )
            # Reconcile leaked reservations: HELD but session not active
            leaked = 0
            for rid, res in list(self._reservations.items()):
                if res.state != ReservationState.HELD:
                    continue
                if res.session_id not in self._active:
                    res.state = ReservationState.LEAKED_RECONCILED
                    res.released_at = self.now()
                    res.release_reason = "leaked_reservation_reconciled"
                    self._reservations_by_session.pop(res.session_id, None)
                    self.metrics["reservations_released"] += 1
                    leaked += 1
                    self._audit("reconcile_leak", session_id=res.session_id, reservation_id=rid)
            return {
                "expired_queue_entries": expired,
                "leaked_reservations_reconciled": leaked,
                "active": self.active_count(),
                "queued": self.queued_count(),
            }

    def restart_reconcile(self) -> Dict[str, Any]:
        """After restart: clear live capacity; do not auto-continue work.

        Durable queue metadata (if any) is inspection-only; live governor resets.
        """
        with self._lock:
            active = list(self._active.keys())
            queued = [
                e.session_id
                for e in self._queue.values()
                if e.state in (QueueEntryState.QUEUED, QueueEntryState.ELIGIBLE)
            ]
            held = [
                r.session_id
                for r in self._reservations.values()
                if r.state == ReservationState.HELD
            ]
            # Safe reset: mark all HELD as reconciled, clear active
            for rid, res in self._reservations.items():
                if res.state == ReservationState.HELD:
                    res.state = ReservationState.LEAKED_RECONCILED
                    res.released_at = self.now()
                    res.release_reason = "restart_reconcile"
            self._active.clear()
            self._reservations_by_session.clear()
            self._usage.clear()
            for e in self._queue.values():
                if e.state in (QueueEntryState.QUEUED, QueueEntryState.ELIGIBLE):
                    e.state = QueueEntryState.QUARANTINED
                    e.disposition_reason = "restart_requires_explicit_reschedule"
            self._queue_by_session.clear()
            self._audit(
                "restart_reconcile",
                prior_active=len(active),
                prior_queued=len(queued),
                prior_held=len(held),
            )
            return {
                "prior_active": active,
                "prior_queued": queued,
                "prior_held_reservations": held,
                "auto_continue": False,
            }

    def list_queued(self) -> List[QueueEntry]:
        return [
            e
            for e in self._queue.values()
            if e.state in (QueueEntryState.QUEUED, QueueEntryState.ELIGIBLE)
        ]

    def get_queue_entry(self, session_id: str) -> Optional[QueueEntry]:
        qid = self._queue_by_session.get(session_id)
        if not qid:
            # Search terminal too
            for e in self._queue.values():
                if e.session_id == session_id:
                    return e
            return None
        return self._queue.get(qid)

    def export_scheduling_metadata(self) -> Dict[str, Any]:
        """Durable-friendly snapshot for restart inspection (not a job queue)."""
        with self._lock:
            return {
                "policy_version": self.policy.policy_version,
                "exported_at": self.now(),
                "active": list(self._active.values()),
                "queue": [
                    {
                        "queue_entry_id": e.queue_entry_id,
                        "session_id": e.session_id,
                        "run_id": e.run_id,
                        "organization_id": e.organization_id,
                        "workspace_id": e.workspace_id,
                        "priority": e.priority,
                        "state": e.state,
                        "requested_at": e.requested_at,
                        "queue_deadline": e.queue_deadline,
                        "disposition_reason": e.disposition_reason,
                    }
                    for e in self._queue.values()
                ],
                "reservations": [
                    {
                        "reservation_id": r.reservation_id,
                        "session_id": r.session_id,
                        "state": r.state,
                        "held_at": r.held_at,
                        "released_at": r.released_at,
                        "release_reason": r.release_reason,
                    }
                    for r in self._reservations.values()
                ],
                "metrics": self.snapshot_metrics(),
            }
