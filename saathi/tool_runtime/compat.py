"""M49.2 compatibility bridge: optional routing from legacy tool names.

Does not replace saathi.tools.execute_tool governance; provides a canonical
path for migrated read-only tools. User input cannot register tools.
"""
from __future__ import annotations

from typing import Any

from saathi.tool_runtime.adapters.migrated import LEGACY_NAME_MAP
from saathi.tool_runtime.contracts import ToolExecutionRequest
from saathi.tool_runtime.service import default_tool_service


def try_canonical_legacy_tool(
    name: str,
    args: dict | None = None,
    *,
    run_id: str = "legacy",
    requested_by: str = "legacy:saathi.tools",
) -> dict | None:
    """If name is mapped to a migrated tool, execute via ToolExecutionService.

    Returns a legacy-shaped dict, or None if not migrated (caller keeps legacy path).
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

    from saathi.execution import ExecutionGateway

    result = ExecutionGateway().execute_registered_tool(
        tool_id=tool_id,
        arguments=args,
        run_id=run_id,
        requested_by=requested_by,
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
