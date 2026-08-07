"""M53 binding administration, runtime operations, and operator workflow."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from saathi.platform.agent_binding import PlatformAgentBinding
from saathi.platform.bindings import BindingAdministrationService
from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformExecutionState
from saathi.platform.operations import RuntimeOperationsService
from saathi.platform.runtime import PlatformAgentRuntime
from saathi.platform.service import reset_platform_for_tests
from saathi.platform.store import PlatformStore
from saathi.tool_runtime.registry import reset_registry_for_tests


@pytest.fixture()
def alpha(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "m53.db")
    owner = platform.bootstrap_owner_secure(
        email="owner@m53.local",
        name="Owner",
        password="OwnerPassw0rd!",
        org_name="M53 Org",
        workspace_name="M53 Workspace",
    )
    return platform, owner["token"], platform.require_context(owner["token"])


def _binding(alpha, *, agent_id="ops-agent", ceiling="LOCAL_MUTATION"):
    platform, _, owner_ctx = alpha
    return BindingAdministrationService(platform).create(
        owner_ctx,
        agent_id=agent_id,
        name="Operations agent",
        allowed_tools=["m49.echo_readonly", "m49.local_note_write"],
        allowed_capabilities=[],
        authority_ceiling=ceiling,
    )


def _waiting(alpha, binding):
    platform, token, _ = alpha
    with pytest.raises(PlatformContextError) as error:
        PlatformAgentRuntime(platform).execute_token(
            token=token,
            tool_id="m49.local_note_write",
            arguments={"key": "m53", "value": "pending"},
            capability="write",
            agent_id=binding.agent_id,
            binding_id=binding.binding_id,
            binding_version=binding.version,
            idempotency_key=f"waiting-{binding.binding_id}",
        )
    assert error.value.code == "APPROVAL_REQUIRED"
    return platform.store.list_platform_executions(
        binding_id=binding.binding_id
    )[0]


def test_binding_create_list_update_rotate_and_audit(alpha):
    platform, _, ctx = alpha
    service = BindingAdministrationService(platform)
    binding = _binding(alpha)
    assert service.inspect(ctx, binding.binding_id).agent_id == "ops-agent"
    assert binding.binding_id in {item.binding_id for item in service.list(ctx)}

    updated = service.update(
        ctx,
        binding.binding_id,
        {"description": "bounded runtime operator", "allowed_tools": ["m49.echo_readonly"]},
    )
    assert updated.version == binding.version + 1
    assert updated.allowed_tools == ["m49.echo_readonly"]
    rotated = service.rotate(ctx, binding.binding_id)
    assert rotated.version == updated.version + 1
    events = {item["event"] for item in platform.store.list_audit(org_id=ctx.org_id)}
    assert {"binding.created", "binding.updated", "binding.rotated"} <= events


def test_m53_schema_migration_is_restart_safe(tmp_path):
    path = tmp_path / "restart-safe.db"
    first = PlatformStore(path)
    execution_columns = {
        row[1]
        for row in first._conn.execute(
            "PRAGMA table_info(platform_executions)"
        ).fetchall()
    }
    first.close()
    second = PlatformStore(path)
    tables = {
        row[0]
        for row in second._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"binding_id", "binding_version"} <= execution_columns
    assert {"platform_agent_bindings", "runtime_reconciliations"} <= tables
    second.close()


def test_binding_lifecycle_suspended_fails_closed_and_revoked_is_immutable(alpha):
    platform, token, ctx = alpha
    service = BindingAdministrationService(platform)
    binding = _binding(alpha)
    suspended = service.suspend(ctx, binding.binding_id)
    with pytest.raises(PlatformContextError) as blocked:
        PlatformAgentBinding(platform).execute(
            token=token,
            tool_id="m49.echo_readonly",
            agent_id=binding.agent_id,
            binding_id=binding.binding_id,
            binding_version=suspended.version,
        )
    assert blocked.value.code == "BINDING_SUSPENDED"
    active = service.activate(ctx, binding.binding_id)
    assert active.state == "ACTIVE"
    revoked = service.revoke(ctx, binding.binding_id)
    assert revoked.state == "REVOKED"
    with pytest.raises(PlatformContextError) as immutable:
        service.activate(ctx, binding.binding_id)
    assert immutable.value.code == "BINDING_REVOKED"


def test_stale_binding_version_and_duplicate_identity_rejected(alpha):
    platform, token, ctx = alpha
    service = BindingAdministrationService(platform)
    binding = _binding(alpha)
    service.rotate(ctx, binding.binding_id)
    with pytest.raises(PlatformContextError) as stale:
        PlatformAgentBinding(platform).execute(
            token=token,
            tool_id="m49.echo_readonly",
            agent_id=binding.agent_id,
            binding_id=binding.binding_id,
            binding_version=binding.version,
        )
    assert stale.value.code == "BINDING_VERSION_STALE"
    with pytest.raises(PlatformContextError) as duplicate:
        _binding(alpha)
    assert duplicate.value.code == "BINDING_IDENTITY_EXISTS"


def test_binding_authority_and_role_permissions_fail_closed(alpha):
    platform, _, ctx = alpha
    with pytest.raises(PlatformContextError) as financial:
        _binding(alpha, agent_id="financial-agent", ceiling="FINANCIAL_EXECUTION")
    assert financial.value.code == "BINDING_AUTHORITY_INVALID"

    invitation = platform.create_invitation(
        ctx, email="viewer@m53.local", role="viewer"
    )
    viewer = platform.accept_invitation(
        invite_code=invitation["invite_code"],
        name="Viewer",
        password="ViewerPassw0rd!",
    )
    viewer_ctx = platform.require_context(viewer["token"])
    with pytest.raises(PlatformContextError) as denied:
        BindingAdministrationService(platform).create(
            viewer_ctx, agent_id="viewer-agent", name="No"
        )
    assert denied.value.code == "PERMISSION_DENIED"


def test_runtime_list_filter_inspect_timeline_attention_and_metrics(alpha):
    platform, token, ctx = alpha
    binding = _binding(alpha)
    complete = PlatformAgentRuntime(platform).execute_token(
        token=token,
        tool_id="m49.echo_readonly",
        arguments={"text": "observable"},
        agent_id=binding.agent_id,
        binding_id=binding.binding_id,
        binding_version=binding.version,
    )
    waiting = _waiting(alpha, binding)
    ops = RuntimeOperationsService(platform)
    listed = ops.list_executions(ctx, binding_id=binding.binding_id)
    assert {item["execution_id"] for item in listed} == {
        complete.platform_execution_id,
        waiting.execution_id,
    }
    detail = ops.inspect(ctx, complete.platform_execution_id)
    assert "arguments_json" not in detail
    assert detail["idempotency"]["present"] is False
    timeline = ops.timeline(ctx, complete.platform_execution_id)
    assert any(item["event_type"] == "runtime.lifecycle_transition" for item in timeline)
    attention = ops.attention(ctx)
    assert attention[0]["attention_reasons"] == ["APPROVAL_REQUIRED"]
    metrics = ops.metrics(ctx)
    assert metrics["total_executions"] == 2
    assert metrics["completed_executions"] == 1
    assert metrics["waiting_approvals"] == 1


def test_safe_cancel_duplicate_reconciliation_and_terminal_immutability(alpha):
    platform, token, ctx = alpha
    waiting = _waiting(alpha, _binding(alpha))
    ops = RuntimeOperationsService(platform)
    reconciled = ops.reconcile(
        ctx,
        token=token,
        execution_id=waiting.execution_id,
        action="CANCEL_BEFORE_DISPATCH",
        idempotency_key="cancel-once",
        note="Owner confirmed cancellation",
    )
    assert reconciled["execution"]["state"] == "CANCELLED"
    with pytest.raises(PlatformContextError) as duplicate:
        ops.reconcile(
            ctx,
            token=token,
            execution_id=waiting.execution_id,
            action="MARK_REVIEWED",
            idempotency_key="cancel-once",
        )
    assert duplicate.value.code == "RECONCILIATION_DUPLICATE"
    with pytest.raises(PlatformContextError) as terminal:
        ops.reconcile(
            ctx,
            token=token,
            execution_id=waiting.execution_id,
            action="RESOLVE_FAILED",
            idempotency_key="mutate-terminal",
        )
    assert terminal.value.code == "TERMINAL_IMMUTABLE"


def test_uncertain_dispatch_never_resumes(alpha):
    platform, token, ctx = alpha
    waiting = _waiting(alpha, _binding(alpha))
    running = platform.store.transition_platform_execution(
        waiting.execution_id,
        PlatformExecutionState.READY,
    )
    running = platform.store.transition_platform_execution(
        running.execution_id,
        PlatformExecutionState.RUNNING,
        dispatch_started=True,
    )
    paused = platform.store.transition_platform_execution(
        running.execution_id,
        PlatformExecutionState.PAUSED,
        error_code="dispatch_recorded_manual_review",
    )
    ops = RuntimeOperationsService(platform)
    assert "DISPATCH_OUTCOME_UNCERTAIN" in ops.inspect(
        ctx, paused.execution_id
    )["attention_reasons"]
    with pytest.raises(PlatformContextError) as blocked:
        ops.reconcile(
            ctx,
            token=token,
            execution_id=paused.execution_id,
            action="RESUME",
            idempotency_key="never-replay",
        )
    assert blocked.value.code == "DISPATCH_OUTCOME_UNCERTAIN"


def test_timeout_resolution_and_operator_note(alpha):
    platform, token, ctx = alpha
    waiting = _waiting(alpha, _binding(alpha))
    platform.store.update_platform_execution_metadata(
        waiting.execution_id, deadline_at=platform.store._now() - 1
    )
    ops = RuntimeOperationsService(platform)
    resolved = ops.reconcile(
        ctx,
        token=token,
        execution_id=waiting.execution_id,
        action="CONFIRM_TIMEOUT",
        idempotency_key="confirm-timeout",
        note="deadline reviewed token=supersecretvalue12345",
        evidence_reference="audit:deadline",
    )
    assert resolved["execution"]["state"] == "TIMED_OUT"
    assert "supersecretvalue12345" not in resolved["reconciliation"]["note"]
    assert "[REDACTED]" in resolved["reconciliation"]["note"]
    timeline = ops.timeline(ctx, waiting.execution_id)
    assert any(item["operator_note_reference"] for item in timeline)


def test_cross_workspace_isolation_and_revoked_session(alpha):
    platform, token, ctx = alpha
    result = PlatformAgentRuntime(platform).execute_token(
        token=token, tool_id="m49.echo_readonly", arguments={"text": "private"}
    )
    other = platform.store.create_workspace(
        ctx.org_id, "Other workspace", ctx.user_id
    )
    switched = platform.select_workspace(
        token, org_id=ctx.org_id, workspace_id=other.workspace_id
    )
    other_ctx = platform.require_context(switched["token"])
    with pytest.raises(PlatformContextError) as hidden:
        RuntimeOperationsService(platform).inspect(
            other_ctx, result.platform_execution_id
        )
    assert hidden.value.code == "EXECUTION_NOT_FOUND"
    platform.logout(switched["token"])
    with pytest.raises(PlatformContextError) as revoked:
        RuntimeOperationsService(platform).context(switched["token"])
    assert revoked.value.code == "SESSION_INVALID"


def test_full_owner_operator_workflow(alpha):
    platform, owner_token, owner_ctx = alpha
    binding = _binding(alpha, agent_id="workflow-agent")
    invitation = platform.create_invitation(
        owner_ctx, email="operator@m53.local", role="operator"
    )
    operator = platform.accept_invitation(
        invite_code=invitation["invite_code"],
        name="Operator",
        password="OperatorPassw0rd!",
    )
    operator_token = operator["token"]
    operator_ctx = platform.require_context(operator_token)
    waiting = None
    with pytest.raises(PlatformContextError) as required:
        PlatformAgentRuntime(platform).execute_token(
            token=operator_token,
            tool_id="m49.local_note_write",
            arguments={"key": "workflow", "value": "approved"},
            capability="write",
            agent_id=binding.agent_id,
            binding_id=binding.binding_id,
            binding_version=binding.version,
            idempotency_key="m53-workflow",
        )
    assert required.value.code == "APPROVAL_REQUIRED"
    waiting = platform.store.list_platform_executions(
        binding_id=binding.binding_id
    )[0]
    assert RuntimeOperationsService(platform).attention(owner_ctx)[0][
        "execution_id"
    ] == waiting.execution_id

    approval = platform.request_approval(
        operator_ctx,
        tool_id="m49.local_note_write",
        capability="write",
        side_effect_class="LOCAL_REVERSIBLE",
        authority="LOCAL_MUTATION",
        ttl_sec=600,
    )
    platform.decide_approval(owner_ctx, approval.approval_id, approve=True)
    completed = RuntimeOperationsService(platform).reconcile(
        owner_ctx,
        token=owner_token,
        execution_id=waiting.execution_id,
        action="RESUME",
        idempotency_key="workflow-resume",
        approval_id=approval.approval_id,
    )
    assert completed["execution"]["execution_state"] == "COMPLETED"
    assert RuntimeOperationsService(platform).timeline(
        owner_ctx, waiting.execution_id
    )
    audit = platform.store.list_audit(org_id=owner_ctx.org_id, limit=200)
    assert any(item["event"] == "runtime.reconciliation_accepted" for item in audit)


def test_m53_api_surfaces(tmp_path, monkeypatch):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "m53-api.db")
    owner = platform.bootstrap_owner_secure(
        email="api@m53.local", name="API", password="ApiPassw0rd!"
    )
    import saathi.platform.api as api_module
    import saathi.platform.service as service_module

    monkeypatch.setattr(service_module, "_DEFAULT", platform)
    monkeypatch.setattr(api_module, "default_platform", lambda: platform)
    from saathi.server import app

    client = TestClient(app)
    headers = {"X-Platform-Token": owner["token"]}
    created = client.post(
        "/api/v1/platform/agent-bindings",
        headers=headers,
        json={
            "agent_id": "api-agent",
            "name": "API agent",
            "allowed_tools": ["m49.echo_readonly"],
            "authority_ceiling": "READ_ONLY",
        },
    )
    assert created.status_code == 200, created.text
    binding = created.json()["binding"]
    assert client.get(
        "/api/v1/platform/agent-bindings", headers=headers
    ).status_code == 200
    executed = client.post(
        "/api/v1/platform/agent/execute",
        headers=headers,
        json={
            "tool_id": "m49.echo_readonly",
            "arguments": {"text": "api"},
            "agent_id": binding["agent_id"],
            "binding_id": binding["binding_id"],
            "binding_version": binding["version"],
        },
    )
    assert executed.status_code == 200, executed.text
    execution_id = executed.json()["execution_id"]
    assert client.get(
        "/api/v1/platform/runtime/executions", headers=headers
    ).status_code == 200
    assert client.get(
        f"/api/v1/platform/runtime/executions/{execution_id}/timeline",
        headers=headers,
    ).status_code == 200
    assert client.get(
        "/api/v1/platform/runtime/metrics", headers=headers
    ).json()["metrics"]["completed_executions"] == 1
