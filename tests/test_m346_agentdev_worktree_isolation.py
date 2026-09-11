"""M346 — Mission-bound worktree isolation.

Creation tests run against a throwaway git repository under ``tmp_path``; the
SaathiOS repository is never mutated. The environment census test runs against
the real repository but is strictly read-only.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from saathi.agentdev.settings import load_settings
from saathi.agentdev.worktrees import (
    FORBIDDEN_GIT_SEQUENCES,
    WorktreeError,
    WorktreeManager,
    _assert_git_allowed,
    build_branch_name,
    parse_branch_name,
)


def _git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    )
    return proc.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal git repository with one commit."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(["init", "-b", "main"], root)
    _git(["config", "user.email", "test@example.invalid"], root)
    _git(["config", "user.name", "Test"], root)
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    _git(["add", "README.md"], root)
    _git(["commit", "-m", "seed"], root)
    return root


@pytest.fixture
def manager(repo: Path, tmp_path: Path) -> WorktreeManager:
    settings = load_settings(
        agentdev_enabled=True,
        worktree_creation_enabled=True,
        store_dir=str(tmp_path / "store"),
        worktree_parent=str(tmp_path / "worktrees"),
        repo_root=str(repo),
    )
    return WorktreeManager(settings=settings, repo_root=repo)


@pytest.fixture
def locked_manager(repo: Path, tmp_path: Path) -> WorktreeManager:
    """Default settings: both flags false."""
    settings = load_settings(
        store_dir=str(tmp_path / "store2"),
        worktree_parent=str(tmp_path / "worktrees2"),
        repo_root=str(repo),
    )
    return WorktreeManager(settings=settings, repo_root=repo)


# --------------------------------------------------------------------------
# Branch naming
# --------------------------------------------------------------------------


def test_branch_name_follows_the_mandated_convention():
    branch = build_branch_name("backend-engineering", "dm001", "eval-coverage")
    assert branch == "agent/backend-engineering/dm001-eval-coverage"
    assert parse_branch_name(branch) == {
        "agent_id": "backend-engineering",
        "mission_id": "dm001",
        "description": "eval-coverage",
    }


def test_mission_ids_carry_no_hyphen_so_the_branch_decomposes_unambiguously():
    branch = build_branch_name("frontend-engineering", "dmeval1", "a-b-c")
    parts = parse_branch_name(branch)
    assert parts["mission_id"] == "dmeval1"
    assert parts["description"] == "a-b-c"


@pytest.mark.parametrize(
    "agent,mission,desc,code",
    [
        ("Backend_Engineering", "dm001", "x", "invalid_agent_id"),
        ("backend-engineering", "m001", "x", "invalid_mission_id"),
        ("backend-engineering", "dm-001", "x", "invalid_mission_id"),
        ("backend-engineering", "dm001", "Bad Desc", "invalid_description"),
        ("backend-engineering", "dm001", "", "invalid_description"),
    ],
)
def test_malformed_branch_components_are_refused(agent, mission, desc, code):
    with pytest.raises(WorktreeError) as exc:
        build_branch_name(agent, mission, desc)
    assert exc.value.code == code


def test_parsing_a_foreign_branch_is_refused():
    for branch in ("main", "milestone/m344", "agent/backend-core", ""):
        with pytest.raises(WorktreeError) as exc:
            parse_branch_name(branch)
        assert exc.value.code == "invalid_branch_name"


# --------------------------------------------------------------------------
# Destructive git operations are refused before subprocess
# --------------------------------------------------------------------------


@pytest.mark.parametrize("sequence", FORBIDDEN_GIT_SEQUENCES)
def test_every_forbidden_git_sequence_is_refused(sequence):
    with pytest.raises(WorktreeError) as exc:
        _assert_git_allowed(list(sequence))
    assert exc.value.code in ("forbidden_git_operation", "git_verb_not_allowed", "forbidden_git_flag")


@pytest.mark.parametrize(
    "argv",
    [
        ["reset", "--hard", "HEAD"],
        ["clean", "-fd"],
        ["clean", "-fdx"],
        ["push", "--force"],
        ["push", "origin", "main"],
        ["merge", "main"],
        ["branch", "-D", "agent/x/dm1-y"],
        ["worktree", "remove", "--force", "/tmp/x"],
        ["worktree", "prune"],
        ["checkout", "--force", "main"],
        ["rebase", "main"],
    ],
)
def test_destructive_invocations_never_reach_subprocess(argv):
    with pytest.raises(WorktreeError):
        _assert_git_allowed(argv)


def test_force_flags_are_refused_on_any_verb():
    for flag in ("--force", "-f", "--hard", "--force-with-lease"):
        with pytest.raises(WorktreeError) as exc:
            _assert_git_allowed(["status", flag])
        assert exc.value.code == "forbidden_git_flag"


def test_unknown_verbs_are_refused():
    with pytest.raises(WorktreeError) as exc:
        _assert_git_allowed(["gc"])
    assert exc.value.code == "git_verb_not_allowed"
    with pytest.raises(WorktreeError) as exc:
        _assert_git_allowed([])
    assert exc.value.code == "empty_git_command"


def test_read_only_inspection_verbs_are_allowed():
    for argv in (
        ["status", "--porcelain=v1"],
        ["rev-parse", "HEAD"],
        ["worktree", "list", "--porcelain"],
        ["rev-list", "--count", "a..b"],
    ):
        _assert_git_allowed(argv)


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------


def test_plan_is_pure_and_creates_nothing(manager: WorktreeManager):
    plan = manager.plan(
        agent_id="backend-engineering", mission_id="dm001", description="eval-coverage"
    )
    assert plan.allowed
    assert plan.branch == "agent/backend-engineering/dm001-eval-coverage"
    assert not Path(plan.path).exists()
    assert plan.base_sha


def test_plan_refuses_when_both_flags_are_off(locked_manager: WorktreeManager):
    plan = locked_manager.plan(
        agent_id="backend-engineering", mission_id="dm001", description="x"
    )
    assert not plan.allowed
    assert "agentdev_disabled" in plan.refusals
    assert "worktree_creation_disabled" in plan.refusals


def test_plan_refuses_a_writable_worktree_for_a_non_coding_role(manager: WorktreeManager):
    plan = manager.plan(
        agent_id="research", mission_id="dm001", description="investigate"
    )
    assert not plan.allowed
    assert "role_may_not_write_code:research" in plan.refusals


def test_plan_refuses_an_unknown_role(manager: WorktreeManager):
    plan = manager.plan(agent_id="ghost-agent", mission_id="dm001", description="x")
    assert not plan.allowed
    assert "unknown_agent_role:ghost-agent" in plan.refusals


def test_plan_refuses_an_unresolvable_base_ref(manager: WorktreeManager):
    plan = manager.plan(
        agent_id="backend-engineering",
        mission_id="dm001",
        description="x",
        base_ref="refs/heads/does-not-exist",
    )
    assert not plan.allowed
    assert any(r.startswith("unresolvable_base_ref") for r in plan.refusals)


def test_plan_collects_every_refusal_not_just_the_first(locked_manager: WorktreeManager):
    plan = locked_manager.plan(
        agent_id="research", mission_id="dm001", description="x"
    )
    assert len(plan.refusals) >= 3


# --------------------------------------------------------------------------
# Creation, collision and binding
# --------------------------------------------------------------------------


def test_create_makes_one_worktree_bound_to_one_mission_and_agent(manager: WorktreeManager):
    plan = manager.plan(
        agent_id="backend-engineering", mission_id="dm001", description="eval-coverage"
    )
    record = manager.create(plan)
    assert Path(record.path).exists()
    assert record.branch == "agent/backend-engineering/dm001-eval-coverage"
    assert record.starting_sha == plan.base_sha
    assert record.status == "active"
    assert [r.name for r in manager.active_records()] == ["dm001-backend-engineering"]


def test_dry_run_creates_nothing(manager: WorktreeManager):
    plan = manager.plan(
        agent_id="backend-engineering", mission_id="dm001", description="x"
    )
    record = manager.create(plan, dry_run=True)
    assert not Path(record.path).exists()
    assert manager.active_records() == []


def test_two_worktrees_cannot_share_a_branch(manager: WorktreeManager):
    plan = manager.plan(
        agent_id="backend-engineering", mission_id="dm001", description="eval-coverage"
    )
    manager.create(plan)
    second = manager.plan(
        agent_id="backend-engineering", mission_id="dm001", description="eval-coverage"
    )
    assert not second.allowed
    assert any("branch_already" in r or "branch_registered" in r for r in second.refusals)
    with pytest.raises(WorktreeError) as exc:
        manager.create(plan)
    assert exc.value.code == "plan_refused"


def test_one_agent_gets_one_worktree_per_mission(manager: WorktreeManager):
    manager.create(
        manager.plan(
            agent_id="backend-engineering", mission_id="dm001", description="first"
        )
    )
    second = manager.plan(
        agent_id="backend-engineering", mission_id="dm001", description="second"
    )
    assert not second.allowed
    assert any(
        r.startswith("agent_already_assigned_for_mission") for r in second.refusals
    )


def test_different_agents_on_the_same_mission_are_allowed(manager: WorktreeManager):
    manager.create(
        manager.plan(
            agent_id="backend-engineering", mission_id="dm001", description="api"
        )
    )
    plan = manager.plan(
        agent_id="frontend-engineering", mission_id="dm001", description="ui"
    )
    assert plan.allowed
    record = manager.create(plan)
    assert record.name == "dm001-frontend-engineering"
    assert len(manager.active_records()) == 2


def test_create_refuses_when_worktree_creation_flag_is_off(
    locked_manager: WorktreeManager, manager: WorktreeManager
):
    plan = manager.plan(
        agent_id="backend-engineering", mission_id="dm001", description="x"
    )
    with pytest.raises(PermissionError) as exc:
        locked_manager.create(plan)
    assert "agentdev_disabled" in str(exc.value)


def test_create_re_plans_and_fails_closed(manager: WorktreeManager, repo: Path):
    """A stale plan must not be trusted."""
    plan = manager.plan(
        agent_id="backend-engineering", mission_id="dm001", description="x"
    )
    # Another process claims the branch in between.
    _git(["branch", "agent/backend-engineering/dm001-x"], repo)
    with pytest.raises(WorktreeError) as exc:
        manager.create(plan)
    assert exc.value.code == "plan_refused"
    assert "branch_already_exists" in exc.value.detail


# --------------------------------------------------------------------------
# Inspection, cleanliness and contamination
# --------------------------------------------------------------------------


def test_inspect_reports_a_clean_worktree(manager: WorktreeManager):
    record = manager.create(
        manager.plan(
            agent_id="backend-engineering", mission_id="dm001", description="x"
        )
    )
    inspection = manager.inspect(record.name)
    assert inspection.exists
    assert inspection.clean
    assert inspection.contamination == ()
    assert inspection.commits_ahead_of_base == 0
    assert inspection.safe_to_remove


def test_inspect_detects_uncommitted_and_untracked_work(manager: WorktreeManager):
    record = manager.create(
        manager.plan(
            agent_id="backend-engineering", mission_id="dm001", description="x"
        )
    )
    (Path(record.path) / "README.md").write_text("modified\n", encoding="utf-8")
    (Path(record.path) / "scratch.txt").write_text("new\n", encoding="utf-8")
    inspection = manager.inspect(record.name)
    assert not inspection.clean
    assert "README.md" in inspection.dirty_files
    assert "scratch.txt" in inspection.untracked_files
    assert not inspection.safe_to_remove


def test_inspect_detects_branch_drift_as_contamination(
    manager: WorktreeManager, repo: Path
):
    record = manager.create(
        manager.plan(
            agent_id="backend-engineering", mission_id="dm001", description="x"
        )
    )
    _git(["checkout", "-b", "sneaky-branch"], Path(record.path))
    inspection = manager.inspect(record.name)
    assert any(c.startswith("branch_drift") for c in inspection.contamination)
    assert any(
        c.startswith("branch_outside_agent_namespace") for c in inspection.contamination
    )
    assert not inspection.safe_to_remove


def test_inspect_counts_commits_ahead_of_the_recorded_start(manager: WorktreeManager):
    record = manager.create(
        manager.plan(
            agent_id="backend-engineering", mission_id="dm001", description="x"
        )
    )
    path = Path(record.path)
    (path / "feature.txt").write_text("work\n", encoding="utf-8")
    _git(["add", "feature.txt"], path)
    _git(["-c", "user.email=t@e.invalid", "-c", "user.name=T", "commit", "-m", "work"], path)
    inspection = manager.inspect(record.name)
    assert inspection.commits_ahead_of_base == 1
    assert inspection.clean


def test_inspect_reports_a_worktree_that_vanished(manager: WorktreeManager):
    record = manager.create(
        manager.plan(
            agent_id="backend-engineering", mission_id="dm001", description="x"
        )
    )
    import shutil

    shutil.rmtree(record.path)
    inspection = manager.inspect(record.name)
    assert not inspection.exists
    assert "worktree_missing_on_disk" in inspection.contamination


def test_inspect_unknown_worktree_is_refused(manager: WorktreeManager):
    with pytest.raises(WorktreeError) as exc:
        manager.inspect("nope")
    assert exc.value.code == "unknown_worktree"


# --------------------------------------------------------------------------
# Removal planning
# --------------------------------------------------------------------------


def test_removal_plan_refuses_while_uncommitted_work_exists(manager: WorktreeManager):
    record = manager.create(
        manager.plan(
            agent_id="backend-engineering", mission_id="dm001", description="x"
        )
    )
    (Path(record.path) / "README.md").write_text("edited\n", encoding="utf-8")
    plan = manager.removal_plan(record.name)
    assert not plan["safe_to_remove"]
    assert plan["operator_command"] is None
    assert any(r.startswith("uncommitted_changes") for r in plan["refusals"])


def test_removal_plan_refuses_while_untracked_files_exist(manager: WorktreeManager):
    record = manager.create(
        manager.plan(
            agent_id="backend-engineering", mission_id="dm001", description="x"
        )
    )
    (Path(record.path) / "notes.txt").write_text("draft\n", encoding="utf-8")
    plan = manager.removal_plan(record.name)
    assert not plan["safe_to_remove"]
    assert any(r.startswith("untracked_files") for r in plan["refusals"])


def test_removal_plan_refuses_while_commits_are_unmerged(manager: WorktreeManager):
    record = manager.create(
        manager.plan(
            agent_id="backend-engineering", mission_id="dm001", description="x"
        )
    )
    path = Path(record.path)
    (path / "feature.txt").write_text("work\n", encoding="utf-8")
    _git(["add", "feature.txt"], path)
    _git(["-c", "user.email=t@e.invalid", "-c", "user.name=T", "commit", "-m", "work"], path)
    plan = manager.removal_plan(record.name)
    assert not plan["safe_to_remove"]
    assert any(r.startswith("unmerged_commits") for r in plan["refusals"])


def test_removal_plan_emits_a_non_forcing_command_when_safe(manager: WorktreeManager):
    record = manager.create(
        manager.plan(
            agent_id="backend-engineering", mission_id="dm001", description="x"
        )
    )
    plan = manager.removal_plan(record.name)
    assert plan["safe_to_remove"]
    assert "--force" not in plan["operator_command"]
    assert plan["operator_command"].startswith("git -C ")
    assert "worktree remove" in plan["operator_command"]
    assert "git worktree remove --force" in plan["forbidden"]
    assert "git branch -D" in plan["forbidden"]


def test_manager_exposes_no_removal_method():
    """Removal is an operator action; the class must not offer one."""
    forbidden = {"remove", "delete", "prune", "force_remove", "destroy"}
    assert not forbidden & set(dir(WorktreeManager))


def test_mark_removed_refuses_while_the_worktree_still_exists(manager: WorktreeManager):
    record = manager.create(
        manager.plan(
            agent_id="backend-engineering", mission_id="dm001", description="x"
        )
    )
    with pytest.raises(WorktreeError) as exc:
        manager.mark_removed(record.name)
    assert exc.value.code == "worktree_still_present"


# --------------------------------------------------------------------------
# Environment census — read-only against the real repository
# --------------------------------------------------------------------------


def test_environment_census_reports_stale_worktrees_without_removing_them():
    settings = load_settings()
    census = WorktreeManager(settings=settings).inspect_environment()
    assert census["counts"]["git_total"] >= 1
    assert "prunable_stale_worktrees" in census["findings"]
    assert "never removed" in census["note"]


def test_census_flags_unregistered_agent_worktrees(manager: WorktreeManager, repo: Path):
    """A worktree on an agent/ branch that the registry does not know about."""
    stray = repo.parent / "stray"
    _git(
        ["worktree", "add", "-b", "agent/frontend-engineering/dm009-stray", str(stray)],
        repo,
    )
    census = manager.inspect_environment()
    assert str(stray.resolve()) in [
        str(Path(p).resolve())
        for p in census["findings"]["unregistered_agent_worktrees"]
    ]
