"""Canonical repository identity for indexing and retrieval (M18.2).

Extends M18.1 namespace isolation with branch, commit, worktree, and remote
identity so same folder names / worktrees never collide.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from saathi.mcp_governance.namespace import (
    NamespaceError,
    normalize_project_root,
    project_namespace,
)

INDEX_SCHEMA_VERSION = "m18.2.1"
NAMESPACE_VERSION = "m18.1+m18.2"


@dataclass(frozen=True)
class RepoIdentity:
    repository_root: str
    repository_id: str
    project_name: str
    project_namespace: str
    workspace_id: str
    branch: str
    commit_sha: str
    worktree_id: str
    git_remote: str
    is_git: bool
    detached_head: bool
    dirty_worktree: bool
    non_git_mode: bool
    namespace_version: str = NAMESPACE_VERSION
    index_schema_version: str = INDEX_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def index_key(self) -> str:
        """Stable key for the on-disk index namespace (repo + worktree + schema)."""
        raw = f"{self.repository_id}|{self.worktree_id}|{self.index_schema_version}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _run_git(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if proc.returncode != 0:
            return None
        return (proc.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return None


def resolve_identity(
    project_root: str | Path | None = None,
    *,
    alias: str | None = None,
    allow_non_git: bool = False,
) -> RepoIdentity:
    """Resolve full identity. Fail closed if not a git repo unless allow_non_git."""
    root = normalize_project_root(project_root or Path.cwd())
    git_dir = root / ".git"
    is_git = git_dir.exists() or (git_dir.is_file())  # worktree .git file

    # Nested git: if root is not git but parent is, still only use *this* root
    if not is_git and not (root / ".git").exists():
        # check if we're inside a git worktree via rev-parse
        top = _run_git(root, "rev-parse", "--show-toplevel")
        if top:
            try:
                top_p = Path(top).resolve()
                if top_p == root:
                    is_git = True
                elif top_p != root:
                    # We are inside a nested path of another repo — treat as non-git
                    # unless this root is itself a nested repo with .git
                    is_git = False
            except OSError:
                is_git = False

    if not is_git:
        if not allow_non_git:
            raise NamespaceError(
                f"not a git repository (fail-closed): {root}. "
                "Pass allow_non_git=True for explicit non-Git workspace mode."
            )
        ns = project_namespace(root, alias=alias)
        rid = hashlib.sha256(str(root).encode()).hexdigest()[:16]
        wt = hashlib.sha256(f"nongit|{root}".encode()).hexdigest()[:12]
        return RepoIdentity(
            repository_root=str(root),
            repository_id=f"nongit_{rid}",
            project_name=root.name,
            project_namespace=ns,
            workspace_id=f"ws_{wt}",
            branch="NO_GIT",
            commit_sha="0" * 40,
            worktree_id=wt,
            git_remote="",
            is_git=False,
            detached_head=False,
            dirty_worktree=False,
            non_git_mode=True,
        )

    # Prefer actual git toplevel
    top = _run_git(root, "rev-parse", "--show-toplevel") or str(root)
    top_p = Path(top).resolve()
    # Nested repository: if requested root has its own .git and differs from top, use root
    if (root / ".git").exists() and top_p != root:
        # We're in a nested git submodule or nested repo — use root if it has .git
        top_p = root

    ns = project_namespace(top_p, alias=alias)
    branch = _run_git(top_p, "rev-parse", "--abbrev-ref", "HEAD") or "HEAD"
    commit = _run_git(top_p, "rev-parse", "HEAD") or ("0" * 40)
    detached = branch == "HEAD"
    if detached:
        # confirm
        symbolic = _run_git(top_p, "symbolic-ref", "-q", "HEAD")
        detached = symbolic is None

    remote = _run_git(top_p, "config", "--get", "remote.origin.url") or ""
    status = _run_git(top_p, "status", "--porcelain")
    dirty = bool(status)

    # Worktree identity: common dir + git-dir
    git_common = _run_git(top_p, "rev-parse", "--git-common-dir") or ".git"
    git_dir_path = _run_git(top_p, "rev-parse", "--git-dir") or ".git"
    wt_raw = f"{top_p}|{git_common}|{git_dir_path}"
    worktree_id = hashlib.sha256(wt_raw.encode()).hexdigest()[:12]

    # Repository ID: remote if present else path hash (same folder names don't collide)
    if remote:
        rid_src = remote.strip().lower().rstrip(".git")
    else:
        rid_src = str(top_p)
    repository_id = "repo_" + hashlib.sha256(rid_src.encode()).hexdigest()[:16]
    workspace_id = "ws_" + hashlib.sha256(
        f"{repository_id}|{worktree_id}".encode()
    ).hexdigest()[:12]

    return RepoIdentity(
        repository_root=str(top_p),
        repository_id=repository_id,
        project_name=top_p.name,
        project_namespace=ns,
        workspace_id=workspace_id,
        branch=branch,
        commit_sha=commit,
        worktree_id=worktree_id,
        git_remote=remote,
        is_git=True,
        detached_head=bool(detached),
        dirty_worktree=dirty,
        non_git_mode=False,
    )


def identity_compatible(stored: dict, current: RepoIdentity) -> tuple[bool, str]:
    """Whether an existing index may be reused for *current* identity."""
    if stored.get("index_schema_version") != current.index_schema_version:
        return False, "schema_mismatch"
    if stored.get("repository_id") != current.repository_id:
        return False, "repository_identity_changed"
    if stored.get("worktree_id") != current.worktree_id:
        return False, "worktree_mismatch"
    return True, "ok"
