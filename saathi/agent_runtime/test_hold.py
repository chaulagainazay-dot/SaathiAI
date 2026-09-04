"""Test-only live-run hold (Phase 5F certification fixture).

A real agent run normally reaches ``agent.started`` and terminates within a few
hundred milliseconds, which is too short to observe the Command Core's
SUPERVISING state in a browser. This module keeps a run legitimately
non-terminal for a bounded window so the *production* observation path
(run events -> Event Fabric -> run-in-context -> snapshot -> UI) can be
inspected.

It is a certification fixture, never a production behaviour:

* Disabled unless ``SAATHI_TEST_RUN_HOLD_MS`` is set to a positive value.
* Applies only to runs whose strategy is exactly ``test_hold``.
* Both gates must pass, so a production run can never be slowed: the very
  first check is the environment variable, and with it unset this function
  returns before reading anything else.
* Hard ceiling of 30 s, so a fixture can never orphan a run indefinitely.
* Grants no authority, touches no external system, and emits no lifecycle
  event of its own beyond two clearly-named markers.
"""
from __future__ import annotations

import os
import threading

HOLD_ENV = "SAATHI_TEST_RUN_HOLD_MS"

#: Strategy name that opts a run into the hold. Absent from objective-based
#: selection in strategies.choose_strategy, so it is only ever reachable by an
#: explicit request.
TEST_HOLD_STRATEGY = "test_hold"

#: A fixture must never hold a run open indefinitely.
MAX_HOLD_MS = 30_000


def configured_hold_ms() -> int:
    """Bounded hold window in milliseconds; 0 when the fixture is disabled."""
    raw = (os.environ.get(HOLD_ENV) or "").strip()
    if not raw:
        return 0
    try:
        ms = int(float(raw))
    except (TypeError, ValueError):
        return 0
    if ms <= 0:
        return 0
    return min(ms, MAX_HOLD_MS)


def hold_for_test(*, run_id: str, strategy: str, store=None, sleeper=None) -> int:
    """Hold a test-strategy run after agent.started. Returns the ms actually held.

    Returns 0 immediately for every production run.
    """
    ms = configured_hold_ms()
    if ms <= 0:
        return 0
    if (strategy or "") != TEST_HOLD_STRATEGY:
        return 0

    if store is not None:
        try:
            store.event(run_id, "test.hold.started", {"ms": ms})
        except Exception:
            pass

    # threading.Event rather than time.sleep so a future release primitive can
    # interrupt the wait without changing this call site.
    waiter = sleeper if sleeper is not None else threading.Event().wait
    waiter(ms / 1000.0)

    if store is not None:
        try:
            store.event(run_id, "test.hold.released", {"ms": ms})
        except Exception:
            pass
    return ms
