"""M49.3 compatibility bridge: bounded routing from legacy tool names.

Only tools in LEGACY_NAME_MAP route through ExecutionGateway. Unknown tools
return None so the caller rejects them — there is no generic legacy fallback
for unmapped names at this layer. User input cannot register tools.
"""
from __future__ import annotations

from typing import Any

from saathi.tool_runtime.adapters.migrated import LEGACY_NAME_MAP
from saathi.tool_runtime.contracts import ToolApprovalReference, ToolExecutionRequest
from saathi.tool_runtime.service import default_tool_service


def try_canonical_legacy_tool(
    name: str,
    args: dict | None = None,
    *,
    run_id: str = "legacy",
    requested_by: str = "legacy:saathi.tools",
    approval_reference: ToolApprovalReference | None = None,
    idempotency_key: str = "",
) -> dict | None:
    """If name is mapped to a migrated tool, execute via ExecutionGateway.

    Returns a legacy-shaped dict, or None if not migrated (caller must not
    invent a generic fallback for unknown tools).
    """
    tool_id = LEGACY_NAME_MAP.get(name)
    if not tool_id:
        return None
    args = dict(args or {})
    # list-only bridges: ignore mutating actions
    if name == "manage_tasks" and args.get("action") not in (None, "", "list"):
        return None
    if name == "my_files" and args.get("action") not in (None, "", "list"):
        return None
    # normalize list args
    if name in ("manage_tasks", "my_files"):
        args = {}
    # check_email → gmail search fixture
    if name == "check_email":
        args = {
            "query": str(args.get("query") or args.get("q") or "is:unread")[:200],
            "limit": int(args.get("limit") or 5),
        }
    # send_email → dry-run connector (requires approval + idempotency)
    if name == "send_email":
        args = {
            "to": str(args.get("to") or "")[:200],
            "subject": str(args.get("subject") or "")[:200],
            "body": str(args.get("body") or args.get("text") or "")[:4000],
        }
        if not idempotency_key:
            idempotency_key = f"legacy-send-{run_id}"
        if not approval_reference:
            # Cannot construct fake approval — return structured requirement
            return {
                "error": "approval_required",
                "message": "M49.3: send_email requires explicit approval via canonical path",
                "canonical_tool_id": tool_id,
                "outcome_class": "BLOCKED",
                "dry_run_only": True,
            }

    from saathi.execution import ExecutionGateway

    result = ExecutionGateway().execute_registered_tool(
        tool_id=tool_id,
        arguments=args,
        run_id=run_id,
        requested_by=requested_by,
        approval_reference=approval_reference,
        idempotency_key=idempotency_key,
    )
    if not result.ok:
        return {
            "error": result.error_code or "canonical_rejected",
            "message": result.safe_message,
            "canonical_tool_id": tool_id,
            "outcome_class": result.outcome_class.value,
        }
    # flatten data for legacy consumers
    data = dict(result.data or {})
    data["_canonical_tool_id"] = tool_id
    data["_outcome_class"] = result.outcome_class.value
    return data
