"""Phase 16 — `gateway_exec` enforces independently of any prior decision.

Authorization and enforcement are separate on purpose, and this file tests the
second one. The interesting cases are time-of-check/time-of-use: an execution
that was legitimate when it was decided and must *not* proceed now, because an
operator hit the kill switch or the run ended in between.

A decision is evidence about an instant, not a capability that outlives it.
Nothing here performs a real side effect: the platform runtime is a stand-in and
no connector, broker or network is involved.
"""
from __future__ import annotations

import pytest

from saathi.agent_runtime import registry
from saathi.agent_runtime.gateway_exec import AgentExecutor, _execution_time_block
from saathi.agent_runtime.store import RunStore


def _fake_exec(role, prompt, system):
    return {"text": "ok", "provider": "test", "tokens": 1, "status": "success"}


@pytest.fixture
def store(tmp_path):
    return RunStore(tmp_path / "ar.db")


class _StubRuntime:
    """Records dispatches. Its whole job is to prove one did not happen."""

    def __init__(self):
        self.calls = []

    def execute_token(self, *, token, tool_id, arguments, run_id):
        self.calls.append((tool_id, run_id))

        class _R:
            ok = True
            cancellation_confirmed = False
            safe_message = "done"
            error_code = ""
            call_id = "c1"
            adapter_invoked = True

            class outcome_class:
                value = "SUCCESS"

        return _R()


@pytest.fixture
def bound():
    runtime = _StubRuntime()
    return AgentExecutor(execute_fn=_fake_exec, platform_runtime=runtime,
                         platform_token="t"), runtime


@pytest.fixture(autouse=True)
def _no_kill_switch(monkeypatch):
    """Default the global stop to *inactive* so each test states its own case.

    Without this the suite would depend on whatever the shared kill-switch store
    happens to hold, and a passing run would not mean what it looks like.
    """
    import saathi.platform.tg.kill_switch as ks

    monkeypatch.setattr(ks.KillSwitchStore, "is_blocked",
                        lambda self, **kw: {"blocked": False})


def _force_state(store: RunStore, rid: str, state: str) -> None:
    """Put the run into `state` directly, bypassing transition validation.

    These tests are about what enforcement does when it *finds* a run in a
    given state, not about how the run legally got there. Routing the setup
    through `transition` would couple them to the lifecycle graph and quietly
    skip any state that graph makes awkward to reach -- which is exactly the
    set of states worth checking.
    """
    with store._conn() as c:
        c.execute("UPDATE orchestration_run SET state=? WHERE id=?", (state, rid))


def _agent():
    return registry.get("researcher")


def _read_tool(agent):
    """A tool this agent may run without approval, so the only thing that can
    stop it is the enforcement being tested."""
    return agent.allowed_tools[0]


# ── the baseline actually dispatches ────────────────────────────────────────

def test_a_permitted_tool_on_a_live_run_dispatches(bound, store):
    executor, runtime = bound
    agent = _agent()
    rid = store.create_run(objective="x", strategy="c", actor="u")
    out = executor.request_tool(agent, _read_tool(agent), {}, store, rid)
    assert out["status"] == "success"
    assert runtime.calls, "baseline must really execute, or the denials prove nothing"


# ── TOCTOU: authority that changed after the decision ───────────────────────

def test_a_kill_switch_activated_after_the_decision_stops_execution(
        bound, store, monkeypatch):
    """The exact race this milestone exists to close: everything upstream said
    yes, and the operator has since said no."""
    executor, runtime = bound
    agent = _agent()
    rid = store.create_run(objective="x", strategy="c", actor="u")

    import saathi.platform.tg.kill_switch as ks
    monkeypatch.setattr(ks.KillSwitchStore, "is_blocked",
                        lambda self, **kw: {"blocked": True})

    out = executor.request_tool(agent, _read_tool(agent), {}, store, rid)
    assert out["status"] == "rejected"
    assert out["error_code"] == "KILL_SWITCH_ACTIVE"
    assert runtime.calls == [], "nothing may be dispatched once the stop is on"


def test_an_unreadable_kill_switch_stops_execution(bound, store, monkeypatch):
    """A stop that cannot be read is not an absent stop."""
    executor, runtime = bound
    agent = _agent()
    rid = store.create_run(objective="x", strategy="c", actor="u")

    import saathi.platform.tg.kill_switch as ks

    def _boom(self, **kw):
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(ks.KillSwitchStore, "is_blocked", _boom)

    out = executor.request_tool(agent, _read_tool(agent), {}, store, rid)
    assert out["status"] == "rejected"
    assert out["error_code"] == "KILL_SWITCH_UNKNOWN"
    assert runtime.calls == []


@pytest.mark.parametrize("state", ["completed", "cancelled", "failed",
                                   "timed_out", "blocked"])
def test_a_run_that_ended_after_the_decision_stops_execution(
        bound, store, state):
    executor, runtime = bound
    agent = _agent()
    rid = store.create_run(objective="x", strategy="c", actor="u")
    _force_state(store, rid, state)

    out = executor.request_tool(agent, _read_tool(agent), {}, store, rid)
    # The property is that nothing ran. A cancelled run is caught earlier, by
    # the pre-existing cancellation check, and reports "cancelled" rather than
    # "rejected" -- a different refusal path for the same outcome, so the
    # assertion is on the outcome and not on which guard got there first.
    assert out["status"] in ("rejected", "cancelled")
    assert out["allowed"] is False
    assert runtime.calls == []
    if out["status"] == "rejected":
        assert out["error_code"] == "RUN_STATE_BLOCKS"


def test_execution_against_a_run_that_does_not_exist_is_refused(bound, store):
    executor, runtime = bound
    agent = _agent()
    out = executor.request_tool(agent, _read_tool(agent), {}, store,
                                "run-that-never-existed")
    assert out["status"] == "rejected"
    assert out["error_code"] == "RUN_NOT_FOUND"
    assert runtime.calls == []


# ── the enforcement helper on its own ───────────────────────────────────────

def test_the_block_check_returns_nothing_for_a_healthy_run(store):
    rid = store.create_run(objective="x", strategy="c", actor="u")
    assert _execution_time_block(store, rid) is None


def test_the_block_check_fails_closed_on_an_unreadable_store(store, monkeypatch):
    rid = store.create_run(objective="x", strategy="c", actor="u")

    def _boom(_rid):
        raise RuntimeError("db gone")

    monkeypatch.setattr(store, "get_run", _boom)
    assert _execution_time_block(store, rid) == "RUN_STATE_UNKNOWN"


def test_a_runless_call_is_still_kill_switch_checked(store, monkeypatch):
    """Not being run-scoped exempts nothing from the global stop."""
    import saathi.platform.tg.kill_switch as ks

    monkeypatch.setattr(ks.KillSwitchStore, "is_blocked",
                        lambda self, **kw: {"blocked": True})
    assert _execution_time_block(store, "") == "KILL_SWITCH_ACTIVE"


# ── binding: no execution without a real runtime ────────────────────────────

def test_an_unbound_executor_dispatches_nothing(store):
    """The precondition Phase 14 reported. Still true, and still fails closed."""
    executor = AgentExecutor(execute_fn=_fake_exec)
    agent = _agent()
    rid = store.create_run(objective="x", strategy="c", actor="u")
    out = executor.request_tool(agent, _read_tool(agent), {}, store, rid)
    assert out["status"] == "rejected"
    assert out["error_code"] == "PLATFORM_RUNTIME_REQUIRED"


def test_a_stolen_token_string_does_not_authorize_a_denied_tool(bound, store):
    """Holding an identifier is not holding permission: a tool the agent's
    policy denies stays denied however the executor is bound."""
    executor, runtime = bound
    agent = _agent()
    rid = store.create_run(objective="x", strategy="c", actor="u")
    denied = "git.push"
    out = executor.request_tool(agent, denied, {}, store, rid)
    assert out["allowed"] is False
    assert runtime.calls == []


# ── approval stays a precondition, not a side channel ───────────────────────

def test_a_tool_needing_approval_is_not_executed_by_requesting_it(bound, store):
    executor, runtime = bound
    agent = registry.get("executor")
    rid = store.create_run(objective="x", strategy="c", actor="u")
    out = executor.request_tool(agent, "video-generation", {}, store, rid)
    assert out["requires_approval"] and out["status"] == "awaiting_approval"
    assert runtime.calls == [], "creating an approval must not run the action"
