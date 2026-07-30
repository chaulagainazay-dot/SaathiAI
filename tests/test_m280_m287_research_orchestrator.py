"""M280–M287 Autonomous Research Orchestrator tests.

RESEARCH ONLY. No brokers. No orders. No live trading.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from saathi.platform.tg.research_orchestrator.errors import OrchestratorError
from saathi.platform.tg.research_orchestrator.models import (
    BROKER_CONNECTIVITY_AUTHORIZED,
    LIVE_TRADING_AUTHORIZED,
    ORDER_EXECUTION_AUTHORIZED,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.research_orchestrator.service import (
    ResearchOrchestratorService,
    reset_research_orchestrator_for_tests,
)


@pytest.fixture()
def svc(tmp_path: Path):
    return reset_research_orchestrator_for_tests(db_path=tmp_path / "orch_test.db")


def test_authority_locks_false():
    assert LIVE_TRADING_AUTHORIZED is False
    assert BROKER_CONNECTIVITY_AUTHORIZED is False
    assert ORDER_EXECUTION_AUTHORIZED is False


def test_enqueue_priority_and_tick(svc: ResearchOrchestratorService):
    low = svc.enqueue_job("low", {"kind": "noop", "seed": 1}, priority="LOW")
    high = svc.enqueue_job("high", {"kind": "noop", "seed": 2}, priority="HIGH")
    assert low["ok"] and high["ok"]
    nxt = svc.queue.peek_next()
    assert nxt["job_id"] == high["job_id"]  # HIGH before LOW
    tick = svc.tick(max_jobs=2)
    assert len(tick["ran"]) == 2
    assert all(r["state"] == "SUCCEEDED" for r in tick["ran"])


def test_dependencies_unblock_in_same_tick(svc: ResearchOrchestratorService):
    a = svc.enqueue_job("parent", {"kind": "noop", "seed": 1})
    b = svc.enqueue_job("child", {"kind": "noop", "seed": 2}, depends_on=[a["job_id"]])
    assert b["state"] == "BLOCKED"
    svc.tick(max_jobs=5)
    assert svc.get_job(a["job_id"])["state"] == "SUCCEEDED"
    assert svc.get_job(b["job_id"])["state"] == "SUCCEEDED"


def test_cancel_suspend_resume(svc: ResearchOrchestratorService):
    j = svc.enqueue_job("cancel_me", {"kind": "noop", "seed": 3}, priority="BACKGROUND")
    c = svc.cancel_job(j["job_id"])
    assert c["state"] == "CANCELLED"
    s = svc.enqueue_job("suspend_me", {"kind": "noop", "seed": 4})
    sus = svc.suspend_job(s["job_id"])
    assert sus["state"] == "SUSPENDED"
    res = svc.resume_job(s["job_id"])
    assert res["state"] == "QUEUED"


def test_retry_then_fail(svc: ResearchOrchestratorService):
    j = svc.enqueue_job("fail_me", {"kind": "fail_probe", "seed": 1}, max_retries=1)
    t1 = svc.tick(max_jobs=1)
    assert t1["ran"][0]["state"] == "RETRYING" or svc.get_job(j["job_id"])["state"] in ("QUEUED", "RETRYING")
    svc.tick(max_jobs=2)
    final = svc.get_job(j["job_id"])
    assert final["state"] == "FAILED"
    fa = svc.failure_analysis()
    assert fa["failed_count"] >= 1


def test_budget_exhausted(svc: ResearchOrchestratorService):
    with pytest.raises(OrchestratorError) as ei:
        svc.budget.reserve(10**9)
    assert ei.value.code == "BUDGET_EXHAUSTED"


def test_replay_immutable(svc: ResearchOrchestratorService):
    j = svc.enqueue_job("replay_me", {"kind": "noop", "seed": 7})
    svc.tick(max_jobs=1)
    rep = svc.replay_job(j["job_id"])
    assert rep["reproducible"] is True
    assert rep["result"]["ok"] is True


def test_templates_strategies_notebook(svc: ResearchOrchestratorService):
    tpls = svc.list_templates()
    assert tpls["count"] >= 3
    strats = svc.list_strategies_v2()
    assert strats["count"] >= 1
    hyp = svc.create_hypothesis("test hypothesis")
    assert hyp["ok"]
    nb = svc.notebook()
    assert nb["title"]


def test_bootstrap_and_certify(svc: ResearchOrchestratorService):
    pipe = svc.bootstrap_demo_pipeline()
    assert pipe["ok"] is True
    assert len(pipe["ran"]) >= 2
    cert = svc.certify()
    assert cert["ok"] is True
    assert cert["verdict"] == TERMINAL_VERDICT


def test_refusals(svc: ResearchOrchestratorService):
    assert svc.refuse_broker()["refused"] is True
    assert svc.refuse_credentials("k")["refused"] is True
    assert svc.refuse_order()["refused"] is True
    assert svc.refuse_canary()["refused"] is True
