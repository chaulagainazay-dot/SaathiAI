"""M49.1 — ToolExecutionService happy path and gateway integration."""
from __future__ import annotations

import time

from saathi.execution import ExecutionGateway
from saathi.tool_runtime.contracts import (
    ToolApprovalReference,
    ToolExecutionRequest,
    ToolOutcomeClass,
)
from saathi.tool_runtime.idempotency import IdempotencyStore
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.tool_runtime.service import ToolExecutionService


def _svc():
    reg = reset_registry_for_tests()
    return ToolExecutionService(registry=reg, idempotency=IdempotencyStore())


def test_echo_readonly_success():
    svc = _svc()
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="run1", tool_id="m49.echo_readonly", arguments={"text": "hello"}
        )
    )
    assert r.ok
    assert r.outcome_class == ToolOutcomeClass.SUCCESS_CONFIRMED
    assert r.data["echo"] == "hello"
    assert r.adapter_invoked is True
    assert "tool.started" in r.events
    assert "tool.completed" in r.events
    assert r.authority_class == "READ_ONLY"


def test_invalid_input_before_adapter():
    svc = _svc()
    r = svc.execute_tool(
        ToolExecutionRequest(run_id="run1", tool_id="m49.echo_readonly", arguments={})
    )
    assert not r.ok
    assert r.error_code == "TOOL_INPUT_INVALID"
    assert r.adapter_invoked is False


def test_unknown_tool_rejected():
    svc = _svc()
    r = svc.execute_tool(
        ToolExecutionRequest(run_id="run1", tool_id="m49.no_such_tool", arguments={})
    )
    assert r.error_code == "TOOL_NOT_FOUND"
    assert r.adapter_invoked is False


def test_mutation_requires_approval():
    svc = _svc()
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="run1",
            tool_id="m49.local_note_write",
            arguments={"key": "k", "value": "v"},
            idempotency_key="ik1",
        )
    )
    assert r.error_code == "TOOL_APPROVAL_REQUIRED"
    assert r.adapter_invoked is False


def test_mutation_with_valid_approval():
    svc = _svc()
    ap = ToolApprovalReference(
        approval_id="ap-1",
        tool_id="m49.local_note_write",
        capability="write",
        run_id="run1",
        side_effect_class="LOCAL_REVERSIBLE",
        expires_at=time.time() + 3600,
        active=True,
    )
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="run1",
            tool_id="m49.local_note_write",
            arguments={"key": "k", "value": "v"},
            approval_reference=ap,
            idempotency_key="ik-ok",
            capability="write",
        )
    )
    assert r.ok
    assert r.data["written"] is True
    assert r.side_effect_confirmed is True


def test_expired_approval_blocks():
    svc = _svc()
    ap = ToolApprovalReference(
        approval_id="ap-x",
        tool_id="m49.local_note_write",
        capability="write",
        run_id="run1",
        side_effect_class="LOCAL_REVERSIBLE",
        expires_at=time.time() - 10,
    )
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="run1",
            tool_id="m49.local_note_write",
            arguments={"key": "k", "value": "v"},
            approval_reference=ap,
            idempotency_key="ik-exp",
        )
    )
    assert r.error_code == "TOOL_APPROVAL_EXPIRED"
    assert r.adapter_invoked is False


def test_revoked_approval_blocks():
    svc = _svc()
    ap = ToolApprovalReference(
        approval_id="ap-r",
        tool_id="m49.local_note_write",
        capability="write",
        run_id="run1",
        side_effect_class="LOCAL_REVERSIBLE",
        expires_at=time.time() + 1000,
        revoked=True,
    )
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="run1",
            tool_id="m49.local_note_write",
            arguments={"key": "k", "value": "v"},
            approval_reference=ap,
            idempotency_key="ik-rev",
        )
    )
    assert r.error_code == "TOOL_APPROVAL_REVOKED"


def test_gateway_execute_registered_tool():
    reset_registry_for_tests()
    gw = ExecutionGateway()
    r = gw.execute_registered_tool(
        tool_id="m49.echo_readonly",
        arguments={"text": "via-gw"},
        run_id="g1",
    )
    assert r.ok
    assert r.data["echo"] == "via-gw"


def test_caller_cannot_override_authority_via_request_fields():
    """Authority comes from manifest; request has no authority field power."""
    svc = _svc()
    req = ToolExecutionRequest(
        run_id="run1",
        tool_id="m49.echo_readonly",
        arguments={"text": "x"},
        _caller_authority_ignored="FINANCIAL_EXECUTION",
        _caller_side_effect_ignored="FINANCIAL_EXECUTION",
    )
    r = svc.execute_tool(req)
    assert r.ok
    assert r.authority_class == "READ_ONLY"
    assert r.side_effect_class == "NO_SIDE_EFFECT"


def test_financial_prohibited_adapter_not_invoked():
    svc = _svc()
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="run1",
            tool_id="m49.financial_execution_stub",
            arguments={"symbol": "AAPL"},
        )
    )
    assert r.outcome_class == ToolOutcomeClass.PROHIBITED
    assert r.error_code == "TOOL_FINANCIAL_EXECUTION_PROHIBITED"
    assert r.adapter_invoked is False
