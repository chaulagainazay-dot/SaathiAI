"""M48.3 — durable run lifecycle controller.

Thin coordinator over Orchestrator + RunStore. Does **not** replace the
runtime. Owns leases, cancellation persistence, timeout classification,
bounded retry classification, restart recovery, and stale reconciliation.
"""
from __future__ import annotations

import os
import socket
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from saathi.agent_runtime.models import RunState, is_terminal, can_transition
from saathi.agent_runtime.policy import is_transient, should_retry
from saathi.agent_runtime.store import RunStore

# ── classifications ───────────────────────────────────────────────────────


class RetryClass(str, Enum):
    RETRYABLE_TRANSIENT = "RETRYABLE_TRANSIENT"
    RETRYABLE_PROVIDER_UNAVAILABLE = "RETRYABLE_PROVIDER_UNAVAILABLE"
    NOT_RETRYABLE_VALIDATION = "NOT_RETRYABLE_VALIDATION"
    NOT_RETRYABLE_AUTHORITY = "NOT_RETRYABLE_AUTHORITY"
    NOT_RETRYABLE_APPROVAL = "NOT_RETRYABLE_APPROVAL"
    NOT_RETRYABLE_PROHIBITED = "NOT_RETRYABLE_PROHIBITED"
    NOT_RETRYABLE_MUTATION_UNCERTAIN = "NOT_RETRYABLE_MUTATION_UNCERTAIN"
    NOT_RETRYABLE_CANCELLED = "NOT_RETRYABLE_CANCELLED"
    NOT_RETRYABLE_DEADLINE_EXCEEDED = "NOT_RETRYABLE_DEADLINE_EXCEEDED"


class RecoveryAction(str, Enum):
    RESUME_SAFE = "RESUME_SAFE"
    RETRY_SAFE = "RETRY_SAFE"
    CANCEL_REQUIRED = "CANCEL_REQUIRED"
    TIMEOUT_REQUIRED = "TIMEOUT_REQUIRED"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    TERMINAL_NO_ACTION = "TERMINAL_NO_ACTION"


class StaleClass(str, Enum):
    ACTIVE_HEALTHY = "ACTIVE_HEALTHY"
    STALE_RECOVERABLE = "STALE_RECOVERABLE"
    STALE_RETRYABLE = "STALE_RETRYABLE"
    STALE_CANCELLATION_PENDING = "STALE_CANCELLATION_PENDING"
    STALE_TIMEOUT = "STALE_TIMEOUT"
    STALE_UNKNOWN_SIDE_EFFECT = "STALE_UNKNOWN_SIDE_EFFECT"
    TERMINAL = "TERMINAL"


class ReconcileAction(str, Enum):
    NO_ACTION = "NO_ACTION"
    MARK_TIMEOUT = "MARK_TIMEOUT"
    MARK_CANCELLED = "MARK_CANCELLED"
    SCHEDULE_RETRY = "SCHEDULE_RETRY"
    BLOCK_FOR_REVIEW = "BLOCK_FOR_REVIEW"
    RELEASE_STALE_LEASE = "RELEASE_STALE_LEASE"


# Backoff seconds by attempt index (bounded)
DEFAULT_BACKOFF = (0.0, 2.0, 10.0, 30.0)
DEFAULT_LEASE_SEC = 30.0
DEFAULT_HEARTBEAT_STALE_SEC = 45.0
DEFAULT_CANCEL_GRACE_SEC = 15.0
MAX_ATTEMPTS = 5


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


@dataclass
class CancelResult:
    ok: bool
    run_id: str
    cancel_status: str
    state: str
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LeaseResult:
    ok: bool
    run_id: str
    owner: str = ""
    expires_at: float = 0.0
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProviderHealth:
    name: str
    status: str  # SELECTED | UNAVAILABLE | CONFIGURATION_MISSING | PROHIBITED
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class RunLifecycleController:
    """Canonical lifecycle operations for agent_runtime runs."""

    def __init__(self, store: RunStore | None = None, *, lease_sec: float = DEFAULT_LEASE_SEC):
        self.store = store or RunStore()
        self.lease_sec = float(lease_sec)

    # ── cancellation ──────────────────────────────────────────────────────
    def request_cancel(
        self,
        rid: str,
        *,
        actor: str = "user:ajay",
        reason: str = "user_cancel",
    ) -> CancelResult:
        """Idempotent durable cancellation request + terminal transition when safe."""
        run = self.store.get_run(rid)
        if not run:
            return CancelResult(False, rid, "", "", "run not found")

        state = RunState(run["state"])
        if is_terminal(state):
            # already terminal — idempotent success if cancelled
            if state == RunState.CANCELLED:
                return CancelResult(True, rid, "completed", state.value, "already cancelled")
            return CancelResult(
                False,
                rid,
                run.get("cancel_status") or "",
                state.value,
                f"run already terminal: {state.value}",
            )

        now = time.time()
        prior = run.get("cancel_status") or ""
        if prior in ("requested", "propagating", "completed"):
            # idempotent re-request
            self.store.event(
                rid,
                "cancel.requested",
                {"actor": actor, "reason": reason, "idempotent": True},
            )
        else:
            self.store.update_lifecycle(
                rid,
                cancel_requested_at=now,
                cancel_reason=reason[:200],
                cancel_status="requested",
            )
            self.store.event(
                rid,
                "cancel.requested",
                {"actor": actor, "reason": reason, "idempotent": False},
            )

        self.store.update_lifecycle(rid, cancel_status="propagating")
        self.store.event(rid, "cancel.propagating", {"actor": actor})

        # Transition to CANCELLED (authoritative durable stop)
        try:
            if can_transition(state, RunState.CANCELLED):
                self.store.transition(
                    rid,
                    RunState.CANCELLED,
                    actor=actor,
                    terminal_reason=f"cancelled:{reason}"[:200],
                )
            else:
                # force via _safe path only if already cancelling-like
                self.store.update_lifecycle(
                    rid,
                    cancel_status="failed_to_stop",
                    last_error_code="CANCEL_TRANSITION_ILLEGAL",
                )
                return CancelResult(
                    False,
                    rid,
                    "failed_to_stop",
                    state.value,
                    f"cannot transition {state.value} → cancelled",
                )
        except Exception as exc:
            self.store.update_lifecycle(
                rid,
                cancel_status="failed_to_stop",
                last_error_code="CANCEL_FAILED",
            )
            self.store.event(rid, "cancel.failed_to_stop", {"error": repr(exc)[:200]})
            return CancelResult(False, rid, "failed_to_stop", state.value, str(exc)[:200])

        self.store.update_lifecycle(rid, cancel_status="completed", lease_owner="", lease_expires_at=0)
        self.store.event(rid, "cancel.completed", {"actor": actor})
        # skip pending tasks
        for t in self.store.list_tasks(rid):
            if t["status"] in ("pending", "ready", "running", "blocked"):
                self.store.update_task(t["id"], status="cancelled")
        return CancelResult(True, rid, "completed", RunState.CANCELLED.value, "cancelled")

    def is_cancel_requested(self, rid: str) -> bool:
        run = self.store.get_run(rid)
        if not run:
            return False
        if RunState(run["state"]) == RunState.CANCELLED:
            return True
        return bool(run.get("cancel_requested_at") or 0) > 0 or (
            run.get("cancel_status") or ""
        ) in ("requested", "propagating", "completed")

    def kill_switch(
        self,
        *,
        scope: str = "run",
        run_id: str = "",
        mission_id: str = "",
        actor: str = "operator",
        reason: str = "kill_switch",
    ) -> dict:
        """Cancel one run, mission-linked runs, or all active runs (local, durable)."""
        results = []
        if scope == "run":
            if not run_id:
                return {"ok": False, "error": "run_id required"}
            results.append(self.request_cancel(run_id, actor=actor, reason=reason).to_dict())
        elif scope == "mission":
            if not mission_id:
                return {"ok": False, "error": "mission_id required"}
            for run in self.store.list_active_runs(limit=500):
                budget = run.get("budget") or {}
                if budget.get("mission_id") == mission_id:
                    results.append(
                        self.request_cancel(run["id"], actor=actor, reason=reason).to_dict()
                    )
        elif scope == "all":
            for run in self.store.list_active_runs(limit=500):
                results.append(
                    self.request_cancel(run["id"], actor=actor, reason=reason).to_dict()
                )
        else:
            return {"ok": False, "error": f"unknown scope {scope}"}
        return {
            "ok": True,
            "scope": scope,
            "cancelled": sum(1 for r in results if r.get("ok")),
            "results": results,
        }

    # ── leases / heartbeats ───────────────────────────────────────────────
    def acquire_lease(
        self,
        rid: str,
        *,
        owner: str | None = None,
        lease_sec: float | None = None,
    ) -> LeaseResult:
        owner = owner or worker_id()
        lease_sec = float(lease_sec if lease_sec is not None else self.lease_sec)
        run = self.store.get_run(rid)
        if not run:
            return LeaseResult(False, rid, message="run not found")
        if is_terminal(RunState(run["state"])):
            return LeaseResult(False, rid, message="terminal run cannot acquire lease")
        if self.is_cancel_requested(rid):
            return LeaseResult(False, rid, message="cancellation blocks lease")

        now = time.time()
        current_owner = run.get("lease_owner") or ""
        expires = float(run.get("lease_expires_at") or 0)
        if current_owner and current_owner != owner and expires > now:
            return LeaseResult(
                False,
                rid,
                owner=current_owner,
                expires_at=expires,
                message="lease held by another worker",
            )
        exp = now + lease_sec
        self.store.update_lifecycle(
            rid,
            lease_owner=owner,
            lease_expires_at=exp,
            heartbeat_at=now,
        )
        self.store.event(rid, "lease.acquired", {"owner": owner, "expires_at": exp})
        return LeaseResult(True, rid, owner=owner, expires_at=exp, message="acquired")

    def heartbeat(self, rid: str, *, owner: str) -> LeaseResult:
        run = self.store.get_run(rid)
        if not run:
            return LeaseResult(False, rid, message="run not found")
        if (run.get("lease_owner") or "") != owner:
            return LeaseResult(False, rid, message="not lease owner")
        if is_terminal(RunState(run["state"])):
            return LeaseResult(False, rid, message="terminal")
        if self.is_cancel_requested(rid):
            return LeaseResult(False, rid, message="cancelled")
        now = time.time()
        exp = now + self.lease_sec
        self.store.update_lifecycle(rid, heartbeat_at=now, lease_expires_at=exp)
        return LeaseResult(True, rid, owner=owner, expires_at=exp, message="heartbeat")

    def release_lease(self, rid: str, *, owner: str) -> LeaseResult:
        run = self.store.get_run(rid)
        if not run:
            return LeaseResult(False, rid, message="run not found")
        if (run.get("lease_owner") or "") and run.get("lease_owner") != owner:
            return LeaseResult(False, rid, message="not lease owner")
        self.store.update_lifecycle(rid, lease_owner="", lease_expires_at=0)
        self.store.event(rid, "lease.released", {"owner": owner})
        return LeaseResult(True, rid, message="released")

    # ── timeout ───────────────────────────────────────────────────────────
    def check_deadline(self, rid: str, *, now: float | None = None) -> bool:
        """Return True if deadline exceeded (does not mutate)."""
        run = self.store.get_run(rid)
        if not run:
            return False
        deadline = float(run.get("deadline_at") or 0)
        if deadline <= 0:
            return False
        return (now if now is not None else time.time()) > deadline

    def enforce_timeout(self, rid: str, *, actor: str = "system") -> dict:
        run = self.store.get_run(rid)
        if not run:
            return {"ok": False, "error": "not found"}
        if is_terminal(RunState(run["state"])):
            return {"ok": True, "state": run["state"], "action": "none"}
        if not self.check_deadline(rid):
            return {"ok": True, "state": run["state"], "action": "within_deadline"}
        # timeout → request cancel semantics then TIMED_OUT
        self.store.update_lifecycle(
            rid,
            cancel_status="propagating",
            cancel_reason="timeout",
            cancel_requested_at=time.time(),
            last_error_code="TIMED_OUT",
        )
        try:
            if can_transition(RunState(run["state"]), RunState.TIMED_OUT):
                self.store.transition(
                    rid,
                    RunState.TIMED_OUT,
                    actor=actor,
                    terminal_reason="deadline_exceeded",
                )
            else:
                self.request_cancel(rid, actor=actor, reason="timeout")
        except Exception:
            self.request_cancel(rid, actor=actor, reason="timeout")
        self.store.event(rid, "run.timeout", {"deadline_at": run.get("deadline_at")})
        return {"ok": True, "state": "timed_out", "action": "timeout"}

    # ── retry ─────────────────────────────────────────────────────────────
    def classify_retry(
        self,
        *,
        error: str = "",
        attempts: int = 0,
        max_retries: int = 2,
        cancelled: bool = False,
        deadline_exceeded: bool = False,
        authority_denied: bool = False,
        approval_invalid: bool = False,
        prohibited: bool = False,
        mutation_uncertain: bool = False,
        provider_unavailable: bool = False,
        last_fingerprint: str | None = None,
        task_id: str = "task",
    ) -> tuple[RetryClass, bool, float]:
        """Return (classification, may_retry, backoff_sec)."""
        if cancelled:
            return RetryClass.NOT_RETRYABLE_CANCELLED, False, 0.0
        if deadline_exceeded:
            return RetryClass.NOT_RETRYABLE_DEADLINE_EXCEEDED, False, 0.0
        if prohibited:
            return RetryClass.NOT_RETRYABLE_PROHIBITED, False, 0.0
        if authority_denied:
            return RetryClass.NOT_RETRYABLE_AUTHORITY, False, 0.0
        if approval_invalid:
            return RetryClass.NOT_RETRYABLE_APPROVAL, False, 0.0
        if mutation_uncertain:
            return RetryClass.NOT_RETRYABLE_MUTATION_UNCERTAIN, False, 0.0
        if attempts >= min(max_retries, MAX_ATTEMPTS):
            return RetryClass.NOT_RETRYABLE_VALIDATION, False, 0.0

        if provider_unavailable or "unavailable" in (error or "").lower():
            backoff = DEFAULT_BACKOFF[min(attempts, len(DEFAULT_BACKOFF) - 1)]
            return RetryClass.RETRYABLE_PROVIDER_UNAVAILABLE, True, backoff

        ok, reason, _fp = should_retry(
            error=error,
            attempts=attempts,
            max_retries=max_retries,
            last_fingerprint=last_fingerprint,
            task_id=task_id,
        )
        if ok:
            backoff = DEFAULT_BACKOFF[min(attempts, len(DEFAULT_BACKOFF) - 1)]
            return RetryClass.RETRYABLE_TRANSIENT, True, backoff
        if "non-transient" in reason or "validation" in reason.lower():
            return RetryClass.NOT_RETRYABLE_VALIDATION, False, 0.0
        return RetryClass.NOT_RETRYABLE_VALIDATION, False, 0.0

    def bump_attempt(self, rid: str) -> int:
        run = self.store.get_run(rid)
        if not run:
            raise KeyError(rid)
        n = int(run.get("attempt") or 1) + 1
        self.store.update_lifecycle(rid, attempt=n)
        self.store.event(rid, "run.attempt", {"attempt": n})
        return n

    # ── recovery / reconcile ──────────────────────────────────────────────
    def classify_recovery(self, rid: str, *, now: float | None = None) -> RecoveryAction:
        run = self.store.get_run(rid)
        if not run:
            return RecoveryAction.MANUAL_REVIEW_REQUIRED
        now = now if now is not None else time.time()
        state = RunState(run["state"])
        if is_terminal(state):
            return RecoveryAction.TERMINAL_NO_ACTION
        if self.is_cancel_requested(rid):
            return RecoveryAction.CANCEL_REQUIRED
        if self.check_deadline(rid, now=now):
            return RecoveryAction.TIMEOUT_REQUIRED
        lease_exp = float(run.get("lease_expires_at") or 0)
        hb = float(run.get("heartbeat_at") or 0)
        if state == RunState.RUNNING and lease_exp and lease_exp < now:
            # expired lease — if no mutation evidence mid-flight, resume-safe
            events = self.store.events(rid, limit=20)
            mid = any(e["name"] == "task.started" for e in events[-5:])
            if mid and not any(e["name"] == "task.completed" for e in events[-5:]):
                return RecoveryAction.MANUAL_REVIEW_REQUIRED
            return RecoveryAction.RESUME_SAFE
        if state == RunState.RUNNING and hb and (now - hb) > DEFAULT_HEARTBEAT_STALE_SEC:
            return RecoveryAction.RECONCILE_REQUIRED
        if state in (RunState.QUEUED, RunState.APPROVED, RunState.PAUSED):
            return RecoveryAction.RESUME_SAFE
        if state == RunState.BLOCKED:
            return RecoveryAction.MANUAL_REVIEW_REQUIRED
        return RecoveryAction.RECONCILE_REQUIRED

    def recover_run(self, rid: str, *, actor: str = "system") -> dict:
        action = self.classify_recovery(rid)
        run = self.store.get_run(rid)
        self.store.event(
            rid,
            "recovery.classified",
            {"action": action.value, "actor": actor},
        )
        if action == RecoveryAction.TERMINAL_NO_ACTION:
            return {"ok": True, "action": action.value, "state": run and run["state"]}
        if action == RecoveryAction.CANCEL_REQUIRED:
            r = self.request_cancel(rid, actor=actor, reason="recovery_cancel")
            return {"ok": r.ok, "action": action.value, "result": r.to_dict()}
        if action == RecoveryAction.TIMEOUT_REQUIRED:
            return {
                "ok": True,
                "action": action.value,
                "result": self.enforce_timeout(rid, actor=actor),
            }
        if action == RecoveryAction.RESUME_SAFE:
            # release stale lease so a new worker can acquire
            self.store.update_lifecycle(rid, lease_owner="", lease_expires_at=0)
            self.store.event(rid, "recovery.resume_safe", {"actor": actor})
            return {"ok": True, "action": action.value, "state": run and run["state"]}
        if action == RecoveryAction.MANUAL_REVIEW_REQUIRED:
            self.store.update_lifecycle(
                rid,
                last_error_code="MANUAL_REVIEW_REQUIRED",
            )
            try:
                if run and can_transition(RunState(run["state"]), RunState.BLOCKED):
                    self.store.transition(
                        rid,
                        RunState.BLOCKED,
                        actor=actor,
                        terminal_reason="",
                    )
            except Exception:
                pass
            return {"ok": True, "action": action.value, "state": "blocked"}
        # RECONCILE / RETRY
        self.store.update_lifecycle(rid, lease_owner="", lease_expires_at=0)
        return {"ok": True, "action": action.value, "state": run and run["state"]}

    def recover_all(self, *, actor: str = "system") -> dict:
        results = []
        for run in self.store.list_active_runs(limit=200):
            results.append({"run_id": run["id"], **self.recover_run(run["id"], actor=actor)})
        return {"ok": True, "count": len(results), "results": results}

    def classify_stale(self, rid: str, *, now: float | None = None) -> StaleClass:
        run = self.store.get_run(rid)
        if not run:
            return StaleClass.TERMINAL
        now = now if now is not None else time.time()
        state = RunState(run["state"])
        if is_terminal(state):
            return StaleClass.TERMINAL
        if self.is_cancel_requested(rid) and state != RunState.CANCELLED:
            return StaleClass.STALE_CANCELLATION_PENDING
        if self.check_deadline(rid, now=now):
            return StaleClass.STALE_TIMEOUT
        lease_exp = float(run.get("lease_expires_at") or 0)
        hb = float(run.get("heartbeat_at") or 0)
        if state == RunState.RUNNING:
            if lease_exp and lease_exp < now:
                return StaleClass.STALE_UNKNOWN_SIDE_EFFECT
            if hb and (now - hb) > DEFAULT_HEARTBEAT_STALE_SEC:
                return StaleClass.STALE_RECOVERABLE
            return StaleClass.ACTIVE_HEALTHY
        if state in (RunState.QUEUED, RunState.APPROVED) and hb and (now - hb) > 120:
            return StaleClass.STALE_RETRYABLE
        return StaleClass.ACTIVE_HEALTHY

    def reconcile(self, rid: str, *, actor: str = "system") -> dict:
        cls = self.classify_stale(rid)
        action = ReconcileAction.NO_ACTION
        if cls == StaleClass.TERMINAL:
            action = ReconcileAction.NO_ACTION
        elif cls == StaleClass.STALE_TIMEOUT:
            action = ReconcileAction.MARK_TIMEOUT
            self.enforce_timeout(rid, actor=actor)
        elif cls == StaleClass.STALE_CANCELLATION_PENDING:
            action = ReconcileAction.MARK_CANCELLED
            self.request_cancel(rid, actor=actor, reason="reconcile_cancel")
        elif cls == StaleClass.STALE_UNKNOWN_SIDE_EFFECT:
            action = ReconcileAction.BLOCK_FOR_REVIEW
            self.recover_run(rid, actor=actor)
        elif cls in (StaleClass.STALE_RECOVERABLE, StaleClass.STALE_RETRYABLE):
            action = ReconcileAction.RELEASE_STALE_LEASE
            self.store.update_lifecycle(rid, lease_owner="", lease_expires_at=0)
            self.store.event(rid, "reconcile.release_lease", {"class": cls.value})
        self.store.event(
            rid,
            "reconcile.classified",
            {"class": cls.value, "action": action.value, "actor": actor},
        )
        return {"ok": True, "class": cls.value, "action": action.value}

    def reconcile_all(self, *, actor: str = "system") -> dict:
        out = []
        for run in self.store.list_active_runs(limit=200):
            out.append({"run_id": run["id"], **self.reconcile(run["id"], actor=actor)})
        return {"ok": True, "count": len(out), "results": out}


# ── provider health (no paid remote calls) ────────────────────────────────


def provider_health_evidence() -> list[ProviderHealth]:
    """Local/config evidence only — never calls paid remote APIs."""
    results: list[ProviderHealth] = []

    # Ollama local
    ollama = ProviderHealth(name="ollama", status="CONFIGURATION_MISSING", evidence={})
    try:
        import urllib.request

        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            body = resp.read(2000).decode("utf-8", "ignore")
            ollama = ProviderHealth(
                name="ollama",
                status="SELECTED",
                evidence={"reachable": True, "snippet_len": len(body)},
            )
    except Exception as exc:
        ollama = ProviderHealth(
            name="ollama",
            status="UNAVAILABLE",
            evidence={"reachable": False, "error": type(exc).__name__},
        )
    results.append(ollama)

    # model_router present?
    try:
        from saathi import model_router  # noqa: F401

        results.append(
            ProviderHealth(
                name="model_router",
                status="SELECTED",
                evidence={"module": "saathi.model_router", "configured": True},
            )
        )
    except Exception as exc:
        results.append(
            ProviderHealth(
                name="model_router",
                status="CONFIGURATION_MISSING",
                evidence={"error": type(exc).__name__},
            )
        )

    # Explicit: remote paid providers not probed
    results.append(
        ProviderHealth(
            name="remote_paid_providers",
            status="PROHIBITED",
            evidence={"reason": "M48.3 forbids paid remote probes", "probed": False},
        )
    )
    return results


def default_lifecycle(store: RunStore | None = None) -> RunLifecycleController:
    return RunLifecycleController(store=store)
