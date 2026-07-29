"""Bounded mission-agent roles over the canonical platform execution runtime."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from saathi.platform.mission_runtime.models import AgentType


@dataclass(frozen=True)
class BoundedPlatformAgent:
    """An orchestration role, never an identity or execution authority.

    Every role delegates its one task dispatch to PlatformAgentRuntime. Platform
    binding policy, RBAC, approvals, tool registration, idempotency, and the
    ExecutionGateway remain authoritative.
    """

    agent_type: AgentType
    responsibility: str

    def dispatch(
        self,
        runtime,
        ctx,
        task: dict[str, Any],
        *,
        idempotency_key: str,
        timeout_sec: float | None,
    ):
        return runtime.execute_context(
            ctx,
            tool_id=task["tool_id"],
            arguments=dict(task["arguments"]),
            approval_id=task["approval_id"],
            idempotency_key=idempotency_key,
            capability=task["capability"],
            timeout_sec=timeout_sec,
        )


class MissionAgentRegistry:
    """Fixed role directory; registration confers no tool permission."""

    _RESPONSIBILITIES = {
        AgentType.PLANNER: "decompose bounded goals and declare dependencies",
        AgentType.ARCHITECT: "review architecture and reuse platform authorities",
        AgentType.RESEARCHER: "gather authorized context and summarize evidence",
        AgentType.IMPLEMENTER: "make the smallest complete implementation change",
        AgentType.REVIEWER: "perform independent evidence-backed review",
        AgentType.TEST: "run deterministic verification through registered tools",
        AgentType.BROWSER: "certify browser behavior through governed browser tools",
        AgentType.SECURITY: "review security, isolation, and policy boundaries",
        AgentType.DOCUMENTATION: "update authoritative project documentation",
        AgentType.CERTIFICATION: "issue a final verdict only from recorded evidence",
        AgentType.OPERATOR: "operate mission controls under human authority",
        AgentType.DOMAIN: "apply domain templates within existing authorities",
    }

    def __init__(self) -> None:
        self._agents = {
            agent_type.value: BoundedPlatformAgent(agent_type, responsibility)
            for agent_type, responsibility in self._RESPONSIBILITIES.items()
        }

    def get(self, agent_type: str) -> BoundedPlatformAgent:
        try:
            return self._agents[AgentType(agent_type).value]
        except (KeyError, ValueError) as exc:
            raise ValueError(f"unknown bounded mission agent {agent_type!r}") from exc

    def describe(self) -> list[dict[str, str]]:
        return [
            {
                "agent_type": agent.agent_type.value,
                "responsibility": agent.responsibility,
                "execution_authority": "PlatformAgentRuntime",
            }
            for agent in self._agents.values()
        ]
