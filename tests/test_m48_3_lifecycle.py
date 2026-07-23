"""M48.3 — durable lifecycle, cancellation, lease, recovery tests."""
from __future__ import annotations

import time

import pytest

from saathi.agent_runtime.gateway_exec import AgentExecutor
from saathi.agent_runtime.lifecycle import (
    RecoveryAction,
    RetryClass,
    RunLifecycleController,
    StaleClass,
    provider_health_evidence,
)
from saathi.agent_runtime.models import RunState, is_terminal
from saathi.agent_runtime.orchestrator import Orchestrator
from saathi.agent_runtime.service import start_agent_run
from saathi.agent_runtime.store import RunStore


def _fake(role, prompt, system):
    return {"text": f"{role}:ok", "provider": "test", "tokens": 2, "status": "success"}


@pytest.fixture
def store(tmp_path):
    return RunStore(tmp_path / "lc.db")


@pytest.fixture
def orch(store):
    return Orchestrator(
        store=store, executor=AgentExecutor(execute_fn=_fake), memory=False
    )


@pytest.fixture
def lc(store):
    return RunLifecycleController(store, lease_sec=5.0)


def test_cancel_is_idempotent_and_terminal(orch, lc):
    rec = start_agent_run(
        objective="implement feature x",
        strategy="build",
        orchestrator=orch,
        execute=False,
    )
    rid = rec.run_id
    r1 = lc.request_cancel(rid, reason="user")
    r2 = lc.request_cancel(rid, reason="user")
    assert r1.ok and r2.ok
    run = orch.store.get_run(rid)
    assert run["state"] == RunState.CANCELLED.value
    assert is_terminal(RunState(run["state"]))
    # no silent resume
    with pytest.raises(Exception):
        orch.store.transition(rid, RunState.RUNNING)


def test_cancel_prevents_new_tasks(orch, lc):
    rec = start_agent_run(
        objective="implement feature y",
        strategy="build",
        orchestrator=orch,
        execute=False,
    )
    rid = rec.run_id
    lc.request_cancel(rid)
    out = orch.run(rid)
    assert out["state"] == RunState.CANCELLED.value or out.get("note") == "cancelled"


def test_lease_exclusive(orch, lc):
    rec = start_agent_run(
        objective="plan week", orchestrator=orch, execute=False
    )
    rid = rec.run_id
    a = lc.acquire_lease(rid, owner="worker-a", lease_sec=30)
    b = lc.acquire_lease(rid, owner="worker-b", lease_sec=30)
    assert a.ok is True
    assert b.ok is False
    assert "another" in b.message
    hb = lc.heartbeat(rid, owner="worker-a")
    assert hb.ok
    rel = lc.release_lease(rid, owner="worker-a")
    assert rel.ok
    c = lc.acquire_lease(rid, owner="worker-b", lease_sec=30)
    assert c.ok


def test_timeout_enforcement(orch, lc):
    rec = start_agent_run(
        objective="plan week",
        orchestrator=orch,
        execute=False,
        timeout_sec=60,
    )
    rid = rec.run_id
    # force past deadline
    orch.store.update_lifecycle(rid, deadline_at=time.time() - 1)
    out = lc.enforce_timeout(rid)
    assert out["action"] == "timeout"
    assert orch.store.get_run(rid)["state"] == RunState.TIMED_OUT.value


def test_retry_classes(tmp_path):
    lc = RunLifecycleController(RunStore(tmp_path / "r.db"))
    cls, ok, _ = lc.classify_retry(cancelled=True)
    assert cls == RetryClass.NOT_RETRYABLE_CANCELLED and not ok
    cls, ok, _ = lc.classify_retry(prohibited=True)
    assert cls == RetryClass.NOT_RETRYABLE_PROHIBITED
    cls, ok, _ = lc.classify_retry(mutation_uncertain=True)
    assert cls == RetryClass.NOT_RETRYABLE_MUTATION_UNCERTAIN
    cls, ok, backoff = lc.classify_retry(
        error="connection reset 503", attempts=0, max_retries=3
    )
    assert ok and cls == RetryClass.RETRYABLE_TRANSIENT
    assert backoff >= 0


def test_kill_switch_all(orch, lc):
    a = start_agent_run(objective="a implement", strategy="build", orchestrator=orch)
    b = start_agent_run(objective="b implement", strategy="build", orchestrator=orch)
    out = lc.kill_switch(scope="all", actor="op")
    assert out["ok"] and out["cancelled"] >= 2
    assert orch.store.get_run(a.run_id)["state"] == "cancelled"
    assert orch.store.get_run(b.run_id)["state"] == "cancelled"


def test_recovery_terminal_no_action(orch, lc):
    rec = start_agent_run(objective="x implement", strategy="build", orchestrator=orch)
    lc.request_cancel(rec.run_id)
    action = lc.classify_recovery(rec.run_id)
    assert action == RecoveryAction.TERMINAL_NO_ACTION


def test_stale_lease_reconcile(orch, lc):
    rec = start_agent_run(objective="x implement", strategy="build", orchestrator=orch)
    rid = rec.run_id
    # start_agent_run leaves run QUEUED — advance legally to RUNNING
    orch.store.transition(rid, RunState.RUNNING)
    orch.store.update_lifecycle(
        rid,
        lease_owner="dead-worker",
        lease_expires_at=time.time() - 10,
        heartbeat_at=time.time() - 100,
    )
    cls = lc.classify_stale(rid)
    assert cls in (
        StaleClass.STALE_UNKNOWN_SIDE_EFFECT,
        StaleClass.STALE_RECOVERABLE,
    )
    out = lc.reconcile(rid)
    assert out["ok"]


def test_provider_health_no_paid_probe():
    health = provider_health_evidence()
    names = {h.name: h for h in health}
    assert "remote_paid_providers" in names
    assert names["remote_paid_providers"].status == "PROHIBITED"
    assert names["remote_paid_providers"].evidence.get("probed") is False


def test_terminal_no_in_place_retry(orch, lc):
    rec = start_agent_run(
        objective="implement z", strategy="build", orchestrator=orch, execute=True
    )
    rid = rec.run_id
    # force terminal failed-like via cancel
    lc.request_cancel(rid)
    tasks = orch.store.list_tasks(rid)
    if tasks:
        out = orch.retry_task(rid, tasks[0]["id"])
        assert out.get("note") in (
            "cancelled",
            "terminal_no_retry_in_place",
            "timed_out",
        ) or out.get("state") == "cancelled"


def test_execute_with_lease_and_cancel_mid(orch, lc):
    # cancel after create before execute completes
    rec = start_agent_run(
        objective="implement feature", strategy="build", orchestrator=orch, execute=False
    )
    lc.request_cancel(rec.run_id)
    out = orch.run(rec.run_id)
    assert out["state"] == "cancelled" or out.get("note") == "cancelled"
