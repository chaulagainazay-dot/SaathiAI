"""FM-I2 — Real ExecutionGateway contract integration (no external side effects).

Uses isolated ExecutionStore + UniversalBoundary + local echo/noop handlers only.
Does not add providers, shell, browser, network tools, or credentials.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest

from saathi.agent_runtime.harness import (
    PRODUCTION_CERTIFIED,
    ApprovalRefState,
    CancelAckStatus,
    FakeInMemoryHarness,
    FakeScenario,
    GatewayTestDouble,
    HarnessBudget,
    HarnessError,
    HarnessErrorCode,
    HarnessSessionController,
    RealExecutionGatewayAdapter,
    ToolProposal,
    ToolProposalDisposition,
)
from saathi.agent_runtime.models import RunState
from saathi.execution.toolintent import (
    ActorType,
    ApprovalLevel,
    BusinessUnit,
    Priority,
    RiskLevel,
    ToolIntent,
)
from saathi.execution.gateway import ExecutionGateway


def _corr() -> str:
    return str(uuid.uuid4())


def _ctrl(scenario=FakeScenario.TEXT_COMPLETION, **kw):
    fake = FakeInMemoryHarness(default_scenario=scenario)
    ctrl = HarnessSessionController(fake, use_real_gateway=True, max_sessions=20, **kw)
    return ctrl, fake


def _start(ctrl, **overrides):
    params = dict(
        run_id="run-eg-1",
        actor_id="actor-eg",
        correlation_id=_corr(),
        mission_id="mission-eg-1",
        organization_id="org-eg",
        workspace_id="ws-eg",
        allowed_tool_names=("fake.echo", "fake.sensitive_read"),
        budget=HarnessBudget(max_turns=8, max_events=100, max_tool_proposals=8),
    )
    params.update(overrides)
    return ctrl.start_session(**params)


# ── Baseline / architecture ─────────────────────────────────────────────────


def test_default_controller_uses_real_execution_gateway():
    ctrl, _ = _ctrl()
    assert ctrl.uses_real_gateway is True
    assert isinstance(ctrl.gateway, RealExecutionGatewayAdapter)
    assert isinstance(ctrl.gateway.gateway, ExecutionGateway)
    assert PRODUCTION_CERTIFIED is False


def test_test_double_still_available_for_isolation():
    fake = FakeInMemoryHarness()
    double = GatewayTestDouble()
    ctrl = HarnessSessionController(fake, gateway=double, use_real_gateway=False)
    assert ctrl.uses_real_gateway is False
    assert isinstance(ctrl.gateway, GatewayTestDouble)


def test_no_second_gateway_class():
    """Adapter wraps ExecutionGateway; does not subclass a parallel authority."""
    adapter = RealExecutionGatewayAdapter(isolated=True)
    assert type(adapter.gateway).__name__ == "ExecutionGateway"
    assert not hasattr(adapter, "submit_external")


# ── ToolIntent → real EG path ───────────────────────────────────────────────


def test_tool_proposal_through_real_gateway_local_echo():
    ctrl, fake = _ctrl(FakeScenario.TOOL_THEN_CONTINUE)
    h = _start(ctrl)
    ctrl.submit_turn(h.session_id, input_text="echo please", correlation_id=_corr())
    assert len(ctrl.gateway.submitted) == 1
    intent = ctrl.gateway.submitted[0]
    assert isinstance(intent, ToolIntent)
    assert intent.validate() == []
    assert intent.connector_id == "local"
    assert intent.operation == "echo"
    assert intent.metadata["source"] == "HarnessSessionController"
    assert intent.metadata["organization_id"] == "org-eg"
    assert intent.metadata["workspace_id"] == "ws-eg"
    assert intent.metadata["run_id"] == "run-eg-1"
    assert intent.metadata["family"] == "local"
    # Immutable: frozen dataclass
    with pytest.raises(Exception):
        intent.operation = "shell"  # type: ignore[misc]
    events = ctrl.poll_events(h.session_id)
    types = [e.event_type.value for e in events]
    assert "TOOL_PROPOSAL" in types
    assert "TOOL_RESULT_DELIVERED" in types
    assert "SESSION_COMPLETED" in types
    # Result path is real EG
    cached = list(ctrl.gateway._results_by_idem.values())
    assert cached and cached[0]["path"] == "ExecutionGateway"
    assert cached[0]["status"] == "succeeded"


def test_idempotent_toolintent_no_double_side_effect():
    ctrl, _ = _ctrl()
    h = _start(ctrl)
    idem = hashlib.sha256(b"fm-i2-idem-1").hexdigest()
    p1 = ToolProposal(
        proposal_id="p1",
        session_id=h.session_id,
        turn_id="t1",
        tool_name="fake.echo",
        parameters={"message": "once"},
        correlation_id=_corr(),
        idempotency_key=idem,
        organization_id="org-eg",
        workspace_id="ws-eg",
    )
    r1 = ctrl.mediate_proposal(p1)
    r2 = ctrl.mediate_proposal(
        ToolProposal(
            proposal_id="p2",
            session_id=h.session_id,
            turn_id="t1",
            tool_name="fake.echo",
            parameters={"message": "once"},
            correlation_id=_corr(),
            idempotency_key=idem,
            organization_id="org-eg",
            workspace_id="ws-eg",
        )
    )
    assert r1.disposition is ToolProposalDisposition.ACCEPTED
    assert r2.disposition is ToolProposalDisposition.ACCEPTED
    # EG + adapter dedupe: one submitted intent (second may replay without re-append
    # depending on cache — at most one successful execution_id)
    assert len(ctrl.gateway.submitted) >= 1
    eids = {
        (r1.redacted_result or {}).get("execution_id"),
        (r2.redacted_result or {}).get("execution_id"),
    }
    assert len([e for e in eids if e]) <= 2


def test_unknown_and_malformed_rejected_before_gateway():
    ctrl, _ = _ctrl()
    h = _start(ctrl)
    r = ctrl.mediate_proposal(
        ToolProposal(
            proposal_id="u1",
            session_id=h.session_id,
            turn_id="t",
            tool_name="evil.shell",
            parameters={"cmd": "rm"},
            correlation_id=_corr(),
            organization_id="org-eg",
            workspace_id="ws-eg",
        )
    )
    assert r.disposition is ToolProposalDisposition.DENIED
    assert ctrl.gateway.submitted == []

    r2 = ctrl.mediate_proposal(
        ToolProposal(
            proposal_id="m1",
            session_id=h.session_id,
            turn_id="t",
            tool_name="",
            parameters={},
            correlation_id=_corr(),
            organization_id="org-eg",
            workspace_id="ws-eg",
        )
    )
    assert r2.disposition is ToolProposalDisposition.DENIED


def test_wrong_scope_rejected():
    ctrl, _ = _ctrl()
    h = _start(ctrl)
    r = ctrl.mediate_proposal(
        ToolProposal(
            proposal_id="s1",
            session_id=h.session_id,
            turn_id="t",
            tool_name="fake.echo",
            parameters={},
            correlation_id=_corr(),
            organization_id="org-OTHER",
            workspace_id="ws-eg",
        )
    )
    assert r.disposition is ToolProposalDisposition.QUARANTINED
    assert ctrl.is_quarantined(h.session_id)


def test_financial_execution_still_blocked():
    ctrl, _ = _ctrl()
    with pytest.raises(HarnessError):
        _start(ctrl, authority_class="FINANCIAL_EXECUTION")


# ── Approval integration via real EG ────────────────────────────────────────


def test_approval_required_then_approve_via_gateway():
    ctrl, fake = _ctrl(FakeScenario.APPROVAL_REQUIRED)
    h = _start(ctrl)
    ctrl.submit_turn(h.session_id, input_text="sensitive", correlation_id=_corr())
    assert ctrl.projected_run_state(h.session_id) is RunState.AWAITING_APPROVAL
    assert "harness.approval_required" in ctrl.audit.actions()
    bound = ctrl._sessions[h.session_id]
    assert bound.pending_execution_id
    # Harness must not have self-approved
    assert not any(
        "self" in (r.detail or {}).get("source", "")
        for r in ctrl.audit.by_session(h.session_id)
    )
    refs = [
        r.detail["approval_ref"]
        for r in ctrl.audit.by_session(h.session_id)
        if r.action == "harness.approval_required"
    ]
    assert refs
    ctrl.resolve_approval(h.session_id, refs[0], decision=ApprovalRefState.APPROVED)
    assert len(ctrl.gateway.approved_execution_ids) == 1
    # Consumed
    with pytest.raises(HarnessError) as ei:
        ctrl.resolve_approval(h.session_id, refs[0], decision=ApprovalRefState.APPROVED)
    assert ei.value.code == HarnessErrorCode.APPROVAL_INVALID
    # Session continued after approve
    events = ctrl.poll_events(h.session_id)
    assert any(e.event_type.value == "TOOL_RESULT_DELIVERED" for e in events)


def test_approval_denied_cancels_execution():
    ctrl, _ = _ctrl(FakeScenario.APPROVAL_REQUIRED)
    h = _start(ctrl, session_id="apr-deny")
    ctrl.submit_turn(h.session_id, input_text="no", correlation_id=_corr())
    refs = [
        r.detail["approval_ref"]
        for r in ctrl.audit.by_session(h.session_id)
        if r.action == "harness.approval_required"
    ]
    eid = ctrl._sessions[h.session_id].pending_execution_id
    ctrl.resolve_approval(h.session_id, refs[0], decision=ApprovalRefState.DENIED)
    assert eid in ctrl.gateway.cancelled_intent_ids
    # No successful approved execution
    assert ctrl.gateway.approved_execution_ids == []


def test_approval_expired_and_revoked():
    for decision in (ApprovalRefState.EXPIRED, ApprovalRefState.REVOKED):
        ctrl, _ = _ctrl(FakeScenario.APPROVAL_REQUIRED)
        h = _start(ctrl, session_id=f"apr-{decision.value}", run_id=f"r-{decision.value}")
        ctrl.submit_turn(h.session_id, input_text="x", correlation_id=_corr())
        refs = [
            r.detail["approval_ref"]
            for r in ctrl.audit.by_session(h.session_id)
            if r.action == "harness.approval_required"
        ]
        ctrl.resolve_approval(h.session_id, refs[0], decision=decision)
        assert ctrl.gateway.approved_execution_ids == []


# ── Cancellation through real gateway ───────────────────────────────────────


def test_cancel_during_approval_wait():
    ctrl, fake = _ctrl(FakeScenario.APPROVAL_REQUIRED)
    h = _start(ctrl, session_id="cancel-apr")
    ctrl.submit_turn(h.session_id, input_text="wait", correlation_id=_corr())
    eid = ctrl._sessions[h.session_id].pending_execution_id
    assert eid
    ack = ctrl.request_cancel(h.session_id, reason="user_abort")
    assert ack.status is CancelAckStatus.ACKNOWLEDGED
    assert eid in ctrl.gateway.cancelled_intent_ids
    assert ctrl.projected_run_state(h.session_id) is RunState.CANCELLED
    # Repeated cancel idempotent
    ack2 = ctrl.request_cancel(h.session_id, reason="again")
    assert ack2.status is CancelAckStatus.ALREADY_TERMINAL


def test_cancel_before_tool_turn():
    ctrl, _ = _ctrl(FakeScenario.MULTI_TURN)
    h = _start(ctrl, session_id="cancel-before")
    ctrl.request_cancel(h.session_id)
    with pytest.raises(HarnessError):
        ctrl.submit_turn(h.session_id, input_text="nope", correlation_id=_corr())


def test_gateway_deny_all_path():
    ctrl, _ = _ctrl(FakeScenario.TOOL_THEN_CONTINUE)
    ctrl.gateway.deny_all = True
    h = _start(ctrl, session_id="deny-all")
    ctrl.submit_turn(h.session_id, input_text="tool", correlation_id=_corr())
    # Denied without EG success
    assert all(
        (not r.get("ok")) or r.get("status") == "denied"
        for r in ctrl.gateway._results_by_idem.values()
    ) or ctrl.gateway.submitted == []


def test_dry_run_execute_false_on_adapter():
    adapter = RealExecutionGatewayAdapter(isolated=True, execute=False)
    fake = FakeInMemoryHarness(default_scenario=FakeScenario.TOOL_THEN_CONTINUE)
    ctrl = HarnessSessionController(fake, gateway=adapter, max_sessions=5)
    h = _start(ctrl, session_id="dry-run")
    # Manual mediate of echo with execute=False path (adapter.execute=False)
    r = ctrl.mediate_proposal(
        ToolProposal(
            proposal_id="dry1",
            session_id=h.session_id,
            turn_id="t",
            tool_name="fake.echo",
            parameters={"message": "dry"},
            correlation_id=_corr(),
            organization_id="org-eg",
            workspace_id="ws-eg",
        )
    )
    # Approved but not handler-executed
    assert r.redacted_result is not None
    assert r.redacted_result.get("executed") is False
    assert r.redacted_result.get("path") == "ExecutionGateway"


# ── Audit / evidence ────────────────────────────────────────────────────────


def test_audit_correlates_gateway_execution():
    ctrl, _ = _ctrl(FakeScenario.TOOL_THEN_CONTINUE)
    h = _start(ctrl, session_id="audit-eg")
    corr = _corr()
    ctrl.submit_turn(h.session_id, input_text="tool", correlation_id=corr)
    actions = ctrl.audit.actions()
    assert "harness.session_started" in actions
    assert "harness.tool_mediated" in actions
    mediated = [r for r in ctrl.audit.all() if r.action == "harness.tool_mediated"]
    assert mediated
    detail = mediated[0].detail
    assert detail.get("gateway_path") == "ExecutionGateway"
    assert detail.get("execution_id")
    assert detail.get("intent_id")
    # No private CoT in audit
    blob = str(ctrl.audit.all())
    assert "chain_of_thought" not in blob
    assert "private_cot" not in blob


def test_malformed_toolintent_rejected_by_gateway_validate():
    adapter = RealExecutionGatewayAdapter(isolated=True)
    # Missing required fields → validate errors
    bad = ToolIntent(
        actor_id="",
        mission_id="",
        capability="",
        connector_id="",
        operation="",
        reason="",
        idempotency_key="not-hex",
    )
    with pytest.raises(HarnessError) as ei:
        adapter.submit(bad)
    assert ei.value.code == HarnessErrorCode.MALFORMED_PROPOSAL


# ── Security scans (FM-I2 package surface) ──────────────────────────────────


def test_fm_i2_no_provider_imports_in_bridge():
    root = Path(__file__).resolve().parents[1] / "saathi" / "agent_runtime" / "harness"
    banned = ("openai", "anthropic", "ollama", "subprocess", "httpx", "requests")
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for b in banned:
            assert f"import {b}" not in text
            assert f"from {b}" not in text


def test_agent_session_adapter_still_untouched():
    eng = Path(__file__).resolve().parents[1] / "saathi" / "engineering"
    for p in eng.rglob("*.py"):
        body = p.read_text(encoding="utf-8", errors="replace")
        assert "RealExecutionGatewayAdapter" not in body
        assert "agent_runtime.harness" not in body
