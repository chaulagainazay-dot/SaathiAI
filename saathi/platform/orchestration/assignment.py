"""Deterministic agent assignment with separation of duties."""
from __future__ import annotations

from typing import Any

from .roles import TASK_ROLE_HINTS, AgentRoleRegistry


class AgentAssignmentService:
    def __init__(self, roles: AgentRoleRegistry | None = None):
        self.roles = roles or AgentRoleRegistry()

    def assign_plan(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        assignments: list[dict[str, Any]] = []
        for task in self._iter_tasks(plan):
            assigned = self.assign_task(task)
            task["agent_type"] = assigned["agent_type"]
            task["role_id"] = assigned["role_id"]
            assignments.append(assigned)
        # Separation of duties post-pass
        self._enforce_sod(plan, assignments)
        return assignments

    def assign_task(self, task: dict[str, Any]) -> dict[str, Any]:
        existing = str(task.get("agent_type") or "")
        if existing in self.roles.known_agent_types():
            policy = self.roles.get_by_agent_type(existing)
            return {
                "task_id": task.get("id"),
                "title": task.get("title"),
                "role_id": policy.role_id,
                "agent_type": policy.agent_type,
                "source": "explicit",
                "approval_requirement": policy.approval_requirement,
                "can_self_certify": policy.can_self_certify,
                "can_final_review": policy.can_final_review,
            }
        # Model recommendation may be present but is advisory only
        model_rec = str(task.get("model_recommended_role") or "")
        title = f"{task.get('title','')} {task.get('objective','')}".lower()
        role_id = self._hint_role(title)
        if model_rec:
            try:
                rec_policy = self.roles.get(model_rec)
                # Accept model rec only if compatible with hints or general research
                if role_id in {"researcher", "planner"} or rec_policy.role_id == role_id:
                    role_id = rec_policy.role_id
            except ValueError:
                pass
        policy = self.roles.get(role_id)
        return {
            "task_id": task.get("id"),
            "title": task.get("title"),
            "role_id": policy.role_id,
            "agent_type": policy.agent_type,
            "source": "deterministic",
            "model_recommendation": model_rec or None,
            "approval_requirement": policy.approval_requirement,
            "can_self_certify": policy.can_self_certify,
            "can_final_review": policy.can_final_review,
        }

    def _hint_role(self, text: str) -> str:
        for keywords, role_id in TASK_ROLE_HINTS:
            if any(k in text for k in keywords):
                return role_id
        return "researcher"

    def _enforce_sod(self, plan: dict[str, Any], assignments: list[dict[str, Any]]) -> None:
        """Ensure implementer tasks have independent review path in the plan."""
        by_id = {a["task_id"]: a for a in assignments if a.get("task_id")}
        for task in self._iter_tasks(plan):
            tid = task.get("id")
            a = by_id.get(tid)
            if not a:
                continue
            if a["agent_type"] == "ImplementerAgent":
                # cannot mark self as certifier
                task["can_self_certify"] = False
                if not task.get("requires_review"):
                    # require review unless a downstream Reviewer/Certification depends on this
                    if not self._has_downstream_reviewer(plan, str(tid)):
                        task["requires_review"] = True
            if a["agent_type"] == "CertificationAgent":
                task["can_self_certify"] = False

    def _has_downstream_reviewer(self, plan: dict[str, Any], task_id: str) -> bool:
        for t in self._iter_tasks(plan):
            deps = t.get("depends_on") or []
            if task_id in [str(d) for d in deps]:
                if t.get("agent_type") in {
                    "ReviewerAgent",
                    "CertificationAgent",
                    "SecurityAgent",
                }:
                    return True
        return False

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
