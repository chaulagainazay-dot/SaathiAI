"""M49.2 security: connector secrets, no live send, registry seal."""
from __future__ import annotations

import time

from saathi.tool_runtime.contracts import ToolExecutionRequest, ToolOutcomeClass
from saathi.tool_runtime.durable_idempotency import DurableIdempotencyStore
from saathi.tool_runtime.registry import ToolRegistry, ToolRegistryError, reset_registry_for_tests
from saathi.tool_runtime.service import ToolExecutionService


def test_connector_rejects_raw_api_key(tmp_path):
    svc = ToolExecutionService(
        registry=reset_registry_for_tests(),
        idempotency=DurableIdempotencyStore(tmp_path / "i.db"),
    )
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gmail.search_messages",
            arguments={"query": "x", "api_key": "sk-abcdefghijklmnopqrstuvwxyz"},
        )
    )
    assert r.adapter_invoked is False
    assert r.error_code in ("TOOL_SECRET_POLICY_VIOLATION", "TOOL_INPUT_INVALID")


def test_no_generic_connector_execute_registered():
    reg = reset_registry_for_tests()
    assert reg.get_manifest("connector.execute_anything") is None
    assert reg.get_manifest("execute_anything") is None


def test_fingerprint_excludes_secrets_via_rejection(tmp_path):
    """Secret fields never enter successful fingerprint path."""
    svc = ToolExecutionService(
        registry=reset_registry_for_tests(),
        idempotency=DurableIdempotencyStore(tmp_path / "i.db"),
    )
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.echo_readonly",
            arguments={"text": "ok", "password": "secretvalue123"},
            idempotency_key="sec1",
        )
    )
    assert not r.ok
    assert r.adapter_invoked is False
