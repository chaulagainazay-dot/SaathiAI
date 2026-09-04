"""Phase 5F — the live-run certification fixture must never touch production."""
from __future__ import annotations

import os

import pytest

from saathi.agent_runtime import test_hold as th
from saathi.agent_runtime.strategies import STRATEGIES, choose_strategy


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(th.HOLD_ENV, raising=False)


def test_disabled_by_default():
    assert th.configured_hold_ms() == 0
    assert th.hold_for_test(run_id="r1", strategy=th.TEST_HOLD_STRATEGY) == 0


def test_production_strategy_never_holds_even_when_enabled(monkeypatch):
    monkeypatch.setenv(th.HOLD_ENV, "5000")
    slept = []
    for strategy in ("build", "document", "business", "architect_build", "broad_research", ""):
        assert th.hold_for_test(run_id="r1", strategy=strategy,
                                sleeper=lambda s: slept.append(s)) == 0
    assert slept == [], "a production strategy must never be delayed"


def test_holds_only_with_both_gates(monkeypatch):
    monkeypatch.setenv(th.HOLD_ENV, "1200")
    slept = []
    held = th.hold_for_test(run_id="r1", strategy=th.TEST_HOLD_STRATEGY,
                            sleeper=lambda s: slept.append(s))
    assert held == 1200
    assert slept == [1.2]


def test_hold_is_bounded():
    assert th.MAX_HOLD_MS == 30_000


@pytest.mark.parametrize("raw,expected", [
    ("0", 0), ("-5", 0), ("", 0), ("abc", 0), ("2000", 2000), ("999999", th.MAX_HOLD_MS),
])
def test_configured_ms_is_clamped_and_fail_closed(monkeypatch, raw, expected):
    monkeypatch.setenv(th.HOLD_ENV, raw)
    assert th.configured_hold_ms() == expected


def test_fixture_strategy_is_never_chosen_by_objective():
    objectives = [
        "implement the billing module", "research competitors", "write release notes",
        "prioritize revenue work", "design the system schema", "hold the test",
        "test_hold", "please test hold this run",
    ]
    for objective in objectives:
        assert choose_strategy(objective) != th.TEST_HOLD_STRATEGY, objective


def test_fixture_strategy_requires_explicit_request():
    assert choose_strategy("anything", requested=th.TEST_HOLD_STRATEGY) == th.TEST_HOLD_STRATEGY
    assert th.TEST_HOLD_STRATEGY in STRATEGIES
    # A single planner step: the fixture adds no extra agents or authority.
    assert STRATEGIES[th.TEST_HOLD_STRATEGY] == ["planner"]


def test_hold_emits_only_its_own_markers(monkeypatch):
    monkeypatch.setenv(th.HOLD_ENV, "10")
    events = []

    class Store:
        def event(self, rid, name, payload=None):
            events.append((rid, name, payload))

    th.hold_for_test(run_id="r1", strategy=th.TEST_HOLD_STRATEGY, store=Store(),
                     sleeper=lambda s: None)
    names = [n for _, n, _ in events]
    assert names == ["test.hold.started", "test.hold.released"]
    # It must not fabricate lifecycle events the orchestrator owns.
    for forbidden in ("agent.started", "run.completed", "verification.passed",
                      "approval.requested", "execution.started"):
        assert forbidden not in names


def test_hold_grants_no_authority_fields(monkeypatch):
    monkeypatch.setenv(th.HOLD_ENV, "10")
    events = []

    class Store:
        def event(self, rid, name, payload=None):
            events.append(payload or {})

    th.hold_for_test(run_id="r1", strategy=th.TEST_HOLD_STRATEGY, store=Store(),
                     sleeper=lambda s: None)
    for payload in events:
        for key in ("approved", "authority_class", "approval_token", "execution_granted",
                    "guardian", "capability"):
            assert key not in payload


def test_store_failure_never_breaks_a_run(monkeypatch):
    monkeypatch.setenv(th.HOLD_ENV, "10")

    class Broken:
        def event(self, *a, **k):
            raise RuntimeError("store down")

    assert th.hold_for_test(run_id="r1", strategy=th.TEST_HOLD_STRATEGY, store=Broken(),
                            sleeper=lambda s: None) == 10
