"""Approved-path discovery for repository indexing."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator

from saathi.codebase_memory.policy import (
    Limits,
    default_limits,
    path_exclusion_reason,
    should_exclude_dir,
)


def file_hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_hash_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 64)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def discover_files(
    root: Path,
    *,
    limits: Limits | None = None,
    max_files: int | None = None,
) -> Iterator[tuple[str, Path, str | None]]:
    """Yield (rel_posix, abs_path, exclusion_reason|None).

    exclusion_reason set means file must not be indexed (but is reported).
    """
    limits = limits or default_limits()
    root = root.resolve()
    count = 0
    cap = max_files or 100_000

    for dirpath, dirnames, filenames in __import__("os").walk(root):
        # prune excluded dirs in-place
        dirnames[:] = [
            d for d in dirnames
            if not should_exclude_dir(d) and d not in (".git",)
        ]
        # skip nested git repositories (separate projects)
        nested = []
        for d in list(dirnames):
            if (Path(dirpath) / d / ".git").exists() and Path(dirpath) != root:
                nested.append(d)
        for d in nested:
            dirnames.remove(d)

        for name in filenames:
            abs_p = Path(dirpath) / name
            try:
                rel = abs_p.resolve().relative_to(root).as_posix()
            except ValueError:
                continue  # symlink escape
            # symlink outside root already blocked by relative_to
            reason = path_exclusion_reason(rel, root=root)
            if reason:
                yield rel, abs_p, reason
                continue
            try:
                if not abs_p.is_file() or abs_p.is_symlink() and not abs_p.exists():
                    continue
                # allow symlinks only if they resolve inside root
                if abs_p.is_symlink():
                    resolved = abs_p.resolve()
                    try:
                        resolved.relative_to(root)
                    except ValueError:
                        yield rel, abs_p, "symlink_escape"
                        continue
                size = abs_p.stat().st_size
                if size > limits.max_file_bytes:
                    yield rel, abs_p, f"oversized:{size}"
                    continue
                if size == 0:
                    yield rel, abs_p, "empty"
                    continue
            except OSError:
                yield rel, abs_p, "stat_error"
                continue
            yield rel, abs_p, None
            count += 1
            if count >= cap:
                return
