"""M280–M287 Autonomous Research Orchestrator — models and authority locks.

RESEARCH ONLY. OFFLINE-FIRST. PAPER/SANDBOX ONLY.
NO BROKER. NO API KEYS. NO ORDER EXECUTION. NO LIVE TRADING.
Maximum authority: AUTONOMOUS_RESEARCH_ORCHESTRATION_ONLY
"""
from __future__ import annotations

from enum import Enum

SCHEMA_VERSION = "m280.research_orchestrator.v1"
ENGINE_VERSION = "m280.research_orchestrator.engine.v1"

TERMINAL_VERDICT = "AUTONOMOUS_RESEARCH_ORCHESTRATOR_CERTIFIED_WITH_LIMITATIONS"
MAX_STATE = "AUTONOMOUS_RESEARCH_ORCHESTRATION_ONLY"
BROWSER_CERT_VERDICT = "AUTONOMOUS_RESEARCH_ORCHESTRATOR_BROWSER_CERT_PASSED_WITH_LIMITATIONS"
MAX_AUTHORITY = "AUTONOMOUS_RESEARCH_ORCHESTRATION_ONLY"

LIVE_TRADING_AUTHORIZED = False
BROKER_CONNECTIVITY_AUTHORIZED = False
REAL_CONNECTIVITY_AUTHORIZED = False
CREDENTIAL_PROVISIONING_AUTHORIZED = False
CANARY_ACTIVATION_AUTHORIZED = False
ORDER_EXECUTION_AUTHORIZED = False
ORDER_SUBMISSION_AUTHORIZED = False
API_KEYS_ACCEPTED = False
OAUTH_AUTHORIZED = False
PAPER_EXECUTION_AUTHORIZED = False
AUTOMATED_INVESTMENT_AUTHORITY = False
PRODUCTION_AUTHORIZED = False
STRATEGY_PROFITABILITY_GUARANTEED = False
INVESTMENT_ADVICE_CERTIFIED = False
LIVE_MARKET_READINESS = False

# Orchestrator defaults (deterministic, bounded)
DEFAULT_MAX_WORKERS = 2
DEFAULT_COMPUTE_BUDGET_UNITS = 1000
DEFAULT_MAX_RETRIES = 2
DEFAULT_PRIORITY = 50
MAX_QUEUE_DEPTH = 500
MAX_JOURNAL_ENTRIES = 10_000

AUTHORITY_VALUES = {
    "LIVE_TRADING_AUTHORIZED": False,
    "BROKER_CONNECTIVITY_AUTHORIZED": False,
    "REAL_CONNECTIVITY_AUTHORIZED": False,
    "CREDENTIAL_PROVISIONING_AUTHORIZED": False,
    "CANARY_ACTIVATION_AUTHORIZED": False,
    "ORDER_EXECUTION_AUTHORIZED": False,
    "ORDER_SUBMISSION_AUTHORIZED": False,
    "API_KEYS_ACCEPTED": False,
    "OAUTH_AUTHORIZED": False,
    "PAPER_EXECUTION_AUTHORIZED": False,
    "AUTOMATED_INVESTMENT_AUTHORITY": False,
    "PRODUCTION_AUTHORIZED": False,
    "STRATEGY_PROFITABILITY_GUARANTEED": False,
    "INVESTMENT_ADVICE_CERTIFIED": False,
    "LIVE_MARKET_READINESS": False,
    "paper_only": True,
    "sandbox_only": True,
    "research_only": True,
    "offline_first": True,
    "offline_capable": True,
    "no_broker_connection": True,
    "no_api_keys": True,
    "no_oauth": True,
    "no_order_submission": True,
    "no_live_trading": True,
    "deterministic_orchestration": True,
    "max_authority": MAX_AUTHORITY,
}

TERMINAL_STATEMENTS = (
    "RESEARCH ONLY",
    "OFFLINE-FIRST",
    "PAPER ONLY",
    "SANDBOX ONLY",
    "NO BROKER CONNECTIVITY",
    "NO ACCOUNT ACCESS",
    "NO CREDENTIALS",
    "NO ORDER EXECUTION",
    "NO LIVE TRADING",
    "AUTONOMOUS RESEARCH ORCHESTRATION ONLY",
    "NO GUARANTEED PROFITABILITY",
    "DETERMINISTIC WORKERS — NO HIDDEN TRIALS",
)

ORCH_POSTURE = {
    "mode": "AUTONOMOUS_RESEARCH_ORCHESTRATION_ONLY",
    "broker_connected": False,
    "credentials_loaded": False,
    "live_data": False,
    "orders_enabled": False,
    "canary_active": False,
    "paper_execution_enabled": False,
    "max_authority": MAX_AUTHORITY,
    "max_workers": DEFAULT_MAX_WORKERS,
}

LLM_BOUNDARY = {
    "may_propose_experiments": True,
    "may_summarise_queue": True,
    "may_explain_failures": True,
    "may_draft_hypotheses": True,
    "may_prepare_journal_entries": True,
    "may_mutate_completed_results": False,
    "may_bypass_budget": False,
    "may_bypass_priority": False,
    "may_inject_hidden_trials": False,
    "may_authorize_execution": False,
    "may_request_credentials": False,
    "may_connect_broker": False,
    "may_place_orders": False,
    "may_claim_guaranteed_performance": False,
}


class JobState(str, Enum):
    DRAFT = "DRAFT"
    QUEUED = "QUEUED"
    BLOCKED = "BLOCKED"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"
    SUSPENDED = "SUSPENDED"
    RESUMED = "RESUMED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class JobPriority(str, Enum):
    CRITICAL = "CRITICAL"  # 10
    HIGH = "HIGH"  # 30
    NORMAL = "NORMAL"  # 50
    LOW = "LOW"  # 70
    BACKGROUND = "BACKGROUND"  # 90


PRIORITY_RANK = {
    JobPriority.CRITICAL.value: 10,
    JobPriority.HIGH.value: 30,
    JobPriority.NORMAL.value: 50,
    JobPriority.LOW.value: 70,
    JobPriority.BACKGROUND.value: 90,
}


class WorkerState(str, Enum):
    IDLE = "IDLE"
    BUSY = "BUSY"
    DRAINING = "DRAINING"
    OFFLINE = "OFFLINE"


class BudgetState(str, Enum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    EXHAUSTED = "EXHAUSTED"
    EXCEEDED = "EXCEEDED"


class PromotionState(str, Enum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PROMOTED_TEMPLATE = "PROMOTED_TEMPLATE"
    PROMOTED_REGISTRY = "PROMOTED_REGISTRY"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"
