"""Repair 1 regression guard for the Universal Secure Execution Layer.

Covers two things that were broken before Repair 1:
1. ``saathi.execution`` exposes a stable public API (empty ``__init__`` before).
2. One narrow reference execution path runs ToolIntent through the
   ExecutionGateway pipeline end to end and produces an auditable result.
"""

import asyncio
from datetime import datetime

import pytest


def test_public_api_surface_importable():
    """The canonical public names resolve (guards against empty __init__)."""
    from saathi.execution import (
        ToolIntent,
        ExecutionGateway,
        ExecutionContext,
        ExecutionResult,
        RiskLevel,
        ApprovalStatus,
        ApprovalDecision,
        ToolExecutionStatus,
        AuditTrail,
        Evidence,
    )

    # Gateway status enum (namespaced to avoid the finance ExecutionStatus clash)
    assert {s.name for s in ToolExecutionStatus} == {
        "SUCCESS",
        "FAILED",
        "TIMEOUT",
        "PARTIAL",
    }
    assert {s.name for s in RiskLevel} == {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    # ApprovalDecision is the mandated alias of ApprovalStatus.
    assert ApprovalDecision is ApprovalStatus


def test_finance_and_gateway_coexist():
    """Both execution concerns import from the same package without clashing."""
    from saathi.execution import (
        ExecutionIntent,       # finance
        ExecutionService,      # finance
        ExecutionStatus,       # finance order status (bare name preserved)
        ToolIntent,            # gateway
        ExecutionGateway,      # gateway
    )

    # Finance order status keeps its historical members.
    assert "FILLED" in {s.name for s in ExecutionStatus}
    assert ExecutionIntent is not ToolIntent


def test_reference_execution_path_produces_auditable_result():
    """One narrow reference path: ToolIntent -> gateway pipeline -> result.

    Exercises validate -> authorize -> classify risk -> approve -> queue ->
    execute (local, zero-cost adapter) -> sanitize -> evidence.
    """
    from saathi.execution import ToolIntent, ExecutionContext, ToolExecutionStatus
    from saathi.execution.integration import execute, get_execution_system
    from saathi.execution.queue.memory import MemoryQueue

    # Fresh in-memory system so the test is isolated and durable-queue-free.
    get_execution_system(MemoryQueue())

    intent = ToolIntent(
        intent_id="ref-llm-001",
        operation="local-llm-inference",
        business_unit="pielts",
        actor_id="user:test",
        parameters={"prompt": "Say hello in one word", "model": "auto-select"},
        metadata={"data_sensitivity": "confidential", "max_latency_sec": 30},
    )
    ctx = ExecutionContext(
        actor_id="user:test",
        business_unit="pielts",
        timestamp=datetime.utcnow(),
        current_time=datetime.utcnow(),
    )

    result = asyncio.run(execute(intent, ctx))

    assert result.status in (ToolExecutionStatus.SUCCESS, ToolExecutionStatus.PARTIAL)
    # confidential data must stay local -> zero external cost
    assert result.cost_usd == 0.0
