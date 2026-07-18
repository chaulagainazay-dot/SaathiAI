"""M32 — Governed provider-adapter pilot.

Public surface for the bounded provider-adapter layer that sits ABOVE the M27
connector adapter boundary and composes with (never replaces) M25 production
certification, M30 connector certification, and M31 credential/account readiness.
"""
from saathi.connectors.providers.config import (
    ProviderConfig,
    RateLimitPolicy,
    RetryPolicy,
    TimeoutPolicy,
    validate_config,
)
from saathi.connectors.providers.contract import (
    ProviderAdapter,
    adapter_satisfies_contract,
    REQUIRED_CONTRACT_METHODS,
)
from saathi.connectors.providers.eligibility import resolve_execution_eligibility
from saathi.connectors.providers.models import (
    DataClassification,
    ExecutionMode,
    ProviderAdapterResult,
    ProviderErrorCode,
    ProviderExecutionContext,
    ProviderHealthState,
    ProviderIdentity,
    ProviderSideEffectClass,
    ProviderStatus,
    ProviderVerificationState,
    RetryCategory,
    provider_is_prohibited,
)
from saathi.connectors.providers.registry import (
    ProviderRegistry,
    ProviderRegistryError,
    get_provider_registry,
)
from saathi.connectors.providers.runtime import ProviderExecutionRuntime
from saathi.connectors.providers.verification import (
    ProviderVerificationStore,
    check_provider_drift,
    resolve_provider_verification,
    verify_provider,
)

__all__ = [
    "ProviderConfig",
    "TimeoutPolicy",
    "RetryPolicy",
    "RateLimitPolicy",
    "validate_config",
    "ProviderAdapter",
    "adapter_satisfies_contract",
    "REQUIRED_CONTRACT_METHODS",
    "ProviderIdentity",
    "ProviderExecutionContext",
    "ProviderAdapterResult",
    "ExecutionMode",
    "ProviderStatus",
    "ProviderErrorCode",
    "RetryCategory",
    "ProviderSideEffectClass",
    "DataClassification",
    "ProviderHealthState",
    "ProviderVerificationState",
    "provider_is_prohibited",
    "ProviderRegistry",
    "ProviderRegistryError",
    "get_provider_registry",
    "ProviderExecutionRuntime",
    "ProviderVerificationStore",
    "verify_provider",
    "resolve_provider_verification",
    "check_provider_drift",
    "resolve_execution_eligibility",
]
