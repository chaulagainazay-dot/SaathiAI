"""M49.1 bounded builtin adapters — safe migration slice only."""
from __future__ import annotations

import time
from typing import Any

from saathi.tool_runtime.context import (
    BoundedToolContext,
    ToolCancelledError,
    ToolTimeoutError,
)
from saathi.tool_runtime.contracts import (
    IdempotencyPolicy,
    RedactionPolicy,
    RetryPolicy,
    TimeoutPolicy,
    ToolApprovalRequirement,
    ToolAuthorityClass,
    ToolAvailability,
    ToolCancellationSupport,
    ToolIdempotencyClass,
    ToolManifest,
    ToolRetryClass,
    ToolSecretPolicy,
    ToolSideEffectClass,
)


# ── Adapters ──────────────────────────────────────────────────────────────


def echo_readonly(args: dict, ctx: BoundedToolContext) -> dict:
    """Read-only local tool — no side effects."""
    ctx.raise_if_cancelled()
    text = str(args.get("text", ""))
    ctx.evidence("echo", {"len": len(text)})
    return {
        "data": {"echo": text, "run_id": ctx.run_id},
        "side_effect_confirmed": True,
    }


def local_note_write(args: dict, ctx: BoundedToolContext) -> dict:
    """Reversible local mutation — writes into ctx.scratch only."""
    ctx.raise_if_cancelled()
    key = str(args.get("key", ""))
    value = str(args.get("value", ""))
    notes = ctx.scratch.setdefault("_notes", {})
    notes[key] = value
    ctx.evidence("note_write", {"key": key})
    return {
        "data": {"written": True, "key": key, "size": len(value)},
        "side_effect_confirmed": True,
    }


def timeout_demo(args: dict, ctx: BoundedToolContext) -> dict:
    """Timeout-capable tool — busy-waits in small slices checking cancel/deadline."""
    sleep_ms = int(args.get("sleep_ms", 50))
    end = time.time() + (sleep_ms / 1000.0)
    while time.time() < end:
        if ctx.should_cancel():
            raise ToolCancelledError("cancelled during wait")
        if ctx.remaining_sec() <= 0:
            raise ToolTimeoutError("deadline")
        time.sleep(0.01)
    return {"data": {"slept_ms": sleep_ms}, "side_effect_confirmed": True}


def cooperative_cancel_demo(args: dict, ctx: BoundedToolContext) -> dict:
    """Cooperative cancel — checks token between stages."""
    stages = int(args.get("stages", 3))
    done = []
    for i in range(stages):
        ctx.raise_if_cancelled()
        if ctx.remaining_sec() <= 0:
            raise ToolTimeoutError("deadline")
        done.append(i)
        time.sleep(0.005)
    return {"data": {"stages_done": done}, "side_effect_confirmed": True}


def financial_execution_stub(args: dict, ctx: BoundedToolContext) -> dict:
    """Must never be invoked — manifest PROHIBITED. Guard if reached."""
    return {
        "error": "financial execution unreachable",
        "outcome_unknown": True,
    }


# ── Manifest factory ──────────────────────────────────────────────────────


def builtin_manifests() -> list[tuple[ToolManifest, Any]]:
    echo = ToolManifest(
        tool_id="m49.echo_readonly",
        version="1.0.0",
        display_name="Echo (read-only)",
        description="Echo text; no side effects. M49.1 migration pilot.",
        domain="tool_runtime",
        capabilities=("read", "echo"),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string", "maxLength": 2000}},
            "required": ["text"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "echo": {"type": "string"},
                "run_id": {"type": "string"},
            },
            "required": ["echo", "run_id"],
        },
        timeout_policy=TimeoutPolicy(default_sec=10, max_sec=30),
        retry_policy=RetryPolicy(max_attempts=2, retry_class=ToolRetryClass.BOUNDED_SAFE),
        idempotency_policy=IdempotencyPolicy(
            klass=ToolIdempotencyClass.NATURALLY_IDEMPOTENT
        ),
        cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
    )

    note = ToolManifest(
        tool_id="m49.local_note_write",
        version="1.0.0",
        display_name="Local note write",
        description="Write a reversible note into scratch storage.",
        domain="tool_runtime",
        capabilities=("write", "note"),
        authority_class=ToolAuthorityClass.LOCAL_MUTATION,
        side_effect_class=ToolSideEffectClass.LOCAL_REVERSIBLE,
        approval_requirement=ToolApprovalRequirement.EXPLICIT_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "maxLength": 64},
                "value": {"type": "string", "maxLength": 2000},
            },
            "required": ["key", "value"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "written": {"type": "boolean"},
                "key": {"type": "string"},
                "size": {"type": "integer"},
            },
            "required": ["written", "key", "size"],
        },
        timeout_policy=TimeoutPolicy(default_sec=10, max_sec=30),
        retry_policy=RetryPolicy(max_attempts=1, retry_class=ToolRetryClass.NEVER),
        idempotency_policy=IdempotencyPolicy(
            klass=ToolIdempotencyClass.IDEMPOTENCY_KEY_REQUIRED,
            require_key=True,
        ),
        cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
    )

    tmo = ToolManifest(
        tool_id="m49.timeout_demo",
        version="1.0.0",
        display_name="Timeout demo",
        description="Bounded sleep with deadline checks.",
        domain="tool_runtime",
        capabilities=("demo", "timeout"),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={
            "type": "object",
            "properties": {"sleep_ms": {"type": "integer"}},
            "required": ["sleep_ms"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"slept_ms": {"type": "integer"}},
            "required": ["slept_ms"],
        },
        timeout_policy=TimeoutPolicy(default_sec=0.2, max_sec=2.0, grace_sec=0.05),
        cancellation_support=ToolCancellationSupport.TIMEOUT_ONLY,
        idempotency_policy=IdempotencyPolicy(
            klass=ToolIdempotencyClass.NATURALLY_IDEMPOTENT
        ),
    )

    coop = ToolManifest(
        tool_id="m49.cooperative_cancel",
        version="1.0.0",
        display_name="Cooperative cancel demo",
        description="Multi-stage tool that honors cancellation token.",
        domain="tool_runtime",
        capabilities=("demo", "cancel"),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={
            "type": "object",
            "properties": {"stages": {"type": "integer"}},
            "required": [],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"stages_done": {"type": "array", "items": {"type": "integer"}}},
            "required": ["stages_done"],
        },
        timeout_policy=TimeoutPolicy(default_sec=5, max_sec=10),
        cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
    )

    fin = ToolManifest(
        tool_id="m49.financial_execution_stub",
        version="1.0.0",
        display_name="Financial execution (prohibited)",
        description="Test-only prohibited financial execution tool.",
        domain="finance",
        capabilities=("trade_execute", "financial_execution"),
        authority_class=ToolAuthorityClass.FINANCIAL_EXECUTION,
        side_effect_class=ToolSideEffectClass.FINANCIAL_EXECUTION,
        approval_requirement=ToolApprovalRequirement.PROHIBITED,
        secret_policy=ToolSecretPolicy.PROHIBITED,
        input_schema={
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
        output_schema={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
        enabled=True,
        availability=ToolAvailability.PROHIBITED,
        cancellation_support=ToolCancellationSupport.NOT_CANCELLABLE,
        idempotency_policy=IdempotencyPolicy(
            klass=ToolIdempotencyClass.NON_IDEMPOTENT
        ),
        retry_policy=RetryPolicy(max_attempts=1, retry_class=ToolRetryClass.NOT_RETRYABLE_PROHIBITED),
    )

    return [
        (echo, echo_readonly),
        (note, local_note_write),
        (tmo, timeout_demo),
        (coop, cooperative_cancel_demo),
        (fin, financial_execution_stub),
    ]
