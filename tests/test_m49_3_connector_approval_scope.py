"""M49.3 approval action and target scope."""
from __future__ import annotations

import time

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


def test_approval_for_draft_does_not_authorize_send(tmp_path):
    svc = _svc(tmp_path)
    ap = ToolApprovalReference(
        approval_id="ap-draft",
        tool_id="m49.connector.gmail.create_draft",
        capability="write",
        action="create_draft",
        connector="gmail",
        run_id="r",
        side_effect_class="EXTERNAL_REVERSIBLE",
        expires_at=time.time() + 999,
    )
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gmail.send_message",
            arguments={"to": "a@example.test", "subject": "s", "body": "b"},
            approval_reference=ap,
            idempotency_key="k1",
            capability="write",
        )
    )
    assert r.error_code == "TOOL_APPROVAL_REQUIRED"
    assert r.adapter_invoked is False


def test_approval_for_read_does_not_authorize_mutation(tmp_path):
    svc = _svc(tmp_path)
    ap = ToolApprovalReference(
        approval_id="ap-read",
        tool_id="m49.connector.gmail.search_messages",
        capability="read",
        run_id="r",
        side_effect_class="NO_SIDE_EFFECT",
        expires_at=time.time() + 999,
    )
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gmail.send_message",
            arguments={"to": "a@example.test", "subject": "s", "body": "b"},
            approval_reference=ap,
            idempotency_key="k2",
            capability="write",
        )
    )
    assert r.error_code == "TOOL_APPROVAL_REQUIRED"
    assert r.adapter_invoked is False


def test_approval_target_mismatch_rejected(tmp_path):
    svc = _svc(tmp_path)
    ap = ToolApprovalReference(
        approval_id="ap-tgt",
        tool_id="m49.connector.gmail.send_message",
        capability="write",
        action="send_message",
        connector="gmail",
        target_resource="allowed@example.test",
        run_id="r",
        side_effect_class="EXTERNAL_IRREVERSIBLE",
        expires_at=time.time() + 999,
    )
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gmail.send_message",
            arguments={
                "to": "other@example.test",
                "subject": "s",
                "body": "b",
            },
            approval_reference=ap,
            idempotency_key="k3",
            capability="write",
        )
    )
    assert r.error_code == "TOOL_APPROVAL_REQUIRED"
    assert r.adapter_invoked is False


def test_matching_action_approval_succeeds(tmp_path):
    svc = _svc(tmp_path)
    ap = ToolApprovalReference(
        approval_id="ap-ok",
        tool_id="m49.connector.gmail.create_draft",
        capability="write",
        action="create_draft",
        connector="gmail",
        target_resource="a@example.test",
        run_id="r",
        side_effect_class="EXTERNAL_REVERSIBLE",
        authority="EXTERNAL_MUTATION",
        expires_at=time.time() + 999,
    )
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gmail.create_draft",
            arguments={
                "to": "a@example.test",
                "subject": "s",
                "body": "b",
            },
            approval_reference=ap,
            idempotency_key="k4",
            capability="write",
        )
    )
    assert r.ok
    assert r.data["mutation_performed"] is False
    assert r.data["network_performed"] is False


def test_expired_approval_rejected(tmp_path):
    svc = _svc(tmp_path)
    ap = ToolApprovalReference(
        approval_id="ap-exp",
        tool_id="m49.connector.gmail.create_draft",
        capability="write",
        run_id="r",
        side_effect_class="EXTERNAL_REVERSIBLE",
        expires_at=time.time() - 10,
    )
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gmail.create_draft",
            arguments={"to": "a@example.test", "subject": "s", "body": "b"},
            approval_reference=ap,
            idempotency_key="k5",
            capability="write",
        )
    )
    assert r.error_code == "TOOL_APPROVAL_EXPIRED"
    assert r.adapter_invoked is False


def test_revoked_approval_rejected(tmp_path):
    svc = _svc(tmp_path)
    ap = ToolApprovalReference(
        approval_id="ap-rev",
        tool_id="m49.connector.gmail.create_draft",
        capability="write",
        run_id="r",
        side_effect_class="EXTERNAL_REVERSIBLE",
        expires_at=time.time() + 999,
        revoked=True,
    )
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gmail.create_draft",
            arguments={"to": "a@example.test", "subject": "s", "body": "b"},
            approval_reference=ap,
            idempotency_key="k6",
            capability="write",
        )
    )
    assert r.error_code == "TOOL_APPROVAL_REVOKED"
    assert r.adapter_invoked is False
