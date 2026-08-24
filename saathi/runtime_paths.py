"""Where runtime state is allowed to be written.

`docs/evidence/` holds committed certification records. Several runtime
components were appending live logs into those same directories, so ordinary
operation — including importing a module during a test run — permanently
modified checked-in evidence. The practical symptom is a working tree that goes
dirty by itself, which trains everyone to ignore `git status` on exactly the
files where a real change matters most.

The split this module enforces:

  docs/evidence/**   immutable historical records. Written only by a deliberate
                     certification run, and committed as the output of that run.
  runtime state dir  everything a running process produces as it goes: event
                     logs, incident ledgers, per-request evidence blobs.

`SAATHI_RUNTIME_STATE_DIR` relocates the runtime side — a test that wants full
isolation, or a deployment with a read-only checkout, points it elsewhere.
Otherwise it is `<repository>/.runtime/`, which is git-ignored.

Historical evidence is never deleted or rewritten by this change; the runtime
simply stops appending to it.

Persistent user state is the second half of the same problem. Legacy SaathiOS
stores each hardcoded ``Path.home() / ".saathi" / <name>``, so a test run, a
validation harness or a second checkout all wrote into the operator's real
databases and keys. ``SAATHI_STATE_ROOT`` relocates that whole tree at once.

Resolution precedence, highest first:

  1. an explicit path passed to the constructor or function
  2. an existing store-specific variable (``SAATHI_PLATFORM_DB``,
     ``SAATHI_VOICE_ARTIFACT_DIR``, ``SAATHI_CBM_INDEX_DIR``, ...)
  3. ``SAATHI_STATE_ROOT``
  4. the historical default ``~/.saathi``

Unset behaves exactly as before, so this is inert in production. The root is
resolved on every call rather than frozen into a module constant, because a
constant captured at import time cannot be redirected by a test that sets the
variable after the first import anywhere in the process. Nothing here creates a
directory: a store creates its own on first write, with its own permissions.
"""
from __future__ import annotations

import os
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

RUNTIME_STATE_ENV = "SAATHI_RUNTIME_STATE_DIR"

DEFAULT_RUNTIME_DIRNAME = ".runtime"

STATE_ROOT_ENV = "SAATHI_STATE_ROOT"

DEFAULT_STATE_DIRNAME = ".saathi"

LEGACY_DB_ENV = "SAATHI_LEGACY_DB"


class StateRootError(ValueError):
    """``SAATHI_STATE_ROOT`` is set to something unusable.

    Raised instead of silently falling back, because a validation run that
    quietly reverts to ``~/.saathi`` writes the operator's real state while
    reporting that it is isolated.
    """


def _ensure(path: pathlib.Path) -> pathlib.Path:
    """Create the directory if possible; never raise.

    A read-only checkout must still be importable. Callers write through their
    own error handling, so a failure here surfaces at the write, not at import.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return path


def runtime_state_dir() -> pathlib.Path:
    """Root for all mutable local state. Created on demand."""
    override = (os.getenv(RUNTIME_STATE_ENV) or "").strip()
    path = pathlib.Path(override) if override else REPO_ROOT / DEFAULT_RUNTIME_DIRNAME
    return _ensure(path)


def runtime_evidence_dir(milestone: str) -> pathlib.Path:
    """Runtime-log counterpart of ``docs/evidence/<milestone>``.

    Same shape as the committed tree so an operator reading a runtime log knows
    which milestone's contract produced it — without the runtime being able to
    touch the committed record.
    """
    return _ensure(runtime_state_dir() / "evidence" / milestone)


def committed_evidence_dir(milestone: str) -> pathlib.Path:
    """Read-side path for the committed historical record. Do not write here."""
    return REPO_ROOT / "docs" / "evidence" / milestone


def state_root() -> pathlib.Path:
    """Root for persistent user state. Not created here.

    Unset (or blank, matching ``runtime_state_dir``'s treatment of a cleared
    variable) keeps the historical ``~/.saathi``. An explicit value must be
    absolute: a relative root would resolve against whatever working directory
    the process happened to start in, which is exactly the ambiguity an
    isolation run is trying to remove.
    """
    override = (os.getenv(STATE_ROOT_ENV) or "").strip()
    if not override:
        return pathlib.Path.home() / DEFAULT_STATE_DIRNAME
    candidate = pathlib.Path(override).expanduser()
    if not candidate.is_absolute():
        raise StateRootError(
            f"{STATE_ROOT_ENV} must be an absolute path, got a relative one "
            f"({len(override)} chars)"
        )
    # normpath, not resolve(): collapse `..` and duplicate separators without
    # dereferencing symlinks or touching the filesystem.
    return pathlib.Path(os.path.normpath(candidate))


def state_path(name: str | pathlib.PathLike[str]) -> pathlib.Path:
    """Resolve one store beneath :func:`state_root`. Not created here.

    ``name`` is the historical basename under ``~/.saathi`` — ``"evidence.db"``,
    ``"codebase_memory"``. It stays relative and inside the root so a caller
    cannot walk back out of an isolated tree.
    """
    rel = pathlib.PurePath(name)
    if rel.is_absolute():
        raise StateRootError(f"state_path() takes a name relative to {STATE_ROOT_ENV}, not an absolute path")
    if not rel.parts or ".." in rel.parts:
        raise StateRootError("state_path() name must be a non-empty path without '..' segments")
    return state_root().joinpath(rel)


def scoped_state_path(
    relative: str | pathlib.PathLike[str],
    *,
    env: str | None = None,
    historical: pathlib.Path,
) -> pathlib.Path:
    """Resolve a store that historically lived in the repository, not in ``~/.saathi``.

    :func:`state_path` is wrong for these: its unset default is ``~/.saathi``,
    and silently relocating ``<repo>/data/baadar.db`` there would change
    production behaviour. This keeps the historical location when no isolation
    is configured, and moves the store under the root only when one is.

    Precedence, highest first:

      1. an explicit argument at the call site (the caller's job, not this one)
      2. ``env``, when that variable names an absolute path
      3. ``SAATHI_STATE_ROOT`` / ``relative``
      4. ``historical``

    Once ``SAATHI_STATE_ROOT`` is set there is deliberately no fall-through to
    ``historical``: a validation run that quietly wrote back into the checkout
    would report isolation it does not have. Nothing is created here.
    """
    if env:
        override = (os.getenv(env) or "").strip()
        if override:
            candidate = pathlib.Path(override).expanduser()
            if not candidate.is_absolute():
                raise StateRootError(
                    f"{env} must be an absolute path, got a relative one "
                    f"({len(override)} chars)"
                )
            return pathlib.Path(os.path.normpath(candidate))
    if (os.getenv(STATE_ROOT_ENV) or "").strip():
        return state_path(relative)
    return historical


# ── concrete repo-local stores ───────────────────────────────────────────────
# Defined here, once, so that every reader and writer of a given store resolves
# the identical path. These were previously computed independently at three
# different call sites, which is exactly how a reader and a writer drift apart.

def baadar_db_path() -> pathlib.Path:
    """Baadar content/intelligence/referral database."""
    return scoped_state_path(
        "data/baadar.db",
        env="BAADAR_DB",
        historical=REPO_ROOT / "data" / "baadar.db",
    )


def projects_registry_path() -> pathlib.Path:
    """Registry of the working projects Baadar knows by name."""
    return scoped_state_path(
        "data/projects.json",
        env="SAATHI_PROJECTS_FILE",
        historical=REPO_ROOT / "data" / "projects.json",
    )


def storage_root_path() -> pathlib.Path:
    """Root of the managed media/artifact store."""
    return scoped_state_path(
        "storage",
        env="SAATHI_STORAGE_ROOT",
        historical=REPO_ROOT / "storage",
    )


def legacy_db_path(explicit: str | pathlib.PathLike[str] | None = None) -> pathlib.Path:
    """The legacy ``saathi.db`` store — conversation turns, facts, feedback, Nepali.

    ``saathi.config`` used to bind this to ``<repo>/data/saathi.db`` at import
    time. Four modules connected to it while being imported, so a backend booted
    with an isolated ``SAATHI_STATE_ROOT`` still held read-write descriptors on a
    database inside the git worktree, and ran ``CREATE TABLE`` DDL against it.
    That is a containment escape: the isolation was reported but not held.

    Precedence, highest first:

      1. ``explicit`` — a path passed by the caller
      2. ``SAATHI_LEGACY_DB``
      3. ``SAATHI_STATE_ROOT/data/saathi.db``
      4. the historical ``<repo>/data/saathi.db``

    Once ``SAATHI_STATE_ROOT`` is set there is no fall-through to the repository
    database. With neither variable set the historical path is returned
    unchanged, so production behaviour is untouched. Nothing is created here,
    and nothing is migrated or copied between roots.
    """
    if explicit is not None:
        candidate = pathlib.Path(explicit).expanduser()
        if not candidate.is_absolute():
            raise StateRootError(
                f"an explicit legacy database path must be absolute, got a "
                f"relative one ({len(str(explicit))} chars)"
            )
        return pathlib.Path(os.path.normpath(candidate))
    return scoped_state_path(
        "data/saathi.db",
        env=LEGACY_DB_ENV,
        historical=REPO_ROOT / "data" / "saathi.db",
    )


def storage_db_path(root: pathlib.Path | None = None) -> pathlib.Path:
    """Ledger for the managed store, alongside the files it describes."""
    override = (os.getenv("SAATHI_STORAGE_DB") or "").strip()
    if override:
        candidate = pathlib.Path(override).expanduser()
        if not candidate.is_absolute():
            raise StateRootError(
                f"SAATHI_STORAGE_DB must be an absolute path, got a relative one "
                f"({len(override)} chars)"
            )
        return pathlib.Path(os.path.normpath(candidate))
    return (pathlib.Path(root) if root is not None else storage_root_path()) / "storage.db"
