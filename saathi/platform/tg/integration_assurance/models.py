"""M232–M239 Reproducibility, Supply-Chain Assurance and Authorization Planning.

PLANNING AND REPRODUCIBILITY ONLY.
NO REAL CONNECTIVITY. NO CREDENTIALS. NO ORDER CAPABILITY. LIVE TRADING NOT AUTHORIZED.
"""
from __future__ import annotations

from enum import Enum

SCHEMA_VERSION = "m232.integration_assurance.v1"
ENGINE_VERSION = "m232.integration_assurance.engine.v1"

TERMINAL_VERDICT = "REPRODUCIBILITY_SUPPLY_CHAIN_AUTHORIZATION_CERTIFIED_WITH_LIMITATIONS"

# Hard authority locks — never true in this milestone.
LIVE_TRADING_AUTHORIZED = False
REAL_CONNECTIVITY_AUTHORIZED = False
REAL_BROKER_CONNECTION_CAPABLE = False
REAL_CREDENTIAL_ACCEPTANCE = False
ORDER_SUBMISSION_CAPABLE = False
ORDER_CANCELLATION_CAPABLE = False
OWNER_SIGNOFF_AUTOMATED = False
CREDENTIAL_USABLE_FOR_REAL_CONNECTION = False

REAL_PROVIDER_TRANSPORT_FORBIDDEN = "REAL_PROVIDER_TRANSPORT_FORBIDDEN"

FORBIDDEN_PROVIDER_DOMAINS = frozenset({
    "api.binance.com", "binance.com", "fapi.binance.com",
    "api.alpaca.markets", "paper-api.alpaca.markets", "alpaca.markets",
    "api.ibkr.com", "interactivebrokers.com", "gdcdyn.interactivebrokers.com",
    "api.kite.trade", "kite.zerodha.com", "zerodha.com",
    "api.bybit.com", "bybit.com",
    "api.coinbase.com", "coinbase.com", "api.exchange.coinbase.com",
    "api.kraken.com", "kraken.com",
    "oauth.binance.com", "login.alpaca.markets",
})

FORBIDDEN_ENV_VARS = frozenset({
    "BINANCE_API_KEY", "BINANCE_API_SECRET", "BINANCE_SECRET",
    "ALPACA_API_KEY", "ALPACA_API_SECRET", "ALPACA_SECRET_KEY",
    "IBKR_USERNAME", "IBKR_PASSWORD", "IBKR_ACCOUNT",
    "ZERODHA_API_KEY", "ZERODHA_ACCESS_TOKEN", "KITE_API_KEY",
    "BYBIT_API_KEY", "BYBIT_API_SECRET",
    "COINBASE_API_KEY", "COINBASE_API_SECRET",
    "KRAKEN_API_KEY", "KRAKEN_API_SECRET",
    "BROKER_API_KEY", "BROKER_API_SECRET", "BROKER_TOKEN",
    "PROVIDER_API_KEY", "PROVIDER_SECRET", "PROVIDER_TOKEN",
    "OAUTH_CLIENT_SECRET", "TRADING_PASSWORD",
})

ALLOWED_PACKAGE_REGISTRIES = frozenset({
    "pypi.org", "files.pythonhosted.org",
    "registry.npmjs.org", "npmjs.org",
    "pypi.python.org",
})

SOURCE_CLASSIFICATIONS = frozenset({
    "COMMITTED_AND_REQUIRED",
    "COMMITTED_NOT_REQUIRED",
    "UNCOMMITTED_AND_REQUIRED",
    "UNCOMMITTED_NOT_REQUIRED",
    "GENERATED_REPRODUCIBLY",
    "GENERATED_NOT_REPRODUCIBLY",
    "STALE_LOCAL_ARTIFACT",
    "UNRESOLVED_DEPENDENCY",
})


class CleanCloneVerdict(str, Enum):
    CLEAN_CLONE_REPRODUCIBLE = "CLEAN_CLONE_REPRODUCIBLE"
    CLEAN_CLONE_REPRODUCIBLE_WITH_LIMITATIONS = "CLEAN_CLONE_REPRODUCIBLE_WITH_LIMITATIONS"
    CLEAN_CLONE_FAILED = "CLEAN_CLONE_FAILED"
    HIDDEN_LOCAL_DEPENDENCY_FOUND = "HIDDEN_LOCAL_DEPENDENCY_FOUND"


class AuthorizationState(str, Enum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    PLANNING_ONLY = "PLANNING_ONLY"
    EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
    AWAITING_OWNER_REVIEW = "AWAITING_OWNER_REVIEW"
    AWAITING_SECURITY_REVIEW = "AWAITING_SECURITY_REVIEW"
    AWAITING_LEGAL_REVIEW = "AWAITING_LEGAL_REVIEW"
    AWAITING_SCOPE_REVIEW = "AWAITING_SCOPE_REVIEW"
    READ_ONLY_CANARY_PLANNING_ELIGIBLE = "READ_ONLY_CANARY_PLANNING_ELIGIBLE"
    REAL_CONNECTIVITY_NOT_AUTHORIZED = "REAL_CONNECTIVITY_NOT_AUTHORIZED"
    AUTHORIZATION_EXPIRED = "AUTHORIZATION_EXPIRED"
    AUTHORIZATION_REVOKED = "AUTHORIZATION_REVOKED"
    FAIL_CLOSED = "FAIL_CLOSED"


# Maximum aggregate state available in M238
MAX_AUTH_STATE = AuthorizationState.READ_ONLY_CANARY_PLANNING_ELIGIBLE

APPROVAL_DOMAINS = (
    ("OWNER_AUTH", "Owner authorization"),
    ("SECURITY_AUTH", "Security authorization"),
    ("LEGAL_TOS", "Legal and terms-of-service review"),
    ("PROVIDER_ELIGIBILITY", "Provider eligibility review"),
    ("CREDENTIAL_SCOPE", "Credential-scope review"),
    ("DATA_RETENTION", "Data-retention review"),
    ("PRIVACY", "Privacy review"),
    ("INFRASTRUCTURE", "Infrastructure review"),
    ("NETWORK_ALLOWLIST", "Network allow-list approval"),
    ("INCIDENT_RESPONSE", "Incident-response readiness"),
    ("REVOCATION", "Revocation readiness"),
    ("RECONCILIATION", "Reconciliation readiness"),
    ("MONITORING", "Monitoring readiness"),
    ("ROLLBACK", "Rollback readiness"),
    ("READ_ONLY_CANARY", "Read-only canary approval"),
    ("POST_CANARY", "Post-canary review"),
)

IA_POSTURE = {
    "mode": "REPRODUCIBILITY_AND_PLANNING_ONLY",
    "paper_only": True,
    "sandbox_only": True,
    "real_connectivity_authorized": False,
    "live_trading_authorized": False,
    "order_submission_capable": False,
    "order_cancellation_capable": False,
    "credentials_accepted": False,
    "provider_account_access": False,
    "owner_signoff_automated": False,
    "disclaimer": (
        "REPRODUCIBILITY AND PLANNING ONLY. "
        "NO REAL CONNECTIVITY. NO CREDENTIALS. "
        "NO PROVIDER ACCOUNT ACCESS. NO ORDER CAPABILITY. "
        "LIVE TRADING NOT AUTHORIZED."
    ),
}

LLM_BOUNDARY = {
    "llm_may_explain_findings": True,
    "llm_may_summarize_risks": True,
    "llm_may_classify_findings": True,
    "llm_may_draft_remediation": True,
    "llm_may_explain_approvals": True,
    "llm_may_identify_missing_evidence": True,
    "llm_may_generate_threat_summaries": True,
    "llm_may_compare_clone_results": True,
    "llm_may_recommend_manual_review": True,
    "llm_may_modify_evidence": False,
    "llm_may_alter_hashes": False,
    "llm_may_approve_dependencies": False,
    "llm_may_approve_provider_access": False,
    "llm_may_provide_owner_signoff": False,
    "llm_may_approve_legal": False,
    "llm_may_approve_security": False,
    "llm_may_authorize_credentials": False,
    "llm_may_create_credentials": False,
    "llm_may_initiate_connectivity": False,
    "llm_may_bypass_network": False,
    "llm_may_certify_failed_clone": False,
    "llm_may_suppress_findings": False,
    "llm_may_authorize_live_trading": False,
}

BOUNDARY_LABELS = {
    "reproducibility_planning": "REPRODUCIBILITY AND PLANNING ONLY",
    "no_real_connectivity": "NO REAL CONNECTIVITY",
    "no_credentials": "NO CREDENTIALS",
    "no_provider_account": "NO PROVIDER ACCOUNT ACCESS",
    "no_order_capability": "NO ORDER CAPABILITY",
    "live_trading_not_authorized": "LIVE TRADING NOT AUTHORIZED",
}

TERMINAL_STATEMENTS = [
    "THE SYSTEM REMAINS PAPER AND SANDBOX ONLY.",
    "THE CERTIFIED RESULT IS REPRODUCIBLE FROM COMMITTED SOURCE.",
    "NO REQUIRED SOURCE FILE REMAINS UNCOMMITTED.",
    "NO REAL BROKER CONNECTION WAS CREATED.",
    "NO REAL BROKER ACCOUNT WAS ACCESSED.",
    "NO REAL CREDENTIALS WERE REQUESTED, ACCEPTED OR STORED.",
    "NO ORDER SUBMISSION OR ORDER CANCELLATION CAPABILITY EXISTS.",
    "LIVE TRADING IS NOT AUTHORIZED.",
    "READ-ONLY INTEGRATION AUTHORIZATION WAS NOT GRANTED.",
    "OWNER SIGN-OFF WAS NOT GENERATED OR CLAIMED BY AUTOMATION.",
    "M232–M239 PROVIDES REPRODUCIBILITY, ASSURANCE AND PLANNING ONLY.",
]

# Required source trees for M216–M231 certification
REQUIRED_SOURCE_TREES = (
    "saathi/platform/tg/broker_sandbox",
    "saathi/platform/tg/broker_readiness",
    "saathi/platform/tg/integration_assurance",
    "tests/test_m224_m231_broker_readiness.py",
    "tests/test_m216_m223_broker_sandbox.py",
)

LOCKFILES = (
    "saathi-os/package-lock.json",
    "requirements.txt",
    "pyproject.toml",
)

SUPPLY_CHAIN_THREATS = (
    "malicious_dependency_update",
    "compromised_package_registry",
    "typosquatted_dependency",
    "dependency_confusion",
    "compromised_maintainer",
    "malicious_install_script",
    "lockfile_tampering",
    "generated_file_tampering",
    "browser_binary_substitution",
    "git_hook_manipulation",
    "ci_action_compromise",
    "floating_github_action_tags",
    "compromised_build_cache",
    "local_path_injection",
    "environment_variable_injection",
    "dns_poisoning",
    "download_substitution",
    "checksum_bypass",
    "stale_vulnerable_dependency",
    "malicious_fixture",
    "malicious_documentation_command",
    "evidence_tampering",
    "sbom_tampering",
)
