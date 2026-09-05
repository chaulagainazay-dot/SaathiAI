"""Stable Mission Control read-model contract for priority integrations."""
from __future__ import annotations

from typing import Any


def build_priority_status(
    *,
    local_runtime: str = "ollama",
    selected_model: str = "qwen2.5:1.5b",
    estimated_cost: str = "0.00",
    actual_cost: str = "0.00",
    workflow_evaluation_score: float | None = None,
    collaboration_score: float | None = None,
    provenance_status: str = "NOT_EVALUATED",
    approval_required: bool = False,
    rollback_available: bool = True,
) -> dict[str, Any]:
    return {
        "schema": "saathios.mission_control.priority_status.v1",
        "local_runtime": local_runtime,
        "selected_model": selected_model,
        "estimated_cost_usd": estimated_cost,
        "actual_cost_usd": actual_cost,
        "workflow_evaluation_score": workflow_evaluation_score,
        "collaboration_score": collaboration_score,
        "provenance_status": provenance_status,
        "approval_required": approval_required,
        "rollback_available": rollback_available,
    }
