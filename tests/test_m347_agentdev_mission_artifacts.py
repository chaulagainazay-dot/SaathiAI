"""M347 — Development-mission lifecycle and durable artifact protocol."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.agentdev.artifacts import (
    INSUFFICIENT_EVIDENCE,
    Artifact,
    ArtifactError,
    ArtifactKind,
    ArtifactStatus,
    ArtifactStore,
    Claim,
    ClaimKind,
    Severity,
    TerminalVerdict,
    can_transition as artifact_can_transition,
    make_artifact,
    validate_artifact,
)
from saathi.agentdev.missions import (
    DevMissionStore,
    Gate,
    GateRecord,
    MissionError,
    MissionState,
    STATE_EXIT_GATES,
    new_mission_id,
)

SHA = "53b9b20736d5acf4a7ca3a9bd25b68d01e666a5d"


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "agentdev")


@pytest.fixture
def missions(tmp_path: Path) -> DevMissionStore:
    return DevMissionStore(tmp_path / "agentdev")


@pytest.fixture
def mission(missions: DevMissionStore):
    return missions.create(
        title="Adopt agent-behaviour evaluation coverage",
        objective="Decide whether SaathiOS should adopt ECC-style evaluation coverage.",
        starting_sha=SHA,
        participants=["ceo", "program-manager", "research"],
    )


def _research(mission_id: str = "", **overrides) -> Artifact:
    payload = {
        "mission_id": mission_id or overrides.pop("mission_id", ""),
        "kind": ArtifactKind.RESEARCH_FINDINGS,
        "authoring_agent": "research",
        "repository_sha": SHA,
        "title": "Agent evaluation patterns",
        "required_next_action": "architecture review",
        "claims": [
            Claim(
                claim_id="c1",
                statement="The repository holds 343 test files.",
                kind=ClaimKind.FACT.value,
                evidence_ref="tests/",
            ),
            Claim(
                claim_id="c2",
                statement="None of them assert agent behaviour.",
                kind=ClaimKind.INFERENCE.value,
                rests_on=["c1"],
            ),
        ],
        "payload": {"not_investigated": ["ECC internals"]},
    }
    payload.update(overrides)
    return make_artifact(**payload)


# --------------------------------------------------------------------------
# Artifact envelope
# --------------------------------------------------------------------------


def test_every_artifact_carries_the_full_envelope(mission):
    artifact = _research(mission.dev_mission_id)
    for attribute in (
        "artifact_id", "mission_id", "kind", "authoring_agent", "created_at",
        "repository_sha", "worktree", "branch", "status", "claims",
        "evidence_references", "assumptions", "limitations",
        "unresolved_questions", "dependencies", "required_next_action",
    ):
        assert hasattr(artifact, attribute), attribute


def test_the_kinds_are_a_closed_vocabulary():
    # Sixteen at M347; ``documentation_update`` added in M354 because the
    # Documentation Agent held a capability with no artifact it could write.
    assert len(ArtifactKind) == 17
    with pytest.raises(ArtifactError) as exc:
        make_artifact(
            mission_id="dm001", kind="gossip", authoring_agent="research",
            repository_sha=SHA, title="x", required_next_action="y",
        )
    assert exc.value.code == "unknown_artifact_kind"


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"mission_id": "not-a-mission"}, "invalid_mission_id"),
        ({"repository_sha": "zzz"}, "invalid_repository_sha"),
        ({"repository_sha": ""}, "invalid_repository_sha"),
        ({"title": "  "}, "missing_title"),
        ({"required_next_action": ""}, "missing_required_next_action"),
        ({"authoring_agent": "nobody"}, "unknown_authoring_agent"),
    ],
)
def test_malformed_envelopes_are_refused(mission, overrides, code):
    kwargs = {"mission_id": mission.dev_mission_id, **overrides}
    with pytest.raises(ArtifactError) as exc:
        _research(**kwargs)
    assert exc.value.code == code


def test_author_must_hold_the_capability_for_the_kind(mission):
    """A research agent cannot author a security review."""
    with pytest.raises(ArtifactError) as exc:
        make_artifact(
            mission_id=mission.dev_mission_id,
            kind=ArtifactKind.SECURITY_REVIEW,
            authoring_agent="research",
            repository_sha=SHA,
            title="Security review",
            required_next_action="decide",
            payload={
                "verdict": "pass",
                "trading_guardian_impact": "none",
                "global_config_impact": "none",
            },
        )
    assert exc.value.code == "author_lacks_capability"


def test_only_the_owner_may_author_an_owner_approval(mission):
    with pytest.raises(ArtifactError) as exc:
        make_artifact(
            mission_id=mission.dev_mission_id,
            kind=ArtifactKind.OWNER_APPROVAL,
            authoring_agent="ceo",
            repository_sha=SHA,
            title="Approved",
            required_next_action="close",
            payload={"approved": True},
        )
    assert exc.value.code == "owner_approval_not_authored_by_owner"


def test_the_owner_may_not_author_agent_artifacts(mission):
    with pytest.raises(ArtifactError) as exc:
        _research(mission.dev_mission_id, authoring_agent="owner")
    assert exc.value.code == "owner_may_only_author_owner_approval"


def test_code_bound_artifacts_must_name_a_worktree_and_branch(mission):
    with pytest.raises(ArtifactError) as exc:
        make_artifact(
            mission_id=mission.dev_mission_id,
            kind=ArtifactKind.CODE_REVIEW,
            authoring_agent="code-review",
            repository_sha=SHA,
            title="Review",
            required_next_action="fix",
            payload={"reviewed_author": "backend-engineering"},
        )
    assert exc.value.code == "code_artifact_without_worktree"


# --------------------------------------------------------------------------
# Claims: fact vs inference vs assumption
# --------------------------------------------------------------------------


def test_a_fact_without_evidence_is_refused(mission):
    with pytest.raises(ArtifactError) as exc:
        _research(
            mission.dev_mission_id,
            claims=[Claim(claim_id="c1", statement="It is so.", kind="fact")],
        )
    assert exc.value.code == "fact_without_evidence"


def test_an_inference_must_name_the_claims_it_rests_on(mission):
    with pytest.raises(ArtifactError) as exc:
        _research(
            mission.dev_mission_id,
            claims=[Claim(claim_id="c1", statement="Therefore X.", kind="inference")],
        )
    assert exc.value.code == "inference_without_basis"


def test_an_inference_cannot_rest_on_a_claim_that_does_not_exist(mission):
    with pytest.raises(ArtifactError) as exc:
        _research(
            mission.dev_mission_id,
            claims=[
                Claim(
                    claim_id="c1", statement="Therefore X.", kind="inference",
                    rests_on=["ghost"],
                )
            ],
        )
    assert exc.value.code == "inference_basis_not_found"


def test_an_assumption_must_state_what_would_falsify_it(mission):
    with pytest.raises(ArtifactError) as exc:
        _research(
            mission.dev_mission_id,
            claims=[Claim(claim_id="c1", statement="Assume Y.", kind="assumption")],
        )
    assert exc.value.code == "assumption_without_falsifier"


def test_insufficient_evidence_is_always_acceptable(mission):
    artifact = _research(
        mission.dev_mission_id,
        claims=[Claim(claim_id="c1", statement=INSUFFICIENT_EVIDENCE, kind="fact")],
    )
    assert artifact.has_insufficient_evidence
    assert artifact.claims[0].is_insufficient_evidence


def test_claims_are_separable_by_epistemic_status(mission):
    artifact = _research(mission.dev_mission_id)
    assert [c.claim_id for c in artifact.claims_of(ClaimKind.FACT)] == ["c1"]
    assert [c.claim_id for c in artifact.claims_of(ClaimKind.INFERENCE)] == ["c2"]


def test_duplicate_claim_ids_are_refused(mission):
    with pytest.raises(ArtifactError) as exc:
        _research(
            mission.dev_mission_id,
            claims=[
                Claim(claim_id="c1", statement="a", kind="fact", evidence_ref="x"),
                Claim(claim_id="c1", statement="b", kind="fact", evidence_ref="y"),
            ],
        )
    assert exc.value.code == "duplicate_claim_id"


@pytest.mark.parametrize("severity", [Severity.HIGH.value, Severity.CRITICAL.value])
def test_high_severity_findings_require_full_evidence(mission, severity):
    with pytest.raises(ArtifactError) as exc:
        _research(
            mission.dev_mission_id,
            claims=[
                Claim(
                    claim_id="c1", statement="Injection risk.", kind="fact",
                    evidence_ref="saathi/x.py:10", severity=severity,
                )
            ],
        )
    assert exc.value.code == "high_severity_without_evidence"


def test_a_fully_evidenced_high_severity_finding_is_accepted(mission):
    artifact = _research(
        mission.dev_mission_id,
        claims=[
            Claim(
                claim_id="c1",
                statement="Unvalidated path join.",
                kind="fact",
                evidence_ref="saathi/x.py:10",
                severity=Severity.HIGH.value,
                source_location="saathi/x.py:10",
                failure_mode="Path traversal writes outside the worktree.",
                trigger_condition="A relative path containing '..' reaches join().",
                caller_or_dataflow_evidence="Called from y.py:44 with request data.",
                severity_rationale="Escapes the sandbox boundary the milestone claims.",
            )
        ],
    )
    assert artifact.claims[0].severity == Severity.HIGH.value


# --------------------------------------------------------------------------
# Kind-specific rules
# --------------------------------------------------------------------------


def test_research_must_declare_what_it_did_not_investigate(mission):
    with pytest.raises(ArtifactError) as exc:
        _research(mission.dev_mission_id, payload={})
    assert exc.value.code == "research_without_not_investigated"


def test_a_challenge_must_carry_the_full_disagreement_structure(mission):
    complete = {
        "claim": "The design duplicates the mission engine.",
        "evidence": "saathi/missions/store.py already persists missions.",
        "counterargument": "A dev mission is a different noun.",
        "failure_mode": "Two stores disagree about mission state.",
        "risk": "Split-brain governance.",
        "alternative": "Extend the existing store.",
        "decision_required": "Which store owns development missions?",
    }
    artifact = make_artifact(
        mission_id=mission.dev_mission_id,
        kind=ArtifactKind.CHALLENGE,
        authoring_agent="security-governance",
        repository_sha=SHA,
        title="Duplicate store challenge",
        required_next_action="architecture responds",
        dependencies=["arch_123"],
        payload=complete,
    )
    assert artifact.payload["decision_required"]

    for field_name in complete:
        broken = dict(complete)
        broken[field_name] = ""
        with pytest.raises(ArtifactError) as exc:
            make_artifact(
                mission_id=mission.dev_mission_id,
                kind=ArtifactKind.CHALLENGE,
                authoring_agent="security-governance",
                repository_sha=SHA,
                title="Incomplete",
                required_next_action="x",
                dependencies=["arch_123"],
                payload=broken,
            )
        assert exc.value.code == "challenge_incomplete"
        assert field_name in exc.value.detail


def test_a_challenge_must_name_what_it_challenges(mission):
    with pytest.raises(ArtifactError) as exc:
        make_artifact(
            mission_id=mission.dev_mission_id,
            kind=ArtifactKind.CHALLENGE,
            authoring_agent="security-governance",
            repository_sha=SHA,
            title="Floating challenge",
            required_next_action="x",
            payload={
                "claim": "a", "evidence": "b", "counterargument": "c",
                "failure_mode": "d", "risk": "e", "alternative": "f",
                "decision_required": "g",
            },
        )
    assert exc.value.code == "challenge_without_target"


def test_a_new_component_needs_a_reason_no_existing_one_covers_it(mission):
    with pytest.raises(ArtifactError) as exc:
        make_artifact(
            mission_id=mission.dev_mission_id,
            kind=ArtifactKind.ARCHITECTURE_DECISION,
            authoring_agent="architecture",
            repository_sha=SHA,
            title="Design",
            required_next_action="security review",
            payload={
                "reuse_table": [],
                "new_components": [{"name": "shiny_thing"}],
                "rollback_path": "git revert",
            },
        )
    assert exc.value.code == "new_component_without_justification"


def test_a_security_review_must_state_trading_guardian_impact(mission):
    with pytest.raises(ArtifactError) as exc:
        make_artifact(
            mission_id=mission.dev_mission_id,
            kind=ArtifactKind.SECURITY_REVIEW,
            authoring_agent="security-governance",
            repository_sha=SHA,
            title="Review",
            required_next_action="decide",
            payload={"verdict": "pass", "global_config_impact": "none"},
        )
    assert exc.value.code == "security_review_without_trading_guardian_statement"


def test_a_verification_result_must_name_the_command_that_produced_it(mission):
    with pytest.raises(ArtifactError) as exc:
        make_artifact(
            mission_id=mission.dev_mission_id,
            kind=ArtifactKind.VERIFICATION_REPORT,
            authoring_agent="testing-verification",
            repository_sha=SHA,
            title="Verification",
            required_next_action="review",
            worktree="/tmp/wt",
            branch="agent/backend-engineering/dm001-x",
            payload={"results": [{"outcome": "pass"}], "not_run": []},
        )
    assert exc.value.code == "verification_result_without_command"


def test_a_code_review_of_its_own_author_is_refused(mission):
    with pytest.raises(ArtifactError) as exc:
        make_artifact(
            mission_id=mission.dev_mission_id,
            kind=ArtifactKind.CODE_REVIEW,
            authoring_agent="code-review",
            repository_sha=SHA,
            title="Self review",
            required_next_action="x",
            worktree="/tmp/wt",
            branch="agent/backend-engineering/dm001-x",
            payload={"reviewed_author": "code-review"},
        )
    assert exc.value.code == "code_review_of_own_work"


@pytest.mark.parametrize("verdict", [v.value for v in TerminalVerdict])
def test_every_terminal_verdict_in_the_vocabulary_is_accepted(mission, verdict):
    artifact = make_artifact(
        mission_id=mission.dev_mission_id,
        kind=ArtifactKind.EXECUTIVE_DECISION,
        authoring_agent="ceo",
        repository_sha=SHA,
        title="Decision",
        required_next_action="owner review",
        payload={"verdict": verdict, "unresolved_risks": []},
    )
    assert artifact.payload["verdict"] == verdict


def test_an_invented_verdict_is_refused(mission):
    with pytest.raises(ArtifactError) as exc:
        make_artifact(
            mission_id=mission.dev_mission_id,
            kind=ArtifactKind.EXECUTIVE_DECISION,
            authoring_agent="ceo",
            repository_sha=SHA,
            title="Decision",
            required_next_action="x",
            payload={"verdict": "LOOKS_FINE", "unresolved_risks": []},
        )
    assert exc.value.code == "invalid_terminal_verdict"


def test_a_decision_must_carry_its_unresolved_risks(mission):
    with pytest.raises(ArtifactError) as exc:
        make_artifact(
            mission_id=mission.dev_mission_id,
            kind=ArtifactKind.EXECUTIVE_DECISION,
            authoring_agent="ceo",
            repository_sha=SHA,
            title="Decision",
            required_next_action="x",
            payload={"verdict": TerminalVerdict.REJECTED.value},
        )
    assert exc.value.code == "decision_without_unresolved_risks"


# --------------------------------------------------------------------------
# Artifact store
# --------------------------------------------------------------------------


def test_artifacts_round_trip_through_the_store(store: ArtifactStore, mission):
    artifact = _research(mission.dev_mission_id)
    store.put(artifact)
    loaded = store.get(mission.dev_mission_id, artifact.artifact_id)
    assert loaded is not None
    assert loaded.title == artifact.title
    assert [c.claim_id for c in loaded.claims] == ["c1", "c2"]


def test_store_filters_by_kind_author_and_status(store: ArtifactStore, mission):
    store.put(_research(mission.dev_mission_id))
    store.put(
        make_artifact(
            mission_id=mission.dev_mission_id,
            kind=ArtifactKind.PROPOSAL,
            authoring_agent="product-strategy",
            repository_sha=SHA,
            title="Product case",
            required_next_action="architecture review",
        )
    )
    assert len(store.list(mission.dev_mission_id)) == 2
    assert len(store.list(mission.dev_mission_id, kind=ArtifactKind.PROPOSAL)) == 1
    assert len(store.list(mission.dev_mission_id, author="research")) == 1
    assert len(store.list(mission.dev_mission_id, status=ArtifactStatus.DRAFT)) == 2


def test_artifact_status_transitions_are_enforced(store: ArtifactStore, mission):
    artifact = store.put(_research(mission.dev_mission_id))
    store.set_status(mission.dev_mission_id, artifact.artifact_id, ArtifactStatus.SUBMITTED)
    store.set_status(mission.dev_mission_id, artifact.artifact_id, ArtifactStatus.UNDER_REVIEW)
    store.set_status(mission.dev_mission_id, artifact.artifact_id, ArtifactStatus.ACCEPTED)
    with pytest.raises(ArtifactError) as exc:
        store.set_status(mission.dev_mission_id, artifact.artifact_id, ArtifactStatus.DRAFT)
    assert exc.value.code == "invalid_status_transition"


def test_an_accepted_artifact_can_only_be_superseded():
    assert artifact_can_transition(ArtifactStatus.ACCEPTED, ArtifactStatus.SUPERSEDED)
    assert not artifact_can_transition(ArtifactStatus.ACCEPTED, ArtifactStatus.REJECTED)


def test_store_keeps_a_backup_of_the_previous_version(store: ArtifactStore, mission):
    artifact = store.put(_research(mission.dev_mission_id))
    store.set_status(mission.dev_mission_id, artifact.artifact_id, ArtifactStatus.SUBMITTED)
    backup = store.mission_dir(mission.dev_mission_id) / f"{artifact.artifact_id}.json.bak"
    assert backup.exists()
    assert json.loads(backup.read_text())["status"] == ArtifactStatus.DRAFT.value


# --------------------------------------------------------------------------
# Mission lifecycle
# --------------------------------------------------------------------------


def test_mission_ids_are_hyphen_free_so_branches_decompose():
    for _ in range(20):
        mission_id = new_mission_id()
        assert "-" not in mission_id
        assert mission_id.startswith("dm")


def test_a_mission_starts_in_intake_with_a_recorded_sha(mission):
    assert mission.state == MissionState.INTAKE.value
    assert mission.starting_sha == SHA
    assert mission.history[0]["event"] == "created"


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"title": ""}, "missing_title"),
        ({"objective": ""}, "missing_objective"),
        ({"starting_sha": "nope"}, "invalid_starting_sha"),
        ({"dev_mission_id": "bad-id"}, "invalid_mission_id"),
    ],
)
def test_malformed_missions_are_refused(missions: DevMissionStore, kwargs, code):
    payload = {
        "title": "T", "objective": "O", "starting_sha": SHA,
    }
    payload.update(kwargs)
    with pytest.raises(MissionError) as exc:
        missions.create(**payload)
    assert exc.value.code == code


def test_duplicate_mission_ids_are_refused(missions: DevMissionStore):
    missions.create(title="A", objective="O", starting_sha=SHA, dev_mission_id="dmdup1")
    with pytest.raises(MissionError) as exc:
        missions.create(title="B", objective="O", starting_sha=SHA, dev_mission_id="dmdup1")
    assert exc.value.code == "duplicate_mission_id"


def test_an_undeclared_transition_is_refused(missions: DevMissionStore, mission):
    with pytest.raises(MissionError) as exc:
        missions.advance(
            mission.dev_mission_id, MissionState.VERIFICATION, actor="program-manager"
        )
    assert exc.value.code == "invalid_state_transition"


def test_a_gate_cannot_be_skipped(missions: DevMissionStore, mission):
    missions.advance(mission.dev_mission_id, MissionState.DECOMPOSED, actor="program-manager")
    missions.advance(mission.dev_mission_id, MissionState.RESEARCH, actor="program-manager")
    with pytest.raises(MissionError) as exc:
        missions.advance(mission.dev_mission_id, MissionState.DESIGN, actor="program-manager")
    assert exc.value.code == "gate_not_passed"
    assert exc.value.detail == Gate.RESEARCH_COMPLETENESS.value


def test_passing_the_gate_unblocks_the_transition(missions: DevMissionStore, mission):
    missions.advance(mission.dev_mission_id, MissionState.DECOMPOSED, actor="program-manager")
    missions.advance(mission.dev_mission_id, MissionState.RESEARCH, actor="program-manager")
    missions.record_gate(
        mission.dev_mission_id,
        GateRecord(
            gate=Gate.RESEARCH_COMPLETENESS.value,
            status="passed",
            approver="architecture",
            subject_author="research",
            evidence_artifact_ids=["rese_1"],
        ),
    )
    updated = missions.advance(
        mission.dev_mission_id, MissionState.DESIGN, actor="program-manager"
    )
    assert updated.state == MissionState.DESIGN.value


def test_every_non_terminal_state_declares_its_exit_gates():
    for state in MissionState:
        assert state in STATE_EXIT_GATES, state


def test_an_open_veto_blocks_every_forward_transition(missions: DevMissionStore, mission):
    missions.advance(mission.dev_mission_id, MissionState.DECOMPOSED, actor="program-manager")
    missions.open_veto(mission.dev_mission_id, "veto-1", actor="security-governance")
    with pytest.raises(MissionError) as exc:
        missions.advance(mission.dev_mission_id, MissionState.RESEARCH, actor="program-manager")
    assert exc.value.code == "security_veto_open"


def test_blocking_a_mission_is_always_reachable(missions: DevMissionStore, mission):
    missions.open_veto(mission.dev_mission_id, "veto-1", actor="security-governance")
    blocked = missions.advance(
        mission.dev_mission_id, MissionState.BLOCKED, actor="security-governance"
    )
    assert blocked.state == MissionState.BLOCKED.value


def test_only_the_veto_author_may_withdraw_it(missions: DevMissionStore, mission):
    missions.open_veto(mission.dev_mission_id, "veto-1", actor="security-governance")
    with pytest.raises(MissionError) as exc:
        missions.withdraw_veto(
            mission.dev_mission_id, "veto-1", actor="ceo", evidence="trust me"
        )
    assert exc.value.code == "veto_withdrawal_by_non_author"


def test_a_veto_cannot_be_withdrawn_without_evidence(missions: DevMissionStore, mission):
    missions.open_veto(mission.dev_mission_id, "veto-1", actor="security-governance")
    with pytest.raises(MissionError) as exc:
        missions.withdraw_veto(
            mission.dev_mission_id, "veto-1", actor="security-governance", evidence="  "
        )
    assert exc.value.code == "veto_withdrawal_without_evidence"


def test_a_withdrawn_veto_records_its_evidence(missions: DevMissionStore, mission):
    missions.open_veto(mission.dev_mission_id, "veto-1", actor="security-governance")
    updated = missions.withdraw_veto(
        mission.dev_mission_id,
        "veto-1",
        actor="security-governance",
        evidence="test_m349 asserts the refusal path",
    )
    assert updated.open_vetoes == []
    assert updated.history[-1]["event"] == "veto_withdrawn"
    assert "test_m349" in updated.history[-1]["evidence"]


def test_only_the_ceo_may_set_a_terminal_verdict(missions: DevMissionStore, mission):
    with pytest.raises(MissionError) as exc:
        missions.set_terminal_verdict(
            mission.dev_mission_id,
            TerminalVerdict.REJECTED.value,
            actor="program-manager",
        )
    assert exc.value.code == "verdict_not_authored_by_ceo"


def test_approval_is_refused_while_a_veto_is_open(missions: DevMissionStore, mission):
    missions.open_veto(mission.dev_mission_id, "veto-1", actor="security-governance")
    with pytest.raises(MissionError) as exc:
        missions.set_terminal_verdict(
            mission.dev_mission_id,
            TerminalVerdict.APPROVED_FOR_IMPLEMENTATION.value,
            actor="ceo",
        )
    assert exc.value.code == "approval_with_open_veto"


def test_approval_is_refused_while_disagreements_are_unresolved(
    missions: DevMissionStore, mission
):
    mission.unresolved_disagreements = ["d1"]
    missions.put(mission)
    with pytest.raises(MissionError) as exc:
        missions.set_terminal_verdict(
            mission.dev_mission_id,
            TerminalVerdict.APPROVED_FOR_IMPLEMENTATION.value,
            actor="ceo",
        )
    assert exc.value.code == "approval_with_unresolved_disagreements"


def test_a_limited_approval_may_carry_unresolved_disagreements(
    missions: DevMissionStore, mission
):
    mission.unresolved_disagreements = ["d1"]
    missions.put(mission)
    updated = missions.set_terminal_verdict(
        mission.dev_mission_id,
        TerminalVerdict.APPROVED_WITH_LIMITATIONS.value,
        actor="ceo",
    )
    assert updated.terminal_verdict == TerminalVerdict.APPROVED_WITH_LIMITATIONS.value


def test_a_mission_cannot_close_without_a_verdict(missions: DevMissionStore, mission):
    mission.state = MissionState.EXECUTIVE_DECISION.value
    missions.put(mission)
    missions.record_gate(
        mission.dev_mission_id,
        GateRecord(
            gate=Gate.EXECUTIVE_SYNTHESIS.value,
            status="passed",
            approver="program-manager",
            subject_author="ceo",
            evidence_artifact_ids=["exec_1"],
        ),
    )
    with pytest.raises(MissionError) as exc:
        missions.advance(mission.dev_mission_id, MissionState.CLOSED, actor="ceo")
    assert exc.value.code == "close_without_terminal_verdict"


def test_status_reports_unmet_gates_and_next_states(missions: DevMissionStore, mission):
    missions.advance(mission.dev_mission_id, MissionState.DECOMPOSED, actor="program-manager")
    missions.advance(mission.dev_mission_id, MissionState.RESEARCH, actor="program-manager")
    status = missions.status(mission.dev_mission_id)
    assert status["unmet_exit_gates"] == [Gate.RESEARCH_COMPLETENESS.value]
    assert status["can_advance"] is False
    assert MissionState.DESIGN.value in status["next_states"]


def test_unknown_gates_are_refused(missions: DevMissionStore, mission):
    with pytest.raises(MissionError) as exc:
        missions.record_gate(mission.dev_mission_id, GateRecord(gate="vibes"))
    assert exc.value.code == "unknown_gate"


def test_missions_are_stored_under_their_own_identifier(
    missions: DevMissionStore, mission, tmp_path: Path
):
    """Duplicate-source-of-truth rule 4: a dev mission never enters saathi/missions."""
    path = tmp_path / "agentdev" / mission.dev_mission_id / "mission.json"
    assert path.is_file()
    assert "dev_mission_id" in json.loads(path.read_text())
