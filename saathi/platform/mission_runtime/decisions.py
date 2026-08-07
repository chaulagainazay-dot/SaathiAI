"""Pure bounded policies for mission scheduling, retry, and safe stops."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from saathi.platform.mission_runtime.models import (
    MissionRuntimeState,
    NodeType,
    TaskStatus,
)


class DecisionAction(str, Enum):
    DISPATCH = "DISPATCH"
    WAIT = "WAIT"
    REVIEW = "REVIEW"
    CONTINUE = "CONTINUE"
    STOP = "STOP"
    COMPLETE = "COMPLETE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"


class StopCondition(str, Enum):
    CONTINUE = "CONTINUE"
    MISSION_EXECUTION_COMPLETE = "MISSION_EXECUTION_COMPLETE"
    BLOCKED_EXTERNAL_INPUT = "BLOCKED_EXTERNAL_INPUT"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    FAILED_SAFETY_GATE = "FAILED_SAFETY_GATE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class MissionDecision:
    action: DecisionAction
    reason: str
    policy: str = "mission-runtime.decision.v1"
    task_ids: tuple[str, ...] = ()
    stop_condition: StopCondition = StopCondition.CONTINUE
    human_approval_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "policy": self.policy,
            "task_ids": list(self.task_ids),
            "stop_condition": self.stop_condition.value,
            "human_approval_required": self.human_approval_required,
        }


class MissionDecisionEngine:
    """Deterministic scheduling with finite resource and no-progress ceilings."""

    def decide(
        self,
        runtime: dict[str, Any],
        nodes: list[dict[str, Any]],
        *,
        now: float,
    ) -> MissionDecision:
        state = MissionRuntimeState(runtime["state"])
        tasks = [
            node
            for node in nodes
            if node["node_type"] in {NodeType.TASK.value, NodeType.SUBTASK.value}
        ]
        if state == MissionRuntimeState.CANCELLED or runtime["cancel_requested"]:
            return MissionDecision(
                DecisionAction.STOP,
                "mission cancellation is terminal or pending confirmation",
                stop_condition=StopCondition.CANCELLED,
            )
        if state == MissionRuntimeState.PAUSED:
            return MissionDecision(
                DecisionAction.STOP,
                "mission is paused by an authorized operator",
                stop_condition=StopCondition.PAUSED,
            )
        if state in {MissionRuntimeState.FAILED, MissionRuntimeState.BLOCKED}:
            external = str(runtime["stop_reason"]).startswith(
                "BLOCKED_EXTERNAL_INPUT"
            )
            return MissionDecision(
                DecisionAction.STOP,
                runtime["stop_reason"] or f"mission is {state.value.lower()}",
                stop_condition=(
                    StopCondition.BLOCKED_EXTERNAL_INPUT
                    if external
                    else StopCondition.FAILED_SAFETY_GATE
                ),
            )
        if state in {
            MissionRuntimeState.COMPLETED,
            MissionRuntimeState.CERTIFIED,
        }:
            return MissionDecision(
                DecisionAction.COMPLETE,
                "all task work has reached a verified terminal state",
                stop_condition=StopCondition.MISSION_EXECUTION_COMPLETE,
            )

        breach = self.budget_breach(runtime)
        if breach:
            return MissionDecision(
                DecisionAction.STOP,
                breach,
                stop_condition=StopCondition.FAILED_SAFETY_GATE,
            )

        waiting_approval = [
            task
            for task in tasks
            if task["status"] == TaskStatus.WAITING.value
            and task["error_code"] == "APPROVAL_REQUIRED"
        ]
        if waiting_approval:
            return MissionDecision(
                DecisionAction.APPROVAL_REQUIRED,
                "one or more tool executions require explicit human approval",
                task_ids=tuple(task["node_id"] for task in waiting_approval),
                stop_condition=StopCondition.APPROVAL_REQUIRED,
                human_approval_required=True,
            )

        running = [
            task for task in tasks if task["status"] == TaskStatus.RUNNING.value
        ]
        if running:
            return MissionDecision(
                DecisionAction.WAIT,
                "one or more task dispatches are still in flight",
                task_ids=tuple(task["node_id"] for task in running),
                stop_condition=StopCondition.BLOCKED_EXTERNAL_INPUT,
            )

        ready = [
            task
            for task in tasks
            if task["status"] == TaskStatus.READY.value
            and float(task["not_before"] or 0) <= now
        ]
        if ready:
            ordered = sorted(
                ready, key=lambda task: (-task["priority"], task["position"])
            )
            unsafe = [task for task in ordered if not task["concurrency_safe"]]
            selected = (
                unsafe[:1]
                if unsafe
                else ordered[: max(1, int(runtime["max_parallel_tasks"]))]
            )
            return MissionDecision(
                DecisionAction.DISPATCH,
                "highest-priority dependency-ready task batch selected",
                task_ids=tuple(task["node_id"] for task in selected),
            )

        waiting = [
            task for task in tasks if task["status"] == TaskStatus.WAITING.value
        ]
        if waiting:
            return MissionDecision(
                DecisionAction.REVIEW,
                "completed dispatches await declared verification or independent review",
                task_ids=tuple(task["node_id"] for task in waiting),
                stop_condition=StopCondition.BLOCKED_EXTERNAL_INPUT,
            )

        retry_wait = [
            task
            for task in tasks
            if task["status"] == TaskStatus.READY.value
            and float(task["not_before"] or 0) > now
        ]
        if retry_wait:
            return MissionDecision(
                DecisionAction.WAIT,
                "bounded retry backoff has not elapsed",
                task_ids=tuple(task["node_id"] for task in retry_wait),
                stop_condition=StopCondition.BLOCKED_EXTERNAL_INPUT,
            )

        pending = [
            task for task in tasks if task["status"] == TaskStatus.PENDING.value
        ]
        if pending:
            return MissionDecision(
                DecisionAction.WAIT,
                "pending tasks have unresolved dependencies",
                task_ids=tuple(task["node_id"] for task in pending),
                stop_condition=StopCondition.BLOCKED_EXTERNAL_INPUT,
            )

        if tasks and all(
            task["status"] in {TaskStatus.COMPLETED.value, TaskStatus.SKIPPED.value}
            for task in tasks
        ):
            return MissionDecision(
                DecisionAction.COMPLETE,
                "all tasks are completed or explicitly skipped",
                stop_condition=StopCondition.MISSION_EXECUTION_COMPLETE,
            )
        return MissionDecision(
            DecisionAction.STOP,
            "no safe executable task remains",
            stop_condition=StopCondition.FAILED_SAFETY_GATE,
        )

    @staticmethod
    def budget_breach(runtime: dict[str, Any]) -> str:
        budget = runtime["budget"]
        usage = runtime["usage"]
        for usage_key, budget_key in (
            ("elapsed_seconds", "max_elapsed_seconds"),
            ("no_progress_cycles", "max_no_progress_cycles"),
        ):
            ceiling = float(budget.get(budget_key, 0))
            if ceiling > 0 and float(usage.get(usage_key, 0)) >= ceiling:
                return f"resource budget exhausted: {usage_key}>={budget_key}"
        if int(usage.get("cycles", 0)) > int(budget.get("max_cycles", 0)):
            return "resource budget exhausted: cycles>max_cycles"
        for usage_key, budget_key in (
            ("token_estimate", "max_token_estimate"),
            ("commit_count", "max_commits"),
            ("test_count", "max_tests"),
            ("browser_runs", "max_browser_runs"),
        ):
            ceiling = float(budget.get(budget_key, 0))
            if ceiling > 0 and float(usage.get(usage_key, 0)) > ceiling:
                return f"resource budget exhausted: {usage_key}>{budget_key}"
        effort_ceiling = float(budget.get("estimated_effort", 0))
        if effort_ceiling and float(usage.get("effort_used", 0)) > effort_ceiling:
            return "resource budget exhausted: effort_used>estimated_effort"
        return ""

    @staticmethod
    def retry_allowed(task: dict[str, Any], outcome: str, error_code: str) -> bool:
        if int(task["attempt"]) > int(task["max_retries"]):
            return False
        if outcome != "FAILURE_CONFIRMED":
            return False
        code = str(error_code or "").upper()
        return code in {
            "RATE_LIMITED",
            "TEMPORARY_UNAVAILABLE",
            "TRANSIENT",
            "PROVIDER_UNAVAILABLE",
            "RETRYABLE",
        } or code.startswith("HTTP_5")
