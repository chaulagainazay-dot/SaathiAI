"""M20.0–M20.5 — Governed Engineering Orchestrator + session ledger.

Control and supervision layer over coding-agent work. Does **not** replace
Mission Engine, ExecutionGateway, Approval Engine, Knowledge Service, Run Ledger,
Event Bus, Scheduler, Repair Loops, or Trading Guardian.

M20.5 adds an engineering-only session ledger + integrity evidence + recovery
(not a second harness run ledger).

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
from saathi.engineering.recovery import SessionRecovery, recover_store
from saathi.engineering.session_ledger import SessionLedger
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
    "SessionLedger",
    "SessionRecovery",
    "Verdict",
    "default_orchestrator",
    "load_settings",
    "recover_store",
]
