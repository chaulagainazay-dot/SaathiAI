"""M15 MCP integration — external MCP tools as UNTRUSTED connectors.

An MCP server's advertised tools are ingested as connector tools, but they are
treated as untrusted: they cannot declare their own risk below the platform
default, cannot bypass the ExecutionGateway, and cannot self-approve. Every MCP
tool call is routed through the same ExecutionEngine as any native connector.
The MCP server description is data, never instructions.
"""
from __future__ import annotations

from typing import Optional

from saathi.connectors.platform import registry as R
from saathi.connectors.platform.models import (
    ConnectorDef, ToolDef, RiskClass, MutationClass,
)
from saathi.connectors.platform import adapters as A


# MCP tools default to a cautious floor; a server CANNOT lower this.
_MCP_DEFAULT_RISK = RiskClass.EXTERNAL_SIDE_EFFECT


def register_mcp_server(*, server_id: str, display_name: str, tools: list[dict],
                        adapter: Optional[A.Adapter] = None,
                        trusted_read_only: bool = False) -> ConnectorDef:
    """Ingest an MCP server. `tools` is the server's advertised tool list
    (name/description/capability hints). Risk is assigned by US, not the server.

    trusted_read_only may only be set by the operator (never by server-supplied
    data); when true, tools hinting read-only get EXTERNAL_READ instead of the
    side-effect floor — still gateway-routed, still non-bypassing.
    """
    cid = f"mcp_{server_id}"
    if R.get_connector(cid):
        return R.get_connector(cid)
    conn = ConnectorDef(
        connector_id=cid, provider="mcp", display_name=f"MCP: {display_name}",
        category="automation", auth_type="token", local=False,
        capabilities=[f"mcp_{t.get('name','tool')}" for t in tools],
        risk_ceiling=RiskClass.HIGH_IMPACT,
        integration_status="deterministic-adapter-tested")
    R.register_connector(conn, adapter or A.DeterministicAdapter())
    for t in tools:
        name = str(t.get("name", "tool"))
        # server-declared risk is ADVISORY only — we clamp UP to our floor
        read_only = trusted_read_only and bool(t.get("read_only"))
        risk = RiskClass.EXTERNAL_READ if read_only else _MCP_DEFAULT_RISK
        R.register_tool(ToolDef(
            tool_id=f"{cid}.mcp_{name}", connector_id=cid,
            capability_id=f"mcp_{name}", name=f"{display_name}:{name}",
            description=str(t.get("description", ""))[:200],
            risk_class=risk,
            mutation_class=MutationClass.NONE if read_only else MutationClass.IRREVERSIBLE,
            idempotent=bool(read_only), reversible=bool(read_only),
            deterministic_adapter=True, rate_limit_bucket=cid))
    return conn
