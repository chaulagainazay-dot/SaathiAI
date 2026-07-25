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
    agent_id: str = "platform-agent"
    binding_id: str = ""
    binding_version: int = 1
    binding_fingerprint: str = ""


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
        agent_id: str = "platform-agent",
        binding_id: str = "",
        binding_version: int | None = None,
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
        from saathi.platform.bindings import BindingAdministrationService
        from saathi.platform.runtime import binding_fingerprint

        binding = BindingAdministrationService(self.platform).resolve_for_execution(
            ctx,
            binding_id=binding_id,
            agent_id=agent_id,
            binding_version=binding_version,
        )

        return BoundAgentCall(
            ctx=ctx,
            tool_id=tool_id,
            arguments=dict(arguments or {}),
            approval_id=approval_id,
            agent_id=binding.agent_id,
            binding_id=binding.binding_id,
            binding_version=binding.version,
            binding_fingerprint=binding_fingerprint(
                ctx,
                binding.agent_id,
                binding.binding_id,
                binding.version,
            ),
        )

    def execute_bound(self, call: BoundAgentCall, **runtime_options):
        from saathi.platform.runtime import PlatformAgentRuntime

        return PlatformAgentRuntime(self.platform).execute_bound(
            call, **runtime_options
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
        idempotency_key: str = "",
        capability: str = "",
        agent_id: str = "platform-agent",
        binding_id: str = "",
        binding_version: int | None = None,
        timeout_sec: float | None = None,
    ):
        call = self.bind(
            token=token,
            tool_id=tool_id,
            arguments=arguments,
            project_id=project_id,
            mission_id=mission_id,
            approval_id=approval_id,
            run_id=run_id,
            agent_id=agent_id,
            binding_id=binding_id,
            binding_version=binding_version,
        )
        return self.execute_bound(
            call,
            idempotency_key=idempotency_key,
            capability=capability,
            timeout_sec=timeout_sec,
        )


def inventory_agent_callers() -> list[dict[str, Any]]:
    """Static inventory of known user-originated tool dispatch surfaces."""
    return [
        {
            "caller": "saathi.agent_runtime.gateway_exec.AgentExecutor",
            "entry": "request_tool",
            "platform_bound": False,
            "migration": "M52_BLOCKED_UNLESS_PLATFORM_RUNTIME_BOUND",
            "residual": True,
        },
        {
            "caller": "saathi.agent_runtime.gateway_exec",
            "entry": "execute_registered_tool",
            "platform_bound": False,
            "migration": "M52 compatibility shell; direct dispatch removed",
            "residual": True,
        },
        {
            "caller": "saathi.platform.service.PlatformService.execute_tool",
            "entry": "PlatformAgentRuntime compatibility delegate",
            "platform_bound": True,
            "migration": "compatibility-only; removal after callers migrate",
            "residual": True,
        },
        {
            "caller": "saathi.platform.agent_binding.PlatformAgentBinding",
            "entry": "PlatformAgentRuntime.execute_bound",
            "platform_bound": True,
            "migration": "canonical binding path",
            "residual": False,
        },
        {
            "caller": "saathi.platform.runtime.PlatformAgentRuntime",
            "entry": "execute_token / execute_bound",
            "platform_bound": True,
            "migration": "M52 canonical platform-agent path",
            "residual": False,
        },
    ]
