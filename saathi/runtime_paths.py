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
"""
from __future__ import annotations

import os
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

RUNTIME_STATE_ENV = "SAATHI_RUNTIME_STATE_DIR"

DEFAULT_RUNTIME_DIRNAME = ".runtime"


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
