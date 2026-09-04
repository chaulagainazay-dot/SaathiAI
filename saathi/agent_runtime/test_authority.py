"""Test-only authority reachability (Phase 10 certification fixture).

The Authority Centre has to be certified against a real `awaiting_approval`
run carrying a real `approval_request`. The repository already contains the
authoritative path -- the orchestrator's approval gate refuses to start a task
whose agent declares `requires_approval`, records an approval request and moves
the run to AWAITING_APPROVAL -- but no production strategy includes the only
agent that declares it (`executor`), so the state is unreachable over HTTP.

This module closes that gap without weakening anything: it makes one strategy
available that routes through the *real* gate. Nothing here creates an approval,
sets a run state, or resolves anything; the orchestrator and store do all of it.

Gated exactly like the Phase 5F/7 fixtures, and gated at *selection* rather than
at behaviour, because merely running this strategy creates authority state:

* disabled unless ``SAATHI_TEST_AUTHORITY`` is truthy, checked first;
* usable only when requested by exact name, never by objective heuristics;
* refused outright when not armed, so an accidental request cannot reach the
  approval gate in a production process.

The approval it produces is genuine and unresolved. It grants nothing, and no
task runs: the gate returns before any work, which is the property the browser
certification checks.
"""
from __future__ import annotations

import os

AUTHORITY_ENV = "SAATHI_TEST_AUTHORITY"

#: Strategy that reaches the real approval gate. Absent from objective-based
#: selection in ``strategies.choose_strategy``.
TEST_APPROVAL_STRATEGY = "test_approval"

#: Every strategy this module gates. Requesting one while disarmed is refused.
GATED_STRATEGIES: tuple[str, ...] = (TEST_APPROVAL_STRATEGY,)

_TRUTHY = {"1", "true", "yes", "on"}


def fixture_enabled() -> bool:
    """Whether authority-reachability fixtures are armed for this process."""
    return (os.environ.get(AUTHORITY_ENV) or "").strip().lower() in _TRUTHY


def is_gated_strategy(strategy: str) -> bool:
    return (strategy or "") in GATED_STRATEGIES


def strategy_allowed(strategy: str) -> bool:
    """False only for a gated strategy in a process that has not armed them.

    Returns True for every production strategy, armed or not, so the gate can
    never affect normal work.
    """
    if not is_gated_strategy(strategy):
        return True
    return fixture_enabled()
