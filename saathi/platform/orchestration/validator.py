"""Deterministic plan validation before any execution."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from .models import (
    MAX_GRAPH_DEPTH,
    MAX_GRAPH_WIDTH,
    MAX_PLAN_NODES,
    MAX_RETRIES_CEILING,
    ApprovalRequirement,
    PlanValidationResult,
    READONLY_ANALYSIS_TOOL,
)
from .roles import FORBIDDEN_ALL, AgentRoleRegistry

# Tools that may appear in orchestration plans without external side effects
SAFE_TOOL_PREFIXES = (
    "m49.echo",
    "m49.",
    "platform.",
    "saathi.orchestration.",
)


class PlanValidator:
    def __init__(self, roles: AgentRoleRegistry | None = None):
        self.roles = roles or AgentRoleRegistry()

    def validate(self, plan: dict[str, Any]) -> PlanValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        if not isinstance(plan, dict):
            return PlanValidationResult(ok=False, errors=["plan must be an object"])

        objective = str(plan.get("objective") or "").strip()
        if not objective:
            errors.append("objective is required")

        if plan.get("production_authorized") is True:
            errors.append("plans cannot claim production_authorized")
        if plan.get("paid_providers") is True:
            errors.append("paid providers are not permitted")
        if plan.get("credential_requirements") is True:
            errors.append("credential requirements are not satisfiable")
        if plan.get("trading_execution") is True:
            errors.append("trading execution is prohibited")

        tasks = list(self._iter_tasks(plan))
        all_nodes = self._count_all(plan)
        if all_nodes > MAX_PLAN_NODES:
            errors.append(f"plan node count {all_nodes} exceeds {MAX_PLAN_NODES}")
        if not tasks:
            errors.append("plan requires at least one task")

        ids = [str(t.get("id") or "") for t in tasks]
        if any(not i for i in ids):
            errors.append("every task requires a stable id")
        if len(ids) != len(set(ids)):
            errors.append("duplicate task ids")

        id_set = set(ids)
        # Dependency graph
        edges: list[tuple[str, str]] = []
        indeg: dict[str, int] = {i: 0 for i in id_set}
        children: dict[str, list[str]] = defaultdict(list)
        for t in tasks:
            tid = str(t.get("id"))
            deps = t.get("depends_on") or []
            if not isinstance(deps, list):
                errors.append(f"task {tid} depends_on must be a list")
                continue
            for d in deps:
                ds = str(d)
                if ds not in id_set:
                    errors.append(f"task {tid} depends on missing node {ds}")
                    continue
                edges.append((ds, tid))
                indeg[tid] = indeg.get(tid, 0) + 1
                children[ds].append(tid)

        # Cycle detection
        if self._has_cycle(id_set, children, indeg.copy()):
            errors.append("dependency cycle detected")

        # Orphans among non-root: allowed; warn only if isolated subgraph for multi-task
        approval_gates = 0
        blocked = 0
        width_at_depth: dict[int, int] = defaultdict(int)
        depths = self._depths(id_set, edges)

        for t in tasks:
            tid = str(t.get("id"))
            agent = str(t.get("agent_type") or "")
            if agent not in self.roles.known_agent_types():
                errors.append(f"unsupported role {agent!r} on task {tid}")
            else:
                policy = self.roles.get_by_agent_type(agent)
                # Implementer cannot self-certify
                if agent == "ImplementerAgent" and policy.can_self_certify:
                    errors.append("implementer cannot self-certify")
                # Forbidden capability requests
                requested = t.get("capabilities") or t.get("requested_capabilities") or []
                if isinstance(requested, list):
                    for cap in requested:
                        if str(cap) in FORBIDDEN_ALL:
                            errors.append(
                                f"task {tid} requests forbidden capability {cap}"
                            )
                forb = t.get("forbidden_capabilities") or []
                # tool checks
            tool = str(t.get("tool_id") or "")
            if not tool:
                errors.append(f"task {tid} missing tool_id (no direct model execution)")
            elif tool.startswith("shell") or "subprocess" in tool:
                errors.append(f"task {tid} uses unsafe tool {tool}")
            elif not any(tool.startswith(p) for p in SAFE_TOOL_PREFIXES):
                # unknown tools require approval classification
                warnings.append(f"task {tid} tool {tool} is non-default; requires gateway registration")

            # Direct tool execution markers in arguments
            args = t.get("arguments") if isinstance(t.get("arguments"), dict) else {}
            for key in ("shell", "subprocess", "execute_raw", "bypass_gateway"):
                if args.get(key):
                    errors.append(f"task {tid} arguments request forbidden {key}")

            retries = int(t.get("max_retries") or 0)
            if retries > MAX_RETRIES_CEILING:
                errors.append(f"task {tid} max_retries exceeds {MAX_RETRIES_CEILING}")
            if retries < 0:
                errors.append(f"task {tid} max_retries cannot be negative")

            ar = str(t.get("approval_requirement") or ApprovalRequirement.NO_APPROVAL_REQUIRED.value)
            try:
                ar_enum = ApprovalRequirement(ar)
            except ValueError:
                errors.append(f"task {tid} invalid approval_requirement {ar}")
                ar_enum = ApprovalRequirement.NO_APPROVAL_REQUIRED
            if ar_enum != ApprovalRequirement.NO_APPROVAL_REQUIRED:
                approval_gates += 1
            if ar_enum == ApprovalRequirement.BLOCKED_BY_POLICY:
                blocked += 1

            if not t.get("title"):
                errors.append(f"task {tid} missing title")
            # Completion criteria / evidence
            if t.get("requires_review") and not (t.get("verification") or []):
                warnings.append(f"task {tid} requires review but has empty verification list")

            depth = depths.get(tid, 0)
            width_at_depth[depth] += 1
            if depth > MAX_GRAPH_DEPTH:
                errors.append(f"graph depth exceeds {MAX_GRAPH_DEPTH}")

        for d, w in width_at_depth.items():
            if w > MAX_GRAPH_WIDTH:
                errors.append(f"graph width at depth {d} exceeds {MAX_GRAPH_WIDTH}")

        # Separation of duties: if implementer present, certification/review must not be same agent id on same node
        implementers = [t for t in tasks if t.get("agent_type") == "ImplementerAgent"]
        certifiers = [t for t in tasks if t.get("agent_type") == "CertificationAgent"]
        if implementers and not (
            any(t.get("agent_type") == "ReviewerAgent" for t in tasks)
            or any(t.get("agent_type") == "CertificationAgent" for t in tasks)
            or any(t.get("requires_review") for t in implementers)
        ):
            warnings.append(
                "implementation tasks without independent review or certification gate"
            )
        if implementers and certifiers:
            for c in certifiers:
                if c.get("id") in {i.get("id") for i in implementers}:
                    errors.append("implementer cannot be certification node")

        # Impossible ordering already covered by cycles
        # Unbounded concurrency
        max_parallel = int(plan.get("max_parallel_tasks") or 1)
        if max_parallel > 8:
            errors.append("max_parallel_tasks exceeds 8")
        if max_parallel < 1:
            errors.append("max_parallel_tasks must be >= 1")

        return PlanValidationResult(
            ok=not errors,
            errors=errors[:50],
            warnings=warnings[:50],
            node_count=all_nodes,
            dependency_count=len(edges),
            approval_gates=approval_gates,
            blocked_nodes=blocked,
        )

    def _iter_tasks(self, plan: dict[str, Any]):
        for goal in plan.get("goals") or []:
            if not isinstance(goal, dict):
                continue
            for phase in goal.get("phases") or []:
                if not isinstance(phase, dict):
                    continue
                for ms in phase.get("milestones") or []:
                    if not isinstance(ms, dict):
                        continue
                    for task in ms.get("tasks") or []:
                        if isinstance(task, dict):
                            yield task
                            for sub in task.get("subtasks") or []:
                                if isinstance(sub, dict):
                                    yield sub

    def _count_all(self, plan: dict[str, Any]) -> int:
        n = 0
        for goal in plan.get("goals") or []:
            n += 1
            for phase in (goal or {}).get("phases") or []:
                n += 1
                for ms in (phase or {}).get("milestones") or []:
                    n += 1
                    for task in (ms or {}).get("tasks") or []:
                        n += 1
                        n += len((task or {}).get("subtasks") or [])
        return n

    def _has_cycle(
        self,
        nodes: set[str],
        children: dict[str, list[str]],
        indeg: dict[str, int],
    ) -> bool:
        q = deque([n for n in nodes if indeg.get(n, 0) == 0])
        seen = 0
        while q:
            n = q.popleft()
            seen += 1
            for c in children.get(n, []):
                indeg[c] -= 1
                if indeg[c] == 0:
                    q.append(c)
        return seen != len(nodes)

    def _depths(
        self, nodes: set[str], edges: list[tuple[str, str]]
    ) -> dict[str, int]:
        children: dict[str, list[str]] = defaultdict(list)
        indeg = {n: 0 for n in nodes}
        for a, b in edges:
            children[a].append(b)
            indeg[b] += 1
        depth = {n: 0 for n in nodes}
        q = deque([n for n in nodes if indeg[n] == 0])
        while q:
            n = q.popleft()
            for c in children[n]:
                depth[c] = max(depth[c], depth[n] + 1)
                indeg[c] -= 1
                if indeg[c] == 0:
                    q.append(c)
        return depth
