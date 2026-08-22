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
