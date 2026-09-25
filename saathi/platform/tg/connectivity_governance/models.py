"""M312–M319 Connectivity Governance — models and authority locks.

GOVERNANCE ONLY. NO PROVIDER CONNECTION. NO CREDENTIALS. NO OAUTH.
NO ACCOUNT ACCESS. NO ORDERS. NO CANARY ACTIVATION. NO LIVE TRADING.
"""
from __future__ import annotations

from enum import Enum

SCHEMA_VERSION = "m312.connectivity_governance.v1"
ENGINE_VERSION = "m312.connectivity_governance.engine.v1"
CHARTER_VERSION = "1.0.0"

TERMINAL_VERDICT = "TRADING_CONNECTIVITY_GOVERNANCE_CERTIFIED_WITH_LIMITATIONS"
MAX_STATE = "CONNECTIVITY_GOVERNANCE_READY_NO_PROVIDER_CONNECTION"
BROWSER_CERT_VERDICT = "TRADING_CONNECTIVITY_GOVERNANCE_BROWSER_CERT_PASSED_WITH_LIMITATIONS"
CURRENT_MATURITY = "GOVERNANCE_ONLY"

# Immutable authority locks — all false for this milestone
REAL_CONNECTIVITY_AUTHORIZED = False
BROKER_CONNECTIVITY_AUTHORIZED = False
CREDENTIAL_PROVISIONING_AUTHORIZED = False
CREDENTIAL_VALIDATION_AUTHORIZED = False
OAUTH_AUTHORIZED = False
ACCOUNT_ACCESS_AUTHORIZED = False
BALANCE_READ_AUTHORIZED = False
POSITION_READ_AUTHORIZED = False
CANARY_ACTIVATION_AUTHORIZED = False
READ_ONLY_PRODUCTION_AUTHORIZED = False
EXTERNAL_PAPER_EXECUTION_AUTHORIZED = False
ORDER_EXECUTION_AUTHORIZED = False
ORDER_SUBMISSION_AUTHORIZED = False
ORDER_MODIFICATION_AUTHORIZED = False
ORDER_CANCELLATION_AUTHORIZED = False
TRANSFER_AUTHORIZED = False
WITHDRAWAL_AUTHORIZED = False
LIVE_TRADING_AUTHORIZED = False
AUTOMATED_INVESTMENT_AUTHORITY = False
CREDENTIAL_STORAGE_AUTHORIZED = False
API_KEYS_ACCEPTED = False
PRODUCTION_AUTHORIZED = False

AUTHORITY_VALUES = {
    "REAL_CONNECTIVITY_AUTHORIZED": False,
    "BROKER_CONNECTIVITY_AUTHORIZED": False,
    "CREDENTIAL_PROVISIONING_AUTHORIZED": False,
    "CREDENTIAL_VALIDATION_AUTHORIZED": False,
    "OAUTH_AUTHORIZED": False,
    "ACCOUNT_ACCESS_AUTHORIZED": False,
    "BALANCE_READ_AUTHORIZED": False,
    "POSITION_READ_AUTHORIZED": False,
    "CANARY_ACTIVATION_AUTHORIZED": False,
    "READ_ONLY_PRODUCTION_AUTHORIZED": False,
    "EXTERNAL_PAPER_EXECUTION_AUTHORIZED": False,
    "ORDER_EXECUTION_AUTHORIZED": False,
    "ORDER_SUBMISSION_AUTHORIZED": False,
    "ORDER_MODIFICATION_AUTHORIZED": False,
    "ORDER_CANCELLATION_AUTHORIZED": False,
    "TRANSFER_AUTHORIZED": False,
    "WITHDRAWAL_AUTHORIZED": False,
    "LIVE_TRADING_AUTHORIZED": False,
    "AUTOMATED_INVESTMENT_AUTHORITY": False,
    "CREDENTIAL_STORAGE_AUTHORIZED": False,
    "API_KEYS_ACCEPTED": False,
    "PRODUCTION_AUTHORIZED": False,
    "paper_only": True,
    "sandbox_only": True,
    "research_only": True,
    "offline_first": True,
    "governance_only": True,
    "no_provider_connection": True,
    "no_broker_login": True,
    "no_oauth": True,
    "no_credential_storage": True,
    "no_orders": True,
    "no_account_access": True,
    "no_balance_access": True,
    "no_position_access": True,
    "no_canary_activation": True,
    "no_live_trading": True,
    "approval_does_not_equal_activation": True,
    "authority_does_not_implicitly_expand": True,
    "raw_credentials_forbidden": True,
    "max_state": MAX_STATE,
    "current_maturity": CURRENT_MATURITY,
}

TERMINAL_STATEMENTS = (
    "GOVERNANCE ONLY",
    "NO PROVIDER CONNECTION",
    "NO CREDENTIALS",
    "NO OAUTH",
    "NO ACCOUNT ACCESS",
    "NO ORDERS",
    "NO CANARY ACTIVATION",
    "NO LIVE TRADING",
    "APPROVAL DOES NOT EQUAL ACTIVATION",
    "HUMAN APPROVAL REQUIRED FOR AUTHORITY EXPANSION",
    "LLM HAS NO APPROVAL AUTHORITY",
)

CG_POSTURE = {
    "mode": "CONNECTIVITY_GOVERNANCE_ONLY",
    "provider_connected": False,
    "broker_login_available": False,
    "credentials_loaded": False,
    "oauth_available": False,
    "orders_enabled": False,
    "account_access": False,
    "canary_active": False,
    "emergency_shutdown": False,
    "maturity": CURRENT_MATURITY,
}

GOVERNANCE_PRINCIPLES = [
    "No connectivity by default",
    "All authority is explicit",
    "Authority is narrowly scoped",
    "Authority expires",
    "Authority is revocable",
    "Authority does not cascade automatically",
    "Read authority does not imply write authority",
    "Market-data access does not imply account access",
    "Account access does not imply order access",
    "Paper execution does not imply live execution",
    "Live execution cannot be granted in this milestone",
    "Credentials must never be pasted into chat or stored in evidence",
    "Provider capabilities must be allowlisted",
    "Unsupported capabilities must fail closed",
    "Human approval is required for every authority expansion",
    "Every decision must be auditable",
    "Emergency shutdown must dominate all other authority",
    "LLM recommendations are non-authoritative",
    "No model or agent may approve its own authority",
    "No milestone may silently inherit higher authority",
]

PROHIBITED_OPERATIONS = frozenset({
    "broker_login",
    "oauth",
    "real_api_key_accept",
    "credential_storage",
    "credential_validation",
    "account_access",
    "balance_read",
    "position_read",
    "order_submit",
    "order_modify",
    "order_cancel",
    "transfer",
    "withdrawal",
    "live_trading",
    "external_paper_execution",
    "canary_activation",
    "provider_connection",
    "authenticated_provider_call",
    "production_activation",
})

FORBIDDEN_SECRET_FIELDS = frozenset({
    "api_key", "api_secret", "secret_key", "private_key",
    "access_token", "refresh_token", "bearer_token",
    "password", "passphrase", "session_cookie",
    "recovery_code", "oauth_code", "broker_password",
    "client_secret", "signing_key",
})

LLM_BOUNDARY = {
    "may": [
        "explain_governance_policy",
        "draft_approval_requests",
        "summarize_provider_risks",
        "compare_capability_scopes",
        "identify_missing_controls",
        "prepare_incident_summaries",
        "recommend_revocation",
        "explain_authority_values",
        "prepare_human_review_materials",
    ],
    "may_not": [
        "approve_request",
        "activate_authority",
        "create_real_credential_reference",
        "inspect_real_credential",
        "connect_provider",
        "initiate_oauth",
        "access_account",
        "access_balances",
        "access_positions",
        "place_order",
        "activate_canary",
        "waive_governance_controls",
        "close_critical_incident",
        "grant_live_authority",
    ],
    "authoritative": False,
}


class AuthorityState(str, Enum):
    DENIED = "DENIED"
    UNDEFINED = "UNDEFINED"
    POLICY_ELIGIBLE = "POLICY_ELIGIBLE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVED_NOT_ACTIVE = "APPROVED_NOT_ACTIVE"
    ACTIVE_BOUNDED = "ACTIVE_BOUNDED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    EMERGENCY_DISABLED = "EMERGENCY_DISABLED"
    PROHIBITED = "PROHIBITED"


class ProviderGovernanceState(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    DOCUMENTATION_REVIEWED = "DOCUMENTATION_REVIEWED"
    MOCK_ELIGIBLE = "MOCK_ELIGIBLE"
    READ_ONLY_CANARY_ELIGIBLE = "READ_ONLY_CANARY_ELIGIBLE"
    EXTERNAL_PAPER_CANARY_ELIGIBLE = "EXTERNAL_PAPER_CANARY_ELIGIBLE"
    PROHIBITED = "PROHIBITED"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class ApprovalState(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED_NOT_ACTIVE = "APPROVED_NOT_ACTIVE"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    EMERGENCY_REVOKED = "EMERGENCY_REVOKED"
    CONSUMED = "CONSUMED"
    SUPERSEDED = "SUPERSEDED"


class CredentialState(str, Enum):
    NO_CREDENTIAL = "NO_CREDENTIAL"
    REFERENCE_DECLARED = "REFERENCE_DECLARED"
    REFERENCE_UNVERIFIED = "REFERENCE_UNVERIFIED"
    REFERENCE_VERIFIED_NOT_ACTIVE = "REFERENCE_VERIFIED_NOT_ACTIVE"
    ACTIVE_BOUNDED = "ACTIVE_BOUNDED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    DESTROYED = "DESTROYED"
    COMPROMISED = "COMPROMISED"


class IncidentState(str, Enum):
    NONE = "NONE"
    DETECTED = "DETECTED"
    TRIAGED = "TRIAGED"
    CONTAINED = "CONTAINED"
    REVOKED = "REVOKED"
    RECOVERY_PENDING = "RECOVERY_PENDING"
    CLOSED_WITH_LIMITATIONS = "CLOSED_WITH_LIMITATIONS"
    CLOSED = "CLOSED"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    PROHIBITED = "PROHIBITED"


class MaturityLevel(str, Enum):
    GOVERNANCE_NOT_ESTABLISHED = "GOVERNANCE_NOT_ESTABLISHED"
    GOVERNANCE_ONLY = "GOVERNANCE_ONLY"
    MOCK_CONTRACT_ELIGIBLE = "MOCK_CONTRACT_ELIGIBLE"
    READ_ONLY_CANARY_ELIGIBLE = "READ_ONLY_CANARY_ELIGIBLE"
    EXTERNAL_PAPER_CANARY_ELIGIBLE = "EXTERNAL_PAPER_CANARY_ELIGIBLE"
    LIVE_EXECUTION_PROHIBITED = "LIVE_EXECUTION_PROHIBITED"


# Authority domains and capabilities
MARKET_DATA_CAPABILITIES = (
    "offline_fixture_access",
    "public_unauthenticated_data",
    "authenticated_market_data",
    "historical_refresh",
    "real_time_quote_stream",
)
ACCOUNT_READ_CAPABILITIES = (
    "account_metadata",
    "balances",
    "positions",
    "orders",
    "fills",
    "activity",
    "margin_state",
)
ACCOUNT_WRITE_CAPABILITIES = (
    "submit_order",
    "modify_order",
    "cancel_order",
    "transfer",
    "withdraw",
    "change_settings",
)
EXECUTION_CAPABILITIES = (
    "internal_simulation",
    "external_paper",
    "live_execution",
)
CREDENTIAL_CAPABILITIES = (
    "credential_reference_creation",
    "credential_validation",
    "credential_use",
    "credential_rotation",
    "credential_revocation",
)

ALL_CAPABILITIES = (
    MARKET_DATA_CAPABILITIES
    + ACCOUNT_READ_CAPABILITIES
    + ACCOUNT_WRITE_CAPABILITIES
    + EXECUTION_CAPABILITIES
    + CREDENTIAL_CAPABILITIES
)

# In this milestone, only offline fixture access is policy-eligible (observation); rest denied/prohibited
MILESTONE_ALLOWED_CAPABILITIES = frozenset({
    "offline_fixture_access",  # already certified via M304–M311; not provider connectivity
})

MILESTONE_PROHIBITED_CAPABILITIES = frozenset({
    "authenticated_market_data",
    "real_time_quote_stream",
    "balances",
    "positions",
    "orders",
    "fills",
    "activity",
    "margin_state",
    "submit_order",
    "modify_order",
    "cancel_order",
    "transfer",
    "withdraw",
    "change_settings",
    "external_paper",
    "live_execution",
    "credential_validation",
    "credential_use",
})

APPROVAL_CATEGORIES = (
    "provider_documentation_review",
    "mock_adapter_testing",
    "credentialless_contract_testing",
    "read_only_canary_request",
    "external_paper_canary_request",
    "incident_exception_request",
    "revocation_request",
    "emergency_shutdown_request",
)

# Max provider state in this milestone
MAX_PROVIDER_STATE = ProviderGovernanceState.MOCK_ELIGIBLE.value
MAX_CREDENTIAL_STATE = CredentialState.REFERENCE_DECLARED.value
MAX_APPROVAL_STATE = ApprovalState.APPROVED_NOT_ACTIVE.value  # never active

SYNTHETIC_REF_PREFIX = "secret-ref://synthetic/"
ALLOWED_SYNTHETIC_REF = "secret-ref://synthetic/not-active"
