"""M240–M247 Provider Selection, Read-Only Canary Design and Human Authorization Package.

PLANNING ONLY.
NO REAL CONNECTIVITY. NO CREDENTIALS. NO ACCOUNT ACCESS.
CANARY NOT AUTHORIZED. LIVE TRADING NOT AUTHORIZED.
"""
from saathi.platform.tg.provider_canary_planning.models import (
    SCHEMA_VERSION,
    ENGINE_VERSION,
    TERMINAL_VERDICT,
    LIVE_TRADING_AUTHORIZED,
    REAL_CONNECTIVITY_AUTHORIZED,
    CREDENTIAL_PROVISIONING_AUTHORIZED,
    CANARY_ACTIVATION_AUTHORIZED,
    REAL_PROVIDER_TRANSPORT_FORBIDDEN,
    PREFERRED_PROVIDER,
    FALLBACK_PROVIDER,
    PCP_POSTURE,
    LLM_BOUNDARY,
)
from saathi.platform.tg.provider_canary_planning.service import (
    ProviderCanaryPlanningService,
    ProviderCanaryPlanningError,
    default_provider_canary_planning,
    reset_provider_canary_planning_for_tests,
)

__all__ = [
    "SCHEMA_VERSION",
    "ENGINE_VERSION",
    "TERMINAL_VERDICT",
    "LIVE_TRADING_AUTHORIZED",
    "REAL_CONNECTIVITY_AUTHORIZED",
    "CREDENTIAL_PROVISIONING_AUTHORIZED",
    "CANARY_ACTIVATION_AUTHORIZED",
    "REAL_PROVIDER_TRANSPORT_FORBIDDEN",
    "PREFERRED_PROVIDER",
    "FALLBACK_PROVIDER",
    "PCP_POSTURE",
    "LLM_BOUNDARY",
    "ProviderCanaryPlanningService",
    "ProviderCanaryPlanningError",
    "default_provider_canary_planning",
    "reset_provider_canary_planning_for_tests",
]
