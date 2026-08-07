"""M216–M223 Broker Integration Sandbox Architecture & Trust Framework.

PAPER ONLY. No live brokers. No real credentials. No exchange authentication.
"""
from saathi.platform.tg.broker_sandbox.models import (
    SCHEMA_VERSION,
    ENGINE_VERSION,
    TERMINAL_VERDICT,
    LIVE_TRADING_AUTHORIZED,
    LIVE_ORDER_CAPABLE,
    BROKER_CREDENTIAL_SUPPORT,
    REAL_BROKER_CONNECTION_CAPABLE,
    LLM_BOUNDARY,
    PAPER_POSTURE,
    ConnectionStatus,
    BrokerLifecycle,
    TrustApprovalStage,
    TrustPipelineStatus,
    FailureScenario,
)
from saathi.platform.tg.broker_sandbox.service import (
    BrokerSandboxService,
    BrokerSandboxError,
    default_broker_sandbox,
    reset_broker_sandbox_for_tests,
)

__all__ = [
    "SCHEMA_VERSION",
    "ENGINE_VERSION",
    "TERMINAL_VERDICT",
    "LIVE_TRADING_AUTHORIZED",
    "LIVE_ORDER_CAPABLE",
    "BROKER_CREDENTIAL_SUPPORT",
    "REAL_BROKER_CONNECTION_CAPABLE",
    "LLM_BOUNDARY",
    "PAPER_POSTURE",
    "ConnectionStatus",
    "BrokerLifecycle",
    "TrustApprovalStage",
    "TrustPipelineStatus",
    "FailureScenario",
    "BrokerSandboxService",
    "BrokerSandboxError",
    "default_broker_sandbox",
    "reset_broker_sandbox_for_tests",
]
