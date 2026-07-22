"""M10 agent registry — config-driven, versioned. Eight production agents.

Permissions are narrowing-only through delegation (enforced in policy.py).
Planner and CEO cannot self-approve.
"""
from __future__ import annotations

from saathi.agent_runtime.models import AgentDefinition, RiskClass

_AGENTS: dict[str, AgentDefinition] = {}


def register(defn: AgentDefinition) -> None:
    _AGENTS[defn.agent_id] = defn


def get(agent_id: str) -> AgentDefinition | None:
    return _AGENTS.get(agent_id)


def all_agents() -> list[AgentDefinition]:
    return list(_AGENTS.values())


def _bootstrap() -> None:
    if _AGENTS:
        return
    defs = [
        AgentDefinition(
            agent_id="planner", name="Planner", role="planning",
            description="Decompose goals into bounded, dependency-aware plans.",
            capabilities=["decompose", "estimate_risk", "select_agents"],
            allowed_tools=["memory.search"], memory_scopes=["project:", "business:"],
            risk_ceiling=RiskClass.READ_ONLY, can_self_approve=False,
            can_delegate_to=["researcher", "architect", "builder", "reviewer", "writer"],
            output_contract="planner", max_steps=6,
            verification=["output_schema"]),
        AgentDefinition(
            agent_id="researcher", name="Researcher", role="research",
            description="Retrieve knowledge, inspect files, cite evidence.",
            capabilities=["retrieve", "compare", "cite"],
            allowed_tools=["memory.search", "knowledge.read", "file.read"],
            memory_scopes=["project:", "business:", "conversation:"],
            risk_ceiling=RiskClass.READ_ONLY, output_contract="generic",
            verification=["citations_present"]),
        AgentDefinition(
            agent_id="architect", name="Architect", role="architecture",
            description="Design systems, interfaces, schemas, migrations.",
            capabilities=["design", "review_arch"],
            allowed_tools=["memory.search", "file.read"],
            memory_scopes=["project:", "business:"],
            risk_ceiling=RiskClass.READ_ONLY, output_contract="generic"),
        AgentDefinition(
            agent_id="builder", name="Builder", role="coding",
            description="Implement approved changes, generate tests, validate.",
            capabilities=["edit", "test", "validate"],
            allowed_tools=["file.read", "file.write", "test.run"],
            denied_tools=["git.push", "deploy", "gmail.send"],
            memory_scopes=["project:"],
            risk_ceiling=RiskClass.LOCAL_REVERSIBLE, output_contract="builder",
            can_delegate_to=["reviewer"], verification=["tests_pass"]),
        AgentDefinition(
            agent_id="reviewer", name="Reviewer", role="review",
            description="Independently review plans, code, tests, security.",
            capabilities=["review", "challenge", "verify_quality"],
            allowed_tools=["file.read", "memory.search"],
            memory_scopes=["project:"],
            risk_ceiling=RiskClass.READ_ONLY, output_contract="reviewer",
            verification=["output_schema"]),
        AgentDefinition(
            agent_id="executor", name="Executor", role="execution",
            description="Execute approved gateway operations; stop on violations.",
            capabilities=["execute"],
            allowed_tools=["local-llm-inference", "video-generation"],
            memory_scopes=["project:"],
            risk_ceiling=RiskClass.EXTERNAL_SIDE_EFFECT, requires_approval=True,
            output_contract="generic"),
        AgentDefinition(
            agent_id="writer", name="Writer", role="writing",
            description="Docs, reports, release notes, specs.",
            capabilities=["write", "summarize"],
            allowed_tools=["memory.search", "file.read"],
            memory_scopes=["project:", "conversation:"],
            risk_ceiling=RiskClass.READ_ONLY, output_contract="generic"),
        AgentDefinition(
            agent_id="ceo", name="CEO Agent", role="business",
            description="Business prioritization, KPI impact, resource allocation.",
            capabilities=["prioritize", "assess_risk_reward"],
            allowed_tools=["memory.search"], memory_scopes=["business:", "project:"],
            risk_ceiling=RiskClass.READ_ONLY, can_self_approve=False,
            can_delegate_to=["researcher", "planner"], output_contract="generic"),
    ]
    for d in defs:
        register(d)


_bootstrap()
