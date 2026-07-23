"""M49.1 ToolExecutionService — canonical path beneath ExecutionGateway."""
from __future__ import annotations

import time
import traceback
from typing import Any, Callable, Optional

from saathi.tool_runtime.context import (
    BoundedToolContext,
    ToolCancelledError,
    ToolTimeoutError,
)
from saathi.tool_runtime.contracts import (
    ToolApprovalReference,
    ToolApprovalRequirement,
    ToolAuthorityClass,
    ToolAvailability,
    ToolErrorCode,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolIdempotencyClass,
    ToolManifest,
    ToolOutcomeClass,
    ToolRetryClass,
    ToolSideEffectClass,
)
from saathi.tool_runtime.idempotency import (
    IdempotencyStore,
    default_idempotency_store,
    fingerprint,
)
from saathi.tool_runtime.registry import ToolRegistry, default_registry
from saathi.tool_runtime.schema import validate_against_schema
from saathi.tool_runtime.secrets import find_secret_violations, redact


def _default_idemp_store():
    """Prefer durable SQLite store; fall back to process-local if import fails."""
    try:
        from saathi.tool_runtime.durable_idempotency import (
            default_durable_idempotency_store,
        )

        return default_durable_idempotency_store()
    except Exception:
        return default_idempotency_store()


class ToolExecutionService:
    """Fail-closed tool execution. Does not replace ExecutionGateway."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        idempotency: IdempotencyStore | None = None,
    ):
        self.registry = registry or default_registry()
        self.idempotency = idempotency if idempotency is not None else _default_idemp_store()

    def execute_tool(
        self,
        request: ToolExecutionRequest,
        *,
        cancel_check: Callable[[], bool] | None = None,
        event_recorder: Callable[[str, dict], None] | None = None,
        scratch: dict | None = None,
    ) -> ToolExecutionResult:
        started = time.time()
        events: list[str] = []
        call_id = request.call_id
        adapter_invoked = False

        def _terminal(
            *,
            status: str,
            outcome: ToolOutcomeClass,
            error: ToolErrorCode | str = "",
            message: str = "",
            data: dict | None = None,
            retryable: bool = False,
            retry_class: str = "",
            side_effect_confirmed: bool = False,
            cancellation_confirmed: bool = False,
            timeout_detected: bool = False,
            evidence: list[str] | None = None,
            manifest: ToolManifest | None = None,
        ) -> ToolExecutionResult:
            finished = time.time()
            code = error.value if isinstance(error, ToolErrorCode) else str(error or "")
            term_event = {
                ToolOutcomeClass.SUCCESS_CONFIRMED: "tool.completed",
                ToolOutcomeClass.FAILURE_CONFIRMED: "tool.failed",
                ToolOutcomeClass.CANCELLED_CONFIRMED: "tool.cancellation_acknowledged",
                ToolOutcomeClass.TIMEOUT_CONFIRMED: "tool.timeout_detected",
                ToolOutcomeClass.BLOCKED: "tool.blocked",
                ToolOutcomeClass.PROHIBITED: "tool.blocked",
                ToolOutcomeClass.SIDE_EFFECT_UNKNOWN: "tool.outcome_unknown",
                ToolOutcomeClass.TOOL_OUTCOME_UNKNOWN: "tool.outcome_unknown",
                ToolOutcomeClass.REQUIRES_REVIEW: "tool.outcome_unknown",
            }.get(outcome, "tool.failed")
            events.append(term_event)
            payload = redact(
                {
                    "status": status,
                    "outcome": outcome.value,
                    "error_code": code,
                    "message": message,
                }
            )
            if event_recorder:
                try:
                    event_recorder(term_event, payload)
                except Exception:
                    pass
            return ToolExecutionResult(
                tool_id=request.tool_id,
                tool_version=(manifest.version if manifest else request.tool_version),
                call_id=call_id,
                status=status,
                outcome_class=outcome,
                data=redact(data or {}),
                safe_message=message[:500],
                error_code=code,
                retryable=retryable,
                side_effect_confirmed=side_effect_confirmed,
                cancellation_confirmed=cancellation_confirmed,
                timeout_detected=timeout_detected,
                evidence_references=evidence or [],
                started_at=started,
                finished_at=finished,
                duration_ms=round((finished - started) * 1000, 2),
                events=list(events),
                retry_class=retry_class,
                authority_class=manifest.authority_class.value if manifest else "",
                side_effect_class=manifest.side_effect_class.value if manifest else "",
                adapter_invoked=adapter_invoked,
            )

        # 1. normalize
        events.append("tool.requested")
        if event_recorder:
            event_recorder("tool.requested", {"tool_id": request.tool_id, "call_id": call_id})

        if not request.tool_id:
            return _terminal(
                status="rejected",
                outcome=ToolOutcomeClass.BLOCKED,
                error=ToolErrorCode.TOOL_NOT_FOUND,
                message="tool_id required",
            )

        # 2–3 resolve + enabled
        resolved = self.registry.resolve(request.tool_id, request.tool_version)
        if not resolved:
            return _terminal(
                status="rejected",
                outcome=ToolOutcomeClass.BLOCKED,
                error=ToolErrorCode.TOOL_NOT_FOUND,
                message=f"unknown tool: {request.tool_id}",
            )
        manifest, adapter = resolved

        if (
            not manifest.enabled
            or manifest.availability == ToolAvailability.DISABLED
        ):
            return _terminal(
                status="rejected",
                outcome=ToolOutcomeClass.BLOCKED,
                error=ToolErrorCode.TOOL_DISABLED,
                message="tool disabled",
                manifest=manifest,
            )

        # 4 capability
        cap = (request.capability or "").strip()
        if cap and cap not in manifest.capabilities:
            return _terminal(
                status="rejected",
                outcome=ToolOutcomeClass.BLOCKED,
                error=ToolErrorCode.TOOL_CAPABILITY_MISMATCH,
                message="capability not declared on manifest",
                manifest=manifest,
            )
        if not cap and manifest.capabilities:
            cap = manifest.capabilities[0]

        # 8 financial prohibition (early)
        if (
            manifest.authority_class == ToolAuthorityClass.FINANCIAL_EXECUTION
            or manifest.side_effect_class == ToolSideEffectClass.FINANCIAL_EXECUTION
            or manifest.approval_requirement == ToolApprovalRequirement.PROHIBITED
            or manifest.availability == ToolAvailability.PROHIBITED
        ):
            return _terminal(
                status="rejected",
                outcome=ToolOutcomeClass.PROHIBITED,
                error=ToolErrorCode.TOOL_FINANCIAL_EXECUTION_PROHIBITED
                if "FINANCIAL" in manifest.authority_class.value
                or "FINANCIAL" in manifest.side_effect_class.value
                else ToolErrorCode.TOOL_SIDE_EFFECT_PROHIBITED,
                message="tool prohibited by manifest policy",
                manifest=manifest,
            )

        # 9 secrets in request
        secret_hits = find_secret_violations(request.arguments or {})
        if secret_hits and manifest.secret_policy.value != "OPTIONAL_SECRET_REFERENCE":
            # Always reject raw secret fields in generic payloads for NO_SECRET
            if secret_hits:
                return _terminal(
                    status="rejected",
                    outcome=ToolOutcomeClass.BLOCKED,
                    error=ToolErrorCode.TOOL_SECRET_POLICY_VIOLATION,
                    message=f"secret-like fields rejected: {','.join(secret_hits[:5])}",
                    manifest=manifest,
                )
        if secret_hits and manifest.secret_policy.value in (
            "NO_SECRET",
            "PROHIBITED",
            "BROKERED_CLIENT_ONLY",
        ):
            return _terminal(
                status="rejected",
                outcome=ToolOutcomeClass.BLOCKED,
                error=ToolErrorCode.TOOL_SECRET_POLICY_VIOLATION,
                message="secret fields not allowed for this tool",
                manifest=manifest,
            )

        # 5 input validation
        in_errs = validate_against_schema(
            request.arguments or {}, manifest.input_schema
        )
        if in_errs:
            events.append("tool.validated")
            return _terminal(
                status="rejected",
                outcome=ToolOutcomeClass.BLOCKED,
                error=ToolErrorCode.TOOL_INPUT_INVALID,
                message="; ".join(in_errs[:5]),
                manifest=manifest,
            )
        events.append("tool.validated")

        # 6 authority from manifest only (caller override ignored)
        authority = manifest.authority_class
        side_effect = manifest.side_effect_class

        # 7 approval
        need = manifest.approval_requirement
        if need in (
            ToolApprovalRequirement.EXPLICIT_APPROVAL_REQUIRED,
            ToolApprovalRequirement.OWNER_AUTHORIZATION_REQUIRED,
            ToolApprovalRequirement.USER_CONFIRMATION_REQUIRED,
        ):
            ref = request.approval_reference
            if not ref:
                return _terminal(
                    status="rejected",
                    outcome=ToolOutcomeClass.BLOCKED,
                    error=ToolErrorCode.TOOL_APPROVAL_REQUIRED,
                    message="approval required",
                    manifest=manifest,
                )
            ok, err = ref.is_valid_for(
                tool_id=manifest.tool_id,
                capability=cap,
                run_id=request.run_id,
                side_effect=side_effect,
            )
            if not ok:
                return _terminal(
                    status="rejected",
                    outcome=ToolOutcomeClass.BLOCKED,
                    error=err or ToolErrorCode.TOOL_APPROVAL_REQUIRED,
                    message="approval invalid",
                    manifest=manifest,
                )

        # 10 cancellation pre-check
        if cancel_check and cancel_check():
            return _terminal(
                status="cancelled",
                outcome=ToolOutcomeClass.CANCELLED_CONFIRMED,
                error=ToolErrorCode.TOOL_CANCELLED,
                message="run cancelled before tool start",
                cancellation_confirmed=True,
                manifest=manifest,
            )

        # 11 deadline
        deadline = float(request.deadline or 0)
        timeout_sec = manifest.timeout_policy.effective(
            request.timeout_sec, deadline if deadline > 0 else None
        )
        if timeout_sec <= 0:
            return _terminal(
                status="rejected",
                outcome=ToolOutcomeClass.TIMEOUT_CONFIRMED
                if deadline and deadline <= time.time()
                else ToolOutcomeClass.BLOCKED,
                error=ToolErrorCode.TOOL_DEADLINE_EXCEEDED
                if deadline and deadline <= time.time()
                else ToolErrorCode.TOOL_TIMEOUT,
                message="deadline exceeded or invalid timeout",
                timeout_detected=bool(deadline and deadline <= time.time()),
                manifest=manifest,
            )
        if deadline <= 0:
            deadline = time.time() + timeout_sec

        # 12 idempotency
        idemp_key = (request.idempotency_key or "").strip()
        idemp_klass = manifest.idempotency_policy.klass
        if (
            idemp_klass == ToolIdempotencyClass.IDEMPOTENCY_KEY_REQUIRED
            and not idemp_key
        ):
            return _terminal(
                status="rejected",
                outcome=ToolOutcomeClass.BLOCKED,
                error=ToolErrorCode.TOOL_IDEMPOTENCY_CONFLICT,
                message="idempotency key required",
                manifest=manifest,
            )
        fp = fingerprint(
            tool_id=manifest.tool_id,
            tool_version=manifest.version,
            arguments=request.normalized_args(),
            authority=authority.value,
            run_id=request.run_id,
            caller=request.requested_by,
        )
        scope = request.run_id or "global"
        if idemp_key:
            begin_kwargs = {}
            # Durable store accepts metadata; process-local ignores via ** not supported — try signature
            try:
                st = self.idempotency.begin(
                    scope,
                    idemp_key,
                    fp,
                    tool_id=manifest.tool_id,
                    tool_version=manifest.version,
                    run_id=request.run_id,
                    call_id=call_id,
                    authority=authority.value,
                    side_effect_class=side_effect.value,
                    attempt=request.attempt,
                )
            except TypeError:
                st = self.idempotency.begin(scope, idemp_key, fp)
            if st["status"] == "conflict":
                return _terminal(
                    status="rejected",
                    outcome=ToolOutcomeClass.BLOCKED,
                    error=ToolErrorCode.TOOL_IDEMPOTENCY_CONFLICT,
                    message="idempotency key conflict",
                    manifest=manifest,
                )
            if st["status"] == "in_progress":
                return _terminal(
                    status="rejected",
                    outcome=ToolOutcomeClass.BLOCKED,
                    error=ToolErrorCode.TOOL_IDEMPOTENCY_CONFLICT,
                    message="idempotency key in progress",
                    manifest=manifest,
                )
            if st["status"] == "replay" and st.get("result"):
                prior = st["result"]
                return _replay_result(prior, events, call_id, started)

        # 13 accepted
        events.append("tool.started")
        if event_recorder:
            event_recorder(
                "tool.started",
                {
                    "tool_id": manifest.tool_id,
                    "authority": authority.value,
                    "side_effect": side_effect.value,
                },
            )

        ctx = BoundedToolContext(
            run_id=request.run_id,
            call_id=call_id,
            attempt=request.attempt,
            mission_id="",
            agent_id=request.requested_by,
            tool_id=manifest.tool_id,
            tool_version=manifest.version,
            capability=cap,
            authority_class=authority.value,
            side_effect_class=side_effect.value,
            approval_present=bool(request.approval_reference),
            deadline=deadline,
            timeout_sec=timeout_sec,
            cancel_check=cancel_check,
            scratch=dict(scratch or {}),
        )
        ctx.emit("tool.started", {"tool_id": manifest.tool_id})

        # 14–15 execute with cancel/timeout awareness
        raw: dict
        try:
            adapter_invoked = True
            # Soft wall: adapters should check cancel/deadline; we also wrap timing
            raw = adapter(dict(request.arguments or {}), ctx)
            if not isinstance(raw, dict):
                raw = {"error": "adapter returned non-object", "valid": False}
        except ToolCancelledError:
            if idemp_key:
                self.idempotency.fail_release(scope, idemp_key)
            return _terminal(
                status="cancelled",
                outcome=ToolOutcomeClass.CANCELLED_CONFIRMED,
                error=ToolErrorCode.TOOL_CANCELLED,
                message="tool cancelled",
                cancellation_confirmed=True,
                manifest=manifest,
            )
        except ToolTimeoutError:
            if idemp_key:
                # timeout on mutation → do not auto-complete as success; leave for review
                if side_effect not in (
                    ToolSideEffectClass.NO_SIDE_EFFECT,
                    ToolSideEffectClass.LOCAL_REVERSIBLE,
                ):
                    pass
                else:
                    self.idempotency.fail_release(scope, idemp_key)
            return _terminal(
                status="timed_out",
                outcome=ToolOutcomeClass.TIMEOUT_CONFIRMED
                if side_effect
                in (
                    ToolSideEffectClass.NO_SIDE_EFFECT,
                    ToolSideEffectClass.LOCAL_REVERSIBLE,
                )
                else ToolOutcomeClass.SIDE_EFFECT_UNKNOWN,
                error=ToolErrorCode.TOOL_TIMEOUT
                if side_effect
                in (
                    ToolSideEffectClass.NO_SIDE_EFFECT,
                    ToolSideEffectClass.LOCAL_REVERSIBLE,
                )
                else ToolErrorCode.TOOL_OUTCOME_UNKNOWN,
                message="tool timed out",
                timeout_detected=True,
                retryable=False,
                retry_class=ToolRetryClass.NOT_RETRYABLE_TIMEOUT_UNKNOWN.value,
                manifest=manifest,
            )
        except Exception as exc:
            if idemp_key:
                self.idempotency.fail_release(scope, idemp_key)
            # Do not leak stack to caller
            _ = traceback.format_exc()
            return _terminal(
                status="failed",
                outcome=ToolOutcomeClass.FAILURE_CONFIRMED,
                error=ToolErrorCode.TOOL_ADAPTER_ERROR,
                message="adapter error",
                data={"error_type": type(exc).__name__},
                retryable=False,
                manifest=manifest,
            )

        # Post-adapter cancel/timeout flags
        if raw.get("cancelled") or (cancel_check and cancel_check() and not raw.get("data")):
            if idemp_key:
                self.idempotency.fail_release(scope, idemp_key)
            return _terminal(
                status="cancelled",
                outcome=ToolOutcomeClass.CANCELLED_CONFIRMED,
                error=ToolErrorCode.TOOL_CANCELLED,
                message="cancelled",
                cancellation_confirmed=True,
                manifest=manifest,
            )
        if raw.get("timeout"):
            return _terminal(
                status="timed_out",
                outcome=ToolOutcomeClass.TIMEOUT_CONFIRMED
                if raw.get("side_effect_confirmed") is False
                or side_effect == ToolSideEffectClass.NO_SIDE_EFFECT
                else ToolOutcomeClass.SIDE_EFFECT_UNKNOWN,
                error=ToolErrorCode.TOOL_TIMEOUT,
                message="timeout",
                timeout_detected=True,
                retryable=False,
                retry_class=ToolRetryClass.NOT_RETRYABLE_TIMEOUT_UNKNOWN.value,
                manifest=manifest,
            )
        if raw.get("outcome_unknown") or raw.get("side_effect_unknown"):
            return _terminal(
                status="failed",
                outcome=ToolOutcomeClass.SIDE_EFFECT_UNKNOWN,
                error=ToolErrorCode.TOOL_OUTCOME_UNKNOWN,
                message="side effect outcome unknown — no automatic retry",
                retryable=False,
                retry_class=ToolRetryClass.NOT_RETRYABLE_UNCERTAIN_MUTATION.value,
                manifest=manifest,
            )
        if raw.get("error") and not raw.get("data"):
            if idemp_key:
                self.idempotency.fail_release(scope, idemp_key)
            return _terminal(
                status="failed",
                outcome=ToolOutcomeClass.FAILURE_CONFIRMED,
                error=ToolErrorCode.TOOL_ADAPTER_ERROR,
                message=str(raw.get("error"))[:300],
                retryable=False,
                manifest=manifest,
            )

        # 17 output validation
        out_data = raw.get("data") if "data" in raw else raw
        if not isinstance(out_data, dict):
            out_data = {"value": out_data}
        out_errs = validate_against_schema(out_data, manifest.output_schema)
        if out_errs:
            if idemp_key:
                self.idempotency.fail_release(scope, idemp_key)
            return _terminal(
                status="failed",
                outcome=ToolOutcomeClass.FAILURE_CONFIRMED,
                error=ToolErrorCode.TOOL_OUTPUT_INVALID,
                message="output validation failed: " + "; ".join(out_errs[:5]),
                data={},  # do not promote invalid output
                retryable=False,
                manifest=manifest,
            )

        # 18–20 redact + evidence + success
        evidence_refs = [e["ref"] for e in ctx.evidence_sink]
        if manifest.evidence_policy.record_output:
            ref = ctx.evidence("tool.output", redact(out_data))
            evidence_refs.append(ref)
            events.append("tool.evidence_recorded")

        side_confirmed = bool(
            raw.get("side_effect_confirmed", side_effect == ToolSideEffectClass.NO_SIDE_EFFECT)
        )
        result = _terminal(
            status="completed",
            outcome=ToolOutcomeClass.SUCCESS_CONFIRMED,
            message="ok",
            data=out_data,
            side_effect_confirmed=side_confirmed,
            evidence=evidence_refs,
            manifest=manifest,
        )
        if idemp_key:
            self.idempotency.complete(scope, idemp_key, result.to_dict())
        return result


def _replay_result(
    prior: dict, events: list[str], call_id: str, started: float
) -> ToolExecutionResult:
    oc = prior.get("outcome_class") or ToolOutcomeClass.SUCCESS_CONFIRMED.value
    if isinstance(oc, ToolOutcomeClass):
        outcome = oc
    else:
        try:
            outcome = ToolOutcomeClass(oc)
        except Exception:
            outcome = ToolOutcomeClass.SUCCESS_CONFIRMED
    finished = time.time()
    events.append("tool.completed")
    return ToolExecutionResult(
        tool_id=str(prior.get("tool_id", "")),
        tool_version=str(prior.get("tool_version", "")),
        call_id=call_id,
        status=str(prior.get("status", "completed")),
        outcome_class=outcome,
        data=dict(prior.get("data") or {}),
        safe_message=str(prior.get("safe_message", "idempotent replay")),
        error_code=str(prior.get("error_code", "")),
        retryable=False,
        side_effect_confirmed=bool(prior.get("side_effect_confirmed")),
        cancellation_confirmed=bool(prior.get("cancellation_confirmed")),
        timeout_detected=bool(prior.get("timeout_detected")),
        evidence_references=list(prior.get("evidence_references") or []),
        started_at=started,
        finished_at=finished,
        duration_ms=round((finished - started) * 1000, 2),
        events=events,
        retry_class="",
        authority_class=str(prior.get("authority_class", "")),
        side_effect_class=str(prior.get("side_effect_class", "")),
        adapter_invoked=False,
    )


def default_tool_service() -> ToolExecutionService:
    return ToolExecutionService()


def classify_retry(
    *,
    outcome: ToolOutcomeClass,
    side_effect: ToolSideEffectClass,
    cancelled: bool,
    timeout: bool,
) -> ToolRetryClass:
    """Deterministic retry classification — never retries uncertain mutations."""
    if cancelled:
        return ToolRetryClass.NOT_RETRYABLE_CANCELLATION
    if outcome == ToolOutcomeClass.PROHIBITED:
        return ToolRetryClass.NOT_RETRYABLE_PROHIBITED
    if outcome in (
        ToolOutcomeClass.SIDE_EFFECT_UNKNOWN,
        ToolOutcomeClass.TOOL_OUTCOME_UNKNOWN,
    ):
        return ToolRetryClass.NOT_RETRYABLE_UNCERTAIN_MUTATION
    if timeout and side_effect not in (
        ToolSideEffectClass.NO_SIDE_EFFECT,
        ToolSideEffectClass.LOCAL_REVERSIBLE,
    ):
        return ToolRetryClass.NOT_RETRYABLE_TIMEOUT_UNKNOWN
    if outcome == ToolOutcomeClass.BLOCKED:
        return ToolRetryClass.NOT_RETRYABLE_VALIDATION
    return ToolRetryClass.NEVER
