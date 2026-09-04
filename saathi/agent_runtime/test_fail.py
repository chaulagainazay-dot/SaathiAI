"""Test-only deterministic task failure (Phase 7 certification fixture).

"What needs you" must show a FAILED attention item, but a real run does not fail
on demand: with providers unavailable the agents still degrade gracefully and the
run completes. This fixture makes one task fail through the *production* failure
path -- the executor raises, the orchestrator records the failure and transitions
the run -- so the observation chain being certified (run.state = failed ->
attention read model -> panel) is the real one.

It is a certification fixture, never a production behaviour, and is gated exactly
like ``test_hold``:

* Disabled unless ``SAATHI_TEST_RUN_FAIL`` is set to a truthy value.
* Applies only to runs whose strategy is exactly ``test_fail``.
* Both gates must pass, and the environment variable is read first, so with it
  unset this returns before inspecting anything about the run.
* Grants no authority and fabricates none: FAILED is a TRUSTED_RUNTIME state, not
  an authoritative one. This fixture cannot produce an approval or a block.
* Touches no external system and writes nothing outside the run's own records.
"""
from __future__ import annotations

import os

FAIL_ENV = "SAATHI_TEST_RUN_FAIL"

#: Strategy name that opts a run into the deterministic failure. Absent from
#: objective-based selection in strategies.choose_strategy, so it is only ever
#: reachable by an explicit request.
TEST_FAIL_STRATEGY = "test_fail"

#: The deterministic reason recorded on the run. The panel shows the backend's
#: reason and never invents one, so this string is what the owner will read.
TEST_FAIL_REASON = "test fixture: deterministic task failure"

_TRUTHY = {"1", "true", "yes", "on"}


def fixture_enabled() -> bool:
    """Whether the deterministic-failure fixture is armed for this process."""
    return (os.environ.get(FAIL_ENV) or "").strip().lower() in _TRUTHY


def should_fail_for_test(*, strategy: str) -> bool:
    """True only for an explicitly requested test_fail run in an armed process.

    Returns False immediately for every production run.
    """
    if not fixture_enabled():
        return False
    return (strategy or "") == TEST_FAIL_STRATEGY
