"""M348 — Structured meetings, bounded submissions and preserved disagreement."""
from __future__ import annotations

from pathlib import Path

import pytest

from saathi.agentdev.artifacts import (
    ArtifactKind,
    ArtifactStore,
    Claim,
    make_artifact,
)
from saathi.agentdev.meetings import (
    ACCEPTS_ADDITIONAL_ENGINEERS,
    REQUIRED_PARTICIPANTS,
    MeetingError,
    MeetingOutcome,
    MeetingPhase,
    MeetingRunner,
    MeetingType,
    disagreement_template,
    required_participants,
)
from saathi.agentdev.missions import DevMissionStore
from saathi.agentdev.roles import get_role

SHA = "53b9b20736d5acf4a7ca3a9bd25b68d01e666a5d"


@pytest.fixture
def runner(tmp_path: Path):
    root = tmp_path / "agentdev"
    return MeetingRunner(ArtifactStore(root), DevMissionStore(root), root=root)


@pytest.fixture
def mission(runner: MeetingRunner):
    return runner.missions.create(
        title="Evaluate agent-behaviour evaluation coverage",
        objective="Decide whether SaathiOS should adopt it.",
        starting_sha=SHA,
    )


def _meeting(runner: MeetingRunner, mission, **overrides):
    kwargs = {
        "dev_mission_id": mission.dev_mission_id,
        "meeting_type": MeetingType.RESEARCH_REVIEW,
        "chair": "program-manager",
        "questions": ["Is the evidence sufficient to design against?"],
        "repository_sha": SHA,
    }
    kwargs.update(overrides)
    return runner.create(**kwargs)


def _findings(mission_id: str, author: str = "research", **overrides):
    payload = {
        "mission_id": mission_id,
        "kind": ArtifactKind.RESEARCH_FINDINGS,
        "authoring_agent": author,
        "repository_sha": SHA,
        "title": "Findings",
        "required_next_action": "architecture review",
        "claims": [
            Claim(
                claim_id="c1", statement="343 test files exist.", kind="fact",
                evidence_ref="tests/",
            )
        ],
        "payload": {"not_investigated": []},
    }
    payload.update(overrides)
    return make_artifact(**payload)


def _challenge(mission_id: str, target: str, author: str = "security-governance"):
    body = disagreement_template()
    body.update({
        "claim": "The finding does not cover authority boundaries.",
        "evidence": "No claim mentions the approval chain.",
        "counterargument": "Behaviour coverage without authority coverage is partial.",
        "failure_mode": "An unauthorized action passes unnoticed.",
        "risk": "Governance regression ships undetected.",
        "alternative": "Add authority scenarios to the first suite.",
        "decision_required": "Must authority scenarios be in scope?",
    })
    return make_artifact(
        mission_id=mission_id,
        kind=ArtifactKind.CHALLENGE,
        authoring_agent=author,
        repository_sha=SHA,
        title="Authority coverage challenge",
        required_next_action="research responds",
        dependencies=[target],
        payload=body,
    )


def _response(mission_id: str, challenge_id: str, author: str = "research"):
    return make_artifact(
        mission_id=mission_id,
        kind=ArtifactKind.RESPONSE,
        authoring_agent=author,
        repository_sha=SHA,
        title="Response on authority coverage",
        required_next_action="chair synthesizes",
        dependencies=[challenge_id],
        payload={"position": "accepted", "detail": "Authority scenarios added."},
    )


def _advance_to(runner, mission, meeting, phase: MeetingPhase):
    order = [
        MeetingPhase.COLLECTING,
        MeetingPhase.CHALLENGING,
        MeetingPhase.RESPONDING,
        MeetingPhase.SYNTHESIZING,
    ]
    for step in order:
        meeting = runner.open_phase(
            mission.dev_mission_id, meeting.meeting_id, step, actor=meeting.chair
        )
        if step is phase:
            break
    return meeting


# --------------------------------------------------------------------------
# Meeting types and participants
# --------------------------------------------------------------------------


def test_the_five_required_meeting_types_exist():
    assert {t.value for t in MeetingType} == {
        "research_review",
        "architecture_council",
        "implementation_planning",
        "red_team_review",
        "executive_decision",
    }


@pytest.mark.parametrize("meeting_type", list(MeetingType))
def test_every_required_participant_is_a_declared_role(meeting_type):
    for role_id in required_participants(meeting_type):
        assert get_role(role_id) is not None, role_id


def test_red_team_review_requires_security_testing_review_and_architecture():
    assert set(REQUIRED_PARTICIPANTS[MeetingType.RED_TEAM_REVIEW]) == {
        "security-governance", "testing-verification", "code-review", "architecture",
    }


def test_executive_decision_requires_the_ceo():
    assert "ceo" in REQUIRED_PARTICIPANTS[MeetingType.EXECUTIVE_DECISION]


def test_a_meeting_seats_every_required_participant(runner, mission):
    meeting = _meeting(runner, mission)
    for role_id in REQUIRED_PARTICIPANTS[MeetingType.RESEARCH_REVIEW]:
        assert role_id in meeting.participants


def test_only_a_chairing_role_may_chair(runner, mission):
    with pytest.raises(MeetingError) as exc:
        _meeting(runner, mission, chair="research")
    assert exc.value.code == "chair_cannot_chair"


def test_an_unknown_chair_is_refused(runner, mission):
    with pytest.raises(MeetingError) as exc:
        _meeting(runner, mission, chair="ghost")
    assert exc.value.code == "unknown_chair"


def test_a_chair_outside_the_participant_list_is_refused(runner, mission):
    with pytest.raises(MeetingError) as exc:
        _meeting(runner, mission, chair="ceo")
    assert exc.value.code == "chair_not_a_participant"


def test_implementation_planning_accepts_the_assigned_engineers(runner, mission):
    meeting = _meeting(
        runner,
        mission,
        meeting_type=MeetingType.IMPLEMENTATION_PLANNING,
        chair="program-manager",
        extra_participants=["backend-engineering"],
    )
    assert "backend-engineering" in meeting.participants
    assert MeetingType.IMPLEMENTATION_PLANNING in ACCEPTS_ADDITIONAL_ENGINEERS


def test_other_meeting_types_refuse_extra_participants(runner, mission):
    with pytest.raises(MeetingError) as exc:
        _meeting(runner, mission, extra_participants=["documentation"])
    assert exc.value.code == "unexpected_participants"


def test_an_agenda_without_questions_is_refused(runner, mission):
    with pytest.raises(MeetingError) as exc:
        _meeting(runner, mission, questions=[])
    assert exc.value.code == "agenda_without_questions"


def test_creating_a_meeting_writes_an_agenda_artifact(runner, mission):
    meeting = _meeting(runner, mission)
    agenda = runner.artifacts.get(mission.dev_mission_id, meeting.agenda_artifact_id)
    assert agenda is not None
    assert agenda.kind == ArtifactKind.MEETING_AGENDA.value
    assert agenda.payload["questions"] == meeting.questions


# --------------------------------------------------------------------------
# Phases
# --------------------------------------------------------------------------


def test_phases_run_in_order(runner, mission):
    meeting = _meeting(runner, mission)
    assert meeting.phase == MeetingPhase.AGENDA.value
    meeting = runner.open_phase(
        mission.dev_mission_id, meeting.meeting_id, MeetingPhase.COLLECTING,
        actor="program-manager",
    )
    assert meeting.phase == MeetingPhase.COLLECTING.value


def test_phases_cannot_be_skipped(runner, mission):
    meeting = _meeting(runner, mission)
    with pytest.raises(MeetingError) as exc:
        runner.open_phase(
            mission.dev_mission_id, meeting.meeting_id, MeetingPhase.RESPONDING,
            actor="program-manager",
        )
    assert exc.value.code == "phase_out_of_order"


def test_only_the_chair_changes_phase(runner, mission):
    meeting = _meeting(runner, mission)
    with pytest.raises(MeetingError) as exc:
        runner.open_phase(
            mission.dev_mission_id, meeting.meeting_id, MeetingPhase.COLLECTING,
            actor="research",
        )
    assert exc.value.code == "phase_change_by_non_chair"


def test_challenging_requires_at_least_one_submission(runner, mission):
    meeting = _meeting(runner, mission)
    runner.open_phase(
        mission.dev_mission_id, meeting.meeting_id, MeetingPhase.COLLECTING,
        actor="program-manager",
    )
    with pytest.raises(MeetingError) as exc:
        runner.open_phase(
            mission.dev_mission_id, meeting.meeting_id, MeetingPhase.CHALLENGING,
            actor="program-manager",
        )
    assert exc.value.code == "no_submissions_collected"


# --------------------------------------------------------------------------
# Bounded submissions
# --------------------------------------------------------------------------


def test_submissions_are_bounded_per_participant(runner, mission):
    meeting = _meeting(runner, mission, max_submissions_per_participant=2)
    meeting = _advance_to(runner, mission, meeting, MeetingPhase.COLLECTING)
    for _ in range(2):
        runner.submit(
            mission.dev_mission_id, meeting.meeting_id, _findings(mission.dev_mission_id)
        )
    with pytest.raises(MeetingError) as exc:
        runner.submit(
            mission.dev_mission_id, meeting.meeting_id, _findings(mission.dev_mission_id)
        )
    assert exc.value.code == "submission_bound_exceeded"


def test_a_non_participant_cannot_submit(runner, mission):
    meeting = _meeting(runner, mission)
    meeting = _advance_to(runner, mission, meeting, MeetingPhase.COLLECTING)
    with pytest.raises(MeetingError) as exc:
        runner.submit(
            mission.dev_mission_id,
            meeting.meeting_id,
            _findings(mission.dev_mission_id, author="documentation"),
        )
    assert exc.value.code == "submission_from_non_participant"


def test_a_challenge_cannot_be_submitted_during_collection(runner, mission):
    meeting = _meeting(runner, mission)
    meeting = _advance_to(runner, mission, meeting, MeetingPhase.COLLECTING)
    findings = _findings(mission.dev_mission_id)
    runner.submit(mission.dev_mission_id, meeting.meeting_id, findings)
    with pytest.raises(MeetingError) as exc:
        runner.submit(
            mission.dev_mission_id,
            meeting.meeting_id,
            _challenge(mission.dev_mission_id, findings.artifact_id),
        )
    assert exc.value.code == "kind_not_accepted_in_phase"


def test_submitting_outside_the_collecting_phase_is_refused(runner, mission):
    meeting = _meeting(runner, mission)
    with pytest.raises(MeetingError) as exc:
        runner.submit(
            mission.dev_mission_id, meeting.meeting_id, _findings(mission.dev_mission_id)
        )
    assert exc.value.code == "not_collecting"


# --------------------------------------------------------------------------
# Challenges and responses
# --------------------------------------------------------------------------


def _collect_one(runner, mission, meeting):
    meeting = _advance_to(runner, mission, meeting, MeetingPhase.COLLECTING)
    findings = _findings(mission.dev_mission_id)
    meeting = runner.submit(mission.dev_mission_id, meeting.meeting_id, findings)
    meeting = runner.open_phase(
        mission.dev_mission_id, meeting.meeting_id, MeetingPhase.CHALLENGING,
        actor=meeting.chair,
    )
    return meeting, findings


def test_a_challenge_must_target_a_submission_in_this_meeting(runner, mission):
    meeting = _meeting(runner, mission)
    meeting, _ = _collect_one(runner, mission, meeting)
    with pytest.raises(MeetingError) as exc:
        runner.challenge(
            mission.dev_mission_id,
            meeting.meeting_id,
            _challenge(mission.dev_mission_id, "foreign_artifact_id"),
        )
    assert exc.value.code == "challenge_target_not_in_meeting"


def test_an_agent_cannot_challenge_only_its_own_submission(runner, mission):
    meeting = _meeting(runner, mission)
    meeting, findings = _collect_one(runner, mission, meeting)
    with pytest.raises(MeetingError) as exc:
        runner.challenge(
            mission.dev_mission_id,
            meeting.meeting_id,
            _challenge(mission.dev_mission_id, findings.artifact_id, author="research"),
        )
    assert exc.value.code == "self_challenge"


def test_a_response_must_target_a_recorded_challenge(runner, mission):
    meeting = _meeting(runner, mission)
    meeting, findings = _collect_one(runner, mission, meeting)
    meeting = runner.challenge(
        mission.dev_mission_id,
        meeting.meeting_id,
        _challenge(mission.dev_mission_id, findings.artifact_id),
    )
    meeting = runner.open_phase(
        mission.dev_mission_id, meeting.meeting_id, MeetingPhase.RESPONDING,
        actor=meeting.chair,
    )
    with pytest.raises(MeetingError) as exc:
        runner.respond(
            mission.dev_mission_id,
            meeting.meeting_id,
            _response(mission.dev_mission_id, "not_a_challenge"),
        )
    assert exc.value.code == "response_target_not_a_challenge"


def test_a_challenge_cannot_be_answered_twice(runner, mission):
    meeting = _meeting(runner, mission)
    meeting, findings = _collect_one(runner, mission, meeting)
    challenge = _challenge(mission.dev_mission_id, findings.artifact_id)
    meeting = runner.challenge(mission.dev_mission_id, meeting.meeting_id, challenge)
    meeting = runner.open_phase(
        mission.dev_mission_id, meeting.meeting_id, MeetingPhase.RESPONDING,
        actor=meeting.chair,
    )
    runner.respond(
        mission.dev_mission_id,
        meeting.meeting_id,
        _response(mission.dev_mission_id, challenge.artifact_id),
    )
    with pytest.raises(MeetingError) as exc:
        runner.respond(
            mission.dev_mission_id,
            meeting.meeting_id,
            _response(mission.dev_mission_id, challenge.artifact_id),
        )
    assert exc.value.code == "challenge_already_answered"


# --------------------------------------------------------------------------
# Finalisation and the no-fabricated-consensus rule
# --------------------------------------------------------------------------


def _to_synthesis_with_open_challenge(runner, mission):
    meeting = _meeting(runner, mission)
    meeting, findings = _collect_one(runner, mission, meeting)
    challenge = _challenge(mission.dev_mission_id, findings.artifact_id)
    meeting = runner.challenge(mission.dev_mission_id, meeting.meeting_id, challenge)
    meeting = runner.open_phase(
        mission.dev_mission_id, meeting.meeting_id, MeetingPhase.RESPONDING,
        actor=meeting.chair,
    )
    meeting = runner.open_phase(
        mission.dev_mission_id, meeting.meeting_id, MeetingPhase.SYNTHESIZING,
        actor=meeting.chair,
    )
    return meeting, challenge


def test_a_decided_outcome_is_refused_while_a_challenge_is_unanswered(runner, mission):
    meeting, _ = _to_synthesis_with_open_challenge(runner, mission)
    with pytest.raises(MeetingError) as exc:
        runner.finalize(
            mission.dev_mission_id,
            meeting.meeting_id,
            actor=meeting.chair,
            agreements=["Everything is fine."],
            outcome=MeetingOutcome.DECIDED,
            repository_sha=SHA,
        )
    assert exc.value.code == "decided_with_unanswered_challenges"


def test_an_agreement_cannot_be_recorded_over_an_open_objection(runner, mission):
    meeting, challenge = _to_synthesis_with_open_challenge(runner, mission)
    with pytest.raises(MeetingError) as exc:
        runner.finalize(
            mission.dev_mission_id,
            meeting.meeting_id,
            actor=meeting.chair,
            agreements=["Authority coverage is out of scope."],
            outcome=MeetingOutcome.BLOCKED,
            repository_sha=SHA,
            contested_points={
                "Authority coverage is out of scope.": challenge.artifact_id
            },
        )
    assert exc.value.code == "agreement_over_unanswered_challenge"


def test_unanswered_challenges_are_preserved_not_dropped(runner, mission):
    meeting, challenge = _to_synthesis_with_open_challenge(runner, mission)
    meeting, minutes = runner.finalize(
        mission.dev_mission_id,
        meeting.meeting_id,
        actor=meeting.chair,
        agreements=[],
        outcome=MeetingOutcome.BLOCKED,
        repository_sha=SHA,
    )
    preserved = meeting.preserved_disagreements
    assert len(preserved) == 1
    assert preserved[0]["challenge_id"] == challenge.artifact_id
    assert preserved[0]["raised_by"] == "security-governance"
    assert preserved[0]["failure_mode"]
    assert preserved[0]["decision_required"]
    assert minutes.payload["disagreements"] == preserved


def test_preserved_disagreements_land_on_the_mission(runner, mission):
    meeting, challenge = _to_synthesis_with_open_challenge(runner, mission)
    runner.finalize(
        mission.dev_mission_id,
        meeting.meeting_id,
        actor=meeting.chair,
        agreements=[],
        outcome=MeetingOutcome.BLOCKED,
        repository_sha=SHA,
    )
    updated = runner.missions.require(mission.dev_mission_id)
    assert challenge.artifact_id in updated.unresolved_disagreements
    assert updated.history[-1]["event"] == "meeting_finalized"


def test_an_answered_challenge_permits_a_decided_outcome(runner, mission):
    meeting = _meeting(runner, mission)
    meeting, findings = _collect_one(runner, mission, meeting)
    challenge = _challenge(mission.dev_mission_id, findings.artifact_id)
    meeting = runner.challenge(mission.dev_mission_id, meeting.meeting_id, challenge)
    meeting = runner.open_phase(
        mission.dev_mission_id, meeting.meeting_id, MeetingPhase.RESPONDING,
        actor=meeting.chair,
    )
    meeting = runner.respond(
        mission.dev_mission_id,
        meeting.meeting_id,
        _response(mission.dev_mission_id, challenge.artifact_id),
    )
    meeting = runner.open_phase(
        mission.dev_mission_id, meeting.meeting_id, MeetingPhase.SYNTHESIZING,
        actor=meeting.chair,
    )
    meeting, minutes = runner.finalize(
        mission.dev_mission_id,
        meeting.meeting_id,
        actor=meeting.chair,
        agreements=["Authority scenarios are in scope for the first suite."],
        outcome=MeetingOutcome.DECIDED,
        repository_sha=SHA,
    )
    assert meeting.outcome == MeetingOutcome.DECIDED.value
    assert meeting.phase == MeetingPhase.FINALIZED.value
    assert minutes.payload["agreements"]
    assert minutes.payload["disagreements"] == []
    assert runner.missions.require(mission.dev_mission_id).unresolved_disagreements == []


def test_insufficient_evidence_is_a_legitimate_outcome(runner, mission):
    meeting = _meeting(runner, mission)
    meeting, _ = _collect_one(runner, mission, meeting)
    for phase in (MeetingPhase.RESPONDING, MeetingPhase.SYNTHESIZING):
        meeting = runner.open_phase(
            mission.dev_mission_id, meeting.meeting_id, phase, actor=meeting.chair
        )
    meeting, minutes = runner.finalize(
        mission.dev_mission_id,
        meeting.meeting_id,
        actor=meeting.chair,
        agreements=[],
        outcome=MeetingOutcome.INSUFFICIENT_EVIDENCE,
        repository_sha=SHA,
    )
    assert minutes.payload["outcome"] == "insufficient_evidence"


def test_insufficient_evidence_cannot_be_claimed_alongside_agreements(runner, mission):
    meeting = _meeting(runner, mission)
    meeting, _ = _collect_one(runner, mission, meeting)
    for phase in (MeetingPhase.RESPONDING, MeetingPhase.SYNTHESIZING):
        meeting = runner.open_phase(
            mission.dev_mission_id, meeting.meeting_id, phase, actor=meeting.chair
        )
    with pytest.raises(MeetingError) as exc:
        runner.finalize(
            mission.dev_mission_id,
            meeting.meeting_id,
            actor=meeting.chair,
            agreements=["We agreed on something."],
            outcome=MeetingOutcome.INSUFFICIENT_EVIDENCE,
            repository_sha=SHA,
        )
    assert exc.value.code == "insufficient_evidence_with_agreements"


def test_only_the_chair_finalizes(runner, mission):
    meeting, _ = _to_synthesis_with_open_challenge(runner, mission)
    with pytest.raises(MeetingError) as exc:
        runner.finalize(
            mission.dev_mission_id,
            meeting.meeting_id,
            actor="research",
            agreements=[],
            outcome=MeetingOutcome.BLOCKED,
            repository_sha=SHA,
        )
    assert exc.value.code == "finalize_by_non_chair"


def test_finalizing_outside_synthesis_is_refused(runner, mission):
    meeting = _meeting(runner, mission)
    with pytest.raises(MeetingError) as exc:
        runner.finalize(
            mission.dev_mission_id,
            meeting.meeting_id,
            actor=meeting.chair,
            agreements=[],
            outcome=MeetingOutcome.BLOCKED,
            repository_sha=SHA,
        )
    assert exc.value.code == "not_synthesizing"


def test_a_closed_meeting_cannot_reopen(runner, mission):
    meeting, _ = _to_synthesis_with_open_challenge(runner, mission)
    runner.finalize(
        mission.dev_mission_id,
        meeting.meeting_id,
        actor=meeting.chair,
        agreements=[],
        outcome=MeetingOutcome.BLOCKED,
        repository_sha=SHA,
    )
    with pytest.raises(MeetingError) as exc:
        runner.open_phase(
            mission.dev_mission_id, meeting.meeting_id, MeetingPhase.SYNTHESIZING,
            actor=meeting.chair,
        )
    assert exc.value.code == "meeting_already_closed"


def test_status_reports_the_whole_meeting(runner, mission):
    meeting, challenge = _to_synthesis_with_open_challenge(runner, mission)
    status = runner.status(mission.dev_mission_id, meeting.meeting_id)
    assert status["phase"] == MeetingPhase.SYNTHESIZING.value
    assert status["unanswered_challenges"] == [challenge.artifact_id]
    assert status["submission_counts"]["research"] == 1
    assert status["outcome"] is None


def test_the_disagreement_template_has_the_seven_mandated_fields():
    assert list(disagreement_template()) == [
        "claim", "evidence", "counterargument", "failure_mode", "risk",
        "alternative", "decision_required",
    ]
