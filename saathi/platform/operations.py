"""M53 tenant-scoped operational views and safe runtime reconciliation."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import re
from typing import Any

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.models import (
    ApprovalStatus,
    PlatformAgentBindingState,
    PlatformExecutionRecord,
    PlatformExecutionState,
    PlatformPermission,
    RuntimeReconciliationRecord,
    new_id,
)


ATTENTION_STATES = {
    PlatformExecutionState.WAITING_APPROVAL.value,
    PlatformExecutionState.PAUSED.value,
    PlatformExecutionState.RECOVERING.value,
}


class RuntimeOperationsService:
    """Read and reconcile persisted runtime state without bypassing the runtime."""

    def __init__(self, platform=None):
        if platform is None:
            from saathi.platform.service import default_platform

            platform = default_platform()
        self.platform = platform
        self.store = platform.store

    def context(self, token: str) -> PlatformExecutionContext:
        ctx = self.platform.require_context(token)
        ctx.require_permission(PlatformPermission.RUNTIME_READ)
        return ctx

    def list_executions(
        self, ctx: PlatformExecutionContext, **filters: Any
    ) -> list[dict[str, Any]]:
        ctx.require_permission(PlatformPermission.RUNTIME_READ)
        project_id = str(filters.get("project_id", "") or "")
        mission_id = str(filters.get("mission_id", "") or "")
        self._validate_filter_scope(ctx, project_id, mission_id)
        records = self.store.list_platform_executions(
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            mission_id=mission_id,
            binding_id=str(filters.get("binding_id", "") or ""),
            user_id=str(filters.get("user_id", "") or ""),
            tool_id=str(filters.get("tool_id", "") or ""),
            state=str(filters.get("state", "") or ""),
            created_after=float(filters.get("created_after", 0) or 0),
            created_before=float(filters.get("created_before", 0) or 0),
            limit=int(filters.get("limit", 100) or 100),
        )
        return [self._safe_execution(record) for record in records]

    def inspect(
        self, ctx: PlatformExecutionContext, execution_id: str
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_READ)
        record = self._scoped(ctx, execution_id)
        result = self._safe_execution(record)
        result["approval"] = self._safe_approval(record)
        result["reconciliations"] = [
            item.to_public()
            for item in self.store.list_runtime_reconciliations(execution_id)
        ]
        return result

    def timeline(
        self, ctx: PlatformExecutionContext, execution_id: str
    ) -> list[dict[str, Any]]:
        ctx.require_permission(PlatformPermission.RUNTIME_READ)
        record = self._scoped(ctx, execution_id)
        entries: list[dict[str, Any]] = []
        for event in self.store.list_execution_audit(
            execution_id,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
        ):
            detail = event.get("detail") or {}
            entries.append(
                {
                    "timestamp": event.get("ts", 0),
                    "previous_state": detail.get("previous_state", ""),
                    "new_state": detail.get("new_state", event.get("outcome", "")),
                    "event_type": event.get("event", ""),
                    "actor_class": "user" if event.get("user_id") else "system",
                    "actor_identifier": event.get("user_id") or "platform-runtime",
                    "reason_code": detail.get("reason_code", detail.get("error", "")),
                    "approval_reference": event.get("approval_id", ""),
                    "execution_reference": execution_id,
                    "correlation_identifier": record.run_id,
                    "recovery_classification": (
                        detail.get("reason", "")
                        if event.get("event") == "runtime.recovery_decision"
                        else ""
                    ),
                    "operator_note_reference": "",
                }
            )
        for reconciliation in self.store.list_runtime_reconciliations(execution_id):
            entries.append(
                {
                    "timestamp": reconciliation.created_at,
                    "previous_state": "",
                    "new_state": reconciliation.outcome,
                    "event_type": "runtime.operator_reconciliation",
                    "actor_class": "operator",
                    "actor_identifier": reconciliation.actor_id,
                    "reason_code": reconciliation.action,
                    "approval_reference": "",
                    "execution_reference": execution_id,
                    "correlation_identifier": record.run_id,
                    "recovery_classification": reconciliation.outcome,
                    "operator_note_reference": reconciliation.reconciliation_id,
                }
            )
        return sorted(entries, key=lambda item: (item["timestamp"], item["event_type"]))

    def attention(
        self, ctx: PlatformExecutionContext, *, limit: int = 200
    ) -> list[dict[str, Any]]:
        ctx.require_permission(PlatformPermission.RUNTIME_READ)
        records = self.store.list_platform_executions(
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            limit=limit,
        )
        items = []
        for record in records:
            reasons = self._attention_reasons(record)
            if reasons:
                item = self._safe_execution(record)
                item["attention_reasons"] = reasons
                items.append(item)
        return items

    def metrics(self, ctx: PlatformExecutionContext) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_READ)
        records = self.store.list_platform_executions(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, limit=500
        )
        states = Counter(record.state for record in records)
        tools = Counter(record.tool_id for record in records)
        bindings = Counter(record.binding_id or "legacy-unbound" for record in records)
        failure = Counter(record.error_code for record in records if record.error_code)
        durations: dict[str, list[float]] = defaultdict(list)
        for record in records:
            duration = max(0.0, record.updated_at - record.created_at)
            durations["observed_runtime"].append(duration)
        return {
            "scope": {"org_id": ctx.org_id, "workspace_id": ctx.workspace_id},
            "total_executions": len(records),
            "active_executions": sum(
                count
                for state, count in states.items()
                if state
                not in {
                    PlatformExecutionState.COMPLETED.value,
                    PlatformExecutionState.FAILED.value,
                    PlatformExecutionState.CANCELLED.value,
                    PlatformExecutionState.TIMED_OUT.value,
                }
            ),
            "waiting_approvals": states[PlatformExecutionState.WAITING_APPROVAL.value],
            "paused_executions": states[PlatformExecutionState.PAUSED.value],
            "recovering_executions": states[PlatformExecutionState.RECOVERING.value],
            "completed_executions": states[PlatformExecutionState.COMPLETED.value],
            "failed_executions": states[PlatformExecutionState.FAILED.value],
            "cancelled_executions": states[PlatformExecutionState.CANCELLED.value],
            "timed_out_executions": states[PlatformExecutionState.TIMED_OUT.value],
            "executions_requiring_attention": sum(
                bool(self._attention_reasons(record)) for record in records
            ),
            "failure_classifications": dict(sorted(failure.items())),
            "executions_per_tool": dict(sorted(tools.items())),
            "executions_per_binding": dict(sorted(bindings.items())),
            "observed_duration_seconds": {
                "average": (
                    sum(durations["observed_runtime"])
                    / len(durations["observed_runtime"])
                    if durations["observed_runtime"]
                    else 0.0
                ),
                "basis": "persisted single-host timestamps; not distributed telemetry",
            },
        }

    def cancel(
        self, ctx: PlatformExecutionContext, *, token: str, execution_id: str
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
        record = self._scoped(ctx, execution_id)
        if record.is_terminal():
            raise PlatformContextError(
                "TERMINAL_IMMUTABLE", "terminal execution cannot be cancelled"
            )
        from saathi.platform.runtime import PlatformAgentRuntime

        return self._safe_execution(
            PlatformAgentRuntime(self.platform).cancel(
                token=token, execution_id=execution_id
            )
        )

    def reconcile(
        self,
        ctx: PlatformExecutionContext,
        *,
        token: str,
        execution_id: str,
        action: str,
        idempotency_key: str,
        note: str = "",
        evidence_reference: str = "",
        approval_id: str = "",
    ) -> dict[str, Any]:
        ctx.require_permission(PlatformPermission.RUNTIME_OPERATE)
        record = self._scoped(ctx, execution_id)
        action = (action or "").strip().upper()
        key = (idempotency_key or "").strip()
        if not key:
            raise PlatformContextError(
                "RECONCILIATION_IDEMPOTENCY_REQUIRED",
                "idempotency_key is required",
            )
        note = self._safe_text(note, 500)
        evidence_reference = self._safe_text(evidence_reference, 300)
        if record.is_terminal() and action not in {"MARK_REVIEWED", "ATTACH_NOTE"}:
            raise PlatformContextError(
                "TERMINAL_IMMUTABLE", "terminal execution state is immutable"
            )
        reconciliation = RuntimeReconciliationRecord(
            reconciliation_id=new_id("rec_"),
            execution_id=execution_id,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            action=action,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            note=note,
            evidence_reference=evidence_reference,
            outcome="REQUESTED",
            idempotency_key=key,
            created_at=self.store._now(),
        )
        try:
            self.store.create_runtime_reconciliation(reconciliation)
        except ValueError as exc:
            raise PlatformContextError(
                "RECONCILIATION_DUPLICATE",
                "reconciliation request was already recorded",
            ) from exc
        self.platform._audit(
            "runtime.reconciliation_requested",
            ctx,
            tool_id=record.tool_id,
            outcome=record.state,
            detail={"execution_id": execution_id, "action": action},
        )
        outcome = record.state
        result: Any = None
        try:
            if action in {"MARK_REVIEWED", "LEAVE_PAUSED", "ATTACH_NOTE"}:
                if action == "LEAVE_PAUSED" and record.state != PlatformExecutionState.PAUSED.value:
                    raise PlatformContextError(
                        "RECONCILIATION_NOT_ALLOWED", "execution is not paused"
                    )
            elif action in {"CANCEL_BEFORE_DISPATCH", "RESOLVE_CANCELLED"}:
                if record.dispatch_started:
                    raise PlatformContextError(
                        "DISPATCH_OUTCOME_UNCERTAIN",
                        "recorded dispatch cannot be resolved as cancelled",
                    )
                result = self.cancel(ctx, token=token, execution_id=execution_id)
                outcome = PlatformExecutionState.CANCELLED.value
            elif action == "CONFIRM_TIMEOUT":
                if not record.deadline_at or self.store._now() < record.deadline_at:
                    raise PlatformContextError(
                        "TIMEOUT_NOT_ELIGIBLE", "execution deadline has not expired"
                    )
                updated = self.store.transition_platform_execution(
                    execution_id, PlatformExecutionState.TIMED_OUT
                )
                result = self._safe_execution(updated)
                outcome = updated.state
            elif action in {"REJECT_RESUME", "RESOLVE_FAILED"}:
                if record.state not in {
                    PlatformExecutionState.PAUSED.value,
                    PlatformExecutionState.RECOVERING.value,
                    PlatformExecutionState.WAITING_APPROVAL.value,
                }:
                    raise PlatformContextError(
                        "RECONCILIATION_NOT_ALLOWED", "execution cannot resolve failed"
                    )
                updated = self.store.transition_platform_execution(
                    execution_id,
                    PlatformExecutionState.FAILED,
                    error_code="OPERATOR_RESOLVED_FAILED",
                )
                result = self._safe_execution(updated)
                outcome = updated.state
            elif action == "REVALIDATE_CONTEXT":
                self._revalidate_context(record, ctx)
                outcome = "CONTEXT_VALID"
            elif action == "REQUEST_NEW_APPROVAL":
                if record.state != PlatformExecutionState.WAITING_APPROVAL.value:
                    raise PlatformContextError(
                        "RECONCILIATION_NOT_ALLOWED", "execution is not awaiting approval"
                    )
                self.store.update_platform_execution_metadata(
                    execution_id, approval_id=""
                )
                outcome = "NEW_APPROVAL_REQUIRED"
            elif action == "RESUME":
                if record.dispatch_started:
                    raise PlatformContextError(
                        "DISPATCH_OUTCOME_UNCERTAIN",
                        "recorded dispatch cannot be replayed",
                    )
                from saathi.platform.runtime import PlatformAgentRuntime

                runtime_result = PlatformAgentRuntime(self.platform).resume(
                    token=token,
                    execution_id=execution_id,
                    approval_id=approval_id,
                )
                result = {
                    "ok": runtime_result.ok,
                    "execution_id": getattr(runtime_result, "platform_execution_id", ""),
                    "execution_state": getattr(
                        runtime_result, "platform_execution_state", ""
                    ),
                    "error_code": runtime_result.error_code or "",
                }
                outcome = result["execution_state"]
            else:
                raise PlatformContextError(
                    "RECONCILIATION_ACTION_UNSUPPORTED",
                    "unsupported reconciliation action",
                )
        except ValueError as exc:
            self.store.update_runtime_reconciliation_outcome(
                reconciliation.reconciliation_id, "REJECTED"
            )
            self.platform._audit(
                "runtime.reconciliation_rejected",
                ctx,
                tool_id=record.tool_id,
                outcome="BLOCKED",
                detail={"execution_id": execution_id, "action": action},
            )
            raise PlatformContextError(
                "RECONCILIATION_STATE_CONFLICT",
                "execution state changed during reconciliation",
            ) from exc
        except PlatformContextError:
            self.store.update_runtime_reconciliation_outcome(
                reconciliation.reconciliation_id, "REJECTED"
            )
            self.platform._audit(
                "runtime.reconciliation_rejected",
                ctx,
                tool_id=record.tool_id,
                outcome="BLOCKED",
                detail={"execution_id": execution_id, "action": action},
            )
            raise
        reconciliation = self.store.update_runtime_reconciliation_outcome(
            reconciliation.reconciliation_id, outcome
        )
        self.platform._audit(
            "runtime.reconciliation_accepted",
            ctx,
            tool_id=record.tool_id,
            outcome=outcome,
            detail={
                "execution_id": execution_id,
                "action": action,
                "reconciliation_id": reconciliation.reconciliation_id,
            },
        )
        return {
            "reconciliation": reconciliation.to_public(),
            "execution": result or self._safe_execution(self._scoped(ctx, execution_id)),
        }

    def _scoped(
        self, ctx: PlatformExecutionContext, execution_id: str
    ) -> PlatformExecutionRecord:
        record = self.store.get_platform_execution(execution_id)
        if (
            not record
            or record.org_id != ctx.org_id
            or record.workspace_id != ctx.workspace_id
        ):
            self.platform._audit(
                "runtime.administration_rejected",
                ctx,
                outcome="BLOCKED",
                detail={"reason": "EXECUTION_NOT_FOUND"},
            )
            raise PlatformContextError(
                "EXECUTION_NOT_FOUND", "execution not found in workspace"
            )
        return record

    def _safe_execution(self, record: PlatformExecutionRecord) -> dict[str, Any]:
        public = record.to_public()
        public["attention_reasons"] = self._attention_reasons(record)
        public["idempotency"] = {
            "present": bool(record.idempotency_key),
            "reference": (
                "idem:"
                + hashlib.sha256(
                    record.idempotency_key.encode("utf-8")
                ).hexdigest()[:12]
                if record.idempotency_key
                else ""
            ),
        }
        public.pop("approval_id", None)
        return public

    def _safe_approval(self, record: PlatformExecutionRecord) -> dict[str, Any]:
        approval = self.store.get_approval(record.approval_id) if record.approval_id else None
        if not approval:
            return {"required": record.state == PlatformExecutionState.WAITING_APPROVAL.value}
        return {
            "required": True,
            "approval_reference": approval.approval_id,
            "status": approval.status,
            "expires_at": approval.expires_at,
        }

    def _attention_reasons(self, record: PlatformExecutionRecord) -> list[str]:
        reasons: list[str] = []
        if record.state == PlatformExecutionState.WAITING_APPROVAL.value:
            reasons.append("APPROVAL_REQUIRED")
            approval = self.store.get_approval(record.approval_id) if record.approval_id else None
            if approval and approval.status == ApprovalStatus.EXPIRED.value:
                reasons.append("APPROVAL_EXPIRED")
            if approval and approval.status == ApprovalStatus.REJECTED.value:
                reasons.append("APPROVAL_REJECTED")
        if record.state == PlatformExecutionState.PAUSED.value:
            reasons.append(
                "DISPATCH_OUTCOME_UNCERTAIN"
                if record.dispatch_started
                else "PAUSED_AFTER_RESTART"
            )
        if record.state == PlatformExecutionState.RECOVERING.value:
            reasons.append("MANUAL_REVIEW_REQUIRED")
        if record.cancel_requested and not record.is_terminal():
            reasons.append("CANCELLATION_PENDING")
        if record.deadline_at and self.store._now() >= record.deadline_at and not record.is_terminal():
            reasons.append("TIMEOUT_PENDING")
        binding = self.store.get_agent_binding(record.binding_id) if record.binding_id else None
        if binding:
            if binding.state == PlatformAgentBindingState.SUSPENDED.value:
                reasons.append("BINDING_SUSPENDED")
            elif binding.state == PlatformAgentBindingState.REVOKED.value:
                reasons.append("BINDING_REVOKED")
            if binding.version != record.binding_version and not record.is_terminal():
                reasons.append("CONTEXT_INVALIDATED")
        elif record.binding_id:
            reasons.append("CONTEXT_INVALIDATED")
        if record.error_code == "IDEMPOTENCY_CONFLICT":
            reasons.append("IDEMPOTENCY_CONFLICT")
        return list(dict.fromkeys(reasons))

    def _revalidate_context(
        self, record: PlatformExecutionRecord, ctx: PlatformExecutionContext
    ) -> None:
        if record.session_id != ctx.session_id and record.user_id != ctx.user_id:
            raise PlatformContextError("CONTEXT_INVALIDATED", "execution identity changed")
        binding = self.store.get_agent_binding(record.binding_id)
        if (
            not binding
            or binding.state != PlatformAgentBindingState.ACTIVE.value
            or binding.version != record.binding_version
        ):
            raise PlatformContextError(
                "CONTEXT_INVALIDATED", "binding is stale or unavailable"
            )

    def _validate_filter_scope(
        self, ctx: PlatformExecutionContext, project_id: str, mission_id: str
    ) -> None:
        if project_id:
            project = self.store.get_project(project_id)
            if (
                not project
                or project.org_id != ctx.org_id
                or project.workspace_id != ctx.workspace_id
            ):
                raise PlatformContextError("EXECUTION_NOT_FOUND", "scope unavailable")
        if mission_id:
            mission = self.store.get_mission(mission_id)
            if (
                not mission
                or mission.org_id != ctx.org_id
                or mission.workspace_id != ctx.workspace_id
                or (project_id and mission.project_id != project_id)
            ):
                raise PlatformContextError("EXECUTION_NOT_FOUND", "scope unavailable")

    @staticmethod
    def _safe_text(value: str, limit: int) -> str:
        text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
        patterns = (
            r"(?i)\bBearer\s+\S+",
            r"\b(?:sk|gh[pousr])_[A-Za-z0-9_-]{12,}\b",
            r"(?i)\b(?:password|token|secret|api[_-]?key)\s*[:=]\s*\S+",
            r"-----BEGIN [^-]*PRIVATE KEY-----",
        )
        for pattern in patterns:
            text = re.sub(pattern, "[REDACTED]", text)
        return text[:limit]
