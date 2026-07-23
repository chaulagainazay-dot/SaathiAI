"""M51 AgentExecutor / gateway platform-context adapter.

Trusted context construction only — callers cannot spoof user/org/workspace.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.models import PlatformPermission
from saathi.platform.service import default_platform


@dataclass
class BoundAgentCall:
    ctx: PlatformExecutionContext
    tool_id: str
    arguments: dict
    approval_id: str = ""


class PlatformAgentBinding:
    """Construct platform context from session token only (never from body trust)."""

    def __init__(self, platform=None):
        self.platform = platform or default_platform()

    def bind(
        self,
        *,
        token: str,
        tool_id: str,
        arguments: dict | None = None,
        project_id: str = "",
        mission_id: str = "",
        approval_id: str = "",
        run_id: str = "",
    ) -> BoundAgentCall:
        if not token:
            raise PlatformContextError("ANONYMOUS_PROHIBITED", "token required")
        # Ignore any client-supplied user/org/role — only token is trusted
        ctx = self.platform.require_context(
            token,
            project_id=project_id,
            mission_id=mission_id,
            run_id=run_id,
        )
        ctx.require_permission(PlatformPermission.RUNTIME_EXECUTE)
        # owner safety: execution disable
        sec = self.platform.store.get_config("security", {}) or {}
        if sec.get("execution_enabled") is False:
            raise PlatformContextError("EXECUTION_DISABLED", "owner disabled execution")
        return BoundAgentCall(
            ctx=ctx,
            tool_id=tool_id,
            arguments=dict(arguments or {}),
            approval_id=approval_id,
        )

    def execute_bound(self, call: BoundAgentCall):
        return self.platform.execute_tool(
            call.ctx,
            tool_id=call.tool_id,
            arguments=call.arguments,
            approval_id=call.approval_id,
        )

    def execute(
        self,
        *,
        token: str,
        tool_id: str,
        arguments: dict | None = None,
        project_id: str = "",
        mission_id: str = "",
        approval_id: str = "",
        run_id: str = "",
    ):
        call = self.bind(
            token=token,
            tool_id=tool_id,
            arguments=arguments,
            project_id=project_id,
            mission_id=mission_id,
            approval_id=approval_id,
            run_id=run_id,
        )
        return self.execute_bound(call)


def inventory_agent_callers() -> list[dict[str, Any]]:
    """Static inventory of known user-originated tool dispatch surfaces."""
    return [
        {
            "caller": "saathi.agent.AgentExecutor",
            "entry": "execute_tool (legacy saathi.tools)",
            "platform_bound": False,
            "migration": "M51_PARTIAL — use PlatformAgentBinding for m49 tools",
            "residual": True,
        },
        {
            "caller": "saathi.agent_runtime.gateway_exec",
            "entry": "execute_registered_tool",
            "platform_bound": "optional",
            "migration": "prefer PlatformAgentBinding when session present",
            "residual": True,
        },
        {
            "caller": "saathi.platform.service.PlatformService.execute_tool",
            "entry": "ExecutionGateway",
            "platform_bound": True,
            "migration": "canonical",
            "residual": False,
        },
        {
            "caller": "saathi.platform.agent_binding.PlatformAgentBinding",
            "entry": "execute",
            "platform_bound": True,
            "migration": "canonical agent path",
            "residual": False,
        },
    ]
