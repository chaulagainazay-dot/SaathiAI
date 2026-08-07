"""Resumable mission orchestration over PlatformAgentRuntime only."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from typing import Any
import json

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.mission_runtime.agents import MissionAgentRegistry
from saathi.platform.mission_runtime.decisions import (
    DecisionAction,
    MissionDecision,
    MissionDecisionEngine,
    StopCondition,
)
from saathi.platform.mission_runtime.models import (
    EvidenceStatus,
    MissionRuntimeState,
    NodeType,
    TaskStatus,
)
from saathi.platform.mission_runtime.service import MissionRuntimeService
from saathi.platform.models import PlatformExecutionState, PlatformPermission
from saathi.platform.runtime import PlatformAgentRuntime


SAFETY_FAILURE_CODES = frozenset(
    {
        "ANONYMOUS_PROHIBITED",
        "APPROVAL_EXPIRED",
        "APPROVAL_REJECTED",
        "APPROVAL_REPLAY",
        "AUTHORITY_UNKNOWN",
        "BINDING_AUTHORITY_DENIED",
        "BINDING_CAPABILITY_DENIED",
        "BINDING_SCOPE_DENIED",
        "CONTEXT_CONTRADICTORY",
        "FINANCIAL_EXECUTION_PROHIBITED",
        "MEMBERSHIP_REVOKED",
        "PERMISSION_DENIED",
        "PROHIBITED",
        "TOOL_NOT_FOUND",
    }
)
UNCERTAIN_OUTCOMES = frozenset(
    {"SIDE_EFFECT_UNKNOWN", "TOOL_OUTCOME_UNKNOWN", "REQUIRES_REVIEW"}
)


class MissionRuntimeOrchestrator:
    """One finite scheduling loop; never a second tool execution engine."""

    def __init__(
        self,
        platform=None,
        *,
        agent_runtime=None,
        decision_engine: MissionDecisionEngine | None = None,
        agents: MissionAgentRegistry | None = None,
    ) -> None:
        self.service = MissionRuntimeService(platform)
        self.platform = self.service.platform
        self.store = self.service.store
        self.repo = self.service.repo
        self.agent_runtime = agent_runtime or PlatformAgentRuntime(self.platform)
        self.decisions = decision_engine or MissionDecisionEngine()
        self.agents = agents or MissionAgentRegistry()

    # --------------------------------------------------------------- cycles
    def run_cycle(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        *,
        token: str = "",
        timeout_sec: float | None = None,
    ) -> dict[str, Any]:
        runtime = self.service._runtime(
            ctx, mission_id, permission=PlatformPermission.MISSION_RUN
        )
        runtime = self._ensure_running(ctx, runtime)
        if runtime["state"] in {
            MissionRuntimeState.RUNNING.value,
            MissionRuntimeState.WAITING.value,
        }:
            self._promote_verified_waiting(ctx, mission_id)
        runtime = self._advance_usage(mission_id)
        nodes = self.repo.list_nodes(mission_id)
        decision = self.decisions.decide(runtime, nodes, now=self.store._now())
        self._record_decision(ctx, mission_id, decision)

        if decision.action != DecisionAction.DISPATCH:
            return self._cycle_report(ctx, mission_id, decision, [], progress=False)

        tasks = [
            self.repo.get_node(mission_id, task_id)
            for task_id in decision.task_ids
        ]
        missing_tool = [task for task in tasks if task and not task["tool_id"]]
        if missing_tool:
            blocker = MissionDecision(
                DecisionAction.STOP,
                "ready autonomous task has no registered tool adapter",
                task_ids=tuple(task["node_id"] for task in missing_tool),
                stop_condition=StopCondition.BLOCKED_EXTERNAL_INPUT,
            )
            for task in missing_tool:
                self.repo.transition_task(
                    mission_id,
                    task["node_id"],
                    TaskStatus.BLOCKED.value,
                    error_code="AGENT_ADAPTER_REQUIRED",
                )
            self.repo.transition_runtime(
                mission_id,
                MissionRuntimeState.BLOCKED.value,
                stop_reason="BLOCKED_EXTERNAL_INPUT:AGENT_ADAPTER_REQUIRED",
            )
            self._record_decision(ctx, mission_id, blocker)
            return self._cycle_report(
                ctx, mission_id, blocker, [], progress=True
            )

        budget_block = self._batch_budget_block(runtime, tasks)
        if budget_block:
            stop = MissionDecision(
                DecisionAction.STOP,
                budget_block,
                task_ids=decision.task_ids,
                stop_condition=StopCondition.FAILED_SAFETY_GATE,
            )
            self.repo.transition_runtime(
                mission_id,
                MissionRuntimeState.BLOCKED.value,
                stop_reason=f"FAILED_SAFETY_GATE:{budget_block}",
            )
            self._record_decision(ctx, mission_id, stop)
            return self._cycle_report(ctx, mission_id, stop, [], progress=False)

        task_context = self._mission_context(ctx, mission_id)
        dispatches = self._dispatch_batch(
            task_context,
            mission_id,
            tasks,
            token=token,
            timeout_sec=timeout_sec,
        )
        return self._cycle_report(
            ctx, mission_id, decision, dispatches, progress=True
        )

    def run_until_stop(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        *,
        token: str = "",
        max_cycles: int | None = None,
        timeout_sec: float | None = None,
    ) -> dict[str, Any]:
        runtime = self.service._runtime(
            ctx, mission_id, permission=PlatformPermission.MISSION_RUN
        )
        finite_limit = min(
            max(1, int(max_cycles or runtime["budget"]["max_cycles"])),
            int(runtime["budget"]["max_cycles"]),
        )
        reports = []
        for _ in range(finite_limit):
            report = self.run_cycle(
                ctx,
                mission_id,
                token=token,
                timeout_sec=timeout_sec,
            )
            reports.append(report)
            if not report["continue"]:
                break
        final = reports[-1]
        return {
            "mission_id": mission_id,
            "cycles_run": len(reports),
            "stop_condition": final["stop_condition"],
            "continue": final["continue"],
            "last_cycle": final,
        }

    def _dispatch_batch(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        tasks: list[dict[str, Any]],
        *,
        token: str,
        timeout_sec: float | None,
    ) -> list[dict[str, Any]]:
        prepared = []
        for task in tasks:
            if task["execution_id"]:
                started = self.repo.transition_task(
                    mission_id,
                    task["node_id"],
                    TaskStatus.RUNNING.value,
                    started_at=self.store._now(),
                )
                self.repo.update_runtime(
                    mission_id,
                    active_phase_id=self.service._phase_for_task(
                        mission_id, task["node_id"]
                    ),
                    active_task_id=task["node_id"],
                    active_agent=task["agent_type"],
                )
            else:
                started = self.service.transition_task(
                    ctx, mission_id, task["node_id"], TaskStatus.RUNNING.value
                )
                self._consume_estimate(mission_id, started)
            prepared.append(started)

        workers = max(1, len(prepared))
        outcomes: dict[str, tuple[Any, Exception | None, str]] = {}
        with ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="mission-agent"
        ) as pool:
            futures = {}
            for task in prepared:
                key = self._idempotency_key(mission_id, task)
                future = pool.submit(
                    self._dispatch_one,
                    ctx,
                    task,
                    token=token,
                    idempotency_key=key,
                    timeout_sec=timeout_sec,
                )
                futures[future] = (task, key)
            for future in as_completed(futures):
                task, key = futures[future]
                try:
                    outcomes[task["node_id"]] = (future.result(), None, key)
                except Exception as exc:  # normalized below; never silently retried
                    outcomes[task["node_id"]] = (None, exc, key)

        reports = []
        for task in prepared:
            result, error, key = outcomes[task["node_id"]]
            reports.append(
                self._apply_dispatch_outcome(
                    ctx,
                    mission_id,
                    task,
                    result=result,
                    error=error,
                    idempotency_key=key,
                )
            )
        return reports

    def _dispatch_one(
        self,
        ctx: PlatformExecutionContext,
        task: dict[str, Any],
        *,
        token: str,
        idempotency_key: str,
        timeout_sec: float | None,
    ):
        if task["execution_id"]:
            if not token:
                raise PlatformContextError(
                    "RESUME_TOKEN_REQUIRED",
                    "fresh authenticated token required to resume platform execution",
                )
            return self.agent_runtime.resume(
                token=token,
                execution_id=task["execution_id"],
                approval_id=task["approval_id"],
                timeout_sec=timeout_sec,
            )
        agent = self.agents.get(task["agent_type"])
        return agent.dispatch(
            self.agent_runtime,
            ctx,
            task,
            idempotency_key=idempotency_key,
            timeout_sec=timeout_sec,
        )

    def _apply_dispatch_outcome(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        task: dict[str, Any],
        *,
        result: Any,
        error: Exception | None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if error is not None:
            return self._apply_dispatch_error(
                ctx,
                mission_id,
                task,
                error=error,
                idempotency_key=idempotency_key,
            )

        execution_id = str(getattr(result, "platform_execution_id", "") or "")
        if execution_id:
            self.repo.update_task(
                mission_id, task["node_id"], execution_id=execution_id
            )
        outcome = str(
            getattr(getattr(result, "outcome_class", ""), "value", "")
            or getattr(result, "outcome_class", "")
        )
        error_code = str(getattr(result, "error_code", "") or "")
        summary = str(
            getattr(result, "safe_message", "")
            or ("platform execution completed" if getattr(result, "ok", False) else "platform execution failed")
        )[:2000]
        status = (
            EvidenceStatus.PASS.value
            if getattr(result, "ok", False)
            else EvidenceStatus.FAIL.value
        )
        self.service.record_evidence(
            ctx,
            mission_id,
            task_id=task["node_id"],
            evidence_type="execution",
            status=status,
            summary=summary,
            reference=execution_id,
            collected_by=task["agent_type"],
            metadata={
                "outcome_class": outcome,
                "error_code": error_code,
                "adapter_invoked": bool(getattr(result, "adapter_invoked", False)),
            },
        )

        if getattr(result, "ok", False):
            current = self.repo.get_node(mission_id, task["node_id"])
            if current["verification"] or current["requires_review"]:
                self.repo.transition_task(
                    mission_id,
                    task["node_id"],
                    TaskStatus.WAITING.value,
                    outcome_summary=summary,
                    execution_id=execution_id,
                )
                state = TaskStatus.WAITING.value
            else:
                state = self.service.complete_task(
                    ctx,
                    mission_id,
                    task["node_id"],
                    summary=summary,
                )["status"]
            return self._dispatch_report(
                task, state, execution_id, outcome, error_code
            )

        if bool(getattr(result, "cancellation_confirmed", False)):
            self.repo.transition_task(
                mission_id,
                task["node_id"],
                TaskStatus.CANCELLED.value,
                error_code=error_code or "CANCELLED_CONFIRMED",
                execution_id=execution_id,
                finished_at=self.store._now(),
            )
            self._finish_cancel_if_safe(mission_id)
            return self._dispatch_report(
                task,
                TaskStatus.CANCELLED.value,
                execution_id,
                outcome,
                error_code,
            )

        current = self.repo.get_node(mission_id, task["node_id"])
        if self.decisions.retry_allowed(current, outcome, error_code):
            not_before = self.store._now() + min(
                300.0, float(2 ** max(0, int(current["attempt"]) - 1))
            )
            self.repo.transition_task(
                mission_id,
                task["node_id"],
                TaskStatus.FAILED.value,
                error_code=error_code or "RETRYABLE_FAILURE",
                execution_id=execution_id,
                finished_at=self.store._now(),
            )
            self.repo.transition_task(
                mission_id,
                task["node_id"],
                TaskStatus.READY.value,
                not_before=not_before,
                execution_id="",
            )
            self.repo.add_decision(
                mission_id=mission_id,
                task_id=task["node_id"],
                decision_type="RETRY",
                outcome="SCHEDULED",
                reason=f"confirmed retryable failure; attempt {current['attempt']}",
                policy="mission-runtime.retry.v1",
                actor=ctx.requested_by(),
            )
            return self._dispatch_report(
                task,
                TaskStatus.READY.value,
                execution_id,
                outcome,
                error_code,
                retry_scheduled=True,
                not_before=not_before,
            )

        if outcome in UNCERTAIN_OUTCOMES:
            task_state = TaskStatus.BLOCKED.value
            mission_state = MissionRuntimeState.BLOCKED.value
            reason = "FAILED_SAFETY_GATE:UNCERTAIN_DISPATCH_REVIEW_REQUIRED"
        else:
            task_state = TaskStatus.FAILED.value
            mission_state = MissionRuntimeState.FAILED.value
            reason = f"FAILED_SAFETY_GATE:{error_code or outcome or 'EXECUTION_FAILED'}"
        self.repo.transition_task(
            mission_id,
            task["node_id"],
            task_state,
            error_code=error_code or outcome or "EXECUTION_FAILED",
            execution_id=execution_id,
            finished_at=self.store._now(),
        )
        self.repo.transition_runtime(
            mission_id, mission_state, stop_reason=reason
        )
        return self._dispatch_report(
            task, task_state, execution_id, outcome, error_code
        )

    def _apply_dispatch_error(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        task: dict[str, Any],
        *,
        error: Exception,
        idempotency_key: str,
    ) -> dict[str, Any]:
        code = (
            error.code
            if isinstance(error, PlatformContextError)
            else type(error).__name__.upper()
        )
        execution = self.store.find_platform_execution_by_idempotency(
            ctx.org_id, ctx.workspace_id, idempotency_key
        )
        execution_id = execution.execution_id if execution else ""
        if execution_id:
            self.repo.update_task(
                mission_id, task["node_id"], execution_id=execution_id
            )
        if code == "APPROVAL_REQUIRED":
            self.repo.transition_task(
                mission_id,
                task["node_id"],
                TaskStatus.WAITING.value,
                execution_id=execution_id,
                error_code=code,
            )
            self.repo.transition_runtime(
                mission_id,
                MissionRuntimeState.WAITING.value,
                stop_reason=StopCondition.APPROVAL_REQUIRED.value,
            )
            self.repo.add_decision(
                mission_id=mission_id,
                task_id=task["node_id"],
                decision_type="APPROVAL",
                outcome=StopCondition.APPROVAL_REQUIRED.value,
                reason="canonical platform runtime requires explicit approval",
                policy="mission-runtime.approval.v1",
                human_approval_required=True,
                actor=ctx.requested_by(),
            )
            return self._dispatch_report(
                task,
                TaskStatus.WAITING.value,
                execution_id,
                "WAITING_APPROVAL",
                code,
            )

        reason = (
            f"FAILED_SAFETY_GATE:{code}"
            if code in SAFETY_FAILURE_CODES
            else f"FAILED_SAFETY_GATE:UNCLASSIFIED_{code}"
        )
        self.repo.transition_task(
            mission_id,
            task["node_id"],
            TaskStatus.BLOCKED.value,
            execution_id=execution_id,
            error_code=code,
        )
        self.repo.transition_runtime(
            mission_id,
            MissionRuntimeState.BLOCKED.value,
            stop_reason=reason,
        )
        return self._dispatch_report(
            task, TaskStatus.BLOCKED.value, execution_id, "BLOCKED", code
        )

    # ------------------------------------------------------- operator control
    def pause(
        self, ctx: PlatformExecutionContext, mission_id: str, *, reason: str
    ) -> dict[str, Any]:
        runtime = self.service._runtime(
            ctx, mission_id, permission=PlatformPermission.MISSION_RUN
        )
        try:
            paused = self.repo.transition_runtime(
                mission_id,
                MissionRuntimeState.PAUSED.value,
                stop_reason=str(reason or "operator pause")[:500],
            )
        except ValueError as exc:
            raise PlatformContextError("INVALID_STATE", str(exc)) from exc
        self.repo.add_decision(
            mission_id=mission_id,
            decision_type="OPERATOR_CONTROL",
            outcome="PAUSED",
            reason=str(reason or "operator pause")[:500],
            policy="mission-runtime.control.v1",
            actor=ctx.requested_by(),
        )
        self.service.create_checkpoint(ctx, mission_id, created_by="runtime")
        return paused

    def resume(
        self, ctx: PlatformExecutionContext, mission_id: str
    ) -> dict[str, Any]:
        runtime = self.service._runtime(
            ctx, mission_id, permission=PlatformPermission.MISSION_RUN
        )
        if MissionRuntimeState(runtime["state"]) not in {
            MissionRuntimeState.PAUSED,
            MissionRuntimeState.WAITING,
        }:
            raise PlatformContextError(
                "INVALID_STATE", f"mission cannot resume from {runtime['state']}"
            )
        waiting_approval = [
            task
            for task in self.repo.list_nodes(mission_id)
            if task["node_type"] in {NodeType.TASK.value, NodeType.SUBTASK.value}
            and task["status"] == TaskStatus.WAITING.value
            and task["error_code"] == "APPROVAL_REQUIRED"
        ]
        if waiting_approval:
            raise PlatformContextError(
                "APPROVAL_REQUIRED", "waiting task has no approved approval reference"
            )
        resumed = self.repo.transition_runtime(
            mission_id,
            MissionRuntimeState.RUNNING.value,
            stop_reason="",
            started_at=runtime["started_at"] or self.store._now(),
        )
        self.repo.add_decision(
            mission_id=mission_id,
            decision_type="OPERATOR_CONTROL",
            outcome="RUNNING",
            reason="authorized operator resumed mission",
            policy="mission-runtime.control.v1",
            actor=ctx.requested_by(),
        )
        self.service.create_checkpoint(ctx, mission_id, created_by="runtime")
        return resumed

    def attach_approval(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        task_id: str,
        approval_id: str,
    ) -> dict[str, Any]:
        self.service._runtime(
            ctx, mission_id, permission=PlatformPermission.MISSION_RUN
        )
        task = self.repo.get_node(mission_id, task_id)
        approval = self.store.get_approval(approval_id)
        if (
            not task
            or task["status"] != TaskStatus.WAITING.value
            or task["error_code"] != "APPROVAL_REQUIRED"
            or not approval
            or approval.status != "approved"
            or approval.org_id != ctx.org_id
            or approval.workspace_id != ctx.workspace_id
            or approval.project_id
            not in {"", self.store.get_mission(mission_id).project_id}
            or approval.mission_id not in {"", mission_id}
            or approval.tool_id != task["tool_id"]
        ):
            raise PlatformContextError(
                "APPROVAL_INVALID", "approved task-scoped approval is required"
            )
        ready = self.repo.transition_task(
            mission_id,
            task_id,
            TaskStatus.READY.value,
            approval_id=approval_id,
            error_code="",
        )
        runtime = self.repo.get_runtime(mission_id)
        if runtime["state"] == MissionRuntimeState.WAITING.value:
            self.repo.transition_runtime(
                mission_id,
                MissionRuntimeState.RUNNING.value,
                stop_reason="",
            )
        self.repo.add_decision(
            mission_id=mission_id,
            task_id=task_id,
            decision_type="APPROVAL",
            outcome="APPROVED_REFERENCE_ATTACHED",
            reason="platform approval will be revalidated and consumed by runtime",
            policy="mission-runtime.approval.v1",
            actor=ctx.requested_by(),
        )
        return ready

    def cancel(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        *,
        token: str = "",
    ) -> dict[str, Any]:
        runtime = self.service._runtime(
            ctx, mission_id, permission=PlatformPermission.MISSION_RUN
        )
        if runtime["state"] in {
            MissionRuntimeState.COMPLETED.value,
            MissionRuntimeState.CERTIFIED.value,
            MissionRuntimeState.FAILED.value,
            MissionRuntimeState.CANCELLED.value,
        }:
            raise PlatformContextError(
                "INVALID_STATE", f"mission cannot cancel from {runtime['state']}"
            )
        self.repo.update_runtime(mission_id, cancel_requested=True)
        pending_confirmation = False
        for task in self.repo.list_nodes(mission_id):
            if task["node_type"] not in {
                NodeType.TASK.value,
                NodeType.SUBTASK.value,
            }:
                continue
            if task["status"] == TaskStatus.RUNNING.value and task["execution_id"]:
                if not token:
                    pending_confirmation = True
                    continue
                record = self.agent_runtime.cancel(
                    token=token, execution_id=task["execution_id"]
                )
                if record.state == PlatformExecutionState.CANCELLED.value:
                    self.repo.transition_task(
                        mission_id,
                        task["node_id"],
                        TaskStatus.CANCELLED.value,
                        finished_at=self.store._now(),
                    )
                else:
                    pending_confirmation = True
            elif task["status"] not in {
                TaskStatus.COMPLETED.value,
                TaskStatus.FAILED.value,
                TaskStatus.CANCELLED.value,
                TaskStatus.SKIPPED.value,
            }:
                self.repo.transition_task(
                    mission_id,
                    task["node_id"],
                    TaskStatus.CANCELLED.value,
                    finished_at=self.store._now(),
                )
        if pending_confirmation:
            if runtime["state"] == MissionRuntimeState.RUNNING.value:
                self.repo.transition_runtime(
                    mission_id,
                    MissionRuntimeState.WAITING.value,
                    cancel_requested=True,
                    stop_reason="BLOCKED_EXTERNAL_INPUT:CANCELLATION_CONFIRMATION",
                )
        else:
            self.repo.transition_runtime(
                mission_id,
                MissionRuntimeState.CANCELLED.value,
                cancel_requested=True,
                finished_at=self.store._now(),
                stop_reason="CANCELLED",
            )
        self.repo.add_decision(
            mission_id=mission_id,
            decision_type="OPERATOR_CONTROL",
            outcome="CANCELLATION_PENDING" if pending_confirmation else "CANCELLED",
            reason="authorized cancellation requested",
            policy="mission-runtime.control.v1",
            actor=ctx.requested_by(),
        )
        self.service.create_checkpoint(ctx, mission_id, created_by="runtime")
        return self.service.get(ctx, mission_id)

    # --------------------------------------------------------------- recovery
    def recover(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        *,
        token: str = "",
    ) -> dict[str, Any]:
        runtime = self.service._runtime(
            ctx, mission_id, permission=PlatformPermission.MISSION_RUN
        )
        recovered = []
        blocked = []
        approval_wait = False
        for task in self.repo.list_nodes(mission_id):
            if task["node_type"] not in {
                NodeType.TASK.value,
                NodeType.SUBTASK.value,
            } or task["status"] != TaskStatus.RUNNING.value:
                continue
            execution = self._execution_for_task(ctx, mission_id, task)
            if not execution:
                self.repo.transition_task(
                    mission_id,
                    task["node_id"],
                    TaskStatus.WAITING.value,
                    error_code="RECOVERED_BEFORE_PLATFORM_RECORD",
                )
                self.repo.transition_task(
                    mission_id, task["node_id"], TaskStatus.READY.value
                )
                recovered.append(task["node_id"])
                continue
            self.repo.update_task(
                mission_id, task["node_id"], execution_id=execution.execution_id
            )
            if not execution.is_terminal() and token:
                execution = self.agent_runtime.reconcile_execution(
                    token=token, execution_id=execution.execution_id
                )
            state = PlatformExecutionState(execution.state)
            if state == PlatformExecutionState.WAITING_APPROVAL:
                self.repo.transition_task(
                    mission_id,
                    task["node_id"],
                    TaskStatus.WAITING.value,
                    error_code="APPROVAL_REQUIRED",
                )
                blocked.append(task["node_id"])
                approval_wait = True
            elif state == PlatformExecutionState.PAUSED and not execution.dispatch_started:
                if token:
                    try:
                        result = self.agent_runtime.resume(
                            token=token,
                            execution_id=execution.execution_id,
                            approval_id=task["approval_id"],
                        )
                    except Exception as exc:
                        self._apply_dispatch_error(
                            ctx,
                            mission_id,
                            task,
                            error=exc,
                            idempotency_key=execution.idempotency_key,
                        )
                    else:
                        self._apply_dispatch_outcome(
                            ctx,
                            mission_id,
                            task,
                            result=result,
                            error=None,
                            idempotency_key=execution.idempotency_key,
                        )
                        recovered.append(task["node_id"])
                else:
                    self.repo.transition_task(
                        mission_id,
                        task["node_id"],
                        TaskStatus.WAITING.value,
                        error_code="RESUME_TOKEN_REQUIRED",
                    )
                    blocked.append(task["node_id"])
            elif state == PlatformExecutionState.COMPLETED and execution.result_json:
                payload = json.loads(execution.result_json)
                outcome = str(payload.get("outcome_class", ""))
                already_recorded = any(
                    item["task_id"] == task["node_id"]
                    and item["reference"] == execution.execution_id
                    for item in self.repo.evidence(mission_id)
                )
                if not already_recorded:
                    self.service.record_evidence(
                        ctx,
                        mission_id,
                        task_id=task["node_id"],
                        evidence_type="execution",
                        status=(
                            EvidenceStatus.PASS.value
                            if outcome == "SUCCESS_CONFIRMED"
                            else EvidenceStatus.FAIL.value
                        ),
                        summary=str(
                            payload.get("safe_message", "recovered platform execution")
                        )[:2000],
                        reference=execution.execution_id,
                        collected_by=task["agent_type"],
                        metadata={
                            "outcome_class": outcome,
                            "recovered": True,
                        },
                    )
                if outcome == "SUCCESS_CONFIRMED":
                    if task["verification"] or task["requires_review"]:
                        self.repo.transition_task(
                            mission_id,
                            task["node_id"],
                            TaskStatus.WAITING.value,
                            outcome_summary=str(payload.get("safe_message", ""))[:2000],
                        )
                    else:
                        self.service.complete_task(
                            ctx,
                            mission_id,
                            task["node_id"],
                            summary=str(payload.get("safe_message", "recovered success"))[
                                :2000
                            ],
                        )
                    recovered.append(task["node_id"])
                else:
                    self.repo.transition_task(
                        mission_id,
                        task["node_id"],
                        TaskStatus.BLOCKED.value,
                        error_code="RECOVERED_NON_SUCCESS",
                    )
                    blocked.append(task["node_id"])
            elif state == PlatformExecutionState.CANCELLED:
                self.repo.transition_task(
                    mission_id,
                    task["node_id"],
                    TaskStatus.CANCELLED.value,
                    error_code=execution.error_code or "CANCELLED",
                    finished_at=self.store._now(),
                )
                recovered.append(task["node_id"])
            elif state in {
                PlatformExecutionState.FAILED,
                PlatformExecutionState.TIMED_OUT,
            }:
                payload = json.loads(execution.result_json or "{}")
                outcome = str(payload.get("outcome_class", ""))
                if outcome == "FAILURE_CONFIRMED":
                    self.repo.transition_task(
                        mission_id,
                        task["node_id"],
                        TaskStatus.FAILED.value,
                        error_code=execution.error_code or "RECOVERED_FAILURE",
                        finished_at=self.store._now(),
                    )
                    self.repo.transition_runtime(
                        mission_id,
                        MissionRuntimeState.FAILED.value,
                        stop_reason="FAILED_SAFETY_GATE:RECOVERED_CONFIRMED_FAILURE",
                    )
                else:
                    self.repo.transition_task(
                        mission_id,
                        task["node_id"],
                        TaskStatus.BLOCKED.value,
                        error_code="UNCERTAIN_DISPATCH_REVIEW_REQUIRED",
                    )
                blocked.append(task["node_id"])
            elif execution.dispatch_started:
                self.repo.transition_task(
                    mission_id,
                    task["node_id"],
                    TaskStatus.BLOCKED.value,
                    error_code="UNCERTAIN_DISPATCH_REVIEW_REQUIRED",
                )
                blocked.append(task["node_id"])
            else:
                self.repo.transition_task(
                    mission_id,
                    task["node_id"],
                    TaskStatus.WAITING.value,
                    error_code="PLATFORM_RECONCILIATION_REQUIRED",
                )
                blocked.append(task["node_id"])

        current_runtime = self.repo.get_runtime(mission_id)
        if (
            approval_wait
            and current_runtime["state"] == MissionRuntimeState.RUNNING.value
        ):
            self.repo.transition_runtime(
                mission_id,
                MissionRuntimeState.WAITING.value,
                stop_reason=StopCondition.APPROVAL_REQUIRED.value,
            )
        elif (
            blocked
            and current_runtime["state"] == MissionRuntimeState.RUNNING.value
        ):
            self.repo.transition_runtime(
                mission_id,
                MissionRuntimeState.BLOCKED.value,
                stop_reason="BLOCKED_EXTERNAL_INPUT:RECOVERY_REVIEW_REQUIRED",
            )
        elif recovered and current_runtime["state"] in {
            MissionRuntimeState.PAUSED.value,
            MissionRuntimeState.WAITING.value,
            MissionRuntimeState.BLOCKED.value,
        }:
            self.repo.transition_runtime(
                mission_id,
                MissionRuntimeState.RUNNING.value,
                stop_reason="",
            )
        self.repo.add_decision(
            mission_id=mission_id,
            decision_type="RECOVERY",
            outcome="BLOCKED" if blocked else "RESUMED",
            reason="interrupted tasks reconciled without replay after recorded dispatch",
            policy="mission-runtime.recovery.v1",
            actor=ctx.requested_by(),
        )
        checkpoint = self.service.create_checkpoint(
            ctx, mission_id, created_by="runtime"
        )
        return {
            "mission_id": mission_id,
            "recovered_task_ids": recovered,
            "blocked_task_ids": blocked,
            "checkpoint_id": checkpoint["checkpoint_id"],
            "runtime": self.repo.get_runtime(mission_id),
        }

    # --------------------------------------------------------------- helpers
    def _ensure_running(
        self, ctx: PlatformExecutionContext, runtime: dict[str, Any]
    ) -> dict[str, Any]:
        state = MissionRuntimeState(runtime["state"])
        if state in {
            MissionRuntimeState.PLANNED,
            MissionRuntimeState.QUEUED,
        }:
            return self.service.start(ctx, runtime["mission_id"])["runtime"]
        return runtime

    def _promote_verified_waiting(
        self, ctx: PlatformExecutionContext, mission_id: str
    ) -> None:
        for task in self.repo.list_nodes(mission_id):
            if task["node_type"] not in {
                NodeType.TASK.value,
                NodeType.SUBTASK.value,
            } or task["status"] != TaskStatus.WAITING.value:
                continue
            if task["execution_id"] and not task["approval_id"]:
                execution = self.store.get_platform_execution(task["execution_id"])
                if execution and not execution.is_terminal():
                    continue
            evidence = self.repo.evidence(mission_id)
            passed = {
                item["check_name"]
                for item in evidence
                if item["task_id"] == task["node_id"]
                and item["status"] == EvidenceStatus.PASS.value
            }
            reviewed = not task["requires_review"] or any(
                review["task_id"] == task["node_id"]
                and review["verdict"] == "APPROVED"
                for review in self.repo.reviews(mission_id)
            )
            if set(task["verification"]) <= passed and reviewed:
                runtime = self.repo.get_runtime(mission_id)
                if runtime["state"] == MissionRuntimeState.WAITING.value:
                    self.repo.transition_runtime(
                        mission_id,
                        MissionRuntimeState.RUNNING.value,
                        stop_reason="",
                    )
                self.service.complete_task(
                    ctx,
                    mission_id,
                    task["node_id"],
                    summary=task["outcome_summary"] or "verification completed",
                )

    def _advance_usage(self, mission_id: str) -> dict[str, Any]:
        runtime = self.repo.get_runtime(mission_id)
        usage = dict(runtime["usage"])
        usage["cycles"] = int(usage.get("cycles", 0)) + 1
        if runtime["started_at"]:
            usage["elapsed_seconds"] = max(
                0.0, self.store._now() - float(runtime["started_at"])
            )
        return self.repo.update_runtime(mission_id, usage=usage)

    def _consume_estimate(
        self, mission_id: str, task: dict[str, Any]
    ) -> None:
        runtime = self.repo.get_runtime(mission_id)
        usage = dict(runtime["usage"])
        usage["token_estimate"] = int(usage.get("token_estimate", 0)) + int(
            task["token_estimate"]
        )
        usage["effort_used"] = float(usage.get("effort_used", 0)) + float(
            task["estimated_effort"]
        )
        self.repo.update_runtime(mission_id, usage=usage)

    def _batch_budget_block(
        self, runtime: dict[str, Any], tasks: list[dict[str, Any]]
    ) -> str:
        budget = runtime["budget"]
        usage = runtime["usage"]
        predicted_tokens = int(usage.get("token_estimate", 0)) + sum(
            int(task["token_estimate"]) for task in tasks
        )
        token_limit = int(budget.get("max_token_estimate", 0))
        if token_limit and predicted_tokens > token_limit:
            return "resource budget exhausted: predicted token estimate"
        effort_limit = float(budget.get("estimated_effort", 0))
        predicted_effort = float(usage.get("effort_used", 0)) + sum(
            float(task["estimated_effort"]) for task in tasks
        )
        if effort_limit and predicted_effort > effort_limit:
            return "resource budget exhausted: predicted effort"
        return ""

    def _cycle_report(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        decision: MissionDecision,
        dispatches: list[dict[str, Any]],
        *,
        progress: bool,
    ) -> dict[str, Any]:
        runtime = self.repo.get_runtime(mission_id)
        usage = dict(runtime["usage"])
        usage["no_progress_cycles"] = (
            0
            if progress
            else int(usage.get("no_progress_cycles", 0)) + 1
        )
        if runtime["started_at"]:
            usage["elapsed_seconds"] = max(
                0.0, self.store._now() - float(runtime["started_at"])
            )
        self.repo.update_runtime(mission_id, usage=usage)
        runtime = self.repo.get_runtime(mission_id)
        post = self.decisions.decide(
            runtime, self.repo.list_nodes(mission_id), now=self.store._now()
        )
        checkpoint = self.service.create_checkpoint(
            ctx, mission_id, created_by="runtime"
        )
        should_continue = post.stop_condition == StopCondition.CONTINUE
        return {
            "mission_id": mission_id,
            "decision": decision.to_dict(),
            "dispatches": dispatches,
            "post_decision": post.to_dict(),
            "continue": should_continue,
            "stop_condition": post.stop_condition.value,
            "checkpoint_id": checkpoint["checkpoint_id"],
        }

    def _record_decision(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        decision: MissionDecision,
    ) -> None:
        self.repo.add_decision(
            mission_id=mission_id,
            decision_type="SCHEDULER",
            outcome=decision.action.value,
            reason=decision.reason,
            policy=decision.policy,
            human_approval_required=decision.human_approval_required,
            actor=ctx.requested_by(),
        )

    def _mission_context(
        self, ctx: PlatformExecutionContext, mission_id: str
    ) -> PlatformExecutionContext:
        mission = self.store.get_mission(mission_id)
        return replace(
            ctx,
            project_id=mission.project_id,
            mission_id=mission_id,
            run_id=ctx.run_id or f"mission:{mission_id}",
        )

    def _execution_for_task(
        self,
        ctx: PlatformExecutionContext,
        mission_id: str,
        task: dict[str, Any],
    ):
        if task["execution_id"]:
            return self.store.get_platform_execution(task["execution_id"])
        return self.store.find_platform_execution_by_idempotency(
            ctx.org_id,
            ctx.workspace_id,
            self._idempotency_key(mission_id, task),
        )

    @staticmethod
    def _idempotency_key(mission_id: str, task: dict[str, Any]) -> str:
        return (
            f"mission-runtime:{mission_id}:{task['node_id']}:"
            f"attempt:{int(task['attempt'])}"
        )

    def _finish_cancel_if_safe(self, mission_id: str) -> None:
        runtime = self.repo.get_runtime(mission_id)
        if not runtime["cancel_requested"]:
            return
        active = [
            task
            for task in self.repo.list_nodes(mission_id)
            if task["node_type"] in {NodeType.TASK.value, NodeType.SUBTASK.value}
            and task["status"] == TaskStatus.RUNNING.value
        ]
        if not active and runtime["state"] in {
            MissionRuntimeState.RUNNING.value,
            MissionRuntimeState.WAITING.value,
            MissionRuntimeState.PAUSED.value,
            MissionRuntimeState.BLOCKED.value,
        }:
            self.repo.transition_runtime(
                mission_id,
                MissionRuntimeState.CANCELLED.value,
                finished_at=self.store._now(),
                stop_reason="CANCELLED",
            )

    @staticmethod
    def _dispatch_report(
        task: dict[str, Any],
        state: str,
        execution_id: str,
        outcome: str,
        error_code: str,
        *,
        retry_scheduled: bool = False,
        not_before: float = 0.0,
    ) -> dict[str, Any]:
        return {
            "task_id": task["node_id"],
            "agent_type": task["agent_type"],
            "state": state,
            "execution_id": execution_id,
            "outcome": outcome,
            "error_code": error_code,
            "retry_scheduled": retry_scheduled,
            "not_before": not_before,
        }
