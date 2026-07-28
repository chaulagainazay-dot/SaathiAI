from pathlib import Path

import pytest

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.ielts.models import IELTSValidationError, validate_goal, validate_payment
from saathi.platform.ielts.scoring import (
    LocalHeuristicScorer,
    SafeFallbackScorer,
    UnavailableScoringProvider,
)
from saathi.platform.ielts.service import IELTSService
from saathi.platform.models import PlatformPermission, PlatformRole, role_has_permission
from saathi.platform.store import PlatformStore


def ctx(*, user="learner", role="operator", org="org-a", workspace="ws-a", authority=""):
    return PlatformExecutionContext(
        user_id=user, role=role, org_id=org, workspace_id=workspace,
        session_id=f"session-{user}", authority=authority,
    )


@pytest.fixture
def service(tmp_path: Path):
    store = PlatformStore(tmp_path / "platform.db", now=lambda: 1000.0)
    svc = IELTSService(store)
    yield svc
    store.close()


def test_permission_namespace_is_explicit_and_not_universal():
    assert role_has_permission(PlatformRole.VIEWER, PlatformPermission.IELTS_READ)
    assert not role_has_permission(PlatformRole.VIEWER, PlatformPermission.IELTS_GOAL_MANAGE)
    assert role_has_permission(PlatformRole.OPERATOR, PlatformPermission.IELTS_GOAL_MANAGE)
    assert not role_has_permission(PlatformRole.OPERATOR, PlatformPermission.IELTS_PAYMENT_REVIEW)
    assert role_has_permission(PlatformRole.OWNER, PlatformPermission.IELTS_PAYMENT_REVIEW)


def test_domain_validation_is_bounded_and_rejects_credentials():
    assert validate_goal({
        "exam_type": "academic", "target_band": 7.5,
        "planned_test_date": "2030-01-02", "daily_minutes": 45,
    })["target_band"] == 7.5
    with pytest.raises(IELTSValidationError):
        validate_goal({"exam_type": "academic", "target_band": 7.3, "planned_test_date": "2030-01-02"})
    with pytest.raises(IELTSValidationError):
        validate_payment({
            "product": "Plan", "amount": "100", "currency": "NPR",
            "payment_method_label": "password=secret", "transaction_reference": "x",
            "evidence_ref": "ev_1",
        })


def test_profile_goal_practice_persist_and_idempotency(service):
    learner = ctx()
    profile = service.upsert_profile(
        learner, {"display_name": "Learner"}, idempotency_key="profile-1"
    )
    goal = service.create_goal(
        learner,
        {"exam_type": "academic", "target_band": 7.0,
         "planned_test_date": "2030-02-01", "daily_minutes": 30},
        idempotency_key="goal-1",
    )
    same = service.create_goal(
        learner,
        {"exam_type": "academic", "target_band": 7.0,
         "planned_test_date": "2030-02-01", "daily_minutes": 30},
        idempotency_key="goal-1",
    )
    practice = service.create_practice(
        learner,
        {"skill": "reading", "task_type": "original_fixture", "prompt": "Read an original note.",
         "response": "A,B,C", "duration_seconds": 120},
        idempotency_key="practice-1",
    )
    assert profile["record_type"] == "profile"
    assert goal["record_id"] == same["record_id"]
    assert practice["body"]["feedback"]["official"] is False
    assert service.dashboard(learner)["progress"]["practice_count"] == 1


def test_tenant_workspace_and_ownership_are_fail_closed(service):
    created = service.create_goal(
        ctx(),
        {"exam_type": "general_training", "target_band": 6.5,
         "planned_test_date": "2030-02-01"},
    )
    for other in (
        ctx(user="learner", org="org-b"),
        ctx(user="learner", workspace="ws-b"),
        ctx(user="other"),
    ):
        with pytest.raises(PlatformContextError) as exc:
            service.get(other, created["record_id"])
        assert exc.value.code == "NOT_FOUND"


def test_agent_actor_cannot_mutate_human_workflows(service):
    with pytest.raises(PlatformContextError) as exc:
        service.create_goal(
            ctx(user="agent:coach", role="system", authority="AUTONOMOUS_AGENT"),
            {"exam_type": "academic", "target_band": 7.0,
             "planned_test_date": "2030-02-01"},
        )
    assert exc.value.code == "PERMISSION_DENIED"


def test_local_scoring_is_repeatable_transparent_and_pronunciation_not_assessed():
    scorer = LocalHeuristicScorer()
    args = {"prompt": "Describe a place", "transcript": "I enjoy this place because it is calm.",
            "part": "part_2", "has_audio": False}
    first = scorer.score_speaking(**args)
    assert first == scorer.score_speaking(**args)
    assert first["official"] is False
    assert first["criteria"]["pronunciation"]["level"] == "not_assessed"
    assert first["audio_analysis_performed"] is False


def test_unavailable_or_failed_provider_uses_labelled_deterministic_fallback():
    unavailable = SafeFallbackScorer(UnavailableScoringProvider())
    args = {
        "prompt": "Describe a place",
        "response": "This original response is calm because it uses local text.",
        "task_type": "task_2",
    }
    first = unavailable.score_writing(**args)
    assert first == unavailable.score_writing(**args)
    assert first["source"] == "local_heuristic_v1"
    assert first["official"] is False
    assert first["provider_assisted"] is False
    assert first["fallback"] == {"used": True, "reason": "provider_unavailable"}
    assert unavailable.health()["provider_assisted"] == "unavailable"


def test_fixture_alert_is_labelled_and_deduplicated(service):
    learner = ctx()
    alert = service.create_alert(
        learner,
        {"exam_type": "academic", "test_format": "computer",
         "preferred_locations": ["Kathmandu"], "date_from": "2030-01-01",
         "date_to": "2030-01-31", "expires_on": "2030-01-31"},
    )
    result = service.evaluate_alerts(learner)
    assert len(result["matches"]) == 1
    assert result["live_availability"] is False
    assert result["matches"][0]["body"]["alert_id"] == alert["record_id"]
    assert service.evaluate_alerts(learner)["matches"] == []


def test_payment_requires_human_authorized_non_self_reviewer(service):
    payment = service.submit_payment(
        ctx(),
        {"product": "Local preparation plan", "amount": "1500", "currency": "NPR",
         "payment_method_label": "Bank transfer", "transaction_reference": "ref-123",
         "evidence_ref": "evidence://manual/123"},
    )
    with pytest.raises(PlatformContextError):
        service.review_payment(ctx(), payment["record_id"], approve=True, reason="same person")
    with pytest.raises(PlatformContextError):
        service.review_payment(
            ctx(user="operator-2", role="operator"), payment["record_id"],
            approve=True, reason="checked",
        )
    reviewed = service.review_payment(
        ctx(user="owner-1", role="owner"), payment["record_id"],
        approve=True, reason="Reference and evidence manually compared.",
    )
    assert reviewed["status"] == "approved"
    assert reviewed["body"]["settlement_performed"] is False
    assert reviewed["body"]["reviewer_id"] == "owner-1"


def test_restart_safe_schema_and_persistence(tmp_path):
    path = tmp_path / "platform.db"
    first = PlatformStore(path, now=lambda: 1000.0)
    created = IELTSService(first).create_goal(
        ctx(),
        {"exam_type": "academic", "target_band": 7.0,
         "planned_test_date": "2030-02-01"},
    )
    first.close()
    second = PlatformStore(path, now=lambda: 1001.0)
    assert IELTSService(second).get(ctx(), created["record_id"])["version"] == 1
    second.close()
