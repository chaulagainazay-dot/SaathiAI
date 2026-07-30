"""M216–M223 Broker Integration Sandbox — domain models.

PAPER ONLY. No live brokers. No real credentials. No exchange connections.
"""
from __future__ import annotations

from enum import Enum

SCHEMA_VERSION = "m216.broker_sandbox.v1"
ENGINE_VERSION = "m216.broker_sandbox.engine.v1"

TERMINAL_VERDICT = "BROKER_SANDBOX_ARCHITECTURE_CERTIFIED_WITH_LIMITATIONS"

# Hard authority flags — never flip true in this milestone.
LIVE_TRADING_AUTHORIZED = False
LIVE_ORDER_CAPABLE = False
BROKER_CREDENTIAL_SUPPORT = False  # real secrets never accepted
REAL_BROKER_CONNECTION_CAPABLE = False
EXCHANGE_AUTH_CAPABLE = False
OAUTH_CAPABLE = False
PRODUCTION_DEPLOY_CAPABLE = False


class ConnectionStatus(str, Enum):
    """Every catalog broker stays NOT_CONNECTED in this milestone."""
    NOT_CONNECTED = "NOT_CONNECTED"
    SANDBOX_ONLY = "SANDBOX_ONLY"
    DISCONNECTED = "DISCONNECTED"
    # Intentionally NO CONNECTED / LIVE / AUTHENTICATED states that enable real I/O.


class BrokerLifecycle(str, Enum):
    CATALOGED = "CATALOGED"
    CAPABILITY_DECLARED = "CAPABILITY_DECLARED"
    TRUST_PENDING = "TRUST_PENDING"
    APPROVED_FOR_SANDBOX = "APPROVED_FOR_SANDBOX"
    SANDBOX_ACTIVE = "SANDBOX_ACTIVE"
    REVOKED = "REVOKED"
    REJECTED = "REJECTED"
    # No LIVE / PRODUCTION states.


class AssetClass(str, Enum):
    EQUITY = "EQUITY"
    CRYPTO = "CRYPTO"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    FX = "FX"
    OTHER = "OTHER"


class OrderTypeCapability(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class AuthMethodDeclared(str, Enum):
    """Declared auth methods for future design — never exercised against live endpoints."""
    NONE = "NONE"
    API_KEY_HEADER = "API_KEY_HEADER"
    API_KEY_QUERY = "API_KEY_QUERY"
    OAUTH2 = "OAUTH2"
    HMAC_SIGNED = "HMAC_SIGNED"
    CERTIFICATE = "CERTIFICATE"
    SESSION_TOKEN = "SESSION_TOKEN"
    SANDBOX_EMULATOR = "SANDBOX_EMULATOR"


class CredentialRefStatus(str, Enum):
    """Metadata-only credential reference status. No secret material is ever stored."""
    PLACEHOLDER = "PLACEHOLDER"
    METADATA_ONLY = "METADATA_ONLY"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED_METADATA = "APPROVED_METADATA"
    UNUSABLE = "UNUSABLE"  # always the runtime usability for secrets


class TrustApprovalStage(str, Enum):
    OWNER = "OWNER"
    SECURITY = "SECURITY"
    CREDENTIAL = "CREDENTIAL"
    RISK = "RISK"
    ENVIRONMENT = "ENVIRONMENT"
    SIMULATION = "SIMULATION"
    PAPER_GRADUATION = "PAPER_GRADUATION"
    MANUAL_CONFIRMATION = "MANUAL_CONFIRMATION"


class TrustPipelineStatus(str, Enum):
    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    FULLY_APPROVED_SANDBOX = "FULLY_APPROVED_SANDBOX"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"
    # Never LIVE_APPROVED.


class FailureScenario(str, Enum):
    NETWORK_LOSS = "NETWORK_LOSS"
    BROKER_OUTAGE = "BROKER_OUTAGE"
    DUPLICATE_FILLS = "DUPLICATE_FILLS"
    LATE_FILLS = "LATE_FILLS"
    CLOCK_SKEW = "CLOCK_SKEW"
    ORDER_REPLAY = "ORDER_REPLAY"
    SEQUENCE_GAPS = "SEQUENCE_GAPS"
    CONNECTION_LOSS = "CONNECTION_LOSS"
    CREDENTIAL_EXPIRY = "CREDENTIAL_EXPIRY"
    RECOVERY = "RECOVERY"
    ROLLBACK = "ROLLBACK"
    RATE_LIMIT = "RATE_LIMIT"
    MARKET_CLOSED = "MARKET_CLOSED"
    INVALID_SYMBOL = "INVALID_SYMBOL"
    TIMEOUT = "TIMEOUT"
    PARTIAL_FILL = "PARTIAL_FILL"
    REJECT = "REJECT"
    LATENCY = "LATENCY"
    DISCONNECT = "DISCONNECT"


class EmulatorOrderState(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"


class SecurityCheckResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    FAIL_CLOSED = "FAIL_CLOSED"


LLM_BOUNDARY = {
    "llm_may_explain": True,
    "llm_may_recommend": True,
    "llm_may_analyse": True,
    "llm_may_compare": True,
    "llm_may_generate_reports": True,
    "llm_may_simulate": True,
    # Forbidden
    "llm_may_connect_brokers": False,
    "llm_may_store_credentials": False,
    "llm_may_approve_credentials": False,
    "llm_may_approve_brokers": False,
    "llm_may_execute_orders": False,
    "llm_may_enable_live_mode": False,
    "llm_may_authorize_trading": False,
    "llm_may_bypass_approval": False,
}

PAPER_POSTURE = {
    "paper_only": True,
    "live_trading_authorized": False,
    "live_order_capable": False,
    "broker_credential_support": False,
    "real_broker_connection_capable": False,
    "exchange_auth_capable": False,
    "oauth_capable": False,
    "production_deploy_capable": False,
    "exchange_connected": False,
    "sandbox_only": True,
    "funds_label": "SIMULATED",
    "disclaimer": (
        "THE SYSTEM REMAINS PAPER ONLY. "
        "NO BROKER CONNECTIONS EXIST. "
        "NO API CREDENTIALS WERE CREATED. "
        "NO LIVE TRADING IS AUTHORIZED. "
        "THE SANDBOX CANNOT EXECUTE REAL ORDERS."
    ),
}

REQUIRED_TRUST_STAGES = [
    TrustApprovalStage.OWNER,
    TrustApprovalStage.SECURITY,
    TrustApprovalStage.CREDENTIAL,
    TrustApprovalStage.RISK,
    TrustApprovalStage.ENVIRONMENT,
    TrustApprovalStage.SIMULATION,
    TrustApprovalStage.PAPER_GRADUATION,
    TrustApprovalStage.MANUAL_CONFIRMATION,
]

# Catalog of conceptual brokers — all permanently NOT_CONNECTED.
CATALOG_BROKERS = [
    {
        "broker_id": "sandbox.emulator",
        "display_name": "Sandbox Emulator",
        "provider": "SAATHI_SANDBOX",
        "description": "Deterministic in-process emulator. The only executable broker surface.",
        "is_emulator": True,
    },
    {
        "broker_id": "catalog.binance",
        "display_name": "Binance (Catalog Only)",
        "provider": "BINANCE",
        "description": "Capability placeholder. NOT_CONNECTED. No API keys. No OAuth.",
        "is_emulator": False,
    },
    {
        "broker_id": "catalog.alpaca",
        "display_name": "Alpaca (Catalog Only)",
        "provider": "ALPACA",
        "description": "Capability placeholder. NOT_CONNECTED. No API keys. No OAuth.",
        "is_emulator": False,
    },
    {
        "broker_id": "catalog.interactive_brokers",
        "display_name": "Interactive Brokers (Catalog Only)",
        "provider": "INTERACTIVE_BROKERS",
        "description": "Capability placeholder. NOT_CONNECTED. No API keys. No OAuth.",
        "is_emulator": False,
    },
    {
        "broker_id": "catalog.zerodha",
        "display_name": "Zerodha (Catalog Only)",
        "provider": "ZERODHA",
        "description": "Capability placeholder. NOT_CONNECTED. No API keys. No OAuth.",
        "is_emulator": False,
    },
    {
        "broker_id": "catalog.bybit",
        "display_name": "Bybit (Catalog Only)",
        "provider": "BYBIT",
        "description": "Capability placeholder. NOT_CONNECTED. No API keys. No OAuth.",
        "is_emulator": False,
    },
    {
        "broker_id": "catalog.coinbase",
        "display_name": "Coinbase (Catalog Only)",
        "provider": "COINBASE",
        "description": "Capability placeholder. NOT_CONNECTED. No API keys. No OAuth.",
        "is_emulator": False,
    },
    {
        "broker_id": "catalog.kraken",
        "display_name": "Kraken (Catalog Only)",
        "provider": "KRAKEN",
        "description": "Capability placeholder. NOT_CONNECTED. No API keys. No OAuth.",
        "is_emulator": False,
    },
]

PROHIBITED_SECRET_KEYS = frozenset({
    "api_key", "api_secret", "secret", "password", "private_key", "access_token",
    "refresh_token", "bearer", "client_secret", "oauth_token", "session_key",
    "signing_key", "passphrase", "seed", "mnemonic", "credential", "token",
})

__all__ = [
    "SCHEMA_VERSION",
    "ENGINE_VERSION",
    "TERMINAL_VERDICT",
    "LIVE_TRADING_AUTHORIZED",
    "LIVE_ORDER_CAPABLE",
    "BROKER_CREDENTIAL_SUPPORT",
    "REAL_BROKER_CONNECTION_CAPABLE",
    "EXCHANGE_AUTH_CAPABLE",
    "OAUTH_CAPABLE",
    "PRODUCTION_DEPLOY_CAPABLE",
    "ConnectionStatus",
    "BrokerLifecycle",
    "AssetClass",
    "OrderTypeCapability",
    "AuthMethodDeclared",
    "CredentialRefStatus",
    "TrustApprovalStage",
    "TrustPipelineStatus",
    "FailureScenario",
    "EmulatorOrderState",
    "SecurityCheckResult",
    "LLM_BOUNDARY",
    "PAPER_POSTURE",
    "REQUIRED_TRUST_STAGES",
    "CATALOG_BROKERS",
    "PROHIBITED_SECRET_KEYS",
]
