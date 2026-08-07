"""M49.3 Trading Guardian boundary — advisory only, no live execution."""
from __future__ import annotations

import time

from saathi.tool_runtime.contracts import (
    ToolApprovalReference,
    ToolExecutionRequest,
    ToolOutcomeClass,
)
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.tool_runtime.service import ToolExecutionService
from saathi.tools.registry import execute_tool


def test_financial_execution_stub_prohibited():
    svc = ToolExecutionService(registry=reset_registry_for_tests())
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.financial_execution_stub",
            arguments={"symbol": "AAPL"},
        )
    )
    assert r.outcome_class == ToolOutcomeClass.PROHIBITED
    assert r.adapter_invoked is False


def test_approval_cannot_enable_financial_execution():
    svc = ToolExecutionService(registry=reset_registry_for_tests())
    ap = ToolApprovalReference(
        approval_id="ap",
        tool_id="m49.financial_execution_stub",
        capability="trade_execute",
        run_id="r",
        side_effect_class="FINANCIAL_EXECUTION",
        expires_at=time.time() + 999,
    )
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.financial_execution_stub",
            arguments={"symbol": "AAPL"},
            approval_reference=ap,
            capability="trade_execute",
        )
    )
    assert r.outcome_class == ToolOutcomeClass.PROHIBITED
    assert r.adapter_invoked is False


def test_generic_shell_cannot_call_trading():
    out = execute_tool(
        "run_shell",
        {"command": "trade --live buy AAPL"},
        speaker_verified=True,
    )
    assert out.get("blocked") is True


def test_financial_advisory_requires_approval_and_not_live():
    svc = ToolExecutionService(registry=reset_registry_for_tests())
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.financial_advisory_stub",
            arguments={"symbol": "AAPL"},
        )
    )
    assert r.error_code == "TOOL_APPROVAL_REQUIRED"
    ap = ToolApprovalReference(
        approval_id="ap",
        tool_id="m49.financial_advisory_stub",
        capability="read",
        run_id="r",
        side_effect_class="FINANCIAL_ADVISORY",
        expires_at=time.time() + 999,
    )
    r2 = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.financial_advisory_stub",
            arguments={"symbol": "AAPL"},
            approval_reference=ap,
            capability="read",
        )
    )
    assert r2.ok
    assert r2.data["live_execution"] is False
    assert r2.data["paper_only"] is True
