"""M20.0 — Governed Engineering Orchestrator.

Control and supervision layer over coding-agent work. Does **not** replace
Mission Engine, ExecutionGateway, Approval Engine, Knowledge Service, Run Ledger,
Event Bus, Scheduler, Repair Loops, or Trading Guardian.

Disabled by default. See ``saathi.engineering.settings``.
"""
from __future__ import annotations

from saathi.engineering.models import (
    EngineeringBacklogItem,
    EngineeringTask,
    ItemStatus,
    Verdict,
)
from saathi.engineering.orchestrator import (
    EngineeringOrchestrator,
    OrchestratorResult,
    default_orchestrator,
)
from saathi.engineering.settings import EngineeringSettings, load_settings
from saathi.engineering.store import EngineeringStore

__all__ = [
    "EngineeringBacklogItem",
    "EngineeringOrchestrator",
    "EngineeringSettings",
    "EngineeringStore",
    "EngineeringTask",
    "ItemStatus",
    "OrchestratorResult",
    "Verdict",
    "default_orchestrator",
    "load_settings",
]
