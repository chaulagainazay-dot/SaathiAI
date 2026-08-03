"""M351 — Offline simulated development mission.

Runs the twelve-step sequence end to end against the real modules, offline and
deterministically: no provider, no network, no paid call, no repository change.

The mission is deliberately the one the ECC audit surfaced — *should SaathiOS
adopt agent-behaviour evaluation coverage?* — because it lets the simulation
answer a real question while proving the mission, meeting, evidence, review and
decision systems work.

The simulation is **not** a production agent-evaluation platform, and it does
not implement one. It builds only the foundation, runs it, and preserves the
disagreement that a real council would leave behind: the Testing agent's
objection about the boundary between behaviour coverage and prompt compliance
goes unanswered, so the terminal verdict is ``APPROVED_WITH_LIMITATIONS``
rather than a clean approval. That outcome is the point — a simulation that
manufactured unanimity would prove nothing.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from saathi.agentdev.artifacts import (
    INSUFFICIENT_EVIDENCE,
    ArtifactKind,
    ArtifactStore,
    Claim,
    ClaimKind,
    Severity,
    TerminalVerdict,
    make_artifact,
)
from saathi.agentdev.gates import GateEngine
from saathi.agentdev.meetings import (
    MeetingOutcome,
    MeetingPhase,
    MeetingRunner,
    MeetingType,
    disagreement_template,
)
from saathi.agentdev.missions import DevMissionStore, Gate, MissionState

SHA = "53b9b20736d5acf4a7ca3a9bd25b68d01e666a5d"
MISSION_ID = "dmevalcov1"

PARTICIPANTS = [
    "ceo",
    "program-manager",
    "research",
    "architecture",
    "security-governance",
    "testing-verification",
    "cost-resource",
]

OBJECTIVE = (
    "Evaluate whether SaathiOS should adopt ECC-style agent-behaviour "
    "evaluation coverage."
)


def _challenge_body(**overrides: str) -> dict[str, str]:
    body = disagreement_template()
    body.update(overrides)
    return body


def run_offline_mission(
    store_dir: str | Path | None = None, *, dry_run: bool = False
) -> dict[str, Any]:
    """Execute the twelve-step mission. Returns a full trace."""
    started = time.perf_counter()
    root = Path(store_dir) if store_dir else Path(
        tempfile.mkdtemp(prefix="agentdev_simulation_")
    )
    root.mkdir(parents=True, exist_ok=True)

    artifacts = ArtifactStore(root)
    missions = DevMissionStore(root)
    gates = GateEngine(artifacts, missions)
    meetings = MeetingRunner(artifacts, missions, root=root)

    steps: list[dict[str, Any]] = []

    def record(number: int, name: str, actor: str, **detail: Any) -> None:
        steps.append({"step": number, "name": name, "actor": actor, **detail})

    if dry_run:
        return {
            "dry_run": True,
            "completed": True,
            "would_run": [
                "1 CEO states the strategic objective",
                "2 Program Manager decomposes the mission",
                "3 Research investigates agent-evaluation patterns",
                "4 Architecture proposes a SaathiOS-native design",
                "5 Security challenges authority, data and execution risk",
                "6 Testing defines measurable behaviour tests",
                "7 Cost assesses runtime and model-cost impact",
                "8 Research Review meeting",
                "9 Architecture Council",
                "10 Red-Team Review",
                "11 CEO produces the final decision",
                "12 Mission closes without production changes",
            ],
            "store": str(root),
            "note": "Nothing was created.",
        }

    # ---- 1. CEO states the strategic objective ----------------------------
    mission = missions.create(
        title="Agent-behaviour evaluation coverage",
        objective=OBJECTIVE,
        starting_sha=SHA,
        created_by="ceo",
        participants=PARTICIPANTS,
        dev_mission_id=MISSION_ID,
    )
    intake = make_artifact(
        mission_id=MISSION_ID,
        kind=ArtifactKind.MISSION_INTAKE,
        authoring_agent="ceo",
        repository_sha=SHA,
        title="Strategic objective: agent-behaviour evaluation coverage",
        required_next_action="program manager decomposes the mission",
        body=OBJECTIVE,
        payload={
            "sufficient_evidence_looks_like": [
                "a source-backed count of existing behaviour coverage",
                "a design that reuses existing SaathiOS systems",
                "a security verdict on authority and execution risk",
                "a measured cost against the host ceilings",
            ],
        },
    )
    artifacts.put(intake)
    record(1, "strategic objective", "ceo", artifact=intake.artifact_id)

    # ---- 2. Program Manager decomposes -------------------------------------
    missions.advance(MISSION_ID, MissionState.DECOMPOSED, actor="program-manager")
    assignment_ids = []
    for owner, task, done_when in (
        ("research", "Investigate agent-evaluation patterns",
         "Every claim labelled fact, inference or assumption with a source."),
        ("architecture", "Propose a SaathiOS-native design",
         "Every new component justified against existing systems."),
        ("security-governance", "Challenge authority, data and execution risk",
         "Trading Guardian and global config impact stated explicitly."),
        ("testing-verification", "Define measurable behaviour tests",
         "Each acceptance criterion has a runnable assertion."),
        ("cost-resource", "Assess runtime and model-cost impact",
         "Every number names its measurement method."),
    ):
        assignment = make_artifact(
            mission_id=MISSION_ID,
            kind=ArtifactKind.TASK_ASSIGNMENT,
            authoring_agent="program-manager",
            repository_sha=SHA,
            title=f"Assignment: {task}",
            required_next_action=f"{owner} produces its required output",
            dependencies=[intake.artifact_id],
            payload={"owner": owner, "task": task, "definition_of_done": done_when},
        )
        artifacts.put(assignment)
        assignment_ids.append(assignment.artifact_id)
    record(2, "mission decomposed", "program-manager", assignments=len(assignment_ids))

    missions.advance(MISSION_ID, MissionState.RESEARCH, actor="program-manager")

    # ---- 3. Research investigates -------------------------------------------
    findings = make_artifact(
        mission_id=MISSION_ID,
        kind=ArtifactKind.RESEARCH_FINDINGS,
        authoring_agent="research",
        repository_sha=SHA,
        title="Agent-evaluation coverage in SaathiOS and elsewhere",
        required_next_action="architecture proposes a design",
        dependencies=[assignment_ids[0]],
        claims=[
            Claim(
                claim_id="r1",
                statement="The repository contains 343 test files under tests/.",
                kind=ClaimKind.FACT.value,
                evidence_ref="tests/ (file count at 53b9b20)",
            ),
            Claim(
                claim_id="r2",
                statement=(
                    "No test file asserts agent or prompt behaviour; all assert "
                    "code behaviour."
                ),
                kind=ClaimKind.FACT.value,
                evidence_ref="tests/test_m*.py naming and contents at 53b9b20",
            ),
            Claim(
                claim_id="r3",
                statement=(
                    "SaathiOS therefore has no regression signal for governance "
                    "behaviour changes."
                ),
                kind=ClaimKind.INFERENCE.value,
                rests_on=["r1", "r2"],
            ),
            Claim(
                claim_id="r4",
                statement=(
                    "A behaviour suite would have caught a silent widening of an "
                    "agent's authority."
                ),
                kind=ClaimKind.ASSUMPTION.value,
                falsified_by=(
                    "A widening that produces no observable refusal difference."
                ),
            ),
            Claim(
                claim_id="r5",
                statement=INSUFFICIENT_EVIDENCE,
                kind=ClaimKind.FACT.value,
            ),
        ],
        limitations=[
            "ECC's own evaluation harness was read as a reference only, not run.",
        ],
        unresolved_questions=[
            "What false-positive rate would a behaviour suite carry over time?",
        ],
        payload={
            "not_investigated": [
                "Long-run flakiness of behaviour assertions",
                "Cost of behaviour evaluation against a live provider",
            ],
            "insufficient_evidence_on": [
                "Whether behaviour coverage reduces incident rate — no baseline exists.",
            ],
        },
    )
    artifacts.put(findings)
    record(3, "research findings", "research", artifact=findings.artifact_id,
           facts=len(findings.claims_of(ClaimKind.FACT)),
           inferences=len(findings.claims_of(ClaimKind.INFERENCE)),
           assumptions=len(findings.claims_of(ClaimKind.ASSUMPTION)))

    # ---- 8a. Research Review meeting ---------------------------------------
    research_review = meetings.create(
        dev_mission_id=MISSION_ID,
        meeting_type=MeetingType.RESEARCH_REVIEW,
        chair="program-manager",
        questions=[
            "Is the evidence sufficient to design against?",
            "What was not investigated, and does it matter?",
        ],
        repository_sha=SHA,
    )
    meetings.open_phase(MISSION_ID, research_review.meeting_id,
                        MeetingPhase.COLLECTING, actor="program-manager")
    meetings.submit(MISSION_ID, research_review.meeting_id, findings)
    product_case = make_artifact(
        mission_id=MISSION_ID,
        kind=ArtifactKind.PROPOSAL,
        authoring_agent="product-strategy",
        repository_sha=SHA,
        title="Product case for behaviour coverage",
        required_next_action="architecture proposes a design",
        payload={
            "problem": "A governance regression is invisible until it causes harm.",
            "do_nothing_alternative": (
                "Continue relying on code tests; accept that authority changes "
                "ship unverified."
            ),
            "existing_capability_overlap": "saathi/security/redteam covers attacks, not agent behaviour.",
        },
    )
    meetings.submit(MISSION_ID, research_review.meeting_id, product_case)
    meetings.open_phase(MISSION_ID, research_review.meeting_id,
                        MeetingPhase.CHALLENGING, actor="program-manager")
    rr_challenge = make_artifact(
        mission_id=MISSION_ID,
        kind=ArtifactKind.CHALLENGE,
        authoring_agent="security-governance",
        repository_sha=SHA,
        title="Authority scenarios are missing from scope",
        required_next_action="research responds",
        dependencies=[findings.artifact_id],
        payload=_challenge_body(
            claim="The findings do not cover authority-boundary behaviour.",
            evidence="No claim in the findings mentions approval or veto behaviour.",
            counterargument=(
                "Behaviour coverage without authority coverage would miss the "
                "regressions that matter most here."
            ),
            failure_mode="A widened agent authority ships with a green suite.",
            risk="Governance regression reaches the owner unnoticed.",
            alternative="Require authority scenarios in the first suite.",
            decision_required="Are authority scenarios in scope for the first suite?",
        ),
    )
    meetings.challenge(MISSION_ID, research_review.meeting_id, rr_challenge)
    meetings.open_phase(MISSION_ID, research_review.meeting_id,
                        MeetingPhase.RESPONDING, actor="program-manager")
    rr_response = make_artifact(
        mission_id=MISSION_ID,
        kind=ArtifactKind.RESPONSE,
        authoring_agent="research",
        repository_sha=SHA,
        title="Accepted: authority scenarios are in scope",
        required_next_action="architecture includes them in the design",
        dependencies=[rr_challenge.artifact_id],
        payload={
            "position": "accepted",
            "detail": (
                "Authority scenarios become BE-03, BE-05, BE-06 and BE-09 in the "
                "first suite."
            ),
        },
    )
    meetings.respond(MISSION_ID, research_review.meeting_id, rr_response)
    meetings.open_phase(MISSION_ID, research_review.meeting_id,
                        MeetingPhase.SYNTHESIZING, actor="program-manager")
    _, rr_minutes = meetings.finalize(
        MISSION_ID,
        research_review.meeting_id,
        actor="program-manager",
        agreements=[
            "The evidence is sufficient to design against.",
            "Authority scenarios are in scope for the first suite.",
        ],
        outcome=MeetingOutcome.DECIDED,
        repository_sha=SHA,
    )
    record(8, "research review meeting", "program-manager",
           meeting=research_review.meeting_id, outcome="decided",
           minutes=rr_minutes.artifact_id)

    gates.pass_gate(
        MISSION_ID, Gate.RESEARCH_COMPLETENESS,
        approver="architecture", subject_author="research",
        evidence_artifact_ids=[findings.artifact_id],
        reason="Claims labelled and sourced; not-investigated list present.",
    )
    missions.advance(MISSION_ID, MissionState.DESIGN, actor="program-manager")

    # ---- 4. Architecture proposes -------------------------------------------
    design = make_artifact(
        mission_id=MISSION_ID,
        kind=ArtifactKind.ARCHITECTURE_DECISION,
        authoring_agent="architecture",
        repository_sha=SHA,
        title="SaathiOS-native behaviour evaluation foundation",
        required_next_action="security reviews authority and execution risk",
        dependencies=[findings.artifact_id, product_case.artifact_id],
        payload={
            "reuse_table": [
                {"component": "saathi/agentdev/gates.py", "extension": "scenarios drive the real gate engine"},
                {"component": "saathi/agentdev/missions.py", "extension": "scenarios drive real lifecycle refusals"},
                {"component": "saathi.safety.SafetyLevel", "extension": "authority vocabulary unchanged"},
                {"component": "tests/test_m*.py convention", "extension": "suite runs under the existing pytest setup"},
            ],
            "new_components": [
                {
                    "name": "saathi/agentdev/behavior_evals.py",
                    "why_no_existing_component": (
                        "343 test files assert code behaviour; none assert agent "
                        "behaviour, and no module models an enforcement tier."
                    ),
                },
            ],
            "rollback_path": "git revert; the module has no callers in the product surface.",
        },
    )
    artifacts.put(design)
    record(4, "architecture proposal", "architecture", artifact=design.artifact_id)

    # ---- 6. Testing defines measurable behaviour tests ----------------------
    from saathi.agentdev.behavior_evals import run_suite

    suite = run_suite(store_dir=root / "behaviour")
    test_plan = make_artifact(
        mission_id=MISSION_ID,
        kind=ArtifactKind.VERIFICATION_REPORT,
        authoring_agent="testing-verification",
        repository_sha=SHA,
        title="Behaviour scenario suite, first run",
        required_next_action="red team attacks the design",
        worktree=str(root),
        branch="milestone/m344-m351-multi-agent-development-foundation",
        dependencies=[design.artifact_id],
        payload={
            "results": [
                {
                    "command": "python -c 'from saathi.agentdev.behavior_evals import run_suite; run_suite()'",
                    "outcome": "pass" if suite["failed"] == 0 else "fail",
                    "total": suite["total"],
                    "passed": suite["passed"],
                }
            ],
            "negative_paths": [
                {
                    "scenario": r["scenario_id"],
                    "expected": r["expected"],
                    "actual": r["observed"],
                }
                for r in suite["results"]
            ],
            "not_run": [
                "Live-provider behaviour evaluation (no provider is connected).",
                "Long-run flakiness measurement (needs history this milestone lacks).",
            ],
            "by_enforcement_tier": suite["by_enforcement_tier"],
        },
    )
    artifacts.put(test_plan)
    record(6, "behaviour tests defined and run", "testing-verification",
           artifact=test_plan.artifact_id, scenarios=suite["total"],
           passed=suite["passed"])

    # ---- 7. Cost assesses ---------------------------------------------------
    cost = make_artifact(
        mission_id=MISSION_ID,
        kind=ArtifactKind.RESEARCH_FINDINGS,
        authoring_agent="cost-resource",
        repository_sha=SHA,
        title="Cost and resource assessment",
        required_next_action="council weighs cost against benefit",
        dependencies=[design.artifact_id],
        claims=[
            Claim(
                claim_id="k1",
                statement=(
                    f"The behaviour suite runs in {suite['duration_ms']:.0f} ms "
                    "offline."
                ),
                kind=ClaimKind.FACT.value,
                evidence_ref="run_suite() duration_ms on this host",
            ),
            Claim(
                claim_id="k2",
                statement="The suite makes zero model or provider calls.",
                kind=ClaimKind.FACT.value,
                evidence_ref="behavior_evals imports no provider client",
            ),
            Claim(
                claim_id="k3",
                statement=(
                    "Adding the suite to CI costs no additional model spend."
                ),
                kind=ClaimKind.INFERENCE.value,
                rests_on=["k2"],
            ),
            Claim(
                claim_id="k4",
                statement=INSUFFICIENT_EVIDENCE,
                kind=ClaimKind.FACT.value,
            ),
        ],
        limitations=[
            "Peak memory was not instrumented; only wall-clock was measured.",
        ],
        payload={
            "not_investigated": ["Peak RSS of the suite process"],
            "host_ceilings": {
                "max_reasoning_agents": 2,
                "max_coding_agents": 1,
                "max_testing_agents": 1,
                "max_local_model_instances": 1,
            },
            "measured": {
                "suite_duration_ms": suite["duration_ms"],
                "model_calls": 0,
                "external_paid_calls": 0,
            },
            "unmeasurable": ["incident-rate reduction — no baseline exists"],
        },
    )
    artifacts.put(cost)
    record(7, "cost assessment", "cost-resource", artifact=cost.artifact_id)

    # ---- 9. Architecture Council -------------------------------------------
    council = meetings.create(
        dev_mission_id=MISSION_ID,
        meeting_type=MeetingType.ARCHITECTURE_COUNCIL,
        chair="architecture",
        questions=[
            "Does the design duplicate an existing SaathiOS system?",
            "Is the enforcement-tier model honest?",
        ],
        repository_sha=SHA,
    )
    meetings.open_phase(MISSION_ID, council.meeting_id,
                        MeetingPhase.COLLECTING, actor="architecture")
    meetings.submit(MISSION_ID, council.meeting_id, design)
    meetings.submit(MISSION_ID, council.meeting_id, test_plan)
    meetings.open_phase(MISSION_ID, council.meeting_id,
                        MeetingPhase.CHALLENGING, actor="architecture")
    council_challenge = make_artifact(
        mission_id=MISSION_ID,
        kind=ArtifactKind.CHALLENGE,
        authoring_agent="security-governance",
        repository_sha=SHA,
        title="The suite must not claim prevention it does not provide",
        required_next_action="architecture responds",
        dependencies=[design.artifact_id],
        payload=_challenge_body(
            claim="A passing behaviour suite could be read as proof of enforcement.",
            evidence="Scenarios BE-01, BE-02, BE-04 and BE-07 are schema checks, not runtime sandboxes.",
            counterargument="Reporting them undifferentiated would overstate the guarantee.",
            failure_mode="An operator trusts a control that only detects, never prevents.",
            risk="False confidence in the isolation boundary.",
            alternative="Every scenario declares its enforcement tier in its result.",
            decision_required="Must each scenario carry an enforcement tier?",
        ),
    )
    meetings.challenge(MISSION_ID, council.meeting_id, council_challenge)
    meetings.open_phase(MISSION_ID, council.meeting_id,
                        MeetingPhase.RESPONDING, actor="architecture")
    council_response = make_artifact(
        mission_id=MISSION_ID,
        kind=ArtifactKind.RESPONSE,
        authoring_agent="architecture",
        repository_sha=SHA,
        title="Accepted: every scenario declares its enforcement tier",
        required_next_action="red team verifies the tiers are accurate",
        dependencies=[council_challenge.artifact_id],
        payload={
            "position": "accepted",
            "detail": (
                "ScenarioResult carries enforcement and proves; the suite reports "
                "by_enforcement_tier and states its limitation."
            ),
        },
    )
    meetings.respond(MISSION_ID, council.meeting_id, council_response)
    meetings.open_phase(MISSION_ID, council.meeting_id,
                        MeetingPhase.SYNTHESIZING, actor="architecture")
    _, council_minutes = meetings.finalize(
        MISSION_ID,
        council.meeting_id,
        actor="architecture",
        agreements=[
            "The design reuses the gate engine and mission store rather than duplicating them.",
            "Every scenario declares its enforcement tier.",
        ],
        outcome=MeetingOutcome.DECIDED,
        repository_sha=SHA,
    )
    record(9, "architecture council", "architecture",
           meeting=council.meeting_id, outcome="decided",
           minutes=council_minutes.artifact_id)

    gates.pass_gate(
        MISSION_ID, Gate.ARCHITECTURE_APPROVAL,
        approver="security-governance", subject_author="architecture",
        evidence_artifact_ids=[design.artifact_id],
        reason="Reuse table complete; the one new component is justified.",
    )
    missions.advance(MISSION_ID, MissionState.SECURITY_REVIEW, actor="program-manager")

    # ---- 5. Security challenges and reviews ---------------------------------
    security_review = make_artifact(
        mission_id=MISSION_ID,
        kind=ArtifactKind.SECURITY_REVIEW,
        authoring_agent="security-governance",
        repository_sha=SHA,
        title="Security review of the behaviour-evaluation foundation",
        required_next_action="red team attacks the claim",
        dependencies=[design.artifact_id, test_plan.artifact_id],
        claims=[
            Claim(
                claim_id="s1",
                statement=(
                    "The suite reads governance state and writes only to a "
                    "temporary store."
                ),
                kind=ClaimKind.FACT.value,
                evidence_ref="behavior_evals.run_suite uses tempfile.mkdtemp",
            ),
            Claim(
                claim_id="s2",
                statement=(
                    "Scenario BE-02 establishes detection, not prevention, of a "
                    "worktree escape."
                ),
                kind=ClaimKind.FACT.value,
                evidence_ref="behavior_evals BE-02 enforcement=schema_validated",
                severity=Severity.MEDIUM.value,
            ),
        ],
        limitations=[
            "No scenario can prove compliance of a model given an unrestricted shell.",
        ],
        payload={
            "verdict": "pass_with_limitations",
            "trading_guardian_impact": (
                "None. saathi/agentdev imports nothing from "
                "saathi.platform.trading_guardian and changes no control."
            ),
            "global_config_impact": (
                "None. config_protection refuses writes to ~/.claude, "
                "~/.config/opencode, shell rc files, MCP config and credentials."
            ),
            "authority_impact": (
                "No new authority. All twelve denials remain false and are "
                "re-applied after every settings load."
            ),
            "execution_impact": "Offline only; zero provider calls, zero paid calls.",
        },
    )
    artifacts.put(security_review)
    record(5, "security review", "security-governance",
           artifact=security_review.artifact_id, verdict="pass_with_limitations")

    gates.pass_gate(
        MISSION_ID, Gate.SECURITY_APPROVAL,
        approver="security-governance", subject_author="architecture",
        evidence_artifact_ids=[security_review.artifact_id],
        reason="Trading Guardian and global config impact stated as none.",
    )

    # ---- 10. Red-Team Review ------------------------------------------------
    red_team = meetings.create(
        dev_mission_id=MISSION_ID,
        meeting_type=MeetingType.RED_TEAM_REVIEW,
        chair="security-governance",
        questions=[
            "Where would this foundation give false confidence?",
            "What would a hostile reading of the evidence conclude?",
        ],
        repository_sha=SHA,
    )
    meetings.open_phase(MISSION_ID, red_team.meeting_id,
                        MeetingPhase.COLLECTING, actor="security-governance")
    meetings.submit(MISSION_ID, red_team.meeting_id, security_review)
    meetings.open_phase(MISSION_ID, red_team.meeting_id,
                        MeetingPhase.CHALLENGING, actor="security-governance")
    red_team_challenge = make_artifact(
        mission_id=MISSION_ID,
        kind=ArtifactKind.CHALLENGE,
        authoring_agent="testing-verification",
        repository_sha=SHA,
        title="Ten scenarios cannot bound the behaviour space",
        required_next_action="owner decides how much coverage is enough",
        dependencies=[security_review.artifact_id],
        payload=_challenge_body(
            claim=(
                "Ten deterministic scenarios establish that ten specific refusals "
                "hold, not that agent behaviour is covered."
            ),
            evidence=(
                "The suite asserts refusals of the orchestration layer; no "
                "scenario exercises a model at all."
            ),
            counterargument=(
                "Calling this 'behaviour coverage' invites the same overstatement "
                "the council just rejected one level down."
            ),
            failure_mode=(
                "A future change to prompt-level guidance passes the suite "
                "unchanged, and is read as verified."
            ),
            risk="The gap between evaluated and enforced widens invisibly.",
            alternative=(
                "Name the suite 'governance refusal coverage' and defer behaviour "
                "coverage until a model is in the loop."
            ),
            decision_required=(
                "Is the first suite allowed to be named behaviour coverage before "
                "any model participates?"
            ),
        ),
    )
    meetings.challenge(MISSION_ID, red_team.meeting_id, red_team_challenge)
    meetings.open_phase(MISSION_ID, red_team.meeting_id,
                        MeetingPhase.RESPONDING, actor="security-governance")
    # Deliberately unanswered: this is a real disagreement, and manufacturing a
    # response here would be exactly the failure the protocol exists to prevent.
    meetings.open_phase(MISSION_ID, red_team.meeting_id,
                        MeetingPhase.SYNTHESIZING, actor="security-governance")
    red_team_meeting, red_team_minutes = meetings.finalize(
        MISSION_ID,
        red_team.meeting_id,
        actor="security-governance",
        agreements=[],
        outcome=MeetingOutcome.BLOCKED,
        repository_sha=SHA,
    )
    record(10, "red-team review", "security-governance",
           meeting=red_team.meeting_id, outcome="blocked",
           minutes=red_team_minutes.artifact_id,
           preserved_disagreements=len(red_team_meeting.preserved_disagreements))

    gates.pass_gate(
        MISSION_ID, Gate.RED_TEAM_REVIEW,
        approver="security-governance", subject_author="architecture",
        evidence_artifact_ids=[red_team_minutes.artifact_id],
        reason="One disagreement preserved and carried forward unresolved.",
    )

    missions.advance(MISSION_ID, MissionState.EXECUTIVE_DECISION,
                     actor="program-manager",
                     reason="No code is produced; the mission answers a question.")

    # ---- 11. CEO produces the final decision --------------------------------
    mission_now = missions.require(MISSION_ID)
    verdict = (
        TerminalVerdict.APPROVED_WITH_LIMITATIONS
        if mission_now.unresolved_disagreements
        else TerminalVerdict.APPROVED_FOR_IMPLEMENTATION
    )
    decision = make_artifact(
        mission_id=MISSION_ID,
        kind=ArtifactKind.EXECUTIVE_DECISION,
        authoring_agent="ceo",
        repository_sha=SHA,
        title="Adopt the behaviour-evaluation foundation, with limitations",
        required_next_action="owner reviews before any further scope is granted",
        dependencies=[
            rr_minutes.artifact_id,
            council_minutes.artifact_id,
            red_team_minutes.artifact_id,
        ],
        payload={
            "verdict": verdict.value,
            "rationale": (
                "The gap is real and source-backed: 343 code test files, none "
                "asserting agent behaviour. The foundation reuses existing "
                "systems and adds no authority. It is adopted as a foundation "
                "only."
            ),
            "unresolved_risks": [
                {
                    "risk": (
                        "Ten scenarios bound ten refusals, not the behaviour space."
                    ),
                    "raised_by": "testing-verification",
                    "challenge_id": red_team_challenge.artifact_id,
                    "carried_because": (
                        "Resolving it needs a model in the loop, which this "
                        "milestone deliberately does not connect."
                    ),
                },
                {
                    "risk": "Peak memory of the suite was not instrumented.",
                    "raised_by": "cost-resource",
                    "carried_because": "Wall-clock only was measured on this host.",
                },
            ],
            "limitations": [
                "No production agent-evaluation platform was built or implied.",
                "Scenarios at schema_validated tier establish detection, not prevention.",
            ],
            "owner_decision_required_on": [
                "Whether the suite may be named behaviour coverage before a model participates.",
            ],
        },
    )
    artifacts.put(decision)
    missions.set_terminal_verdict(MISSION_ID, verdict.value, actor="ceo")
    gates.pass_gate(
        MISSION_ID, Gate.EXECUTIVE_SYNTHESIS,
        approver="program-manager", subject_author="ceo",
        evidence_artifact_ids=[decision.artifact_id],
        reason="Every preserved disagreement is restated as an unresolved risk.",
    )
    record(11, "executive decision", "ceo", artifact=decision.artifact_id,
           verdict=verdict.value)

    # ---- 12. Mission closes without production changes ----------------------
    missions.advance(MISSION_ID, MissionState.CLOSED, actor="ceo",
                     reason="Decision recorded; no production change was made.")
    final = missions.status(MISSION_ID)
    record(12, "mission closed", "ceo", state=final["state"],
           verdict=final["terminal_verdict"])

    all_artifacts = artifacts.list(MISSION_ID)
    return {
        "completed": True,
        "dev_mission_id": MISSION_ID,
        "objective": OBJECTIVE,
        "store": str(root),
        "steps": steps,
        "participants": PARTICIPANTS,
        "artifact_count": len(all_artifacts),
        "artifact_kinds": sorted({a.kind for a in all_artifacts}),
        "meetings": [
            meetings.status(MISSION_ID, m.meeting_id)
            for m in meetings.list(MISSION_ID)
        ],
        "gates": gates.report(MISSION_ID)["gates"],
        "preserved_disagreements": final["unresolved_disagreements"],
        "terminal_verdict": final["terminal_verdict"],
        "final_state": final["state"],
        "behaviour_suite": {
            "total": suite["total"],
            "passed": suite["passed"],
            "failed": suite["failed"],
            "by_enforcement_tier": suite["by_enforcement_tier"],
        },
        "production_changes": [],
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "note": (
            "Offline and deterministic. No provider, no network, no paid call, "
            "no repository change, no push, no merge, no deploy. The verdict is "
            "APPROVED_WITH_LIMITATIONS because a real disagreement was left "
            "unresolved rather than manufactured away."
        ),
    }
