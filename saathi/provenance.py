"""Runtime provenance — which checkout is actually serving this request.

SaathiOS is developed across many git worktrees. A browser certificate produced
against a frontend from one commit and a backend from another looks identical to
a real one, because nothing in the evidence records where either half came from.
The import guard in the repository-root ``conftest.py`` closes that hole for the
Python test session; this module closes it for the running server, so a
certification harness can *prove* which code answered it rather than assuming.

What is exposed is deliberately split by environment:

* everywhere — build identity: commit SHA, branch, dirty flag, repository name.
* local / development / test only — filesystem identity: the worktree path and
  the resolved ``saathi`` package path.

Absolute paths name a developer's home directory and the layout of their
machine, which is host information a production service has no reason to
publish. Build identity is not secret and is the part a certificate needs.

Nothing here reads configuration, credentials, or request state.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
from typing import Any

from .cors_policy import _PROD_ENVS, resolve_environment

SCHEMA = "saathi.runtime_provenance.v1"

#: Root of the checkout this module was imported from.
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Resolved location of the ``saathi`` package serving this process.
PACKAGE_PATH = pathlib.Path(__file__).resolve().parent

_UNKNOWN = "UNKNOWN"
_GIT_TIMEOUT_SECONDS = 5

_cache: dict[str, dict[str, Any]] = {}


def _git(*args: str) -> str:
    """Run a read-only git command in this checkout. Never raises."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _build_identity() -> dict[str, Any]:
    """Commit identity of the serving code.

    ``SAATHI_BUILD_SHA`` wins when set, for deployments built from an archive
    with no ``.git`` directory. Otherwise the working checkout answers.
    """
    env_sha = (os.getenv("SAATHI_BUILD_SHA") or "").strip()
    if env_sha:
        return {
            "backendSha": env_sha,
            "backendBranch": (os.getenv("SAATHI_BUILD_REF") or "").strip() or _UNKNOWN,
            "backendDirty": False,
            "shaSource": "env",
        }

    sha = _git("rev-parse", "HEAD")
    if not sha:
        return {
            "backendSha": _UNKNOWN,
            "backendBranch": _UNKNOWN,
            "backendDirty": False,
            "shaSource": "unavailable",
        }
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or _UNKNOWN
    return {
        "backendSha": sha,
        "backendBranch": branch,
        "backendDirty": bool(_git("status", "--porcelain")),
        "shaSource": "git",
    }


def exposes_local_paths(environment: str | None = None) -> bool:
    """Whether filesystem identity may be published in this environment."""
    return resolve_environment(environment) not in _PROD_ENVS


def runtime_provenance(environment: str | None = None) -> dict[str, Any]:
    """Non-secret identity of the code serving this process.

    Cached per environment: a running process cannot change its own commit, and
    a certification harness may ask repeatedly.
    """
    env = resolve_environment(environment)
    cached = _cache.get(env)
    if cached is not None:
        return dict(cached)

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "environment": env,
        "repository": REPO_ROOT.name,
        **_build_identity(),
    }
    if exposes_local_paths(env):
        payload["worktreePath"] = str(REPO_ROOT)
        payload["packagePath"] = str(PACKAGE_PATH)
        # Configuration identity is safe in local diagnostics and lets a
        # launcher validate a backend before lazy stores have opened files.
        payload["securityDbPath"] = os.getenv(
            "SAATHI_SECURITY_DB", str(pathlib.Path.home() / ".saathi" / "security.db")
        )
        payload["platformDbPath"] = os.getenv(
            "SAATHI_PLATFORM_DB", str(REPO_ROOT / "data" / "platform" / "platform.db")
        )
    else:
        payload["worktreePath"] = None
        payload["packagePath"] = None
        payload["securityDbPath"] = None
        payload["platformDbPath"] = None

    _cache[env] = dict(payload)
    return payload


def reset_cache() -> None:
    """Drop the memoized provenance. For tests that vary the environment."""
    _cache.clear()
