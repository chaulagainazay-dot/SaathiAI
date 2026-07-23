"""M49.3 action-specific connector authority."""
from __future__ import annotations

import time

from saathi.tool_runtime.contracts import (
    ToolApprovalReference,
    ToolExecutionRequest,
    ToolOutcomeClass,
)
from saathi.tool_runtime.durable_idempotency import DurableIdempotencyStore
from saathi.tool_runtime.gateway_audit import audit_connectors
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.tool_runtime.service import ToolExecutionService


def _svc(tmp_path):
    return ToolExecutionService(
        registry=reset_registry_for_tests(),
        idempotency=DurableIdempotencyStore(tmp_path / "i.db"),
    )


def test_connector_audit_no_generic_executor():
    reset_registry_for_tests()
    report = audit_connectors()
    assert report["generic_connector_execution"] == "ABSENT"
    assert report["status"] == "PASS"
    assert report["mutation_mode"] == "DRY_RUN_ONLY"
    assert report["connector_actions"] >= 5


def test_gmail_search_read_fixture():
    svc = _svc
    from pathlib import Path
    import tempfile

    # use service without tmp for read-only
    svc = ToolExecutionService(registry=reset_registry_for_tests())
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gmail.search_messages",
            arguments={"query": "test", "limit": 2},
        )
    )
    assert r.ok
    assert r.data["fixture"] is True
    assert r.authority_class == "READ_ONLY"


def test_github_read_repository_fixture():
    svc = ToolExecutionService(registry=reset_registry_for_tests())
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.github.read_repository",
            arguments={"repo": "example/repo"},
        )
    )
    assert r.ok
    assert r.data["action"] == "read_repository"
    assert r.data["network_performed"] is False


def test_no_generic_connector_execute_tool():
    svc = ToolExecutionService(registry=reset_registry_for_tests())
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gmail.execute",
            arguments={},
        )
    )
    assert r.error_code == "TOOL_NOT_FOUND"
    assert r.adapter_invoked is False


def test_raw_credential_argument_rejected(tmp_path):
    svc = _svc(tmp_path)
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gmail.search_messages",
            arguments={"query": "x", "access_token": "secret-token-value"},
        )
    )
    assert r.error_code == "TOOL_SECRET_POLICY_VIOLATION"
    assert r.adapter_invoked is False
