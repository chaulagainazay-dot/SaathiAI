"""Rollback manager — creates a safe restore point before any code edit.

Never stashes, resets, or discards unrelated work. It records the current
HEAD as the rollback reference and refuses to run auto-repair if unrelated
uncommitted work is present that the incident did not authorize.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(ROOT), capture_output=True, text=True, timeout=30
    )


@dataclass
class RollbackPoint:
    incident_id: str
    branch: str
    head: str
    dirty_files: list[str] = field(default_factory=list)
    repair_branch: str = ""
    created: bool = False
    refused_reason: str = ""

    @property
    def ok(self) -> bool:
        return self.created and not self.refused_reason


def current_head() -> str:
    return _git("rev-parse", "HEAD").stdout.strip()


def current_branch() -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def dirty_files() -> list[str]:
    out = _git("status", "--short").stdout
    return [ln[3:] for ln in out.splitlines() if ln.strip()]


def create_rollback_point(incident_id: str, *,
                          allow_dirty: list[str] | None = None) -> RollbackPoint:
    """Record HEAD as the rollback ref. Refuse if unrelated dirty work exists.

    `allow_dirty` lists paths the repair itself is expected to touch (e.g. the
    repair-history file). Any OTHER dirty file blocks the auto-repair so we
    never silently overwrite the user's in-flight work.
    """
    branch = current_branch()
    head = current_head()
    allow = set(allow_dirty or [])
    dirty = dirty_files()
    unrelated = [f for f in dirty if f not in allow]

    rp = RollbackPoint(incident_id=incident_id, branch=branch, head=head,
                       dirty_files=dirty)
    if unrelated:
        rp.refused_reason = (
            f"unrelated uncommitted work present ({len(unrelated)} file(s)); "
            "commit or stash it first — auto-repair will not overwrite it"
        )
        return rp

    # The rollback reference is simply the current HEAD commit. Restoring means
    # `git reset --hard <head>` (done only via the explicit rollback command,
    # never automatically). We also record it as a lightweight tag-free ref.
    rp.repair_branch = f"repair/auto-{incident_id}"
    rp.created = True
    return rp


def rollback_to(head: str) -> bool:
    """Explicit, operator-invoked restore. Hard-resets working tree to `head`.

    Only reachable via `saathi repair rollback <id>` — never from the auto loop.
    """
    res = _git("reset", "--hard", head)
    return res.returncode == 0
