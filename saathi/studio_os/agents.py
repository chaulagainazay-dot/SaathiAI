"""M13 Studio agent roles — registered INTO the existing M10 registry.

No new agent system: these are M10 AgentDefinitions with Studio capabilities,
gateway-only tools, and narrow risk ceilings. Idempotent registration.
"""
from __future__ import annotations

from saathi.agent_runtime.models import AgentDefinition, RiskClass
from saathi.agent_runtime import registry


def register_studio_agents() -> None:
    if registry.get("script_writer"):
        return  # already registered
    defs = [
        AgentDefinition(agent_id="content_strategist", name="Content Strategist",
                        role="business", description="Audience + platform strategy.",
                        allowed_tools=["memory.search"], memory_scopes=["project:", "business:"],
                        risk_ceiling=RiskClass.READ_ONLY, output_contract="generic"),
        AgentDefinition(agent_id="script_writer", name="Script Writer", role="writing",
                        description="Write structured scripts (hook/sections/CTA).",
                        allowed_tools=["memory.search", "file.read"],
                        memory_scopes=["project:"], risk_ceiling=RiskClass.READ_ONLY,
                        output_contract="generic", verification=["output_schema"]),
        AgentDefinition(agent_id="storyboard_agent", name="Storyboard Agent", role="architecture",
                        description="Plan scenes: shot/visual/timing.",
                        allowed_tools=["memory.search"], memory_scopes=["project:"],
                        risk_ceiling=RiskClass.READ_ONLY, output_contract="generic"),
        AgentDefinition(agent_id="visual_director", name="Visual Director", role="review",
                        description="Brand/visual consistency review.",
                        allowed_tools=["file.read"], memory_scopes=["project:"],
                        risk_ceiling=RiskClass.READ_ONLY, output_contract="reviewer"),
        AgentDefinition(agent_id="seo_agent", name="SEO Agent", role="writing",
                        description="Platform SEO metadata.",
                        allowed_tools=["memory.search"], memory_scopes=["project:"],
                        risk_ceiling=RiskClass.READ_ONLY, output_contract="generic"),
        AgentDefinition(agent_id="brand_reviewer", name="Brand Reviewer", role="review",
                        description="Independent brand/compliance review.",
                        allowed_tools=["file.read"], memory_scopes=["project:"],
                        risk_ceiling=RiskClass.READ_ONLY, output_contract="reviewer",
                        verification=["output_schema"]),
        AgentDefinition(agent_id="publisher", name="Publisher", role="execution",
                        description="Publish approved content (external side effect).",
                        allowed_tools=["publish"], denied_tools=["deploy"],
                        memory_scopes=["project:"],
                        risk_ceiling=RiskClass.EXTERNAL_SIDE_EFFECT,
                        requires_approval=True, output_contract="generic"),
    ]
    for d in defs:
        registry.register(d)


register_studio_agents()
