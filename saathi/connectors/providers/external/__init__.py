"""M33 — Governed external read-only provider pilot.

Public surface for the bounded external-provider layer that sits ABOVE the M32
provider adapter and composes with (never replaces) M25 production certification,
M30 connector certification, and M32 provider (simulation) verification. Maximum
state: EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS. Rollout stays OFF; Trading
Guardian stays UNCHANGED / UNENGAGED.
"""
from saathi.connectors.providers.external.models import (
    EndpointClass,
    ExternalFailure,
    ExternalProfileError,
    ExternalProviderProfile,
    ExternalVerificationState,
    M33_ALLOWED_METHODS,
    M33_MAX_VERIFICATION,
    SchemaDrift,
    TermsReviewStatus,
    validate_external_profile,
)
from saathi.connectors.providers.external.profiles import (
    GITHUB_META,
    GITHUB_META_SCHEMA,
    is_external_candidate,
    list_external_profiles,
    resolve_external_profile,
    schema_for,
)
from saathi.connectors.providers.external.schema import (
    SchemaContract,
    SchemaField,
    validate_schema,
)
from saathi.connectors.providers.external.transport import ExternalTransport, TransportResult
from saathi.connectors.providers.external.verification import (
    ExternalVerificationStore,
    check_external_drift,
    compute_external_fingerprint,
    resolve_external_verification,
)
from saathi.connectors.providers.external.verify import (
    plan_external_verification,
    run_live_verification,
    run_offline_verification,
)

__all__ = [
    "EndpointClass",
    "ExternalFailure",
    "ExternalProfileError",
    "ExternalProviderProfile",
    "ExternalVerificationState",
    "M33_ALLOWED_METHODS",
    "M33_MAX_VERIFICATION",
    "SchemaDrift",
    "TermsReviewStatus",
    "validate_external_profile",
    "GITHUB_META",
    "GITHUB_META_SCHEMA",
    "resolve_external_profile",
    "schema_for",
    "list_external_profiles",
    "is_external_candidate",
    "SchemaContract",
    "SchemaField",
    "validate_schema",
    "ExternalTransport",
    "TransportResult",
    "ExternalVerificationStore",
    "compute_external_fingerprint",
    "resolve_external_verification",
    "check_external_drift",
    "run_offline_verification",
    "run_live_verification",
    "plan_external_verification",
]
