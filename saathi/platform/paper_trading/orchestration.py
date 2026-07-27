"""M62.5 — the canonical broker-submission path.

    PlatformAgentRuntime → ExecutionGateway → registered paper-trading tool →
    PaperTradingService → PaperBroker

The API and any agent runtime call ONLY these helpers. They build a server-side
``ToolApprovalReference`` (never UI-only authority) and route through
``ExecutionGateway.execute_registered_tool`` so the fail-closed tool-runtime layer
re-validates approval scope, idempotency, authority, and side-effect class before
the adapter ever reaches the broker.
"""
from __future__ import annotations

import time as _time
from typing import Any

from saathi.execution.gateway import ExecutionGateway
from saathi.tool_runtime.contracts import ToolApprovalReference


def _gateway() -> ExecutionGateway:
    return ExecutionGateway()


def _identity_args(ctx) -> dict:
    return {"user_id": ctx.user_id, "role": ctx.role, "org_id": ctx.org_id,
            "workspace_id": ctx.workspace_id, "project_id": ctx.project_id}


def submit_via_gateway(ctx, *, intent_id: str, market: dict, approval_id: str = "",
                       idempotency_key: str = "", expires_at: float = 0.0, gateway: ExecutionGateway | None = None):
    """Submit a paper order through the Runtime/Gateway/tool boundary. Returns the
    ToolExecutionResult (never the broker service directly)."""
    gw = gateway or _gateway()
    requested_by = ctx.requested_by()
    approval_ref = None
    if approval_id:
        approval_ref = ToolApprovalReference(
            approval_id=approval_id, actor=requested_by, capability="paper_order_submit",
            tool_id="paper.order.submit", tool_version="1.0.0", side_effect_class="LOCAL_IRREVERSIBLE",
            authority="LOCAL_MUTATION", action="paper_order_submit", active=True,
            expires_at=float(expires_at or (_time.time() + 3600)))
    args = {**_identity_args(ctx), "intent_id": intent_id, "approval_id": approval_id, "market": market}
    return gw.execute_registered_tool(
        tool_id="paper.order.submit", arguments=args, run_id=ctx.run_id or f"paper:{ctx.org_id}",
        requested_by=requested_by, capability="paper_order_submit", tool_version="1.0.0",
        idempotency_key=idempotency_key or intent_id, approval_reference=approval_ref)


def cancel_via_gateway(ctx, *, order_id: str, idempotency_key: str = "", gateway: ExecutionGateway | None = None):
    gw = gateway or _gateway()
    args = {**_identity_args(ctx), "order_id": order_id, "idempotency_key": idempotency_key}
    return gw.execute_registered_tool(
        tool_id="paper.order.cancel", arguments=args, run_id=ctx.run_id or f"paper:{ctx.org_id}",
        requested_by=ctx.requested_by(), capability="paper_order_cancel", tool_version="1.0.0",
        idempotency_key=idempotency_key or f"cancel:{order_id}")


def process_event_via_gateway(ctx, *, order_id: str, market: dict, gateway: ExecutionGateway | None = None):
    gw = gateway or _gateway()
    args = {**_identity_args(ctx), "order_id": order_id, "market": market}
    return gw.execute_registered_tool(
        tool_id="paper.order.process_event", arguments=args, run_id=ctx.run_id or f"paper:{ctx.org_id}",
        requested_by=ctx.requested_by(), capability="paper_order_process_event", tool_version="1.0.0")
