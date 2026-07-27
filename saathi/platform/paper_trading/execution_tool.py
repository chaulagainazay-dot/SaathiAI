"""M62.5 — registered paper-trading tools (the ONLY broker mutation path).

These manifests + adapters plug into the M49.1 canonical tool registry so every
paper-broker mutation flows PlatformAgentRuntime → ExecutionGateway →
ToolExecutionService → this adapter → PaperTradingService → PaperBroker. No API
route, agent, or browser may reach the broker except through here.

Authority is ``LOCAL_MUTATION`` with a ``LOCAL_*`` side effect — never
``FINANCIAL_EXECUTION`` (which the registry prohibits). A paper fill mutates only
local SQLite simulation state; no real capital, no external side effect, no network.
"""
from __future__ import annotations

import threading
from typing import Any

from saathi.platform.context import PlatformExecutionContext, PlatformContextError
from saathi.platform.paper_trading.broker import MarketEvent
from saathi.platform.paper_trading.models import D
from saathi.platform.trading_models import DataQuality, MarketState
from saathi.tool_runtime.context import BoundedToolContext
from saathi.tool_runtime.contracts import (
    IdempotencyPolicy, RetryPolicy, TimeoutPolicy, ToolApprovalRequirement, ToolAuthorityClass,
    ToolCancellationSupport, ToolIdempotencyClass, ToolManifest, ToolRetryClass, ToolSecretPolicy,
    ToolSideEffectClass,
)

_SVC = None
_SVC_LOCK = threading.RLock()


def default_paper_service():
    """Process-wide PaperTradingService sharing the platform DB (for approvals/audit)."""
    global _SVC
    with _SVC_LOCK:
        if _SVC is None:
            from saathi.platform.paper_trading.service import PaperTradingService
            from saathi.platform.paper_trading.store import PaperStore
            try:
                from saathi.platform.service import default_platform
                pstore = default_platform().store
            except Exception:
                pstore = None
            _SVC = PaperTradingService(PaperStore(), platform_store=pstore)
            if pstore is not None:
                _SVC.bind_audit(pstore)
        return _SVC


def set_paper_service_for_tests(svc) -> None:
    global _SVC
    with _SVC_LOCK:
        _SVC = svc


def _ctx_from_args(args: dict) -> PlatformExecutionContext:
    return PlatformExecutionContext(
        user_id=str(args.get("user_id", "")), role=str(args.get("role", "")),
        org_id=str(args.get("org_id", "")), workspace_id=str(args.get("workspace_id", "")),
        project_id=str(args.get("project_id", "")), approval_id=str(args.get("approval_id", "")))


def _event_from_args(m: dict) -> MarketEvent:
    return MarketEvent(
        symbol=str(m["symbol"]), ts=float(m.get("ts", 0.0)), bid=D(m["bid"]), ask=D(m["ask"]),
        last=D(m.get("last", m["ask"])), liquidity=D(m.get("liquidity", "0")),
        quality=DataQuality(m.get("quality", "VALID")), market_state=MarketState(m.get("market_state", "OPEN")),
        ref=str(m.get("ref", "")))


# ── adapters ──────────────────────────────────────────────────────────────────
def submit_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    svc = default_paper_service()
    pctx = _ctx_from_args(args)
    try:
        res = svc.submit_order(pctx, intent_id=str(args["intent_id"]), event=_event_from_args(args["market"]),
                               approval_id=str(args.get("approval_id", "")), _via_gateway=True)
    except PlatformContextError as e:
        return {"error": f"{e.code}: {e.message}"}
    ctx.evidence("paper.order.submit", {"order_id": res["order"]["id"]})
    return {"data": {"order_id": res["order"]["id"], "broker_state": res["order"]["broker_state"],
                     "idempotent_replay": bool(res.get("idempotent_replay"))},
            "side_effect_confirmed": True}


def cancel_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    svc = default_paper_service()
    pctx = _ctx_from_args(args)
    try:
        res = svc.cancel_order(pctx, order_id=str(args["order_id"]), idempotency_key=str(args.get("idempotency_key", "")))
    except PlatformContextError as e:
        return {"error": f"{e.code}: {e.message}"}
    ctx.evidence("paper.order.cancel", {"order_id": args.get("order_id")})
    return {"data": {"cancelled": bool(res.get("cancelled")), "order_id": res["order"]["id"],
                     "broker_state": res["order"]["broker_state"]}, "side_effect_confirmed": True}


def process_event_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    svc = default_paper_service()
    pctx = _ctx_from_args(args)
    try:
        res = svc.process_market_event(pctx, order_id=str(args["order_id"]), event=_event_from_args(args["market"]))
    except PlatformContextError as e:
        return {"error": f"{e.code}: {e.message}"}
    ctx.evidence("paper.order.process_event", {"order_id": args.get("order_id"), "filled": res.get("filled")})
    return {"data": {"filled": bool(res.get("filled")), "reason": res.get("reason", ""),
                     "broker_state": res["order"]["broker_state"]}, "side_effect_confirmed": True}


# ── manifests ───────────────────────────────────────────────────────────────
_IDENTITY_PROPS = {
    "user_id": {"type": "string", "maxLength": 128}, "role": {"type": "string", "maxLength": 32},
    "org_id": {"type": "string", "maxLength": 128}, "workspace_id": {"type": "string", "maxLength": 128},
    "project_id": {"type": "string", "maxLength": 128},
}
_MARKET_SCHEMA = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string", "maxLength": 64}, "ts": {"type": "number"},
        "bid": {"type": "string"}, "ask": {"type": "string"}, "last": {"type": "string"},
        "liquidity": {"type": "string"}, "quality": {"type": "string", "maxLength": 32},
        "market_state": {"type": "string", "maxLength": 32}, "ref": {"type": "string", "maxLength": 128},
    },
    "required": ["symbol", "bid", "ask"],
}


def paper_trading_manifests() -> list[tuple[ToolManifest, Any]]:
    submit = ToolManifest(
        tool_id="paper.order.submit", version="1.0.0", display_name="Paper order submit",
        description="Authorize + reserve + create a durable paper broker order (PAPER only, long-only).",
        domain="paper_trading", capabilities=("paper_order_submit",),
        authority_class=ToolAuthorityClass.LOCAL_MUTATION, side_effect_class=ToolSideEffectClass.LOCAL_IRREVERSIBLE,
        approval_requirement=ToolApprovalRequirement.EXPLICIT_APPROVAL_REQUIRED, secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={"type": "object", "properties": {**_IDENTITY_PROPS,
                      "intent_id": {"type": "string", "maxLength": 128}, "approval_id": {"type": "string", "maxLength": 128},
                      "market": _MARKET_SCHEMA}, "required": ["org_id", "workspace_id", "user_id", "role", "intent_id", "market"],
                      "additionalProperties": False},
        output_schema={"type": "object", "properties": {"order_id": {"type": "string"},
                       "broker_state": {"type": "string"}, "idempotent_replay": {"type": "boolean"}},
                       "required": ["order_id", "broker_state"]},
        timeout_policy=TimeoutPolicy(default_sec=10, max_sec=30),
        retry_policy=RetryPolicy(max_attempts=1, retry_class=ToolRetryClass.NEVER),
        idempotency_policy=IdempotencyPolicy(klass=ToolIdempotencyClass.IDEMPOTENCY_KEY_REQUIRED, require_key=True),
        cancellation_support=ToolCancellationSupport.NOT_CANCELLABLE)

    cancel = ToolManifest(
        tool_id="paper.order.cancel", version="1.0.0", display_name="Paper order cancel",
        description="Cancel an open/partially-filled paper order and release its reservation.",
        domain="paper_trading", capabilities=("paper_order_cancel",),
        authority_class=ToolAuthorityClass.LOCAL_MUTATION, side_effect_class=ToolSideEffectClass.LOCAL_REVERSIBLE,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED, secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={"type": "object", "properties": {**_IDENTITY_PROPS,
                      "order_id": {"type": "string", "maxLength": 128}, "idempotency_key": {"type": "string", "maxLength": 128}},
                      "required": ["org_id", "workspace_id", "user_id", "role", "order_id"], "additionalProperties": False},
        output_schema={"type": "object", "properties": {"cancelled": {"type": "boolean"}, "order_id": {"type": "string"},
                       "broker_state": {"type": "string"}}, "required": ["cancelled", "order_id"]},
        timeout_policy=TimeoutPolicy(default_sec=10, max_sec=30),
        idempotency_policy=IdempotencyPolicy(klass=ToolIdempotencyClass.NATURALLY_IDEMPOTENT),
        cancellation_support=ToolCancellationSupport.NOT_CANCELLABLE)

    process = ToolManifest(
        tool_id="paper.order.process_event", version="1.0.0", display_name="Paper order process market event",
        description="Deterministically fill a paper order against one market event (system, bounded).",
        domain="paper_trading", capabilities=("paper_order_process_event",),
        authority_class=ToolAuthorityClass.LOCAL_MUTATION, side_effect_class=ToolSideEffectClass.LOCAL_IRREVERSIBLE,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED, secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={"type": "object", "properties": {**_IDENTITY_PROPS,
                      "order_id": {"type": "string", "maxLength": 128}, "market": _MARKET_SCHEMA},
                      "required": ["org_id", "workspace_id", "user_id", "role", "order_id", "market"],
                      "additionalProperties": False},
        output_schema={"type": "object", "properties": {"filled": {"type": "boolean"}, "reason": {"type": "string"},
                       "broker_state": {"type": "string"}}, "required": ["filled"]},
        timeout_policy=TimeoutPolicy(default_sec=10, max_sec=30),
        idempotency_policy=IdempotencyPolicy(klass=ToolIdempotencyClass.NATURALLY_IDEMPOTENT),
        cancellation_support=ToolCancellationSupport.NOT_CANCELLABLE)

    return [(submit, submit_adapter), (cancel, cancel_adapter), (process, process_event_adapter)]


def register_paper_tools(registry) -> list[str]:
    keys = []
    for manifest, adapter in paper_trading_manifests():
        try:
            keys.append(registry.register(manifest, adapter, trusted=True))
        except Exception as exc:
            if "duplicate" not in str(exc).lower():
                raise
    return keys
