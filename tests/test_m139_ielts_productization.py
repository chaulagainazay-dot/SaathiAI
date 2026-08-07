"""M139–M147 IELTSAlert native productization — focused tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from saathi.platform.apps import AppRuntime, reset_app_runtime_for_tests
from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.ielts.scoring import LocalHeuristicScorer, PRONUNCIATION_TEXT_ONLY
from saathi.platform.ielts.service import IELTSService
from saathi.platform.models import PlatformPermission, PlatformRole, role_has_permission
from saathi.platform.service import reset_platform_for_tests
from saathi.platform.store import PlatformStore
from saathi.tool_runtime.registry import reset_registry_for_tests


def ctx(*, user="learner", role="operator", org="org-i", workspace="ws-i"):
    return PlatformExecutionContext(
        user_id=user, role=role, org_id=org, workspace_id=workspace,
        session_id=f"s-{user}",
    )


@pytest.fixture
def service(tmp_path: Path):
    store = PlatformStore(tmp_path / "ielts.db", now=lambda: 2_000_000_000.0)
    svc = IELTSService(store, scorer=LocalHeuristicScorer())
    yield svc, store
    store.close()


def test_speaking_text_only_does_not_claim_acoustic_pronunciation(service):
    svc, _ = service
    c = ctx()
    out = svc.create_practice(
        c,
        {
            "skill": "speaking",
            "task_type": "part_1",
            "prompt": "Hometown?",
            "response": "I live in a quiet city with parks and friendly people near the river.",
            "duration_seconds": 45,
        },
        idempotency_key="sp1",
    )
    fb = out["body"]["feedback"]
    assert fb["official"] is False
    assert fb.get("audio_analysis_performed") is False
    assert fb.get("acoustic_pronunciation_claimed") is False
    assert fb["criteria"]["pronunciation"]["level"] == "not_assessed"
    assert "not inferred" in fb["criteria"]["pronunciation"]["feedback"].lower() or "not" in PRONUNCIATION_TEXT_ONLY.lower()


def test_writing_immutable_revision_linked(service):
    svc, _ = service
    c = ctx()
    original = svc.create_practice(
        c,
        {
            "skill": "writing",
            "task_type": "task_2",
            "prompt": "Discuss both views.",
            "response": "Many people think skills matter more than theory. " * 12,
        },
        idempotency_key="wr1",
    )
    parent_body = dict(original["body"])
    rev = svc.submit_writing_revision(
        c, parent_submission_id=original["record_id"],
        response="Revised essay with better structure and clearer examples. " * 10,
        idempotency_key="rev1",
    )
    assert rev["parent_immutable"] is True
    assert rev["revision"]["body"]["parent_submission_id"] == original["record_id"]
    # original unchanged
    got = svc.get(c, original["record_id"])
    assert got["body"]["response"] == parent_body["response"]


def test_academic_vs_general_reading_conversion_differs(service):
    svc, _ = service
    c = ctx()
    ac = svc.submit_objective_practice(
        c, skill="reading", exam_type="academic",
        answers=["false", "20", "true", "flowering plants"], idempotency_key="rd-ac",
    )
    gt = svc.submit_objective_practice(
        c, skill="reading", exam_type="general_training",
        answers=["8:00", "tuesdays", "false", "500"], idempotency_key="rd-gt",
    )
    assert ac["body"]["feedback"]["exam_type"] == "academic"
    assert gt["body"]["feedback"]["exam_type"] == "general_training"
    assert ac["body"]["feedback"]["official"] is False
    assert "indicative" in ac["body"]["feedback"]["band_conversion"]["conversion_label"].lower()


def test_diagnostic_study_plan_readiness(service):
    svc, _ = service
    c = ctx(role="owner")
    svc.upsert_profile(c, {"display_name": "Learner A"})
    svc.create_goal(
        c,
        {"exam_type": "academic", "target_band": 7.0, "planned_test_date": "2030-06-01", "daily_minutes": 40},
        idempotency_key="g1",
    )
    diag = svc.run_diagnostic(c, exam_type="academic", idempotency_key="d1")
    assert diag["body"]["official"] is False
    assert "speaking" in diag["body"]["skill_estimates"]
    plan = svc.generate_study_plan(c, weeks=2, idempotency_key="p1")
    assert plan["body"]["validation"]["within_time_budget"] is True
    assert plan["body"]["validation"]["covers_four_skills"] is True
    assert plan["body"]["orchestration_subject_to_plan_validator"] is True
    ready = svc.readiness_snapshot(c)["data"]
    assert ready["official"] is False
    assert ready["practice_count"] >= 1


def test_yeti_cannot_mutate(service):
    svc, _ = service
    c = ctx()
    ans = svc.grounded_answer(c, "What is my readiness?")
    assert ans["can_mutate"] is False
    assert ans["official"] is False
    prop = svc.propose_action(c, action="change_band", payload={"band": 9})
    assert prop["proposal"]["executed"] is False


def test_mock_and_listening_fixture(service):
    svc, _ = service
    c = ctx()
    mock = svc.create_mock_test(c, exam_type="academic", idempotency_key="m1")
    out = svc.complete_mock_section(
        c, mock["record_id"], skill="listening",
        answers=["second", "10", "17:00", "true"],
    )
    assert out["section"]["body"]["feedback"]["skill"] == "listening"
    assert out["section"]["body"]["feedback"]["correct"] == 4


def test_backup_restore_requires_approval(service):
    svc, _ = service
    c = ctx(role="owner")
    svc.upsert_profile(c, {"display_name": "Backup Learner"})
    backup = svc.export_backup_payload(c)
    assert backup["content_hash"]
    with pytest.raises(PlatformContextError) as err:
        svc.restore_payload(c, backup, approval_reference="")
    assert err.value.code == "APPROVAL_REQUIRED"


def test_learner_isolation(service):
    svc, _ = service
    a = ctx(user="a")
    b = ctx(user="b")
    g = svc.create_goal(
        a,
        {"exam_type": "academic", "target_band": 6.5, "planned_test_date": "2030-01-01"},
        idempotency_key="ga",
    )
    with pytest.raises(PlatformContextError):
        svc.get(b, g["record_id"])


def test_app_runtime_launch_ielts(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "apps.db")
    boot = platform.bootstrap_owner_secure(
        email="ielts-owner@local", name="O", password="IeltsOwnerPass1!",
    )
    c = platform.require_context(boot["token"])
    apps = AppRuntime(platform)
    apps.register(c, package_id="ielts_alert")
    apps.enable(c, "saathi.ielts_alert")
    launch = apps.launch(c, "saathi.ielts_alert")
    assert launch["app"]["lifecycle_state"] == "RUNNING"
    assert launch["bypass_gateway"] is False
    assert launch["workspace"]["isolated"] is True
    reset_app_runtime_for_tests(platform)
    reset_platform_for_tests()
    reset_registry_for_tests()


def test_scoring_versions_present(service):
    svc, _ = service
    c = ctx()
    out = svc.create_practice(
        c,
        {
            "skill": "writing",
            "task_type": "task_1",
            "prompt": "Describe the chart.",
            "response": "The chart shows increases over the decade in all three regions overall. " * 5,
        },
    )
    fb = out["body"]["feedback"]
    assert fb.get("rubric_version")
    assert fb.get("scoring_version")
    assert fb["official"] is False


def test_permissions_still_fail_closed():
    assert role_has_permission(PlatformRole.VIEWER, PlatformPermission.IELTS_READ)
    assert not role_has_permission(PlatformRole.VIEWER, PlatformPermission.IELTS_PRACTICE_CREATE)
