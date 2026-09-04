"""Phase 10 — authority reachability.

Approval must be reachable through the *real* orchestrator gate, and the fixture
that makes it reachable must be incapable of touching production work.
"""
import pytest

from saathi.agent_runtime import registry, strategies
from saathi.agent_runtime.models import RunState
from saathi.agent_runtime.store import RunStore
from saathi.agent_runtime.test_authority import (
    AUTHORITY_ENV, GATED_STRATEGIES, TEST_APPROVAL_STRATEGY,
    fixture_enabled, is_gated_strategy, strategy_allowed)

PRODUCTION_STRATEGIES = ("single", "build", "architect_build", "document",
                         "business", "broad_research")


@pytest.fixture(autouse=True)
def _disarmed(monkeypatch):
    monkeypatch.delenv(AUTHORITY_ENV, raising=False)


@pytest.fixture()
def store(tmp_path):
    return RunStore(db_path=tmp_path / "authority.db")


# ── fixture gating ─────────────────────────────────────────────────────────

def test_disabled_without_the_environment_gate():
    assert fixture_enabled() is False
    assert strategy_allowed(TEST_APPROVAL_STRATEGY) is False


def test_arming_requires_a_truthy_value(monkeypatch):
    for raw in ("0", "false", "no", "off", "", "  "):
        monkeypatch.setenv(AUTHORITY_ENV, raw)
        assert strategy_allowed(TEST_APPROVAL_STRATEGY) is False
    monkeypatch.setenv(AUTHORITY_ENV, "1")
    assert strategy_allowed(TEST_APPROVAL_STRATEGY) is True


def test_production_strategies_are_never_gated(monkeypatch):
    for armed in ("1", None):
        if armed:
            monkeypatch.setenv(AUTHORITY_ENV, armed)
        else:
            monkeypatch.delenv(AUTHORITY_ENV, raising=False)
        for name in PRODUCTION_STRATEGIES:
            assert strategy_allowed(name) is True, f"{name} must never be gated"
            assert is_gated_strategy(name) is False


def test_disarmed_request_cannot_reach_the_fixture():
    # Falls through to the heuristics, which never return a fixture.
    chosen = strategies.choose_strategy("anything", requested=TEST_APPROVAL_STRATEGY)
    assert chosen != TEST_APPROVAL_STRATEGY
    assert chosen in strategies.STRATEGIES


def test_armed_request_selects_it_only_by_exact_name(monkeypatch):
    monkeypatch.setenv(AUTHORITY_ENV, "1")
    assert strategies.choose_strategy("x", requested=TEST_APPROVAL_STRATEGY) == TEST_APPROVAL_STRATEGY
    assert strategies.choose_strategy("x", requested="test_approvals") != TEST_APPROVAL_STRATEGY


def test_objective_heuristics_can_never_select_it(monkeypatch):
    monkeypatch.setenv(AUTHORITY_ENV, "1")           # even fully armed
    for objective in ("approve this", "approval required", "test approval",
                      "execute the trade", "authorize the payment", "build it",
                      "research approvals", "document the approval process"):
        assert strategies.choose_strategy(objective) != TEST_APPROVAL_STRATEGY


def test_only_the_executor_strategy_is_authority_gated():
    assert GATED_STRATEGIES == (TEST_APPROVAL_STRATEGY,)
    assert strategies.STRATEGIES[TEST_APPROVAL_STRATEGY] == ["executor"]


def test_no_production_strategy_contains_the_approval_agent():
    """The fixture exists precisely because production never routes to executor.

    If this ever fails, approval became reachable in production and the fixture
    should be reconsidered rather than silently kept.
    """
    for name in PRODUCTION_STRATEGIES:
        assert "executor" not in strategies.STRATEGIES[name], (
            f"{name} now includes executor")


def test_no_production_strategy_routes_to_an_approval_requiring_agent():
    """The property that actually makes approval unreachable in production.

    Corrects an earlier assertion that `executor` was the only agent declaring
    `requires_approval`. It is not: `saathi.studio_os.agents` registers a
    `publisher` with the same flag at import time, so the earlier test only
    passed when that module happened not to be imported. What matters is not how
    many such agents exist but that no production strategy routes to one -- which
    is what is asserted here, across every approval-requiring agent there is.
    """
    import saathi.studio_os.agents  # noqa: F401  -- force its registration

    requiring = {a.agent_id for a in registry.all_agents() if a.requires_approval}
    assert "executor" in requiring

    for name, roles in strategies.STRATEGIES.items():
        if name in GATED_STRATEGIES:
            continue
        overlap = requiring.intersection(roles)
        assert not overlap, f"{name} routes to approval-requiring {overlap}"


# ── the real approval path ─────────────────────────────────────────────────

def _approval_run(monkeypatch, store, *, objective="publish the brief",
                  conversation_id=""):
    """Drive a run through the canonical entry point the HTTP route uses.

    Not a shortcut into the orchestrator: `start_agent_run` is what
    `POST /api/v1/agents/runs` calls, so this exercises validation, planning and
    the approval gate exactly as the browser will.
    """
    from saathi.agent_runtime.orchestrator import Orchestrator
    from saathi.agent_runtime.service import start_agent_run

    monkeypatch.setenv(AUTHORITY_ENV, "1")
    orch = Orchestrator(store=store, memory=False)
    rec = start_agent_run(
        objective=objective,
        strategy=TEST_APPROVAL_STRATEGY,
        actor="user:test",
        conversation_id=conversation_id,
        orchestrator=orch,
        execute=True,
    )
    assert rec.ok, f"the fixture run was refused: {rec.error_code} {rec.message}"
    return rec.run_id


def test_the_fixture_reaches_awaiting_approval_through_the_real_gate(monkeypatch, store):
    rid = _approval_run(monkeypatch, store)
    assert store.get_run(rid)["state"] == RunState.AWAITING_APPROVAL.value


def test_a_real_approval_request_is_created(monkeypatch, store):
    rid = _approval_run(monkeypatch, store, objective="publish the brief")
    pending = store.pending_approvals(rid)
    assert len(pending) == 1

    appr = pending[0]
    assert appr["run_id"] == rid
    assert appr["status"] == "pending"
    assert appr["agent"] == "executor"
    assert appr["action"], "the approval records what it is for"
    assert appr["expires_at"] > appr["created_at"]


def test_nothing_executes_while_approval_is_pending(monkeypatch, store):
    rid = _approval_run(monkeypatch, store)
    tasks = store.list_tasks(rid)
    assert tasks and all(t["status"] == "blocked" for t in tasks), \
        "the gate returns before any task runs"
    assert store.artifacts(rid) == [], "no work product may exist"
    assert store.verifications(rid) == [], "nothing was verified"
    names = [e["name"] for e in store.events(rid)]
    assert "task.started" not in names, "no task may start"


def test_the_approval_is_unresolved_and_grants_nothing(monkeypatch, store):
    rid = _approval_run(monkeypatch, store)
    appr = store.pending_approvals(rid)[0]
    assert appr["status"] == "pending"
    assert not appr.get("resolved_by")
    assert not appr.get("resolved_at")


def test_resolution_is_backend_truth(monkeypatch, store):
    """Read-model resolution: the item stops being pending because the store says so."""
    rid = _approval_run(monkeypatch, store)
    aid = store.pending_approvals(rid)[0]["id"]

    store.resolve_approval(aid, approved=True, actor="user:owner")
    assert store.get_approval(aid)["status"] == "approved"
    assert store.pending_approvals(rid) == [], "a resolved approval is no longer pending"


def test_denial_is_recorded_distinctly(monkeypatch, store):
    rid = _approval_run(monkeypatch, store)
    aid = store.pending_approvals(rid)[0]["id"]
    store.resolve_approval(aid, approved=False, actor="user:owner")
    assert store.get_approval(aid)["status"] == "denied"


def test_resolution_is_idempotent(monkeypatch, store):
    rid = _approval_run(monkeypatch, store)
    aid = store.pending_approvals(rid)[0]["id"]
    first = store.resolve_approval(aid, approved=True, actor="user:owner")
    again = store.resolve_approval(aid, approved=False, actor="user:someone-else")
    assert again["status"] == first["status"] == "approved", \
        "a resolved approval cannot be re-decided"


def test_approvals_from_separate_runs_do_not_contaminate(monkeypatch, store):
    a = _approval_run(monkeypatch, store, objective="run a", conversation_id="cmd-a")
    b = _approval_run(monkeypatch, store, objective="run b", conversation_id="cmd-b")
    assert store.pending_approvals(a)[0]["run_id"] == a
    assert store.pending_approvals(b)[0]["run_id"] == b
    assert store.pending_approvals(a)[0]["id"] != store.pending_approvals(b)[0]["id"]


def test_conversation_correlation_survives_the_gate(monkeypatch, store):
    rid = _approval_run(monkeypatch, store, conversation_id="cmd-xyz")
    assert store.get_run(rid)["conversation_id"] == "cmd-xyz"


# ── BLOCKED: documented gap, not fabricated ────────────────────────────────

def test_blocked_has_no_http_reachable_resting_path(store):
    """Documented backend gap, deliberately not worked around.

    BLOCKED has exactly two producers. The orchestrator derives it from a graph
    whose dependencies failed, but `_finalize` then transitions the run to
    FAILED, so that BLOCKED is transient rather than a state history can rest in.
    The lifecycle controller produces a resting BLOCKED via
    `recover_run` -> MANUAL_REVIEW_REQUIRED, but that requires an expired lease
    with mid-task mutation evidence *and* is not exposed over HTTP.

    Phase 10 therefore leaves BLOCKED browser-unavailable rather than assigning
    the state directly, which would prove nothing about the real mechanism.
    """
    from saathi.agent_runtime import api
    routes = [r for r in dir(api) if "recover" in r.lower()]
    assert routes == [], "if a recovery route appears, BLOCKED becomes certifiable"


def test_the_lifecycle_controller_still_derives_blocked_legitimately(store):
    """The mechanism itself is real; only its HTTP reachability is missing."""
    import time

    from saathi.agent_runtime.lifecycle import RecoveryAction, RunLifecycleController

    rid = store.create_run(objective="abandoned mid-task", strategy="build", actor="u")
    store.transition(rid, RunState.PLANNING)
    store.transition(rid, RunState.QUEUED)
    store.transition(rid, RunState.RUNNING)
    # A worker took a lease, started a task, then died: the lease expires with
    # mutation evidence in flight. That is a genuine manual-review condition.
    store.update_lifecycle(rid, lease_owner="worker-1", lease_expires_at=time.time() - 60)
    store.event(rid, "task.started", {"task": "t1", "agent": "builder"})

    lc = RunLifecycleController(store)
    assert lc.classify_recovery(rid) == RecoveryAction.MANUAL_REVIEW_REQUIRED

    lc.recover_run(rid, actor="operator")
    assert store.get_run(rid)["state"] == RunState.BLOCKED.value, \
        "the real controller derives BLOCKED; it is never assigned by hand"
