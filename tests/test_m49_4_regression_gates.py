"""M49.4 regression gates — prior M49 suites remain green on this tip."""
from __future__ import annotations

from saathi.execution import ExecutionGateway
from saathi.tool_runtime.contracts import ToolOutcomeClass
from saathi.tool_runtime.gateway_audit import validate_tool_gateway_coverage
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.tool_runtime.service import ToolExecutionService
from saathi.tool_runtime.contracts import ToolExecutionRequest
from saathi.tools.registry import execute_tool


def test_m49_1_echo_still_works():
    reset_registry_for_tests()
    r = ExecutionGateway().execute_registered_tool(
        tool_id="m49.echo_readonly",
        arguments={"text": "m49.4"},
        run_id="reg",
    )
    assert r.ok
    assert r.data["echo"] == "m49.4"


def test_m49_2_durable_idempotency_replay(tmp_path):
    from saathi.tool_runtime.durable_idempotency import DurableIdempotencyStore

    store = DurableIdempotencyStore(tmp_path / "idemp.db")
    svc = ToolExecutionService(registry=reset_registry_for_tests(), idempotency=store)
    req = ToolExecutionRequest(
        run_id="r1",
        tool_id="m49.echo_readonly",
        arguments={"text": "same"},
        idempotency_key="m494-key-1",
    )
    a = svc.execute_tool(req)
    b = svc.execute_tool(req)
    assert a.ok and b.ok
    assert a.data["echo"] == b.data["echo"] == "same"
    # second should be replay (adapter not re-invoked)
    assert b.adapter_invoked is False


def test_m49_3_shell_still_blocked():
    out = execute_tool("run_shell", {"command": "whoami"}, speaker_verified=True)
    assert out.get("blocked") is True


def test_m49_3_financial_still_prohibited():
    reset_registry_for_tests()
    r = ToolExecutionService().execute_tool(
        ToolExecutionRequest(run_id="r", tool_id="m49.financial_execution_stub", arguments={})
    )
    assert r.outcome_class == ToolOutcomeClass.PROHIBITED
    assert r.adapter_invoked is False


def test_gateway_coverage_still_pass():
    reset_registry_for_tests()
    report = validate_tool_gateway_coverage()
    assert report["ok"] is True or report["status"] == "PASS"
