"""M69 Autonomous Mission Runtime persistence, hierarchy, and lifecycle gates."""
from __future__ import annotations

from copy import deepcopy

import pytest

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.mission_runtime import MissionRuntimeService
from saathi.platform.service import PlatformService, reset_platform_for_tests
from saathi.platform.store import PlatformStore


@pytest.fixture()
def runtime_env(tmp_path):
    db_path = tmp_path / "m69.db"
    platform = reset_platform_for_tests(db_path)
    boot = platform.bootstrap_owner_secure(
        email="owner@m69.local",
        name="Mission Owner",
        password="GoodPassw0rd!",
    )
    ctx = platform.require_context(boot["token"])
    project = platform.create_project(ctx, "Autonomous Mission Runtime")
    mission = platform.create_mission(
        ctx,
        project["project_id"],
        "M69",
        "Mission Runtime Foundation",
    )
    return db_path, platform, ctx, project, mission


def _plan() -> dict:
    return {
        "objective": "Deliver a bounded, restart-safe engineering mission.",
        "max_parallel_tasks": 2,
        "budget": {
            "estimated_effort": 12,
            "max_elapsed_seconds": 7200,
            "max_token_estimate": 10000,
            "max_commits": 4,
            "max_tests": 8,
            "max_browser_runs": 2,
            "max_cycles": 20,
            "max_no_progress_cycles": 2,
        },
        "goals": [
            {
                "id": "goal-runtime",
                "title": "Autonomous mission runtime",
                "phases": [
                    {
                        "id": "phase-foundation",
                        "title": "Foundation",
                        "milestones": [
                            {
                                "id": "milestone-persistence",
                                "title": "Persistence",
                                "tasks": [
                                    {
                                        "id": "design",
                                        "title": "Design contracts",
                                        "agent_type": "ArchitectAgent",
                                        "priority": 90,
                                        "estimated_effort": 2,
                                        "token_estimate": 1000,
                                        "verification": ["architecture-review"],
                                        "requires_review": True,
                                    },
                                    {
                                        "id": "implement",
                                        "title": "Implement persistence",
                                        "agent_type": "ImplementerAgent",
                                        "depends_on": ["design"],
                                        "priority": 80,
                                        "estimated_effort": 5,
                                        "verification": ["focused-tests"],
                                    },
                                    {
                                        "id": "document",
                                        "title": "Document contracts",
                                        "agent_type": "DocumentationAgent",
                                        "depends_on": ["design"],
                                        "priority": 50,
                                        "estimated_effort": 1,
                                        "verification": [],
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _tasks_by_title(snapshot: dict) -> dict[str, dict]:
    return {task["title"]: task for task in snapshot["tasks"]}


def test_hierarchy_dag_queue_and_restart_persistence(runtime_env):
    db_path, platform, ctx, project, mission = runtime_env
    service = MissionRuntimeService(platform)
    planned = service.plan(ctx, mission["mission_id"], _plan())

    assert planned["runtime"]["state"] == "PLANNED"
    assert planned["hierarchy"][0]["node_type"] == "GOAL"
    assert planned["hierarchy"][0]["children"][0]["node_type"] == "PHASE"
    assert (
        planned["hierarchy"][0]["children"][0]["children"][0]["node_type"]
        == "MILESTONE"
    )
    tasks = _tasks_by_title(planned)
    assert tasks["Design contracts"]["status"] == "READY"
    assert tasks["Implement persistence"]["status"] == "PENDING"
    assert tasks["Document contracts"]["status"] == "PENDING"
    assert len(planned["dependencies"]) == 2
    assert planned["dashboard"]["progress_percent"] == 0.0
    assert planned["checkpoints"][0]["pending_tasks"]
    assert len(planned["checkpoints"][0]["snapshot_hash"]) == 64

    restarted = PlatformService(PlatformStore(db_path))
    restored_ctx = PlatformExecutionContext(
        user_id=ctx.user_id,
        role=ctx.role,
        org_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        project_id=project["project_id"],
    )
    restored = MissionRuntimeService(restarted).get(
        restored_ctx, mission["mission_id"]
    )
    assert restored["runtime"]["objective"] == planned["runtime"]["objective"]
    assert restored["dependencies"] == planned["dependencies"]
    assert [task["status"] for task in restored["tasks"]] == [
        task["status"] for task in planned["tasks"]
    ]
    assert (
        restored["checkpoints"][0]["snapshot_hash"]
        == planned["checkpoints"][0]["snapshot_hash"]
    )


def test_lifecycle_requires_evidence_and_review_before_completion(runtime_env):
    _, platform, ctx, _, mission = runtime_env
    service = MissionRuntimeService(platform)
    planned = service.plan(ctx, mission["mission_id"], _plan())
    design = _tasks_by_title(planned)["Design contracts"]

    started = service.start(ctx, mission["mission_id"])
    assert started["runtime"]["state"] == "RUNNING"
    running = service.transition_task(
        ctx, mission["mission_id"], design["node_id"], "RUNNING"
    )
    assert running["status"] == "RUNNING"
    active = service.get(ctx, mission["mission_id"])
    assert active["runtime"]["active_task_id"] == design["node_id"]
    assert active["runtime"]["active_agent"] == "ArchitectAgent"
    assert active["dashboard"]["active_phase"]

    with pytest.raises(PlatformContextError) as no_evidence:
        service.complete_task(
            ctx, mission["mission_id"], design["node_id"], summary="done"
        )
    assert no_evidence.value.code == "VERIFICATION_REQUIRED"

    evidence = service.record_evidence(
        ctx,
        mission["mission_id"],
        task_id=design["node_id"],
        evidence_type="test",
        status="PASS",
        summary="Architecture assertions passed.",
        check_name="architecture-review",
        reference="tests/test_m69_mission_runtime_foundation.py",
    )
    with pytest.raises(PlatformContextError) as no_review:
        service.complete_task(
            ctx, mission["mission_id"], design["node_id"], summary="done"
        )
    assert no_review.value.code == "REVIEW_REQUIRED"

    review = service.record_review(
        ctx,
        mission["mission_id"],
        task_id=design["node_id"],
        verdict="APPROVED",
        findings=[],
        evidence_ids=[evidence["evidence_id"]],
    )
    completed = service.complete_task(
        ctx,
        mission["mission_id"],
        design["node_id"],
        summary="Contracts reviewed and verified.",
    )
    assert completed["status"] == "COMPLETED"

    snapshot = service.get(ctx, mission["mission_id"])
    tasks = _tasks_by_title(snapshot)
    assert tasks["Implement persistence"]["status"] == "READY"
    assert tasks["Document contracts"]["status"] == "READY"
    assert snapshot["runtime"]["active_task_id"] == ""
    assert snapshot["runtime"]["usage"]["test_count"] == 1
    assert snapshot["reviews"][0]["review_id"] == review["review_id"]
    assert "findings_json" not in snapshot["reviews"][0]
    assert snapshot["dashboard"]["progress_percent"] == pytest.approx(33.3)
    checkpoint = snapshot["checkpoints"][0]
    assert design["node_id"] in checkpoint["completed_tasks"]
    assert checkpoint["resource_usage"]["test_count"] == 1


def test_cycle_secret_rbac_and_project_isolation_fail_closed(runtime_env):
    _, platform, ctx, project, mission = runtime_env
    service = MissionRuntimeService(platform)

    cyclic = _plan()
    cyclic["goals"][0]["phases"][0]["milestones"][0]["tasks"][0][
        "depends_on"
    ] = ["implement"]
    with pytest.raises(PlatformContextError) as cycle:
        service.plan(ctx, mission["mission_id"], cyclic)
    assert cycle.value.code == "VALIDATION_FAILED"
    assert service.get(ctx, mission["mission_id"])["runtime"] is None

    secret = _plan()
    secret["goals"][0]["phases"][0]["milestones"][0]["tasks"][0][
        "arguments"
    ] = {"api_key": "must-not-persist"}
    with pytest.raises(PlatformContextError) as rejected:
        service.plan(ctx, mission["mission_id"], secret)
    assert rejected.value.code == "VALIDATION_FAILED"

    viewer = PlatformExecutionContext(
        user_id="viewer",
        role="viewer",
        org_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
    )
    with pytest.raises(PlatformContextError) as denied:
        service.plan(viewer, mission["mission_id"], _plan())
    assert denied.value.code == "PERMISSION_DENIED"

    service.plan(ctx, mission["mission_id"], _plan())
    wrong_project = PlatformExecutionContext(
        user_id=ctx.user_id,
        role=ctx.role,
        org_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        project_id="prj_other",
    )
    with pytest.raises(PlatformContextError) as isolated:
        service.get(wrong_project, mission["mission_id"])
    assert isolated.value.code == "PROJECT_ISOLATION"
    assert service.list_dashboard(wrong_project) == []

    other_scope = PlatformExecutionContext(
        user_id=ctx.user_id,
        role=ctx.role,
        org_id="org_other",
        workspace_id="ws_other",
    )
    with pytest.raises(PlatformContextError) as hidden:
        service.get(other_scope, mission["mission_id"])
    assert hidden.value.code == "NOT_FOUND"
    assert service.list_dashboard(other_scope) == []


def test_invalid_transition_and_safe_replan_reset(runtime_env):
    _, platform, ctx, _, mission = runtime_env
    service = MissionRuntimeService(platform)
    first = service.plan(ctx, mission["mission_id"], _plan())
    design = _tasks_by_title(first)["Design contracts"]

    with pytest.raises(PlatformContextError) as not_running:
        service.transition_task(
            ctx, mission["mission_id"], design["node_id"], "RUNNING"
        )
    assert not_running.value.code == "INVALID_STATE"

    revised = deepcopy(_plan())
    revised["objective"] = "Revised before any task attempt."
    second = service.plan(ctx, mission["mission_id"], revised)
    assert second["runtime"]["objective"] == revised["objective"]
    assert len(second["checkpoints"]) == 1
    assert len(second["decisions"]) == 1

    service.start(ctx, mission["mission_id"])
    current_design = _tasks_by_title(service.get(ctx, mission["mission_id"]))[
        "Design contracts"
    ]
    service.transition_task(
        ctx, mission["mission_id"], current_design["node_id"], "RUNNING"
    )
    with pytest.raises(PlatformContextError) as immutable:
        service.plan(ctx, mission["mission_id"], _plan())
    assert immutable.value.code == "INVALID_STATE"

    bad_budget = _plan()
    bad_budget["budget"]["max_magic_loops"] = 1
    fresh = platform.create_mission(
        ctx,
        mission["project_id"],
        "M69-BUDGET",
        "Mission Runtime Budget Validation",
    )
    with pytest.raises(PlatformContextError) as unknown_budget:
        service.plan(ctx, fresh["mission_id"], bad_budget)
    assert unknown_budget.value.code == "VALIDATION_FAILED"
