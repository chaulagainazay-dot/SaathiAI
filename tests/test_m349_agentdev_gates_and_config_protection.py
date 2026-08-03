"""M349 — Lifecycle gates, independent review, and configuration protection."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from saathi.agentdev.artifacts import (
    ArtifactKind,
    ArtifactStatus,
    ArtifactStore,
    Claim,
    Severity,
    TerminalVerdict,
    make_artifact,
)
from saathi.agentdev.config_protection import (
    PROTECTED_BASENAMES,
    PROTECTED_HOME_PREFIXES,
    ConfigChangeProposal,
    ConfigProtectionError,
    assert_change_allowed,
    assert_write_allowed,
    classify_path,
    is_protected,
    protected_surface,
    validate_proposal,
)
from saathi.agentdev.gates import (
    GATE_EVIDENCE_KIND,
    OWNER_ONLY_GATES,
    SECURITY_OWNED_GATES,
    GateEngine,
    GateError,
    review_finding_requirements,
    unresolved_critical_findings,
)
from saathi.agentdev.missions import DevMissionStore, Gate

SHA = "53b9b20736d5acf4a7ca3a9bd25b68d01e666a5d"


@pytest.fixture
def engine(tmp_path: Path):
    root = tmp_path / "agentdev"
    return GateEngine(ArtifactStore(root), DevMissionStore(root))


@pytest.fixture
def mission(engine: GateEngine):
    return engine.missions.create(
        title="Evaluate evaluation coverage",
        objective="Decide whether to adopt it.",
        starting_sha=SHA,
    )


def _findings(engine, mission, **overrides):
    payload = {
        "mission_id": mission.dev_mission_id,
        "kind": ArtifactKind.RESEARCH_FINDINGS,
        "authoring_agent": "research",
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
    artifact = make_artifact(**payload)
    engine.artifacts.put(artifact)
    return artifact


# --------------------------------------------------------------------------
# The gate map
# --------------------------------------------------------------------------


def test_every_gate_declares_its_required_evidence_kind():
    for gate in Gate:
        assert gate in GATE_EVIDENCE_KIND, gate


def test_the_eleven_lifecycle_gates_exist():
    assert {g.value for g in Gate} == {
        "research_completeness",
        "architecture_approval",
        "security_approval",
        "implementation_readiness",
        "code_review",
        "automated_testing",
        "negative_path_testing",
        "red_team_review",
        "executive_synthesis",
        "owner_approval",
        "integration_candidacy",
    }


def test_owner_approval_is_owner_only():
    assert Gate.OWNER_APPROVAL in OWNER_ONLY_GATES


def test_security_gates_are_security_owned():
    assert SECURITY_OWNED_GATES == {Gate.SECURITY_APPROVAL, Gate.RED_TEAM_REVIEW}


# --------------------------------------------------------------------------
# No self-approval
# --------------------------------------------------------------------------


def test_an_agent_cannot_approve_its_own_output(engine, mission):
    artifact = _findings(engine, mission)
    decision = engine.evaluate(
        mission.dev_mission_id,
        Gate.RESEARCH_COMPLETENESS,
        approver="research",
        subject_author="research",
        evidence_artifact_ids=[artifact.artifact_id],
    )
    assert not decision.allowed
    assert "self_approval_forbidden" in decision.refusals


def test_pass_gate_refuses_self_approval(engine, mission):
    artifact = _findings(engine, mission)
    with pytest.raises(GateError) as exc:
        engine.pass_gate(
            mission.dev_mission_id,
            Gate.RESEARCH_COMPLETENESS,
            approver="research",
            subject_author="research",
            evidence_artifact_ids=[artifact.artifact_id],
        )
    assert exc.value.code == "gate_refused"
    assert "self_approval_forbidden" in exc.value.detail


def test_failing_a_gate_also_cannot_be_self_recorded(engine, mission):
    with pytest.raises(GateError) as exc:
        engine.fail_gate(
            mission.dev_mission_id,
            Gate.RESEARCH_COMPLETENESS,
            approver="research",
            subject_author="research",
            reason="not good enough",
        )
    assert exc.value.code == "self_approval_forbidden"


def test_an_undeclared_reviewer_cannot_pass_a_gate(engine, mission):
    artifact = _findings(engine, mission)
    decision = engine.evaluate(
        mission.dev_mission_id,
        Gate.RESEARCH_COMPLETENESS,
        approver="documentation",
        subject_author="research",
        evidence_artifact_ids=[artifact.artifact_id],
    )
    assert not decision.allowed
    assert any("reviewer_not_declared_for" in r for r in decision.refusals)


def test_a_declared_reviewer_passes_the_gate(engine, mission):
    artifact = _findings(engine, mission)
    updated, decision = engine.pass_gate(
        mission.dev_mission_id,
        Gate.RESEARCH_COMPLETENESS,
        approver="architecture",
        subject_author="research",
        evidence_artifact_ids=[artifact.artifact_id],
    )
    assert decision.allowed
    assert updated.gate(Gate.RESEARCH_COMPLETENESS).passed
    assert updated.gate(Gate.RESEARCH_COMPLETENESS).approver == "architecture"


# --------------------------------------------------------------------------
# Owner-only gates
# --------------------------------------------------------------------------


def test_no_agent_may_pass_the_owner_approval_gate(engine, mission):
    approval = make_artifact(
        mission_id=mission.dev_mission_id,
        kind=ArtifactKind.OWNER_APPROVAL,
        authoring_agent="owner",
        repository_sha=SHA,
        title="Owner approval",
        required_next_action="close",
        payload={"approved": True},
    )
    engine.artifacts.put(approval)
    decision = engine.evaluate(
        mission.dev_mission_id,
        Gate.OWNER_APPROVAL,
        approver="ceo",
        subject_author="owner",
        evidence_artifact_ids=[approval.artifact_id],
    )
    assert not decision.allowed
    assert "owner_only_gate:owner_approval" in decision.refusals


def test_the_owner_passes_the_owner_gate(engine, mission):
    approval = make_artifact(
        mission_id=mission.dev_mission_id,
        kind=ArtifactKind.OWNER_APPROVAL,
        authoring_agent="owner",
        repository_sha=SHA,
        title="Owner approval",
        required_next_action="close",
        payload={"approved": True},
    )
    engine.artifacts.put(approval)
    _, decision = engine.pass_gate(
        mission.dev_mission_id,
        Gate.OWNER_APPROVAL,
        approver="owner",
        subject_author="ceo",
        evidence_artifact_ids=[approval.artifact_id],
    )
    assert decision.allowed


def test_the_owner_may_not_pass_agent_gates(engine, mission):
    artifact = _findings(engine, mission)
    decision = engine.evaluate(
        mission.dev_mission_id,
        Gate.RESEARCH_COMPLETENESS,
        approver="owner",
        subject_author="research",
        evidence_artifact_ids=[artifact.artifact_id],
    )
    assert "owner_may_only_pass_owner_gates" in decision.refusals


def test_only_security_may_pass_a_security_gate(engine, mission):
    review = make_artifact(
        mission_id=mission.dev_mission_id,
        kind=ArtifactKind.SECURITY_REVIEW,
        authoring_agent="security-governance",
        repository_sha=SHA,
        title="Security review",
        required_next_action="decide",
        payload={
            "verdict": "pass",
            "trading_guardian_impact": "none",
            "global_config_impact": "none",
        },
    )
    engine.artifacts.put(review)
    decision = engine.evaluate(
        mission.dev_mission_id,
        Gate.SECURITY_APPROVAL,
        approver="architecture",
        subject_author="security-governance",
        evidence_artifact_ids=[review.artifact_id],
    )
    assert any(
        r.startswith("security_gate_requires_security_role") for r in decision.refusals
    )


# --------------------------------------------------------------------------
# Evidence requirements
# --------------------------------------------------------------------------


def test_a_gate_without_evidence_is_refused(engine, mission):
    decision = engine.evaluate(
        mission.dev_mission_id,
        Gate.RESEARCH_COMPLETENESS,
        approver="architecture",
        subject_author="research",
        evidence_artifact_ids=[],
    )
    assert "gate_without_evidence" in decision.refusals


def test_missing_evidence_is_reported_by_id(engine, mission):
    decision = engine.evaluate(
        mission.dev_mission_id,
        Gate.RESEARCH_COMPLETENESS,
        approver="architecture",
        subject_author="research",
        evidence_artifact_ids=["ghost_1"],
    )
    assert "evidence_not_found:ghost_1" in decision.refusals


def test_evidence_of_the_wrong_kind_is_refused(engine, mission):
    proposal = make_artifact(
        mission_id=mission.dev_mission_id,
        kind=ArtifactKind.PROPOSAL,
        authoring_agent="product-strategy",
        repository_sha=SHA,
        title="A proposal",
        required_next_action="review",
    )
    engine.artifacts.put(proposal)
    decision = engine.evaluate(
        mission.dev_mission_id,
        Gate.RESEARCH_COMPLETENESS,
        approver="ceo",
        subject_author="product-strategy",
        evidence_artifact_ids=[proposal.artifact_id],
    )
    assert any(r.startswith("evidence_wrong_kind") for r in decision.refusals)


def test_evidence_must_be_the_subjects_own_work(engine, mission):
    artifact = _findings(engine, mission)
    decision = engine.evaluate(
        mission.dev_mission_id,
        Gate.RESEARCH_COMPLETENESS,
        approver="architecture",
        subject_author="product-strategy",
        evidence_artifact_ids=[artifact.artifact_id],
    )
    assert "evidence_not_authored_by_subject:product-strategy" in decision.refusals


# --------------------------------------------------------------------------
# Critical findings and vetoes
# --------------------------------------------------------------------------


def _critical_claim() -> Claim:
    return Claim(
        claim_id="crit",
        statement="Writable scope escapes the worktree.",
        kind="fact",
        evidence_ref="saathi/agentdev/roles.py:1",
        severity=Severity.CRITICAL.value,
        source_location="saathi/agentdev/roles.py:1",
        failure_mode="An agent writes outside its assigned worktree.",
        trigger_condition="A contract declares repo: in writable_paths.",
        caller_or_dataflow_evidence="load_registry validates writable scopes.",
        severity_rationale="Breaks the isolation guarantee the milestone claims.",
    )


def test_an_unresolved_critical_finding_blocks_the_gate(engine, mission):
    artifact = _findings(
        engine,
        mission,
        claims=[
            Claim(
                claim_id="c1", statement="ok", kind="fact", evidence_ref="tests/"
            ),
            _critical_claim(),
        ],
    )
    decision = engine.evaluate(
        mission.dev_mission_id,
        Gate.RESEARCH_COMPLETENESS,
        approver="architecture",
        subject_author="research",
        evidence_artifact_ids=[artifact.artifact_id],
    )
    assert any(r.startswith("unresolved_critical_findings") for r in decision.refusals)


def test_a_critical_finding_on_an_accepted_artifact_is_resolved(engine, mission):
    artifact = _findings(
        engine, mission,
        claims=[
            Claim(claim_id="c1", statement="ok", kind="fact", evidence_ref="tests/"),
            _critical_claim(),
        ],
    )
    for status in (
        ArtifactStatus.SUBMITTED, ArtifactStatus.UNDER_REVIEW, ArtifactStatus.ACCEPTED
    ):
        engine.artifacts.set_status(mission.dev_mission_id, artifact.artifact_id, status)
    reloaded = engine.artifacts.get(mission.dev_mission_id, artifact.artifact_id)
    assert unresolved_critical_findings([reloaded]) == []


def test_an_open_veto_blocks_every_gate_except_security_approval(engine, mission):
    artifact = _findings(engine, mission)
    engine.missions.open_veto(
        mission.dev_mission_id, "veto-1", actor="security-governance"
    )
    decision = engine.evaluate(
        mission.dev_mission_id,
        Gate.RESEARCH_COMPLETENESS,
        approver="architecture",
        subject_author="research",
        evidence_artifact_ids=[artifact.artifact_id],
    )
    assert any(r.startswith("security_veto_open") for r in decision.refusals)


# --------------------------------------------------------------------------
# Testing gates
# --------------------------------------------------------------------------


def _verification(engine, mission, **payload_overrides):
    payload = {
        "results": [{"command": "pytest -q tests/x.py", "outcome": "pass"}],
        "not_run": [],
    }
    payload.update(payload_overrides)
    artifact = make_artifact(
        mission_id=mission.dev_mission_id,
        kind=ArtifactKind.VERIFICATION_REPORT,
        authoring_agent="testing-verification",
        repository_sha=SHA,
        title="Verification",
        required_next_action="review",
        worktree="/tmp/wt",
        branch="agent/backend-engineering/dm001-x",
        payload=payload,
    )
    engine.artifacts.put(artifact)
    return artifact


def test_negative_path_gate_requires_negative_path_results(engine, mission):
    artifact = _verification(engine, mission)
    decision = engine.evaluate(
        mission.dev_mission_id,
        Gate.NEGATIVE_PATH_TESTING,
        approver="code-review",
        subject_author="testing-verification",
        evidence_artifact_ids=[artifact.artifact_id],
    )
    assert "no_negative_path_results" in decision.refusals


def test_negative_path_gate_passes_with_recorded_refusals(engine, mission):
    artifact = _verification(
        engine,
        mission,
        negative_paths=[
            {"scenario": "self approval", "expected": "refused", "actual": "refused"}
        ],
    )
    _, decision = engine.pass_gate(
        mission.dev_mission_id,
        Gate.NEGATIVE_PATH_TESTING,
        approver="code-review",
        subject_author="testing-verification",
        evidence_artifact_ids=[artifact.artifact_id],
    )
    assert decision.allowed


def test_unresolved_disagreements_warn_at_executive_synthesis(engine, mission):
    decision_artifact = make_artifact(
        mission_id=mission.dev_mission_id,
        kind=ArtifactKind.EXECUTIVE_DECISION,
        authoring_agent="ceo",
        repository_sha=SHA,
        title="Decision",
        required_next_action="owner review",
        payload={
            "verdict": TerminalVerdict.APPROVED_WITH_LIMITATIONS.value,
            "unresolved_risks": ["scope"],
        },
    )
    engine.artifacts.put(decision_artifact)
    mission.unresolved_disagreements = ["chal_1"]
    engine.missions.put(mission)
    decision = engine.evaluate(
        mission.dev_mission_id,
        Gate.EXECUTIVE_SYNTHESIS,
        approver="program-manager",
        subject_author="ceo",
        evidence_artifact_ids=[decision_artifact.artifact_id],
    )
    assert decision.allowed
    assert any(
        w.startswith("unresolved_disagreements_carried_into_decision")
        for w in decision.warnings
    )


def test_report_lists_every_gate(engine, mission):
    report = engine.report(mission.dev_mission_id)
    assert len(report["gates"]) == len(Gate)
    assert all(row["status"] == "pending" for row in report["gates"])


def test_an_unknown_gate_is_refused(engine, mission):
    with pytest.raises(GateError) as exc:
        engine.evaluate(
            mission.dev_mission_id,
            "vibes",
            approver="architecture",
            subject_author="research",
            evidence_artifact_ids=[],
        )
    assert exc.value.code == "unknown_gate"


def test_the_review_standard_is_published_as_data():
    requirements = review_finding_requirements()
    assert "concrete, relevant failure mode" in requirements["principle"]
    for key in (
        "source_location", "failure_mode", "trigger_condition",
        "caller_or_dataflow_evidence", "severity_rationale",
    ):
        assert key in requirements


# --------------------------------------------------------------------------
# Configuration protection
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "~/.claude",
        "~/.claude/settings.json",
        "~/.claude/hooks/hooks.json",
        "~/.claude/skills/x/SKILL.md",
        "~/.config/opencode/config.json",
        "~/.opencode/plugins/x.js",
        "~/.codex/config.toml",
        "~/.cursor/rules/x.md",
        "~/.zshrc",
        "~/.bashrc",
        "~/.zprofile",
        "~/.profile",
        "~/.netrc",
        "~/.npmrc",
        "~/.ssh/id_ed25519",
        "~/.aws/credentials",
        "~/.gnupg/secring.gpg",
        "~/.mcp.json",
        "~/.saathi/evidence.db",
    ],
)
def test_the_protected_surface_is_refused(path):
    verdict = classify_path(path)
    assert verdict.protected, path
    assert verdict.category
    with pytest.raises(ConfigProtectionError) as exc:
        assert_write_allowed(path, actor="backend-engineering")
    assert exc.value.code == "protected_configuration_path"


@pytest.mark.parametrize(
    "path",
    [
        "saathi/agentdev/roles.py",
        "docs/ai-development/overview.md",
        "tests/test_m349_agentdev_gates_and_config_protection.py",
    ],
)
def test_ordinary_repository_paths_are_not_protected(path):
    assert not is_protected(path)
    assert_write_allowed(path)


def test_a_repository_local_settings_file_is_not_protected(tmp_path):
    local = tmp_path / "project" / ".claude" / "settings.json"
    local.parent.mkdir(parents=True)
    local.write_text("{}", encoding="utf-8")
    assert not is_protected(local)


def test_the_home_spelling_cannot_be_used_to_evade_the_check():
    home = os.path.expanduser("~")
    for spelling in ("~/.claude/settings.json", f"{home}/.claude/settings.json",
                     "$HOME/.claude/settings.json"):
        assert is_protected(spelling), spelling


def test_credential_markers_are_caught_anywhere():
    assert is_protected("/var/tmp/some_api_key.txt")
    assert is_protected("/opt/service/secrets/db.json")


def test_a_proposal_needs_every_required_field():
    proposal = ConfigChangeProposal(
        path="~/.claude/settings.json", proposed_by="backend-engineering"
    )
    refusals = validate_proposal(proposal)
    for field_name in ("inventory", "backup_plan", "change_diff", "rollback_plan"):
        assert f"missing_{field_name}" in refusals
    assert "missing_rationale" in refusals
    assert "owner_approval_required" in refusals


def test_an_agent_cannot_grant_the_owner_approval():
    proposal = ConfigChangeProposal(
        path="~/.claude/settings.json",
        proposed_by="backend-engineering",
        rationale="Enable a hook.",
        inventory=["~/.claude/settings.json"],
        backup_plan="Copy to settings.json.bak",
        change_diff="+ hooks",
        rollback_plan="Restore the backup",
        owner_approved=True,
        owner_approval_actor="ceo",
    )
    refusals = validate_proposal(proposal)
    assert "owner_approval_not_by_owner:ceo" in refusals
    with pytest.raises(ConfigProtectionError) as exc:
        assert_change_allowed(proposal)
    assert exc.value.code == "config_change_refused"


def test_a_complete_owner_approved_proposal_is_allowed():
    proposal = ConfigChangeProposal(
        path="~/.claude/settings.json",
        proposed_by="backend-engineering",
        rationale="Enable a hook the owner asked for.",
        inventory=["~/.claude/settings.json"],
        backup_plan="Copy to settings.json.bak first",
        change_diff="+ \"hooks\": {...}",
        rollback_plan="cp settings.json.bak settings.json",
        owner_approved=True,
        owner_approval_actor="owner",
    )
    assert validate_proposal(proposal) == []
    assert_change_allowed(proposal)


def test_an_unprotected_path_needs_no_proposal():
    proposal = ConfigChangeProposal(path="docs/x.md", proposed_by="documentation")
    assert validate_proposal(proposal) == ["path_not_protected:no_proposal_required"]


def test_the_protected_surface_is_published_as_data():
    surface = protected_surface()
    prefixes = {row["path"] for row in surface["home_prefixes"]}
    assert "~/.claude" in prefixes
    assert "~/.config/opencode" in prefixes
    names = {row["name"] for row in surface["basenames"]}
    assert ".zshrc" in names
    assert "hooks.json" in names
    assert len(surface["home_prefixes"]) == len(PROTECTED_HOME_PREFIXES)
    assert len(surface["basenames"]) == len(PROTECTED_BASENAMES)
