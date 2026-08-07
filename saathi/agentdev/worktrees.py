"""M346 — Mission-bound worktree isolation.

The gap this closes, measured on the baseline commit: ``git worktree list``
reported over one hundred stale ``m233-worktree-*`` entries marked
``prunable``, created by the ad-hoc helper in
``saathi/platform/tg/integration_assurance/reproduction.py`` and removed with
``git worktree remove --force``. Two further hand-made agent worktrees existed
at ``~/.worktrees/`` on ``agent/*`` branches with no registry, no mission
binding and no collision check.

This module owns the opposite properties:

* one worktree binds to exactly one mission **and** one agent;
* branch names follow ``agent/<agent-id>/<mission-id>-<description>``;
* the starting SHA is recorded at creation and never rewritten;
* two worktrees can never share a branch or a path;
* removal is *planned*, and refused while uncommitted work exists;
* the destructive git verbs are absent from the allowlist, and
  :func:`_run_git` refuses an argv containing them even if a caller constructs
  one — technically enforced, not documented.

Creation additionally requires two environment flags that both default false,
plus a role that actually declares ``write_code``.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from saathi.agentdev.roles import RoleContract, require_role
from saathi.agentdev.settings import AgentDevSettings, load_settings

BRANCH_PREFIX = "agent"
_AGENT_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
_MISSION_RE = re.compile(r"^dm[a-z0-9]{2,24}$")
_DESC_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_BRANCH_RE = re.compile(
    r"^agent/(?P<agent>[a-z][a-z0-9-]*)/(?P<mission>dm[a-z0-9]+)-(?P<desc>[a-z0-9-]+)$"
)
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

#: Verbs and flags this module refuses to execute, whatever the caller asks for.
#: Checked as whole argv tokens, and as ``verb + flag`` pairs, in :func:`_run_git`.
FORBIDDEN_GIT_TOKENS = frozenset({
    "--force",
    "-f",
    "--hard",
    "-fd",
    "-fdx",
    "--force-with-lease",
})
#: Compared case-insensitively, which deliberately conflates ``git branch -d``
#: with ``git branch -D``: this module refuses to delete a branch either way,
#: because an unmerged implementation candidate is still evidence.
FORBIDDEN_GIT_SEQUENCES = (
    ("reset", "--hard"),
    ("clean",),
    ("push",),
    ("merge",),
    ("rebase",),
    ("branch", "-d"),
    ("branch", "-D"),
    ("branch", "--delete"),
    ("checkout", "--force"),
    ("worktree", "remove", "--force"),
    ("worktree", "prune"),
)

#: Read-only git verbs this module is allowed to run at all.
READ_ONLY_VERBS = frozenset({
    "rev-parse", "rev-list", "status", "worktree", "branch", "log", "diff",
    "show-ref",
})


class WorktreeError(RuntimeError):
    """Raised with a stable ``code`` so callers and tests can branch on it."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}" + (f" ({detail})" if detail else ""))


def build_branch_name(agent_id: str, mission_id: str, description: str) -> str:
    """Compose and validate the mandated branch name.

    ``mission_id`` deliberately contains no hyphen so the branch decomposes
    unambiguously back into its three parts.
    """
    if not _AGENT_RE.match(agent_id or ""):
        raise WorktreeError("invalid_agent_id", agent_id)
    if not _MISSION_RE.match(mission_id or ""):
        raise WorktreeError("invalid_mission_id", mission_id)
    if not _DESC_RE.match(description or ""):
        raise WorktreeError("invalid_description", description)
    branch = f"{BRANCH_PREFIX}/{agent_id}/{mission_id}-{description}"
    if not _BRANCH_RE.match(branch):
        raise WorktreeError("invalid_branch_name", branch)
    return branch


def parse_branch_name(branch: str) -> dict[str, str]:
    m = _BRANCH_RE.match(branch or "")
    if not m:
        raise WorktreeError("invalid_branch_name", branch)
    return {
        "agent_id": m.group("agent"),
        "mission_id": m.group("mission"),
        "description": m.group("desc"),
    }


def _assert_git_allowed(args: Iterable[str]) -> None:
    argv = list(args)
    if not argv:
        raise WorktreeError("empty_git_command")
    verb = argv[0]
    if verb not in READ_ONLY_VERBS and verb != "worktree":
        raise WorktreeError("git_verb_not_allowed", verb)
    lowered = [a.lower() for a in argv]
    for token in lowered:
        if token in FORBIDDEN_GIT_TOKENS:
            raise WorktreeError("forbidden_git_flag", token)
    for seq in FORBIDDEN_GIT_SEQUENCES:
        lowered_seq = tuple(part.lower() for part in seq)
        n = len(lowered_seq)
        for i in range(len(lowered) - n + 1):
            if tuple(lowered[i:i + n]) == lowered_seq:
                raise WorktreeError("forbidden_git_operation", " ".join(seq))


def _run_git(args: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str]:
    """Run one allowlisted git command.

    Every destructive verb is refused here, before ``subprocess`` is reached.
    This is the technically-enforced layer; the role contract's
    ``prohibited_actions`` list is the declarative one.
    """
    _assert_git_allowed(args)
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as exc:
        return 124, f"timeout: {exc}"
    except FileNotFoundError as exc:  # pragma: no cover — git absent
        return 127, str(exc)


def run_read_only_git(args: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str]:
    """Public entry point for other ``agentdev`` modules needing git.

    Delegates to the same allowlist :class:`WorktreeManager` uses, so there is
    one place where a destructive verb can be refused rather than two.
    """
    return _run_git(list(args), Path(cwd), timeout=timeout)


@dataclass
class GitWorktree:
    """One entry from ``git worktree list --porcelain``."""

    path: str
    head: str = ""
    branch: str = ""
    detached: bool = False
    prunable: bool = False
    prunable_reason: str = ""
    locked: bool = False

    @property
    def is_agent_worktree(self) -> bool:
        return bool(self.branch) and bool(_BRANCH_RE.match(self.branch))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["is_agent_worktree"] = self.is_agent_worktree
        return d


@dataclass
class WorktreePlan:
    """A proposed worktree. Produced without side effects; safe to print."""

    agent_id: str
    mission_id: str
    description: str
    branch: str
    path: str
    base_ref: str
    base_sha: str
    mode: str = "writable"
    refusals: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)

    @property
    def allowed(self) -> bool:
        return not self.refusals

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["allowed"] = self.allowed
        d["refusals"] = list(self.refusals)
        d["warnings"] = list(self.warnings)
        return d


@dataclass
class WorktreeRecord:
    """The registry entry that binds a worktree to one mission and one agent."""

    name: str
    agent_id: str
    mission_id: str
    description: str
    branch: str
    path: str
    base_ref: str
    starting_sha: str
    mode: str = "writable"
    status: str = "active"  # active | removal_planned | removed
    created_at: float = field(default_factory=time.time)
    removed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WorktreeRecord":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class WorktreeInspection:
    name: str
    path: str
    exists: bool
    branch: str = ""
    head: str = ""
    clean: bool = True
    dirty_files: tuple[str, ...] = ()
    untracked_files: tuple[str, ...] = ()
    contamination: tuple[str, ...] = ()
    commits_ahead_of_base: int = 0

    @property
    def safe_to_remove(self) -> bool:
        return self.clean and not self.contamination

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["dirty_files"] = list(self.dirty_files)
        d["untracked_files"] = list(self.untracked_files)
        d["contamination"] = list(self.contamination)
        d["safe_to_remove"] = self.safe_to_remove
        return d


class WorktreeManager:
    """Inspect, plan, create and plan-removal of mission-bound worktrees.

    Every mutating method is gated on :class:`AgentDevSettings`; every
    destructive one is absent by design. There is no ``remove()`` — only
    :meth:`removal_plan`, which emits the exact command an operator may run
    after reading the refusals.
    """

    def __init__(
        self,
        settings: AgentDevSettings | None = None,
        repo_root: Path | str | None = None,
    ):
        self.settings = settings or load_settings()
        self.repo_root = Path(repo_root or self.settings.repo_root).resolve()
        self.registry_path = self.settings.store_path() / "worktrees.json"

    # ---- registry -----------------------------------------------------------

    def _read_registry(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"worktrees": {}}
        try:
            return json.loads(self.registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            backup = self.registry_path.with_suffix(".json.bak")
            if backup.exists():
                try:
                    return json.loads(backup.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass
            raise WorktreeError("registry_corrupt", str(self.registry_path))

    def _write_registry(self, data: dict[str, Any]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        if self.registry_path.exists() and self.registry_path.stat().st_size > 0:
            backup = self.registry_path.with_suffix(".json.bak")
            backup.write_bytes(self.registry_path.read_bytes())
        tmp = self.registry_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, self.registry_path)

    def records(self) -> list[WorktreeRecord]:
        data = self._read_registry()
        return [
            WorktreeRecord.from_dict(v) for v in data.get("worktrees", {}).values()
        ]

    def record(self, name: str) -> WorktreeRecord | None:
        raw = self._read_registry().get("worktrees", {}).get(name)
        return WorktreeRecord.from_dict(raw) if raw else None

    def active_records(self) -> list[WorktreeRecord]:
        return [r for r in self.records() if r.status == "active"]

    # ---- git inspection -----------------------------------------------------

    def list_git_worktrees(self) -> list[GitWorktree]:
        """Parse ``git worktree list --porcelain``. Read-only."""
        code, out = _run_git(["worktree", "list", "--porcelain"], self.repo_root)
        if code != 0:
            raise WorktreeError("git_worktree_list_failed", out.strip()[:300])
        entries: list[GitWorktree] = []
        current: dict[str, Any] = {}
        for line in out.splitlines():
            if not line.strip():
                if current.get("path"):
                    entries.append(_to_git_worktree(current))
                current = {}
                continue
            key, _, value = line.partition(" ")
            if key == "worktree":
                if current.get("path"):
                    entries.append(_to_git_worktree(current))
                current = {"path": value}
            elif key in ("HEAD", "branch", "detached", "prunable", "locked"):
                current[key] = value if value else True
        if current.get("path"):
            entries.append(_to_git_worktree(current))
        return entries

    def inspect_environment(self) -> dict[str, Any]:
        """Census of the live git state plus the registry, and their disagreements."""
        git_entries = self.list_git_worktrees()
        registered = {r.path: r for r in self.active_records()}
        by_path = {e.path: e for e in git_entries}

        unregistered_agent = sorted(
            e.path for e in git_entries
            if e.is_agent_worktree and e.path not in registered
        )
        missing_on_disk = sorted(p for p in registered if p not in by_path)
        prunable = sorted(e.path for e in git_entries if e.prunable)

        branch_counts: dict[str, list[str]] = {}
        for e in git_entries:
            if e.branch:
                branch_counts.setdefault(e.branch, []).append(e.path)
        duplicate_branches = {b: p for b, p in branch_counts.items() if len(p) > 1}

        return {
            "repo_root": str(self.repo_root),
            "git_worktrees": [e.to_dict() for e in git_entries],
            "registered_active": [r.to_dict() for r in self.active_records()],
            "counts": {
                "git_total": len(git_entries),
                "agent_branches": sum(1 for e in git_entries if e.is_agent_worktree),
                "registered_active": len(registered),
                "prunable": len(prunable),
            },
            "findings": {
                "unregistered_agent_worktrees": unregistered_agent,
                "registered_but_missing_on_disk": missing_on_disk,
                "prunable_stale_worktrees": prunable,
                "duplicate_branch_checkouts": duplicate_branches,
            },
            "note": (
                "Stale prunable worktrees are reported, never removed. "
                "Pruning is an operator action; this milestone removes nothing."
            ),
        }

    # ---- planning -----------------------------------------------------------

    def plan(
        self,
        *,
        agent_id: str,
        mission_id: str,
        description: str,
        base_ref: str = "HEAD",
        mode: str = "writable",
    ) -> WorktreePlan:
        """Propose a worktree. Pure inspection — creates nothing.

        Collects **all** refusals rather than raising on the first, so an
        operator sees the complete picture in one pass.
        """
        refusals: list[str] = []
        warnings: list[str] = []

        branch = build_branch_name(agent_id, mission_id, description)
        parts = parse_branch_name(branch)
        path = str(self.settings.worktree_parent_path() / f"{mission_id}-{agent_id}")

        role: RoleContract | None = None
        try:
            role = require_role(agent_id)
        except Exception:
            refusals.append(f"unknown_agent_role:{agent_id}")

        if role is not None:
            if mode == "writable" and not role.may_write_code:
                refusals.append(f"role_may_not_write_code:{agent_id}")
            if mode == "writable" and role.default_worktree_mode != "writable":
                refusals.append(f"role_default_mode_is_{role.default_worktree_mode}")
            if mode not in ("readonly", "writable"):
                refusals.append(f"invalid_mode:{mode}")

        if not self.settings.agentdev_enabled:
            refusals.append("agentdev_disabled")
        if mode == "writable" and not self.settings.worktree_creation_enabled:
            refusals.append("worktree_creation_disabled")

        code, sha = _run_git(["rev-parse", base_ref], self.repo_root)
        base_sha = sha.strip() if code == 0 else ""
        if code != 0 or not _SHA_RE.match(base_sha):
            refusals.append(f"unresolvable_base_ref:{base_ref}")
            base_sha = ""

        # Branch collision — against live git and against the registry.
        for entry in self.list_git_worktrees():
            if entry.branch == branch:
                refusals.append(f"branch_already_checked_out:{entry.path}")
            if entry.path == path:
                refusals.append(f"path_already_a_worktree:{path}")
        code, _ = _run_git(["show-ref", "--verify", f"refs/heads/{branch}"], self.repo_root)
        if code == 0:
            refusals.append(f"branch_already_exists:{branch}")

        for record in self.active_records():
            if record.branch == branch:
                refusals.append(f"branch_registered_to:{record.name}")
            if record.path == path:
                refusals.append(f"path_registered_to:{record.name}")
            if record.mission_id == mission_id and record.agent_id == agent_id:
                refusals.append(f"agent_already_assigned_for_mission:{record.name}")

        if Path(path).exists():
            refusals.append(f"path_exists_on_disk:{path}")

        parent = self.settings.worktree_parent_path()
        if not parent.exists():
            warnings.append(f"worktree_parent_will_be_created:{parent}")

        return WorktreePlan(
            agent_id=parts["agent_id"],
            mission_id=parts["mission_id"],
            description=parts["description"],
            branch=branch,
            path=path,
            base_ref=base_ref,
            base_sha=base_sha,
            mode=mode,
            refusals=tuple(dict.fromkeys(refusals)),
            warnings=tuple(warnings),
        )

    # ---- creation -----------------------------------------------------------

    def create(self, plan: WorktreePlan, *, dry_run: bool = False) -> WorktreeRecord:
        """Create the worktree described by ``plan``.

        Re-plans first: a plan computed minutes ago may have been invalidated by
        another process. Fail-closed — any refusal aborts.
        """
        self.settings.assert_enabled()
        if plan.mode == "writable":
            self.settings.assert_worktree_creation_allowed()

        fresh = self.plan(
            agent_id=plan.agent_id,
            mission_id=plan.mission_id,
            description=plan.description,
            base_ref=plan.base_ref,
            mode=plan.mode,
        )
        if not fresh.allowed:
            raise WorktreeError("plan_refused", "; ".join(fresh.refusals))

        name = f"{fresh.mission_id}-{fresh.agent_id}"
        record = WorktreeRecord(
            name=name,
            agent_id=fresh.agent_id,
            mission_id=fresh.mission_id,
            description=fresh.description,
            branch=fresh.branch,
            path=fresh.path,
            base_ref=fresh.base_ref,
            starting_sha=fresh.base_sha,
            mode=fresh.mode,
        )
        if dry_run:
            return record

        self.settings.worktree_parent_path().mkdir(parents=True, exist_ok=True)
        code, out = _run_git(
            ["worktree", "add", "-b", fresh.branch, fresh.path, fresh.base_sha],
            self.repo_root,
            timeout=300,
        )
        if code != 0:
            raise WorktreeError("git_worktree_add_failed", out.strip()[:300])

        data = self._read_registry()
        data.setdefault("worktrees", {})[name] = record.to_dict()
        self._write_registry(data)
        return record

    # ---- inspection of one worktree ----------------------------------------

    def inspect(self, name: str) -> WorktreeInspection:
        record = self.record(name)
        if record is None:
            raise WorktreeError("unknown_worktree", name)
        path = Path(record.path)
        if not path.exists():
            return WorktreeInspection(
                name=name, path=record.path, exists=False,
                contamination=("worktree_missing_on_disk",),
                clean=False,
            )

        code, status_out = _run_git(["status", "--porcelain=v1"], path)
        if code != 0:
            raise WorktreeError("git_status_failed", status_out.strip()[:300])
        # porcelain=v1 lines are "XY<space>path"; the path always starts at 3.
        dirty, untracked = [], []
        for line in status_out.splitlines():
            if len(line) < 4:
                continue
            filename = line[3:].strip()
            if line.startswith("??"):
                untracked.append(filename)
            else:
                dirty.append(filename)

        code, head = _run_git(["rev-parse", "HEAD"], path)
        head = head.strip() if code == 0 else ""
        code, branch_out = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], path)
        branch = branch_out.strip() if code == 0 else ""

        contamination: list[str] = []
        if branch != record.branch:
            contamination.append(
                f"branch_drift:expected={record.branch}:actual={branch}"
            )
        try:
            parts = parse_branch_name(branch)
            if parts["agent_id"] != record.agent_id:
                contamination.append(f"agent_drift:{parts['agent_id']}")
            if parts["mission_id"] != record.mission_id:
                contamination.append(f"mission_drift:{parts['mission_id']}")
        except WorktreeError:
            contamination.append(f"branch_outside_agent_namespace:{branch}")

        for other in self.active_records():
            if other.name == name:
                continue
            if other.branch == record.branch:
                contamination.append(f"branch_shared_with:{other.name}")
            if other.path == record.path:
                contamination.append(f"path_shared_with:{other.name}")

        ahead = 0
        if record.starting_sha and head:
            code, count = _run_git(
                ["rev-list", "--count", f"{record.starting_sha}..HEAD"], path
            )
            if code == 0 and count.strip().isdigit():
                ahead = int(count.strip())

        return WorktreeInspection(
            name=name,
            path=record.path,
            exists=True,
            branch=branch,
            head=head,
            clean=not dirty and not untracked,
            dirty_files=tuple(dirty),
            untracked_files=tuple(untracked),
            contamination=tuple(dict.fromkeys(contamination)),
            commits_ahead_of_base=ahead,
        )

    # ---- removal planning ---------------------------------------------------

    def removal_plan(self, name: str) -> dict[str, Any]:
        """Prepare — never perform — removal.

        Refuses while uncommitted work exists. There is deliberately no method
        on this class that removes a worktree: the operator runs the emitted
        command, or does not.
        """
        record = self.record(name)
        if record is None:
            raise WorktreeError("unknown_worktree", name)

        inspection = self.inspect(name)
        refusals: list[str] = []
        if inspection.exists and inspection.dirty_files:
            refusals.append(
                f"uncommitted_changes:{len(inspection.dirty_files)}_files"
            )
        if inspection.exists and inspection.untracked_files:
            refusals.append(
                f"untracked_files:{len(inspection.untracked_files)}_files"
            )
        if inspection.contamination:
            refusals.append("contaminated:" + ",".join(inspection.contamination))
        if inspection.commits_ahead_of_base > 0:
            refusals.append(
                f"unmerged_commits:{inspection.commits_ahead_of_base}"
                " (branch is preserved; review before removing the checkout)"
            )

        safe = not refusals
        return {
            "name": name,
            "path": record.path,
            "branch": record.branch,
            "starting_sha": record.starting_sha,
            "inspection": inspection.to_dict(),
            "refusals": refusals,
            "safe_to_remove": safe,
            "operator_command": (
                f"git -C {self.repo_root} worktree remove {record.path}"
                if safe else None
            ),
            "forbidden": [
                "git worktree remove --force",
                "git branch -D",
                "git clean -fd",
                "git reset --hard",
            ],
            "note": (
                "This plan performs nothing. --force removal is never emitted, "
                "and the branch is never deleted: an implementation candidate "
                "that is not merged is still evidence."
            ),
        }

    def mark_removed(self, name: str) -> WorktreeRecord:
        """Record that an operator removed a worktree, after the fact.

        Only accepted when the worktree is genuinely gone from disk and from
        ``git worktree list``, so the registry cannot be desynchronised by an
        optimistic call.
        """
        record = self.record(name)
        if record is None:
            raise WorktreeError("unknown_worktree", name)
        if Path(record.path).exists():
            raise WorktreeError("worktree_still_present", record.path)
        if any(e.path == record.path for e in self.list_git_worktrees()):
            raise WorktreeError("worktree_still_registered_in_git", record.path)
        record.status = "removed"
        record.removed_at = time.time()
        data = self._read_registry()
        data.setdefault("worktrees", {})[name] = record.to_dict()
        self._write_registry(data)
        return record


def _to_git_worktree(raw: dict[str, Any]) -> GitWorktree:
    prunable = raw.get("prunable")
    return GitWorktree(
        path=str(raw.get("path") or ""),
        head=str(raw.get("HEAD") or ""),
        branch=str(raw.get("branch") or "").replace("refs/heads/", ""),
        detached=bool(raw.get("detached")),
        prunable=bool(prunable),
        prunable_reason="" if prunable is True or not prunable else str(prunable),
        locked=bool(raw.get("locked")),
    )
