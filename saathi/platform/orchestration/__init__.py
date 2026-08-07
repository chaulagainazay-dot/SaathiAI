"""SaathiOS Agent Orchestration and Planning Runtime (M95–M102).

Plans and supervises multi-step work. Does not replace Mission Runtime,
ExecutionGateway, Approval Center, Evidence, or Audit.
"""
from __future__ import annotations

from .models import (
    ApprovalRequirement,
    FailureClass,
    ObjectiveIntake,
    OrchestrationState,
    PlanValidationResult,
)
from .roles import AgentRoleRegistry
from .service import (
    AgentOrchestrationService,
    default_orchestration_service,
    reset_orchestration_service_for_tests,
)
from .templates import list_templates

__all__ = [
    "AgentOrchestrationService",
    "AgentRoleRegistry",
    "ApprovalRequirement",
    "FailureClass",
    "ObjectiveIntake",
    "OrchestrationState",
    "PlanValidationResult",
    "default_orchestration_service",
    "list_templates",
    "reset_orchestration_service_for_tests",
]
