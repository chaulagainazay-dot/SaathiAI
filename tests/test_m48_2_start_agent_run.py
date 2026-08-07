"""M48.2 — canonical start_agent_run façade and create_run contract gate."""
from __future__ import annotations

import time

import pytest

from saathi.agent_runtime.contracts import AgentRunRequest, AuthorityClass
from saathi.agent_runtime.errors import AgentRunError, AgentRuntimeErrorCode
from saathi.agent_runtime.gateway_exec import AgentExecutor
from saathi.agent_runtime.orchestrator import Orchestrator
from saathi.agent_runtime.service import start_agent_run
from saathi.agent_runtime.store import RunStore


def _fake_exec(role, prompt, system):
    return {
        "text": f"{role} ok",
        "provider": "test",
        "tokens": 4,
        "status": "success",
    }


@pytest.fixture
def orch(tmp_path):
    return Orchestrator(
        store=RunStore(tmp_path / "ar.db"),
        executor=AgentExecutor(execute_fn=_fake_exec),
        memory=False,
    )


def test_start_rejects_unknown_capability_without_run(orch):
    rec = start_agent_run(
        objective="do something",
        requested_capability="teleport",
        orchestrator=orch,
    )
    assert rec.ok is False
    assert rec.status == "rejected"
    assert rec.run_id == ""
    assert orch.store.list_runs(limit=10) == []


def test_start_rejects_financial_execution(orch):
    rec = start_agent_run(
        objective="buy shares",
        authority_class=AuthorityClass.FINANCIAL_EXECUTION.value,
        requested_capability="plan",
        orchestrator=orch,
        approval_token="x",
    )
    assert rec.ok is False
    assert rec.error_code == AgentRuntimeErrorCode.PROHIBITED_OPERATION
    assert orch.store.list_runs(limit=5) == []


def test_start_requires_approval_for_local_mutation(orch):
    rec = start_agent_run(
        objective="migrate schema",
        authority_class=AuthorityClass.LOCAL_MUTATION.value,
        requested_capability="execute_local",
        orchestrator=orch,
    )
    assert rec.ok is False
    assert rec.error_code == AgentRuntimeErrorCode.APPROVAL_REQUIRED


def test_start_accepts_read_only_plan(orch):
    rec = start_agent_run(
        objective="summarize project status",
        strategy="build",
        orchestrator=orch,
        execute=False,
    )
    assert rec.ok is True
    assert rec.run_id
    run = orch.store.get_run(rec.run_id)
    assert run["state"] == "queued"
    # validation.passed event present
    names = [e["name"] for e in orch.store.events(rec.run_id, limit=50)]
    assert "validation.passed" in names or "run.created" in names


def test_create_run_blocks_prohibited_without_skip(orch):
    with pytest.raises(AgentRunError) as ei:
        orch.create_run(
            "trade",
            budget={"authority_class": "FINANCIAL_EXECUTION", "capability": "plan"},
        )
    assert ei.value.code == AgentRuntimeErrorCode.PROHIBITED_OPERATION
    assert orch.store.list_runs(limit=5) == []


def test_create_run_skip_contract_for_low_level_tests(orch):
    rid = orch.create_run("raw path", strategy="build", skip_contract=True)
    assert orch.store.get_run(rid)


def test_expired_approval_rejected(orch):
    rec = start_agent_run(
        objective="mutate",
        authority_class=AuthorityClass.LOCAL_MUTATION.value,
        requested_capability="execute_local",
        approval_token="tok",
        approval_expires_at=time.time() - 5,
        orchestrator=orch,
    )
    assert rec.ok is False
    assert rec.error_code == AgentRuntimeErrorCode.APPROVAL_EXPIRED


def test_provider_unavailable_rejected(orch):
    rec = start_agent_run(
        objective="plan week",
        orchestrator=orch,
        provider_available=False,
    )
    assert rec.ok is False
    assert rec.error_code == AgentRuntimeErrorCode.PROVIDER_UNAVAILABLE
    assert orch.store.list_runs(limit=5) == []


def test_idempotency_replay(orch):
    r1 = start_agent_run(
        objective="stable task",
        strategy="build",
        idempotency_key="k-1",
        orchestrator=orch,
    )
    r2 = start_agent_run(
        objective="stable task",
        strategy="build",
        idempotency_key="k-1",
        orchestrator=orch,
    )
    assert r1.ok and r2.ok
    assert r1.run_id == r2.run_id


def test_idempotency_conflict(orch):
    start_agent_run(
        objective="task A",
        strategy="build",
        idempotency_key="k-2",
        orchestrator=orch,
    )
    r2 = start_agent_run(
        objective="task B different",
        strategy="build",
        idempotency_key="k-2",
        orchestrator=orch,
    )
    assert r2.ok is False
    assert r2.error_code == AgentRuntimeErrorCode.IDEMPOTENCY_CONFLICT


def test_execute_path(orch):
    rec = start_agent_run(
        objective="implement tiny fix",
        strategy="build",
        orchestrator=orch,
        execute=True,
        max_wall_sec=30,
    )
    assert rec.ok is True
    assert rec.outcome is not None


def test_api_create_run_uses_facade(tmp_path, monkeypatch):
    from saathi.agent_runtime import api

    store = RunStore(tmp_path / "api.db")
    orch = Orchestrator(
        store=store, executor=AgentExecutor(execute_fn=_fake_exec), memory=False
    )
    monkeypatch.setattr(api, "default_orchestrator", lambda: orch)
    # also patch service default used by start_agent_run when orch not injected via api
    import saathi.agent_runtime.service as svc

    monkeypatch.setattr(svc, "default_orchestrator", lambda: orch)

    ok = api.create_run(api.CreateRun(objective="implement x", strategy="build"))
    assert ok.get("run_id")
    bad = api.create_run(
        api.CreateRun(
            objective="x",
            authority_class="FINANCIAL_EXECUTION",
            requested_capability="plan",
        )
    )
    assert bad.get("ok") is False
    assert bad.get("error") == AgentRuntimeErrorCode.PROHIBITED_OPERATION
