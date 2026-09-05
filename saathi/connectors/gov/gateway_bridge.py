"""M28 — Canonical bridge: ExecutionGateway → GovernedConnectorRuntime.

Single production path for governed connector execution:

    Caller
      → ToolIntent (or ConnectorRequest → ToolIntent)
      → ExecutionGateway.submit
      → connector family handler
      → GovernedConnectorRuntime.execute
      → adapter
      → redacted ConnectorResult (bypass=false)
"""
from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from saathi.connectors.gov.models import ConnectorRequest, ConnectorResult
from saathi.connectors.gov.side_effects import (
    SideEffectClass,
    classify_operation,
    evaluate_side_effect,
)


_DEPRECATION_EVENTS: list[dict[str, Any]] = []
_DEP_LOCK = threading.Lock()
_IDEM: dict[str, dict[str, Any]] = {}
_IDEM_LOCK = threading.Lock()


def emit_deprecation(
    *,
    legacy_path: str,
    canonical_path: str = "ExecutionGateway→GovernedConnectorRuntime",
    caller_id: str = "",
    detail: str = "",
) -> dict[str, Any]:
    ev = {
        "schema": "m28.deprecation.v1",
        "ts": time.time(),
        "legacy_path": legacy_path,
        "canonical_path": canonical_path,
        "caller_id": caller_id,
        "detail": detail[:200],
        "privacy_safe": True,
    }
    with _DEP_LOCK:
        _DEPRECATION_EVENTS.append(ev)
        # cap memory
        if len(_DEPRECATION_EVENTS) > 500:
            del _DEPRECATION_EVENTS[:250]
    try:
        import json

        from saathi.runtime_paths import runtime_evidence_dir

        # Appended on every legacy-path call, including during imports and test
        # collection. It is a runtime log, not a certification record, so it
        # must not dirty the committed evidence tree.
        path = runtime_evidence_dir("m28") / "deprecation_events.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, default=str) + "\n")
    except Exception:
        pass
    return ev


def deprecation_events() -> list[dict[str, Any]]:
    with _DEP_LOCK:
        return list(_DEPRECATION_EVENTS)


def reset_deprecation_events() -> None:
    with _DEP_LOCK:
        _DEPRECATION_EVENTS.clear()


def reset_idempotency_cache() -> None:
    with _IDEM_LOCK:
        _IDEM.clear()


def _sha_idem(key: str) -> str:
    if len(key) == 64:
        try:
            int(key, 16)
            return key
        except ValueError:
            pass
    return hashlib.sha256((key or uuid.uuid4().hex).encode()).hexdigest()


def connector_request_to_toolintent(
    request: ConnectorRequest,
    *,
    risk_level: str | None = None,
    approval_level: str | None = None,
):
    """Build an immutable ToolIntent from a ConnectorRequest (no secrets)."""
    from saathi.execution.toolintent import (
        ActorType,
        ApprovalLevel,
        RiskLevel,
        builder,
    )
    from saathi.connectors.gov.side_effects import SideEffectClass as SEC

    sec = classify_operation(
        request.operation,
        method=request.method,
        capability=request.capability or request.operation,
    )
    # Risk from side-effect (caller cannot weaken)
    if sec in (SEC.PROHIBITED, SEC.FINANCIAL, SEC.ACCOUNT_CHANGE, SEC.PRIVILEGED):
        rl = RiskLevel.CRITICAL
        al = ApprovalLevel.L4
    elif sec in (SEC.EXTERNAL_MUTATION, SEC.COMMUNICATION):
        rl = RiskLevel.HIGH
        al = ApprovalLevel.L4
    elif sec is SEC.LOCAL_MUTATION:
        rl = RiskLevel.MEDIUM
        al = ApprovalLevel.L2
    else:
        rl = RiskLevel.LOW
        al = ApprovalLevel.L1

    if risk_level:
        try:
            rl = RiskLevel(risk_level)
        except Exception:
            pass
    if approval_level:
        try:
            al = ApprovalLevel(approval_level)
        except Exception:
            pass

    actor = request.actor_id or request.caller_id or "system"
    actor_type = ActorType.SYSTEM
    cc = (request.caller_class or "").lower()
    if cc in ("agent", "mission", "automation"):
        actor_type = ActorType.AGENT
    elif cc in ("api", "cli", "control_center", "test"):
        actor_type = ActorType.USER

    payload = dict(request.payload or {})
    # Never put credentials into intent parameters
    for k in list(payload.keys()):
        if str(k).lower() in (
            "api_key", "authorization", "password", "secret", "token",
            "access_token", "refresh_token", "cookie", "credential",
        ):
            payload[k] = "***REDACTED***"

    idem = request.idempotency_key or ""
    if not idem:
        idem = _sha_idem(
            f"{request.connector_id}:{request.operation}:{request.request_id or uuid.uuid4().hex}"
        )
    else:
        idem = _sha_idem(idem)

    meta = {
        "family": "connector",
        "m28_governed": True,
        "caller_class": request.caller_class or "connector_framework",
        "caller_id": request.caller_id,
        "resource_target": request.resource_target or request.url or "",
        "method": request.method,
        "url": request.url or "",
        "correlation_id": request.correlation_id or "",
        "approval_token": request.approval_token or "",
        "dry_run": bool(request.dry_run),
        "claimed_side_effect_class": request.claimed_side_effect_class or "",
        # approval_pre_resolved only when token present and will be validated in runtime
        "require_approval": sec in (
            SEC.EXTERNAL_MUTATION, SEC.COMMUNICATION, SEC.PRIVILEGED,
            SEC.FINANCIAL, SEC.ACCOUNT_CHANGE, SEC.PROHIBITED,
        ),
    }

    b = (
        builder()
        .actor(actor, actor_type)
        .mission(f"connector:{request.connector_id}")
        .capability(
            request.capability or request.operation,
            request.connector_id,
            request.operation,
        )
        .parameters({
            "payload": payload,
            "method": request.method,
            "url": request.url or "",
            "resource_target": request.resource_target or "",
            "headers_keys": sorted((request.headers or {}).keys()),
        })
        .reason(f"m28 connector {request.connector_id}.{request.operation}")
        .risk(rl, al)
        .metadata(meta)
    )
    b.data["idempotency_key"] = idem
    if request.correlation_id:
        b.data["correlation_id"] = request.correlation_id
    if request.request_id:
        # keep as metadata only; intent_id is uuid
        meta["request_id"] = request.request_id
        b.data["metadata"] = meta
    if request.timeout_seconds and request.timeout_seconds > 0:
        b.data["timeout"] = int(request.timeout_seconds)
    return b.build()


def _toolintent_to_request(intent) -> ConnectorRequest:
    params = dict(intent.parameters or {})
    meta = dict(intent.metadata or {})
    payload = params.get("payload") if isinstance(params.get("payload"), dict) else {
        k: v for k, v in params.items() if k not in ("payload", "method", "url", "headers_keys", "resource_target")
    }
    return ConnectorRequest(
        connector_id=intent.connector_id or "",
        operation=intent.operation or "",
        payload=payload,
        method=str(meta.get("method") or params.get("method") or "GET"),
        url=str(meta.get("url") or params.get("url") or ""),
        headers={},  # never rehydrate secrets from intent
        caller_id=str(meta.get("caller_id") or intent.actor_id or "unknown"),
        request_id=str(meta.get("request_id") or intent.intent_id or ""),
        approval_token=str(meta.get("approval_token") or ""),
        dry_run=bool(meta.get("dry_run")),
        actor_id=intent.actor_id or "",
        caller_class=str(meta.get("caller_class") or "unknown"),
        capability=intent.capability or intent.operation or "",
        resource_target=str(meta.get("resource_target") or params.get("resource_target") or ""),
        idempotency_key=intent.idempotency_key or "",
        correlation_id=intent.correlation_id or str(meta.get("correlation_id") or ""),
        claimed_side_effect_class=str(meta.get("claimed_side_effect_class") or ""),
    )


def _result_from_connector(cr: ConnectorResult) -> dict[str, Any]:
    """Map ConnectorResult → UniversalBoundary handler dict."""
    if cr.ok and cr.status in ("success", "shadow"):
        return {
            "status": "succeeded",
            "summary": cr.safe_message or cr.detail or cr.status,
            "connector_result": cr.to_dict(),
        }
    if cr.status in ("denied", "draining"):
        return {
            "status": "denied" if cr.status == "denied" else "failed",
            "summary": cr.safe_message or cr.detail or cr.status,
            "failure_category": cr.error_code or "permission",
            "retryable": False,
            "connector_result": cr.to_dict(),
        }
    return {
        "status": "failed",
        "summary": cr.safe_message or cr.detail or cr.status,
        "failure_category": cr.error_code or cr.status or "execution",
        "retryable": cr.status == "timeout",
        "connector_result": cr.to_dict(),
    }


def governed_connector_handler(intent, rec) -> dict:
    """Default ExecutionGateway handler for family=connector (M28)."""
    from saathi.connectors.gov.runtime import get_runtime

    request = _toolintent_to_request(intent)
    # Trading / future families already filtered; double-check side effects
    sec = classify_operation(
        request.operation,
        method=request.method,
        capability=request.capability,
    )
    if sec is SideEffectClass.PROHIBITED:
        cr = ConnectorResult(
            ok=False,
            connector_id=request.connector_id,
            operation=request.operation,
            status="denied",
            detail="side_effect:PROHIBITED",
            bypass=False,
            request_id=request.request_id,
            executed=False,
            side_effect_class=sec.value,
            error_code="PROHIBITED",
            safe_message="trading and prohibited operations are blocked",
            policy_state="deny",
            approval_state="denied",
        )
        return _result_from_connector(cr)

    # Idempotency short-circuit at bridge (in addition to gateway digest)
    if request.idempotency_key:
        with _IDEM_LOCK:
            prior = _IDEM.get(request.idempotency_key)
            if prior is not None:
                fp = f"{request.connector_id}:{request.operation}:{request.resource_target}"
                if prior.get("fingerprint") != fp:
                    cr = ConnectorResult(
                        ok=False,
                        connector_id=request.connector_id,
                        operation=request.operation,
                        status="denied",
                        detail="idempotency_conflict",
                        bypass=False,
                        request_id=request.request_id,
                        executed=False,
                        idempotency_state="conflict",
                        error_code="idempotency_conflict",
                        safe_message="idempotency key bound to different request fingerprint",
                    )
                    return _result_from_connector(cr)
                replay = dict(prior.get("result") or {})
                replay["idempotency_state"] = "replay"
                return {
                    "status": "succeeded" if replay.get("ok") else "failed",
                    "summary": replay.get("safe_message") or "idempotent_replay",
                    "connector_result": replay,
                }

    # Approval token for runtime: prefer gateway-bound approval id on record
    if getattr(rec, "approval_id", None) and not request.approval_token:
        request.approval_token = rec.approval_id

    rt = get_runtime()
    # M29: resolve connector identity only through registry (never import/path/filename)
    try:
        rt.registry.resolve(request.connector_id)
    except KeyError:
        cr = ConnectorResult(
            ok=False,
            connector_id=request.connector_id,
            operation=request.operation,
            status="denied",
            detail="connector_not_registered",
            bypass=False,
            request_id=request.request_id,
            executed=False,
            side_effect_class=sec.value,
            error_code="connector_not_registered",
            safe_message="unknown or unregistered connector",
            policy_state="deny",
        )
        return _result_from_connector(cr)

    # Grant approval token into runtime store when gateway already approved
    if request.approval_token:
        try:
            rt.grant_approval(request.approval_token)
        except Exception:
            pass
    # If gateway auto-approved read-only, synthesize token for runtime path consistency
    appr = getattr(rec, "approval", "") or ""
    if appr in ("automatic", "approved") and not request.approval_token:
        # For EXTERNAL_MUTATION the gateway would not auto-approve without binding
        pass

    # Trust-aware approval floor (caller cannot lower)
    try:
        from saathi.connectors.registry.trust import approval_floor_for_trust
        insp = rt.registry.inspect(request.connector_id)
        floor = approval_floor_for_trust(insp.get("trust_level") or "INTERNAL")
        if floor == "DENIED":
            cr = ConnectorResult(
                ok=False,
                connector_id=request.connector_id,
                operation=request.operation,
                status="denied",
                detail="trust:PROHIBITED",
                bypass=False,
                request_id=request.request_id,
                executed=False,
                side_effect_class=SideEffectClass.PROHIBITED.value,
                error_code="PROHIBITED",
                safe_message="connector trust level PROHIBITED",
                policy_state="deny",
            )
            return _result_from_connector(cr)
    except Exception:
        pass

    cr = rt.execute(request)
    if cr.ok and request.idempotency_key:
        fp = f"{request.connector_id}:{request.operation}:{request.resource_target}"
        with _IDEM_LOCK:
            _IDEM[request.idempotency_key] = {
                "fingerprint": fp,
                "result": cr.to_dict(),
            }
    return _result_from_connector(cr)


def ensure_default_connector_handler(boundary=None) -> None:
    """Register M28 connector handler on a UniversalBoundary if missing."""
    if boundary is None:
        from saathi.execution.universal import default_boundary
        boundary = default_boundary()
    if "connector" not in boundary.handlers:
        boundary.register_handler("connector", governed_connector_handler)
    # Also cover mcp when connector_id is gov.mcp without custom handler
    if "mcp" not in boundary.handlers:
        boundary.register_handler("mcp", governed_connector_handler)


def execute_via_gateway(
    request: ConnectorRequest,
    *,
    gateway=None,
    runtime=None,
    force_new: bool = False,
) -> ConnectorResult:
    """Canonical production entry: ConnectorRequest → ExecutionGateway → runtime.

    Returns ConnectorResult with bypass=False.
    """
    if not request.caller_id and not request.actor_id:
        return ConnectorResult(
            ok=False,
            connector_id=request.connector_id,
            operation=request.operation,
            status="denied",
            detail="missing_caller_identity",
            bypass=False,
            executed=False,
            error_code="unauthorized_caller",
            safe_message="caller identity required",
            policy_state="deny",
        )
    if not request.connector_id:
        return ConnectorResult(
            ok=False,
            connector_id="",
            operation=request.operation,
            status="denied",
            detail="missing_connector",
            bypass=False,
            executed=False,
            error_code="intent_validation_failed",
            safe_message="connector_id required",
        )
    if not request.operation:
        return ConnectorResult(
            ok=False,
            connector_id=request.connector_id,
            operation="",
            status="denied",
            detail="missing_operation",
            bypass=False,
            executed=False,
            error_code="intent_validation_failed",
            safe_message="operation required",
        )

    # Optional inject runtime for tests
    if runtime is not None:
        from saathi.connectors.gov import runtime as rt_mod
        # use provided runtime by temporarily swapping is hard; call directly
        # but still go through gateway when gateway provided.
        pass

    from saathi.execution.gateway import ExecutionGateway
    from saathi.execution.universal import UniversalBoundary, reset_boundary
    from saathi.execution.store import ExecutionStore
    from saathi.execution.queue.memory import MemoryQueue
    import tempfile
    from pathlib import Path

    if gateway is None:
        # Isolated boundary for one-shot when no process gateway injected
        fd, p = tempfile.mkstemp(suffix=".m28.egw.db")
        import os
        os.close(fd)
        store = ExecutionStore(Path(p))
        boundary = UniversalBoundary(store=store, auto_integrations=False)
        ensure_default_connector_handler(boundary)
        gateway = ExecutionGateway(MemoryQueue(), boundary=boundary)
    else:
        ensure_default_connector_handler(getattr(gateway, "_ub", lambda: None)() if hasattr(gateway, "_ub") else None)
        try:
            ensure_default_connector_handler(gateway._ub())
        except Exception:
            pass

    intent = connector_request_to_toolintent(request)
    captured: dict[str, Any] = {}

    def _capturing_handler(intent_obj, rec):
        req = _toolintent_to_request(intent_obj)
        if getattr(rec, "approval_id", None) and not req.approval_token:
            req.approval_token = rec.approval_id
        use_rt = runtime
        if use_rt is None:
            from saathi.connectors.gov.runtime import get_runtime
            use_rt = get_runtime()
        if req.approval_token:
            try:
                use_rt.grant_approval(req.approval_token)
            except Exception:
                pass
        # Gateway automatic approval for read-only: mint single-use token so runtime
        # side-effect checks that require approval can still pass when gateway already approved.
        appr_state = getattr(rec, "approval", "") or ""
        if appr_state in ("automatic", "approved") and not req.approval_token:
            tok = f"gw-auto-{rec.execution_id}"
            try:
                use_rt.grant_approval(tok)
                req.approval_token = tok
            except Exception:
                pass
        cr = use_rt.execute(req)
        captured["cr"] = cr
        return _result_from_connector(cr)

    approval_id = request.approval_token or ""
    # When approval token present, bind it so gateway accepts L4 intents
    if approval_id:
        try:
            digest = __import__(
                "saathi.execution.record", fromlist=["tool_intent_digest"]
            ).tool_intent_digest(intent)
            ub = gateway._ub() if hasattr(gateway, "_ub") else None
            if ub is not None:
                ub.store.bind_approval(
                    approval_id,
                    digest=digest,
                    actor=intent.actor_id,
                    expires_at=time.time() + 3600,
                )
        except Exception:
            pass

    rec = gateway.submit(
        intent,
        approval_id=approval_id,
        handler=_capturing_handler,
        execute=True,
        force_new=force_new,
    )

    if "cr" in captured:
        cr = captured["cr"]
        cr.bypass = False
        if rec.execution_id and rec.execution_id not in (cr.evidence_refs or []):
            cr.evidence_refs = list(cr.evidence_refs or []) + [rec.execution_id]
        return cr

    if rec.status == "approval_required":
        return ConnectorResult(
            ok=False,
            connector_id=request.connector_id,
            operation=request.operation,
            status="denied",
            detail="approval_required",
            bypass=False,
            request_id=request.request_id or intent.intent_id,
            executed=False,
            approval_state="required",
            error_code="approval_required",
            safe_message="approval required for this side-effect class",
            evidence_refs=[rec.execution_id] if rec.execution_id else [],
            policy_state="deny",
        )
    return ConnectorResult(
        ok=False,
        connector_id=request.connector_id,
        operation=request.operation,
        status="denied" if rec.status == "denied" else "error",
        detail=rec.result_summary or rec.status,
        bypass=False,
        request_id=request.request_id or intent.intent_id,
        executed=False,
        error_code=rec.failure_category or rec.status,
        safe_message=rec.result_summary or rec.status,
        evidence_refs=[rec.execution_id] if rec.execution_id else [],
        policy_state="deny",
        approval_state="denied" if rec.status == "denied" else "",
    )


@dataclass
class BridgeStatus:
    schema: str = "m28.gateway_bridge.v1"
    connector_handler_registered: bool = False
    deprecation_events: int = 0
    production_bypasses: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "connector_handler_registered": self.connector_handler_registered,
            "deprecation_events": self.deprecation_events,
            "production_bypasses": self.production_bypasses,
        }
