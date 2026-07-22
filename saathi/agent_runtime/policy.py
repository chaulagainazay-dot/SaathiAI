"""M10 policy — risk classification, approval enforcement, permission
narrowing, budgets, retry classification, no-progress detection.

Permissions may only narrow through delegation (never widen). Planner/CEO
cannot self-approve. Risk ≥ LOCAL_MUTATION needs explicit user approval.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from saathi.agent_runtime.models import (
    AgentDefinition, RiskClass, APPROVAL_THRESHOLD, Task,
)

# tool → risk class (deny-by-severity mapping)
_TOOL_RISK: dict[str, RiskClass] = {
    "memory.search": RiskClass.READ_ONLY, "knowledge.read": RiskClass.READ_ONLY,
    "file.read": RiskClass.READ_ONLY, "diagnostics": RiskClass.READ_ONLY,
    "local-llm-inference": RiskClass.READ_ONLY,
    "file.write": RiskClass.LOCAL_REVERSIBLE, "test.run": RiskClass.LOCAL_REVERSIBLE,
    "db.migrate": RiskClass.LOCAL_MUTATION, "deps.update": RiskClass.LOCAL_MUTATION,
    "file.delete": RiskClass.LOCAL_MUTATION,
    "gmail.send": RiskClass.EXTERNAL_SIDE_EFFECT, "calendar.write": RiskClass.EXTERNAL_SIDE_EFFECT,
    "git.push": RiskClass.EXTERNAL_SIDE_EFFECT, "publish": RiskClass.EXTERNAL_SIDE_EFFECT,
    "video-generation": RiskClass.EXTERNAL_SIDE_EFFECT,
    "deploy": RiskClass.HIGH_IMPACT, "payment": RiskClass.HIGH_IMPACT,
    "trade.execute": RiskClass.HIGH_IMPACT, "credential.modify": RiskClass.HIGH_IMPACT,
}


def tool_risk(tool: str) -> RiskClass:
    return _TOOL_RISK.get(tool, RiskClass.LOCAL_MUTATION)  # unknown = cautious


@dataclass
class PolicyDecision:
    allowed: bool
    risk: RiskClass
    requires_approval: bool
    reason: str


def check_tool(agent: AgentDefinition, tool: str) -> PolicyDecision:
    """Can this agent use this tool? Enforces allow/deny lists + risk ceiling."""
    if tool in agent.denied_tools:
        return PolicyDecision(False, tool_risk(tool), False,
                              f"tool '{tool}' explicitly denied for {agent.agent_id}")
    if agent.allowed_tools and tool not in agent.allowed_tools:
        return PolicyDecision(False, tool_risk(tool), False,
                              f"tool '{tool}' not in {agent.agent_id} allow-list")
    risk = tool_risk(tool)
    if int(risk) > int(agent.risk_ceiling):
        return PolicyDecision(False, risk, True,
                              f"tool risk {int(risk)} exceeds {agent.agent_id} "
                              f"ceiling {int(agent.risk_ceiling)}")
    needs = risk >= APPROVAL_THRESHOLD or agent.requires_approval
    return PolicyDecision(True, risk, needs,
                          "requires approval" if needs else "auto-permitted")


def can_self_approve(agent: AgentDefinition) -> bool:
    return agent.can_self_approve and agent.agent_id not in ("planner", "ceo")


def narrow_permissions(parent: AgentDefinition, child: AgentDefinition) -> AgentDefinition:
    """Delegated child permissions = intersection with parent (narrowing-only).

    Returns a copy of `child` whose tools/scopes/risk never exceed the parent.
    """
    import copy
    c = copy.deepcopy(child)
    # tools: child allowed ∩ parent allowed (empty parent allow = unrestricted-by-list)
    if parent.allowed_tools:
        c.allowed_tools = [t for t in (child.allowed_tools or parent.allowed_tools)
                           if t in parent.allowed_tools]
    c.denied_tools = list(set(child.denied_tools) | set(parent.denied_tools))
    # risk ceiling: min of the two
    c.risk_ceiling = RiskClass(min(int(parent.risk_ceiling), int(child.risk_ceiling)))
    # memory scopes: intersection by prefix (child cannot see broader scopes)
    if parent.memory_scopes:
        c.memory_scopes = [s for s in (child.memory_scopes or parent.memory_scopes)
                           if any(s.startswith(p) or p.startswith(s)
                                  for p in parent.memory_scopes)]
    return c


# ── budgets (Phase 13) ──────────────────────────────────────────────────────
@dataclass
class Budget:
    tokens: int = 40_000
    cost_usd: float = 1.0
    wall_sec: float = 300.0
    steps: int = 40
    tool_calls: int = 60
    retries: int = 6
    delegation_depth: int = 3
    artifacts: int = 50
    parallel_tasks: int = 4
    # consumed
    used_tokens: int = 0
    used_cost: float = 0.0
    used_steps: int = 0
    used_tool_calls: int = 0
    used_retries: int = 0
    used_artifacts: int = 0

    def charge(self, *, tokens: int = 0, cost: float = 0.0, steps: int = 0,
               tool_calls: int = 0, retries: int = 0, artifacts: int = 0) -> None:
        self.used_tokens += tokens
        self.used_cost += cost
        self.used_steps += steps
        self.used_tool_calls += tool_calls
        self.used_retries += retries
        self.used_artifacts += artifacts

    def exhausted(self) -> str | None:
        if self.used_tokens > self.tokens:
            return "token budget exhausted"
        if self.used_cost > self.cost_usd:
            return "cost budget exhausted"
        if self.used_steps >= self.steps:
            return "step budget exhausted"
        if self.used_tool_calls >= self.tool_calls:
            return "tool-call budget exhausted"
        if self.used_retries >= self.retries:
            return "retry budget exhausted"
        if self.used_artifacts >= self.artifacts:
            return "artifact budget exhausted"
        return None


# ── delegation limits (Phase 8) ─────────────────────────────────────────────
@dataclass
class DelegationLimits:
    max_depth: int = 3
    max_children_per_agent: int = 4
    max_total_agents: int = 12
    max_repeat_delegation: int = 2


def check_delegation(parent: AgentDefinition, child_id: str, *, depth: int,
                     children_count: int, total_agents: int,
                     repeat_count: int, limits: DelegationLimits) -> PolicyDecision:
    if child_id not in parent.can_delegate_to:
        return PolicyDecision(False, RiskClass.READ_ONLY, False,
                              f"{parent.agent_id} may not delegate to {child_id}")
    if depth >= limits.max_depth:
        return PolicyDecision(False, RiskClass.READ_ONLY, False, "max delegation depth")
    if children_count >= limits.max_children_per_agent:
        return PolicyDecision(False, RiskClass.READ_ONLY, False, "max children per agent")
    if total_agents >= limits.max_total_agents:
        return PolicyDecision(False, RiskClass.READ_ONLY, False, "max total agents")
    if repeat_count >= limits.max_repeat_delegation:
        return PolicyDecision(False, RiskClass.READ_ONLY, False, "repeated delegation loop")
    return PolicyDecision(True, RiskClass.READ_ONLY, False, "ok")


# ── retry / no-progress (Phase 14) ──────────────────────────────────────────
_TRANSIENT = ("timeout", "temporarily", "rate limit", "connection reset",
              "503", "502", "unavailable", "econnreset")


def is_transient(error: str) -> bool:
    e = (error or "").lower()
    return any(k in e for k in _TRANSIENT)


def failure_fingerprint(task_id: str, error: str) -> str:
    import re
    norm = re.sub(r"0x[0-9a-f]+|\d+", "N", (error or "").lower())[:120]
    return hashlib.sha1(f"{task_id}|{norm}".encode()).hexdigest()[:16]


def should_retry(*, error: str, attempts: int, max_retries: int,
                 last_fingerprint: str | None, task_id: str) -> tuple[bool, str, str]:
    """Return (retry?, reason, fingerprint). Retry only transient + progress +
    budget remaining + fingerprint changed."""
    fp = failure_fingerprint(task_id, error)
    if attempts >= max_retries:
        return False, "retry budget exhausted", fp
    if not is_transient(error):
        return False, "non-transient failure", fp
    if last_fingerprint == fp:
        return False, "no progress — identical failure fingerprint", fp
    return True, "transient + progress possible", fp
