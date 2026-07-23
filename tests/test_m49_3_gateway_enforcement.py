"""M49.3 gateway enforcement and coverage audit."""
from __future__ import annotations

from saathi.execution import ExecutionGateway
from saathi.tool_runtime.contracts import ToolExecutionRequest, ToolOutcomeClass
from saathi.tool_runtime.gateway_audit import validate_tool_gateway_coverage
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.tool_runtime.service import ToolExecutionService


def test_gateway_audit_passes():
    reset_registry_for_tests()
    report = validate_tool_gateway_coverage()
    assert report["critical_count"] == 0
    assert report["status"] in ("PASS", "PARTIAL")
    assert report["manifest_count"] >= 20
    assert report["ok"] is True or report["status"] == "PASS"


def test_all_supported_manifests_validate():
    reg = reset_registry_for_tests()
    v = reg.validate_all()
    assert v["ok"] is True
    assert v["count"] >= 20


def test_unknown_tool_rejected():
    svc = ToolExecutionService(registry=reset_registry_for_tests())
    r = svc.execute_tool(
        ToolExecutionRequest(run_id="r", tool_id="m49.does_not_exist", arguments={})
    )
    assert r.outcome_class == ToolOutcomeClass.BLOCKED
    assert r.error_code == "TOOL_NOT_FOUND"
    assert r.adapter_invoked is False


def test_execute_registered_tool_is_canonical_path():
    reset_registry_for_tests()
    r = ExecutionGateway().execute_registered_tool(
        tool_id="m49.echo_readonly",
        arguments={"text": "hello"},
        run_id="gw",
    )
    assert r.ok
    assert r.data["echo"] == "hello"
    assert r.authority_class == "READ_ONLY"


def test_financial_execution_not_invoked():
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
