"""M62.7 — automated paper-trading circuit breakers, safety sweeps, alert
escalation, acknowledgement, and fail-closed reset controls.

Simulation only. Breakers HALT/FREEZE/REJECT/ACKNOWLEDGE and (fail-closed) RESET a
bounded scope; they NEVER repair financial state and never touch fills, positions,
cash, or the ledger. Reconciliation (M62.6) remains the authoritative integrity
verifier. No live broker, real money, leverage, margin, short-selling, options,
futures, perpetuals, derivatives, borrowing, credentials, or network access exists.
PAPER only; long-only; localhost-only. Breaker mutations flow exclusively through the
registered ``paper_safety.*`` tools under ExecutionGateway.
"""
from saathi.platform.safety.models import (
    BreakerType, BreakerScope, BreakerState, OpenOrderPolicy, AlertLevel, Severity, SweepStatus,
    CircuitBreakerDefinition, CircuitBreakerState, CircuitBreakerTrip, SafetyMetricSnapshot,
    SafetyFinding, BreakerAcknowledgement, BreakerResetRequest, BreakerResetDecision,
    can_breaker_transition, default_open_order_policy, default_alert_level, assert_safety_safe,
    is_agent_actor, trading_day, BLOCKING_STATES, BROAD_SCOPES, SAFETY_ENGINE_VERSION,
    PROHIBITED_SAFETY_TOKENS,
)
from saathi.platform.safety.store import SafetyStore
from saathi.platform.safety.metrics import MetricsCollector
from saathi.platform.safety.evaluator import BreakerEvaluator, default_account_breakers
from saathi.platform.safety.service import SafetyService
from saathi.platform.safety import orchestration
from saathi.platform.safety.execution_tool import (
    register_safety_tools, paper_safety_manifests, default_safety_service, set_safety_service_for_tests,
)

__all__ = [
    "BreakerType", "BreakerScope", "BreakerState", "OpenOrderPolicy", "AlertLevel", "Severity", "SweepStatus",
    "CircuitBreakerDefinition", "CircuitBreakerState", "CircuitBreakerTrip", "SafetyMetricSnapshot",
    "SafetyFinding", "BreakerAcknowledgement", "BreakerResetRequest", "BreakerResetDecision",
    "can_breaker_transition", "default_open_order_policy", "default_alert_level", "assert_safety_safe",
    "is_agent_actor", "trading_day", "BLOCKING_STATES", "BROAD_SCOPES", "SAFETY_ENGINE_VERSION",
    "PROHIBITED_SAFETY_TOKENS",
    "SafetyStore", "MetricsCollector", "BreakerEvaluator", "default_account_breakers",
    "SafetyService", "orchestration", "register_safety_tools", "paper_safety_manifests",
    "default_safety_service", "set_safety_service_for_tests",
]
