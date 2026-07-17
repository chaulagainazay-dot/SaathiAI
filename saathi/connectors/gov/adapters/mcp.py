"""M27 — MCP adapter: reuse mcp_governance; no duplicate architecture."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from saathi.connectors.gov.models import ConnectorRequest, ConnectorResult
from saathi.connectors.gov.redaction import redact_payload


@dataclass
class McpAdapter:
    """Thin governed wrapper around existing MCP policy/inventory."""

    name: str = "mcp"

    def execute(self, request: ConnectorRequest, **_: Any) -> ConnectorResult:
        op = request.operation
        mcp_id = str((request.payload or {}).get("mcp_id") or "saathi-codebase-memory")

        try:
            from saathi.mcp_governance import policy as mcp_policy
        except Exception as e:
            return ConnectorResult(
                ok=False,
                connector_id=request.connector_id,
                operation=op,
                status="error",
                detail=f"mcp_governance_unavailable:{type(e).__name__}",
                bypass=False,
            )

        if op in ("health", "status", "validate"):
            enabled = mcp_policy.is_enabled(mcp_id)
            # Policy snapshot — no secrets
            snap = {
                "mcp_id": mcp_id,
                "enabled": enabled,
                "connect_timeout_sec": getattr(mcp_policy, "DEFAULT_CONNECT_TIMEOUT_SEC", 5.0),
                "request_timeout_sec": getattr(mcp_policy, "DEFAULT_REQUEST_TIMEOUT_SEC", 30.0),
                "max_retries": getattr(mcp_policy, "DEFAULT_MAX_RETRIES", 2),
            }
            return ConnectorResult(
                ok=True,
                connector_id=request.connector_id,
                operation=op,
                status="success",
                detail="mcp_policy_ok" if enabled else "mcp_disabled",
                data=redact_payload(snap) if isinstance(redact_payload(snap), dict) else snap,
                privacy_safe=True,
                bypass=False,
            )

        if op == "inventory":
            try:
                from saathi.mcp_governance import inventory as inv

                items = inv.list_inventory() if hasattr(inv, "list_inventory") else []
                if callable(items):
                    items = items()
            except Exception:
                items = []
            return ConnectorResult(
                ok=True,
                connector_id=request.connector_id,
                operation=op,
                status="success",
                detail="mcp_inventory",
                data={"count": len(items) if isinstance(items, list) else 0},
                privacy_safe=True,
                bypass=False,
            )

        # Non-allowlisted MCP ops fail closed (no arbitrary remote MCP calls in M27)
        return ConnectorResult(
            ok=False,
            connector_id=request.connector_id,
            operation=op,
            status="denied",
            detail=f"mcp_operation_not_enabled_m27:{op}",
            bypass=False,
        )
