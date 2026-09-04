"""M350 — Agent environment control surface.

Every command is exercised through ``main()`` with a temporary store, so the
tests never touch the repository's own ``data/agentdev`` directory.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.agentdev.cli import (
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_USAGE,
    FORBIDDEN_FLAGS,
    build_parser,
    main,
)

SHA = "53b9b20736d5acf4a7ca3a9bd25b68d01e666a5d"


@pytest.fixture
def store(tmp_path: Path) -> str:
    return str(tmp_path / "agentdev")


def _run(capsys, argv: list[str]) -> tuple[int, dict]:
    code = main(argv)
    out = capsys.readouterr().out
    try:
        return code, json.loads(out)
    except json.JSONDecodeError:
        return code, {"_raw": out}


def _create_mission(capsys, store: str) -> str:
    code, payload = _run(capsys, [
        "--store", store, "mission", "create",
        "--title", "Eval coverage",
        "--objective", "Decide whether to adopt it.",
        "--sha", SHA,
    ])
    assert code == EXIT_OK
    return payload["dev_mission_id"]


# --------------------------------------------------------------------------
# Forbidden flags
# --------------------------------------------------------------------------


@pytest.mark.parametrize("flag", FORBIDDEN_FLAGS)
def test_every_forbidden_flag_is_refused_before_parsing(capsys, flag):
    code, payload = _run(capsys, ["mission", "list", flag])
    assert code == EXIT_USAGE
    assert payload["error"] == "forbidden_flag"
    assert payload["flag"] == flag


def test_the_forbidden_set_covers_the_dangerous_verbs():
    for flag in ("--force", "--skip-approval", "--merge", "--push", "--deploy", "--trade"):
        assert flag in FORBIDDEN_FLAGS


def test_no_subcommand_named_after_a_prohibited_action():
    parser = build_parser()
    actions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
    names: set[str] = set()
    for action in actions:
        names.update(action.choices or {})
    for prohibited in ("push", "merge", "deploy", "remove", "delete", "prune", "trade"):
        assert prohibited not in names


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------


def test_doctor_reports_settings_registry_and_denials(capsys, store):
    code, payload = _run(capsys, ["--store", store, "doctor"])
    assert code == EXIT_OK
    assert payload["registry"]["status"] == "ok"
    assert payload["registry"]["roles"] == 14
    assert payload["registry"]["security_veto"] == ["security-governance"]
    assert all(value is False for value in payload["denials"].values())
    assert payload["settings"]["agentdev_enabled"] is False


def test_doctor_reports_the_worktree_census_without_removing_anything(capsys, store):
    _, payload = _run(capsys, ["--store", store, "doctor"])
    assert "counts" in payload["worktrees"]
    assert "prunable_stale_worktrees" in payload["worktrees"]["findings"]


# --------------------------------------------------------------------------
# agents
# --------------------------------------------------------------------------


def test_agent_list_returns_all_fourteen(capsys, store):
    code, payload = _run(capsys, ["--store", store, "agent", "list"])
    assert code == EXIT_OK
    assert len(payload["roles"]) == 14
    writers = [r for r in payload["roles"] if r["writes_code"]]
    assert len(writers) == 3


def test_agent_show_returns_one_contract(capsys, store):
    code, payload = _run(capsys, ["--store", store, "agent", "show", "ceo"])
    assert code == EXIT_OK
    assert payload["agent_id"] == "ceo"
    assert payload["may_write_code"] is False


def test_agent_show_refuses_an_unknown_id(capsys, store):
    code, payload = _run(capsys, ["--store", store, "agent", "show", "ghost"])
    assert code == EXIT_NOT_FOUND
    assert payload["error"] == "unknown_agent_id"


# --------------------------------------------------------------------------
# missions
# --------------------------------------------------------------------------


def test_mission_create_dry_run_creates_nothing(capsys, store):
    code, payload = _run(capsys, [
        "--store", store, "mission", "create", "--dry-run",
        "--title", "T", "--objective", "O", "--sha", SHA,
    ])
    assert code == EXIT_OK
    assert payload["dry_run"] is True
    code, listing = _run(capsys, ["--store", store, "mission", "list"])
    assert listing["missions"] == []


def test_mission_create_and_status(capsys, store):
    mission_id = _create_mission(capsys, store)
    code, payload = _run(capsys, ["--store", store, "mission", "status", mission_id])
    assert code == EXIT_OK
    assert payload["state"] == "intake"
    assert payload["terminal_verdict"] is None


def test_mission_create_refuses_a_bad_sha(capsys, store):
    code, payload = _run(capsys, [
        "--store", store, "mission", "create",
        "--title", "T", "--objective", "O", "--sha", "nope",
    ])
    assert code == EXIT_REFUSED
    assert payload["error"] == "invalid_starting_sha"


def test_mission_status_refuses_an_unknown_mission(capsys, store):
    code, payload = _run(capsys, ["--store", store, "mission", "status", "dmnope"])
    assert code == EXIT_NOT_FOUND
    assert payload["error"] == "unknown_mission"


def test_mission_advance_dry_run_reports_the_gate_it_would_hit(capsys, store):
    mission_id = _create_mission(capsys, store)
    _run(capsys, [
        "--store", store, "mission", "advance", mission_id,
        "--state", "decomposed", "--actor", "program-manager",
    ])
    _run(capsys, [
        "--store", store, "mission", "advance", mission_id,
        "--state", "research", "--actor", "program-manager",
    ])
    code, payload = _run(capsys, [
        "--store", store, "mission", "advance", mission_id,
        "--state", "design", "--actor", "program-manager", "--dry-run",
    ])
    assert code == EXIT_OK
    assert payload["would_succeed"] is False
    assert payload["unmet_exit_gates"] == ["research_completeness"]


def test_mission_advance_refuses_a_skipped_gate(capsys, store):
    mission_id = _create_mission(capsys, store)
    for state in ("decomposed", "research"):
        _run(capsys, [
            "--store", store, "mission", "advance", mission_id,
            "--state", state, "--actor", "program-manager",
        ])
    code, payload = _run(capsys, [
        "--store", store, "mission", "advance", mission_id,
        "--state", "design", "--actor", "program-manager",
    ])
    assert code == EXIT_REFUSED
    assert payload["error"] == "gate_not_passed"


# --------------------------------------------------------------------------
# worktrees
# --------------------------------------------------------------------------


def test_worktree_census_is_read_only(capsys, store):
    code, payload = _run(capsys, ["--store", store, "worktree", "census"])
    assert code == EXIT_OK
    assert "never removed" in payload["note"]


def test_worktree_plan_refuses_while_the_flags_are_off(capsys, store):
    code, payload = _run(capsys, [
        "--store", store, "worktree", "plan",
        "--agent-id", "backend-engineering",
        "--mission-id", "dm001",
        "--description", "eval-coverage",
    ])
    assert code == EXIT_REFUSED
    assert "agentdev_disabled" in payload["refusals"]
    assert payload["allowed"] is False


def test_worktree_plan_refuses_a_non_coding_role(capsys, store):
    code, payload = _run(capsys, [
        "--store", store, "worktree", "plan",
        "--agent-id", "research", "--mission-id", "dm001", "--description", "x",
    ])
    assert code == EXIT_REFUSED
    assert "role_may_not_write_code:research" in payload["refusals"]


def test_worktree_create_is_refused_without_the_flags(capsys, store):
    code, payload = _run(capsys, [
        "--store", store, "worktree", "create",
        "--agent-id", "backend-engineering",
        "--mission-id", "dm001", "--description", "x",
    ])
    assert code == EXIT_REFUSED
    assert payload["error"] == "permission_denied"


def test_worktree_inspect_refuses_an_unknown_name(capsys, store):
    code, payload = _run(capsys, ["--store", store, "worktree", "inspect", "nope"])
    assert code == EXIT_NOT_FOUND
    assert payload["error"] == "unknown_worktree"


# --------------------------------------------------------------------------
# meetings, gates, review, config
# --------------------------------------------------------------------------


def test_meeting_participants_lists_the_required_roles(capsys, store):
    code, payload = _run(capsys, [
        "--store", store, "meeting", "participants", "red_team_review",
    ])
    assert code == EXIT_OK
    assert set(payload["required_participants"]) == {
        "security-governance", "testing-verification", "code-review", "architecture",
    }


def test_meeting_participants_refuses_an_unknown_type(capsys, store):
    code, payload = _run(capsys, ["--store", store, "meeting", "participants", "standup"])
    assert code == EXIT_USAGE
    assert payload["error"] == "unknown_meeting_type"


def test_gate_report_lists_every_gate(capsys, store):
    mission_id = _create_mission(capsys, store)
    code, payload = _run(capsys, ["--store", store, "gate", "report", mission_id])
    assert code == EXIT_OK
    assert len(payload["gates"]) == 11
    assert all(row["status"] == "pending" for row in payload["gates"])


def test_gate_evaluate_writes_nothing_and_reports_refusals(capsys, store):
    mission_id = _create_mission(capsys, store)
    code, payload = _run(capsys, [
        "--store", store, "gate", "evaluate", mission_id,
        "--gate", "research_completeness",
        "--approver", "research", "--subject", "research",
    ])
    assert code == EXIT_REFUSED
    assert "self_approval_forbidden" in payload["refusals"]
    _, report = _run(capsys, ["--store", store, "gate", "report", mission_id])
    assert all(row["status"] == "pending" for row in report["gates"])


def test_review_standard_publishes_the_finding_requirements(capsys, store):
    code, payload = _run(capsys, ["--store", store, "review", "standard"])
    assert code == EXIT_OK
    assert "concrete, relevant failure mode" in payload["principle"]


def test_config_check_refuses_a_protected_path(capsys, store):
    code, payload = _run(capsys, [
        "--store", store, "config", "check", "~/.claude/settings.json",
    ])
    assert code == EXIT_REFUSED
    assert payload["protected"] is True


def test_config_check_allows_a_repository_path(capsys, store):
    code, payload = _run(capsys, [
        "--store", store, "config", "check", "saathi/agentdev/roles.py",
    ])
    assert code == EXIT_OK
    assert payload["protected"] is False


def test_config_surface_publishes_the_protected_set(capsys, store):
    code, payload = _run(capsys, ["--store", store, "config", "surface"])
    assert code == EXIT_OK
    paths = {row["path"] for row in payload["home_prefixes"]}
    assert "~/.claude" in paths
    assert "~/.config/opencode" in paths


# --------------------------------------------------------------------------
# verify and simulate
# --------------------------------------------------------------------------


def test_verify_reports_a_fresh_mission_as_consistent(capsys, store):
    mission_id = _create_mission(capsys, store)
    code, payload = _run(capsys, ["--store", store, "verify", mission_id])
    assert code == EXIT_OK
    assert payload["verdict"] == "consistent"
    assert payload["problems"] == []


def test_verify_refuses_an_unknown_mission(capsys, store):
    code, payload = _run(capsys, ["--store", store, "verify", "dmnope"])
    assert code == EXIT_NOT_FOUND


def test_simulate_dry_run_creates_nothing(capsys, store):
    code, payload = _run(capsys, ["--store", store, "simulate", "--dry-run"])
    assert code == EXIT_OK
    assert payload["dry_run"] is True
    assert len(payload["would_run"]) == 12
    assert not Path(store).exists() or not list(Path(store).glob("dm*"))
