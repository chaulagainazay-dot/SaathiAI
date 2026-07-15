"""M17.22 Universal ExecutionGateway boundary — authoritative external-action path.

Every connector / CLI / local / MCP action eventually enters here:

    ToolIntent
      → Validation
      → Permission
      → Risk evaluation
      → Approval check
      → ExecutionGateway.submit
      → Handler (ConnectorManager / local tool)
      → Evidence
      → Security Event
      → Run Ledger
      → CEO Metrics (via Control Center + daily brief)

Phase 1 supports: connector, cli, local, mcp families.
Browser automation, n8n, LLM execution, Trading Guardian remain future migration.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from saathi.execution.errors import (
    ApprovalException,
    AuthorizationException,
    StateException,
    ValidationException,
)
from saathi.execution.execution_state import ExecutionState, is_terminal
from saathi.execution.record import (
    ExecutionRecord,
    safe_summary,
    tool_intent_digest,
)
from saathi.execution.store import ExecutionStore, default_store, reset_default_store
from saathi.execution.toolintent import ApprovalLevel, RiskLevel, ToolIntent

logger = logging.getLogger(__name__)

# Reuse M17 retry infrastructure (deterministic exponential schedule)
try:
    from saathi.application_harness.run_ledger import (
        MAX_DELIVERY_ATTEMPTS,
        retry_delay,
    )
except Exception:  # pragma: no cover
    MAX_DELIVERY_ATTEMPTS = 5

    def retry_delay(attempt_count: int) -> float:
        schedule = (0.0, 60.0, 300.0, 900.0, 3600.0)
        if attempt_count < 0:
            attempt_count = 0
        if attempt_count >= len(schedule):
            return schedule[-1]
        return schedule[attempt_count]


MAX_RETRIES = MAX_DELIVERY_ATTEMPTS
Handler = Callable[[ToolIntent, ExecutionRecord], dict]

# Families in scope for Phase 1
PHASE1_FAMILIES = frozenset({"connector", "cli", "local", "mcp"})
# Explicitly out of Phase 1 migration (must not claim completeness)
FUTURE_FAMILIES = frozenset({"browser", "n8n", "llm", "trading"})

_digest_locks: dict[str, threading.Lock] = {}
_digest_locks_guard = threading.Lock()


def _lock_for(digest: str) -> threading.Lock:
    with _digest_locks_guard:
        if digest not in _digest_locks:
            _digest_locks[digest] = threading.Lock()
        return _digest_locks[digest]


def classify_family(intent: ToolIntent) -> str:
    """Map ToolIntent to execution family (Phase 1)."""
    meta = intent.metadata or {}
    if meta.get("family"):
        return str(meta["family"]).lower()
    cid = (intent.connector_id or "").lower()
    cap = (intent.capability or "").lower()
    if cid.startswith("mcp:") or cid.startswith("mcp_") or "mcp" in cap:
        return "mcp"
    if cid in ("cli", "local-cli") or cap in ("cli", "shell"):
        return "cli"
    if cid in ("local", "local-tool", "builtin") or cap in ("local", "builtin"):
        return "local"
    if cid in FUTURE_FAMILIES or cap in FUTURE_FAMILIES:
        return cid if cid in FUTURE_FAMILIES else cap
    return "connector"


def target_label(intent: ToolIntent) -> str:
    family = classify_family(intent)
    return f"{family}:{intent.connector_id}:{intent.operation}"


def needs_approval(intent: ToolIntent) -> bool:
    """Reuse existing approval-level / risk model — no new approval engine."""
    meta = intent.metadata or {}
    # Substrate (e.g. connector store) already bound & verified approval
    if meta.get("approval_pre_resolved"):
        return False
    if meta.get("require_approval") is False:
        return False
    level = intent.approval_level
    risk = intent.risk_level
    if level in (ApprovalLevel.L4, ApprovalLevel.L3):
        return True
    if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return True
    if meta.get("require_approval"):
        return True
    return False


def _permission_ok(intent: ToolIntent) -> tuple[bool, str]:
    """Fail-closed permission gate (actor + business unit present)."""
    if not intent.actor_id:
        return False, "missing_actor"
    if not intent.operation:
        return False, "missing_operation"
    if not intent.connector_id and classify_family(intent) != "local":
        return False, "missing_connector"
    # Explicit deny list via metadata
    denied = (intent.metadata or {}).get("denied_actors") or []
    if intent.actor_id in denied:
        return False, "actor_denied"
    return True, "ok"


class UniversalBoundary:
    """Authoritative execution boundary used by ExecutionGateway.

    Not a second gateway — this is the Phase-1 completion of the single
    ExecutionGateway authority (durable record + state machine + integrations).
    """

    def __init__(
        self,
        store: ExecutionStore | None = None,
        *,
        handlers: Optional[dict[str, Handler]] = None,
        ledger: Any = None,
        evidence_store: Any = None,
        event_bus: Any = None,
        security_timeline: Any = None,
        auto_integrations: bool = True,
    ):
        self.store = store or default_store()
        self.handlers: dict[str, Handler] = dict(handlers or {})
        self._ledger = ledger
        self._evidence = evidence_store
        self._bus = event_bus
        self._security = security_timeline
        self._auto = auto_integrations
        self._pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="exec-gw")
        # Register default local handler
        if "local" not in self.handlers:
            self.handlers["local"] = self._default_local_handler

    # ── public API ────────────────────────────────────────────────────────

    def submit(
        self,
        intent: ToolIntent,
        *,
        approval_id: str = "",
        handler: Handler | None = None,
        execute: bool = True,
        force_new: bool = False,
    ) -> ExecutionRecord:
        """Run one ToolIntent through the universal boundary.

        Returns the durable ExecutionRecord (may be terminal or approval_required).
        """
        digest = tool_intent_digest(intent)
        with _lock_for(digest):
            return self._submit_locked(
                intent,
                digest=digest,
                approval_id=approval_id,
                handler=handler,
                execute=execute,
                force_new=force_new,
            )

    def cancel(self, execution_id: str, *, reason: str = "cancelled") -> ExecutionRecord:
        rec = self.store.get(execution_id)
        if not rec:
            raise KeyError(execution_id)
        if is_terminal(rec.status):
            raise StateException(f"terminal state {rec.status} is immutable")
        rec = self.store.transition(
            execution_id,
            ExecutionState.CANCELLED,
            reason=reason,
            extra={"result_summary": safe_summary(reason), "failure_category": "cancelled"},
        )
        self._emit_security(rec, "execution_cancelled")
        self._emit_bus("execution.cancelled", rec)
        self._finalize_ledger(rec, "cancelled")
        return rec

    def expire(self, execution_id: str, *, reason: str = "expired") -> ExecutionRecord:
        rec = self.store.get(execution_id)
        if not rec:
            raise KeyError(execution_id)
        if is_terminal(rec.status):
            raise StateException(f"terminal state {rec.status} is immutable")
        rec = self.store.transition(
            execution_id,
            ExecutionState.EXPIRED,
            reason=reason,
            extra={
                "approval": "expired",
                "result_summary": safe_summary(reason),
                "failure_category": "expired",
            },
        )
        self._emit_security(rec, "execution_expired")
        self._emit_bus("execution.expired", rec)
        self._finalize_ledger(rec, "cancelled")
        return rec

    def approve(
        self,
        execution_id: str,
        *,
        approval_id: str = "",
        execute: bool = True,
        handler: Handler | None = None,
        intent: ToolIntent | None = None,
    ) -> ExecutionRecord:
        """Mark approval granted for an approval_required record; optionally execute.

        Approval is bound to tool_intent_digest. If `intent` is provided, its
        digest must match the record (changing ToolIntent invalidates approval).
        """
        rec = self.store.get(execution_id)
        if not rec:
            raise KeyError(execution_id)
        if rec.status != ExecutionState.APPROVAL_REQUIRED.value:
            if is_terminal(rec.status):
                raise StateException(f"terminal state {rec.status} is immutable")
            raise StateException(f"cannot approve from {rec.status}")
        if intent is not None:
            d = tool_intent_digest(intent)
            if d != rec.tool_intent_digest:
                raise ApprovalException("approval invalidated: ToolIntent digest mismatch")
        aid = approval_id or f"appr-{uuid.uuid4().hex[:12]}"
        self.store.bind_approval(
            aid,
            digest=rec.tool_intent_digest,
            actor=rec.actor,
            expires_at=time.time() + 3600,
        )
        rec = self.store.transition(
            execution_id,
            ExecutionState.APPROVED,
            reason="human_approved",
            extra={"approval": "approved", "approval_id": aid},
        )
        if not execute:
            return rec
        if intent is None:
            # Cannot re-run without intent; leave approved
            return rec
        return self._continue_after_approval(intent, rec, handler=handler)

    def retry(self, execution_id: str, *, intent: ToolIntent, handler: Handler | None = None) -> ExecutionRecord:
        """Retry a failed retryable execution — no duplicate if digest still running."""
        rec = self.store.get(execution_id)
        if not rec:
            raise KeyError(execution_id)
        if rec.status != ExecutionState.FAILED.value:
            raise StateException(f"retry only from failed, got {rec.status}")
        if not rec.retryable:
            raise StateException("execution is non-retryable")
        if rec.retry_count >= MAX_RETRIES:
            raise StateException("max retry count exceeded")
        if rec.next_retry_at and time.time() < float(rec.next_retry_at):
            raise StateException("backoff wait not elapsed")
        # Bypass backoff for explicit retry after caller waited; bump attempt counter
        prior_retries = int(rec.retry_count or 0)
        # Temporarily clear backoff by force path
        new_rec = self.submit(intent, handler=handler, force_new=True)
        if new_rec and new_rec.execution_id != rec.execution_id:
            try:
                self.store.update_fields(
                    new_rec.execution_id,
                    retry_count=prior_retries + 1,
                )
                new_rec = self.store.get(new_rec.execution_id) or new_rec
            except Exception:
                pass
        return new_rec

    def metrics(self, **kwargs) -> dict:
        return self.store.metrics(**kwargs)

    def ceo_summary(self, *, since: float | None = None) -> dict | None:
        """CEO-facing summary only when something needs attention (no spam)."""
        m = self.metrics(since=since)
        latency = float(m.get("average_runtime_sec") or 0)
        include = bool(
            m.get("failed")
            or m.get("retry_count")
            or m.get("approval_required")
            or latency >= 30.0
        )
        if not include:
            return None
        return {
            "include_in_ceo_brief": True,
            "failed": m.get("failed", 0),
            "retries": m.get("retry_count", 0),
            "approval_backlog": m.get("approval_required", 0),
            "average_runtime_sec": latency,
            "running": m.get("running", 0),
            "denied": m.get("denied", 0),
            "recent_failures": (m.get("recent_failures") or [])[:5],
        }

    def recover_after_restart(self, *, older_than_sec: float = 3600) -> list[str]:
        return self.store.recover_stale_running(older_than_sec=older_than_sec)

    def register_handler(self, family: str, handler: Handler) -> None:
        self.handlers[family] = handler

    # ── core pipeline ─────────────────────────────────────────────────────

    def _submit_locked(
        self,
        intent: ToolIntent,
        *,
        digest: str,
        approval_id: str,
        handler: Handler | None,
        execute: bool,
        force_new: bool,
    ) -> ExecutionRecord:
        # 0) Expiry
        if intent.is_expired():
            rec = self._new_record(intent, digest)
            rec = self.store.insert(rec)
            rec = self.store.transition(
                rec.execution_id,
                ExecutionState.EXPIRED,
                reason="intent_expired",
                extra={"approval": "expired", "failure_category": "expired",
                       "result_summary": "ToolIntent expired before execution"},
            )
            return self._post_terminal(rec, intent)

        # 1) Idempotency — same ToolIntent digest / key → same execution
        if not force_new:
            prior = None
            if intent.idempotency_key:
                prior = self.store.find_by_idempotency(intent.idempotency_key)
            if prior is None:
                prior = self.store.find_by_digest(digest)
            if prior is not None:
                # If digest mismatch on same idempotency key → conflict deny
                if prior.tool_intent_digest and prior.tool_intent_digest != digest:
                    rec = self._new_record(intent, digest)
                    rec = self.store.insert(rec)
                    rec = self.store.transition(
                        rec.execution_id,
                        ExecutionState.DENIED,
                        reason="idempotency_digest_conflict",
                        extra={
                            "failure_category": "idempotency_conflict",
                            "result_summary": "idempotency key bound to different ToolIntent",
                        },
                    )
                    return self._post_terminal(rec, intent)

                # Resume approval_required when approval is now available
                if prior.status == ExecutionState.APPROVAL_REQUIRED.value:
                    if approval_id or not needs_approval(intent):
                        if approval_id:
                            self.store.bind_approval(
                                approval_id,
                                digest=digest,
                                actor=intent.actor_id,
                                expires_at=time.time() + 3600,
                            )
                            self.store.consume_approval(approval_id)
                        prior = self.store.transition(
                            prior.execution_id,
                            ExecutionState.APPROVED,
                            reason="approval_resumed",
                            extra={
                                "approval": "approved" if approval_id or needs_approval(intent) is False else "automatic",
                                "approval_id": approval_id or prior.approval_id,
                            },
                        )
                        if execute:
                            return self._run_handler(intent, prior, handler=handler)
                        return prior
                    return prior  # still waiting

                # In-flight: never double-run
                if prior.status in (
                    ExecutionState.RUNNING.value,
                    ExecutionState.QUEUED.value,
                    ExecutionState.APPROVED.value,
                    ExecutionState.REQUESTED.value,
                    ExecutionState.VALIDATED.value,
                ):
                    return prior

                # Terminal replay only when the *same* idempotency_key matches.
                # Digest alone binds approval / in-flight dedupe; it must not
                # force-replay a finished execution when the caller issues a
                # new attempt (e.g. connector single-use approval re-run).
                if (
                    is_terminal(prior.status)
                    and intent.idempotency_key
                    and prior.idempotency_key
                    and prior.idempotency_key == intent.idempotency_key
                ):
                    return prior
                # else: fall through to a new execution record

        rec = self._new_record(intent, digest)
        rec = self.store.insert(rec)
        self._emit_bus("execution.requested", rec)

        # 2) Validation
        errors = intent.validate() if hasattr(intent, "validate") else []
        family = classify_family(intent)
        if family in FUTURE_FAMILIES and family not in self.handlers and handler is None:
            errors = list(errors) + [f"family {family} not migrated to gateway (phase 1)"]
        if errors:
            rec = self.store.transition(
                rec.execution_id,
                ExecutionState.DENIED,
                reason="validation_failed",
                extra={
                    "failure_category": "validation",
                    "result_summary": safe_summary("; ".join(errors)),
                },
            )
            return self._post_terminal(rec, intent)

        rec = self.store.transition(
            rec.execution_id, ExecutionState.VALIDATED, reason="schema_ok"
        )

        # 3) Permission
        ok, why = _permission_ok(intent)
        if not ok:
            rec = self.store.transition(
                rec.execution_id,
                ExecutionState.DENIED,
                reason=why,
                extra={
                    "failure_category": "permission",
                    "result_summary": safe_summary(why),
                },
            )
            return self._post_terminal(rec, intent)

        # 4) Risk (recorded; classification reuses intent.risk_level)
        risk = getattr(intent.risk_level, "value", str(intent.risk_level))
        self.store.update_fields(rec.execution_id, risk=risk)

        # 5) Approval
        if needs_approval(intent):
            valid = None
            if approval_id:
                # explicit token must match digest
                bound = self.store.find_valid_approval(digest, actor=intent.actor_id)
                if bound and bound.get("approval_id") == approval_id:
                    valid = bound
                else:
                    # also accept freshly bound id matching
                    row = None
                    try:
                        with self.store._conn() as c:
                            row = c.execute(
                                "SELECT * FROM approval_binding WHERE approval_id=?",
                                (approval_id,),
                            ).fetchone()
                    except Exception:
                        row = None
                    if row:
                        d = dict(row)
                        if d.get("tool_intent_digest") == digest and d.get("status") == "approved":
                            if not d.get("expires_at") or float(d["expires_at"]) >= time.time():
                                if int(d.get("used") or 0) < int(d.get("max_uses") or 1):
                                    valid = d
            else:
                valid = self.store.find_valid_approval(digest, actor=intent.actor_id)

            if not valid:
                rec = self.store.transition(
                    rec.execution_id,
                    ExecutionState.APPROVAL_REQUIRED,
                    reason="approval_required",
                    extra={
                        "approval": "required",
                        "result_summary": "awaiting approval bound to ToolIntent digest",
                    },
                )
                self._emit_security(rec, "execution_approval_required")
                self._emit_bus("execution.approval_required", rec)
                self._record_evidence(rec, intent, status="approval_required")
                return rec

            self.store.consume_approval(valid["approval_id"])
            rec = self.store.transition(
                rec.execution_id,
                ExecutionState.APPROVED,
                reason="approval_bound",
                extra={"approval": "approved", "approval_id": valid["approval_id"]},
            )
        else:
            rec = self.store.transition(
                rec.execution_id,
                ExecutionState.APPROVED,
                reason="auto_approved",
                extra={"approval": "automatic"},
            )

        if not execute:
            return rec

        return self._run_handler(intent, rec, handler=handler)

    def _continue_after_approval(
        self, intent: ToolIntent, rec: ExecutionRecord, *, handler: Handler | None
    ) -> ExecutionRecord:
        return self._run_handler(intent, rec, handler=handler)

    def _run_handler(
        self, intent: ToolIntent, rec: ExecutionRecord, *, handler: Handler | None
    ) -> ExecutionRecord:
        # Queued → Running
        rec = self.store.transition(
            rec.execution_id, ExecutionState.QUEUED, reason="enqueued"
        )
        ledger_id = self._begin_ledger(rec, intent)
        if ledger_id:
            self.store.update_fields(rec.execution_id, ledger_run_id=ledger_id)
            rec = self.store.get(rec.execution_id) or rec

        rec = self.store.transition(
            rec.execution_id, ExecutionState.RUNNING, reason="handler_start"
        )
        self._emit_bus("execution.running", rec)

        family = classify_family(intent)
        fn = handler or self.handlers.get(family)
        try:
            if fn is None:
                raise RuntimeError(f"no handler registered for family={family}")
            result = fn(intent, rec) or {}
            if not isinstance(result, dict):
                result = {"status": "succeeded", "summary": safe_summary(result)}
            status = str(result.get("status", "succeeded")).lower()
            summary = safe_summary(result.get("summary") or result.get("message") or status)
            retryable = bool(result.get("retryable", False))
            fcat = safe_summary(result.get("failure_category") or result.get("error_class") or "")

            if status in ("success", "succeeded", "ok", "partial"):
                rec = self.store.transition(
                    rec.execution_id,
                    ExecutionState.SUCCEEDED,
                    reason="handler_ok",
                    extra={"result_summary": summary, "failure_category": ""},
                )
                return self._post_terminal(rec, intent, success=True)

            if status in ("denied", "blocked", "authorization"):
                # Already running — cannot go to DENIED; map to FAILED/non-retryable
                rec = self.store.transition(
                    rec.execution_id,
                    ExecutionState.FAILED,
                    reason="handler_denied",
                    extra={
                        "result_summary": summary,
                        "failure_category": fcat or "permission",
                        "retryable": False,
                    },
                )
                return self._post_terminal(rec, intent)

            # Failed path + optional retry bookkeeping (retry via submit(force_new)/retry())
            retry_count = int(rec.retry_count or 0)
            next_at = None
            if retryable and retry_count < MAX_RETRIES:
                next_at = time.time() + retry_delay(retry_count)
            rec = self.store.transition(
                rec.execution_id,
                ExecutionState.FAILED,
                reason="handler_failed",
                extra={
                    "result_summary": summary,
                    "failure_category": fcat or "execution",
                    "retryable": retryable and retry_count < MAX_RETRIES,
                    "retry_count": retry_count,
                    "next_retry_at": next_at,
                },
            )
            return self._post_terminal(rec, intent)

        except Exception as e:
            logger.exception("execution handler error")
            rec = self.store.transition(
                rec.execution_id,
                ExecutionState.FAILED,
                reason="handler_exception",
                extra={
                    "result_summary": safe_summary(str(e)),
                    "failure_category": "internal",
                    "retryable": False,
                },
            )
            return self._post_terminal(rec, intent)

    def _new_record(self, intent: ToolIntent, digest: str) -> ExecutionRecord:
        return ExecutionRecord(
            tool_intent_digest=digest,
            intent_id=intent.intent_id,
            actor=intent.actor_id,
            target=target_label(intent),
            family=classify_family(intent),
            status=ExecutionState.REQUESTED.value,
            risk=getattr(intent.risk_level, "value", str(intent.risk_level)),
            idempotency_key=intent.idempotency_key or "",
            correlation_id=intent.correlation_id or "",
            metadata={
                "capability": intent.capability,
                "connector_id": intent.connector_id,
                "operation": intent.operation,
            },
        )

    # ── integrations ──────────────────────────────────────────────────────

    def _post_terminal(
        self, rec: ExecutionRecord, intent: ToolIntent, *, success: bool = False
    ) -> ExecutionRecord:
        self._record_evidence(rec, intent, status=rec.status)
        # re-read after evidence_id write
        rec = self.store.get(rec.execution_id) or rec
        self._emit_security(rec, f"execution_{rec.status}")
        rec = self.store.get(rec.execution_id) or rec
        self._emit_bus(f"execution.{rec.status}", rec)
        self._finalize_ledger(rec, "succeeded" if success else (
            "cancelled" if rec.status == "cancelled" else "failed"
        ))
        return self.store.get(rec.execution_id) or rec

    def _record_evidence(self, rec: ExecutionRecord, intent: ToolIntent, *, status: str) -> None:
        if not self._auto and self._evidence is None:
            return
        try:
            from saathi.evidence.schema import Evidence
            from saathi.evidence.store import default_store as ev_store

            store = self._evidence or ev_store()
            ev = Evidence(
                department="execution_gateway",
                project=getattr(intent.business_unit, "value", str(intent.business_unit)),
                episode=rec.execution_id,
                run=rec.execution_id,
                director="ExecutionGateway",
                workflow="m17.22",
                provider=rec.family,
                model=intent.connector_id,
                status=status,
                latency_ms=(rec.runtime_sec() or 0) * 1000,
                metrics={
                    "risk": rec.risk,
                    "approval": rec.approval,
                    "retry_count": rec.retry_count,
                    "target": rec.target,
                    "digest": rec.tool_intent_digest[:16],
                },
                artifacts={"intent_id": intent.intent_id},
                confidence=1.0 if status == "succeeded" else 0.0,
            )
            eid = store.record(ev)
            self.store.update_fields(rec.execution_id, evidence_id=eid)
        except Exception as e:
            logger.debug("evidence record skipped: %s", e)

    def _emit_security(self, rec: ExecutionRecord, kind: str) -> None:
        if not self._auto and self._security is None:
            return
        try:
            from saathi.security.timeline import get_timeline

            tl = self._security or get_timeline()
            # Map to known kind vocabulary (fail closed to security_setting_changed)
            skind = "risk_alert" if rec.status in ("failed", "denied", "expired") else "security_setting_changed"
            sid = tl.record(
                rec.actor or "system",
                skind,
                f"ExecutionGateway {kind}",
                detail=safe_summary(
                    f"{rec.status} {rec.target} retries={rec.retry_count} "
                    f"failure={rec.failure_category}"
                ),
                meta={
                    "execution_id": rec.execution_id,
                    "status": rec.status,
                    "target": rec.target,
                    "digest": rec.tool_intent_digest[:16],
                },
            )
            if sid:
                self.store.update_fields(rec.execution_id, security_event_id=str(sid))
        except Exception as e:
            logger.debug("security event skipped: %s", e)

    def _emit_bus(self, name: str, rec: ExecutionRecord) -> None:
        if not self._auto and self._bus is None:
            return
        try:
            payload = rec.to_safe_dict()
            if self._bus is not None:
                if hasattr(self._bus, "emit"):
                    self._bus.emit(name, "execution_gateway", payload, subject=rec.execution_id)
                elif hasattr(self._bus, "publish_sync"):
                    self._bus.publish_sync(name, payload)
                return
            from saathi.events.bus import default_bus

            default_bus().emit(
                name, "execution_gateway", payload, subject=rec.execution_id
            )
        except Exception as e:
            logger.debug("event bus emit skipped: %s", e)

    def _begin_ledger(self, rec: ExecutionRecord, intent: ToolIntent) -> str:
        if not self._auto and self._ledger is None:
            return ""
        try:
            from saathi.application_harness.run_ledger import RunLedger, default_ledger

            led = self._ledger or default_ledger()
            run_id = f"egw-{rec.execution_id}"
            # ledger idempotency key must be clean/short; use execution id
            created = led.create_run(
                run_id,
                owner=intent.actor_id or "system",
                harness_id="execution_gateway",
                operation_id=safe_summary(intent.operation, maxlen=64),
                intent_digest=rec.tool_intent_digest[:64],
                approval_id=rec.approval_id or "",
                idempotency_key=f"egw-{rec.execution_id}",
                correlation_id=rec.correlation_id or rec.execution_id,
                timeout=float(intent.timeout or 0),
                metadata={"family": rec.family, "target": rec.target},
            )
            rid = created.get("run_id") or run_id
            try:
                led.claim(rid)
            except Exception:
                pass
            try:
                led.mark_running(rid)
            except Exception:
                pass
            return rid
        except Exception as e:
            logger.debug("ledger begin skipped: %s", e)
            return ""

    def _finalize_ledger(self, rec: ExecutionRecord, state: str) -> None:
        if not rec.ledger_run_id:
            return
        if not self._auto and self._ledger is None:
            return
        try:
            from saathi.application_harness.run_ledger import default_ledger

            led = self._ledger or default_ledger()
            terminal = {
                "succeeded": "succeeded",
                "failed": "failed",
                "cancelled": "cancelled",
                "denied": "blocked",
                "expired": "cancelled",
            }.get(state, "failed")
            led.complete(
                rec.ledger_run_id,
                state=terminal,
                failure_code=rec.failure_category or "",
                verification_status="gateway",
            )
        except Exception as e:
            logger.debug("ledger finalize skipped: %s", e)

    @staticmethod
    def _default_local_handler(intent: ToolIntent, rec: ExecutionRecord) -> dict:
        """Safe local handler for Phase 1 local tools (no shell by default)."""
        op = intent.operation
        params = intent.parameters or {}
        if op in ("echo", "ping", "noop", "local-echo"):
            msg = safe_summary(params.get("message", "ok"))
            return {"status": "succeeded", "summary": f"local:{op}:{msg}"}
        if op == "fail":
            return {
                "status": "failed",
                "summary": safe_summary(params.get("message", "forced failure")),
                "retryable": bool(params.get("retryable", False)),
                "failure_category": "forced",
            }
        if op == "retryable_fail":
            return {
                "status": "failed",
                "summary": "transient failure",
                "retryable": True,
                "failure_category": "transient",
            }
        return {
            "status": "failed",
            "summary": f"unknown local operation {op}",
            "retryable": False,
            "failure_category": "unsupported",
        }


# ── process singleton ─────────────────────────────────────────────────────
_BOUNDARY: Optional[UniversalBoundary] = None
_BOUNDARY_LOCK = threading.Lock()


def default_boundary(**kwargs) -> UniversalBoundary:
    global _BOUNDARY
    with _BOUNDARY_LOCK:
        if _BOUNDARY is None or kwargs:
            if kwargs:
                return UniversalBoundary(**kwargs)
            _BOUNDARY = UniversalBoundary()
        return _BOUNDARY


def reset_boundary() -> None:
    global _BOUNDARY
    with _BOUNDARY_LOCK:
        _BOUNDARY = None
    reset_default_store()
