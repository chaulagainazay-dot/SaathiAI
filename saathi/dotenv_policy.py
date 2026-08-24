"""Where — and whether — a ``.env`` file is read and written.

``saathi.config`` used to call ``load_dotenv(<repo>/.env)`` unconditionally. An
isolated validation run therefore inherited whatever the operator happened to
keep in the checkout's ``.env``, and two password endpoints wrote a plaintext
credential back into that same worktree file. Neither is acceptable while a run
is supposed to be contained, and neither was controllable.

Two variables make it explicit:

  ``SAATHI_DOTENV_PATH``  load (and write) only this absolute file.
  ``SAATHI_LOAD_DOTENV``  ``false``/``0``/``no``/``off`` disables dotenv entirely.

With neither set the historical ``<repo>/.env`` is used, so production and
developer checkouts behave exactly as before.

Rules that hold in every mode:

* the process environment is authoritative — dotenv never overrides a variable
  that is already set;
* an explicit path must be absolute;
* an explicit path that does not exist is a **documented non-load**, never a
  silent fall back to the worktree file;
* when loading is disabled no ``.env`` is opened at all, not even to test for
  its existence;
* no value from the environment or the file is returned, printed or logged —
  callers get paths and reasons, never contents.
"""
from __future__ import annotations

import os
import pathlib
import tempfile

from .runtime_paths import REPO_ROOT

DOTENV_PATH_ENV = "SAATHI_DOTENV_PATH"
DOTENV_ENABLED_ENV = "SAATHI_LOAD_DOTENV"

HISTORICAL_DOTENV = REPO_ROOT / ".env"

_FALSEY = {"false", "0", "no", "off"}


class DotenvPolicyError(ValueError):
    """The dotenv configuration is unusable, or a write was refused.

    Raised instead of silently retargeting: a run that is told to stay out of
    the worktree must fail loudly rather than persist there anyway.
    """


def dotenv_enabled() -> bool:
    """False when ``SAATHI_LOAD_DOTENV`` names a falsey value."""
    return (os.getenv(DOTENV_ENABLED_ENV) or "").strip().lower() not in _FALSEY


def dotenv_target() -> pathlib.Path | None:
    """The single file this process may read or write, or ``None`` when disabled.

    Returns a path whether or not it exists; existence is the caller's concern,
    because a reader treats "missing" as a non-load while a writer creates it.
    """
    if not dotenv_enabled():
        return None
    explicit = (os.getenv(DOTENV_PATH_ENV) or "").strip()
    if explicit:
        candidate = pathlib.Path(explicit).expanduser()
        if not candidate.is_absolute():
            raise DotenvPolicyError(
                f"{DOTENV_PATH_ENV} must be an absolute path, got a relative one "
                f"({len(explicit)} chars)"
            )
        return pathlib.Path(os.path.normpath(candidate))
    return HISTORICAL_DOTENV


def apply_dotenv() -> dict[str, object]:
    """Load the configured dotenv file, if there is one, and report what happened.

    The result carries paths and a reason only — never a key's value, and never
    the set of keys, which for this file is itself a credential inventory.
    """
    if not dotenv_enabled():
        return {"loaded": False, "path": None, "reason": "disabled"}

    target = dotenv_target()
    if target is None:                                   # defensive; disabled above
        return {"loaded": False, "path": None, "reason": "disabled"}

    explicit = bool((os.getenv(DOTENV_PATH_ENV) or "").strip())
    if not target.exists():
        return {
            "loaded": False,
            "path": str(target),
            # An explicit path that is missing must not fall back to the
            # worktree file; saying so here is the documented outcome.
            "reason": "explicit_path_missing" if explicit else "default_path_missing",
        }

    from dotenv import load_dotenv

    # override=False keeps the process environment authoritative.
    load_dotenv(target, override=False)
    return {"loaded": True, "path": str(target), "reason": "explicit" if explicit else "default"}


def _render(existing: str, updates: dict[str, str]) -> str:
    """Apply ``updates`` to ``existing`` text, leaving every other line alone.

    Unrelated keys, comments and blank lines survive byte for byte; only the
    assignments named in ``updates`` are rewritten, in place, and keys that were
    absent are appended.
    """
    lines = existing.splitlines()
    remaining = dict(updates)
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    for key, value in remaining.items():
        out.append(f"{key}={value}")
    return "\n".join(out) + "\n" if out else ""


def write_dotenv_values(updates: dict[str, str]) -> pathlib.Path:
    """Persist ``updates`` into the configured dotenv file, atomically.

    Refuses with :class:`DotenvPolicyError` when dotenv is disabled — a run that
    opted out of dotenv has nowhere legitimate to persist a credential, and
    writing to the worktree anyway is the exact escape this module exists to
    stop. The file is replaced through a temporary file in the same directory so
    a crash cannot leave it truncated, and it is left readable only by its
    owner.
    """
    target = dotenv_target()
    if target is None:
        raise DotenvPolicyError(
            f"dotenv persistence is disabled by {DOTENV_ENABLED_ENV}; refusing to write"
        )

    existing = target.read_text() if target.exists() else ""
    text = _render(existing, updates)

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        # A new file must not be world-readable; an existing one keeps its mode,
        # because tightening it here would be an unrelated change to the host.
        os.chmod(tmp_name, target.stat().st_mode & 0o7777 if target.exists() else 0o600)
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return target
