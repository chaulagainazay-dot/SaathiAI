"""M208–M215 operational graduation domain models.

PAPER ONLY. Graduation never authorizes live trading.
"""
from __future__ import annotations

from enum import Enum

SCHEMA_VERSION = "m208.ops.graduation.v1"
ENGINE_VERSION = "m208.ops.engine.v1"


class HealthClass(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    FAILED_SAFE = "FAILED_SAFE"


class StrategyClassification(str, Enum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    PAPER_ACTIVE = "PAPER_ACTIVE"
    PAPER_VALIDATED = "PAPER_VALIDATED"
    PAPER_GRADUATE = "PAPER_GRADUATE"
    MORE_EVIDENCE_REQUIRED = "MORE_EVIDENCE_REQUIRED"
    REJECTED = "REJECTED"


class CampaignCertOutcome(str, Enum):
    VALIDATED = "VALIDATED"
    VALIDATED_WITH_LIMITATIONS = "VALIDATED_WITH_LIMITATIONS"
    MORE_EVIDENCE_REQUIRED = "MORE_EVIDENCE_REQUIRED"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    REJECTED = "REJECTED"


class CampaignStatusExt(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"
    SCHEDULED = "SCHEDULED"


# Terminal platform verdict for M208–M215
TERMINAL_VERDICT = "OPERATIONAL_GRADUATION_CERTIFIED_WITH_LIMITATIONS"

LLM_BOUNDARY = {
    "llm_may_approve_campaigns": False,
    "llm_may_graduate_strategies": False,
    "llm_may_change_metrics": False,
    "llm_may_modify_journals": False,
    "llm_may_modify_evidence": False,
    "llm_may_override_risk": False,
    "llm_may_override_reconciliation": False,
    "llm_may_execute_trades": False,
    "llm_may_authorize_live": False,
    "may_explain": True,
    "may_summarize": True,
    "may_compare": True,
    "may_recommend": True,
    "may_generate_reports": True,
    "may_identify_anomalies": True,
    "may_draft_documentation": True,
}

PAPER_POSTURE = {
    "paper_only": True,
    "live_trading_authorized": False,
    "live_order_capable": False,
    "broker_credential_support": False,
    "exchange_connected": False,
    "strategy_auto_promoted_to_live": False,
    "funds_label": "SIMULATED",
    "disclaimer": (
        "THE SYSTEM REMAINS PAPER ONLY. "
        "LIVE TRADING IS NOT AUTHORIZED. "
        "NO STRATEGY IS AUTOMATICALLY PROMOTED TO LIVE EXECUTION."
    ),
}
