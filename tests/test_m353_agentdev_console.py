"""M353 — the read-only Agent Operations Console.

Three obligations. The console must show all fifteen panels. It must stay
read-only — asserted structurally (no write verb exists in the module) and
behaviourally (running it over a populated store leaves every byte unchanged).
And it must degrade honestly when a source is unavailable rather than crashing
or, worse, reporting a comfortable default.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from saathi.agentdev import console as console_module
from saathi.agentdev.artifacts import ArtifactKind, ArtifactStore, Claim, make_artifact
from saathi.agentdev.console import (
    CONSOLE_VERSION,
    collect_console_state,
    panel_agent_hierarchy,
    panel_approvals,
    panel_blocked_missions,
    panel_branches,
    panel_certification,
    panel_disagreements,
    panel_integration_candidates,
    panel_lifecycle,
    panel_missions,
    panel_repository,
    panel_review_queue,
    render_html,
    render_text,
)
from saathi.agentdev.missions import DevMissionStore, Gate, GateRecord, MissionState
from saathi.agentdev.settings import load_settings

SHA = "53b9b20736d5acf4a7ca3a9bd25b68d01e666a5d"

REQUIRED_PANELS = (
    "operator_notices",
    "missions",
    "blocked_missions",
    "mission_lifecycle",
    "agent_hierarchy",
    "review_queue",
    "approvals",
    "disagreements",
    "evidence",
    "worktrees",
    "certification",
    "repository",
    "branches",
    "integration_candidates",
    "resources",
)


@pytest.fixture()
def populated(tmp_path):
    """A store with one simulated mission in it."""
    from saathi.agentdev.simulation import run_offline_mission

    store = tmp_path / "store"
    store.mkdir()
    run_offline_mission(store_dir=str(store))
    return load_settings(store_dir=str(store))


@pytest.fixture()
def empty(tmp_path):
    store = tmp_path / "empty"
    store.mkdir()
    return load_settings(store_dir=str(store))


def _fingerprint(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# --------------------------------------------------------------------------
# Completeness
# --------------------------------------------------------------------------


def test_every_required_panel_is_present(populated):
    state = collect_console_state(populated)
    assert set(REQUIRED_PANELS) <= set(state["panels"])
    assert state["console"] == CONSOLE_VERSION


def test_the_console_reports_the_simulated_mission(populated):
    panels = collect_console_state(populated)["panels"]
    assert panels["missions"]["total"] == 1
    assert panels["evidence"]["total"] > 0
    assert panels["approvals"]["count"] > 0
    assert panels["disagreements"]["challenges"] > 0


def test_state_is_json_serialisable(populated):
    json.dumps(collect_console_state(populated), default=str)


def test_console_declares_it_holds_no_write_capability(populated):
    capabilities = collect_console_state(populated)["capabilities"]
    assert capabilities == {
        "writes": False,
        "approves": False,
        "executes_missions": False,
        "contacts_provider": False,
        "polls": False,
    }


def test_console_publishes_that_it_is_a_snapshot_not_a_live_view(populated):
    assert "snapshot" in collect_console_state(populated)["limitation"].lower()


# --------------------------------------------------------------------------
# Read-only — structural
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "verb",
    ["approve", "advance", "create", "remove", "prune", "merge", "push", "deploy", "run_mission"],
)
def test_the_console_module_exposes_no_write_verb(verb):
    assert not hasattr(console_module, verb)
    assert not any(
        name.startswith(verb) for name in dir(console_module) if not name.startswith("_")
    )


def test_the_console_source_calls_no_store_write_method():
    source = Path(console_module.__file__).read_text(encoding="utf-8")
    for forbidden in (".put(", ".advance(", ".record_gate(", ".set_status(",
                      ".open_veto(", ".set_terminal_verdict(", "os.replace"):
        assert forbidden not in source, forbidden


def test_the_console_source_writes_no_file():
    source = Path(console_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("write_text", "write_bytes", "open(", "mkdir"):
        assert forbidden not in source, forbidden


# --------------------------------------------------------------------------
# Read-only — behavioural
# --------------------------------------------------------------------------


def test_collecting_state_changes_no_byte_of_the_store(populated):
    root = populated.store_path()
    before = _fingerprint(root)
    collect_console_state(populated)
    collect_console_state(populated)
    assert _fingerprint(root) == before


def test_rendering_changes_no_byte_of_the_store(populated):
    root = populated.store_path()
    state = collect_console_state(populated)
    before = _fingerprint(root)
    render_html(state)
    render_text(state)
    assert _fingerprint(root) == before


def test_collecting_state_creates_no_store_for_an_absent_one(tmp_path):
    missing = tmp_path / "never-created"
    collect_console_state(load_settings(store_dir=str(missing)))
    assert not missing.exists()


# --------------------------------------------------------------------------
# Panels in isolation
# --------------------------------------------------------------------------


def test_missions_panel_separates_active_from_all(tmp_path):
    store = DevMissionStore(tmp_path)
    live = store.create(title="live", objective="o", starting_sha=SHA, dev_mission_id="dmlive1")
    store.advance("dmlive1", MissionState.DECOMPOSED, actor="program-manager")
    store.create(title="done", objective="o", starting_sha=SHA, dev_mission_id="dmdone1")
    panel = panel_missions(store.list())
    assert panel["total"] == 2
    assert panel["active"] == 2
    assert {r["dev_mission_id"] for r in panel["all_rows"]} == {"dmlive1", "dmdone1"}
    assert live.dev_mission_id in {r["dev_mission_id"] for r in panel["rows"]}


def test_blocked_panel_reports_the_reason(tmp_path):
    store = DevMissionStore(tmp_path)
    store.create(title="t", objective="o", starting_sha=SHA, dev_mission_id="dmblk1")
    store.open_veto("dmblk1", "veto-1", actor="security-governance")
    rows = panel_blocked_missions(store.list())["rows"]
    assert rows and "security_veto_open" in rows[0]["blocked_because"]


def test_blocked_panel_is_empty_for_a_healthy_mission(tmp_path):
    store = DevMissionStore(tmp_path)
    store.create(title="t", objective="o", starting_sha=SHA, dev_mission_id="dmok1")
    assert panel_blocked_missions(store.list())["count"] == 0


def test_lifecycle_panel_lists_every_state_and_gate(tmp_path):
    panel = panel_lifecycle([])
    assert len(panel["states"]) == len(MissionState)
    assert len(panel["gate_catalogue"]) == len(Gate)
    owner_only = [g for g in panel["gate_catalogue"] if g["owner_only"]]
    assert [g["gate"] for g in owner_only] == ["owner_approval"]


def test_hierarchy_panel_roots_at_the_owner():
    panel = panel_agent_hierarchy()
    assert panel["status"] == "ok"
    assert panel["tree"]["agent_id"] == "owner"
    assert panel["count"] == len(panel["roles"])
    # Every declared role appears exactly once somewhere in the tree.
    seen: list[str] = []

    def walk(node):
        seen.append(node["agent_id"])
        for child in node["reports"]:
            walk(child)

    walk(panel["tree"])
    assert sorted(seen[1:]) == sorted(r["agent_id"] for r in panel["roles"])


def test_approvals_panel_flags_a_self_approval(tmp_path):
    store = DevMissionStore(tmp_path)
    store.create(title="t", objective="o", starting_sha=SHA, dev_mission_id="dmself1")
    # Written directly to the store: the gate engine would refuse this, and the
    # console's job is to make it visible if it ever reached disk anyway.
    store.record_gate("dmself1", GateRecord(
        gate=Gate.RESEARCH_COMPLETENESS.value, status="passed",
        approver="research", subject_author="research",
    ))
    panel = panel_approvals(store.list())
    assert panel["self_approved"] == 1
    assert panel["rows"][0]["self_approved"] is True


def test_review_queue_lists_submitted_artifacts_oldest_first(tmp_path):
    missions = DevMissionStore(tmp_path)
    artifacts = ArtifactStore(tmp_path)
    missions.create(title="t", objective="o", starting_sha=SHA, dev_mission_id="dmq1")
    for index in (1, 2):
        artifact = make_artifact(
            mission_id="dmq1",
            kind=ArtifactKind.RESEARCH_FINDINGS,
            authoring_agent="research",
            repository_sha=SHA,
            title=f"findings {index}",
            required_next_action="review",
            status="submitted",
            claims=[Claim(claim_id="c1", statement="x", kind="fact", evidence_ref="tests/")],
            payload={"not_investigated": []},
        )
        artifacts.put(artifact)
    panel = panel_review_queue(artifacts, missions.list())
    assert panel["count"] == 2
    assert panel["rows"][0]["waiting_since"] <= panel["rows"][1]["waiting_since"]


def test_review_queue_ignores_accepted_artifacts(populated):
    artifacts = ArtifactStore(populated.store_path())
    missions = DevMissionStore(populated.store_path()).list()
    for row in panel_review_queue(artifacts, missions)["rows"]:
        assert row["status"] != "accepted"


def test_disagreements_panel_marks_the_unanswered_challenge(populated):
    artifacts = ArtifactStore(populated.store_path())
    missions = DevMissionStore(populated.store_path()).list()
    panel = panel_disagreements(artifacts, missions)
    assert panel["unanswered"] >= 1
    assert panel["recorded_unresolved"]


def test_integration_candidates_carry_their_open_risks(populated):
    artifacts = ArtifactStore(populated.store_path())
    missions = DevMissionStore(populated.store_path()).list()
    panel = panel_integration_candidates(artifacts, missions)
    assert panel["count"] == 1
    assert panel["rows"][0]["terminal_verdict"] == "APPROVED_WITH_LIMITATIONS"
    assert panel["rows"][0]["carried_risks"]


def test_integration_candidates_exclude_a_rejected_mission(tmp_path):
    missions = DevMissionStore(tmp_path)
    artifacts = ArtifactStore(tmp_path)
    mission = missions.create(
        title="t", objective="o", starting_sha=SHA, dev_mission_id="dmrej1"
    )
    mission.terminal_verdict = "REJECTED"
    missions.put(mission)
    assert panel_integration_candidates(artifacts, missions.list())["count"] == 0


def test_certification_panel_parses_the_verdict_token(tmp_path):
    evidence = tmp_path / "docs" / "evidence" / "m999"
    evidence.mkdir(parents=True)
    (evidence / "CERTIFICATION.md").write_text(
        "# X\n\n**Verdict:** `SOMETHING_CERTIFIED_WITH_LIMITATIONS`\n",
        encoding="utf-8",
    )
    panel = panel_certification(tmp_path)
    assert panel["rows"] == [{
        "milestone": "m999",
        "verdict": "SOMETHING_CERTIFIED_WITH_LIMITATIONS",
        "path": "docs/evidence/m999/CERTIFICATION.md",
        "has_machine_readable": False,
    }]


def test_certification_panel_reports_a_missing_verdict_as_none(tmp_path):
    evidence = tmp_path / "docs" / "evidence" / "m998"
    evidence.mkdir(parents=True)
    (evidence / "CERTIFICATION.md").write_text("# no verdict here\n", encoding="utf-8")
    assert panel_certification(tmp_path)["rows"][0]["verdict"] is None


def test_certification_panel_is_empty_without_an_evidence_tree(tmp_path):
    assert panel_certification(tmp_path)["count"] == 0


# --------------------------------------------------------------------------
# Honest degradation
# --------------------------------------------------------------------------


def test_repository_panel_reports_unavailable_outside_a_repository(tmp_path):
    panel = panel_repository(tmp_path)
    assert panel["status"] == "unavailable"


def test_branches_panel_reports_unavailable_outside_a_repository(tmp_path):
    assert panel_branches(tmp_path)["status"] == "unavailable"


def test_console_survives_an_empty_store(empty):
    state = collect_console_state(empty)
    assert state["panels"]["missions"]["total"] == 0
    assert state["panels"]["review_queue"]["count"] == 0
    render_html(state)
    render_text(state)


def test_notices_flag_an_open_veto_as_a_blocker(tmp_path):
    settings = load_settings(store_dir=str(tmp_path))
    store = DevMissionStore(tmp_path)
    store.create(title="t", objective="o", starting_sha=SHA, dev_mission_id="dmveto1")
    store.open_veto("dmveto1", "veto-1", actor="security-governance")
    notices = collect_console_state(settings)["panels"]["operator_notices"]
    assert notices["blockers"] >= 1
    assert any(n["code"] == "security_veto_open" for n in notices["rows"])


def test_notices_are_ordered_blockers_first(tmp_path):
    settings = load_settings(store_dir=str(tmp_path))
    store = DevMissionStore(tmp_path)
    store.create(title="t", objective="o", starting_sha=SHA, dev_mission_id="dmord1")
    store.open_veto("dmord1", "veto-1", actor="security-governance")
    rows = collect_console_state(settings)["panels"]["operator_notices"]["rows"]
    levels = [r["level"] for r in rows]
    assert levels == sorted(levels, key=lambda l: {"blocker": 0, "warning": 1}.get(l, 2))


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def test_html_is_self_contained(populated):
    page = render_html(collect_console_state(populated))
    assert page.startswith("<!doctype html>")
    for external in ("<script", "src=", "href=", "@import", "http://", "https://"):
        assert external not in page, external


def test_html_names_every_panel(populated):
    page = render_html(collect_console_state(populated))
    for label in ("Operator notices", "Missions", "Blocked missions", "Mission lifecycle",
                  "Agent hierarchy", "Review queue", "Approvals", "Disagreements",
                  "Evidence", "Worktrees", "Certification", "Repository",
                  "Active branches", "Integration candidates", "Resource usage"):
        assert label in page, label


def test_html_states_it_is_read_only(populated):
    page = render_html(collect_console_state(populated))
    assert "Read-only." in page
    assert "does not poll" in page


def test_html_escapes_hostile_content(tmp_path):
    settings = load_settings(store_dir=str(tmp_path))
    store = DevMissionStore(tmp_path)
    store.create(
        title="<script>alert(1)</script>",
        objective="o",
        starting_sha=SHA,
        dev_mission_id="dmxss1",
    )
    page = render_html(collect_console_state(settings))
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_text_render_lists_all_fifteen_panels(populated):
    text = render_text(collect_console_state(populated))
    for number in range(1, 16):
        assert f"\n{number} " in text or text.startswith(f"{number} ")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_cli_console_show_exits_zero(populated, capsys):
    from saathi.agentdev.cli import main

    assert main(["--store", str(populated.store_path()), "console", "show"]) == 0
    assert "Agent Operations Console" in capsys.readouterr().out


def test_cli_console_state_emits_json(populated, capsys):
    from saathi.agentdev.cli import main

    assert main(["--store", str(populated.store_path()), "console", "state"]) == 0
    assert json.loads(capsys.readouterr().out)["read_only"] is True


def test_cli_console_render_writes_the_requested_file(populated, tmp_path, capsys):
    from saathi.agentdev.cli import main

    target = tmp_path / "out" / "console.html"
    code = main([
        "--store", str(populated.store_path()),
        "console", "render", "--output", str(target),
    ])
    assert code == 0
    assert target.is_file()
    assert json.loads(capsys.readouterr().out)["rendered"] == str(target)


def test_cli_console_render_refuses_a_protected_output_path(populated, capsys):
    from saathi.agentdev.cli import EXIT_REFUSED, main

    code = main([
        "--store", str(populated.store_path()),
        "console", "render", "--output", "~/.claude/settings.json",
    ])
    assert code == EXIT_REFUSED
    assert json.loads(capsys.readouterr().out)["error"] == "output_path_protected"


def test_cli_console_rejects_a_forbidden_flag(capsys):
    from saathi.agentdev.cli import EXIT_USAGE, main

    assert main(["console", "show", "--force"]) == EXIT_USAGE
    assert json.loads(capsys.readouterr().out)["error"] == "forbidden_flag"
