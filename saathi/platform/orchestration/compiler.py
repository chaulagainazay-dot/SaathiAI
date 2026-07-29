"""Compile objectives into Mission Runtime plan definitions."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import (
    ApprovalRequirement,
    MAX_PLAN_NODES,
    ObjectiveIntake,
    READONLY_ANALYSIS_TOOL,
    RiskLevel,
)
from .roles import AgentRoleRegistry
from .templates import build_template_plan, infer_template


class PlanCompiler:
    """Produces Mission Runtime-compatible plan dicts from intake + templates."""

    def __init__(self, roles: AgentRoleRegistry | None = None):
        self.roles = roles or AgentRoleRegistry()

    def compile(
        self,
        intake: ObjectiveIntake,
        *,
        model_proposal: dict[str, Any] | None = None,
        grounded_context: str = "",
    ) -> dict[str, Any]:
        template_id = intake.template_id or infer_template(intake.objective, intake.domain)
        base = build_template_plan(
            template_id,
            objective=intake.objective,
            domain=intake.domain,
        )
        # Optional model-assisted merge: only accept validated structural patches
        if model_proposal and isinstance(model_proposal, dict):
            base = self._merge_model_proposal(base, model_proposal)

        base["objective"] = intake.objective
        base["intake"] = intake.to_public()
        base["grounded_context_chars"] = len(grounded_context or "")
        base["risk_level"] = intake.risk_level
        base["production_impact"] = intake.production_impact
        base["success_criteria"] = intake.success_criteria
        base["stop_conditions"] = intake.stop_conditions or "fail_closed_on_security"
        base["exclusions"] = intake.exclusions

        # Annotate tasks with approval requirements and role policy defaults
        self._annotate_tasks(base, intake)

        # Production impact elevates risk and approval gates
        if intake.production_impact or intake.risk_level in {
            RiskLevel.HIGH.value,
            RiskLevel.CRITICAL.value,
        }:
            base["max_parallel_tasks"] = min(int(base.get("max_parallel_tasks") or 2), 2)
            for task in self._iter_tasks(base):
                if task.get("approval_requirement") == ApprovalRequirement.NO_APPROVAL_REQUIRED.value:
                    task["approval_requirement"] = (
                        ApprovalRequirement.APPROVAL_REQUIRED_BEFORE_EXECUTION.value
                    )
                task["requires_review"] = True

        # Credential / paid / production never auto-enabled
        base["credential_requirements"] = False
        base["paid_providers"] = False
        base["production_authorized"] = False
        base["trading_execution"] = False
        return base

    def _merge_model_proposal(
        self, base: dict[str, Any], proposal: dict[str, Any]
    ) -> dict[str, Any]:
        """Accept only bounded additive task suggestions after structural checks."""
        out = deepcopy(base)
        extra = proposal.get("additional_tasks") or proposal.get("tasks") or []
        if not isinstance(extra, list):
            return out
        # Attach at most 5 extra analysis tasks to first milestone
        goals = out.get("goals") or []
        if not goals:
            return out
        try:
            milestone = goals[0]["phases"][0]["milestones"][0]
            tasks = milestone.setdefault("tasks", [])
        except (KeyError, IndexError, TypeError):
            return out
        existing_ids = {str(t.get("id")) for t in tasks if isinstance(t, dict)}
        added = 0
        for raw in extra:
            if added >= 5 or not isinstance(raw, dict):
                break
            tid = str(raw.get("id") or f"model-extra-{added}")[:40]
            if tid in existing_ids:
                continue
            title = str(raw.get("title") or "Model-suggested analysis")[:200]
            agent = str(raw.get("agent_type") or "ResearcherAgent")
            if agent not in self.roles.known_agent_types():
                agent = "ResearcherAgent"
            # Model cannot introduce mutation tools
            tool_id = READONLY_ANALYSIS_TOOL
            deps = raw.get("depends_on") or []
            if not isinstance(deps, list):
                deps = []
            deps = [str(d)[:80] for d in deps if str(d) in existing_ids][:10]
            tasks.append(
                {
                    "id": tid,
                    "title": f"[model-suggestion] {title}",
                    "agent_type": agent,
                    "tool_id": tool_id,
                    "arguments": {"text": title, "model_suggested": True},
                    "depends_on": deps,
                    "priority": 30,
                    "estimated_effort": 1,
                    "token_estimate": 150,
                    "max_retries": 1,
                    "requires_review": True,
                    "verification": [],
                    "model_suggested": True,
                }
            )
            existing_ids.add(tid)
            added += 1
        return out

    def _annotate_tasks(self, plan: dict[str, Any], intake: ObjectiveIntake) -> None:
        for task in self._iter_tasks(plan):
            agent = str(task.get("agent_type") or "ImplementerAgent")
            try:
                policy = self.roles.get_by_agent_type(agent)
            except ValueError:
                policy = self.roles.get("researcher")
                task["agent_type"] = policy.agent_type
            task.setdefault("max_retries", policy.max_retries)
            task.setdefault("timeout_sec", policy.timeout_sec)
            task["approval_requirement"] = policy.approval_requirement
            task["role_id"] = policy.role_id
            task["forbidden_capabilities"] = list(policy.forbidden_capabilities)
            # Force analysis-safe tool unless explicitly already set to registered readonly
            tool = str(task.get("tool_id") or READONLY_ANALYSIS_TOOL)
            # Never allow empty tool for autonomous dispatch path
            task["tool_id"] = tool or READONLY_ANALYSIS_TOOL
            # Trading / production keywords force blocked classification
            blob = f"{task.get('title','')} {task.get('objective','')}".lower()
            if any(x in blob for x in ("trade", "live order", "withdraw", "leverage")):
                task["approval_requirement"] = ApprovalRequirement.BLOCKED_BY_POLICY.value
                task["blocked_reason"] = "Trading Guardian: financial execution prohibited"
            if intake.production_impact and "deploy" in blob:
                task["approval_requirement"] = (
                    ApprovalRequirement.APPROVAL_REQUIRED_BEFORE_PRODUCTION.value
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

    def count_nodes(self, plan: dict[str, Any]) -> int:
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
