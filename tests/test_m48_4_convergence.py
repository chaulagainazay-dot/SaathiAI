"""M48.4 — M8 wrap, skip_contract guard, cancellation token."""
from __future__ import annotations

import os

import pytest

from saathi.agent_runtime.errors import AgentRunError
from saathi.agent_runtime.gateway_exec import AgentExecutor, CancellationToken
from saathi.agent_runtime.models import AgentDefinition, RiskClass
from saathi.agent_runtime.orchestrator import Orchestrator
from saathi.agent_runtime.store import RunStore
from saathi.chat.engine import ChatEngine
from saathi.chat.store import ChatStore


def test_skip_contract_blocked_outside_pytest(tmp_path, monkeypatch):
    store = RunStore(tmp_path / "s.db")
    orch = Orchestrator(
        store=store,
        executor=AgentExecutor(execute_fn=lambda r, p, s: {"text": "x", "status": "success"}),
        memory=False,
    )
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with pytest.raises(AgentRunError) as ei:
        orch.create_run("x", skip_contract=True)
    assert "test-only" in ei.value.message.lower() or "skip_contract" in ei.value.message


def test_skip_contract_allowed_under_pytest(tmp_path):
    assert os.environ.get("PYTEST_CURRENT_TEST")
    store = RunStore(tmp_path / "s2.db")
    orch = Orchestrator(
        store=store,
        executor=AgentExecutor(execute_fn=lambda r, p, s: {"text": "x", "status": "success"}),
        memory=False,
    )
    rid = orch.create_run("raw", strategy="build", skip_contract=True)
    assert store.get_run(rid)


def test_cancellation_token_raises():
    t = CancellationToken(run_id="r1")
    t.force_cancel()
    assert t.should_cancel()
    with pytest.raises(RuntimeError, match="CANCELLATION"):
        t.raise_if_cancelled()


def test_executor_respects_cancel_before_turn():
    def boom(*a):
        raise AssertionError("should not execute")

    ex = AgentExecutor(execute_fn=boom)
    agent = AgentDefinition(
        agent_id="planner", name="P", role="planner", risk_ceiling=RiskClass.READ_ONLY
    )
    tok = CancellationToken()
    tok.force_cancel()
    with pytest.raises(RuntimeError, match="CANCELLATION"):
        ex.run_turn(agent, "do it", cancel_token=tok)


def test_m8_run_agent_uses_canonical_run(tmp_path, monkeypatch):
    from saathi.memory.engine import MemoryEngine, MemoryStore
    import saathi.memory.engine.core as core

    iso = MemoryEngine(MemoryStore(tmp_path / "m.db"))
    monkeypatch.setattr(core, "_default", iso)
    monkeypatch.setattr(core, "default_engine", lambda: iso)

    cstore = ChatStore(tmp_path / "c.db")
    eng = ChatEngine(
        cstore,
        memory=iso,
        llm_fn=lambda p, s: {"text": f"plan:{p[-20:]}", "provider": "t", "tokens": 3},
    )
    # isolate agent_runtime store
    rstore = RunStore(tmp_path / "ar.db")
    import saathi.agent_runtime.orchestrator as om

    shared = Orchestrator(
        store=rstore,
        executor=AgentExecutor(
            execute_fn=lambda r, p, s: {"text": "ok", "provider": "t", "tokens": 1, "status": "success"}
        ),
        memory=False,
    )
    monkeypatch.setattr(om, "default_orchestrator", lambda: shared)

    conv = cstore.create_conversation(title="t")
    out = eng.run_agent(conv["id"], "planner", "plan the week")
    assert out["status"] == "done"
    assert out.get("canonical_run_id")
    run = rstore.get_run(out["canonical_run_id"])
    assert run is not None
    assert run["state"] in ("completed", "partially_completed", "queued", "failed")
