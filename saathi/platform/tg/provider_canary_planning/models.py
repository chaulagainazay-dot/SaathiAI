"""M240–M247 Provider Canary Planning — models and authority locks.

PLANNING ONLY. NO REAL CONNECTIVITY. NO CREDENTIALS. NO CANARY ACTIVATION.
LIVE TRADING NOT AUTHORIZED.
"""
from __future__ import annotations

from enum import Enum

SCHEMA_VERSION = "m240.provider_canary_planning.v1"
ENGINE_VERSION = "m240.provider_canary_planning.engine.v1"

TERMINAL_VERDICT = "PROVIDER_CANARY_PLANNING_CERTIFIED_WITH_LIMITATIONS"
MAX_PLANNING_STATE = "READ_ONLY_CANARY_PACKAGE_READY_FOR_OWNER_REVIEW"
CANARY_DESIGN_STATE = "CANARY_DESIGNED_NOT_AUTHORIZED"
CREDENTIAL_CEREMONY_STATUS = "CREDENTIAL_CEREMONY_DOCUMENTED_NOT_EXECUTED"

# Hard authority locks — never true in this milestone.
LIVE_TRADING_AUTHORIZED = False
REAL_CONNECTIVITY_AUTHORIZED = False
CREDENTIAL_PROVISIONING_AUTHORIZED = False
CANARY_ACTIVATION_AUTHORIZED = False
READ_ONLY_PRODUCTION_AUTHORIZED = False
REAL_BROKER_CONNECTION_CAPABLE = False
REAL_CREDENTIAL_ACCEPTANCE = False
ORDER_SUBMISSION_CAPABLE = False
ORDER_CANCELLATION_CAPABLE = False
OWNER_SIGNOFF_AUTOMATED = False
PROVIDER_ADAPTER_IMPLEMENTED = False
OAUTH_SESSION_CAPABLE = False

REAL_PROVIDER_TRANSPORT_FORBIDDEN = "REAL_PROVIDER_TRANSPORT_FORBIDDEN"

RETRIEVAL_DATE = "2026-07-30"

FORBIDDEN_PROVIDER_DOMAINS = frozenset({
    "api.binance.com", "binance.com", "fapi.binance.com", "dapi.binance.com",
    "api.alpaca.markets", "paper-api.alpaca.markets", "alpaca.markets", "data.alpaca.markets",
    "api.ibkr.com", "interactivebrokers.com", "gdcdyn.interactivebrokers.com",
    "api.kite.trade", "kite.zerodha.com", "zerodha.com", "kite.trade",
    "api.bybit.com", "bybit.com",
    "api.coinbase.com", "coinbase.com", "api.exchange.coinbase.com", "api.prime.coinbase.com",
    "api.kraken.com", "kraken.com", "futures.kraken.com",
    "oauth.binance.com", "login.alpaca.markets", "login.coinbase.com",
    "portal.cdp.coinbase.com", "api-pub.bitfinex.com",
})

FORBIDDEN_ENV_VARS = frozenset({
    "BINANCE_API_KEY", "BINANCE_API_SECRET", "BINANCE_SECRET",
    "ALPACA_API_KEY", "ALPACA_API_SECRET", "ALPACA_SECRET_KEY", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY",
    "IBKR_USERNAME", "IBKR_PASSWORD", "IBKR_ACCOUNT",
    "ZERODHA_API_KEY", "ZERODHA_ACCESS_TOKEN", "KITE_API_KEY", "KITE_ACCESS_TOKEN",
    "BYBIT_API_KEY", "BYBIT_API_SECRET",
    "COINBASE_API_KEY", "COINBASE_API_SECRET", "CDP_API_KEY", "CDP_API_SECRET",
    "KRAKEN_API_KEY", "KRAKEN_API_SECRET", "KRAKEN_PRIVATE_KEY",
    "BROKER_API_KEY", "BROKER_API_SECRET", "BROKER_TOKEN",
    "PROVIDER_API_KEY", "PROVIDER_SECRET", "PROVIDER_TOKEN",
    "OAUTH_CLIENT_SECRET", "TRADING_PASSWORD",
})

# Classification taxonomy (M240)
class CandidateClass(str, Enum):
    ELIGIBLE_CANDIDATE = "ELIGIBLE_CANDIDATE"
    CONDITIONALLY_ELIGIBLE = "CONDITIONALLY_ELIGIBLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    OWNER_ELIGIBILITY_UNCONFIRMED = "OWNER_ELIGIBILITY_UNCONFIRMED"
    LEGAL_REVIEW_REQUIRED = "LEGAL_REVIEW_REQUIRED"
    SECURITY_REVIEW_REQUIRED = "SECURITY_REVIEW_REQUIRED"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"
    DISQUALIFIED = "DISQUALIFIED"


class AuthCategory(str, Enum):
    PUBLIC_UNAUTHENTICATED = "PUBLIC_UNAUTHENTICATED"
    PRIVATE_READ_ONLY = "PRIVATE_READ_ONLY"
    TRADING_WRITE = "TRADING_WRITE"
    TRANSFER_WRITE = "TRANSFER_WRITE"
    WITHDRAWAL_WRITE = "WITHDRAWAL_WRITE"
    ACCOUNT_ADMIN = "ACCOUNT_ADMIN"
    CREDENTIAL_ADMIN = "CREDENTIAL_ADMIN"
    UNKNOWN = "UNKNOWN"
    FORBIDDEN = "FORBIDDEN"


class EligibilityItemClass(str, Enum):
    SUPPORTED_BY_OFFICIAL_SOURCE = "SUPPORTED_BY_OFFICIAL_SOURCE"
    OWNER_CONFIRMATION_REQUIRED = "OWNER_CONFIRMATION_REQUIRED"
    LEGAL_REVIEW_REQUIRED = "LEGAL_REVIEW_REQUIRED"
    SECURITY_REVIEW_REQUIRED = "SECURITY_REVIEW_REQUIRED"
    UNRESOLVED = "UNRESOLVED"
    BLOCKING = "BLOCKING"


class EligibilityResult(str, Enum):
    PLANNING_ELIGIBLE = "PLANNING_ELIGIBLE"
    ELIGIBILITY_UNCONFIRMED = "ELIGIBILITY_UNCONFIRMED"
    TERMS_REVIEW_INCOMPLETE = "TERMS_REVIEW_INCOMPLETE"
    BLOCKED_BY_PROVIDER_RESTRICTION = "BLOCKED_BY_PROVIDER_RESTRICTION"
    LEGAL_REVIEW_REQUIRED = "LEGAL_REVIEW_REQUIRED"


class OwnerDecisionOption(str, Enum):
    REJECT = "REJECT"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    APPROVE_PLANNING_PACKAGE_ONLY = "APPROVE_PLANNING_PACKAGE_ONLY"


CANDIDATE_PROVIDERS = (
    "alpaca",
    "kraken",
    "coinbase",
    "binance",
    "interactive_brokers",
    "zerodha",
    "bybit",
)

PREFERRED_PROVIDER = "alpaca"
FALLBACK_PROVIDER = "kraken"

PCP_POSTURE = {
    "mode": "PROVIDER_CANARY_PLANNING_ONLY",
    "paper_only": True,
    "sandbox_only": True,
    "planning_only": True,
    "real_connectivity_authorized": False,
    "credential_provisioning_authorized": False,
    "canary_activation_authorized": False,
    "read_only_production_authorized": False,
    "live_trading_authorized": False,
    "order_submission_capable": False,
    "order_cancellation_capable": False,
    "credentials_accepted": False,
    "provider_account_access": False,
    "oauth_session_capable": False,
    "provider_adapter_implemented": False,
    "owner_signoff_automated": False,
    "owner_signoff_generated_by_automation": False,
    "canary_state": CANARY_DESIGN_STATE,
    "credential_ceremony_status": CREDENTIAL_CEREMONY_STATUS,
    "max_planning_state": MAX_PLANNING_STATE,
    "disclaimer": (
        "PLANNING ONLY. NO REAL CONNECTIVITY. NO CREDENTIALS. "
        "NO ACCOUNT ACCESS. CANARY NOT AUTHORIZED. LIVE TRADING NOT AUTHORIZED. "
        "PREFERRED PROVIDER IS A RECOMMENDATION ONLY."
    ),
}

LLM_BOUNDARY = {
    "llm_may_research_official_docs": True,
    "llm_may_summarise_capabilities": True,
    "llm_may_compare_providers": True,
    "llm_may_identify_missing_evidence": True,
    "llm_may_recommend_preferred_provider": True,
    "llm_may_classify_endpoint_authority": True,
    "llm_may_draft_canary_plans": True,
    "llm_may_draft_runbooks": True,
    "llm_may_draft_monitoring_criteria": True,
    "llm_may_draft_abort_criteria": True,
    "llm_may_explain_residual_risks": True,
    "llm_may_assemble_owner_review_package": True,
    "llm_may_certify_owner_eligibility": False,
    "llm_may_provide_legal_approval": False,
    "llm_may_provide_owner_approval": False,
    "llm_may_provide_security_approval": False,
    "llm_may_create_credentials": False,
    "llm_may_receive_credentials": False,
    "llm_may_store_credentials": False,
    "llm_may_activate_canary": False,
    "llm_may_initiate_oauth": False,
    "llm_may_connect_provider": False,
    "llm_may_access_account_data": False,
    "llm_may_approve_scopes": False,
    "llm_may_override_blocking_findings": False,
    "llm_may_authorize_live_trading": False,
    "llm_may_generate_owner_signoff": False,
}

BOUNDARY_LABELS = {
    "planning_only": "PLANNING ONLY",
    "no_real_connectivity": "NO REAL CONNECTIVITY",
    "no_credentials": "NO CREDENTIALS",
    "no_account_access": "NO ACCOUNT ACCESS",
    "canary_not_authorized": "CANARY NOT AUTHORIZED",
    "live_trading_not_authorized": "LIVE TRADING NOT AUTHORIZED",
}

TERMINAL_STATEMENTS = [
    "THE SYSTEM REMAINS PAPER, SANDBOX AND PLANNING ONLY.",
    "NO REAL BROKER CONNECTION WAS CREATED.",
    "NO REAL BROKER ACCOUNT WAS ACCESSED.",
    "NO REAL API CREDENTIALS WERE REQUESTED, ACCEPTED OR STORED.",
    "NO OAUTH SESSION WAS CREATED.",
    "NO PROVIDER-SPECIFIC RUNTIME ADAPTER WAS ACTIVATED.",
    "NO CANARY WAS ACTIVATED.",
    "NO ORDER SUBMISSION OR ORDER CANCELLATION CAPABILITY EXISTS.",
    "LIVE TRADING IS NOT AUTHORIZED.",
    "THE PREFERRED PROVIDER IS A RECOMMENDATION ONLY.",
    "OWNER ELIGIBILITY IS NOT CLAIMED WITHOUT EXPLICIT VERIFIED EVIDENCE.",
    "OWNER SIGN-OFF WAS NOT GENERATED OR CLAIMED BY AUTOMATION.",
    "THE PACKAGE IS READY FOR HUMAN OWNER REVIEW ONLY.",
]

AUTHORITY_VALUES = {
    "REAL_CONNECTIVITY_AUTHORIZED": False,
    "CREDENTIAL_PROVISIONING_AUTHORIZED": False,
    "CANARY_ACTIVATION_AUTHORIZED": False,
    "READ_ONLY_PRODUCTION_AUTHORIZED": False,
    "LIVE_TRADING_AUTHORIZED": False,
}

THREATS = (
    "incorrect_provider_selection",
    "outdated_provider_documentation",
    "false_eligibility_assumption",
    "excessive_credential_scope",
    "mixed_read_write_permission",
    "oauth_scope_escalation",
    "credential_leakage",
    "provider_impersonation",
    "dns_redirection",
    "malicious_sdk",
    "dependency_compromise",
    "undocumented_endpoint_behaviour",
    "rate_limit_lockout",
    "incomplete_history",
    "timestamp_drift",
    "pagination_omission",
    "account_mismatch",
    "data_retention_violation",
    "terms_of_service_violation",
    "malicious_provider_metadata",
    "prompt_injection_through_documentation",
    "approval_forgery",
    "owner_signoff_fabrication",
    "canary_auto_activation",
    "abort_trigger_suppression",
    "revocation_failure",
    "evidence_tampering",
    "hidden_connectivity_path",
    "trading_guardian_authority_escalation",
)

SCORE_DIMENSIONS = (
    "eligibility",
    "security",
    "api_quality",
    "operational_suitability",
    "commercial_product_fit",
)
