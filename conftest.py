"""Repository-root pytest configuration.

Sole responsibility: prove that the `saathi` package under test is the one in
THIS checkout.

Why this exists
---------------
SaathiOS is developed across many git worktrees. A `pip install -e .` performed
from one worktree registers a global import finder that resolves `saathi` to
that worktree's source from any interpreter sharing those site-packages. The
result is silent: `pytest` run inside worktree B imports worktree A's code and
reports a green suite that describes neither checkout. Browser certification
inherits the same failure — a certificate can be produced from a frontend and a
backend belonging to different commits, with nothing in the evidence recording
it.

The guard turns that silent misroute into a loud collection-time error.

It also has a deliberate side effect: because this file sits at the repository
root and that directory has no ``__init__.py``, pytest prepends the repository
root to ``sys.path``. That makes the ``pytest`` console script resolve `saathi`
the same way ``python -m pytest`` already does, closing the last invocation
style that could differ.
"""
from __future__ import annotations

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent


def _assert_saathi_is_local() -> None:
    import saathi

    origin = getattr(saathi, "__file__", None)
    if origin is None:  # namespace package — no single source of truth
        raise RuntimeError(
            "SAATHI_IMPORT_GUARD: `saathi` imported as a namespace package with no "
            f"__file__. Expected a real package under {REPO_ROOT}. "
            "Fix: create a checkout-local venv and `pip install -e .` inside it."
        )

    resolved = pathlib.Path(origin).resolve()
    try:
        resolved.relative_to(REPO_ROOT)
    except ValueError:
        raise RuntimeError(
            "SAATHI_IMPORT_GUARD: refusing to run — the test session would have "
            "exercised a different checkout than the one it lives in.\n"
            f"  this repository : {REPO_ROOT}\n"
            f"  `saathi` resolved to: {resolved}\n"
            "\n"
            "Cause: a `pip install -e .` from another worktree is registered in "
            "the active interpreter's site-packages, so `import saathi` is routed "
            "away from this checkout.\n"
            "\n"
            "Fix:\n"
            "  1. Find the stray install:  python -m pip show saathiai\n"
            "  2. Remove it:               python -m pip uninstall saathiai\n"
            "  3. Create a checkout-local venv and reinstall inside it:\n"
            f"       cd {REPO_ROOT} && python3 -m venv --system-site-packages .venv\n"
            "       ./.venv/bin/python -m pip install --no-deps -e .\n"
            "  4. Run tests with that interpreter."
        ) from None


_assert_saathi_is_local()


# ── test isolation: never touch the operator's real ~/.saathi/security.db ────
#
# `SecurityStore()` with no explicit path defaults to ``~/.saathi/security.db``.
# Several code paths (audit emit in particular) construct one per call, so an
# unfiltered test session opens dozens of connections against one shared,
# real-home database. That is both a correctness hazard (tests mutating the
# developer's live security store) and the cause of a hard suite hang: two
# threads in `test_25_concurrent_claims_one_winner` block forever in
# `SecurityStore.__init__` executing schema DDL while another test's connection
# holds the lock.
#
# Redirecting the default to a per-session temporary file removes both problems
# without changing any production default: `SAATHI_SECURITY_DB` is only consulted
# when no explicit path is passed.
import os as _os
import tempfile as _tempfile

if not _os.environ.get("SAATHI_SECURITY_DB"):
    _os.environ["SAATHI_SECURITY_DB"] = _os.path.join(
        _tempfile.mkdtemp(prefix="saathi-test-security-"), "security.db"
    )
