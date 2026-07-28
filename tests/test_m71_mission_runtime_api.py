"""M71 authenticated Autonomous Mission Runtime HTTP contracts."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests


@pytest.fixture()
def api_env(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "m71.db")
    boot = platform.bootstrap_owner_secure(
        email="owner@m71.local",
        name="Mission Owner",
        password="GoodPassw0rd!",
    )
    ctx = platform.require_context(boot["token"])
    project = platform.create_project(ctx, "M71 API")
    mission = platform.create_mission(
        ctx, project["project_id"], "M71", "Mission Runtime API"
    )
    from saathi.server import app

    return (
        platform,
        boot["token"],
        ctx,
        project,
        mission,
        TestClient(app),
    )


def _definition(*, tool_id: str = "m49.echo_readonly") -> dict:
    return {
        "objective": "Prove authenticated mission runtime APIs.",
        "max_parallel_tasks": 1,
        "budget": {
            "estimated_effort": 4,
            "max_elapsed_seconds": 600,
            "max_token_estimate": 1000,
            "max_commits": 2,
            "max_tests": 4,
            "max_browser_runs": 2,
            "max_cycles": 10,
            "max_no_progress_cycles": 2,
        },
        "goals": [
            {
                "title": "API",
                "phases": [
                    {
                        "title": "Delivery",
                        "milestones": [
                            {
                                "title": "Runtime",
                                "tasks": [
                                    {
                                        "id": "api-task",
                                        "title": "Execute API task",
                                        "agent_type": "TestAgent",
                                        "tool_id": tool_id,
                                        "arguments": {"text": "m71"},
                                        "estimated_effort": 1,
                                        "token_estimate": 100,
                                        "verification": [],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_authenticated_plan_dashboard_detail_and_run(api_env):
    platform, token, _, _, mission, client = api_env
    base = f"/api/v1/platform/missions/{mission['mission_id']}/runtime"
    headers = {"X-Platform-Token": token}

    assert client.get(base).status_code == 401
    before = client.get(base, headers=headers)
    assert before.status_code == 200
    assert before.json()["runtime"] is None

    planned = client.put(
        f"{base}/plan",
        headers=headers,
        json={"definition": _definition()},
    )
    assert planned.status_code == 200
    assert planned.json()["runtime"]["state"] == "PLANNED"
    assert planned.json()["dashboard"]["health"] == "IDLE"
    assert planned.json()["tasks"][0]["status"] == "READY"

    dashboards = client.get(
        "/api/v1/platform/mission-runtimes/dashboard", headers=headers
    )
    assert dashboards.status_code == 200
    summary = dashboards.json()["mission_runtimes"][0]
    assert summary["mission_id"] == mission["mission_id"]
    assert summary["progress_percent"] == 0.0
    assert summary["task_counts"]["ready"] == 1

    executed = client.post(
        f"{base}/run",
        headers=headers,
        json={"max_cycles": 2, "timeout_sec": 30},
    )
    assert executed.status_code == 200
    assert executed.json()["stop_condition"] == "MISSION_EXECUTION_COMPLETE"

    detail = client.get(base, headers=headers).json()
    assert detail["runtime"]["state"] == "COMPLETED"
    assert detail["dashboard"]["progress_percent"] == 100.0
    assert detail["dashboard"]["health"] == "COMPLETE"
    assert detail["tasks"][0]["execution_id"].startswith("pex_")
    assert detail["evidence"][0]["status"] == "PASS"
    assert token not in str(detail)
    events = {
        item["event"]
        for item in platform.store.list_audit(
            org_id=detail["runtime"]["org_id"], limit=200
        )
    }
    assert "runtime.dispatch_started" in events


def test_api_validation_control_and_checkpoint_contracts(api_env):
    platform, token, ctx, project, mission, client = api_env
    headers = {"X-Platform-Token": token}
    base = f"/api/v1/platform/missions/{mission['mission_id']}/runtime"

    unsafe = _definition()
    unsafe["goals"][0]["phases"][0]["milestones"][0]["tasks"][0][
        "arguments"
    ] = {"authorization": "must-not-persist"}
    rejected = client.put(
        f"{base}/plan",
        headers=headers,
        json={"definition": unsafe},
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"]["code"] == "VALIDATION_FAILED"

    planned = client.put(
        f"{base}/plan",
        headers=headers,
        json={"definition": _definition()},
    )
    assert planned.status_code == 200
    task_id = planned.json()["tasks"][0]["node_id"]
    invalid_reviewer = client.post(
        f"{base}/reviews",
        headers=headers,
        json={
            "task_id": task_id,
            "verdict": "APPROVED",
            "findings": [],
            "reviewer_agent": "UnboundedAgent",
        },
    )
    assert invalid_reviewer.status_code == 400
    assert invalid_reviewer.json()["detail"]["code"] == "VALIDATION_FAILED"
    paused = client.post(
        f"{base}/pause", headers=headers, json={"reason": "API checkpoint"}
    )
    assert paused.status_code == 200
    assert paused.json()["runtime"]["state"] == "PAUSED"
    resumed = client.post(f"{base}/resume", headers=headers)
    assert resumed.status_code == 200
    assert resumed.json()["runtime"]["state"] == "RUNNING"
    checkpoint = client.post(
        f"{base}/checkpoints",
        headers=headers,
        json={
            "latest_commit": "abc123",
            "rollback_sha": "def456",
            "test_status": "PASS",
            "browser_status": "PASS",
            "known_blockers": [],
        },
    )
    assert checkpoint.status_code == 200
    assert checkpoint.json()["checkpoint"]["latest_commit"] == "abc123"

    cancellable = platform.create_mission(
        ctx, project["project_id"], "M71-CANCEL", "API cancellation"
    )
    cancel_base = (
        f"/api/v1/platform/missions/{cancellable['mission_id']}/runtime"
    )
    assert (
        client.put(
            f"{cancel_base}/plan",
            headers=headers,
            json={"definition": _definition()},
        ).status_code
        == 200
    )
    cancelled = client.post(f"{cancel_base}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["runtime"]["state"] == "CANCELLED"
    assert cancelled.json()["tasks"][0]["status"] == "CANCELLED"


def test_api_not_found_scope_and_bounded_run_fail_closed(api_env):
    _, token, _, _, mission, client = api_env
    headers = {"X-Platform-Token": token}
    missing = client.get(
        "/api/v1/platform/missions/mis_missing/runtime", headers=headers
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "NOT_FOUND"

    base = f"/api/v1/platform/missions/{mission['mission_id']}/runtime"
    assert (
        client.put(
            f"{base}/plan",
            headers=headers,
            json={"definition": _definition(tool_id="")},
        ).status_code
        == 200
    )
    bounded = client.post(
        f"{base}/run", headers=headers, json={"max_cycles": 1}
    )
    assert bounded.status_code == 200
    assert bounded.json()["stop_condition"] == "BLOCKED_EXTERNAL_INPUT"
    assert bounded.json()["cycles_run"] == 1

    too_many = client.post(
        f"{base}/run", headers=headers, json={"max_cycles": 1000}
    )
    assert too_many.status_code == 422
