"""M62.7 — registered safety tools (the canonical mutation path for breakers).

Manual trips, acknowledgements, reset requests, resets and system sweeps flow
PlatformAgentRuntime → ExecutionGateway → ToolExecutionService → these adapters →
SafetyService. No API route or agent mutates breaker state except through here.

Authority is ``LOCAL_MUTATION`` with a ``LOCAL_*`` side effect — never
``FINANCIAL_EXECUTION``. A reset transitions protective state only; it never touches
fills, positions, cash, ledger, and never repairs corrupted state.
"""
from __future__ import annotations

import threading
from typing import Any

from saathi.platform.context import PlatformExecutionContext, PlatformContextError
from saathi.tool_runtime.context import BoundedToolContext
from saathi.tool_runtime.contracts import (
    IdempotencyPolicy, RetryPolicy, TimeoutPolicy, ToolApprovalRequirement, ToolAuthorityClass,
    ToolCancellationSupport, ToolIdempotencyClass, ToolManifest, ToolRetryClass, ToolSecretPolicy,
    ToolSideEffectClass,
)

_SVC = None
_SVC_LOCK = threading.RLock()


def default_safety_service():
    """Process-wide SafetyService sharing the platform DB (approvals + audit)."""
    global _SVC
    with _SVC_LOCK:
        if _SVC is None:
            from saathi.platform.safety.service import SafetyService
            from saathi.platform.paper_trading.store import PaperStore
            try:
                from saathi.platform.service import default_platform
                pstore = default_platform().store
            except Exception:
                pstore = None
            _SVC = SafetyService(PaperStore(), platform_store=pstore)
            if pstore is not None:
                _SVC.bind_audit(pstore)
        return _SVC


def set_safety_service_for_tests(svc) -> None:
    global _SVC
    with _SVC_LOCK:
        _SVC = svc


def _ctx(args: dict) -> PlatformExecutionContext:
    return PlatformExecutionContext(
        user_id=str(args.get("user_id", "")), role=str(args.get("role", "")),
        org_id=str(args.get("org_id", "")), workspace_id=str(args.get("workspace_id", "")),
        project_id=str(args.get("project_id", "")), approval_id=str(args.get("approval_id", "")),
        authority=str(args.get("authority", "")))


# ── adapters ──────────────────────────────────────────────────────────────────
def trip_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    svc = default_safety_service()
    try:
        res = svc.manual_trip(_ctx(args), scope=str(args["scope"]), scope_ref=str(args.get("scope_ref", "")),
                              reason=str(args.get("reason", "manual kill switch")))
    except PlatformContextError as e:
        return {"error": f"{e.code}: {e.message}"}
    ctx.evidence("paper_safety.trip", {"scope": args.get("scope")})
    trip = res.get("trip") or {}
    return {"data": {"tripped": bool(res.get("tripped", bool(trip))), "trip_id": trip.get("trip_id", "")},
            "side_effect_confirmed": True}


def acknowledge_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    svc = default_safety_service()
    try:
        res = svc.acknowledge(_ctx(args), str(args["trip_id"]), note=str(args.get("note", "")),
                              evidence_reviewed=bool(args.get("evidence_reviewed", False)))
    except PlatformContextError as e:
        return {"error": f"{e.code}: {e.message}"}
    ctx.evidence("paper_safety.acknowledge", {"trip_id": args.get("trip_id")})
    return {"data": {"acknowledged": True, "halt_retained": True, "state": res.get("state", "")},
            "side_effect_confirmed": True}


def request_reset_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    svc = default_safety_service()
    try:
        res = svc.request_reset(_ctx(args), str(args["trip_id"]), reason=str(args.get("reason", "")),
                                idempotency_key=str(args.get("idempotency_key", "")),
                                approval_id=str(args.get("approval_id", "")))
    except PlatformContextError as e:
        return {"error": f"{e.code}: {e.message}"}
    ctx.evidence("paper_safety.request_reset", {"trip_id": args.get("trip_id")})
    return {"data": {"request_id": res.get("request_id", ""), "status": res.get("status", "")},
            "side_effect_confirmed": True}


def reset_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    svc = default_safety_service()
    try:
        res = svc.execute_reset(_ctx(args), str(args["request_id"]), _via_gateway=True)
    except PlatformContextError as e:
        return {"error": f"{e.code}: {e.message}"}
    ctx.evidence("paper_safety.reset", {"request_id": args.get("request_id"), "allowed": res.get("allowed")})
    return {"data": {"allowed": bool(res.get("allowed")),
                     "account_unhalted": bool(res.get("account_unhalted", False)),
                     "financial_state_modified": False}, "side_effect_confirmed": True}


def run_sweep_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    svc = default_safety_service()
    try:
        acc = args.get("account_ids")
        manifest = svc.run_sweep(_ctx(args), account_ids=(list(acc) if acc else None))
    except PlatformContextError as e:
        return {"error": f"{e.code}: {e.message}"}
    ctx.evidence("paper_safety.run_sweep", {"sweep_id": manifest.get("sweep_id")})
    return {"data": {"sweep_id": manifest.get("sweep_id"), "trips_created": manifest.get("trips_created", 0)},
            "side_effect_confirmed": True}


# ── manifests ─────────────────────────────────────────────────────────────────
_ID = {"user_id": {"type": "string", "maxLength": 128}, "role": {"type": "string", "maxLength": 32},
       "org_id": {"type": "string", "maxLength": 128}, "workspace_id": {"type": "string", "maxLength": 128},
       "project_id": {"type": "string", "maxLength": 128}, "authority": {"type": "string", "maxLength": 64}}


def _m(tool_id, name, desc, props, required, *, side_effect, approval, idem_required=False,
       idem_class=ToolIdempotencyClass.NATURALLY_IDEMPOTENT):
    return ToolManifest(
        tool_id=tool_id, version="1.0.0", display_name=name, description=desc, domain="paper_safety",
        capabilities=(tool_id.replace(".", "_"),), authority_class=ToolAuthorityClass.LOCAL_MUTATION,
        side_effect_class=side_effect, approval_requirement=approval, secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={"type": "object", "properties": {**_ID, **props},
                      "required": ["org_id", "workspace_id", "user_id", "role"] + required,
                      "additionalProperties": False},
        output_schema={"type": "object", "properties": {}, "required": []},
        timeout_policy=TimeoutPolicy(default_sec=15, max_sec=45),
        retry_policy=RetryPolicy(max_attempts=1, retry_class=ToolRetryClass.NEVER),
        idempotency_policy=IdempotencyPolicy(klass=idem_class, require_key=idem_required),
        cancellation_support=ToolCancellationSupport.NOT_CANCELLABLE)


def paper_safety_manifests() -> list[tuple[ToolManifest, Any]]:
    trip = _m("paper_safety.trip", "Paper safety manual trip",
              "Manually trip a paper circuit breaker (halt a bounded scope). PAPER only.",
              {"scope": {"type": "string", "maxLength": 32}, "scope_ref": {"type": "string", "maxLength": 128},
               "reason": {"type": "string", "maxLength": 200}}, ["scope"],
              side_effect=ToolSideEffectClass.LOCAL_REVERSIBLE,
              approval=ToolApprovalRequirement.NO_APPROVAL_REQUIRED)
    ack = _m("paper_safety.acknowledge", "Paper safety acknowledge",
             "Acknowledge a breaker trip (awareness only; the halt is retained).",
             {"trip_id": {"type": "string", "maxLength": 128}, "note": {"type": "string", "maxLength": 500},
              "evidence_reviewed": {"type": "boolean"}}, ["trip_id"],
             side_effect=ToolSideEffectClass.LOCAL_REVERSIBLE,
             approval=ToolApprovalRequirement.NO_APPROVAL_REQUIRED)
    reqreset = _m("paper_safety.request_reset", "Paper safety reset request",
                  "Request a breaker reset (does NOT remove the halt).",
                  {"trip_id": {"type": "string", "maxLength": 128}, "reason": {"type": "string", "maxLength": 500},
                   "idempotency_key": {"type": "string", "maxLength": 128},
                   "approval_id": {"type": "string", "maxLength": 128}}, ["trip_id", "reason"],
                  side_effect=ToolSideEffectClass.LOCAL_REVERSIBLE,
                  approval=ToolApprovalRequirement.NO_APPROVAL_REQUIRED)
    reset = _m("paper_safety.reset", "Paper safety reset",
               "Execute a fail-closed, approval-backed breaker reset after all safe-condition checks pass. "
               "Transitions protective state only; never modifies fills/positions/cash/ledger, never repairs.",
               {"request_id": {"type": "string", "maxLength": 128},
                "approval_id": {"type": "string", "maxLength": 128}}, ["request_id"],
               side_effect=ToolSideEffectClass.LOCAL_IRREVERSIBLE,
               approval=ToolApprovalRequirement.EXPLICIT_APPROVAL_REQUIRED,
               idem_required=True, idem_class=ToolIdempotencyClass.IDEMPOTENCY_KEY_REQUIRED)
    sweep = _m("paper_safety.run_sweep", "Paper safety sweep",
               "Run a bounded on-demand/scheduled safety sweep over paper accounts.",
               {"account_ids": {"type": "array", "items": {"type": "string", "maxLength": 128}, "maxItems": 500}},
               [], side_effect=ToolSideEffectClass.LOCAL_REVERSIBLE,
               approval=ToolApprovalRequirement.NO_APPROVAL_REQUIRED)
    return [(trip, trip_adapter), (ack, acknowledge_adapter), (reqreset, request_reset_adapter),
            (reset, reset_adapter), (sweep, run_sweep_adapter)]


def register_safety_tools(registry) -> list[str]:
    keys = []
    for manifest, adapter in paper_safety_manifests():
        try:
            keys.append(registry.register(manifest, adapter, trusted=True))
        except Exception as exc:
            if "duplicate" not in str(exc).lower():
                raise
    return keys
