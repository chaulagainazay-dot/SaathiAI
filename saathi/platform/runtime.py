"""M52 canonical platform-agent orchestration above the M49 ExecutionGateway.

This module owns platform context, lifecycle, approval coordination, and restart
decisions. It deliberately does not own adapter dispatch, gateway authorization,
tool idempotency, registry policy, or cancellation mechanics inside adapters.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.models import (
    ApprovalStatus,
    PlatformExecutionRecord,
    PlatformExecutionState,
    PlatformPermission,
    PlatformRole,
    new_id,
)

CANONICAL_PLATFORM_AGENT_ID = "platform-agent"


def binding_fingerprint(
    ctx: PlatformExecutionContext,
    agent_id: str,
    binding_id: str = "",
    binding_version: int = 1,
) -> str:
    payload = "|".join(
        (
            ctx.session_id,
            ctx.user_id,
            ctx.org_id,
            ctx.workspace_id,
            ctx.project_id,
            ctx.mission_id,
            agent_id,
            binding_id,
            str(binding_version),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PlatformAgentRuntime:
    """Synchronous, single-host platform-agent lifecycle coordinator."""

    def __init__(self, platform=None, *, gateway_factory=None):
        if platform is None:
            from saathi.platform.service import default_platform

            platform = default_platform()
        self.platform = platform
        self.store = platform.store
        self._gateway_factory = gateway_factory

    def execute_token(
        self,
        *,
        token: str,
        tool_id: str,
        arguments: dict | None = None,
        project_id: str = "",
        mission_id: str = "",
        approval_id: str = "",
        run_id: str = "",
        idempotency_key: str = "",
        capability: str = "",
        agent_id: str = CANONICAL_PLATFORM_AGENT_ID,
        binding_id: str = "",
        binding_version: int | None = None,
        timeout_sec: float | None = None,
    ):
        from saathi.platform.agent_binding import PlatformAgentBinding

        call = PlatformAgentBinding(self.platform).bind(
            token=token,
            tool_id=tool_id,
            arguments=arguments,
            project_id=project_id,
            mission_id=mission_id,
            approval_id=approval_id,
            run_id=run_id,
            agent_id=agent_id,
            binding_id=binding_id,
            binding_version=binding_version,
        )
        return self.execute_bound(
            call,
            idempotency_key=idempotency_key,
            capability=capability,
            timeout_sec=timeout_sec,
        )

    def execute_context(
        self,
        ctx: PlatformExecutionContext,
        *,
        tool_id: str,
        arguments: dict | None = None,
        approval_id: str = "",
        idempotency_key: str = "",
        capability: str = "",
        agent_id: str = CANONICAL_PLATFORM_AGENT_ID,
        binding_id: str = "",
        binding_version: int | None = None,
        timeout_sec: float | None = None,
    ):
        """Compatibility entry; revalidates the persisted session before dispatch."""
        from saathi.platform.agent_binding import BoundAgentCall
        from saathi.platform.bindings import BindingAdministrationService

        binding = BindingAdministrationService(self.platform).resolve_for_execution(
            ctx,
            binding_id=binding_id,
            agent_id=agent_id,
            binding_version=binding_version,
        )
        call = BoundAgentCall(
            ctx=ctx,
            tool_id=tool_id,
            arguments=dict(arguments or {}),
            approval_id=approval_id,
            agent_id=binding.agent_id,
            binding_id=binding.binding_id,
            binding_version=binding.version,
            binding_fingerprint=binding_fingerprint(
                ctx,
                binding.agent_id,
                binding.binding_id,
                binding.version,
            ),
        )
        return self.execute_bound(
            call,
            idempotency_key=idempotency_key,
            capability=capability,
            timeout_sec=timeout_sec,
        )

    def execute_bound(
        self,
        call,
        *,
        idempotency_key: str = "",
        capability: str = "",
        timeout_sec: float | None = None,
        _resume_record: PlatformExecutionRecord | None = None,
    ):
        ctx = call.ctx
        self._audit("runtime.execution_requested", ctx, tool_id=call.tool_id)
        try:
            binding = self._validate_bound_call(call)
        except PlatformContextError as exc:
            self._audit(
                "runtime.context_rejected",
                ctx,
                tool_id=call.tool_id,
                outcome="BLOCKED",
                detail={"error": exc.code},
            )
            raise
        self._audit("runtime.context_accepted", ctx, tool_id=call.tool_id, outcome="ACCEPTED")

        args = dict(call.arguments or {})
        approval_id = call.approval_id or ctx.approval_id
        fingerprint = self._request_fingerprint(
            ctx,
            agent_id=call.agent_id,
            binding_id=call.binding_id,
            binding_version=call.binding_version,
            tool_id=call.tool_id,
            arguments=args,
            capability=capability,
            approval_id=approval_id,
        )
        idemp = (idempotency_key or "").strip()
        if _resume_record is None:
            existing = self.store.find_platform_execution_by_idempotency(
                ctx.org_id, ctx.workspace_id, idemp
            )
            if existing:
                if existing.request_fingerprint != fingerprint:
                    raise PlatformContextError(
                        "IDEMPOTENCY_CONFLICT",
                        "idempotency key was used for another request",
                    )
                if existing.result_json:
                    result = self._result_from_json(existing.result_json)
                    self._attach_runtime_metadata(result, existing)
                    return result
                raise PlatformContextError(
                    "IDEMPOTENCY_IN_PROGRESS",
                    f"execution {existing.execution_id} is {existing.state}",
                )

            now = self.store._now()
            deadline_at = (
                now + float(timeout_sec) if timeout_sec and timeout_sec > 0 else 0.0
            )
            record = PlatformExecutionRecord(
                execution_id=new_id("pex_"),
                state=PlatformExecutionState.CREATED.value,
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                project_id=ctx.project_id,
                mission_id=ctx.mission_id,
                agent_id=call.agent_id,
                binding_id=call.binding_id,
                binding_version=call.binding_version,
                run_id=ctx.run_id,
                tool_id=call.tool_id,
                request_fingerprint=fingerprint,
                arguments_json=json.dumps(
                    args, sort_keys=True, separators=(",", ":"), default=str
                ),
                capability=capability,
                idempotency_key=idemp,
                approval_id=approval_id,
                created_at=now,
                updated_at=now,
                deadline_at=deadline_at,
            )
            self.store.create_platform_execution(record)
            self._transition(record.execution_id, PlatformExecutionState.QUEUED, ctx)
        else:
            record = _resume_record
            idemp = record.idempotency_key
            deadline_at = record.deadline_at

        from saathi.tool_runtime.registry import default_registry

        manifest = default_registry().get_manifest(call.tool_id)
        if not manifest:
            self._fail_before_dispatch(record.execution_id, ctx, "TOOL_NOT_FOUND")
            raise PlatformContextError("TOOL_NOT_FOUND", call.tool_id)
        authority = manifest.authority_class.value
        if not authority or authority == "UNKNOWN":
            self._fail_before_dispatch(record.execution_id, ctx, "AUTHORITY_UNKNOWN")
            raise PlatformContextError("AUTHORITY_UNKNOWN", "tool authority is not declared")
        # Explicitly prohibited manifests still reach the gateway's canonical
        # denial path so compatibility callers receive a structured, audited
        # non-execution result. This grants no authority and invokes no adapter.
        if manifest.approval_requirement.value != "PROHIBITED":
            try:
                from saathi.platform.bindings import BindingAdministrationService

                BindingAdministrationService(self.platform).validate_execution_policy(
                    ctx,
                    binding,
                    tool_id=call.tool_id,
                    capability=capability,
                    authority=authority,
                )
            except PlatformContextError as exc:
                self._fail_before_dispatch(record.execution_id, ctx, exc.code)
                self._audit(
                    "runtime.binding_policy_rejected",
                    ctx,
                    tool_id=call.tool_id,
                    authority=authority,
                    outcome="BLOCKED",
                    detail={
                        "execution_id": record.execution_id,
                        "binding_id": call.binding_id,
                        "error": exc.code,
                    },
                )
                raise

        needs_approval = manifest.approval_requirement.value not in (
            "NO_APPROVAL_REQUIRED",
            "PROHIBITED",
        )
        if needs_approval and not approval_id:
            self._transition(
                record.execution_id,
                PlatformExecutionState.WAITING_APPROVAL,
                ctx,
                approval_id="",
                authority=authority,
            )
            self._audit(
                "runtime.approval_required",
                ctx,
                tool_id=call.tool_id,
                authority=authority,
                outcome="WAITING_APPROVAL",
                detail={"execution_id": record.execution_id},
            )
            raise PlatformContextError(
                "APPROVAL_REQUIRED",
                f"tool {call.tool_id} requires approval_id; execution={record.execution_id}",
            )

        try:
            approval_ref = self._approval_reference(
                ctx,
                manifest=manifest,
                approval_id=approval_id,
                capability=capability,
            )
        except PlatformContextError as exc:
            self._fail_before_dispatch(record.execution_id, ctx, exc.code)
            self._audit(
                "runtime.approval_rejected",
                ctx,
                tool_id=call.tool_id,
                approval_id=approval_id,
                authority=authority,
                outcome="BLOCKED",
                detail={"error": exc.code, "execution_id": record.execution_id},
            )
            raise
        if approval_ref:
            self._audit(
                "runtime.approval_accepted",
                ctx,
                tool_id=call.tool_id,
                approval_id=approval_id,
                authority=authority,
                outcome="ACCEPTED",
                detail={"execution_id": record.execution_id},
            )

        if not idemp:
            from saathi.tool_runtime.contracts import ToolIdempotencyClass

            klass = getattr(
                getattr(manifest, "idempotency_policy", None), "klass", None
            )
            if klass in (
                ToolIdempotencyClass.IDEMPOTENCY_KEY_REQUIRED,
                ToolIdempotencyClass.NON_IDEMPOTENT,
            ):
                idemp = (
                    f"m52:{ctx.org_id}:{ctx.workspace_id}:{ctx.run_id}:"
                    f"{call.tool_id}:{record.execution_id}"
                )

        if PlatformExecutionState(record.state) != PlatformExecutionState.READY:
            record = self._transition(
                record.execution_id,
                PlatformExecutionState.READY,
                ctx,
                approval_id=approval_id,
                authority=authority,
            )
        if self._cancel_requested(record.execution_id):
            self._transition(record.execution_id, PlatformExecutionState.CANCELLED, ctx)
            raise PlatformContextError("CANCELLED", "execution cancelled before dispatch")
        if deadline_at and self.store._now() >= deadline_at:
            self._transition(record.execution_id, PlatformExecutionState.TIMED_OUT, ctx)
            raise PlatformContextError("TIMED_OUT", "execution expired before dispatch")

        # Claim approval before dispatch so concurrent/replayed calls cannot both use it.
        if approval_ref:
            if not self.store.consume_approval_if_approved(approval_id):
                self._fail_before_dispatch(record.execution_id, ctx, "APPROVAL_REPLAY")
                raise PlatformContextError("APPROVAL_REPLAY", "approval no longer available")

        self._transition(
            record.execution_id,
            PlatformExecutionState.RUNNING,
            ctx,
            dispatch_started=True,
        )
        self._audit(
            "runtime.dispatch_started",
            ctx,
            tool_id=call.tool_id,
            approval_id=approval_id,
            authority=authority,
            outcome="RUNNING",
            detail={"execution_id": record.execution_id},
        )
        try:
            gateway = self._gateway()
            result = gateway.execute_registered_tool(
                tool_id=call.tool_id,
                arguments=args,
                run_id=ctx.run_id,
                requested_by=ctx.requested_by(),
                capability=capability,
                idempotency_key=idemp,
                approval_reference=approval_ref,
                timeout_sec=timeout_sec,
                cancel_check=lambda: self._cancel_requested(record.execution_id),
                event_recorder=lambda event, payload: self._gateway_event(
                    event, payload, ctx, record.execution_id
                ),
            )
        except Exception as exc:
            self._transition(
                record.execution_id,
                PlatformExecutionState.FAILED,
                ctx,
                error_code="GATEWAY_EXCEPTION",
            )
            self._audit(
                "runtime.failure",
                ctx,
                tool_id=call.tool_id,
                approval_id=approval_id,
                authority=authority,
                outcome="FAILED",
                detail={
                    "execution_id": record.execution_id,
                    "error": type(exc).__name__,
                },
            )
            raise

        final_state = self._state_for_result(result)
        payload = json.dumps(result.to_dict(), sort_keys=True, default=str)
        final = self._transition(
            record.execution_id,
            final_state,
            ctx,
            adapter_invoked=bool(getattr(result, "adapter_invoked", False)),
            result_json=payload,
            error_code=result.error_code or "",
        )
        accepted = bool(result.ok)
        self._audit(
            "runtime.gateway_accepted" if accepted else "runtime.gateway_denied",
            ctx,
            tool_id=call.tool_id,
            approval_id=approval_id,
            authority=authority,
            outcome=result.outcome_class.value,
            detail={
                "execution_id": record.execution_id,
                "error_code": result.error_code or "",
                "adapter_invoked": bool(getattr(result, "adapter_invoked", False)),
            },
        )
        self._audit(
            "runtime.completion" if final_state == PlatformExecutionState.COMPLETED else
            "runtime.timeout" if final_state == PlatformExecutionState.TIMED_OUT else
            "runtime.failure",
            ctx,
            tool_id=call.tool_id,
            approval_id=approval_id,
            authority=authority,
            outcome=final_state.value,
            evidence=",".join(result.evidence_references or [])[:500],
            detail={"execution_id": record.execution_id},
        )
        # Stable M50 audit event retained for downstream readers.
        self._audit(
            "runtime.execute",
            ctx,
            tool_id=call.tool_id,
            approval_id=approval_id,
            authority=authority,
            outcome=result.outcome_class.value,
            evidence=",".join(result.evidence_references or [])[:500],
            detail={
                "execution_id": record.execution_id,
                "state": final_state.value,
                "error_code": result.error_code or "",
                "adapter_invoked": bool(getattr(result, "adapter_invoked", False)),
            },
        )
        self._attach_runtime_metadata(result, final)
        return result

    def cancel(self, *, token: str, execution_id: str) -> PlatformExecutionRecord:
        rec = self._scoped_record(token, execution_id)
        self._audit(
            "runtime.cancellation_requested",
            self._context_for_record(token, rec),
            tool_id=rec.tool_id,
            outcome=rec.state,
            detail={"execution_id": execution_id},
        )
        rec = self.store.mark_platform_execution_cancel_requested(execution_id)
        state = PlatformExecutionState(rec.state)
        if state in {
            PlatformExecutionState.CREATED,
            PlatformExecutionState.QUEUED,
            PlatformExecutionState.READY,
            PlatformExecutionState.WAITING_APPROVAL,
            PlatformExecutionState.PAUSED,
            PlatformExecutionState.RECOVERING,
        }:
            rec = self.store.transition_platform_execution(
                execution_id, PlatformExecutionState.CANCELLED
            )
        return rec

    def resume(
        self,
        *,
        token: str,
        execution_id: str,
        approval_id: str = "",
        timeout_sec: float | None = None,
    ):
        rec = self._scoped_record(token, execution_id)
        state = PlatformExecutionState(rec.state)
        if rec.is_terminal():
            if rec.result_json:
                result = self._result_from_json(rec.result_json)
                self._attach_runtime_metadata(result, rec)
                return result
            raise PlatformContextError("TERMINAL_IMMUTABLE", rec.state)
        if state == PlatformExecutionState.WAITING_APPROVAL:
            if not approval_id:
                raise PlatformContextError("APPROVAL_REQUIRED", execution_id)
        elif state == PlatformExecutionState.PAUSED:
            if rec.dispatch_started:
                raise PlatformContextError(
                    "RECOVERY_REVIEW_REQUIRED",
                    "recorded dispatch cannot be replayed after restart",
                )
        else:
            raise PlatformContextError("RESUME_NOT_ALLOWED", rec.state)
        # Preserve the original idempotency key; remove the old row's key before
        # re-entering so the same execution is not mistaken for a new duplicate.
        resumed = self.store.transition_platform_execution(
            execution_id,
            PlatformExecutionState.READY,
            expected_states={state},
            approval_id=approval_id or rec.approval_id,
        )
        ctx = self._context_for_record(token, rec)
        from saathi.platform.agent_binding import BoundAgentCall

        call = BoundAgentCall(
            ctx=ctx,
            tool_id=rec.tool_id,
            arguments=json.loads(rec.arguments_json or "{}"),
            approval_id=approval_id or rec.approval_id,
            agent_id=rec.agent_id,
            binding_id=rec.binding_id,
            binding_version=rec.binding_version,
            binding_fingerprint=binding_fingerprint(
                ctx,
                rec.agent_id,
                rec.binding_id,
                rec.binding_version,
            ),
        )
        # A resume is a new orchestration attempt only when no dispatch occurred.
        # M49 still owns tool idempotency for the preserved key.
        return self.execute_bound(
            call,
            idempotency_key=rec.idempotency_key,
            capability=rec.capability,
            timeout_sec=timeout_sec,
            _resume_record=resumed,
        )

    def reconcile(self) -> list[dict[str, str]]:
        """Classify interrupted rows without automatically replaying any tool."""
        decisions: list[dict[str, str]] = []
        now = self.store._now()
        for rec in self.store.list_recoverable_platform_executions():
            state = PlatformExecutionState(rec.state)
            if rec.cancel_requested:
                target = PlatformExecutionState.CANCELLED
                reason = "cancel_requested"
            elif rec.deadline_at and now >= rec.deadline_at:
                target = PlatformExecutionState.TIMED_OUT
                reason = "deadline_expired"
            elif state == PlatformExecutionState.WAITING_APPROVAL:
                decisions.append(
                    {"execution_id": rec.execution_id, "decision": "WAITING_APPROVAL"}
                )
                continue
            else:
                recovering = self.store.transition_platform_execution(
                    rec.execution_id, PlatformExecutionState.RECOVERING
                )
                target = PlatformExecutionState.PAUSED
                reason = (
                    "dispatch_recorded_manual_review"
                    if recovering.dispatch_started
                    else "safe_to_resume_before_dispatch"
                )
            updated = self.store.transition_platform_execution(
                rec.execution_id,
                target,
                error_code=reason,
                recovery_count=rec.recovery_count + 1,
            )
            self.store.append_audit(
                "runtime.recovery_decision",
                user_id=updated.user_id,
                org_id=updated.org_id,
                workspace_id=updated.workspace_id,
                project_id=updated.project_id,
                mission_id=updated.mission_id,
                run_id=updated.run_id,
                tool_id=updated.tool_id,
                outcome=updated.state,
                detail={"execution_id": updated.execution_id, "reason": reason},
            )
            decisions.append(
                {"execution_id": updated.execution_id, "decision": updated.state}
            )
        return decisions

    def _validate_bound_call(self, call):
        ctx = call.ctx
        from saathi.platform.bindings import BindingAdministrationService

        binding = BindingAdministrationService(self.platform).resolve_for_execution(
            ctx,
            binding_id=call.binding_id,
            agent_id=call.agent_id,
            binding_version=call.binding_version,
        )
        expected_fingerprint = binding_fingerprint(
            ctx,
            binding.agent_id,
            binding.binding_id,
            binding.version,
        )
        if call.binding_fingerprint != expected_fingerprint:
            raise PlatformContextError(
                "AGENT_BINDING_MISMATCH", "platform agent binding scope mismatch"
            )
        ctx.require_permission(PlatformPermission.RUNTIME_EXECUTE)
        ctx.validate()
        session = self.store.get_session(ctx.session_id)
        if not session or not session.is_active(self.store._now()):
            raise PlatformContextError("SESSION_INVALID", "session expired or revoked")
        expected = (
            session.user_id,
            session.org_id,
            session.workspace_id,
        )
        actual = (ctx.user_id, ctx.org_id, ctx.workspace_id)
        if expected != actual:
            raise PlatformContextError(
                "CONTEXT_CONTRADICTORY", "context does not match persisted session"
            )
        role = self.store.membership_role(ctx.org_id, ctx.user_id)
        if not role:
            raise PlatformContextError(
                "MEMBERSHIP_REVOKED", "membership missing or suspended"
            )
        if role != ctx.role:
            raise PlatformContextError("ROLE_STALE", "context role is stale")
        user = self.store.get_user(ctx.user_id)
        org = self.store.get_org(ctx.org_id)
        workspace = self.store.get_workspace(ctx.workspace_id)
        if not user or user.status != "active":
            raise PlatformContextError("USER_INACTIVE", "user is not active")
        if not org or org.status != "active":
            raise PlatformContextError("ORG_INACTIVE", "organization is not active")
        if (
            not workspace
            or workspace.status != "active"
            or workspace.org_id != ctx.org_id
        ):
            raise PlatformContextError(
                "WORKSPACE_ISOLATION", "workspace is not active in organization"
            )
        if ctx.project_id:
            project = self.store.get_project(ctx.project_id)
            if (
                not project
                or project.status != "active"
                or project.org_id != ctx.org_id
                or project.workspace_id != ctx.workspace_id
            ):
                raise PlatformContextError(
                    "PROJECT_ISOLATION", "project is not active in workspace"
                )
        if ctx.mission_id:
            if not ctx.project_id:
                raise PlatformContextError(
                    "PROJECT_REQUIRED", "mission execution requires project"
                )
            mission = self.store.get_mission(ctx.mission_id)
            if (
                not mission
                or mission.status != "active"
                or mission.org_id != ctx.org_id
                or mission.workspace_id != ctx.workspace_id
                or mission.project_id != ctx.project_id
            ):
                raise PlatformContextError(
                    "MISSION_ISOLATION", "mission is not active in project/workspace"
                )
        sec = self.store.get_config("security", {}) or {}
        if sec.get("execution_enabled") is False:
            raise PlatformContextError("EXECUTION_DISABLED", "owner disabled execution")
        if sec.get("approvals_enabled") is False and call.approval_id:
            raise PlatformContextError("APPROVALS_DISABLED", "owner disabled approvals")
        return binding

    def _approval_reference(self, ctx, *, manifest, approval_id: str, capability: str):
        if not approval_id:
            return None
        from saathi.tool_runtime.contracts import ToolApprovalReference

        self.store.expire_stale_approvals()
        rec = self.store.get_approval(approval_id)
        if not rec:
            raise PlatformContextError("APPROVAL_NOT_FOUND", approval_id)
        if rec.org_id != ctx.org_id or rec.workspace_id != ctx.workspace_id:
            raise PlatformContextError("APPROVAL_SCOPE", "org/workspace mismatch")
        if rec.user_id and rec.user_id != ctx.user_id and ctx.role not in (
            PlatformRole.OWNER.value,
            PlatformRole.ADMIN.value,
            PlatformRole.SYSTEM.value,
        ):
            raise PlatformContextError(
                "APPROVAL_USER_MISMATCH", "approval not for this user"
            )
        if rec.tool_id != manifest.tool_id:
            raise PlatformContextError(
                "APPROVAL_TOOL_MISMATCH", "approval tool mismatch"
            )
        if rec.project_id and rec.project_id != ctx.project_id:
            raise PlatformContextError(
                "APPROVAL_PROJECT_MISMATCH", "project mismatch"
            )
        if rec.mission_id and rec.mission_id != ctx.mission_id:
            raise PlatformContextError(
                "APPROVAL_MISSION_MISMATCH", "mission mismatch"
            )
        code_for_status = {
            ApprovalStatus.REVOKED.value: "APPROVAL_REVOKED",
            ApprovalStatus.EXPIRED.value: "APPROVAL_EXPIRED",
            ApprovalStatus.REJECTED.value: "APPROVAL_REJECTED",
            ApprovalStatus.CONSUMED.value: "APPROVAL_REPLAY",
        }
        if rec.status in code_for_status:
            raise PlatformContextError(code_for_status[rec.status], rec.status)
        if rec.status != ApprovalStatus.APPROVED.value:
            raise PlatformContextError("APPROVAL_NOT_APPROVED", rec.status)
        if rec.expires_at and rec.expires_at < self.store._now():
            rec.status = ApprovalStatus.EXPIRED.value
            self.store.save_approval(rec)
            raise PlatformContextError("APPROVAL_EXPIRED", approval_id)
        action = rec.action
        if not rec.tool_id.startswith("m49.connector."):
            action = rec.capability or capability or rec.action or ""
        return ToolApprovalReference(
            approval_id=rec.approval_id,
            actor=ctx.requested_by(),
            capability=rec.capability or capability or "",
            tool_id=rec.tool_id,
            tool_version=rec.tool_version or "",
            run_id=rec.run_id or "",
            mission_id=ctx.mission_id or rec.mission_id,
            side_effect_class=rec.side_effect_class
            or manifest.side_effect_class.value,
            connector=rec.connector,
            action=action,
            target_resource=rec.target_resource,
            authority=rec.authority or manifest.authority_class.value,
            expires_at=rec.expires_at,
            revoked=False,
            active=True,
        )

    def _scoped_record(self, token: str, execution_id: str) -> PlatformExecutionRecord:
        rec = self.store.get_platform_execution(execution_id)
        if not rec:
            raise PlatformContextError("EXECUTION_NOT_FOUND", execution_id)
        ctx = self._context_for_record(token, rec)
        if ctx.user_id != rec.user_id and ctx.role not in (
            PlatformRole.OWNER.value,
            PlatformRole.ADMIN.value,
            PlatformRole.SYSTEM.value,
        ):
            raise PlatformContextError("EXECUTION_SCOPE", "execution belongs to another user")
        return rec

    def _context_for_record(
        self, token: str, rec: PlatformExecutionRecord
    ) -> PlatformExecutionContext:
        ctx = self.platform.require_context(
            token,
            project_id=rec.project_id,
            mission_id=rec.mission_id,
            run_id=rec.run_id,
        )
        if ctx.org_id != rec.org_id or ctx.workspace_id != rec.workspace_id:
            raise PlatformContextError("EXECUTION_SCOPE", "execution tenant mismatch")
        return ctx

    def _gateway(self):
        if self._gateway_factory:
            return self._gateway_factory()
        from saathi.execution import ExecutionGateway

        return ExecutionGateway()

    def _cancel_requested(self, execution_id: str) -> bool:
        rec = self.store.get_platform_execution(execution_id)
        if not rec:
            return True
        return rec.cancel_requested

    def _transition(self, execution_id, state, ctx, **updates):
        before = self.store.get_platform_execution(execution_id)
        rec = self.store.transition_platform_execution(execution_id, state, **updates)
        self._audit(
            "runtime.lifecycle_transition",
            ctx,
            tool_id=rec.tool_id,
            approval_id=rec.approval_id,
            authority=rec.authority,
            outcome=rec.state,
            detail={
                "execution_id": rec.execution_id,
                "previous_state": before.state if before else "",
                "new_state": rec.state,
                "reason_code": rec.error_code or "",
            },
        )
        return rec

    def _fail_before_dispatch(self, execution_id, ctx, code):
        rec = self.store.get_platform_execution(execution_id)
        if rec and not rec.is_terminal():
            self._transition(
                execution_id,
                PlatformExecutionState.FAILED,
                ctx,
                error_code=code,
            )

    def _gateway_event(self, event, _payload, ctx, execution_id):
        self._audit(
            "runtime.gateway_event",
            ctx,
            tool_id=(
                self.store.get_platform_execution(execution_id).tool_id
                if self.store.get_platform_execution(execution_id)
                else ""
            ),
            detail={
                "execution_id": execution_id,
                "gateway_event": str(event)[:100],
                "payload_recorded": False,
            },
        )

    def _audit(self, event, ctx=None, **extra):
        self.platform._audit(event, ctx, **extra)

    @staticmethod
    def _request_fingerprint(
        ctx,
        *,
        agent_id,
        binding_id,
        binding_version,
        tool_id,
        arguments,
        capability,
        approval_id,
    ):
        payload = {
            "user_id": ctx.user_id,
            "org_id": ctx.org_id,
            "workspace_id": ctx.workspace_id,
            "project_id": ctx.project_id,
            "mission_id": ctx.mission_id,
            "agent_id": agent_id,
            "binding_id": binding_id,
            "binding_version": binding_version,
            "tool_id": tool_id,
            "arguments": arguments,
            "capability": capability,
            "approval_id": approval_id,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _state_for_result(result):
        if result.ok:
            return PlatformExecutionState.COMPLETED
        if result.cancellation_confirmed or result.status == "cancelled":
            return PlatformExecutionState.CANCELLED
        if result.timeout_detected or result.status == "timed_out":
            return PlatformExecutionState.TIMED_OUT
        return PlatformExecutionState.FAILED

    @staticmethod
    def _result_from_json(raw: str):
        from saathi.tool_runtime.contracts import ToolExecutionResult, ToolOutcomeClass

        payload = json.loads(raw)
        payload["outcome_class"] = ToolOutcomeClass(payload["outcome_class"])
        return ToolExecutionResult(**payload)

    @staticmethod
    def _attach_runtime_metadata(result, rec):
        result.platform_execution_id = rec.execution_id
        result.platform_execution_state = rec.state
        result.platform_run_id = rec.run_id
