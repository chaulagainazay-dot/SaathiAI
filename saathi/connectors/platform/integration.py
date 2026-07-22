"""M15.1 connector integration funnel — the ONE surface Chat, M10 Agents,
CEO OS, and Voice use to reach external systems.

Every caller (Chat, Agent, CEO, Voice) discovers capabilities and executes
through this module, which delegates to the ExecutionEngine. None of them call a
provider client directly — the direct-call scanner (`migration.py`) enforces
that. `describe_action` lets a caller show the user the exact risk/approval/
account BEFORE executing; `run` is the only execution entry.
"""
from __future__ import annotations

from typing import Optional

from saathi.connectors.platform import registry as R
from saathi.connectors.platform import catalog
from saathi.connectors.platform.execution import (
    ExecutionEngine, ExecRequest, default_engine,
)
from saathi.connectors.platform.models import (
    RiskClass, APPROVAL_THRESHOLD, MANUAL_ONLY, normalized_input_hash,
)


def available_capabilities() -> list[dict]:
    """What the platform can do, provider-neutral. For agent tool discovery."""
    return catalog.all_capabilities()


def tools_for(capability_id: str) -> list[dict]:
    return [t.to_dict() for t in R.tools_for_capability(capability_id)]


def describe_action(*, tool_id: str, account_id: str = "", args: Optional[dict] = None,
                    owner: str = "") -> dict:
    """Explain an action to a human/agent BEFORE it runs: connector, account,
    risk, whether approval is required, and manual-only status. Used by Chat,
    Voice (spoken confirmation), and CEO OS to present the exact action."""
    args = args or {}
    tool = R.get_tool(tool_id)
    if not tool:
        return {"error": "unknown tool", "tool_id": tool_id}
    risk = tool.risk_class
    return {
        "tool_id": tool.tool_id, "connector_id": tool.connector_id,
        "capability_id": tool.capability_id, "account_id": account_id,
        "risk_class": int(risk), "risk_label": risk.name,
        "requires_approval": int(risk) >= int(APPROVAL_THRESHOLD) or tool.requires_approval,
        "manual_only": int(risk) >= int(MANUAL_ONLY),
        "mutation_class": tool.mutation_class.value,
        "input_hash": normalized_input_hash(tool_id, account_id, args),
    }


def run(*, owner: str, tool_id: str, account_id: str = "", args: Optional[dict] = None,
        approval_id: str = "", idempotency_key: str = "", environment: str = "staging",
        target: str = "", actor_type: str = "user",
        engine: Optional[ExecutionEngine] = None) -> dict:
    """The single execution entry for every caller. Gateway-routed. actor_type
    'agent' marks the run as agent-originated (agents can never self-approve —
    the engine still requires a bound approval for risk >= 3)."""
    eng = engine or default_engine()
    r = eng.execute(ExecRequest(
        owner=owner, tool_id=tool_id, account_id=account_id, args=dict(args or {}),
        approval_id=approval_id, idempotency_key=idempotency_key,
        environment=environment, target=target, actor_type=actor_type))
    return r.to_dict()


def ceo_evidence_tier(result: dict) -> str:
    """Map a connector result to a CEO-OS evidence tier so a connector FAILURE
    is never silently turned into a zero/success. Unavailable stays unavailable.
    """
    status = result.get("status")
    if status in ("success", "partial"):
        return "verified"          # real connector-sourced data
    if status == "approval_required":
        return "pending_approval"
    if status in ("failed", "blocked"):
        return "unavailable"       # NOT zero, NOT success
    if status == "uncertain":
        return "uncertain"
    return "unavailable"
