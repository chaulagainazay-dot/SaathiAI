"""M358 — the owner review and evidence console.

Three obligations.

*The packet shows everything.* Mission, agent outputs, review comments,
approval history, artifact lineage, tests, behaviour evaluation, resource
usage, limitations, confidence signals and remaining risks.

*Only the owner decides, and every decision is immutable.* The ledger is
append-only and hash-chained, so the tampering tests here are the point of the
milestone: editing, reordering or deleting any earlier decision must be
detected and located.

*Nothing outside the four actions exists.* No merge, push, deploy, release,
publish or rollout verb is present, and none can be reached.
"""
from __future__ import annotations

import json

import pytest

from saathi.agentdev import review_console as review_module
from saathi.agentdev.artifacts import ArtifactKind, ArtifactStore
from saathi.agentdev.missions import DevMissionStore, Gate
from saathi.agentdev.review_console import (
    ABSENT_VERBS,
    ACTION_EFFECT,
    OwnerAction,
    OwnerDecision,
    OwnerDecisionLedger,
    ReviewError,
    build_review_packet,
    record_owner_action,
    render_review_html,
)
from saathi.agentdev.runner import run_reference_mission
from saathi.agentdev.settings import load_settings

MISSION = "dmrunner01"


@pytest.fixture()
def reviewed(tmp_path):
    """A completed reference mission, ready for the owner."""
    store = tmp_path / "store"
    store.mkdir()
    run_reference_mission(store)
    return load_settings(store_dir=str(store))


def _approve(settings, **kw):
    payload = {
        "actor": "owner",
        "rationale": "The governance path holds and the risks are acceptable.",
    }
    payload.update(kw)
    return record_owner_action(settings, MISSION, OwnerAction.APPROVE, **payload)


# --------------------------------------------------------------------------
# The packet
# --------------------------------------------------------------------------


def test_the_packet_contains_every_required_section(reviewed):
    packet = build_review_packet(MISSION, reviewed)
    for section in (
        "mission", "agent_outputs", "review_comments", "approval_history",
        "artifact_lineage", "tests", "behaviour_evaluation", "resource_usage",
        "limitations", "confidence_signals", "remaining_risks",
    ):
        assert section in packet, section


def test_the_packet_is_json_serialisable(reviewed):
    json.dumps(build_review_packet(MISSION, reviewed), default=str)


def test_agent_outputs_cover_every_artifact(reviewed):
    packet = build_review_packet(MISSION, reviewed)
    stored = ArtifactStore(reviewed.store_path()).list(MISSION)
    assert len(packet["agent_outputs"]) == len(stored)


def test_lineage_edges_are_present(reviewed):
    assert build_review_packet(MISSION, reviewed)["artifact_lineage"]


def test_tests_section_carries_the_not_run_list(reviewed):
    tests = build_review_packet(MISSION, reviewed)["tests"]
    assert tests
    assert tests[0]["not_run"]


def test_confidence_is_reported_as_signals_not_a_score(reviewed):
    signals = build_review_packet(MISSION, reviewed)["confidence_signals"]
    assert "No scalar confidence score is computed" in signals["note"]
    assert "score" not in {k for k in signals if k != "note"}
    assert signals["gates_total"] == len(Gate)
    assert signals["self_approved_gates"] == 0


def test_remaining_risks_carry_the_decision_s_own_unresolved_list(reviewed):
    risks = build_review_packet(MISSION, reviewed)["remaining_risks"]
    assert risks["carried_into_decision"]


def test_the_packet_declares_it_cannot_merge_or_deploy(reviewed):
    capabilities = build_review_packet(MISSION, reviewed)["capabilities"]
    assert capabilities["merges"] is False
    assert capabilities["deploys"] is False
    assert capabilities["pushes"] is False
    assert capabilities["contacts_provider"] is False


def test_the_four_owner_actions_are_published_with_their_effects(reviewed):
    actions = build_review_packet(MISSION, reviewed)["owner_actions"]
    assert {a["action"] for a in actions} == {a.value for a in OwnerAction}
    for action in actions:
        assert action["effect"] == ACTION_EFFECT[OwnerAction(action["action"])]


def test_an_unknown_mission_is_refused(reviewed):
    from saathi.agentdev.missions import MissionError

    with pytest.raises(MissionError):
        build_review_packet("dmnothere1", reviewed)


# --------------------------------------------------------------------------
# Only the owner decides
# --------------------------------------------------------------------------


@pytest.mark.parametrize("actor", ["ceo", "program-manager", "security-governance", ""])
def test_an_action_by_anyone_but_the_owner_is_refused(reviewed, actor):
    with pytest.raises(ReviewError) as exc:
        record_owner_action(
            reviewed, MISSION, OwnerAction.APPROVE, actor=actor, rationale="x",
        )
    assert exc.value.code == "action_not_by_owner"


def test_an_action_without_a_rationale_is_refused(reviewed):
    with pytest.raises(ReviewError) as exc:
        record_owner_action(
            reviewed, MISSION, OwnerAction.REJECT, actor="owner", rationale="   ",
        )
    assert exc.value.code == "action_without_rationale"


def test_an_unknown_action_is_refused(reviewed):
    with pytest.raises(ReviewError) as exc:
        record_owner_action(reviewed, MISSION, "ship_it", actor="owner", rationale="x")
    assert exc.value.code == "unknown_action"


def test_citing_an_artifact_that_does_not_exist_is_refused(reviewed):
    with pytest.raises(ReviewError) as exc:
        _approve(reviewed, reviewed_artifact_ids=["nope_00"])
    assert exc.value.code == "reviewed_artifact_not_found"


def test_approval_requires_acknowledging_every_remaining_risk(reviewed):
    missions = DevMissionStore(reviewed.store_path())
    mission = missions.require(MISSION)
    mission.unresolved_disagreements = ["chal_open_1"]
    missions.put(mission)
    with pytest.raises(ReviewError) as exc:
        _approve(reviewed)
    assert exc.value.code == "unacknowledged_remaining_risks"
    result = _approve(reviewed, acknowledged_risks=["chal_open_1"])
    assert result["recorded"]["remaining_risks_acknowledged"] == ["chal_open_1"]


def test_approval_over_an_open_veto_is_refused(reviewed):
    DevMissionStore(reviewed.store_path()).open_veto(
        MISSION, "veto-1", actor="security-governance"
    )
    with pytest.raises(ReviewError) as exc:
        _approve(reviewed, acknowledged_risks=["veto-1"])
    assert exc.value.code == "approval_with_open_veto"


def test_a_dry_run_records_nothing(reviewed):
    result = record_owner_action(
        reviewed, MISSION, OwnerAction.APPROVE, actor="owner",
        rationale="thinking about it", dry_run=True,
    )
    assert result["dry_run"] is True
    assert OwnerDecisionLedger(reviewed.store_path(), MISSION).entries() == []


# --------------------------------------------------------------------------
# What each action does to the mission
# --------------------------------------------------------------------------


def test_approve_records_an_owner_authored_artifact_and_passes_the_owner_gate(reviewed):
    result = _approve(reviewed)
    assert result["gate"]["status"] == "passed"
    artifacts = ArtifactStore(reviewed.store_path()).list(
        MISSION, kind=ArtifactKind.OWNER_APPROVAL
    )
    assert len(artifacts) == 1
    assert artifacts[0].authoring_agent == "owner"
    mission = DevMissionStore(reviewed.store_path()).require(MISSION)
    assert mission.gate(Gate.OWNER_APPROVAL).passed


def test_reject_records_a_failed_owner_gate(reviewed):
    result = record_owner_action(
        reviewed, MISSION, OwnerAction.REJECT, actor="owner",
        rationale="The verification report omits the negative paths I care about.",
    )
    assert result["gate"]["status"] == "failed"
    mission = DevMissionStore(reviewed.store_path()).require(MISSION)
    assert mission.gate(Gate.OWNER_APPROVAL).status == "failed"
    assert not mission.gate(Gate.OWNER_APPROVAL).passed


@pytest.mark.parametrize(
    "action", [OwnerAction.REQUEST_CHANGES, OwnerAction.NEEDS_RESEARCH]
)
def test_the_soft_actions_change_no_gate_but_are_recorded(reviewed, action):
    result = record_owner_action(
        reviewed, MISSION, action, actor="owner",
        rationale="I need the missing evidence before I can decide.",
    )
    assert result["gate"]["changed"] is False
    mission = DevMissionStore(reviewed.store_path()).require(MISSION)
    assert mission.gate(Gate.OWNER_APPROVAL).status == "pending"
    assert OwnerDecisionLedger(reviewed.store_path(), MISSION).entries()[0].action == (
        action.value
    )


def test_no_action_moves_the_mission_state(reviewed):
    """The reference mission is already closed; approving must not move it at all."""
    missions = DevMissionStore(reviewed.store_path())
    before = missions.require(MISSION).state
    _approve(reviewed)
    record_owner_action(reviewed, MISSION, OwnerAction.REQUEST_CHANGES,
                        actor="owner", rationale="one more thought")
    assert missions.require(MISSION).state == before


# --------------------------------------------------------------------------
# Immutability
# --------------------------------------------------------------------------


def test_the_ledger_has_no_update_or_delete_method():
    for verb in ("update", "delete", "remove", "edit", "rewrite", "truncate"):
        assert not hasattr(OwnerDecisionLedger, verb), verb


def test_each_entry_links_to_the_one_before_it(reviewed):
    record_owner_action(reviewed, MISSION, OwnerAction.NEEDS_RESEARCH,
                        actor="owner", rationale="first look")
    record_owner_action(reviewed, MISSION, OwnerAction.REQUEST_CHANGES,
                        actor="owner", rationale="second look")
    _approve(reviewed)
    ledger = OwnerDecisionLedger(reviewed.store_path(), MISSION)
    entries = ledger.entries()
    assert [e.seq for e in entries] == [1, 2, 3]
    assert entries[0].prev_hash == ""
    assert entries[1].prev_hash == entries[0].entry_hash
    assert entries[2].prev_hash == entries[1].entry_hash
    assert ledger.verify_chain()["intact"] is True


def test_editing_an_earlier_decision_breaks_the_chain(reviewed):
    record_owner_action(reviewed, MISSION, OwnerAction.NEEDS_RESEARCH,
                        actor="owner", rationale="original reason")
    _approve(reviewed)
    ledger = OwnerDecisionLedger(reviewed.store_path(), MISSION)
    assert ledger.verify_chain()["intact"] is True

    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["rationale"] = "a reason the owner never gave"
    lines[0] = json.dumps(tampered, sort_keys=True, default=str)
    ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    verdict = ledger.verify_chain()
    assert verdict["intact"] is False
    assert verdict["broken_at"] == 1
    assert "does not match its hash" in verdict["reason"]


def test_deleting_a_decision_breaks_the_chain(reviewed):
    record_owner_action(reviewed, MISSION, OwnerAction.NEEDS_RESEARCH,
                        actor="owner", rationale="first")
    record_owner_action(reviewed, MISSION, OwnerAction.REQUEST_CHANGES,
                        actor="owner", rationale="second")
    ledger = OwnerDecisionLedger(reviewed.store_path(), MISSION)
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    ledger.path.write_text(lines[1] + "\n", encoding="utf-8")
    verdict = ledger.verify_chain()
    assert verdict["intact"] is False
    assert verdict["broken_at"] == 1


def test_reordering_decisions_breaks_the_chain(reviewed):
    record_owner_action(reviewed, MISSION, OwnerAction.NEEDS_RESEARCH,
                        actor="owner", rationale="first")
    record_owner_action(reviewed, MISSION, OwnerAction.REQUEST_CHANGES,
                        actor="owner", rationale="second")
    ledger = OwnerDecisionLedger(reviewed.store_path(), MISSION)
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    ledger.path.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")
    assert ledger.verify_chain()["intact"] is False


def test_appending_a_forged_decision_breaks_the_chain(reviewed):
    _approve(reviewed)
    ledger = OwnerDecisionLedger(reviewed.store_path(), MISSION)
    forged = OwnerDecision(
        seq=2, at=0.0, action="approve", dev_mission_id=MISSION, actor="owner",
        rationale="forged", prev_hash="deadbeef", entry_hash="deadbeef",
    )
    with open(ledger.path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(forged.to_dict(), sort_keys=True) + "\n")
    verdict = ledger.verify_chain()
    assert verdict["intact"] is False
    assert verdict["broken_at"] == 2


def test_a_corrupt_ledger_line_is_reported_not_ignored(reviewed):
    _approve(reviewed)
    ledger = OwnerDecisionLedger(reviewed.store_path(), MISSION)
    with open(ledger.path, "a", encoding="utf-8") as handle:
        handle.write("{not json at all\n")
    with pytest.raises(ReviewError) as exc:
        ledger.entries()
    assert exc.value.code == "ledger_corrupt"


def test_an_empty_ledger_verifies_as_intact(reviewed):
    verdict = OwnerDecisionLedger(reviewed.store_path(), MISSION).verify_chain()
    assert verdict == {
        "intact": True, "entries": 0, "head": None,
        "note": verdict["note"],
    }


# --------------------------------------------------------------------------
# Absent verbs
# --------------------------------------------------------------------------


@pytest.mark.parametrize("verb", ABSENT_VERBS)
def test_the_module_defines_no_merge_push_or_deploy_verb(verb):
    assert not any(
        name.startswith(verb) for name in dir(review_module) if not name.startswith("_")
    )


def test_the_four_actions_are_the_only_actions():
    assert {a.value for a in OwnerAction} == {
        "approve", "reject", "request_changes", "needs_research"
    }


def test_the_module_contacts_no_provider():
    import ast
    from pathlib import Path

    tree = ast.parse(Path(review_module.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint({"urllib", "socket", "subprocess", "http", "requests"})


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def test_the_page_is_self_contained(reviewed):
    page = render_review_html(build_review_packet(MISSION, reviewed))
    for external in ("<script", "src=", "href=", "@import", "http://", "https://"):
        assert external not in page, external


def test_the_page_says_it_cannot_act(reviewed):
    page = render_review_html(build_review_packet(MISSION, reviewed))
    assert "This page displays. It does not act." in page
    assert "no merge, push, deploy or provider control" in page


def test_the_page_shows_the_command_for_every_action(reviewed):
    page = render_review_html(build_review_packet(MISSION, reviewed))
    for action in ("approve", "reject", "request-changes", "needs-research"):
        assert f"review {action} {MISSION}" in page


def test_the_page_reports_a_broken_chain_prominently(reviewed):
    _approve(reviewed)
    ledger = OwnerDecisionLedger(reviewed.store_path(), MISSION)
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["rationale"] = "tampered"
    ledger.path.write_text(json.dumps(tampered, sort_keys=True) + "\n", encoding="utf-8")
    page = render_review_html(build_review_packet(MISSION, reviewed))
    assert "BROKEN at entry 1" in page


def test_the_page_escapes_hostile_content(reviewed):
    missions = DevMissionStore(reviewed.store_path())
    mission = missions.require(MISSION)
    mission.title = "<script>alert(1)</script>"
    missions.put(mission)
    page = render_review_html(build_review_packet(MISSION, reviewed))
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_cli_review_packet_emits_json(reviewed, capsys):
    from saathi.agentdev.cli import main

    assert main(["--store", str(reviewed.store_path()), "review", "packet", MISSION]) == 0
    assert json.loads(capsys.readouterr().out)["console"]


def test_cli_review_approve_records_a_decision(reviewed, capsys):
    from saathi.agentdev.cli import main

    code = main([
        "--store", str(reviewed.store_path()), "review", "approve", MISSION,
        "--actor", "owner", "--rationale", "Acceptable.",
    ])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["recorded"]["action"] == "approve"


def test_cli_review_refuses_a_non_owner_actor(reviewed, capsys):
    from saathi.agentdev.cli import EXIT_REFUSED, main

    code = main([
        "--store", str(reviewed.store_path()), "review", "approve", MISSION,
        "--actor", "ceo", "--rationale", "Looks fine to me.",
    ])
    assert code == EXIT_REFUSED
    assert json.loads(capsys.readouterr().out)["error"] == "action_not_by_owner"


def test_cli_review_ledger_exits_nonzero_on_a_broken_chain(reviewed, capsys):
    from saathi.agentdev.cli import EXIT_FAIL, main

    _approve(reviewed)
    ledger = OwnerDecisionLedger(reviewed.store_path(), MISSION)
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["actor"] = "not-the-owner"
    ledger.path.write_text(json.dumps(tampered, sort_keys=True) + "\n", encoding="utf-8")
    code = main(["--store", str(reviewed.store_path()), "review", "ledger", MISSION])
    assert code == EXIT_FAIL
    assert json.loads(capsys.readouterr().out)["chain"]["intact"] is False


def test_cli_review_render_refuses_a_protected_output_path(reviewed, capsys):
    from saathi.agentdev.cli import EXIT_REFUSED, main

    code = main([
        "--store", str(reviewed.store_path()), "review", "render", MISSION,
        "--output", "~/.claude/settings.json",
    ])
    assert code == EXIT_REFUSED
    assert json.loads(capsys.readouterr().out)["error"] == "output_path_protected"


def test_cli_review_standard_still_works(capsys):
    from saathi.agentdev.cli import main

    assert main(["review", "standard"]) == 0
    assert "principle" in json.loads(capsys.readouterr().out)
