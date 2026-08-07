"""M49.2 migrated tools and connector fixtures."""
from __future__ import annotations

import time

from saathi.execution import ExecutionGateway
from saathi.tool_runtime.contracts import (
    ToolApprovalReference,
    ToolExecutionRequest,
    ToolOutcomeClass,
)
from saathi.tool_runtime.durable_idempotency import DurableIdempotencyStore
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.tool_runtime.service import ToolExecutionService


def _svc(tmp_path):
    return ToolExecutionService(
        registry=reset_registry_for_tests(),
        idempotency=DurableIdempotencyStore(tmp_path / "i.db"),
    )


def test_migrated_system_health(tmp_path):
    svc = _svc(tmp_path)
    r = svc.execute_tool(
        ToolExecutionRequest(run_id="r", tool_id="m49.system_health", arguments={})
    )
    assert r.ok
    assert "health" in r.data
    assert r.authority_class == "READ_ONLY"


def test_migrated_my_files_list(tmp_path):
    svc = _svc(tmp_path)
    r = svc.execute_tool(
        ToolExecutionRequest(run_id="r", tool_id="m49.my_files_list", arguments={})
    )
    assert r.ok
    assert "files" in r.data
    assert r.data["count"] >= 0


def test_migrated_list_tasks(tmp_path):
    svc = _svc(tmp_path)
    r = svc.execute_tool(
        ToolExecutionRequest(run_id="r", tool_id="m49.list_open_tasks", arguments={})
    )
    assert r.ok
    assert "open_tasks" in r.data


def test_local_artifact_write_requires_approval(tmp_path):
    svc = _svc(tmp_path)
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.local_artifact_write",
            arguments={"name": "a.txt", "content": "hi"},
            idempotency_key="art1",
        )
    )
    assert r.error_code == "TOOL_APPROVAL_REQUIRED"
    assert r.adapter_invoked is False


def test_local_artifact_write_ok(tmp_path):
    svc = _svc(tmp_path)
    ap = ToolApprovalReference(
        approval_id="ap",
        tool_id="m49.local_artifact_write",
        capability="write",
        run_id="r",
        side_effect_class="LOCAL_REVERSIBLE",
        expires_at=time.time() + 999,
    )
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.local_artifact_write",
            arguments={"name": "note.txt", "content": "hello"},
            approval_reference=ap,
            idempotency_key="art2",
            capability="write",
        )
    )
    assert r.ok
    assert r.data["written"] is True


def test_connector_gmail_search_fixture(tmp_path):
    svc = _svc(tmp_path)
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gmail.search_messages",
            arguments={"query": "is:unread", "limit": 2},
        )
    )
    assert r.ok
    assert r.data["fixture"] is True
    assert r.data["count"] >= 1


def test_connector_gcal_list_fixture(tmp_path):
    r = ExecutionGateway().execute_registered_tool(
        tool_id="m49.connector.gcal.list_events",
        arguments={"days": 2},
        run_id="r",
    )
    assert r.ok
    assert r.data["fixture"] is True


def test_gmail_send_stub_requires_approval(tmp_path):
    svc = _svc(tmp_path)
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gmail.send_message",
            arguments={"to": "a@example.test", "subject": "s", "body": "b"},
            idempotency_key="send1",
        )
    )
    assert r.error_code == "TOOL_APPROVAL_REQUIRED"
    assert r.adapter_invoked is False


def test_gmail_send_stub_with_approval_never_sends(tmp_path):
    svc = _svc(tmp_path)
    ap = ToolApprovalReference(
        approval_id="ap",
        tool_id="m49.connector.gmail.send_message",
        capability="write",
        run_id="r",
        side_effect_class="EXTERNAL_IRREVERSIBLE",
        expires_at=time.time() + 999,
    )
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gmail.send_message",
            arguments={"to": "a@example.test", "subject": "s", "body": "b"},
            approval_reference=ap,
            idempotency_key="send2",
            capability="write",
        )
    )
    assert r.ok
    assert r.data["sent"] is False
    assert r.data["stub"] is True


def test_financial_still_prohibited(tmp_path):
    svc = _svc(tmp_path)
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.financial_execution_stub",
            arguments={"symbol": "X"},
        )
    )
    assert r.outcome_class == ToolOutcomeClass.PROHIBITED
    assert r.adapter_invoked is False


def test_legacy_compat_bridge_system_health():
    from saathi.tools.registry import execute_tool

    # governance may allow system_health for USER; then canonical path
    out = execute_tool("system_health", {}, speaker_verified=True)
    assert "error" not in out or out.get("error") != "unknown tool"
    # if governance allows, should have health or canonical marker
    if "error" not in out:
        assert "health" in out or "_canonical_tool_id" in out or "status" in out
