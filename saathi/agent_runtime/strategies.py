"""M10 orchestration strategies — config-driven agent pipelines.

Each strategy is a list of (agent, depends_on_prev) steps compiled into a task
DAG. Simple requests use SINGLE_AGENT; multi-agent activates only when selected
or justified by the objective.
"""
from __future__ import annotations

from saathi.agent_runtime.test_authority import strategy_allowed

STRATEGIES: dict[str, list[str]] = {
    "single": ["planner"],  # replaced by chosen single agent at runtime
    "build": ["planner", "builder", "reviewer"],
    "architect_build": ["planner", "researcher", "architect", "builder", "reviewer"],
    "document": ["researcher", "writer", "reviewer"],
    "business": ["ceo", "researcher", "planner"],
    "broad_research": ["planner", "researcher", "researcher", "writer"],  # fan-out
    # Certification fixture (Phase 5F). Reachable ONLY by an explicit
    # `requested` strategy AND with SAATHI_TEST_RUN_HOLD_MS set; the
    # objective heuristics below never return it.
    "test_hold": ["planner"],
    # Certification fixture (Phase 7). Same double gate: reachable ONLY by an
    # explicit `requested` strategy AND with SAATHI_TEST_RUN_FAIL set.
    "test_fail": ["planner"],
    # Certification fixture (Phase 10). The only strategy containing `executor`,
    # the one agent that declares requires_approval, so it is the only way to
    # reach the orchestrator's real approval gate. Gated at selection by
    # SAATHI_TEST_AUTHORITY, because running it creates authority state.
    "test_approval": ["executor"],
}


def choose_strategy(objective: str, *, requested: str = "") -> str:
    # A gated fixture is honoured only in a process that armed it. Disarmed, the
    # request falls through to the heuristics below -- which never return one --
    # so a production process cannot reach the approval gate by accident.
    if requested in STRATEGIES and strategy_allowed(requested):
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
