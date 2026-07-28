"""M72 fail-closed Autonomous Mission Runtime certification contracts."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from saathi.platform.context import PlatformContextError
from saathi.platform.mission_runtime.orchestrator import MissionRuntimeOrchestrator
from saathi.platform.mission_runtime.service import MissionRuntimeService
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests


@pytest.fixture()
def certification_env(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "m72.db")
    boot = platform.bootstrap_owner_secure(
        email="owner@m72.local",
        name="Certification Owner",
        password="GoodPassw0rd!",
    )
    token = boot["token"]
    ctx = platform.require_context(token)
    project = platform.create_project(ctx, "M72 Certification")
    mission = platform.create_mission(
        ctx, project["project_id"], "M72", "Mission Runtime Certification"
    )
    from saathi.server import app

    return platform, token, ctx, project, mission, TestClient(app)


def _plan() -> dict:
    return {
        "objective": "Prove fail-closed final certification.",
        "max_parallel_tasks": 1,
        "budget": {
            "estimated_effort": 8,
            "max_elapsed_seconds": 1200,
            "max_token_estimate": 2000,
            "max_commits": 3,
            "max_tests": 5,
            "max_browser_runs": 3,
            "max_cycles": 20,
            "max_no_progress_cycles": 3,
        },
        "goals": [
            {
                "title": "Certification",
                "phases": [
                    {
                        "title": "Final gate",
                        "milestones": [
                            {
                                "title": "Certify",
                                "tasks": [
                                    {
                                        "id": "certify-task",
                                        "title": "Produce reviewed evidence",
                                        "agent_type": "TestAgent",
                                        "tool_id": "m49.echo_readonly",
                                        "arguments": {"text": "m72"},
                                        "estimated_effort": 1,
                                        "token_estimate": 100,
                                        "requires_review": True,
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


def _complete_reviewed_mission(platform, token, ctx, mission):
    service = MissionRuntimeService(platform)
    service.plan(ctx, mission["mission_id"], _plan())
    first = MissionRuntimeOrchestrator(platform).run_until_stop(
        ctx, mission["mission_id"], token=token, max_cycles=1
    )
    assert first["stop_condition"] == "BLOCKED_EXTERNAL_INPUT"
    assert first["last_cycle"]["post_decision"]["action"] == "REVIEW"
    detail = service.get(ctx, mission["mission_id"])
    task = detail["tasks"][0]
    execution_evidence = next(
        item
        for item in detail["evidence"]
        if item["task_id"] == task["node_id"]
        and item["evidence_type"] == "execution"
    )
    service.record_review(
        ctx,
        mission["mission_id"],
        task_id=task["node_id"],
        verdict="APPROVED",
        findings=[],
        evidence_ids=[execution_evidence["evidence_id"]],
    )
    second = MissionRuntimeOrchestrator(platform).run_until_stop(
        ctx, mission["mission_id"], token=token, max_cycles=2
    )
    assert second["stop_condition"] == "MISSION_EXECUTION_COMPLETE"
    assert service.get(ctx, mission["mission_id"])["runtime"]["state"] == "COMPLETED"
    return service, task, execution_evidence


def _record_final_evidence(service, ctx, mission_id):
    evidence = []
    for evidence_type, check_name in (
        ("test", "backend-and-frontend-tests"),
        ("browser", "production-browser-certification"),
        ("security", "security-review"),
        ("regression", "regression-review"),
        ("documentation", "documentation-complete"),
        ("commit", "local-commit"),
    ):
        evidence.append(
            service.record_evidence(
                ctx,
                mission_id,
                evidence_type=evidence_type,
                status="PASS",
                summary=f"{check_name} passed.",
                check_name=check_name,
                reference=f"local://{check_name}",
                collected_by="CertificationAgent",
            )
        )
    service.create_checkpoint(
        ctx,
        mission_id,
        created_by="CertificationAgent",
        latest_commit="abc1234",
        rollback_sha="def5678",
        test_status="PASS",
        browser_status="PASS",
        known_blockers=[],
    )
    return evidence


def test_certification_requires_verified_checkpoint_review_and_evidence(
    certification_env,
):
    platform, token, ctx, _, mission, _ = certification_env
    service, _, execution_evidence = _complete_reviewed_mission(
        platform, token, ctx, mission
    )

    with pytest.raises(PlatformContextError) as incomplete_checkpoint:
        service.certify(
            ctx,
            mission["mission_id"],
            verdict="MISSION_RUNTIME_COMPLETE",
            summary="Not enough evidence.",
            evidence_ids=[execution_evidence["evidence_id"]],
        )
    assert incomplete_checkpoint.value.code == "VERIFICATION_REQUIRED"

    final_evidence = _record_final_evidence(
        service, ctx, mission["mission_id"]
    )
    evidence_ids = [
        execution_evidence["evidence_id"],
        *(item["evidence_id"] for item in final_evidence),
    ]
    failed = service.record_evidence(
        ctx,
        mission["mission_id"],
        evidence_type="security",
        status="FAIL",
        summary="Deliberate negative certification fixture.",
        check_name="negative-gate",
    )
    with pytest.raises(PlatformContextError) as failed_evidence:
        service.certify(
            ctx,
            mission["mission_id"],
            verdict="MISSION_RUNTIME_COMPLETE",
            summary="Must fail closed.",
            evidence_ids=[*evidence_ids, failed["evidence_id"]],
        )
    assert failed_evidence.value.code == "VERIFICATION_REQUIRED"

    certified = service.certify(
        ctx,
        mission["mission_id"],
        verdict="MISSION_RUNTIME_COMPLETE",
        summary="All bounded gates passed.",
        evidence_ids=evidence_ids,
        limitations=["Single-host execution remains explicit."],
    )
    assert certified["runtime"]["state"] == "CERTIFIED"
    assert certified["dashboard"]["health"] == "COMPLETE"
    assert certified["certification"]["verdict"] == "MISSION_RUNTIME_COMPLETE"
    assert certified["certification"]["certified_by"].startswith(
        "CertificationAgent:"
    )
    assert len(certified["certification"]["snapshot_hash"]) == 64


def test_certification_is_atomic_immutable_and_restart_persistent(
    certification_env,
):
    platform, token, ctx, _, mission, _ = certification_env
    service, _, execution_evidence = _complete_reviewed_mission(
        platform, token, ctx, mission
    )
    final_evidence = _record_final_evidence(
        service, ctx, mission["mission_id"]
    )
    evidence_ids = [
        execution_evidence["evidence_id"],
        *(item["evidence_id"] for item in final_evidence),
    ]
    certified = service.certify(
        ctx,
        mission["mission_id"],
        verdict="MISSION_RUNTIME_COMPLETE",
        summary="Atomic terminal certificate.",
        evidence_ids=evidence_ids,
    )

    restarted = reset_platform_for_tests(platform.store.db_path)
    restarted_ctx = restarted.require_context(token)
    snapshot = MissionRuntimeService(restarted).get(
        restarted_ctx, mission["mission_id"]
    )
    assert snapshot["runtime"]["state"] == "CERTIFIED"
    assert snapshot["certifications"] == [certified["certification"]]

    with pytest.raises(PlatformContextError) as immutable:
        MissionRuntimeService(restarted).certify(
            restarted_ctx,
            mission["mission_id"],
            verdict="MISSION_RUNTIME_COMPLETE",
            summary="A second certificate must not be appended.",
            evidence_ids=evidence_ids,
        )
    assert immutable.value.code == "INVALID_STATE"
    assert len(
        MissionRuntimeService(restarted)
        .get(restarted_ctx, mission["mission_id"])["certifications"]
    ) == 1


def test_certification_api_auth_validation_and_audit(certification_env):
    platform, token, ctx, _, mission, client = certification_env
    service, _, execution_evidence = _complete_reviewed_mission(
        platform, token, ctx, mission
    )
    final_evidence = _record_final_evidence(
        service, ctx, mission["mission_id"]
    )
    evidence_ids = [
        execution_evidence["evidence_id"],
        *(item["evidence_id"] for item in final_evidence),
    ]
    path = (
        f"/api/v1/platform/missions/{mission['mission_id']}"
        "/runtime/certifications"
    )
    body = {
        "verdict": "MISSION_RUNTIME_COMPLETE",
        "summary": "Authenticated certification API passed.",
        "evidence_ids": evidence_ids,
        "limitations": [],
    }
    assert client.post(path, json=body).status_code == 401
    invalid = client.post(
        path,
        headers={"X-Platform-Token": token},
        json={**body, "verdict": "BYPASS_SAFETY"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == "VALIDATION_FAILED"

    response = client.post(
        path, headers={"X-Platform-Token": token}, json=body
    )
    assert response.status_code == 200
    assert response.json()["runtime"]["state"] == "CERTIFIED"
    assert token not in str(response.json())
    events = {
        item["event"]
        for item in platform.store.list_audit(org_id=ctx.org_id, limit=200)
    }
    assert "mission_runtime.certified" in events
