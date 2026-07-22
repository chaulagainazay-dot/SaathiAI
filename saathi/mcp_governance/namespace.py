"""Deterministic project namespace isolation for codebase-memory MCP.

One project must not search another by default. Paths are normalized safely;
symlink / ``..`` traversal that escapes a bound root is rejected.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

# Known SaathiOS multi-project map (deterministic ids)
KNOWN_PROJECTS: dict[str, str] = {
    "saathiai": "saathiai",
    "saathi": "saathiai",
    "ieltsalert": "ieltsalert",
    "ielts-practice-app": "ieltsalert",
    "cafeteria": "cafeteria",
    "hcgms": "cafeteria",
    "canteen": "cafeteria",
    "travel-client": "travel-client",
    "surmount": "travel-client",
}

_NS_SAFE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class NamespaceError(ValueError):
    """Raised when a namespace is invalid or crosses project boundaries."""


def normalize_project_root(path: str | Path) -> Path:
    """Resolve *path* to an absolute real path without following unrelated roots.

    Rejects empty paths. Uses ``resolve()`` so ``..`` and symlinks collapse;
    callers must still assert the result stays inside an allowed bound.
    """
    if path is None or str(path).strip() == "":
        raise NamespaceError("empty project root")
    p = Path(str(path)).expanduser()
    try:
        resolved = p.resolve(strict=False)
    except (OSError, RuntimeError) as e:
        raise NamespaceError(f"cannot resolve project root: {e}") from e
    if ".." in p.parts:
        # After resolve, .. should be gone; if the *input* tried traversal
        # outside a bound, assert_namespace_bound will catch it.
        pass
    return resolved


def project_namespace(project_root: str | Path, *, alias: str | None = None) -> str:
    """Return a deterministic namespace id for a repository root.

    Prefer known project aliases when the directory name matches; otherwise
    use ``proj_<12-hex-of-realpath>`` so unrelated paths never collide.
    """
    root = normalize_project_root(project_root)
    name = root.name.lower().replace(" ", "-")
    if alias:
        key = alias.lower().strip()
        if key in KNOWN_PROJECTS:
            return KNOWN_PROJECTS[key]
        if _NS_SAFE.match(key):
            return key
        raise NamespaceError(f"invalid namespace alias: {alias!r}")
    if name in KNOWN_PROJECTS:
        return KNOWN_PROJECTS[name]
    # Hash of real path → stable id across renames only if path identical
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:12]
    return f"proj_{digest}"


def assert_namespace_bound(
    requested_ns: str,
    *,
    bound_ns: str,
    project_root: str | Path | None = None,
    candidate_path: str | Path | None = None,
) -> str:
    """Ensure *requested_ns* matches the bound project namespace.

    Optionally verify *candidate_path* does not escape *project_root*.
    Returns the bound namespace on success.
    """
    if not requested_ns or not isinstance(requested_ns, str):
        raise NamespaceError("namespace required")
    ns = requested_ns.strip().lower()
    bound = (bound_ns or "").strip().lower()
    if not bound:
        raise NamespaceError("bound namespace required")
    if ns != bound:
        raise NamespaceError(
            f"namespace violation: requested={ns!r} bound={bound!r}"
        )
    if not _NS_SAFE.match(ns) and not ns.startswith("proj_"):
        raise NamespaceError(f"malformed namespace: {ns!r}")

    if candidate_path is not None and project_root is not None:
        root = normalize_project_root(project_root)
        cand = Path(str(candidate_path)).expanduser()
        try:
            cand_res = cand.resolve(strict=False)
        except (OSError, RuntimeError) as e:
            raise NamespaceError(f"path resolve failed: {e}") from e
        try:
            cand_res.relative_to(root)
        except ValueError as e:
            raise NamespaceError(
                f"path escapes project root: {cand_res} not under {root}"
            ) from e
        # Reject null bytes / odd separators after normalization
        if "\x00" in str(candidate_path):
            raise NamespaceError("null byte in path")
    return bound


def parse_namespace_query(raw: str) -> str:
    """Normalize a caller-supplied namespace; reject traversal tokens."""
    if raw is None:
        raise NamespaceError("namespace required")
    s = str(raw).strip().lower()
    if not s:
        raise NamespaceError("empty namespace")
    if ".." in s or "/" in s or "\\" in s or s.startswith("."):
        raise NamespaceError(f"namespace traversal rejected: {raw!r}")
    if not (_NS_SAFE.match(s) or s.startswith("proj_")):
        raise NamespaceError(f"invalid namespace: {raw!r}")
    return s
