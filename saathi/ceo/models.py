"""M14 CEO OS — canonical business-entity models + state machines.

CEO OS is the decision/operating layer over existing systems, not a new brain.
Every insight carries provenance and an evidence tier so a recommendation is
never presented as a verified fact.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class EvidenceTier(str, Enum):
    """Every CEO OS value declares how it is known."""
    OBSERVED = "observed"          # persisted fact from an authoritative source
    CALCULATED = "calculated"      # deterministic metric from observed data
    INFERRED = "inferred"          # derived risk/heuristic
    FORECAST = "forecast"          # projection with assumptions
    RECOMMENDED = "recommended"    # a proposed action
    UNAVAILABLE = "unavailable"    # no verified data source


class GoalStatus(str, Enum):
    ACTIVE = "active"
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    BEHIND = "behind"
    ACHIEVED = "achieved"
    MISSED = "missed"
    ARCHIVED = "archived"


class DecisionStatus(str, Enum):
    PROPOSED = "proposed"
    RESEARCHING = "researching"
    AWAITING_DECISION = "awaiting_decision"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    SUPERSEDED = "superseded"
    IMPLEMENTED = "implemented"
    REVIEWED = "reviewed"


_DECISION_TRANSITIONS = {
    DecisionStatus.PROPOSED: {DecisionStatus.RESEARCHING, DecisionStatus.AWAITING_DECISION,
                             DecisionStatus.REJECTED, DecisionStatus.DEFERRED},
    DecisionStatus.RESEARCHING: {DecisionStatus.AWAITING_DECISION, DecisionStatus.DEFERRED},
    DecisionStatus.AWAITING_DECISION: {DecisionStatus.APPROVED, DecisionStatus.REJECTED,
                                       DecisionStatus.DEFERRED, DecisionStatus.SUPERSEDED},
    DecisionStatus.APPROVED: {DecisionStatus.IMPLEMENTED, DecisionStatus.SUPERSEDED},
    DecisionStatus.IMPLEMENTED: {DecisionStatus.REVIEWED},
    DecisionStatus.DEFERRED: {DecisionStatus.AWAITING_DECISION, DecisionStatus.REJECTED},
    DecisionStatus.REJECTED: set(),
    DecisionStatus.SUPERSEDED: set(),
    DecisionStatus.REVIEWED: set(),
}

# statuses only an authorized human may set (agents cannot self-finalize)
PROTECTED_DECISION_STATES = {DecisionStatus.APPROVED, DecisionStatus.REJECTED,
                            DecisionStatus.IMPLEMENTED}


class IllegalDecisionTransition(Exception):
    pass


def validate_decision_transition(src: DecisionStatus, dst: DecisionStatus) -> None:
    if dst not in _DECISION_TRANSITIONS.get(src, set()):
        raise IllegalDecisionTransition(f"illegal decision transition {src.value} → {dst.value}")


class RiskStatus(str, Enum):
    OPEN = "open"
    MITIGATING = "mitigating"
    ACCEPTED = "accepted"
    CLOSED = "closed"
    REALIZED = "realized"


RISK_CATEGORIES = {"financial", "operational", "technical", "security", "legal",
                   "provider", "product", "customer", "staffing", "reputation",
                   "schedule", "storage", "deployment", "data_loss"}


class OpportunityStatus(str, Enum):
    IDENTIFIED = "identified"
    EVALUATING = "evaluating"
    PURSUING = "pursuing"
    CONVERTED = "converted"
    DECLINED = "declined"


class ProjectHealth(str, Enum):
    ON_TRACK = "on_track"
    ATTENTION = "attention"
    AT_RISK = "at_risk"
    BLOCKED = "blocked"
    PAUSED = "paused"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


class FinancialState(str, Enum):
    ACTUAL = "actual"          # from an authoritative financial record
    ESTIMATED = "estimated"    # a labeled estimate
    FORECAST = "forecast"      # a projection
    UNKNOWN = "unknown"        # no source


class KPIType(str, Enum):
    REVENUE = "revenue"
    PROFIT = "profit"
    CASH = "cash"
    EXPENSE = "expense"
    USERS = "users"
    ACTIVE_USERS = "active_users"
    RETENTION = "retention"
    CONVERSION = "conversion"
    CONTENT_OUTPUT = "content_output"
    VIEWS = "views"
    LEADS = "leads"
    TASK_COMPLETION = "task_completion"
    MISSION_COMPLETION = "mission_completion"
    UPTIME = "uptime"
    INCIDENT_COUNT = "incident_count"
    TEST_HEALTH = "test_health"
    STORAGE_HEALTH = "storage_health"
    PROVIDER_HEALTH = "provider_health"
    DREAM_PROGRESS = "dream_progress"
    CUSTOM = "custom"


@dataclass
class Provenance:
    source: str = ""              # e.g. "missions.store", "manual", "ops.storage"
    authority: str = "internal"   # internal | authoritative | estimated | none
    freshness_sec: Optional[float] = None
    evidence_tier: str = EvidenceTier.UNAVAILABLE.value
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# priority factors (deterministic weights; LLM may recommend adjustments only)
PRIORITY_WEIGHTS = {
    "revenue_impact": 20,
    "customer_impact": 15,
    "strategic_alignment": 20,
    "risk_reduction": 12,
    "dependency_blocking": 18,
    "deadline_urgency": 15,
    "low_risk_bonus": 10,
    "provider_unavailable_penalty": -12,
    "high_effort_penalty": -8,
}
