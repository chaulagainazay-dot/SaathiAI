"""Live-file verification and freshness states."""
from __future__ import annotations

import hashlib
from enum import Enum
from pathlib import Path
from typing import Any

from saathi.codebase_memory.identity import RepoIdentity


class Freshness(str, Enum):
    CURRENT_WORKTREE = "CURRENT_WORKTREE"
    CURRENT_COMMIT = "CURRENT_COMMIT"
    HISTORICAL = "HISTORICAL"
    STALE_INDEX = "STALE_INDEX"
    DELETED_SOURCE = "DELETED_SOURCE"
    UNKNOWN = "UNKNOWN"


def hash_file(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            while True:
                b = f.read(65536)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except OSError:
        return None


def verify_result(
    *,
    root: Path,
    path: str,
    indexed_hash: str,
    indexed_commit: str,
    identity: RepoIdentity,
    historical: bool = False,
) -> dict[str, Any]:
    abs_p = (root / path).resolve()
    try:
        abs_p.relative_to(root.resolve())
    except ValueError:
        return {
            "freshness": Freshness.UNKNOWN.value,
            "warning": "path_escape",
            "live_exists": False,
            "hash_match": False,
        }
    if not abs_p.is_file():
        return {
            "freshness": Freshness.DELETED_SOURCE.value,
            "warning": "source_file_missing",
            "live_exists": False,
            "hash_match": False,
        }
    live = hash_file(abs_p)
    hash_match = bool(live and live == indexed_hash)
    if historical:
        return {
            "freshness": Freshness.HISTORICAL.value,
            "warning": "historical_mode" if not hash_match else "",
            "live_exists": True,
            "hash_match": hash_match,
            "live_hash": (live or "")[:16],
        }
    if indexed_commit and indexed_commit != identity.commit_sha and not hash_match:
        return {
            "freshness": Freshness.STALE_INDEX.value,
            "warning": "index_commit_or_hash_mismatch",
            "live_exists": True,
            "hash_match": False,
            "live_hash": (live or "")[:16],
        }
    if hash_match:
        if identity.dirty_worktree:
            return {
                "freshness": Freshness.CURRENT_WORKTREE.value,
                "warning": "",
                "live_exists": True,
                "hash_match": True,
            }
        return {
            "freshness": Freshness.CURRENT_COMMIT.value,
            "warning": "",
            "live_exists": True,
            "hash_match": True,
        }
    # file changed since index
    return {
        "freshness": Freshness.STALE_INDEX.value,
        "warning": "live_hash_differs_prefer_live_file",
        "live_exists": True,
        "hash_match": False,
        "live_hash": (live or "")[:16],
    }
