"""M10 orchestration strategies — config-driven agent pipelines.

Each strategy is a list of (agent, depends_on_prev) steps compiled into a task
DAG. Simple requests use SINGLE_AGENT; multi-agent activates only when selected
or justified by the objective.
"""
from __future__ import annotations

STRATEGIES: dict[str, list[str]] = {
    "single": ["planner"],  # replaced by chosen single agent at runtime
    "build": ["planner", "builder", "reviewer"],
    "architect_build": ["planner", "researcher", "architect", "builder", "reviewer"],
    "document": ["researcher", "writer", "reviewer"],
    "business": ["ceo", "researcher", "planner"],
    "broad_research": ["planner", "researcher", "researcher", "writer"],  # fan-out
}


def choose_strategy(objective: str, *, requested: str = "") -> str:
    if requested in STRATEGIES:
        return requested
    o = objective.lower()
    if any(k in o for k in ("architecture", "design the system", "schema", "migration")):
        return "architect_build"
    if any(k in o for k in ("document", "report", "write ", "release notes", "spec")):
        return "document"
    if any(k in o for k in ("prioritize", "business", "kpi", "revenue", "roi")):
        return "business"
    if any(k in o for k in ("implement", "build", "code", "fix", "add ", "refactor")):
        return "build"
    if any(k in o for k in ("research", "compare", "investigate", "gather")):
        return "broad_research"
    return "build"
