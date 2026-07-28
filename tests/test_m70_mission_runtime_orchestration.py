"""M70 bounded agents, decisions, retry, recovery, and runtime-only dispatch."""
from __future__ import annotations

from dataclasses import replace
from threading import Lock
import time

import pytest

from saathi.platform.context import PlatformContextError
from saathi.platform.mission_runtime import (
    MissionAgentRegistry,
    MissionRuntimeOrchestrator,
    MissionRuntimeService,
)
from saathi.platform.models import (
    PlatformExecutionRecord,
    PlatformExecutionState,
    new_id,
)
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.contracts import ToolExecutionResult, ToolOutcomeClass
from saathi.tool_runtime.registry import reset_registry_for_tests


@pytest.fixture()
def mission_env(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "m70.db")
    boot = platform.bootstrap_owner_secure(
        email="owner@m70.local",
        name="Mission Owner",
        password="GoodPassw0rd!",
    )
    ctx = platform.require_context(boot["token"])
    project = platform.create_project(ctx, "M70 Orchestration")
    mission = platform.create_mission(
        ctx, project["project_id"], "M70", "Mission Orchestration"
    )
    return platform, boot["token"], ctx, project, mission


def _plan(
    tasks: list[dict],
    *,
    max_parallel: int = 2,
    max_cycles: int = 20,
) -> dict:
    return {
        "objective": "Execute a bounded test mission.",
        "max_parallel_tasks": max_parallel,
        "budget": {
            "estimated_effort": 20,
            "max_elapsed_seconds": 3600,
            "max_token_estimate": 10000,
            "max_commits": 5,
            "max_tests": 10,
            "max_browser_runs": 3,
            "max_cycles": max_cycles,
            "max_no_progress_cycles": 3,
        },
        "goals": [
            {
                "title": "Goal",
                "phases": [
                    {
                        "title": "Phase",
                        "milestones": [{"title": "Milestone", "tasks": tasks}],
                    }
                ],
            }
        ],
    }


def _task(
    task_id: str,
    title: str,
    *,
    tool_id: str = "m49.echo_readonly",
    agent: str = "ImplementerAgent",
    depends_on: list[str] | None = None,
    max_retries: int = 1,
    verification: list[str] | None = None,
) -> dict:
    return {
        "id": task_id,
        "title": title,
        "agent_type": agent,
        "tool_id": tool_id,
        "arguments": {"text": title},
        "depends_on": depends_on or [],
        "priority": 50,
        "estimated_effort": 1,
        "token_estimate": 100,
        "max_retries": max_retries,
        "verification": verification or [],
    }


def _result(
    *,
    ok: bool = True,
    outcome: ToolOutcomeClass = ToolOutcomeClass.SUCCESS_CONFIRMED,
    error_code: str = "",
    execution_id: str = "pex_fake",
) -> ToolExecutionResult:
    result = ToolExecutionResult(
        tool_id="m49.echo_readonly",
        tool_version="1.0.0",
        call_id="fake-call",
        status="completed" if ok else "failed",
        outcome_class=outcome,
        data={"echo": "ok"} if ok else {},
        safe_message="confirmed success" if ok else "confirmed failure",
        error_code=error_code,
        adapter_invoked=True,
    )
    result.platform_execution_id = execution_id
    return result


def _task_by_title(snapshot: dict, title: str) -> dict:
    return next(task for task in snapshot["tasks"] if task["title"] == title)


def test_real_dispatch_uses_platform_runtime_and_execution_gateway(mission_env):
    platform, token, ctx, _, mission = mission_env
    service = MissionRuntimeService(platform)
    service.plan(
        ctx,
        mission["mission_id"],
        _plan([_task("echo", "Echo through canonical runtime")], max_parallel=1),
    )

    report = MissionRuntimeOrchestrator(platform).run_until_stop(
        ctx, mission["mission_id"], token=token
    )
    snapshot = service.get(ctx, mission["mission_id"])

    assert report["stop_condition"] == "MISSION_EXECUTION_COMPLETE"
    assert snapshot["runtime"]["state"] == "COMPLETED"
    assert snapshot["tasks"][0]["status"] == "COMPLETED"
    assert snapshot["tasks"][0]["attempt"] == 1
    assert snapshot["tasks"][0]["execution_id"].startswith("pex_")
    assert snapshot["evidence"][0]["evidence_type"] == "execution"
    events = {
        event["event"]
        for event in platform.store.list_audit(org_id=ctx.org_id, limit=200)
    }
    assert {
        "runtime.execution_requested",
        "runtime.dispatch_started",
        "runtime.gateway_accepted",
        "runtime.completion",
    } <= events


def test_independent_safe_agents_dispatch_in_parallel(mission_env):
    platform, _, ctx, _, mission = mission_env
    lock = Lock()

    class ConcurrentRuntime:
        active = 0
        max_active = 0
        calls = []

        def execute_context(self, call_ctx, **kwargs):
            with lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                self.calls.append((call_ctx.mission_id, kwargs["tool_id"]))
            time.sleep(0.05)
            with lock:
                self.active -= 1
            return _result(execution_id=f"pex_{len(self.calls)}")

    fake = ConcurrentRuntime()
    service = MissionRuntimeService(platform)
    service.plan(
        ctx,
        mission["mission_id"],
        _plan(
            [
                _task("architecture", "Architecture", agent="ArchitectAgent"),
                _task("implementation", "Implementation", agent="ImplementerAgent"),
            ]
        ),
    )
    report = MissionRuntimeOrchestrator(
        platform, agent_runtime=fake
    ).run_cycle(ctx, mission["mission_id"])

    assert len(report["dispatches"]) == 2
    assert fake.max_active == 2
    assert {item["agent_type"] for item in report["dispatches"]} == {
        "ArchitectAgent",
        "ImplementerAgent",
    }
    assert all(call[0] == mission["mission_id"] for call in fake.calls)
    descriptions = MissionAgentRegistry().describe()
    assert len(descriptions) == 8
    assert {item["execution_authority"] for item in descriptions} == {
        "PlatformAgentRuntime"
    }


def test_approval_wait_survives_and_resumes_same_execution(mission_env):
    platform, token, ctx, project, mission = mission_env
    task = _task(
        "write",
        "Governed local write",
        tool_id="m49.local_note_write",
        agent="DocumentationAgent",
    )
    task["arguments"] = {"key": "m70", "value": "bounded"}
    task["capability"] = "write"
    service = MissionRuntimeService(platform)
    service.plan(ctx, mission["mission_id"], _plan([task], max_parallel=1))
    orchestrator = MissionRuntimeOrchestrator(platform)

    waiting = orchestrator.run_cycle(ctx, mission["mission_id"], token=token)
    snapshot = service.get(ctx, mission["mission_id"])
    runtime_task = snapshot["tasks"][0]
    first_execution = runtime_task["execution_id"]
    assert waiting["stop_condition"] == "APPROVAL_REQUIRED"
    assert snapshot["runtime"]["state"] == "WAITING"
    assert runtime_task["status"] == "WAITING"
    assert runtime_task["attempt"] == 1

    mission_ctx = replace(
        ctx,
        project_id=project["project_id"],
        mission_id=mission["mission_id"],
    )
    approval = platform.request_approval(
        mission_ctx,
        tool_id="m49.local_note_write",
        action="write",
        capability="write",
        side_effect_class="LOCAL_REVERSIBLE",
        authority="LOCAL_MUTATION",
        ttl_sec=600,
    )
    platform.decide_approval(ctx, approval.approval_id, approve=True)
    orchestrator.attach_approval(
        ctx, mission["mission_id"], runtime_task["node_id"], approval.approval_id
    )
    resumed = orchestrator.run_cycle(ctx, mission["mission_id"], token=token)
    final = service.get(ctx, mission["mission_id"])

    assert resumed["stop_condition"] == "MISSION_EXECUTION_COMPLETE"
    assert final["tasks"][0]["status"] == "COMPLETED"
    assert final["tasks"][0]["attempt"] == 1
    assert final["tasks"][0]["execution_id"] == first_execution
    assert platform.store.get_approval(approval.approval_id).consumed_at > 0


def test_confirmed_transient_failure_retries_once_then_completes(mission_env):
    platform, _, ctx, _, mission = mission_env

    class RetryRuntime:
        calls = 0

        def execute_context(self, call_ctx, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return _result(
                    ok=False,
                    outcome=ToolOutcomeClass.FAILURE_CONFIRMED,
                    error_code="TRANSIENT",
                    execution_id="pex_attempt_1",
                )
            return _result(execution_id="pex_attempt_2")

    fake = RetryRuntime()
    service = MissionRuntimeService(platform)
    service.plan(
        ctx,
        mission["mission_id"],
        _plan([_task("retry", "Retry bounded", max_retries=1)], max_parallel=1),
    )
    orchestrator = MissionRuntimeOrchestrator(platform, agent_runtime=fake)
    first = orchestrator.run_cycle(ctx, mission["mission_id"])
    retry_task = service.get(ctx, mission["mission_id"])["tasks"][0]

    assert first["dispatches"][0]["retry_scheduled"] is True
    assert retry_task["status"] == "READY"
    assert retry_task["attempt"] == 1
    orchestrator.repo.update_task(
        mission["mission_id"], retry_task["node_id"], not_before=0
    )
    second = orchestrator.run_cycle(ctx, mission["mission_id"])
    final = service.get(ctx, mission["mission_id"])

    assert second["stop_condition"] == "MISSION_EXECUTION_COMPLETE"
    assert fake.calls == 2
    assert final["tasks"][0]["attempt"] == 2
    assert final["tasks"][0]["status"] == "COMPLETED"
    retry_decisions = [
        item for item in final["decisions"] if item["decision_type"] == "RETRY"
    ]
    assert len(retry_decisions) == 1


def test_success_waits_for_declared_verification_then_promotes(mission_env):
    platform, _, ctx, _, mission = mission_env

    class SuccessRuntime:
        def execute_context(self, call_ctx, **kwargs):
            return _result(execution_id="pex_verify")

    service = MissionRuntimeService(platform)
    service.plan(
        ctx,
        mission["mission_id"],
        _plan(
            [
                _task(
                    "verify",
                    "Verify result",
                    verification=["focused-tests"],
                )
            ],
            max_parallel=1,
        ),
    )
    orchestrator = MissionRuntimeOrchestrator(
        platform, agent_runtime=SuccessRuntime()
    )
    waiting = orchestrator.run_cycle(ctx, mission["mission_id"])
    task = service.get(ctx, mission["mission_id"])["tasks"][0]

    assert waiting["stop_condition"] == "BLOCKED_EXTERNAL_INPUT"
    assert waiting["post_decision"]["action"] == "REVIEW"
    assert task["status"] == "WAITING"
    service.record_evidence(
        ctx,
        mission["mission_id"],
        task_id=task["node_id"],
        evidence_type="test",
        status="PASS",
        summary="Focused verification passed.",
        check_name="focused-tests",
    )
    promoted = orchestrator.run_cycle(ctx, mission["mission_id"])
    final = service.get(ctx, mission["mission_id"])
    assert promoted["stop_condition"] == "MISSION_EXECUTION_COMPLETE"
    assert final["runtime"]["state"] == "COMPLETED"
    assert final["tasks"][0]["status"] == "COMPLETED"


def test_predicted_resource_budget_stops_before_dispatch(mission_env):
    platform, _, ctx, _, mission = mission_env

    class MustNotDispatch:
        calls = 0

        def execute_context(self, call_ctx, **kwargs):
            self.calls += 1
            raise AssertionError("budget gate must precede dispatch")

    plan = _plan([_task("expensive", "Expensive")], max_parallel=1)
    plan["budget"]["max_token_estimate"] = 50
    service = MissionRuntimeService(platform)
    service.plan(ctx, mission["mission_id"], plan)
    fake = MustNotDispatch()
    report = MissionRuntimeOrchestrator(
        platform, agent_runtime=fake
    ).run_cycle(ctx, mission["mission_id"])
    snapshot = service.get(ctx, mission["mission_id"])

    assert report["stop_condition"] == "FAILED_SAFETY_GATE"
    assert fake.calls == 0
    assert snapshot["runtime"]["state"] == "BLOCKED"
    assert "predicted token estimate" in snapshot["runtime"]["stop_reason"]
    assert snapshot["tasks"][0]["attempt"] == 0


def test_uncertain_dispatch_never_retries_and_recovery_blocks_replay(mission_env):
    platform, token, ctx, project, mission = mission_env
    service = MissionRuntimeService(platform)
    service.plan(
        ctx,
        mission["mission_id"],
        _plan([_task("uncertain", "Uncertain task")], max_parallel=1),
    )
    service.start(ctx, mission["mission_id"])
    task = service.get(ctx, mission["mission_id"])["tasks"][0]
    running = service.transition_task(
        ctx, mission["mission_id"], task["node_id"], "RUNNING"
    )
    execution_id = new_id("pex_")
    execution = PlatformExecutionRecord(
        execution_id=execution_id,
        state=PlatformExecutionState.RUNNING.value,
        user_id=ctx.user_id,
        session_id=ctx.session_id,
        org_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        project_id=project["project_id"],
        mission_id=mission["mission_id"],
        agent_id="platform-default",
        run_id=f"mission:{mission['mission_id']}",
        tool_id=running["tool_id"],
        request_fingerprint="recovery-test",
        idempotency_key=(
            f"mission-runtime:{mission['mission_id']}:{running['node_id']}:"
            f"attempt:{running['attempt']}"
        ),
        dispatch_started=True,
    )
    platform.store.create_platform_execution(execution)
    service.repo.update_task(
        mission["mission_id"], running["node_id"], execution_id=execution_id
    )

    recovered = MissionRuntimeOrchestrator(platform).recover(
        ctx, mission["mission_id"], token=token
    )
    snapshot = service.get(ctx, mission["mission_id"])

    assert recovered["recovered_task_ids"] == []
    assert recovered["blocked_task_ids"] == [running["node_id"]]
    assert snapshot["runtime"]["state"] == "BLOCKED"
    assert snapshot["tasks"][0]["status"] == "BLOCKED"
    assert snapshot["tasks"][0]["attempt"] == 1
    record = platform.store.get_platform_execution(execution_id)
    assert record.state == PlatformExecutionState.PAUSED.value
    assert record.error_code == "dispatch_recorded_manual_review"
    assert record.recovery_count == 1


def test_pause_resume_cancel_and_missing_adapter_safe_stop(mission_env):
    platform, _, ctx, _, mission = mission_env
    service = MissionRuntimeService(platform)
    service.plan(
        ctx,
        mission["mission_id"],
        _plan([_task("manual", "Manual adapter", tool_id="")], max_parallel=1),
    )
    orchestrator = MissionRuntimeOrchestrator(platform)
    paused = orchestrator.pause(
        ctx, mission["mission_id"], reason="operator checkpoint"
    )
    assert paused["state"] == "PAUSED"
    assert orchestrator.resume(ctx, mission["mission_id"])["state"] == "RUNNING"

    blocked = orchestrator.run_cycle(ctx, mission["mission_id"])
    assert blocked["stop_condition"] == "BLOCKED_EXTERNAL_INPUT"
    assert service.get(ctx, mission["mission_id"])["tasks"][0]["status"] == "BLOCKED"

    other = platform.create_mission(
        ctx,
        mission["project_id"],
        "M70-CANCEL",
        "Cancellation",
    )
    service.plan(
        ctx,
        other["mission_id"],
        _plan([_task("pending", "Pending task")], max_parallel=1),
    )
    cancelled = orchestrator.cancel(ctx, other["mission_id"])
    assert cancelled["runtime"]["state"] == "CANCELLED"
    assert cancelled["tasks"][0]["status"] == "CANCELLED"
