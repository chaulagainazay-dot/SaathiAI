"""M224–M231 Read-Only Broker Connectivity Readiness — domain models.

SIMULATION ONLY. No real brokers. No real credentials. No order submission.
"""
from __future__ import annotations

from enum import Enum

SCHEMA_VERSION = "m224.broker_readiness.v1"
ENGINE_VERSION = "m224.broker_readiness.engine.v1"

TERMINAL_VERDICT = "READ_ONLY_BROKER_READINESS_CERTIFIED_WITH_LIMITATIONS"

# Hard authority locks — never true in this milestone.
LIVE_TRADING_AUTHORIZED = False
LIVE_ORDER_CAPABLE = False
REAL_BROKER_CONNECTION_CAPABLE = False
REAL_CREDENTIAL_ACCEPTANCE = False
ORDER_SUBMISSION_CAPABLE = False
ORDER_CANCELLATION_CAPABLE = False
PRODUCTION_READ_ONLY_AUTHORITY = False
CREDENTIAL_USABLE_FOR_REAL_CONNECTION = False


class AuthorityClass(str, Enum):
    PUBLIC_DATA = "PUBLIC_DATA"
    READ_ONLY_ACCOUNT = "READ_ONLY_ACCOUNT"
    TRADING_WRITE = "TRADING_WRITE"
    TRANSFER_WRITE = "TRANSFER_WRITE"
    ADMINISTRATIVE_WRITE = "ADMINISTRATIVE_WRITE"
    FORBIDDEN = "FORBIDDEN"


class PolicyDecision(str, Enum):
    ALLOW_SIMULATION_ONLY = "ALLOW_SIMULATION_ONLY"
    READINESS_APPROVED_NOT_CONNECTED = "READINESS_APPROVED_NOT_CONNECTED"
    DENY_WRITE_SCOPE = "DENY_WRITE_SCOPE"
    DENY_EXCESS_PERMISSION = "DENY_EXCESS_PERMISSION"
    DENY_EXPIRED = "DENY_EXPIRED"
    DENY_REVOKED = "DENY_REVOKED"
    DENY_UNAPPROVED = "DENY_UNAPPROVED"
    DENY_WRONG_ENVIRONMENT = "DENY_WRONG_ENVIRONMENT"
    DENY_REAL_CONNECTION = "DENY_REAL_CONNECTION"
    DENY_UNKNOWN_CAPABILITY = "DENY_UNKNOWN_CAPABILITY"
    FAIL_CLOSED = "FAIL_CLOSED"


class CredentialLifecycleState(str, Enum):
    PROPOSED = "proposed"
    CLASSIFIED = "classified"
    SCOPE_REVIEWED = "scope-reviewed"
    SECURITY_REVIEWED = "security-reviewed"
    OWNER_REVIEWED = "owner-reviewed"
    APPROVED_FOR_SIMULATION = "approved-for-simulation"
    ACTIVATED_IN_SIMULATION = "activated-in-simulation"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    ROTATION_REQUIRED = "rotation-required"
    ROTATED_IN_SIMULATION = "rotated-in-simulation"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    DESTROYED = "destroyed"
    ARCHIVED = "archived"


class ConnectionState(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    METADATA_PROPOSED = "METADATA_PROPOSED"
    UNDER_REVIEW = "UNDER_REVIEW"
    SIMULATION_APPROVED = "SIMULATION_APPROVED"
    SIMULATED_CONNECTING = "SIMULATED_CONNECTING"
    SIMULATED_CONNECTED_READ_ONLY = "SIMULATED_CONNECTED_READ_ONLY"
    SIMULATED_DEGRADED = "SIMULATED_DEGRADED"
    SIMULATED_RATE_LIMITED = "SIMULATED_RATE_LIMITED"
    SIMULATED_EXPIRED = "SIMULATED_EXPIRED"
    SIMULATED_REVOKED = "SIMULATED_REVOKED"
    SIMULATED_DISCONNECTED = "SIMULATED_DISCONNECTED"
    SIMULATED_FAILED_SAFE = "SIMULATED_FAILED_SAFE"
    REAL_CONNECTION_FORBIDDEN = "REAL_CONNECTION_FORBIDDEN"


class ScopeOutcome(str, Enum):
    LEAST_PRIVILEGE_CONFIRMED_IN_SIMULATION = "LEAST_PRIVILEGE_CONFIRMED_IN_SIMULATION"
    EXCESS_SCOPE_REJECTED = "EXCESS_SCOPE_REJECTED"
    SCOPE_MISMATCH_REJECTED = "SCOPE_MISMATCH_REJECTED"
    WRITE_PERMISSION_REJECTED = "WRITE_PERMISSION_REJECTED"
    UNKNOWN_SCOPE_REJECTED = "UNKNOWN_SCOPE_REJECTED"


class ReconciliationClass(str, Enum):
    MATCHED = "MATCHED"
    TIMING_DIFFERENCE = "TIMING_DIFFERENCE"
    ROUNDING_DIFFERENCE = "ROUNDING_DIFFERENCE"
    MISSING_PROVIDER_RECORD = "MISSING_PROVIDER_RECORD"
    MISSING_LOCAL_RECORD = "MISSING_LOCAL_RECORD"
    DUPLICATE_RECORD = "DUPLICATE_RECORD"
    STALE_SNAPSHOT = "STALE_SNAPSHOT"
    PERMISSION_MISMATCH = "PERMISSION_MISMATCH"
    UNKNOWN_ASSET = "UNKNOWN_ASSET"
    CRITICAL_RECONCILIATION_FAILURE = "CRITICAL_RECONCILIATION_FAILURE"


# Adapter operations (M224) — authority-classified.
ADAPTER_OPERATIONS: dict[str, AuthorityClass] = {
    "provider_identity": AuthorityClass.PUBLIC_DATA,
    "provider_capabilities": AuthorityClass.PUBLIC_DATA,
    "connection_status": AuthorityClass.PUBLIC_DATA,
    "server_time": AuthorityClass.PUBLIC_DATA,
    "provider_health": AuthorityClass.PUBLIC_DATA,
    "rate_limit_status": AuthorityClass.PUBLIC_DATA,
    "supported_assets": AuthorityClass.PUBLIC_DATA,
    "account_metadata": AuthorityClass.READ_ONLY_ACCOUNT,
    "account_type": AuthorityClass.READ_ONLY_ACCOUNT,
    "balances": AuthorityClass.READ_ONLY_ACCOUNT,
    "positions": AuthorityClass.READ_ONLY_ACCOUNT,
    "portfolio_snapshot": AuthorityClass.READ_ONLY_ACCOUNT,
    "transaction_history": AuthorityClass.READ_ONLY_ACCOUNT,
    "deposit_history": AuthorityClass.READ_ONLY_ACCOUNT,
    "withdrawal_history": AuthorityClass.READ_ONLY_ACCOUNT,
    "order_history": AuthorityClass.READ_ONLY_ACCOUNT,
    "trade_history": AuthorityClass.READ_ONLY_ACCOUNT,
    "fee_history": AuthorityClass.READ_ONLY_ACCOUNT,
    "market_permissions": AuthorityClass.READ_ONLY_ACCOUNT,
    "account_permissions": AuthorityClass.READ_ONLY_ACCOUNT,
    "session_health": AuthorityClass.READ_ONLY_ACCOUNT,
    # Write ops classified but never exposed by M224 adapter.
    "place_order": AuthorityClass.TRADING_WRITE,
    "cancel_order": AuthorityClass.TRADING_WRITE,
    "modify_order": AuthorityClass.TRADING_WRITE,
    "withdraw": AuthorityClass.TRANSFER_WRITE,
    "transfer": AuthorityClass.TRANSFER_WRITE,
    "admin_change": AuthorityClass.ADMINISTRATIVE_WRITE,
}

ALLOWED_ADAPTER_AUTHORITIES = frozenset({
    AuthorityClass.PUBLIC_DATA,
    AuthorityClass.READ_ONLY_ACCOUNT,
})

ALLOWED_SCOPES = frozenset({
    "ACCOUNT_METADATA_READ",
    "BALANCE_READ",
    "POSITION_READ",
    "PORTFOLIO_READ",
    "ORDER_HISTORY_READ",
    "TRADE_HISTORY_READ",
    "TRANSACTION_HISTORY_READ",
    "FEE_HISTORY_READ",
    "MARKET_DATA_READ",
    "ACCOUNT_PERMISSION_READ",
})

FORBIDDEN_SCOPES = frozenset({
    "ORDER_CREATE",
    "ORDER_CANCEL",
    "ORDER_MODIFY",
    "TRADING_ENABLE",
    "WITHDRAWAL_CREATE",
    "WITHDRAWAL_APPROVE",
    "TRANSFER_CREATE",
    "TRANSFER_APPROVE",
    "ACCOUNT_ADMIN",
    "API_KEY_ADMIN",
    "SUBACCOUNT_ADMIN",
    "MARGIN_ENABLE",
    "LEVERAGE_ENABLE",
})

# Forbidden permission keywords in any declared set.
FORBIDDEN_PERMISSION_KEYWORDS = frozenset({
    "trading", "order placement", "order_placement", "order cancellation",
    "order_cancellation", "withdrawal", "transfer", "account administration",
    "api-key management", "api_key_management", "sub-account management",
    "subaccount", "order_create", "order_cancel", "withdraw",
})

CREDENTIAL_LIFECYCLE_ORDER = [
    CredentialLifecycleState.PROPOSED,
    CredentialLifecycleState.CLASSIFIED,
    CredentialLifecycleState.SCOPE_REVIEWED,
    CredentialLifecycleState.SECURITY_REVIEWED,
    CredentialLifecycleState.OWNER_REVIEWED,
    CredentialLifecycleState.APPROVED_FOR_SIMULATION,
    CredentialLifecycleState.ACTIVATED_IN_SIMULATION,
    CredentialLifecycleState.EXPIRING,
    CredentialLifecycleState.EXPIRED,
    CredentialLifecycleState.ROTATION_REQUIRED,
    CredentialLifecycleState.ROTATED_IN_SIMULATION,
    CredentialLifecycleState.SUSPENDED,
    CredentialLifecycleState.REVOKED,
    CredentialLifecycleState.DESTROYED,
    CredentialLifecycleState.ARCHIVED,
]

# Terminal / fail-closed lifecycle states (no further activation).
TERMINAL_LIFECYCLE = frozenset({
    CredentialLifecycleState.EXPIRED,
    CredentialLifecycleState.REVOKED,
    CredentialLifecycleState.DESTROYED,
    CredentialLifecycleState.ARCHIVED,
    CredentialLifecycleState.SUSPENDED,
})

PROHIBITED_SECRET_KEYS = frozenset({
    "api_key", "api_secret", "secret", "password", "private_key", "access_token",
    "refresh_token", "bearer", "client_secret", "oauth_token", "session_key",
    "signing_key", "passphrase", "seed", "mnemonic", "credential", "token",
    "cookie", "recovery_code", "authorization", "raw_authorization_header",
    "seed_phrase", "pem", "jwt",
})

# Patterns that indicate secret-shaped values (aggressive detection).
SECRET_VALUE_PATTERNS = [
    r"(?i)^bearer\s+\S+",
    r"(?i)^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",  # JWT
    r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
    r"(?i)^sk[-_][A-Za-z0-9]{16,}",
    r"(?i)^pk[-_][A-Za-z0-9]{16,}",
    r"(?i)^AKIA[0-9A-Z]{16}",
    r"(?i)^xox[baprs]-[0-9A-Za-z-]{10,}",
    r"^[0-9a-fA-F]{32,}$",  # hex secret
    r"^[A-Za-z0-9+/]{40,}={0,2}$",  # base64 secret
    r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*\S+",
    r"(?i)^(binance|alpaca|ibkr|zerodha|bybit|coinbase|kraken)[_-]?[A-Za-z0-9]{16,}",
]

FORBIDDEN_PROVIDER_DOMAINS = frozenset({
    "binance.com", "api.binance.com", "alpaca.markets", "api.alpaca.markets",
    "interactivebrokers.com", "api.ibkr.com", "kite.zerodha.com", "api.kite.trade",
    "bybit.com", "api.bybit.com", "coinbase.com", "api.coinbase.com",
    "kraken.com", "api.kraken.com", "api.exchange.coinbase.com",
})

LLM_BOUNDARY = {
    "llm_may_explain_adapter_contracts": True,
    "llm_may_summarize_scope_differences": True,
    "llm_may_identify_excessive_permissions": True,
    "llm_may_explain_reconciliation": True,
    "llm_may_recommend_revocation": True,
    "llm_may_recommend_investigation": True,
    "llm_may_draft_incident_reports": True,
    "llm_may_compare_provider_capabilities": True,
    "llm_may_generate_simulation_scenarios": True,
    # Forbidden
    "llm_may_accept_credentials": False,
    "llm_may_store_credentials": False,
    "llm_may_approve_credentials": False,
    "llm_may_approve_providers": False,
    "llm_may_activate_sessions": False,
    "llm_may_restore_revoked_access": False,
    "llm_may_change_scopes": False,
    "llm_may_connect_brokers": False,
    "llm_may_access_account_data": False,
    "llm_may_submit_orders": False,
    "llm_may_cancel_orders": False,
    "llm_may_modify_portfolios": False,
    "llm_may_authorize_live_trading": False,
    "llm_may_certify_owner_approval": False,
    "llm_may_override_reconciliation": False,
    "llm_may_override_security_failures": False,
}

READINESS_POSTURE = {
    "paper_only": True,
    "sandbox_only": True,
    "simulation_only": True,
    "no_real_connection": True,
    "no_real_credential": True,
    "read_only_architecture": True,
    "no_order_submission": True,
    "live_trading_not_authorized": True,
    "live_trading_authorized": False,
    "real_broker_connection_capable": False,
    "credential_usable_for_real_connection": False,
    "production_read_only_authority": False,
    "funds_label": "SIMULATED",
    "connection_state_default": "SIMULATED_NOT_CONNECTED",
    "disclaimer": (
        "THE SYSTEM REMAINS PAPER AND SANDBOX ONLY. "
        "NO REAL BROKER CONNECTION WAS CREATED. "
        "NO REAL BROKER ACCOUNT WAS ACCESSED. "
        "NO REAL API CREDENTIALS WERE REQUESTED, ACCEPTED OR STORED. "
        "NO ORDER SUBMISSION OR ORDER CANCELLATION CAPABILITY EXISTS. "
        "LIVE TRADING IS NOT AUTHORIZED. "
        "READ-ONLY READINESS DOES NOT GRANT READ-ONLY PRODUCTION AUTHORITY."
    ),
}

# Synthetic providers for simulation (never real endpoints).
SIMULATED_PROVIDERS = [
    {
        "provider_id": "sim.readonly.fixture",
        "display_name": "Simulated Read-Only Fixture Provider",
        "description": "Deterministic fixture provider for readiness drills.",
        "is_emulator": True,
        "connection_state": "SIMULATED_NOT_CONNECTED",
    },
    {
        "provider_id": "sim.catalog.placeholder",
        "display_name": "Catalog Placeholder (Not Connected)",
        "description": "Capability catalog entry. Never connects.",
        "is_emulator": False,
        "connection_state": "SIMULATED_NOT_CONNECTED",
    },
]

DRILL_SCENARIOS = [
    "credential_expiry_during_session",
    "credential_revocation_before_connection",
    "credential_revocation_during_session",
    "scope_reduction",
    "unexpected_scope_expansion",
    "owner_approval_withdrawal",
    "security_approval_withdrawal",
    "provider_account_suspension",
    "provider_outage",
    "provider_permission_mutation",
    "clock_skew",
    "stale_account_snapshot",
    "replayed_account_snapshot",
    "duplicate_transaction_history",
    "rate_limit_exhaustion",
    "malformed_balance",
    "impossible_negative_quantity",
    "unknown_asset",
    "partial_history",
    "provider_identity_mismatch",
    "audit_storage_failure",
    "reconciliation_failure",
    "kill_switch_activation",
]

THREAT_CATALOG = [
    "secret_leakage",
    "excessive_permissions",
    "credential_reuse",
    "expired_credentials",
    "unrevoked_credentials",
    "provider_impersonation",
    "confused_deputy",
    "scope_drift",
    "session_replay",
    "snapshot_replay",
    "audit_tampering",
    "malicious_fixture_data",
    "schema_confusion",
    "order_command_injection",
    "prompt_injection_provider_metadata",
    "unauthorized_environment_promotion",
    "approval_bypass",
    "llm_authority_escalation",
    "real_transport_activation",
    "dependency_compromise",
    "logging_secret_shaped_values",
]

__all__ = [
    "SCHEMA_VERSION",
    "ENGINE_VERSION",
    "TERMINAL_VERDICT",
    "LIVE_TRADING_AUTHORIZED",
    "LIVE_ORDER_CAPABLE",
    "REAL_BROKER_CONNECTION_CAPABLE",
    "REAL_CREDENTIAL_ACCEPTANCE",
    "ORDER_SUBMISSION_CAPABLE",
    "ORDER_CANCELLATION_CAPABLE",
    "PRODUCTION_READ_ONLY_AUTHORITY",
    "CREDENTIAL_USABLE_FOR_REAL_CONNECTION",
    "AuthorityClass",
    "PolicyDecision",
    "CredentialLifecycleState",
    "ConnectionState",
    "ScopeOutcome",
    "ReconciliationClass",
    "ADAPTER_OPERATIONS",
    "ALLOWED_ADAPTER_AUTHORITIES",
    "ALLOWED_SCOPES",
    "FORBIDDEN_SCOPES",
    "FORBIDDEN_PERMISSION_KEYWORDS",
    "CREDENTIAL_LIFECYCLE_ORDER",
    "TERMINAL_LIFECYCLE",
    "PROHIBITED_SECRET_KEYS",
    "SECRET_VALUE_PATTERNS",
    "FORBIDDEN_PROVIDER_DOMAINS",
    "LLM_BOUNDARY",
    "READINESS_POSTURE",
    "SIMULATED_PROVIDERS",
    "DRILL_SCENARIOS",
    "THREAT_CATALOG",
]
