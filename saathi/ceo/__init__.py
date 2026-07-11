"""M14 CEO OS — unified operating + decision layer over existing systems.

Reuses M10 (mission execution + approvals), M9 (memory), M13 (studio),
ExecutionGateway, event bus, and the verified BFF/dream_pct contracts. CEO OS
never executes directly, never fabricates unavailable metrics, never presents a
recommendation as a verified fact, and cannot self-approve protected decisions.
"""
from saathi.ceo.models import (
    EvidenceTier, GoalStatus, DecisionStatus, RiskStatus, OpportunityStatus,
    ProjectHealth, FinancialState, KPIType, Provenance, PRIORITY_WEIGHTS,
    PROTECTED_DECISION_STATES, validate_decision_transition, IllegalDecisionTransition,
)
from saathi.ceo.store import CEOStore, default_store
from saathi.ceo.service import CEOService, default_service
from saathi.ceo.agent import CEOAgent
from saathi.ceo import kpi, priority, finance, project_health

__all__ = [
    "EvidenceTier", "GoalStatus", "DecisionStatus", "RiskStatus", "OpportunityStatus",
    "ProjectHealth", "FinancialState", "KPIType", "Provenance", "PRIORITY_WEIGHTS",
    "PROTECTED_DECISION_STATES", "validate_decision_transition", "IllegalDecisionTransition",
    "CEOStore", "default_store", "CEOService", "default_service", "CEOAgent",
    "kpi", "priority", "finance", "project_health",
]
