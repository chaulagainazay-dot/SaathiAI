"""M20.0 — Repository readiness checker (pre-launch gate)."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from saathi.engineering.models import ReadinessState
from saathi.engineering.settings import EngineeringSettings

# Minimum free disk (bytes) before degraded/unsafe
MIN_DISK_BYTES = 500 * 1024 * 1024  # 500 MB
LOW_DISK_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB


@dataclass
class ReadinessReport:
    state: str
    repository_root: str
    branch: str = ""
    head: str = ""
    checks: dict[str, Any] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    write_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def ok_for_write_launch(self) -> bool:
        return self.state in (
            ReadinessState.READY.value,
            ReadinessState.DEGRADED.value,
        ) and self.write_allowed and not self.blockers


def _run_git(root: Path, *args: str, timeout: int = 15) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except Exception as exc:
        return 99, "", str(exc)


def _branch_allowed(branch: str, patterns: list[str]) -> bool:
    import fnmatch
    if not branch or branch == "HEAD":
        return False
    for pat in patterns:
        if fnmatch.fnmatch(branch, pat) or branch == pat:
            return True
    return False


def _repo_registered(root: Path, settings: EngineeringSettings) -> bool:
    root_s = str(root.resolve())
    for allowed in settings.allowed_repositories:
        if allowed in ("saathiai", "saathi", "SaathiAI"):
            # canonical monorepo name or path suffix
            if root_s.endswith("SaathiAI") or root.name in ("SaathiAI", "saathi"):
                return True
        try:
            if Path(allowed).resolve() == root.resolve():
                return True
        except Exception:
            if allowed == root_s or allowed == root.name:
                return True
    return False


def check_repository_readiness(
    repository_root: str | Path,
    settings: EngineeringSettings,
    *,
    expected_branch: str | None = None,
    require_remote: bool = False,
    active_writer: bool = False,
    required_tools: list[str] | None = None,
    disk_free_fn: Callable[[Path], int] | None = None,
    git_runner: Callable[..., tuple[int, str, str]] | None = None,
) -> ReadinessReport:
    """Structured readiness. No agent launch for write work unless acceptable."""
    root = Path(repository_root).resolve()
    report = ReadinessReport(
        state=ReadinessState.READY.value,
        repository_root=str(root),
    )
    checks: dict[str, Any] = {}
    blockers: list[str] = []
    warnings: list[str] = []
    git = git_runner or (lambda *a, **k: _run_git(root, *a))

    # Canonical root exists + .git
    if not root.is_dir():
        blockers.append("root_missing")
        checks["root"] = False
    else:
        checks["root"] = True
    git_dir = root / ".git"
    if not git_dir.exists():
        blockers.append("not_a_git_repository")
        checks["git"] = False
    else:
        checks["git"] = True

    # Registered
    registered = _repo_registered(root, settings)
    checks["registered"] = registered
    if not registered:
        blockers.append("repository_not_registered")

    # Branch / HEAD
    rc, branch, _ = git("rev-parse", "--abbrev-ref", "HEAD")
    rc2, head, _ = git("rev-parse", "HEAD")
    report.branch = branch
    report.head = head[:12] if head else ""
    checks["branch"] = branch
    checks["head"] = report.head

    if branch == "HEAD" or not branch:
        blockers.append("detached_HEAD")
        checks["detached"] = True
    else:
        checks["detached"] = False

    if expected_branch and branch != expected_branch:
        blockers.append(f"unexpected_branch:{branch}!={expected_branch}")
        checks["expected_branch"] = False
    else:
        checks["expected_branch"] = True

    if not _branch_allowed(branch, settings.allowed_branches):
        blockers.append(f"branch_not_allowlisted:{branch}")
        checks["branch_allowlisted"] = False
    else:
        checks["branch_allowlisted"] = True

    # Working tree
    rc, dirty, _ = git("status", "--porcelain")
    dirty_lines = [ln for ln in dirty.splitlines() if ln.strip()]
    checks["dirty_count"] = len(dirty_lines)
    checks["dirty_sample"] = dirty_lines[:20]
    if dirty_lines:
        warnings.append("working_tree_dirty")
        # dirty is degraded unless explicitly understood; for write launch block
        if settings.repository_writes_enabled:
            blockers.append("working_tree_not_clean")

    # Merge / rebase in progress
    merge_in = (root / ".git" / "MERGE_HEAD").exists()
    rebase_in = (root / ".git" / "rebase-merge").exists() or (
        root / ".git" / "rebase-apply"
    ).exists()
    checks["merge_in_progress"] = merge_in
    checks["rebase_in_progress"] = rebase_in
    if merge_in:
        blockers.append("merge_in_progress")
    if rebase_in:
        blockers.append("rebase_in_progress")

    # Active conflicting writer
    checks["active_writer"] = active_writer
    if active_writer:
        blockers.append("active_conflicting_writer")

    # Divergence
    rc, counts, _ = git("rev-list", "--left-right", "--count",
                        f"origin/{branch}...HEAD")
    if rc == 0 and counts:
        parts = counts.split()
        if len(parts) == 2:
            behind, ahead = int(parts[0]), int(parts[1])
            checks["behind"] = behind
            checks["ahead"] = ahead
            if behind > 0 and ahead > 0:
                warnings.append("diverged_from_origin")
                if behind > 20:
                    blockers.append("unsafe_divergence")
    else:
        checks["divergence"] = "unknown"
        if require_remote:
            warnings.append("remote_unreachable_or_missing")

    if require_remote:
        rc, _, err = git("ls-remote", "--heads", "origin", timeout=20)
        checks["remote_reachable"] = rc == 0
        if rc != 0:
            warnings.append("remote_not_reachable")
            if settings.pushes_enabled:
                blockers.append("remote_required_unreachable")

    # Disk
    def _disk(p: Path) -> int:
        if disk_free_fn:
            return disk_free_fn(p)
        try:
            return shutil.disk_usage(p).free
        except Exception:
            return -1

    free = _disk(root)
    checks["disk_free_bytes"] = free
    if free >= 0:
        if free < MIN_DISK_BYTES:
            blockers.append("disk_space_unsafe")
        elif free < LOW_DISK_BYTES:
            warnings.append("disk_space_low")

    # Tools
    tools = required_tools or ["git", "python3"]
    missing = [t for t in tools if shutil.which(t) is None]
    checks["required_tools"] = tools
    checks["missing_tools"] = missing
    if missing:
        blockers.append(f"missing_tools:{','.join(missing)}")

    # Write permission flag from settings (not OS)
    write_perm = bool(
        settings.orchestrator_enabled
        and settings.repository_writes_enabled
        and registered
    )
    checks["settings_write_permission"] = write_perm

    # Secret exposure: flag if .env is staged
    staged_secrets = [
        ln for ln in dirty_lines
        if any(x in ln for x in (".env", "credentials", "id_rsa", ".pem"))
    ]
    if staged_secrets:
        blockers.append("unresolved_secret_exposure_risk")
        checks["secret_risk_paths"] = staged_secrets[:5]

    report.checks = checks
    report.blockers = blockers
    report.warnings = warnings
    report.write_allowed = write_perm and not blockers

    if any(b in blockers for b in (
        "not_a_git_repository", "root_missing", "disk_space_unsafe",
        "merge_in_progress", "rebase_in_progress", "detached_HEAD",
        "unresolved_secret_exposure_risk",
    )):
        report.state = ReadinessState.UNSAFE.value
    elif blockers:
        if any("approval" in b for b in blockers):
            report.state = ReadinessState.REQUIRES_APPROVAL.value
        else:
            report.state = ReadinessState.BLOCKED.value
    elif warnings:
        report.state = ReadinessState.DEGRADED.value
    else:
        report.state = ReadinessState.READY.value

    return report
