"""M62.7 — canonical safety mutation path through Runtime/Gateway.

    PlatformAgentRuntime → ExecutionGateway → registered paper_safety.* tool →
    SafetyService

The API and any operator action call ONLY these helpers for breaker mutations. The
reset helper builds a server-side ``ToolApprovalReference`` (never UI-only authority)
so the fail-closed tool-runtime layer re-validates approval scope, idempotency,
authority and side-effect class before the adapter reaches SafetyService.
"""
from __future__ import annotations

import time as _time

from saathi.execution.gateway import ExecutionGateway
from saathi.tool_runtime.contracts import ToolApprovalReference


def _gateway() -> ExecutionGateway:
    return ExecutionGateway()


def _identity(ctx) -> dict:
    return {"user_id": ctx.user_id, "role": ctx.role, "org_id": ctx.org_id,
            "workspace_id": ctx.workspace_id, "project_id": ctx.project_id, "authority": ctx.authority}


def trip_via_gateway(ctx, *, scope: str, scope_ref: str = "", reason: str = "manual kill switch",
                     gateway: ExecutionGateway | None = None):
    gw = gateway or _gateway()
    args = {**_identity(ctx), "scope": scope, "scope_ref": scope_ref, "reason": reason}
    return gw.execute_registered_tool(tool_id="paper_safety.trip", arguments=args,
                                      run_id=ctx.run_id or f"safety:{ctx.org_id}", requested_by=ctx.requested_by(),
                                      capability="paper_safety_trip", tool_version="1.0.0",
                                      idempotency_key=f"trip:{scope}:{scope_ref}")


def acknowledge_via_gateway(ctx, *, trip_id: str, note: str = "", evidence_reviewed: bool = False,
                            gateway: ExecutionGateway | None = None):
    gw = gateway or _gateway()
    args = {**_identity(ctx), "trip_id": trip_id, "note": note, "evidence_reviewed": evidence_reviewed}
    return gw.execute_registered_tool(tool_id="paper_safety.acknowledge", arguments=args,
                                      run_id=ctx.run_id or f"safety:{ctx.org_id}", requested_by=ctx.requested_by(),
                                      capability="paper_safety_acknowledge", tool_version="1.0.0",
                                      idempotency_key=f"ack:{trip_id}")


def request_reset_via_gateway(ctx, *, trip_id: str, reason: str, approval_id: str = "",
                              idempotency_key: str = "", gateway: ExecutionGateway | None = None):
    gw = gateway or _gateway()
    args = {**_identity(ctx), "trip_id": trip_id, "reason": reason, "approval_id": approval_id,
            "idempotency_key": idempotency_key}
    return gw.execute_registered_tool(tool_id="paper_safety.request_reset", arguments=args,
                                      run_id=ctx.run_id or f"safety:{ctx.org_id}", requested_by=ctx.requested_by(),
                                      capability="paper_safety_request_reset", tool_version="1.0.0",
                                      idempotency_key=idempotency_key or f"rreq:{trip_id}")


def reset_via_gateway(ctx, *, request_id: str, approval_id: str = "", expires_at: float = 0.0,
                      idempotency_key: str = "", gateway: ExecutionGateway | None = None):
    gw = gateway or _gateway()
    approval_ref = None
    if approval_id:
        approval_ref = ToolApprovalReference(
            approval_id=approval_id, actor=ctx.requested_by(), capability="paper_safety_reset",
            tool_id="paper_safety.reset", tool_version="1.0.0", side_effect_class="LOCAL_IRREVERSIBLE",
            authority="LOCAL_MUTATION", action="paper_safety_reset", active=True,
            expires_at=float(expires_at or (_time.time() + 3600)))
    args = {**_identity(ctx), "request_id": request_id, "approval_id": approval_id}
    return gw.execute_registered_tool(tool_id="paper_safety.reset", arguments=args,
                                      run_id=ctx.run_id or f"safety:{ctx.org_id}", requested_by=ctx.requested_by(),
                                      capability="paper_safety_reset", tool_version="1.0.0",
                                      idempotency_key=idempotency_key or f"reset:{request_id}",
                                      approval_reference=approval_ref)


def run_sweep_via_gateway(ctx, *, account_ids=None, gateway: ExecutionGateway | None = None):
    gw = gateway or _gateway()
    args = {**_identity(ctx), "account_ids": list(account_ids or [])}
    return gw.execute_registered_tool(tool_id="paper_safety.run_sweep", arguments=args,
                                      run_id=ctx.run_id or f"safety:{ctx.org_id}", requested_by=ctx.requested_by(),
                                      capability="paper_safety_run_sweep", tool_version="1.0.0")
