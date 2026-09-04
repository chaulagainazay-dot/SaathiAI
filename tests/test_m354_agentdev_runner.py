"""M354 — the deterministic agent runner.

Four obligations.

*Completeness* — all eight participants execute, and the reference plan drives a
mission from intake to closed through every gate the lifecycle demands.

*The contract* — every step passes all seven phases in order, and a step that
fails records which phase failed and why.

*Determinism* — two runs of the same plan produce byte-identical artifact
content. This is the property the whole milestone rests on, so it is asserted
against a digest of the real stored files, not against a summary.

*No bypass* — the runner uses the real gate engine and the real mission store,
so a plan that self-approves, cites the wrong evidence or skips a gate fails.
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from saathi.agentdev.artifacts import ArtifactKind, ArtifactStore
from saathi.agentdev.missions import DevMissionStore, Gate
from saathi.agentdev.runner import (
    HANDLERS,
    PARTICIPANTS,
    PHASES,
    RUNNER_VERSION,
    AgentRunner,
    HandlerContext,
    MissionPlan,
    PlanStep,
    RunnerError,
    artifact_digest,
    deterministic_artifact_id,
    reference_plan,
    run_reference_mission,
)

SHA = "53b9b20736d5acf4a7ca3a9bd25b68d01e666a5d"


@pytest.fixture()
def trace(tmp_path):
    return run_reference_mission(tmp_path / "run")


def _digests(root) -> dict[str, str]:
    store = ArtifactStore(root)
    missions = DevMissionStore(root)
    out: dict[str, str] = {}
    for mission in missions.list():
        for artifact in store.list(mission.dev_mission_id):
            out[artifact.artifact_id] = artifact_digest(artifact)
    return out


# --------------------------------------------------------------------------
# Completeness
# --------------------------------------------------------------------------


def test_the_eight_specified_participants_map_to_declared_roles():
    from saathi.agentdev.roles import get_role

    assert set(PARTICIPANTS) == {
        "CEO", "Manager", "Research", "Architecture",
        "Security", "Testing", "Documentation", "Code Review",
    }
    for label, agent_id in PARTICIPANTS.items():
        assert get_role(agent_id) is not None, label


def test_every_participant_has_at_least_one_handler():
    handled = {agent_id for agent_id, _kind in HANDLERS}
    assert set(PARTICIPANTS.values()) <= handled


def test_every_handler_targets_a_kind_its_role_may_author():
    from saathi.agentdev.artifacts import KIND_CAPABILITY
    from saathi.agentdev.roles import require_role

    for (agent_id, kind), _handler in HANDLERS.items():
        capability = KIND_CAPABILITY[ArtifactKind(kind)]
        assert require_role(agent_id).has_capability(capability), f"{agent_id}:{kind}"


def test_the_reference_mission_reaches_closed_with_a_verdict(trace):
    assert trace["completed"] is True
    assert trace["final_state"] == "closed"
    assert trace["terminal_verdict"] == "APPROVED_WITH_LIMITATIONS"
    assert trace["failures"] == []


def test_the_reference_mission_exercises_all_eight_participants(trace):
    executed = {s["agent_id"] for s in trace["steps"] if s["agent_id"]}
    assert set(PARTICIPANTS.values()) <= executed


def test_the_reference_mission_passes_every_gate_the_lifecycle_requires(tmp_path):
    run_reference_mission(tmp_path / "run")
    mission = DevMissionStore(tmp_path / "run").require("dmrunner01")
    required = {
        Gate.RESEARCH_COMPLETENESS, Gate.ARCHITECTURE_APPROVAL, Gate.SECURITY_APPROVAL,
        Gate.IMPLEMENTATION_READINESS, Gate.CODE_REVIEW, Gate.AUTOMATED_TESTING,
        Gate.NEGATIVE_PATH_TESTING, Gate.RED_TEAM_REVIEW, Gate.EXECUTIVE_SYNTHESIS,
    }
    for gate in required:
        assert mission.gate(gate).passed, gate.value


def test_no_gate_in_the_reference_mission_was_self_approved(tmp_path):
    run_reference_mission(tmp_path / "run")
    mission = DevMissionStore(tmp_path / "run").require("dmrunner01")
    for name, record in mission.gates.items():
        assert record.approver != record.subject_author, name


def test_the_trace_is_json_serialisable(trace):
    json.dumps(trace)
    assert trace["runner"] == RUNNER_VERSION


# --------------------------------------------------------------------------
# The seven-phase contract
# --------------------------------------------------------------------------


def test_every_completed_step_ran_all_seven_phases_in_order(trace):
    for step in trace["steps"]:
        if step["status"] != "completed":
            continue
        assert tuple(p["phase"] for p in step["phases"]) == PHASES, step["step_id"]
        assert all(p["ok"] for p in step["phases"]), step["step_id"]


def test_each_phase_records_its_own_duration(trace):
    for step in trace["steps"]:
        for phase in step["phases"]:
            assert phase["duration_ms"] >= 0.0


def test_the_runner_declares_no_model_was_used(trace):
    assert trace["model_used"] is None
    assert trace["deterministic"] is True


def test_the_trace_publishes_what_scripted_execution_does_not_establish(trace):
    assert "not" in trace["limitation"]
    assert "model" in trace["limitation"]


# --------------------------------------------------------------------------
# Lineage, timing, failure causes
# --------------------------------------------------------------------------


def test_lineage_edges_connect_real_artifacts(trace):
    produced = {s["output_artifact_id"] for s in trace["steps"] if s["output_artifact_id"]}
    assert trace["lineage"]
    for edge in trace["lineage"]:
        assert edge["from"] in produced
        assert edge["to"] in produced
        assert edge["from"] != edge["to"]


def test_timing_is_reported_per_agent_and_per_phase(trace):
    timing = trace["timing"]
    assert set(timing["per_phase_ms"]) == set(PHASES)
    assert set(timing["per_agent_ms"]) <= set(PARTICIPANTS.values())
    assert timing["slowest_step"]


def test_a_failing_step_records_the_phase_and_the_cause(tmp_path):
    plan = reference_plan()
    broken = replace(
        plan.steps[4], inputs=("never_executed",)
    )  # the research step, fed by a step that does not exist
    plan = replace(plan, steps=plan.steps[:4] + (broken,) + plan.steps[5:])
    trace = AgentRunner(tmp_path / "run").run(plan).to_dict()
    assert trace["completed"] is False
    assert trace["failures"][0]["cause"] == "input_step_not_executed"
    assert trace["failures"][0]["phase"] == "receive"


def test_a_failing_step_stops_the_run_by_default(tmp_path):
    plan = reference_plan()
    broken = replace(plan.steps[4], inputs=("never_executed",))
    plan = replace(plan, steps=plan.steps[:4] + (broken,) + plan.steps[5:])
    trace = AgentRunner(tmp_path / "run").run(plan)
    assert len(trace.steps) == 5


def test_a_run_can_continue_past_a_failure_when_asked(tmp_path):
    plan = reference_plan()
    broken = replace(plan.steps[4], inputs=("never_executed",))
    plan = replace(plan, steps=plan.steps[:4] + (broken,) + plan.steps[5:])
    trace = AgentRunner(tmp_path / "run").run(plan, stop_on_failure=False)
    assert len(trace.steps) == len(plan.steps)
    assert len(trace.failed_steps) >= 1


def test_an_unknown_action_fails_the_step(tmp_path):
    plan = MissionPlan(
        dev_mission_id="dmbad01", title="t", objective="o", starting_sha=SHA,
        participants=("ceo",),
        steps=(PlanStep(step_id="x", action="teleport"),),
    )
    trace = AgentRunner(tmp_path / "run").run(plan)
    assert trace.failed_steps[0].failure_cause == "unknown_action"


def test_a_step_for_an_agent_with_no_handler_fails_at_process(tmp_path):
    plan = MissionPlan(
        dev_mission_id="dmnoh01", title="t", objective="o", starting_sha=SHA,
        participants=("cost-resource",),
        steps=(
            PlanStep(
                step_id="x", action="agent", agent_id="cost-resource",
                kind=ArtifactKind.RESEARCH_FINDINGS.value, title="t", task="t",
            ),
        ),
    )
    trace = AgentRunner(tmp_path / "run").run(plan)
    assert trace.failed_steps[0].failure_cause == "no_handler"
    assert trace.failed_steps[0].failure_phase == "process"


def test_a_step_for_an_unknown_agent_fails_at_receive(tmp_path):
    plan = MissionPlan(
        dev_mission_id="dmunk01", title="t", objective="o", starting_sha=SHA,
        participants=("ghost",),
        steps=(
            PlanStep(
                step_id="x", action="agent", agent_id="ghost",
                kind=ArtifactKind.RESEARCH_FINDINGS.value, title="t", task="t",
            ),
        ),
    )
    trace = AgentRunner(tmp_path / "run").run(plan)
    assert trace.failed_steps[0].failure_phase == "receive"


def test_a_handler_returning_the_wrong_type_fails_at_process(tmp_path):
    runner = AgentRunner(tmp_path / "run")
    runner.override_handler("research", ArtifactKind.RESEARCH_FINDINGS, lambda ctx: "nope")
    plan = reference_plan()
    trace = runner.run(plan)
    failed = trace.failed_steps[0]
    assert failed.failure_cause == "handler_returned_non_mapping"
    assert failed.failure_phase == "process"


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_two_runs_produce_identical_artifact_content(tmp_path):
    run_reference_mission(tmp_path / "a")
    run_reference_mission(tmp_path / "b")
    assert _digests(tmp_path / "a") == _digests(tmp_path / "b")


def test_two_runs_produce_the_same_step_outcomes(tmp_path):
    first = run_reference_mission(tmp_path / "a")
    second = run_reference_mission(tmp_path / "b")
    shape = lambda t: [
        (s["step_id"], s["action"], s["status"], s["output_artifact_id"], s["output_digest"])
        for s in t["steps"]
    ]
    assert shape(first) == shape(second)


def test_artifact_ids_are_derived_from_the_step_index_not_a_random_source():
    assert deterministic_artifact_id("research_findings", "dmx1", 4) == "rese_dmx1_04"
    assert deterministic_artifact_id("research_findings", "dmx1", 4) == (
        deterministic_artifact_id("research_findings", "dmx1", 4)
    )


def test_the_digest_ignores_clocks_only(tmp_path):
    store = ArtifactStore(tmp_path)
    run_reference_mission(tmp_path)
    artifact = store.list("dmrunner01")[0]
    before = artifact_digest(artifact)
    artifact.updated_at += 1000
    artifact.created_at += 1000
    assert artifact_digest(artifact) == before
    artifact.title = "changed"
    assert artifact_digest(artifact) != before


# --------------------------------------------------------------------------
# No bypass
# --------------------------------------------------------------------------


def test_a_self_approved_gate_step_is_refused(tmp_path):
    plan = reference_plan()
    index = next(i for i, s in enumerate(plan.steps) if s.step_id == "gate_research")
    tampered = replace(plan.steps[index], approver="research")
    plan = replace(plan, steps=plan.steps[:index] + (tampered,) + plan.steps[index + 1:])
    trace = AgentRunner(tmp_path / "run").run(plan)
    failed = trace.failed_steps[0]
    assert failed.step_id == "gate_research"
    assert "self_approval_forbidden" in failed.failure_detail


def test_a_gate_citing_the_wrong_evidence_kind_is_refused(tmp_path):
    plan = reference_plan()
    index = next(i for i, s in enumerate(plan.steps) if s.step_id == "gate_research")
    tampered = replace(plan.steps[index], evidence_from=("intake",))
    plan = replace(plan, steps=plan.steps[:index] + (tampered,) + plan.steps[index + 1:])
    trace = AgentRunner(tmp_path / "run").run(plan)
    assert "evidence_wrong_kind" in trace.failed_steps[0].failure_detail


def test_a_gate_with_no_evidence_is_refused(tmp_path):
    plan = reference_plan()
    index = next(i for i, s in enumerate(plan.steps) if s.step_id == "gate_research")
    tampered = replace(plan.steps[index], evidence_from=())
    plan = replace(plan, steps=plan.steps[:index] + (tampered,) + plan.steps[index + 1:])
    trace = AgentRunner(tmp_path / "run").run(plan)
    assert "gate_without_evidence" in trace.failed_steps[0].failure_detail


def test_advancing_past_an_unmet_gate_is_refused(tmp_path):
    plan = reference_plan()
    index = next(i for i, s in enumerate(plan.steps) if s.step_id == "gate_research")
    plan = replace(plan, steps=plan.steps[:index] + plan.steps[index + 1:])
    trace = AgentRunner(tmp_path / "run").run(plan)
    failed = trace.failed_steps[0]
    assert failed.step_id == "to_design"
    assert failed.failure_cause == "gate_not_passed"


def test_only_the_ceo_may_record_the_terminal_verdict(tmp_path):
    plan = reference_plan()
    index = next(i for i, s in enumerate(plan.steps) if s.action == "verdict")
    tampered = replace(plan.steps[index], actor="program-manager")
    plan = replace(plan, steps=plan.steps[:index] + (tampered,) + plan.steps[index + 1:])
    trace = AgentRunner(tmp_path / "run").run(plan)
    assert trace.failed_steps[0].failure_cause == "verdict_not_authored_by_ceo"


def test_a_handler_cannot_forge_the_artifact_envelope(tmp_path):
    """The envelope is the runner's; a handler returning one must not win."""
    runner = AgentRunner(tmp_path / "run")
    runner.override_handler(
        "research",
        ArtifactKind.RESEARCH_FINDINGS,
        lambda ctx: {
            "authoring_agent": "ceo",
            "mission_id": "dmforged1",
            "repository_sha": "0" * 40,
            "claims": [],
            "payload": {"not_investigated": []},
        },
    )
    trace = runner.run(reference_plan())
    failed = trace.failed_steps[0]
    assert failed.step_id == "research"
    assert failed.failure_phase == "produce"
    assert failed.failure_cause == "handler_returned_envelope_field"
    assert "authoring_agent" in failed.failure_detail
    assert "mission_id" in failed.failure_detail


def test_an_agent_writing_a_kind_it_lacks_capability_for_is_refused(tmp_path):
    plan = MissionPlan(
        dev_mission_id="dmcap01", title="t", objective="o", starting_sha=SHA,
        participants=("documentation",),
        steps=(
            PlanStep(
                step_id="x", action="agent", agent_id="documentation",
                kind=ArtifactKind.EXECUTIVE_DECISION.value, title="t", task="t",
            ),
        ),
    )
    runner = AgentRunner(tmp_path / "run")
    runner.override_handler(
        "documentation", ArtifactKind.EXECUTIVE_DECISION,
        lambda ctx: {"payload": {"verdict": "REJECTED", "unresolved_risks": []}},
    )
    trace = runner.run(plan)
    assert trace.failed_steps[0].failure_cause == "author_lacks_capability"


# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------


def test_the_runner_writes_only_inside_its_store(tmp_path):
    root = tmp_path / "run"
    outside = tmp_path / "outside"
    outside.mkdir()
    run_reference_mission(root)
    assert list(outside.iterdir()) == []
    assert {p.name for p in root.iterdir()} == {"dmrunner01"}


def test_the_runner_module_names_no_shell_credential_or_network_verb():
    from pathlib import Path

    from saathi.agentdev import runner as runner_module

    source = Path(runner_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("subprocess", "os.system", "socket", "urllib", "requests",
                      "http", "getenv", "environ"):
        assert forbidden not in source, forbidden


def test_handler_context_exposes_only_the_plan_step_and_inputs():
    fields = set(HandlerContext.__dataclass_fields__)
    assert fields == {"plan", "step", "inputs"}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_cli_runner_plan_lists_the_participants(capsys):
    from saathi.agentdev.cli import main

    assert main(["runner", "plan"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload["participants"]) == set(PARTICIPANTS)


def test_cli_runner_run_executes_and_exits_zero(tmp_path, capsys):
    from saathi.agentdev.cli import main

    code = main(["--store", str(tmp_path / "s"), "runner", "run"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["completed"] is True


def test_cli_runner_run_dry_run_writes_nothing(tmp_path, capsys):
    from saathi.agentdev.cli import main

    store = tmp_path / "s"
    assert main(["--store", str(store), "runner", "run", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert not store.exists()


def test_cli_runner_rejects_a_forbidden_flag(capsys):
    from saathi.agentdev.cli import EXIT_USAGE, main

    assert main(["runner", "run", "--skip-gate"]) == EXIT_USAGE
