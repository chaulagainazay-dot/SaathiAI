"""M50 Approval Center + M49 gateway integration."""
from __future__ import annotations

import time

import pytest

from saathi.platform.context import PlatformContextError
from saathi.platform.models import ApprovalStatus
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests


@pytest.fixture()
def plat(tmp_path):
    reset_registry_for_tests()
    return reset_platform_for_tests(tmp_path / "p.db")


def _owner_token(plat):
    plat.bootstrap_owner(email="owner@local", name="Owner")
    return plat.login(email="owner@local")["token"]


def test_approval_lifecycle(plat):
    token = _owner_token(plat)
    ctx = plat.require_context(token)
    rec = plat.request_approval(
        ctx,
        tool_id="m49.local_note_write",
        action="write",
        target_resource="note:k",
        authority="LOCAL_MUTATION",
        side_effect_class="LOCAL_REVERSIBLE",
        capability="write",
        ttl_sec=600,
    )
    assert rec.status == ApprovalStatus.PENDING.value
    inbox = plat.inbox(ctx, status="pending")
    assert any(a["approval_id"] == rec.approval_id for a in inbox)

    approved = plat.decide_approval(ctx, rec.approval_id, approve=True, reason="ok")
    assert approved.status == ApprovalStatus.APPROVED.value

    rejected_req = plat.request_approval(
        ctx, tool_id="m49.local_note_write", action="write", capability="write", ttl_sec=600
    )
    rej = plat.decide_approval(ctx, rejected_req.approval_id, approve=False, reason="no")
    assert rej.status == ApprovalStatus.REJECTED.value


def test_approval_expiry(plat):
    token = _owner_token(plat)
    ctx = plat.require_context(token)
    rec = plat.request_approval(
        ctx, tool_id="m49.echo_readonly", action="echo", ttl_sec=0.01
    )
    time.sleep(0.05)
    plat.store.expire_stale_approvals()
    got = plat.store.get_approval(rec.approval_id)
    assert got.status == ApprovalStatus.EXPIRED.value


def test_approval_revocation_blocks_execute(plat):
    token = _owner_token(plat)
    ctx = plat.require_context(token)
    rec = plat.request_approval(
        ctx,
        tool_id="m49.local_note_write",
        action="write",
        capability="write",
        side_effect_class="LOCAL_REVERSIBLE",
        authority="LOCAL_MUTATION",
        ttl_sec=600,
    )
    plat.decide_approval(ctx, rec.approval_id, approve=True)
    plat.revoke_approval(ctx, rec.approval_id)
    with pytest.raises(PlatformContextError) as ei:
        plat.execute_tool(
            ctx,
            tool_id="m49.local_note_write",
            arguments={"key": "k", "value": "v"},
            approval_id=rec.approval_id,
            capability="write",
        )
    assert ei.value.code in ("APPROVAL_REVOKED", "APPROVAL_NOT_APPROVED")


def test_readonly_tool_via_gateway_no_approval(plat):
    token = _owner_token(plat)
    ctx = plat.require_context(token)
    result = plat.execute_tool(
        ctx, tool_id="m49.echo_readonly", arguments={"text": "m50"}
    )
    assert result.ok
    assert result.data["echo"] == "m50"
    # audit recorded
    events = plat.store.list_audit(org_id=ctx.org_id, limit=20)
    assert any(e["event"] == "runtime.execute" for e in events)


def test_mutation_requires_approval_and_consumes(plat):
    token = _owner_token(plat)
    ctx = plat.require_context(token)
    rec = plat.request_approval(
        ctx,
        tool_id="m49.local_note_write",
        action="write",
        capability="write",
        side_effect_class="LOCAL_REVERSIBLE",
        authority="LOCAL_MUTATION",
        ttl_sec=600,
    )
    plat.decide_approval(ctx, rec.approval_id, approve=True)
    r1 = plat.execute_tool(
        ctx,
        tool_id="m49.local_note_write",
        arguments={"key": "m50k", "value": "v1"},
        approval_id=rec.approval_id,
        capability="write",
    )
    assert r1.ok
    # replay blocked
    with pytest.raises(PlatformContextError) as ei:
        plat.execute_tool(
            ctx,
            tool_id="m49.local_note_write",
            arguments={"key": "m50k", "value": "v2"},
            approval_id=rec.approval_id,
            capability="write",
        )
    assert ei.value.code == "APPROVAL_REPLAY"


def test_approval_tool_mismatch(plat):
    token = _owner_token(plat)
    ctx = plat.require_context(token)
    rec = plat.request_approval(
        ctx,
        tool_id="m49.local_note_write",
        capability="write",
        side_effect_class="LOCAL_REVERSIBLE",
        ttl_sec=600,
    )
    plat.decide_approval(ctx, rec.approval_id, approve=True)
    with pytest.raises(PlatformContextError) as ei:
        plat.execute_tool(
            ctx,
            tool_id="m49.echo_readonly",
            arguments={"text": "x"},
            approval_id=rec.approval_id,
        )
    assert ei.value.code == "APPROVAL_TOOL_MISMATCH"


def test_financial_still_prohibited_through_platform(plat):
    token = _owner_token(plat)
    ctx = plat.require_context(token)
    r = plat.execute_tool(
        ctx, tool_id="m49.financial_execution_stub", arguments={"symbol": "AAPL"}
    )
    assert r.outcome_class.value == "PROHIBITED"
    assert r.adapter_invoked is False


def test_config_cannot_enable_live_connectors(plat):
    token = _owner_token(plat)
    ctx = plat.require_context(token)
    cfg = plat.update_configuration(
        ctx, {"connectors": {"live": True, "mutations": "LIVE"}}
    )
    assert cfg["connectors"]["live"] is False
    assert cfg["connectors"]["mutations"] == "DRY_RUN_ONLY"
    assert cfg["trading_guardian"] == "ADVISORY_ONLY"


def test_project_and_mission_models(plat):
    token = _owner_token(plat)
    ctx = plat.require_context(token)
    proj = plat.create_project(ctx, "Alpha Project", mission_key="alpha")
    assert proj["project_id"]
    mis = plat.create_mission(ctx, proj["project_id"], "alpha", "Alpha Mission")
    assert mis["mission_id"]
    assert mis["project_id"] == proj["project_id"]
    # isolation: other org mission not accessible
    with pytest.raises(PlatformContextError):
        plat.require_context(token, mission_id="mis_foreign")
