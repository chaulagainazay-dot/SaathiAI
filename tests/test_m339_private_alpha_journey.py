"""M339 — certified end-to-end private-alpha journey.

Runs the whole journey once and asserts against the resulting report, so a
regression anywhere in identity, RBAC, approvals, mission lifecycle, audit,
observability or session revocation surfaces here.
"""
from __future__ import annotations

import pytest

from saathi.platform.private_alpha.journey import run_private_alpha_journey

REQUIRED_STAGES = (
    "identity_and_session",
    "rbac",
    "approvals",
    "mission_lifecycle",
    "evidence_and_audit",
    "operations",
    "session_revocation_and_signout",
)

# A refusal that surfaces as a programming error proves nothing about the
# security boundary — it only proves the call was malformed.
INVALID_REFUSAL_TYPES = {"TypeError", "AttributeError", "NameError", "KeyError", "IndexError"}


@pytest.fixture(scope="module")
def journey(tmp_path_factory):
    return run_private_alpha_journey(
        db_path=tmp_path_factory.mktemp("m339") / "journey.db",
        write_evidence=False,
    )


def test_journey_passes(journey):
    assert journey["verdict"] == "PRIVATE_ALPHA_E2E_JOURNEY_PASSED", journey["failed_steps"]
    assert journey["failed"] == 0


def test_all_required_stages_ran_and_passed(journey):
    for stage in REQUIRED_STAGES:
        assert stage in journey["stages"], f"stage {stage} did not run"
        assert journey["stages"][stage]["status"] == "PASS", journey["stages"][stage]


def test_journey_exercises_both_arms(journey):
    """A journey with no refused operations proves nothing about fail-closed."""
    assert journey["positive_steps"] >= 25
    assert journey["negative_steps"] >= 15
    assert journey["assertions"] >= 15


def test_every_refusal_is_a_real_authorization_failure(journey):
    negatives = [s for s in journey["steps"] if s["kind"] == "negative"]
    assert negatives
    for step in negatives:
        assert step["ok"] is True, f"{step['step']} was permitted but must be refused"
        assert step["refused_with"] not in INVALID_REFUSAL_TYPES, (
            f"{step['step']} was 'refused' by a programming error "
            f"({step['refused_with']}), which does not prove the boundary holds"
        )


@pytest.mark.parametrize(
    "step_name,expected_code",
    [
        ("anonymous_access_refused", "ANONYMOUS_PROHIBITED"),
        ("invalid_token_refused", "SESSION_INVALID"),
        ("invalid_password_login_refused", "AUTH_FAILED"),
        ("reused_invite_refused", "INVITE_NOT_PENDING"),
        ("expired_session_refused", "SESSION_INVALID"),
        ("viewer_cannot_create_project", "PERMISSION_DENIED"),
        ("foreign_project_refused", "PROJECT_ISOLATION"),
        ("unauthorized_workspace_access_refused", "WORKSPACE_ISOLATION"),
        ("cross_organization_workspace_switch_refused", "MEMBERSHIP_REVOKED"),
        ("cross_organization_project_access_refused", "PROJECT_ISOLATION"),
        ("self_approval_blocked_maker_checker", "PERMISSION_DENIED"),
        ("viewer_cannot_approve", "PERMISSION_DENIED"),
        ("revoked_approval_cannot_authorize_execution", "APPROVAL_REVOKED"),
        ("expired_approval_cannot_authorize_execution", "APPROVAL_EXPIRED"),
        ("approval_does_not_grant_unrelated_authority", "APPROVAL_TOOL_MISMATCH"),
        ("mutating_tool_without_approval_refused", "APPROVAL_REQUIRED"),
        ("revoked_session_cannot_authenticate", "SESSION_INVALID"),
        ("signed_out_session_cannot_authenticate", "SESSION_INVALID"),
    ],
)
def test_refusal_codes_are_specific(journey, step_name, expected_code):
    """Each boundary must fail closed for its own documented reason."""
    matches = [s for s in journey["steps"] if s["step"] == step_name]
    assert matches, f"{step_name} did not run"
    assert matches[0]["refused_with"] == expected_code


def test_runtime_stayed_local_and_offline(journey):
    boundary = journey["runtime_boundary"]
    assert boundary["external_provider_calls"] == 0
    assert boundary["network_calls"] == 0
    assert boundary["all_tools_local_deterministic"] is True
    assert boundary["mock_providers_only"] is True


def test_journey_grants_no_authority(journey):
    for key, value in journey["authority"].items():
        assert value is False, f"{key} must remain false"


def test_evidence_is_written_when_requested(tmp_path):
    out = tmp_path / "journey_evidence.json"
    report = run_private_alpha_journey(
        db_path=tmp_path / "ev.db", write_evidence=True, evidence_path=out
    )
    assert out.is_file()
    assert report["verdict"] == "PRIVATE_ALPHA_E2E_JOURNEY_PASSED"
    assert out.read_text(encoding="utf-8").strip().startswith("{")
