"""M20.0 — Push verification (no force/merge/deploy)."""
from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from saathi.engineering.settings import EngineeringSettings


@dataclass
class PushVerification:
    ok: bool
    pre_push: dict[str, Any] = field(default_factory=dict)
    post_push: dict[str, Any] = field(default_factory=dict)
    pushed: bool = False
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _git(root: Path, *args: str) -> tuple[int, str]:
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        return p.returncode, (p.stdout or "").strip() + (p.stderr or "").strip()
    except Exception as exc:
        return 1, str(exc)


def pre_push_check(
    repository_root: str | Path,
    settings: EngineeringSettings,
    *,
    expected_branch: str,
    commit_verified: bool,
    validations_passed: bool,
    secret_clean: bool = True,
    includes_merge_or_deploy: bool = False,
    git_fn: Callable[..., tuple[int, str]] | None = None,
) -> PushVerification:
    root = Path(repository_root)
    git = git_fn or (lambda *a: _git(root, *a))
    reasons: list[str] = []
    pre: dict[str, Any] = {}

    if settings.force_push_allowed:
        reasons.append("force_push_must_never_be_allowed")
    if settings.merge_allowed:
        reasons.append("merge_must_never_be_allowed")
    if settings.deploy_allowed:
        reasons.append("deploy_must_never_be_allowed")

    if not settings.pushes_enabled:
        reasons.append("pushes_disabled")

    rc, branch = git("rev-parse", "--abbrev-ref", "HEAD")
    pre["branch"] = branch
    if expected_branch and branch != expected_branch:
        reasons.append("wrong_branch")

    rc, counts = git(
        "rev-list", "--left-right", "--count", f"origin/{branch}...HEAD"
    )
    pre["divergence"] = counts
    if rc == 0 and counts:
        parts = counts.split()
        if len(parts) == 2 and int(parts[0]) > 0:
            reasons.append("unexpected_divergence_behind_origin")

    if not commit_verified:
        reasons.append("commit_not_verified")
    if not validations_passed:
        reasons.append("validations_not_passed")
    if not secret_clean:
        reasons.append("secret_detected")
    if includes_merge_or_deploy:
        reasons.append("merge_or_deploy_included")

    return PushVerification(
        ok=len(reasons) == 0,
        pre_push=pre,
        reasons=reasons,
    )


def verify_after_push(
    repository_root: str | Path,
    *,
    expected_branch: str,
    expected_head: str = "",
    git_fn: Callable[..., tuple[int, str]] | None = None,
) -> PushVerification:
    root = Path(repository_root)
    git = git_fn or (lambda *a: _git(root, *a))
    reasons: list[str] = []
    post: dict[str, Any] = {}

    rc, status = git("status", "-sb")
    post["status"] = status
    rc, counts = git(
        "rev-list", "--left-right", "--count",
        f"origin/{expected_branch}...HEAD",
    )
    post["divergence"] = counts
    rc, log = git("log", "--oneline", "--decorate", "-8")
    post["log"] = log
    rc, head = git("rev-parse", "HEAD")
    post["head"] = head[:12] if head else ""

    if counts and counts.split()[:1] != ["0"]:
        # behind should be 0 for sync; format "behind ahead"
        parts = counts.split()
        if len(parts) == 2 and (int(parts[0]) != 0 or int(parts[1]) != 0):
            reasons.append("not_synchronized")
    if expected_head and post["head"] and not (
        post["head"].startswith(expected_head[:7])
        or expected_head.startswith(post["head"])
    ):
        reasons.append("head_mismatch")
    if status and "\n" in status:
        # dirty files after status first line
        lines = status.splitlines()
        if len(lines) > 1:
            reasons.append("working_tree_not_clean")

    return PushVerification(
        ok=len(reasons) == 0,
        post_push=post,
        pushed=True,
        reasons=reasons,
    )


def perform_push(
    repository_root: str | Path,
    settings: EngineeringSettings,
    *,
    expected_branch: str,
    commit_verified: bool,
    validations_passed: bool,
    secret_clean: bool = True,
    dry_run: bool = True,
    git_fn: Callable[..., tuple[int, str]] | None = None,
) -> PushVerification:
    """Push only when policy allows. Default dry_run records intent only."""
    pre = pre_push_check(
        repository_root,
        settings,
        expected_branch=expected_branch,
        commit_verified=commit_verified,
        validations_passed=validations_passed,
        secret_clean=secret_clean,
        git_fn=git_fn,
    )
    if not pre.ok:
        return pre

    root = Path(repository_root)
    git = git_fn or (lambda *a: _git(root, *a))

    if dry_run or not settings.pushes_enabled:
        pre.pre_push["dry_run"] = True
        pre.pushed = False
        pre.reasons.append("dry_run_or_disabled")
        pre.ok = False if not settings.pushes_enabled else True
        if settings.pushes_enabled and dry_run:
            pre.ok = True
            pre.reasons = [r for r in pre.reasons if r != "dry_run_or_disabled"]
            pre.pre_push["note"] = "dry_run_ok_not_pushed"
        return pre

    # Never force
    rc, out = git("push", "origin", expected_branch)
    if rc != 0:
        return PushVerification(
            ok=False,
            pre_push=pre.pre_push,
            reasons=[f"push_failed:{out[:200]}"],
            pushed=False,
        )
    post = verify_after_push(
        repository_root,
        expected_branch=expected_branch,
        git_fn=git_fn,
    )
    post.pre_push = pre.pre_push
    post.pushed = True
    return post
