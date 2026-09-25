"""M351 — Offline simulated mission and the behaviour-evaluation foundation."""
from __future__ import annotations

from pathlib import Path

import pytest

from saathi.agentdev.artifacts import ArtifactKind, ArtifactStore, TerminalVerdict
from saathi.agentdev.behavior_evals import SCENARIOS, run_suite
from saathi.agentdev.meetings import MeetingType
from saathi.agentdev.missions import DevMissionStore, Gate, MissionState
from saathi.agentdev.simulation import MISSION_ID, PARTICIPANTS, run_offline_mission


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    root = tmp_path_factory.mktemp("simulation")
    return run_offline_mission(store_dir=root)


# --------------------------------------------------------------------------
# Behaviour evaluation foundation
# --------------------------------------------------------------------------


def test_the_first_suite_covers_the_ten_required_scenarios():
    assert len(SCENARIOS) == 10
    assert [s.scenario_id for s in SCENARIOS] == [
        f"BE-{n:02d}" for n in range(1, 11)
    ]
    titles = {s.scenario_id: s.title.lower() for s in SCENARIOS}
    required = {
        "BE-01": "forbids",              # refuses an unauthorized action
        "BE-02": "worktree",             # writes only inside its assigned worktree
        "BE-03": "approve its own",      # does not approve its own work
        "BE-04": "insufficient evidence",  # reports it instead of inventing certainty
        "BE-05": "veto",                 # security veto blocks advancement
        "BE-06": "gate",                 # manager cannot skip gates
        "BE-07": "fact from inference",  # research separates fact from inference
        "BE-08": "unresolved risks",     # synthesis preserves them
        "BE-09": "configuration",        # global config needs owner approval
        "BE-10": "destructive git",      # destructive git rejected
    }
    for scenario_id, keyword in required.items():
        assert keyword in titles[scenario_id], (scenario_id, titles[scenario_id])


def test_the_suite_is_offline_and_deterministic(tmp_path):
    first = run_suite(store_dir=tmp_path / "a")
    second = run_suite(store_dir=tmp_path / "b")
    assert first["offline"] and first["deterministic"]
    assert [r["scenario_id"] for r in first["results"]] == [
        r["scenario_id"] for r in second["results"]
    ]
    assert [r["passed"] for r in first["results"]] == [
        r["passed"] for r in second["results"]
    ]


def test_every_scenario_passes(tmp_path):
    suite = run_suite(store_dir=tmp_path / "suite")
    failures = [r for r in suite["results"] if not r["passed"]]
    assert not failures, [(r["scenario_id"], r["observed"], r["detail"]) for r in failures]
    assert suite["passed"] == suite["total"] == 10


def test_every_scenario_declares_an_honest_enforcement_tier(tmp_path):
    suite = run_suite(store_dir=tmp_path / "suite")
    allowed = {
        "technically_enforced", "schema_validated",
        "orchestration_checked", "prompt_guidance",
    }
    for row in suite["results"]:
        assert row["enforcement"] in allowed, row
        assert row["proves"].strip(), row["scenario_id"]


def test_the_suite_states_what_it_cannot_prove(tmp_path):
    suite = run_suite(store_dir=tmp_path / "suite")
    assert "cannot prove" in suite["limitation"]
    assert "detection, not prevention" in suite["limitation"]


def test_the_worktree_scenario_does_not_overclaim(tmp_path):
    """BE-02 must not be reported as prevention."""
    suite = run_suite(store_dir=tmp_path / "suite")
    be02 = next(r for r in suite["results"] if r["scenario_id"] == "BE-02")
    assert be02["enforcement"] == "schema_validated"
    assert "not prevented" in be02["proves"] or "not prevented" in be02["detail"]


# --------------------------------------------------------------------------
# The twelve-step mission
# --------------------------------------------------------------------------


def test_the_mission_completes(result):
    assert result["completed"] is True
    assert result["dev_mission_id"] == MISSION_ID
    assert result["final_state"] == MissionState.CLOSED.value


def test_all_twelve_steps_run(result):
    numbers = sorted(step["step"] for step in result["steps"])
    assert numbers == list(range(1, 13))


def test_the_required_participants_took_part(result):
    assert result["participants"] == PARTICIPANTS
    actors = {step["actor"] for step in result["steps"]}
    for role in (
        "ceo", "program-manager", "research", "architecture",
        "security-governance", "testing-verification", "cost-resource",
    ):
        assert role in actors, role


def test_the_three_required_meetings_happened(result):
    types = {m["meeting_type"] for m in result["meetings"]}
    assert types == {
        MeetingType.RESEARCH_REVIEW.value,
        MeetingType.ARCHITECTURE_COUNCIL.value,
        MeetingType.RED_TEAM_REVIEW.value,
    }


def test_disagreement_was_preserved_not_manufactured_away(result):
    assert len(result["preserved_disagreements"]) == 1
    red_team = next(
        m for m in result["meetings"]
        if m["meeting_type"] == MeetingType.RED_TEAM_REVIEW.value
    )
    assert red_team["outcome"] == "blocked"
    assert len(red_team["preserved_disagreements"]) == 1
    assert red_team["preserved_disagreements"][0]["raised_by"] == "testing-verification"
    assert red_team["preserved_disagreements"][0]["decision_required"]


def test_the_verdict_is_limited_because_a_disagreement_stands(result):
    assert result["terminal_verdict"] == TerminalVerdict.APPROVED_WITH_LIMITATIONS.value
    assert result["terminal_verdict"] != TerminalVerdict.APPROVED_FOR_IMPLEMENTATION.value


def test_the_decision_restates_every_preserved_disagreement(result, tmp_path_factory):
    artifacts = ArtifactStore(result["store"])
    decisions = artifacts.list(MISSION_ID, kind=ArtifactKind.EXECUTIVE_DECISION)
    assert len(decisions) == 1
    risks = decisions[0].payload["unresolved_risks"]
    challenge_ids = {
        r.get("challenge_id") for r in risks if isinstance(r, dict)
    }
    for preserved in result["preserved_disagreements"]:
        assert preserved in challenge_ids


def test_the_gates_that_ran_were_independently_approved(result):
    passed = [g for g in result["gates"] if g["status"] == "passed"]
    assert passed, "no gate passed"
    for gate in passed:
        assert gate["approver"] != gate["subject_author"], gate
        assert gate["evidence"], gate


def test_the_security_gates_were_approved_by_security(result):
    for row in result["gates"]:
        if row["security_owned"] and row["status"] == "passed":
            assert row["approver"] == "security-governance", row


def test_the_owner_gate_was_never_passed_by_an_agent(result):
    owner_gate = next(
        row for row in result["gates"] if row["gate"] == Gate.OWNER_APPROVAL.value
    )
    assert owner_gate["status"] == "pending"
    assert owner_gate["owner_only"] is True


def test_research_output_separated_fact_inference_and_assumption(result):
    step = next(s for s in result["steps"] if s["step"] == 3)
    assert step["facts"] >= 2
    assert step["inferences"] >= 1
    assert step["assumptions"] >= 1


def test_the_mission_recorded_insufficient_evidence_rather_than_guessing(result):
    artifacts = ArtifactStore(result["store"])
    findings = artifacts.list(MISSION_ID, kind=ArtifactKind.RESEARCH_FINDINGS)
    assert any(a.has_insufficient_evidence for a in findings)


def test_the_mission_produced_the_expected_artifact_kinds(result):
    for kind in (
        ArtifactKind.MISSION_INTAKE,
        ArtifactKind.TASK_ASSIGNMENT,
        ArtifactKind.RESEARCH_FINDINGS,
        ArtifactKind.PROPOSAL,
        ArtifactKind.ARCHITECTURE_DECISION,
        ArtifactKind.SECURITY_REVIEW,
        ArtifactKind.CHALLENGE,
        ArtifactKind.RESPONSE,
        ArtifactKind.MEETING_AGENDA,
        ArtifactKind.MEETING_MINUTES,
        ArtifactKind.VERIFICATION_REPORT,
        ArtifactKind.EXECUTIVE_DECISION,
    ):
        assert kind.value in result["artifact_kinds"], kind.value


def test_the_security_review_states_trading_guardian_impact(result):
    artifacts = ArtifactStore(result["store"])
    review = artifacts.list(MISSION_ID, kind=ArtifactKind.SECURITY_REVIEW)[0]
    assert "None" in review.payload["trading_guardian_impact"]
    assert "None" in review.payload["global_config_impact"]


def test_no_production_change_was_made(result):
    assert result["production_changes"] == []
    assert "no repository change" in result["note"]


def test_the_mission_is_reproducible_from_a_clean_store(tmp_path):
    first = run_offline_mission(store_dir=tmp_path / "one")
    second = run_offline_mission(store_dir=tmp_path / "two")
    assert first["terminal_verdict"] == second["terminal_verdict"]
    assert first["artifact_count"] == second["artifact_count"]
    assert first["artifact_kinds"] == second["artifact_kinds"]
    assert len(first["preserved_disagreements"]) == len(second["preserved_disagreements"])


def test_a_second_run_in_the_same_store_is_refused(tmp_path):
    """The mission id is fixed, so re-running over the same store must not
    silently create a second copy."""
    from saathi.agentdev.missions import MissionError

    root = tmp_path / "once"
    run_offline_mission(store_dir=root)
    with pytest.raises(MissionError) as exc:
        run_offline_mission(store_dir=root)
    assert exc.value.code == "duplicate_mission_id"


def test_dry_run_lists_the_sequence_without_creating_it(tmp_path):
    root = tmp_path / "dry"
    payload = run_offline_mission(store_dir=root, dry_run=True)
    assert payload["dry_run"] is True
    assert len(payload["would_run"]) == 12
    assert DevMissionStore(root).list() == []


def test_the_simulation_did_not_build_a_production_platform(result):
    """The mission proves the systems; it does not implement the thing it evaluated."""
    artifacts = ArtifactStore(result["store"])
    decision = artifacts.list(MISSION_ID, kind=ArtifactKind.EXECUTIVE_DECISION)[0]
    limitations = " ".join(decision.payload["limitations"]).lower()
    assert "no production agent-evaluation platform" in limitations
