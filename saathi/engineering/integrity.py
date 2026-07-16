"""M20.4 — Repository integrity snapshots for supervised engineering sessions.

Detects mutations without performing destructive rollback.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class RepoSnapshot:
    """Bounded integrity representation (not a full tree hash of everything)."""

    head: str = ""
    branch: str = ""
    status_porcelain: str = ""
    tracked_digest: str = ""  # hash of name+oid pairs from git ls-files -s
    untracked: list[str] = field(default_factory=list)
    index_digest: str = ""
    captured_at: float = field(default_factory=time.time)
    root: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RepoSnapshot":
        return cls(
            head=str(d.get("head") or ""),
            branch=str(d.get("branch") or ""),
            status_porcelain=str(d.get("status_porcelain") or ""),
            tracked_digest=str(d.get("tracked_digest") or ""),
            untracked=list(d.get("untracked") or []),
            index_digest=str(d.get("index_digest") or ""),
            captured_at=float(d.get("captured_at") or 0),
            root=str(d.get("root") or ""),
        )


@dataclass
class IntegrityDiff:
    ok: bool
    mutations: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _git(root: Path, *args: str, timeout: int = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 1, str(e)


def capture_snapshot(root: Path | str, *, max_untracked: int = 200) -> RepoSnapshot:
    root = Path(root).resolve()
    rc_h, head = _git(root, "rev-parse", "HEAD")
    head = head.strip().splitlines()[0] if rc_h == 0 else ""
    rc_b, branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    branch = branch.strip().splitlines()[0] if rc_b == 0 else ""
    _, status = _git(root, "status", "--porcelain=v1")
    rc_ls, ls_out = _git(root, "ls-files", "-s")
    tracked_digest = (
        "sha256:" + hashlib.sha256(ls_out.encode("utf-8", errors="replace")).hexdigest()
        if rc_ls == 0
        else ""
    )
    # index file hash if present
    index_path = root / ".git" / "index"
    index_digest = ""
    if index_path.is_file():
        try:
            index_digest = "sha256:" + hashlib.sha256(index_path.read_bytes()).hexdigest()
        except Exception:
            index_digest = "unreadable"
    untracked: list[str] = []
    for line in status.splitlines():
        if line.startswith("?? "):
            untracked.append(line[3:].strip())
            if len(untracked) >= max_untracked:
                break
    return RepoSnapshot(
        head=head,
        branch=branch,
        status_porcelain=status,
        tracked_digest=tracked_digest,
        untracked=untracked,
        index_digest=index_digest,
        root=str(root),
    )


def compare_snapshots(before: RepoSnapshot, after: RepoSnapshot) -> IntegrityDiff:
    mutations: list[str] = []
    details: dict[str, Any] = {}
    if before.head != after.head:
        mutations.append("head_changed")
        details["head"] = {"before": before.head, "after": after.head}
    if before.branch != after.branch:
        mutations.append("branch_changed")
        details["branch"] = {"before": before.branch, "after": after.branch}
    if before.tracked_digest != after.tracked_digest:
        mutations.append("tracked_files_changed")
    if before.index_digest != after.index_digest:
        mutations.append("index_mutated")
    if before.status_porcelain != after.status_porcelain:
        # finer: new untracked / deleted markers
        b_un = set(before.untracked)
        a_un = set(after.untracked)
        if a_un - b_un:
            mutations.append("new_untracked_files")
            details["new_untracked"] = sorted(a_un - b_un)[:50]
        if b_un - a_un:
            mutations.append("untracked_removed")
        # any porcelain change not only untracked
        if "new_untracked_files" not in mutations or before.status_porcelain.strip() != after.status_porcelain.strip():
            # Detect tracked modifications via status lines not starting with ??
            def _tracked_lines(s: str) -> set[str]:
                return {ln for ln in s.splitlines() if ln and not ln.startswith("??")}

            if _tracked_lines(before.status_porcelain) != _tracked_lines(after.status_porcelain):
                if "tracked_files_changed" not in mutations:
                    mutations.append("tracked_status_changed")
    # de-dupe preserve order
    seen = set()
    uniq = []
    for m in mutations:
        if m not in seen:
            seen.add(m)
            uniq.append(m)
    return IntegrityDiff(ok=len(uniq) == 0, mutations=uniq, details=details)


def verify_unchanged(root: Path | str, baseline: RepoSnapshot) -> IntegrityDiff:
    return compare_snapshots(baseline, capture_snapshot(root))


# Forbidden operations in read-only mode (code-enforced denylist)
READONLY_FORBIDDEN_OPS = frozenset({
    "write_file",
    "create_file",
    "delete_file",
    "rename_file",
    "chmod",
    "git_add",
    "git_commit",
    "git_push",
    "git_merge",
    "git_rebase",
    "git_reset",
    "git_checkout",
    "apply_patch",
    "package_install",
    "deploy",
    "db_mutate",
    "secret_mutate",
    "trade",
})


def forbid_readonly_operation(op: str) -> tuple[bool, str]:
    """Return (allowed, reason)."""
    key = (op or "").strip().lower()
    if key in READONLY_FORBIDDEN_OPS:
        return False, f"readonly_forbidden:{key}"
    # pattern denials
    for bad in (
        "commit", "push", "merge", "rebase", "checkout", "reset",
        "pip install", "npm install", "deploy", "place_order",
    ):
        if bad in key:
            return False, f"readonly_forbidden_pattern:{bad}"
    return True, "ok"
