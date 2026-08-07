"""M52 canonical platform-agent runtime, security, lifecycle, and recovery."""
from __future__ import annotations

import threading
import time

import pytest

from saathi.platform.agent_binding import PlatformAgentBinding
from saathi.platform.context import PlatformContextError
from saathi.platform.models import (
    PlatformExecutionRecord,
    PlatformExecutionState,
    new_id,
)
from saathi.platform.runtime import PlatformAgentRuntime
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.contracts import ToolExecutionResult, ToolOutcomeClass
from saathi.tool_runtime.registry import reset_registry_for_tests


@pytest.fixture()
def alpha(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "m52.db")
    boot = platform.bootstrap_owner_secure(
        email="owner@m52.local", name="Owner", password="GoodPassw0rd!"
    )
    return platform, boot["token"]


def _ctx(alpha):
    platform, token = alpha
    return platform, token, platform.require_context(token)


def _approved_note(platform, ctx):
    approval = platform.request_approval(
        ctx,
        tool_id="m49.local_note_write",
        action="write",
        capability="write",
        side_effect_class="LOCAL_REVERSIBLE",
        authority="LOCAL_MUTATION",
        ttl_sec=600,
    )
    platform.decide_approval(ctx, approval.approval_id, approve=True)
    return approval


def _result(
    *,
    status="completed",
    outcome=ToolOutcomeClass.SUCCESS_CONFIRMED,
    cancelled=False,
    timed_out=False,
):
    return ToolExecutionResult(
        tool_id="m49.echo_readonly",
        tool_version="1.0.0",
        call_id="fake-call",
        status=status,
        outcome_class=outcome,
        data={"echo": "fake"} if outcome == ToolOutcomeClass.SUCCESS_CONFIRMED else {},
        safe_message="fake",
        cancellation_confirmed=cancelled,
        timeout_detected=timed_out,
        adapter_invoked=outcome == ToolOutcomeClass.SUCCESS_CONFIRMED,
    )


def test_complete_platform_agent_execution_and_audit(alpha):
    platform, token, ctx = _ctx(alpha)
    result = PlatformAgentRuntime(platform).execute_token(
        token=token,
        tool_id="m49.echo_readonly",
        arguments={"text": "m52"},
        idempotency_key="m52-complete",
    )
    assert result.ok
    assert result.data["echo"] == "m52"
    rec = platform.store.get_platform_execution(result.platform_execution_id)
    assert rec.state == PlatformExecutionState.COMPLETED.value
    events = platform.store.list_audit(org_id=ctx.org_id, limit=100)
    names = {event["event"] for event in events}
    assert {
        "runtime.execution_requested",
        "runtime.context_accepted",
        "runtime.dispatch_started",
        "runtime.gateway_accepted",
        "runtime.completion",
    } <= names


def test_approval_required_rejected_expired_and_replay(alpha):
    platform, token, ctx = _ctx(alpha)
    runtime = PlatformAgentRuntime(platform)
    with pytest.raises(PlatformContextError) as missing:
        runtime.execute_token(
            token=token,
            tool_id="m49.local_note_write",
            arguments={"key": "k", "value": "v"},
        )
    assert missing.value.code == "APPROVAL_REQUIRED"
    assert platform.store.list_platform_executions()[0].state == "WAITING_APPROVAL"

    rejected = platform.request_approval(
        ctx, tool_id="m49.local_note_write", capability="write", ttl_sec=600
    )
    platform.decide_approval(ctx, rejected.approval_id, approve=False)
    with pytest.raises(PlatformContextError) as denied:
        runtime.execute_token(
            token=token,
            tool_id="m49.local_note_write",
            arguments={"key": "k", "value": "v"},
            approval_id=rejected.approval_id,
            capability="write",
        )
    assert denied.value.code == "APPROVAL_REJECTED"

    expired = platform.request_approval(
        ctx, tool_id="m49.local_note_write", capability="write", ttl_sec=-1
    )
    with pytest.raises(PlatformContextError) as stale:
        runtime.execute_token(
            token=token,
            tool_id="m49.local_note_write",
            arguments={"key": "k", "value": "v"},
            approval_id=expired.approval_id,
            capability="write",
        )
    assert stale.value.code in {"APPROVAL_EXPIRED", "APPROVAL_NOT_APPROVED"}

    approved = _approved_note(platform, ctx)
    first = runtime.execute_token(
        token=token,
        tool_id="m49.local_note_write",
        arguments={"key": "once", "value": "v"},
        approval_id=approved.approval_id,
        capability="write",
    )
    assert first.ok
    with pytest.raises(PlatformContextError) as replay:
        runtime.execute_token(
            token=token,
            tool_id="m49.local_note_write",
            arguments={"key": "twice", "value": "v"},
            approval_id=approved.approval_id,
            capability="write",
        )
    assert replay.value.code == "APPROVAL_REPLAY"


def test_approval_is_claimed_once_before_concurrent_dispatch(alpha):
    platform, token, ctx = _ctx(alpha)
    approval = _approved_note(platform, ctx)
    started = threading.Event()
    release = threading.Event()

    class Gate:
        calls = 0

        def execute_registered_tool(self, **kwargs):
            Gate.calls += 1
            started.set()
            assert release.wait(2)
            result = _result()
            result.tool_id = "m49.local_note_write"
            return result

    runtime = PlatformAgentRuntime(platform, gateway_factory=Gate)
    holder = {}

    def first_dispatch():
        holder["result"] = runtime.execute_token(
            token=token,
            tool_id="m49.local_note_write",
            arguments={"key": "one", "value": "v"},
            approval_id=approval.approval_id,
            capability="write",
        )

    thread = threading.Thread(target=first_dispatch)
    thread.start()
    assert started.wait(2)
    with pytest.raises(PlatformContextError) as replay:
        runtime.execute_token(
            token=token,
            tool_id="m49.local_note_write",
            arguments={"key": "two", "value": "v"},
            approval_id=approval.approval_id,
            capability="write",
        )
    assert replay.value.code == "APPROVAL_REPLAY"
    release.set()
    thread.join(3)
    assert holder["result"].ok
    assert Gate.calls == 1


def test_context_spoof_suspension_and_revocation_fail_closed(alpha):
    platform, token, ctx = _ctx(alpha)
    ctx.user_id = "usr_spoofed"
    with pytest.raises(PlatformContextError) as spoof:
        platform.execute_tool(
            ctx, tool_id="m49.echo_readonly", arguments={"text": "x"}
        )
    assert spoof.value.code == "CONTEXT_CONTRADICTORY"

    ctx = platform.require_context(token)
    platform.store.set_member_status(ctx.org_id, ctx.user_id, "suspended")
    with pytest.raises(PlatformContextError) as suspended:
        PlatformAgentRuntime(platform).execute_token(
            token=token, tool_id="m49.echo_readonly", arguments={"text": "x"}
        )
    assert suspended.value.code == "MEMBERSHIP_REVOKED"

    platform.store.set_member_status(ctx.org_id, ctx.user_id, "active")
    stale_ctx = platform.require_context(token)
    platform.store.revoke_session(stale_ctx.session_id, reason="test")
    with pytest.raises(PlatformContextError) as revoked:
        platform.execute_tool(
            stale_ctx, tool_id="m49.echo_readonly", arguments={"text": "x"}
        )
    assert revoked.value.code == "SESSION_INVALID"


def test_agent_binding_and_tenant_scope_mismatches(alpha):
    platform, token, ctx = _ctx(alpha)
    with pytest.raises(PlatformContextError) as binding:
        PlatformAgentRuntime(platform).execute_token(
            token=token,
            tool_id="m49.echo_readonly",
            arguments={"text": "x"},
            agent_id="client-supplied-agent",
        )
    assert binding.value.code == "AGENT_BINDING_MISMATCH"

    other_user = platform.store.create_user(email="other@m52.local", name="Other")
    other_org = platform.store.create_org("Other Org", other_user.user_id)
    other_ws = platform.store.create_workspace(
        other_org.org_id, "Other WS", other_user.user_id
    )
    other_project = platform.store.create_project(
        workspace_id=other_ws.workspace_id,
        org_id=other_org.org_id,
        name="Foreign",
        owner_id=other_user.user_id,
    )
    with pytest.raises(PlatformContextError) as cross_org:
        PlatformAgentRuntime(platform).execute_token(
            token=token,
            tool_id="m49.echo_readonly",
            arguments={"text": "x"},
            project_id=other_project.project_id,
        )
    assert cross_org.value.code == "PROJECT_ISOLATION"

    second_ws = platform.store.create_workspace(ctx.org_id, "Second", ctx.user_id)
    second_project = platform.store.create_project(
        workspace_id=second_ws.workspace_id,
        org_id=ctx.org_id,
        name="Other workspace",
        owner_id=ctx.user_id,
    )
    with pytest.raises(PlatformContextError) as cross_ws:
        PlatformAgentRuntime(platform).execute_token(
            token=token,
            tool_id="m49.echo_readonly",
            arguments={"text": "x"},
            project_id=second_project.project_id,
        )
    assert cross_ws.value.code == "PROJECT_ISOLATION"


def test_project_mission_and_approval_scope_isolation(alpha):
    platform, token, ctx = _ctx(alpha)
    p1 = platform.create_project(ctx, "P1")
    p2 = platform.create_project(ctx, "P2")
    m1 = platform.create_mission(ctx, p1["project_id"], "m1", "M1")
    with pytest.raises(PlatformContextError) as cross_mission:
        PlatformAgentRuntime(platform).execute_token(
            token=token,
            tool_id="m49.echo_readonly",
            arguments={"text": "x"},
            project_id=p2["project_id"],
            mission_id=m1["mission_id"],
        )
    assert cross_mission.value.code == "MISSION_PROJECT_MISMATCH"

    scoped_ctx = platform.require_context(
        token, project_id=p1["project_id"], mission_id=m1["mission_id"]
    )
    approval = _approved_note(platform, scoped_ctx)
    with pytest.raises(PlatformContextError) as cross_project:
        PlatformAgentRuntime(platform).execute_token(
            token=token,
            tool_id="m49.local_note_write",
            arguments={"key": "x", "value": "x"},
            project_id=p2["project_id"],
            approval_id=approval.approval_id,
            capability="write",
        )
    assert cross_project.value.code == "APPROVAL_PROJECT_MISMATCH"


def test_runtime_idempotency_and_terminal_replay(alpha):
    platform, token, _ = _ctx(alpha)
    runtime = PlatformAgentRuntime(platform)
    first = runtime.execute_token(
        token=token,
        tool_id="m49.echo_readonly",
        arguments={"text": "same"},
        idempotency_key="same-key",
    )
    second = runtime.execute_token(
        token=token,
        tool_id="m49.echo_readonly",
        arguments={"text": "same"},
        idempotency_key="same-key",
    )
    assert second.ok
    assert second.platform_execution_id == first.platform_execution_id
    with pytest.raises(PlatformContextError) as conflict:
        runtime.execute_token(
            token=token,
            tool_id="m49.echo_readonly",
            arguments={"text": "different"},
            idempotency_key="same-key",
        )
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"


def test_approval_wait_survives_restart_and_duplicate_resume_replays(alpha):
    platform, token, _ = _ctx(alpha)
    runtime = PlatformAgentRuntime(platform)
    with pytest.raises(PlatformContextError):
        runtime.execute_token(
            token=token,
            tool_id="m49.local_note_write",
            arguments={"key": "resume", "value": "v"},
            run_id="run-resume",
        )
    waiting = platform.store.list_platform_executions()[0]
    assert PlatformAgentRuntime(platform).reconcile() == [
        {"execution_id": waiting.execution_id, "decision": "WAITING_APPROVAL"}
    ]
    approval_ctx = platform.require_context(token, run_id="run-resume")
    approval = _approved_note(platform, approval_ctx)
    resumed = PlatformAgentRuntime(platform).resume(
        token=token,
        execution_id=waiting.execution_id,
        approval_id=approval.approval_id,
    )
    assert resumed.ok
    assert resumed.platform_execution_id == waiting.execution_id
    replay = PlatformAgentRuntime(platform).resume(
        token=token,
        execution_id=waiting.execution_id,
        approval_id=approval.approval_id,
    )
    assert replay.ok
    assert replay.platform_execution_id == waiting.execution_id


def test_api_ignores_identity_and_authority_spoof_fields(alpha):
    platform, token, _ = _ctx(alpha)
    from saathi.platform.api import AgentExecuteBody, agent_execute

    response = agent_execute(
        AgentExecuteBody(
            tool_id="m49.echo_readonly",
            arguments={"text": "api"},
            user_id="usr_attacker",
            org_id="org_attacker",
            workspace_id="ws_attacker",
            role="system",
            authority="FINANCIAL_EXECUTION",
        ),
        authorization=None,
        x_platform_token=token,
    )
    assert response["ok"] is True
    assert response["data"]["echo"] == "api"
    assert set(response["spoof_fields_ignored"]) == {
        "user_id",
        "org_id",
        "workspace_id",
        "role",
        "authority",
    }
    rec = platform.store.get_platform_execution(response["execution_id"])
    trusted = platform.require_context(token)
    assert rec.user_id == trusted.user_id
    assert rec.org_id == trusted.org_id
    assert rec.workspace_id == trusted.workspace_id


def test_illegal_lifecycle_and_terminal_immutability(alpha):
    platform, _, ctx = _ctx(alpha)
    now = platform.store._now()
    rec = PlatformExecutionRecord(
        execution_id=new_id("pex_"),
        state="CREATED",
        user_id=ctx.user_id,
        session_id=ctx.session_id,
        org_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        project_id="",
        mission_id="",
        agent_id="platform-agent",
        run_id=new_id("run_"),
        tool_id="m49.echo_readonly",
        request_fingerprint="test",
        created_at=now,
        updated_at=now,
    )
    platform.store.create_platform_execution(rec)
    with pytest.raises(ValueError, match="illegal"):
        platform.store.transition_platform_execution(rec.execution_id, "COMPLETED")
    platform.store.transition_platform_execution(rec.execution_id, "CANCELLED")
    with pytest.raises(ValueError, match="immutable"):
        platform.store.transition_platform_execution(rec.execution_id, "FAILED")


def test_cancellation_before_dispatch_and_across_restart(alpha):
    platform, token, _ = _ctx(alpha)
    runtime = PlatformAgentRuntime(platform)
    with pytest.raises(PlatformContextError):
        runtime.execute_token(
            token=token,
            tool_id="m49.local_note_write",
            arguments={"key": "k", "value": "v"},
        )
    waiting = platform.store.list_platform_executions()[0]
    cancelled = runtime.cancel(token=token, execution_id=waiting.execution_id)
    assert cancelled.state == "CANCELLED"
    assert PlatformAgentRuntime(platform).reconcile() == []


def test_cooperative_cancellation_during_dispatch(alpha):
    platform, token, _ = _ctx(alpha)
    started = threading.Event()

    class BlockingGateway:
        def execute_registered_tool(self, **kwargs):
            started.set()
            for _ in range(200):
                if kwargs["cancel_check"]():
                    return _result(
                        status="cancelled",
                        outcome=ToolOutcomeClass.CANCELLED_CONFIRMED,
                        cancelled=True,
                    )
                time.sleep(0.005)
            raise AssertionError("cancel was not observed")

    runtime = PlatformAgentRuntime(platform, gateway_factory=BlockingGateway)
    holder = {}

    def execute():
        holder["result"] = runtime.execute_token(
            token=token,
            tool_id="m49.echo_readonly",
            arguments={"text": "wait"},
        )

    thread = threading.Thread(target=execute)
    thread.start()
    assert started.wait(2)
    running = platform.store.list_platform_executions()[0]
    runtime.cancel(token=token, execution_id=running.execution_id)
    thread.join(3)
    assert not thread.is_alive()
    assert holder["result"].platform_execution_state == "CANCELLED"


def test_timeout_maps_to_terminal_state(alpha):
    platform, token, _ = _ctx(alpha)

    class TimeoutGateway:
        def execute_registered_tool(self, **kwargs):
            assert kwargs["timeout_sec"] == 0.01
            return _result(
                status="timed_out",
                outcome=ToolOutcomeClass.TIMEOUT_CONFIRMED,
                timed_out=True,
            )

    result = PlatformAgentRuntime(
        platform, gateway_factory=TimeoutGateway
    ).execute_token(
        token=token,
        tool_id="m49.echo_readonly",
        arguments={"text": "timeout"},
        timeout_sec=0.01,
    )
    assert result.platform_execution_state == "TIMED_OUT"


def test_restart_reconciliation_never_replays_dispatch(alpha):
    platform, _, ctx = _ctx(alpha)
    now = platform.store._now()
    for state, dispatched in (("READY", False), ("RUNNING", True)):
        platform.store.create_platform_execution(
            PlatformExecutionRecord(
                execution_id=new_id("pex_"),
                state=state,
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                project_id="",
                mission_id="",
                agent_id="platform-agent",
                run_id=new_id("run_"),
                tool_id="m49.echo_readonly",
                request_fingerprint=new_id(),
                dispatch_started=dispatched,
                created_at=now,
                updated_at=now,
            )
        )
    decisions = PlatformAgentRuntime(platform).reconcile()
    assert {decision["decision"] for decision in decisions} == {"PAUSED"}
    records = platform.store.list_platform_executions()
    assert all(rec.state == "PAUSED" for rec in records)
    assert any(rec.error_code == "dispatch_recorded_manual_review" for rec in records)


def test_compatibility_wrapper_and_legacy_agent_bypass_prevention(alpha, tmp_path):
    platform, _, ctx = _ctx(alpha)
    result = platform.execute_tool(
        ctx, tool_id="m49.echo_readonly", arguments={"text": "compat"}
    )
    assert result.ok
    assert result.platform_execution_id

    from saathi.agent_runtime import registry as agent_registry
    from saathi.agent_runtime.gateway_exec import AgentExecutor
    from saathi.agent_runtime.store import RunStore

    store = RunStore(tmp_path / "agent.db")
    run_id = store.create_run(objective="m52", strategy="single", actor="u")
    out = AgentExecutor(execute_fn=lambda *a: {"text": "x"}).request_tool(
        agent_registry.get("researcher"), "file.read", {}, store, run_id
    )
    assert out["error_code"] == "PLATFORM_RUNTIME_REQUIRED"
    assert out["status"] == "rejected"


def test_connector_dry_run_and_trading_guardian_unengaged(alpha):
    platform, token, ctx = _ctx(alpha)
    approval = platform.request_approval(
        ctx,
        tool_id="m49.connector.gmail.send_message",
        action="send_message",
        capability="write",
        side_effect_class="EXTERNAL_IRREVERSIBLE",
        authority="EXTERNAL_MUTATION",
        connector="gmail",
        ttl_sec=600,
    )
    platform.decide_approval(ctx, approval.approval_id, approve=True)
    result = PlatformAgentBinding(platform).execute(
        token=token,
        tool_id="m49.connector.gmail.send_message",
        arguments={"to": "a@example.test", "subject": "s", "body": "b"},
        approval_id=approval.approval_id,
        capability="write",
        idempotency_key="m52-dry-run",
    )
    assert result.ok
    assert result.data["network_performed"] is False
    assert result.data["mutation_performed"] is False
    assert result.data["execution_mode"] == "DRY_RUN_ONLY"

    financial = PlatformAgentRuntime(platform).execute_token(
        token=token,
        tool_id="m49.financial_execution_stub",
        arguments={"symbol": "AAPL"},
    )
    assert financial.outcome_class == ToolOutcomeClass.PROHIBITED
    assert financial.adapter_invoked is False
    assert platform.configuration(ctx)["trading_guardian"] == "ADVISORY_ONLY"
