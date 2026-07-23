"""M49.2 durable idempotency store."""
from __future__ import annotations

import time

from saathi.tool_runtime.contracts import (
    ToolApprovalReference,
    ToolExecutionRequest,
    ToolOutcomeClass,
)
from saathi.tool_runtime.durable_idempotency import (
    DurableIdempotencyStore,
    OUTCOME_UNKNOWN,
    SUCCESS_CONFIRMED,
)
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.tool_runtime.service import ToolExecutionService


def test_durable_replay(tmp_path):
    db = tmp_path / "i.db"
    store = DurableIdempotencyStore(db)
    reg = reset_registry_for_tests()
    svc = ToolExecutionService(registry=reg, idempotency=store)
    ap = ToolApprovalReference(
        approval_id="a1",
        tool_id="m49.local_note_write",
        capability="write",
        run_id="r1",
        side_effect_class="LOCAL_REVERSIBLE",
        expires_at=time.time() + 9999,
    )
    req = ToolExecutionRequest(
        run_id="r1",
        tool_id="m49.local_note_write",
        arguments={"key": "k", "value": "v"},
        approval_reference=ap,
        idempotency_key="dur-1",
        capability="write",
    )
    r1 = svc.execute_tool(req)
    assert r1.ok and r1.adapter_invoked
    r2 = svc.execute_tool(req)
    assert r2.ok and r2.adapter_invoked is False


def test_durable_conflict(tmp_path):
    store = DurableIdempotencyStore(tmp_path / "c.db")
    reg = reset_registry_for_tests()
    svc = ToolExecutionService(registry=reg, idempotency=store)
    ap = ToolApprovalReference(
        approval_id="a1",
        tool_id="m49.local_note_write",
        capability="write",
        run_id="r1",
        side_effect_class="LOCAL_REVERSIBLE",
        expires_at=time.time() + 9999,
    )
    r1 = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r1",
            tool_id="m49.local_note_write",
            arguments={"key": "k", "value": "v1"},
            approval_reference=ap,
            idempotency_key="dur-c",
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
            idempotency_key="dur-c",
            capability="write",
        )
    )
    assert r2.error_code == "TOOL_IDEMPOTENCY_CONFLICT"


def test_stale_lease_reconcile_read_only(tmp_path):
    store = DurableIdempotencyStore(tmp_path / "s.db", lease_sec=0.05)
    st = store.begin(
        "r",
        "k1",
        "fp1",
        tool_id="t",
        side_effect_class="NO_SIDE_EFFECT",
    )
    assert st["status"] == "acquired"
    # force expire
    with store._conn() as c:
        c.execute(
            "UPDATE tool_idempotency SET lease_expires_at=? WHERE scope=? AND idempotency_key=?",
            (time.time() - 10, "r", "k1"),
        )
    out = store.reconcile_stale()
    assert out["recovered"] >= 1
    # re-acquire works
    st2 = store.begin("r", "k1", "fp1", side_effect_class="NO_SIDE_EFFECT")
    assert st2["status"] == "acquired"


def test_stale_mutation_requires_review(tmp_path):
    store = DurableIdempotencyStore(tmp_path / "m.db", lease_sec=0.05)
    store.begin(
        "r",
        "k2",
        "fp2",
        tool_id="t",
        side_effect_class="EXTERNAL_IRREVERSIBLE",
    )
    with store._conn() as c:
        c.execute(
            "UPDATE tool_idempotency SET lease_expires_at=? WHERE scope=? AND idempotency_key=?",
            (time.time() - 10, "r", "k2"),
        )
    out = store.reconcile_stale()
    assert out["requires_review"] >= 1
    with store._conn() as c:
        row = c.execute(
            "SELECT status FROM tool_idempotency WHERE scope=? AND idempotency_key=?",
            ("r", "k2"),
        ).fetchone()
    assert row["status"] == OUTCOME_UNKNOWN
