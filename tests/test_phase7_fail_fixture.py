"""Phase 7 certification fixture must be inert in production."""
import os

import pytest

from saathi.agent_runtime import strategies
from saathi.agent_runtime.test_fail import (
    FAIL_ENV, TEST_FAIL_STRATEGY, fixture_enabled, should_fail_for_test)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(FAIL_ENV, raising=False)


def test_disabled_without_the_environment_gate():
    assert fixture_enabled() is False
    assert should_fail_for_test(strategy=TEST_FAIL_STRATEGY) is False


def test_armed_env_alone_does_not_fail_production_runs(monkeypatch):
    monkeypatch.setenv(FAIL_ENV, "1")
    assert fixture_enabled() is True
    # Every real strategy stays unaffected even with the fixture armed.
    for name in ("single", "build", "architect_build", "document", "business",
                 "broad_research", "test_hold"):
        assert should_fail_for_test(strategy=name) is False
    assert should_fail_for_test(strategy="") is False


def test_both_gates_together_are_required(monkeypatch):
    monkeypatch.setenv(FAIL_ENV, "1")
    assert should_fail_for_test(strategy=TEST_FAIL_STRATEGY) is True


def test_non_truthy_values_leave_it_disabled(monkeypatch):
    for raw in ("0", "false", "no", "off", "", "  "):
        monkeypatch.setenv(FAIL_ENV, raw)
        assert should_fail_for_test(strategy=TEST_FAIL_STRATEGY) is False


def test_objective_heuristics_never_select_the_fixture():
    for objective in ("build the thing", "research the market", "write a report",
                      "fix the bug", "design the schema", "prioritize revenue",
                      "fail", "test fail", "make it fail"):
        assert strategies.choose_strategy(objective) != TEST_FAIL_STRATEGY


def test_fixture_is_reachable_only_by_explicit_request():
    assert strategies.choose_strategy("anything", requested=TEST_FAIL_STRATEGY) == TEST_FAIL_STRATEGY
    assert TEST_FAIL_STRATEGY in strategies.STRATEGIES


def test_fixture_grants_no_authority():
    """It can answer one boolean and nothing else.

    Checked against the parsed module rather than its prose: the docstring
    legitimately mentions approvals and blocks to say it cannot create them.
    """
    import ast
    import saathi.agent_runtime.test_fail as mod

    tree = ast.parse(open(mod.__file__).read())

    # No imports at all beyond the standard library `os` -- it cannot reach the
    # store, the lifecycle, the registry or the gateway.
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported <= {"os", "__future__"}, f"unexpected imports: {imported}"

    # Both public functions return booleans only.
    for fn in ("fixture_enabled", "should_fail_for_test"):
        assert isinstance(getattr(mod, fn)(**({} if fn == "fixture_enabled"
                                              else {"strategy": "x"})), bool)

    # And it writes nothing: no assignment to any attribute of another object.
    assert not [n for n in ast.walk(tree)
                if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)]
