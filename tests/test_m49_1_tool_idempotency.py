"""M49.1 — idempotency behavior."""
from __future__ import annotations

import time

from saathi.tool_runtime.contracts import (
    ToolApprovalReference,
    ToolExecutionRequest,
    ToolOutcomeClass,
)
from saathi.tool_runtime.idempotency import IdempotencyStore, fingerprint
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.tool_runtime.service import ToolExecutionService


def _svc():
    return ToolExecutionService(
        registry=reset_registry_for_tests(), idempotency=IdempotencyStore()
    )


def _approval(run_id="r1"):
    return ToolApprovalReference(
        approval_id="ap",
        tool_id="m49.local_note_write",
        capability="write",
        run_id=run_id,
        side_effect_class="LOCAL_REVERSIBLE",
        expires_at=time.time() + 9999,
    )


def test_fingerprint_stable():
    a = fingerprint(
        tool_id="t",
        tool_version="1",
        arguments={"b": 2, "a": 1},
        authority="READ_ONLY",
        run_id="r",
        caller="u",
    )
    b = fingerprint(
        tool_id="t",
        tool_version="1",
        arguments={"a": 1, "b": 2},
        authority="READ_ONLY",
        run_id="r",
        caller="u",
    )
    assert a == b


def test_missing_idempotency_key_blocks_mutation():
    svc = _svc()
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r1",
            tool_id="m49.local_note_write",
            arguments={"key": "k", "value": "v"},
            approval_reference=_approval(),
            # no idempotency_key
        )
    )
    assert r.error_code == "TOOL_IDEMPOTENCY_CONFLICT"
    assert r.adapter_invoked is False


def test_same_key_same_fingerprint_replays():
    svc = _svc()
    req = ToolExecutionRequest(
        run_id="r1",
        tool_id="m49.local_note_write",
        arguments={"key": "k", "value": "v"},
        approval_reference=_approval(),
        idempotency_key="same-key",
        capability="write",
    )
    r1 = svc.execute_tool(req)
    assert r1.ok and r1.adapter_invoked
    r2 = svc.execute_tool(req)
    assert r2.ok
    assert r2.adapter_invoked is False  # replay
    assert r2.data.get("written") is True


def test_same_key_different_args_conflicts():
    svc = _svc()
    ap = _approval()
    r1 = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r1",
            tool_id="m49.local_note_write",
            arguments={"key": "k", "value": "v1"},
            approval_reference=ap,
            idempotency_key="conflict-key",
            capability="write",
        )
    )
    assert r1.ok
    r2 = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r1",
            tool_id="m49.local_note_write",
            arguments={"key": "k", "value": "v2"},
            approval_reference=ap,
            idempotency_key="conflict-key",
            capability="write",
        )
    )
    assert r2.error_code == "TOOL_IDEMPOTENCY_CONFLICT"
    assert r2.adapter_invoked is False
