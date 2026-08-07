"""M49.1 — cancellation and timeout contracts."""
from __future__ import annotations

import time

from saathi.tool_runtime.contracts import ToolExecutionRequest, ToolOutcomeClass
from saathi.tool_runtime.idempotency import IdempotencyStore
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.tool_runtime.service import ToolExecutionService


def _svc():
    return ToolExecutionService(
        registry=reset_registry_for_tests(), idempotency=IdempotencyStore()
    )


def test_pre_cancel_blocks_start():
    svc = _svc()
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="c1", tool_id="m49.cooperative_cancel", arguments={"stages": 5}
        ),
        cancel_check=lambda: True,
    )
    assert r.outcome_class == ToolOutcomeClass.CANCELLED_CONFIRMED
    assert r.cancellation_confirmed is True
    assert r.adapter_invoked is False
    assert r.ok is False


def test_cooperative_cancel_during_adapter():
    svc = _svc()
    state = {"n": 0}

    def cancel_after_start():
        # First checks may be pre-start; after adapter begins, force cancel
        state["n"] += 1
        return state["n"] > 2

    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="c2",
            tool_id="m49.cooperative_cancel",
            arguments={"stages": 50},
            timeout_sec=5.0,
        ),
        cancel_check=cancel_after_start,
    )
    # Either cancelled during stages or completed if cancel too late — never success+cancel
    assert r.outcome_class != ToolOutcomeClass.SUCCESS_CONFIRMED or not r.cancellation_confirmed
    if r.cancellation_confirmed:
        assert r.outcome_class == ToolOutcomeClass.CANCELLED_CONFIRMED
        assert r.error_code == "TOOL_CANCELLED"


def test_timeout_not_reported_as_cancel():
    svc = _svc()
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="t1",
            tool_id="m49.timeout_demo",
            arguments={"sleep_ms": 500},
            timeout_sec=0.05,
            deadline=time.time() + 0.05,
        )
    )
    assert r.timeout_detected or r.outcome_class in (
        ToolOutcomeClass.TIMEOUT_CONFIRMED,
        ToolOutcomeClass.SIDE_EFFECT_UNKNOWN,
        ToolOutcomeClass.BLOCKED,
    )
    assert r.outcome_class != ToolOutcomeClass.CANCELLED_CONFIRMED
    assert r.outcome_class != ToolOutcomeClass.SUCCESS_CONFIRMED


def test_deadline_exceeded_before_start():
    svc = _svc()
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="t2",
            tool_id="m49.echo_readonly",
            arguments={"text": "x"},
            deadline=time.time() - 1,
        )
    )
    assert not r.ok
    assert r.adapter_invoked is False
    assert r.error_code in ("TOOL_DEADLINE_EXCEEDED", "TOOL_TIMEOUT")


def test_cancel_cannot_emit_success_status():
    svc = _svc()
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="c3", tool_id="m49.echo_readonly", arguments={"text": "x"}
        ),
        cancel_check=lambda: True,
    )
    assert r.status == "cancelled"
    assert r.outcome_class == ToolOutcomeClass.CANCELLED_CONFIRMED
