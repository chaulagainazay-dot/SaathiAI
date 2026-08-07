"""M224–M231 Read-Only Broker Connectivity Readiness and Credential Lifecycle Simulation.

SIMULATION ONLY. No real brokers. No real credentials. No order submission.
"""
from saathi.platform.tg.broker_readiness.models import (
    SCHEMA_VERSION,
    ENGINE_VERSION,
    TERMINAL_VERDICT,
    LIVE_TRADING_AUTHORIZED,
    REAL_BROKER_CONNECTION_CAPABLE,
    CREDENTIAL_USABLE_FOR_REAL_CONNECTION,
    LLM_BOUNDARY,
    READINESS_POSTURE,
    AuthorityClass,
    PolicyDecision,
    CredentialLifecycleState,
    ConnectionState,
    ScopeOutcome,
)
from saathi.platform.tg.broker_readiness.service import (
    BrokerReadinessService,
    BrokerReadinessError,
    default_broker_readiness,
    reset_broker_readiness_for_tests,
)
from saathi.platform.tg.broker_readiness.transport import (
    REAL_PROVIDER_TRANSPORT_FORBIDDEN,
    TransportGuard,
)

__all__ = [
    "SCHEMA_VERSION",
    "ENGINE_VERSION",
    "TERMINAL_VERDICT",
    "LIVE_TRADING_AUTHORIZED",
    "REAL_BROKER_CONNECTION_CAPABLE",
    "CREDENTIAL_USABLE_FOR_REAL_CONNECTION",
    "LLM_BOUNDARY",
    "READINESS_POSTURE",
    "AuthorityClass",
    "PolicyDecision",
    "CredentialLifecycleState",
    "ConnectionState",
    "ScopeOutcome",
    "BrokerReadinessService",
    "BrokerReadinessError",
    "default_broker_readiness",
    "reset_broker_readiness_for_tests",
    "REAL_PROVIDER_TRANSPORT_FORBIDDEN",
    "TransportGuard",
]
