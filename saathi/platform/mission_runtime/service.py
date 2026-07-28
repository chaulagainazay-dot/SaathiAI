"""Authoritative mission hierarchy, DAG, evidence, checkpoint, and dashboard service."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any
import re

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.models import PlatformPermission
from saathi.platform.mission_runtime.models import (
    AgentType,
    EvidenceStatus,
    MISSION_TERMINAL,
    MissionRuntimeState,
    NodeType,
    ResourceBudget,
    TASK_TERMINAL,
    TaskStatus,
    reject_secret_fields,
    snapshot_hash,
)
from saathi.platform.mission_runtime.repository import MissionRuntimeRepository


MAX_GOALS = 20
MAX_PHASES = 50
MAX_MILESTONES = 100
MAX_TASKS = 300
MAX_NODES = 500
ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
CERTIFICATION_VERDICTS = frozenset(
    {"MISSION_COMPLETE", "MISSION_RUNTIME_COMPLETE"}
)


def _text(value: Any, *, name: str, maximum: int, required: bool = True) -> str:
    out = str(value or "").strip()
    if required and not out:
        raise ValueError(f"{name} is required")
    if len(out) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    return out


def _int(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= out <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return out


def _number(value: Any, *, name: str, minimum: float, maximum: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not minimum <= out <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return out


class MissionRuntimeService:
    """Tenant-scoped mission control plane.

    Planning and state transitions are deterministic. Tool execution is added by
    the M70 dispatcher and remains owned by PlatformAgentRuntime.
    """

    def __init__(self, platform=None):
        if platform is None:
            from saathi.platform.service import default_platform

            platform = default_platform()
        self.platform = platform
        self.store = platform.store
        self.repo = MissionRuntimeRepository(self.store)

    # ------------------------------------------------------------------ scope
    def _mission(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        *,
        permission: PlatformPermission = PlatformPermission.MISSION_READ,
    ):
        ctx.require_permission(permission)
        mission = self.store.get_mission(mission_id)
        if (
            not mission
            or mission.org_id != ctx.org_id
            or mission.workspace_id != ctx.workspace_id
        ):
            raise PlatformContextError("NOT_FOUND", "mission is not accessible")
        if ctx.project_id and mission.project_id != ctx.project_id:
            raise PlatformContextError("PROJECT_ISOLATION", "mission project mismatch")
        return mission

    def _runtime(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        *,
        permission: PlatformPermission = PlatformPermission.MISSION_READ,
    ) -> dict[str, Any]:
        self._mission(ctx, mission_id, permission=permission)
        runtime = self.repo.get_runtime(mission_id)
        if not runtime:
            raise PlatformContextError("NOT_FOUND", "mission runtime is not planned")
        return runtime

    def _audit(
        self,
        event: str,
        ctx: PlatformExecutionContext,
        mission_id: str,
        *,
        outcome: str = "ok",
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.platform._audit(
            event,
            ctx,
            mission_id=mission_id,
            project_id=ctx.project_id,
            outcome=outcome,
            detail=detail or {},
        )

    # --------------------------------------------------------------- planning
    def plan(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate and persist Mission→Goal→Phase→Milestone→Task→Subtask."""

        mission = self._mission(
            ctx, mission_id, permission=PlatformPermission.MISSION_WRITE
        )
        try:
            reject_secret_fields(definition)
            objective = _text(
                definition.get("objective"), name="objective", maximum=4000
            )
            max_parallel = _int(
                definition.get("max_parallel_tasks", 1),
                name="max_parallel_tasks",
                minimum=1,
                maximum=8,
            )
            budget = ResourceBudget.from_dict(definition.get("budget"))
            nodes, dependencies = self._flatten_plan(mission_id, definition)
            self._validate_dag(nodes, dependencies)
        except ValueError as exc:
            raise PlatformContextError("VALIDATION_FAILED", str(exc)) from exc

        now = self.store._now()
        try:
            runtime = self.repo.replace_plan(
                runtime={
                    "mission_id": mission_id,
                    "org_id": ctx.org_id,
                    "workspace_id": ctx.workspace_id,
                    "project_id": mission.project_id,
                    "owner_id": mission.owner_id,
                    "objective": objective,
                    "max_parallel_tasks": max_parallel,
                    "budget": budget.to_dict(),
                    "updated_at": now,
                },
                nodes=nodes,
                dependencies=dependencies,
            )
        except ValueError as exc:
            raise PlatformContextError("INVALID_STATE", str(exc)) from exc
        self._refresh_ready(mission_id)
        checkpoint = self.create_checkpoint(
            ctx, mission_id, created_by=AgentType.PLANNER.value
        )
        self.repo.add_decision(
            mission_id=mission_id,
            decision_type="PLAN_ACCEPTED",
            outcome="PLANNED",
            reason="hierarchy and acyclic dependency graph validated",
            policy="mission-runtime.plan.v1",
            actor=ctx.requested_by(),
        )
        self._audit(
            "mission_runtime.planned",
            ctx,
            mission_id,
            detail={
                "node_count": len(nodes),
                "dependency_count": len(dependencies),
                "max_parallel_tasks": max_parallel,
                "checkpoint_id": checkpoint["checkpoint_id"],
            },
        )
        return self.get(ctx, mission_id)

    def _flatten_plan(
        self, mission_id: str, definition: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
        goals = definition.get("goals")
        if not isinstance(goals, list) or not goals:
            raise ValueError("at least one goal is required")
        if len(goals) > MAX_GOALS:
            raise ValueError(f"goal count exceeds {MAX_GOALS}")

        nodes: list[dict[str, Any]] = []
        requested_to_node: dict[str, str] = {}
        pending_dependencies: list[tuple[str, list[str]]] = []
        counts = defaultdict(int)
        position = 0

        def node_id(node_type: NodeType, raw: dict[str, Any], path: str) -> str:
            requested = str(raw.get("id") or "").strip()
            if requested and not ID_RE.fullmatch(requested):
                raise ValueError(f"invalid node id {requested!r}")
            identity = requested or path
            digest = snapshot_hash(
                {"mission_id": mission_id, "node_type": node_type.value, "id": identity}
            )[:20]
            actual = f"mn_{digest}"
            if requested:
                if requested in requested_to_node:
                    raise ValueError(f"duplicate node id {requested}")
                requested_to_node[requested] = actual
            return actual

        def append_node(
            node_type: NodeType,
            raw: dict[str, Any],
            parent_id: str,
            path: str,
        ) -> str:
            nonlocal position
            if not isinstance(raw, dict):
                raise ValueError(f"{node_type.value.lower()} must be an object")
            counts[node_type.value] += 1
            position += 1
            title = _text(
                raw.get("title") or raw.get("name"),
                name=f"{node_type.value.lower()} title",
                maximum=240,
            )
            actual = node_id(node_type, raw, path)
            is_task = node_type in {NodeType.TASK, NodeType.SUBTASK}
            agent_type = ""
            if is_task:
                try:
                    agent_type = AgentType(
                        raw.get("agent_type") or AgentType.IMPLEMENTER.value
                    ).value
                except ValueError as exc:
                    raise ValueError(
                        f"unknown agent_type {raw.get('agent_type')!r}"
                    ) from exc
            arguments = raw.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise ValueError(f"arguments for {title} must be an object")
            verification = raw.get("verification") or []
            if not isinstance(verification, list) or len(verification) > 20:
                raise ValueError(f"verification for {title} must be a list of <=20")
            verification = [
                _text(item, name="verification check", maximum=120)
                for item in verification
            ]
            node = {
                "node_id": actual,
                "parent_id": parent_id,
                "node_type": node_type.value,
                "title": title,
                "objective": _text(
                    raw.get("objective", ""),
                    name=f"{title} objective",
                    maximum=2000,
                    required=False,
                ),
                "status": TaskStatus.PENDING.value,
                "priority": _int(
                    raw.get("priority", 50),
                    name=f"{title} priority",
                    minimum=0,
                    maximum=100,
                ),
                "position": position,
                "agent_type": agent_type,
                "tool_id": _text(
                    raw.get("tool_id", ""),
                    name=f"{title} tool_id",
                    maximum=160,
                    required=False,
                )
                if is_task
                else "",
                "capability": _text(
                    raw.get("capability", ""),
                    name=f"{title} capability",
                    maximum=160,
                    required=False,
                )
                if is_task
                else "",
                "arguments": arguments if is_task else {},
                "approval_id": "",
                "estimated_effort": _number(
                    raw.get("estimated_effort", 0),
                    name=f"{title} estimated_effort",
                    minimum=0,
                    maximum=100_000,
                ),
                "token_estimate": _int(
                    raw.get("token_estimate", 0),
                    name=f"{title} token_estimate",
                    minimum=0,
                    maximum=1_000_000,
                ),
                "max_retries": _int(
                    raw.get("max_retries", 1 if is_task else 0),
                    name=f"{title} max_retries",
                    minimum=0,
                    maximum=5,
                ),
                "requires_review": bool(raw.get("requires_review", False)),
                "concurrency_safe": bool(raw.get("concurrency_safe", True)),
                "verification": verification,
            }
            nodes.append(node)
            if is_task:
                deps = raw.get("depends_on") or []
                if not isinstance(deps, list) or len(deps) > MAX_TASKS:
                    raise ValueError(f"depends_on for {title} must be a bounded list")
                pending_dependencies.append(
                    (
                        actual,
                        [
                            _text(dep, name="dependency id", maximum=80)
                            for dep in deps
                        ],
                    )
                )
            return actual

        for gi, goal in enumerate(goals):
            gid = append_node(NodeType.GOAL, goal, "", f"goal:{gi}")
            phases = goal.get("phases") if isinstance(goal, dict) else None
            if not isinstance(phases, list) or not phases:
                raise ValueError("every goal requires at least one phase")
            for pi, phase in enumerate(phases):
                pid = append_node(NodeType.PHASE, phase, gid, f"goal:{gi}/phase:{pi}")
                milestones = phase.get("milestones") if isinstance(phase, dict) else None
                if not isinstance(milestones, list) or not milestones:
                    raise ValueError("every phase requires at least one milestone")
                for mi, milestone in enumerate(milestones):
                    mid = append_node(
                        NodeType.MILESTONE,
                        milestone,
                        pid,
                        f"goal:{gi}/phase:{pi}/milestone:{mi}",
                    )
                    tasks = (
                        milestone.get("tasks") if isinstance(milestone, dict) else None
                    )
                    if not isinstance(tasks, list) or not tasks:
                        raise ValueError("every milestone requires at least one task")
                    for ti, task in enumerate(tasks):
                        tid = append_node(
                            NodeType.TASK,
                            task,
                            mid,
                            f"goal:{gi}/phase:{pi}/milestone:{mi}/task:{ti}",
                        )
                        subtasks = (
                            task.get("subtasks") if isinstance(task, dict) else None
                        ) or []
                        if not isinstance(subtasks, list):
                            raise ValueError("subtasks must be a list")
                        for si, subtask in enumerate(subtasks):
                            append_node(
                                NodeType.SUBTASK,
                                subtask,
                                tid,
                                f"goal:{gi}/phase:{pi}/milestone:{mi}/task:{ti}/subtask:{si}",
                            )

        if counts[NodeType.PHASE.value] > MAX_PHASES:
            raise ValueError(f"phase count exceeds {MAX_PHASES}")
        if counts[NodeType.MILESTONE.value] > MAX_MILESTONES:
            raise ValueError(f"milestone count exceeds {MAX_MILESTONES}")
        task_count = counts[NodeType.TASK.value] + counts[NodeType.SUBTASK.value]
        if task_count > MAX_TASKS:
            raise ValueError(f"task count exceeds {MAX_TASKS}")
        if len(nodes) > MAX_NODES:
            raise ValueError(f"node count exceeds {MAX_NODES}")

        task_ids = {
            node["node_id"]
            for node in nodes
            if node["node_type"] in {NodeType.TASK.value, NodeType.SUBTASK.value}
        }
        dependencies: list[tuple[str, str]] = []
        for task_id, requested_deps in pending_dependencies:
            for requested in requested_deps:
                dependency_id = requested_to_node.get(requested)
                if not dependency_id or dependency_id not in task_ids:
                    raise ValueError(f"dependency {requested!r} is not a task")
                if dependency_id == task_id:
                    raise ValueError("a task cannot depend on itself")
                dependencies.append((task_id, dependency_id))
        return nodes, dependencies

    @staticmethod
    def _validate_dag(
        nodes: list[dict[str, Any]], dependencies: list[tuple[str, str]]
    ) -> None:
        tasks = {
            node["node_id"]
            for node in nodes
            if node["node_type"] in {NodeType.TASK.value, NodeType.SUBTASK.value}
        }
        inbound = {task_id: 0 for task_id in tasks}
        outbound: dict[str, list[str]] = defaultdict(list)
        seen = set()
        for task_id, depends_on in dependencies:
            edge = (task_id, depends_on)
            if edge in seen:
                raise ValueError("duplicate dependency edge")
            seen.add(edge)
            if task_id not in tasks or depends_on not in tasks:
                raise ValueError("dependency references unknown task")
            inbound[task_id] += 1
            outbound[depends_on].append(task_id)
        queue = deque(sorted(task_id for task_id, count in inbound.items() if count == 0))
        visited = 0
        while queue:
            current = queue.popleft()
            visited += 1
            for child in sorted(outbound[current]):
                inbound[child] -= 1
                if inbound[child] == 0:
                    queue.append(child)
        if visited != len(tasks):
            raise ValueError("task dependency graph must be acyclic")

    # ------------------------------------------------------------- lifecycle
    def start(
        self, ctx: PlatformExecutionContext, mission_id: str
    ) -> dict[str, Any]:
        runtime = self._runtime(
            ctx, mission_id, permission=PlatformPermission.MISSION_RUN
        )
        state = MissionRuntimeState(runtime["state"])
        if state == MissionRuntimeState.PLANNED:
            runtime = self.repo.transition_runtime(
                mission_id, MissionRuntimeState.QUEUED.value
            )
            state = MissionRuntimeState(runtime["state"])
        if state == MissionRuntimeState.QUEUED:
            runtime = self.repo.transition_runtime(
                mission_id,
                MissionRuntimeState.RUNNING.value,
                started_at=runtime["started_at"] or self.store._now(),
            )
        elif state != MissionRuntimeState.RUNNING:
            raise PlatformContextError(
                "INVALID_STATE", f"mission cannot start from {state.value}"
            )
        self.repo.add_decision(
            mission_id=mission_id,
            decision_type="MISSION_START",
            outcome=runtime["state"],
            reason="operator-authorized mission start",
            policy="mission-runtime.lifecycle.v1",
            actor=ctx.requested_by(),
        )
        self.create_checkpoint(ctx, mission_id, created_by="runtime")
        self._audit("mission_runtime.started", ctx, mission_id)
        return self.get(ctx, mission_id)

    def transition_task(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        task_id: str,
        target: str,
        *,
        summary: str = "",
        error_code: str = "",
    ) -> dict[str, Any]:
        runtime = self._runtime(
            ctx, mission_id, permission=PlatformPermission.MISSION_RUN
        )
        if MissionRuntimeState(runtime["state"]) != MissionRuntimeState.RUNNING:
            raise PlatformContextError("INVALID_STATE", "mission is not running")
        try:
            destination = TaskStatus(target).value
            current = self.repo.get_node(mission_id, task_id)
            if not current:
                raise KeyError(task_id)
            if (
                current["status"] == TaskStatus.FAILED.value
                and destination == TaskStatus.READY.value
            ):
                raise ValueError("failed tasks may retry only through bounded policy")
            fields: dict[str, Any] = {}
            if destination == TaskStatus.RUNNING.value:
                fields["started_at"] = self.store._now()
                fields["attempt"] = int(current["attempt"]) + 1
            if destination in {status.value for status in TASK_TERMINAL}:
                fields["finished_at"] = self.store._now()
            if summary:
                fields["outcome_summary"] = _text(
                    summary, name="task summary", maximum=2000
                )
            if error_code:
                fields["error_code"] = _text(
                    error_code, name="error code", maximum=160
                )
            task = self.repo.transition_task(
                mission_id, task_id, destination, **fields
            )
        except (ValueError, KeyError) as exc:
            raise PlatformContextError("INVALID_STATE", str(exc)) from exc
        if destination == TaskStatus.RUNNING.value:
            phase_id = self._phase_for_task(mission_id, task_id)
            self.repo.update_runtime(
                mission_id,
                active_phase_id=phase_id,
                active_task_id=task_id,
                active_agent=task["agent_type"],
            )
        elif runtime["active_task_id"] == task_id:
            self.repo.update_runtime(
                mission_id,
                active_phase_id="",
                active_task_id="",
                active_agent="",
            )
        self._refresh_ready(mission_id)
        self._audit(
            "mission_runtime.task_transition",
            ctx,
            mission_id,
            detail={"task_id": task_id, "state": destination},
        )
        return task

    def complete_task(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        task_id: str,
        *,
        summary: str,
    ) -> dict[str, Any]:
        self._runtime(ctx, mission_id, permission=PlatformPermission.MISSION_RUN)
        task = self.repo.get_node(mission_id, task_id)
        if not task:
            raise PlatformContextError("NOT_FOUND", "task not found")
        evidence = self.repo.evidence(mission_id)
        passed_checks = {
            item["check_name"]
            for item in evidence
            if item["task_id"] == task_id
            and item["status"] == EvidenceStatus.PASS.value
            and item["check_name"]
        }
        missing = sorted(set(task["verification"]) - passed_checks)
        if missing:
            raise PlatformContextError(
                "VERIFICATION_REQUIRED", f"missing passing evidence: {', '.join(missing)}"
            )
        if task["requires_review"]:
            approved = any(
                item["task_id"] == task_id and item["verdict"] == "APPROVED"
                for item in self.repo.reviews(mission_id)
            )
            if not approved:
                raise PlatformContextError(
                    "REVIEW_REQUIRED", "independent review has not approved the task"
                )
        try:
            completed = self.repo.transition_task(
                mission_id,
                task_id,
                TaskStatus.COMPLETED.value,
                outcome_summary=_text(summary, name="task summary", maximum=2000),
                finished_at=self.store._now(),
            )
        except ValueError as exc:
            raise PlatformContextError("INVALID_STATE", str(exc)) from exc
        self._refresh_ready(mission_id)
        self._maybe_complete_mission(mission_id)
        runtime = self.repo.get_runtime(mission_id)
        if runtime["active_task_id"] == task_id:
            self.repo.update_runtime(
                mission_id,
                active_phase_id="",
                active_task_id="",
                active_agent="",
            )
        self.create_checkpoint(ctx, mission_id, created_by=task["agent_type"])
        return completed

    def _phase_for_task(self, mission_id: str, task_id: str) -> str:
        nodes = {
            node["node_id"]: node for node in self.repo.list_nodes(mission_id)
        }
        current = nodes.get(task_id)
        while current:
            if current["node_type"] == NodeType.PHASE.value:
                return current["node_id"]
            current = nodes.get(current["parent_id"])
        return ""

    def _refresh_ready(self, mission_id: str) -> None:
        tasks = {
            item["node_id"]: item
            for item in self.repo.list_nodes(mission_id)
            if item["node_type"] in {NodeType.TASK.value, NodeType.SUBTASK.value}
        }
        deps: dict[str, list[str]] = defaultdict(list)
        for edge in self.repo.dependencies(mission_id):
            deps[edge["task_id"]].append(edge["depends_on_task_id"])
        for task_id, task in sorted(
            tasks.items(), key=lambda pair: (-pair[1]["priority"], pair[1]["position"])
        ):
            if task["status"] != TaskStatus.PENDING.value:
                continue
            upstream = [tasks[dep]["status"] for dep in deps[task_id]]
            if any(
                state
                in {
                    TaskStatus.FAILED.value,
                    TaskStatus.CANCELLED.value,
                    TaskStatus.BLOCKED.value,
                }
                for state in upstream
            ):
                self.repo.transition_task(
                    mission_id,
                    task_id,
                    TaskStatus.BLOCKED.value,
                    error_code="DEPENDENCY_BLOCKED",
                )
            elif all(
                state
                in {TaskStatus.COMPLETED.value, TaskStatus.SKIPPED.value}
                for state in upstream
            ):
                self.repo.transition_task(
                    mission_id, task_id, TaskStatus.READY.value
                )

    def _maybe_complete_mission(self, mission_id: str) -> None:
        runtime = self.repo.get_runtime(mission_id)
        tasks = [
            node
            for node in self.repo.list_nodes(mission_id)
            if node["node_type"] in {NodeType.TASK.value, NodeType.SUBTASK.value}
        ]
        if not tasks or MissionRuntimeState(runtime["state"]) != MissionRuntimeState.RUNNING:
            return
        if all(
            task["status"]
            in {TaskStatus.COMPLETED.value, TaskStatus.SKIPPED.value}
            for task in tasks
        ):
            self.repo.transition_runtime(
                mission_id,
                MissionRuntimeState.COMPLETED.value,
                active_phase_id="",
                active_task_id="",
                active_agent="",
                finished_at=self.store._now(),
                stop_reason="ALL_TASKS_VERIFIED",
            )

    # ---------------------------------------------------------- evidence/review
    def record_evidence(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        *,
        task_id: str = "",
        evidence_type: str,
        status: str,
        summary: str,
        reference: str = "",
        check_name: str = "",
        collected_by: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        runtime = self._runtime(
            ctx, mission_id, permission=PlatformPermission.MISSION_WRITE
        )
        if task_id and not self.repo.get_node(mission_id, task_id):
            raise PlatformContextError("NOT_FOUND", "task not found")
        normalized_type = str(evidence_type or "").lower()
        usage = dict(runtime["usage"])
        counter = {
            "test": ("test_count", "max_tests"),
            "browser": ("browser_runs", "max_browser_runs"),
            "commit": ("commit_count", "max_commits"),
        }.get(normalized_type)
        if counter:
            usage_key, budget_key = counter
            projected = int(usage.get(usage_key, 0)) + 1
            if projected > int(runtime["budget"].get(budget_key, 0)):
                raise PlatformContextError(
                    "RESOURCE_BUDGET_EXHAUSTED",
                    f"{usage_key} would exceed {budget_key}",
                )
            usage[usage_key] = projected
        try:
            reject_secret_fields(metadata or {})
            state = EvidenceStatus(status).value
            evidence = self.repo.add_evidence(
                mission_id=mission_id,
                task_id=task_id,
                evidence_type=_text(
                    evidence_type, name="evidence_type", maximum=80
                ),
                status=state,
                summary=_text(summary, name="summary", maximum=2000),
                reference=_text(
                    reference, name="reference", maximum=500, required=False
                ),
                check_name=_text(
                    check_name, name="check_name", maximum=120, required=False
                ),
                collected_by=_text(
                    collected_by or ctx.requested_by(),
                    name="collected_by",
                    maximum=120,
                ),
                metadata=metadata or {},
            )
        except ValueError as exc:
            raise PlatformContextError("VALIDATION_FAILED", str(exc)) from exc
        if counter:
            self.repo.update_runtime(mission_id, usage=usage)
        self._audit(
            "mission_runtime.evidence_recorded",
            ctx,
            mission_id,
            detail={
                "evidence_id": evidence["evidence_id"],
                "task_id": task_id,
                "status": state,
            },
        )
        return evidence

    def record_review(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        *,
        task_id: str,
        verdict: str,
        findings: list[str],
        evidence_ids: list[str] | None = None,
        reviewer_agent: str = AgentType.REVIEWER.value,
    ) -> dict[str, Any]:
        self._runtime(ctx, mission_id, permission=PlatformPermission.MISSION_WRITE)
        if not self.repo.get_node(mission_id, task_id):
            raise PlatformContextError("NOT_FOUND", "task not found")
        verdict = str(verdict or "").upper()
        if verdict not in {"APPROVED", "REVISE", "BLOCKED"}:
            raise PlatformContextError("VALIDATION_FAILED", "invalid review verdict")
        if not isinstance(findings, list) or len(findings) > 50:
            raise PlatformContextError(
                "VALIDATION_FAILED", "findings must be a bounded list"
            )
        try:
            safe_findings = [
                _text(item, name="review finding", maximum=1000)
                for item in findings
            ]
        except ValueError as exc:
            raise PlatformContextError("VALIDATION_FAILED", str(exc)) from exc
        try:
            reviewer = AgentType(reviewer_agent).value
        except ValueError as exc:
            raise PlatformContextError(
                "VALIDATION_FAILED", "invalid reviewer agent"
            ) from exc
        raw_evidence_ids = [] if evidence_ids is None else evidence_ids
        if not isinstance(raw_evidence_ids, list) or len(raw_evidence_ids) > 100:
            raise PlatformContextError(
                "VALIDATION_FAILED", "review evidence_ids must be a bounded list"
            )
        try:
            safe_evidence_ids = [
                _text(item, name="evidence_id", maximum=120)
                for item in raw_evidence_ids
            ]
        except ValueError as exc:
            raise PlatformContextError("VALIDATION_FAILED", str(exc)) from exc
        if len(safe_evidence_ids) != len(set(safe_evidence_ids)):
            raise PlatformContextError(
                "VALIDATION_FAILED", "review evidence_ids must be unique"
            )
        available = {
            item["evidence_id"]: item for item in self.repo.evidence(mission_id)
        }
        if any(item not in available for item in safe_evidence_ids):
            raise PlatformContextError(
                "VALIDATION_FAILED", "review evidence is not part of this mission"
            )
        if verdict == "APPROVED":
            if not safe_evidence_ids:
                raise PlatformContextError(
                    "VERIFICATION_REQUIRED",
                    "approved review must reference mission evidence",
                )
            if any(
                available[item]["status"] != EvidenceStatus.PASS.value
                for item in safe_evidence_ids
            ):
                raise PlatformContextError(
                    "VERIFICATION_REQUIRED",
                    "approved review may reference only passing evidence",
                )
        review = self.repo.add_review(
            mission_id=mission_id,
            task_id=task_id,
            reviewer_agent=reviewer,
            verdict=verdict,
            findings=safe_findings,
            evidence_ids=safe_evidence_ids,
        )
        self._audit(
            "mission_runtime.review_recorded",
            ctx,
            mission_id,
            detail={"task_id": task_id, "verdict": verdict},
        )
        return review

    # ---------------------------------------------------------- certification
    def certify(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        *,
        verdict: str,
        summary: str,
        evidence_ids: list[str],
        limitations: list[str] | None = None,
    ) -> dict[str, Any]:
        runtime = self._runtime(
            ctx, mission_id, permission=PlatformPermission.MISSION_RUN
        )
        if runtime["state"] != MissionRuntimeState.COMPLETED.value:
            raise PlatformContextError(
                "INVALID_STATE", "only a completed mission can be certified"
            )
        if self.repo.certifications(mission_id):
            raise PlatformContextError(
                "INVALID_STATE", "mission already has a final certification"
            )

        normalized_verdict = str(verdict or "").strip().upper()
        if normalized_verdict not in CERTIFICATION_VERDICTS:
            raise PlatformContextError(
                "VALIDATION_FAILED", "invalid certification verdict"
            )
        try:
            safe_summary = _text(
                summary, name="certification summary", maximum=4000
            )
        except ValueError as exc:
            raise PlatformContextError("VALIDATION_FAILED", str(exc)) from exc
        if not isinstance(evidence_ids, list) or not 1 <= len(evidence_ids) <= 100:
            raise PlatformContextError(
                "VALIDATION_FAILED",
                "certification evidence_ids must contain 1 to 100 items",
            )
        try:
            safe_evidence_ids = [
                _text(item, name="evidence_id", maximum=120)
                for item in evidence_ids
            ]
        except ValueError as exc:
            raise PlatformContextError("VALIDATION_FAILED", str(exc)) from exc
        if len(safe_evidence_ids) != len(set(safe_evidence_ids)):
            raise PlatformContextError(
                "VALIDATION_FAILED", "certification evidence_ids must be unique"
            )
        raw_limitations = limitations or []
        if not isinstance(raw_limitations, list) or len(raw_limitations) > 50:
            raise PlatformContextError(
                "VALIDATION_FAILED", "limitations must be a bounded list"
            )
        try:
            safe_limitations = [
                _text(item, name="limitation", maximum=1000)
                for item in raw_limitations
            ]
        except ValueError as exc:
            raise PlatformContextError("VALIDATION_FAILED", str(exc)) from exc

        nodes = self.repo.list_nodes(mission_id)
        tasks = [
            node
            for node in nodes
            if node["node_type"] in {NodeType.TASK.value, NodeType.SUBTASK.value}
        ]
        if not tasks or any(
            task["status"]
            not in {TaskStatus.COMPLETED.value, TaskStatus.SKIPPED.value}
            for task in tasks
        ):
            raise PlatformContextError(
                "VERIFICATION_REQUIRED",
                "all mission tasks must be completed or explicitly skipped",
            )
        if runtime["known_blockers"]:
            raise PlatformContextError(
                "VERIFICATION_REQUIRED",
                "known blockers must be resolved before certification",
            )
        if str(runtime["test_status"]).upper() != EvidenceStatus.PASS.value:
            raise PlatformContextError(
                "VERIFICATION_REQUIRED",
                "passing test status is required for certification",
            )
        if str(runtime["browser_status"]).upper() != EvidenceStatus.PASS.value:
            raise PlatformContextError(
                "VERIFICATION_REQUIRED",
                "passing browser status is required for certification",
            )
        if not SHA_RE.fullmatch(str(runtime["latest_commit"] or "")):
            raise PlatformContextError(
                "VERIFICATION_REQUIRED",
                "a valid latest commit SHA is required for certification",
            )
        if not SHA_RE.fullmatch(str(runtime["rollback_sha"] or "")):
            raise PlatformContextError(
                "VERIFICATION_REQUIRED",
                "a valid rollback SHA is required for certification",
            )

        all_evidence = {
            item["evidence_id"]: item for item in self.repo.evidence(mission_id)
        }
        if any(item not in all_evidence for item in safe_evidence_ids):
            raise PlatformContextError(
                "VALIDATION_FAILED",
                "certification evidence is not part of this mission",
            )
        if any(
            all_evidence[item]["status"] != EvidenceStatus.PASS.value
            for item in safe_evidence_ids
        ):
            raise PlatformContextError(
                "VERIFICATION_REQUIRED",
                "certification may reference only passing evidence",
            )
        approved_reviews = [
            item
            for item in self.repo.reviews(mission_id)
            if item["verdict"] == "APPROVED" and item["evidence_ids"]
        ]
        selected_ids = set(safe_evidence_ids)
        accepted_reviews = [
            item
            for item in approved_reviews
            if set(item["evidence_ids"]).issubset(selected_ids)
        ]
        if not accepted_reviews:
            raise PlatformContextError(
                "REVIEW_REQUIRED",
                "an approved review of selected evidence is required",
            )

        checkpoints = self.repo.checkpoints(mission_id)
        if not checkpoints:
            raise PlatformContextError(
                "VERIFICATION_REQUIRED",
                "a durable completion checkpoint is required",
            )
        checkpoint = checkpoints[0]
        completed_ids = sorted(task["node_id"] for task in tasks)
        checkpoint_matches = (
            sorted(checkpoint["completed_tasks"]) == completed_ids
            and not checkpoint["pending_tasks"]
            and checkpoint["resource_usage"] == runtime["usage"]
            and checkpoint["latest_commit"] == runtime["latest_commit"]
            and checkpoint["rollback_sha"] == runtime["rollback_sha"]
            and str(checkpoint["test_status"]).upper()
            == EvidenceStatus.PASS.value
            and str(checkpoint["browser_status"]).upper()
            == EvidenceStatus.PASS.value
            and not checkpoint["known_blockers"]
            and bool(checkpoint["snapshot_hash"])
        )
        if not checkpoint_matches:
            raise PlatformContextError(
                "VERIFICATION_REQUIRED",
                "latest checkpoint does not match completed mission state",
            )

        certified_by = _text(
            f"{AgentType.CERTIFICATION.value}:{ctx.requested_by()}",
            name="certified_by",
            maximum=120,
        )
        certificate_snapshot = {
            "mission_id": mission_id,
            "runtime_version": runtime["version"],
            "from_state": runtime["state"],
            "target_state": MissionRuntimeState.CERTIFIED.value,
            "tasks": [
                {
                    "node_id": task["node_id"],
                    "status": task["status"],
                    "execution_id": task["execution_id"],
                    "outcome_summary": task["outcome_summary"],
                }
                for task in sorted(tasks, key=lambda item: item["node_id"])
            ],
            "budget": runtime["budget"],
            "usage": runtime["usage"],
            "latest_commit": runtime["latest_commit"],
            "rollback_sha": runtime["rollback_sha"],
            "test_status": runtime["test_status"],
            "browser_status": runtime["browser_status"],
            "checkpoint_id": checkpoint["checkpoint_id"],
            "checkpoint_hash": checkpoint["snapshot_hash"],
            "evidence_ids": sorted(safe_evidence_ids),
            "approved_review_ids": sorted(
                item["review_id"] for item in accepted_reviews
            ),
            "verdict": normalized_verdict,
            "summary": safe_summary,
            "limitations": safe_limitations,
        }
        try:
            certification, certified_runtime = self.repo.certify_runtime(
                mission_id=mission_id,
                verdict=normalized_verdict,
                summary=safe_summary,
                evidence_ids=sorted(safe_evidence_ids),
                limitations=safe_limitations,
                certified_by=certified_by,
                snapshot_hash=snapshot_hash(certificate_snapshot),
            )
        except (KeyError, ValueError) as exc:
            raise PlatformContextError("INVALID_STATE", str(exc)) from exc
        self._audit(
            "mission_runtime.certified",
            ctx,
            mission_id,
            detail={
                "certification_id": certification["certification_id"],
                "verdict": normalized_verdict,
                "snapshot_hash": certification["snapshot_hash"],
            },
        )
        return {
            "certification": certification,
            "runtime": certified_runtime,
            "dashboard": self._dashboard(certified_runtime, nodes),
        }

    # -------------------------------------------------------------- checkpoint
    def create_checkpoint(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        *,
        created_by: str,
        latest_commit: str | None = None,
        rollback_sha: str | None = None,
        test_status: str | None = None,
        browser_status: str | None = None,
        known_blockers: list[str] | None = None,
    ) -> dict[str, Any]:
        runtime = self._runtime(
            ctx, mission_id, permission=PlatformPermission.MISSION_WRITE
        )
        updates: dict[str, Any] = {}
        if latest_commit is not None:
            updates["latest_commit"] = _text(
                latest_commit, name="latest_commit", maximum=80, required=False
            )
        if rollback_sha is not None:
            updates["rollback_sha"] = _text(
                rollback_sha, name="rollback_sha", maximum=80, required=False
            )
        if test_status is not None:
            updates["test_status"] = _text(
                test_status, name="test_status", maximum=80
            )
        if browser_status is not None:
            updates["browser_status"] = _text(
                browser_status, name="browser_status", maximum=80
            )
        if known_blockers is not None:
            if not isinstance(known_blockers, list) or len(known_blockers) > 100:
                raise PlatformContextError(
                    "VALIDATION_FAILED", "known_blockers must be a bounded list"
                )
            updates["known_blockers"] = [
                _text(item, name="blocker", maximum=500) for item in known_blockers
            ]
        if updates:
            runtime = self.repo.update_runtime(mission_id, **updates)
        tasks = [
            node
            for node in self.repo.list_nodes(mission_id)
            if node["node_type"] in {NodeType.TASK.value, NodeType.SUBTASK.value}
        ]
        completed = sorted(
            task["node_id"]
            for task in tasks
            if task["status"]
            in {TaskStatus.COMPLETED.value, TaskStatus.SKIPPED.value}
        )
        pending = sorted(
            task["node_id"]
            for task in tasks
            if task["status"] not in {status.value for status in TASK_TERMINAL}
        )
        snapshot = {
            "mission_id": mission_id,
            "state": runtime["state"],
            "completed_tasks": completed,
            "pending_tasks": pending,
            "active_agent": runtime["active_agent"],
            "active_phase_id": runtime["active_phase_id"],
            "active_task_id": runtime["active_task_id"],
            "usage": runtime["usage"],
            "latest_commit": runtime["latest_commit"],
            "rollback_sha": runtime["rollback_sha"],
            "test_status": runtime["test_status"],
            "browser_status": runtime["browser_status"],
            "known_blockers": runtime["known_blockers"],
        }
        checkpoint = self.repo.add_checkpoint(
            {
                "mission_id": mission_id,
                "current_phase_id": runtime["active_phase_id"],
                "active_task_id": runtime["active_task_id"],
                "active_agent": runtime["active_agent"],
                "completed_tasks": completed,
                "pending_tasks": pending,
                "resource_usage": runtime["usage"],
                "latest_commit": runtime["latest_commit"],
                "rollback_sha": runtime["rollback_sha"],
                "test_status": runtime["test_status"],
                "browser_status": runtime["browser_status"],
                "known_blockers": runtime["known_blockers"],
                "snapshot_hash": snapshot_hash(snapshot),
                "created_by": _text(
                    created_by, name="created_by", maximum=120
                ),
            }
        )
        self.repo.update_runtime(
            mission_id, last_checkpoint_at=checkpoint["created_at"]
        )
        self._audit(
            "mission_runtime.checkpoint_created",
            ctx,
            mission_id,
            detail={
                "checkpoint_id": checkpoint["checkpoint_id"],
                "snapshot_hash": checkpoint["snapshot_hash"],
            },
        )
        return checkpoint

    # ------------------------------------------------------------------- reads
    def get(
        self, ctx: PlatformExecutionContext, mission_id: str
    ) -> dict[str, Any]:
        mission = self._mission(ctx, mission_id)
        runtime = self.repo.get_runtime(mission_id)
        if not runtime:
            return {
                "mission": mission.to_public(),
                "runtime": None,
                "hierarchy": [],
                "tasks": [],
                "dependencies": [],
                "evidence": [],
                "decisions": [],
                "checkpoints": [],
                "reviews": [],
                "certifications": [],
                "dashboard": None,
            }
        nodes = self.repo.list_nodes(mission_id)
        hierarchy = self._hierarchy(nodes)
        tasks = [
            item
            for item in nodes
            if item["node_type"] in {NodeType.TASK.value, NodeType.SUBTASK.value}
        ]
        return {
            "mission": mission.to_public(),
            "runtime": runtime,
            "hierarchy": hierarchy,
            "tasks": tasks,
            "dependencies": self.repo.dependencies(mission_id),
            "evidence": self.repo.evidence(mission_id),
            "decisions": self.repo.decisions(mission_id),
            "checkpoints": self.repo.checkpoints(mission_id),
            "reviews": self.repo.reviews(mission_id),
            "certifications": self.repo.certifications(mission_id),
            "dashboard": self._dashboard(runtime, nodes),
        }

    def list_dashboard(
        self, ctx: PlatformExecutionContext, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        ctx.require_permission(PlatformPermission.MISSION_READ)
        runtimes = self.repo.list_runtimes(
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            project_id=ctx.project_id,
            limit=limit,
        )
        return [
            self._dashboard(runtime, self.repo.list_nodes(runtime["mission_id"]))
            for runtime in runtimes
        ]

    @staticmethod
    def _hierarchy(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        children: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in nodes:
            children[item["parent_id"]].append(item)

        def build(item: dict[str, Any]) -> dict[str, Any]:
            return {
                **item,
                "children": [
                    build(child)
                    for child in sorted(
                        children[item["node_id"]], key=lambda value: value["position"]
                    )
                ],
            }

        return [
            build(item)
            for item in sorted(children[""], key=lambda value: value["position"])
        ]

    @staticmethod
    def _dashboard(
        runtime: dict[str, Any], nodes: list[dict[str, Any]]
    ) -> dict[str, Any]:
        tasks = [
            node
            for node in nodes
            if node["node_type"] in {NodeType.TASK.value, NodeType.SUBTASK.value}
        ]
        total = len(tasks)
        complete = sum(
            1
            for task in tasks
            if task["status"]
            in {TaskStatus.COMPLETED.value, TaskStatus.SKIPPED.value}
        )
        failed = sum(1 for task in tasks if task["status"] == TaskStatus.FAILED.value)
        blocked = sum(
            1 for task in tasks if task["status"] == TaskStatus.BLOCKED.value
        )
        running = sum(
            1 for task in tasks if task["status"] == TaskStatus.RUNNING.value
        )
        ready = sum(1 for task in tasks if task["status"] == TaskStatus.READY.value)
        remaining_effort = sum(
            float(task["estimated_effort"])
            for task in tasks
            if task["status"]
            not in {
                TaskStatus.COMPLETED.value,
                TaskStatus.SKIPPED.value,
                TaskStatus.CANCELLED.value,
            }
        )
        node_by_id = {node["node_id"]: node for node in nodes}
        active_phase = node_by_id.get(runtime["active_phase_id"])
        active_task = node_by_id.get(runtime["active_task_id"])
        if runtime["state"] in {
            MissionRuntimeState.FAILED.value,
            MissionRuntimeState.BLOCKED.value,
        } or failed:
            health = "CRITICAL"
        elif runtime["known_blockers"] or blocked:
            health = "AT_RISK"
        elif runtime["state"] in {
            MissionRuntimeState.RUNNING.value,
            MissionRuntimeState.QUEUED.value,
        }:
            health = "HEALTHY"
        elif runtime["state"] in {
            MissionRuntimeState.COMPLETED.value,
            MissionRuntimeState.CERTIFIED.value,
        }:
            health = "COMPLETE"
        else:
            health = "IDLE"
        return {
            "mission_id": runtime["mission_id"],
            "health": health,
            "state": runtime["state"],
            "progress_percent": round((complete / total) * 100, 1) if total else 0.0,
            "active_phase": runtime["active_phase_id"] or None,
            "active_phase_title": active_phase["title"] if active_phase else None,
            "active_task": runtime["active_task_id"] or None,
            "active_task_title": active_task["title"] if active_task else None,
            "current_agent": runtime["active_agent"] or None,
            "task_counts": {
                "total": total,
                "completed": complete,
                "ready": ready,
                "running": running,
                "blocked": blocked,
                "failed": failed,
            },
            "warnings": runtime["warnings"],
            "blockers": runtime["known_blockers"],
            "eta_seconds": round(
                remaining_effort / max(1, int(runtime["max_parallel_tasks"])), 1
            ),
            "resource_usage": runtime["usage"],
            "test_status": runtime["test_status"],
            "browser_status": runtime["browser_status"],
            "latest_commit": runtime["latest_commit"] or None,
            "rollback_sha": runtime["rollback_sha"] or None,
            "last_checkpoint_at": runtime["last_checkpoint_at"] or None,
        }
