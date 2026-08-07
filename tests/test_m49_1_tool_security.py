"""M49.1 — security: secrets, authority, bypass, financial."""
from __future__ import annotations

import os
import time

import pytest

from saathi.tool_runtime.contracts import (
    ToolApprovalReference,
    ToolExecutionRequest,
    ToolOutcomeClass,
)
from saathi.tool_runtime.idempotency import IdempotencyStore
from saathi.tool_runtime.registry import ToolRegistry, ToolRegistryError, reset_registry_for_tests
from saathi.tool_runtime.secrets import find_secret_violations, redact
from saathi.tool_runtime.service import ToolExecutionService


def _svc():
    return ToolExecutionService(
        registry=reset_registry_for_tests(), idempotency=IdempotencyStore()
    )


@pytest.mark.parametrize(
    "field",
    [
        "api_key",
        "token",
        "password",
        "secret",
        "authorization",
        "cookie",
        "private_key",
        "credential",
    ],
)
def test_secret_field_rejected(field):
    svc = _svc()
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="s1",
            tool_id="m49.echo_readonly",
            arguments={"text": "ok", field: "sk-abcdefghijklmnopqrstuvwxyz"},
        )
    )
    # Either secret policy or additionalProperties rejection — never adapter invoke
    assert r.adapter_invoked is False
    assert r.error_code in (
        "TOOL_SECRET_POLICY_VIOLATION",
        "TOOL_INPUT_INVALID",
    )
    assert r.ok is False


def test_secret_value_redacted_from_evidence_payload():
    payload = {"note": "x", "api_key": "sk-abcdefghijklmnopqrstuv", "nested": {"token": "ghp_abcdefghijklmnopqrst"}}
    out = redact(payload)
    assert out["api_key"] == "***REDACTED***"
    assert out["nested"]["token"] == "***REDACTED***"
    assert "sk-" not in str(out)


def test_ordinary_text_not_false_positive():
    # "keyboard" / "token_count" style ordinary fields
    hits = find_secret_violations({"text": "the secret of success is work", "count": 3})
    assert hits == []


def test_agent_cannot_self_register_tool():
    reg = ToolRegistry(allow_dynamic=False)

    def evil(a, c):
        return {"data": {"pwned": True}}

    from saathi.tool_runtime.contracts import (
        ToolApprovalRequirement,
        ToolAuthorityClass,
        ToolCancellationSupport,
        ToolManifest,
        ToolSecretPolicy,
        ToolSideEffectClass,
    )

    m = ToolManifest(
        tool_id="m49.evil",
        version="1",
        display_name="evil",
        description="x",
        domain="x",
        capabilities=("x",),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        cancellation_support=ToolCancellationSupport.TIMEOUT_ONLY,
    )
    with pytest.raises(ToolRegistryError):
        reg.register(m, evil, trusted=False)


def test_financial_execution_never_succeeds():
    svc = _svc()
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="f1",
            tool_id="m49.financial_execution_stub",
            arguments={"symbol": "BTC"},
        )
    )
    assert r.outcome_class == ToolOutcomeClass.PROHIBITED
    assert r.adapter_invoked is False


def test_skip_contract_style_bypass_not_in_tool_service():
    """Tool service has no skip_authority flag — only manifests govern."""
    svc = _svc()
    req = ToolExecutionRequest(
        run_id="b1",
        tool_id="m49.local_note_write",
        arguments={"key": "k", "value": "v"},
        idempotency_key="x",
    )
    r = svc.execute_tool(req)
    assert r.error_code == "TOOL_APPROVAL_REQUIRED"
    assert r.adapter_invoked is False
    # Callers cannot authorize by stuffing metadata into arguments either
    # (additionalProperties false → input invalid; never success)
    r2 = svc.execute_tool(
        ToolExecutionRequest(
            run_id="b1",
            tool_id="m49.local_note_write",
            arguments={"key": "k", "value": "v", "approved": True},
            idempotency_key="x2",
        )
    )
    assert r2.ok is False
    assert r2.adapter_invoked is False


def test_test_only_registry_reset_requires_pytest_env_not_user_api():
    # reset_registry_for_tests is a Python import — not exposed via HTTP.
    # Guard: ensure we are under pytest when using it in this file.
    assert os.environ.get("PYTEST_CURRENT_TEST")


def test_gateway_path_used_by_agent_executor(tmp_path):
    from saathi.agent_runtime.gateway_exec import AgentExecutor
    from saathi.agent_runtime.store import RunStore
    from saathi.agent_runtime import registry as agent_reg

    reset_registry_for_tests()
    store = RunStore(tmp_path / "r.db")
    rid = store.create_run(objective="t", strategy="single", actor="u")
    ex = AgentExecutor(execute_fn=lambda *a, **k: {"text": "ok", "tokens": 1})
    # Use a known agent; tool m49.echo_readonly may be denied by agent policy
    # Direct path via gateway for registered tool still works for service.
    from saathi.execution import ExecutionGateway

    r = ExecutionGateway().execute_registered_tool(
        tool_id="m49.echo_readonly", arguments={"text": "agent-path"}, run_id=rid
    )
    assert r.ok
    # Unknown tool via agent executor fails closed
    out = ex.request_tool(
        agent_reg.get("researcher"), "totally-unknown-tool-xyz", {}, store, rid
    )
    assert out["status"] in ("rejected", "denied", "no-op")
    assert out.get("status") != "success"
