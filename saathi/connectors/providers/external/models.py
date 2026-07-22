"""M33 — External read-only provider model, taxonomies, and states.

An *external provider profile* is the canonical, secret-free description of one
real read-only endpoint. Runtime callers NEVER supply a URL, host, port, header,
auth, proxy, or TLS setting — every one of those resolves from the profile and is
validated fail-closed. The external path composes with (never replaces) M25
production certification, M30 connector certification, and the M32 provider
verification / simulation layer.

The maximum verification state M33 may claim is
``EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS``. Nothing here grants production,
write, account, CANARY, or ACTIVE authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from saathi.connectors.providers.models import (
    DataClassification,
    ProviderSideEffectClass,
    provider_is_prohibited,
)

M33_SCHEMA_VERSION = "m33.external_provider.v1"

# Methods M33 permits — read-only only.
M33_ALLOWED_METHODS = frozenset({"GET", "HEAD"})
M33_FORBIDDEN_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"})

# Live-call budget for external verification.
M33_DEFAULT_CALL_BUDGET = 1
M33_MAX_CALL_BUDGET = 3


# ── Endpoint classes ─────────────────────────────────────────────────────────
class EndpointClass(str, Enum):
    HTTPS_EXTERNAL = "https_external"   # real external HTTPS provider (M33)
    INPROCESS = "inprocess"             # M32 local simulator (unchanged)
    LOOPBACK = "loopback"              # M32 loopback tests (unchanged)


# ── External verification states (extends M32 provider verification) ─────────
class ExternalVerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    SIMULATION_VERIFIED = "SIMULATION_VERIFIED"
    EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS = "EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS"
    EXTERNAL_VERIFICATION_FAILED = "EXTERNAL_VERIFICATION_FAILED"
    EXTERNAL_VERIFICATION_STALE = "EXTERNAL_VERIFICATION_STALE"
    REVOKED = "REVOKED"


EXTERNAL_VERIFIED_STATES = frozenset({
    ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS,
})
# The single highest state M33 may ever claim.
M33_MAX_VERIFICATION = ExternalVerificationState.EXTERNAL_READ_ONLY_VERIFIED_WITH_LIMITATIONS


# ── Live-network failure taxonomy (bounded, redacted, provider-safe) ─────────
class ExternalFailure(str, Enum):
    DNS_RESOLUTION_FAILED = "DNS_RESOLUTION_FAILED"
    DNS_POLICY_BLOCKED = "DNS_POLICY_BLOCKED"
    SSRF_POLICY_BLOCKED = "SSRF_POLICY_BLOCKED"
    TLS_CERTIFICATE_FAILED = "TLS_CERTIFICATE_FAILED"
    TLS_HOSTNAME_FAILED = "TLS_HOSTNAME_FAILED"
    TLS_POLICY_BLOCKED = "TLS_POLICY_BLOCKED"
    REDIRECT_POLICY_BLOCKED = "REDIRECT_POLICY_BLOCKED"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    CONNECTION_REFUSED = "CONNECTION_REFUSED"
    CONNECTION_RESET = "CONNECTION_RESET"
    PROXY_POLICY_BLOCKED = "PROXY_POLICY_BLOCKED"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    DECOMPRESSION_LIMIT_EXCEEDED = "DECOMPRESSION_LIMIT_EXCEEDED"
    UNSUPPORTED_CONTENT_TYPE = "UNSUPPORTED_CONTENT_TYPE"
    MALFORMED_ENCODING = "MALFORMED_ENCODING"
    SCHEMA_INCOMPATIBLE = "SCHEMA_INCOMPATIBLE"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    ENDPOINT_POLICY_BLOCKED = "ENDPOINT_POLICY_BLOCKED"
    REQUEST_CONTRACT_VIOLATION = "REQUEST_CONTRACT_VIOLATION"
    EXTERNAL_VERIFICATION_ABORTED = "EXTERNAL_VERIFICATION_ABORTED"


# ── Schema drift classification ──────────────────────────────────────────────
class SchemaDrift(str, Enum):
    COMPATIBLE_ADDITIVE = "COMPATIBLE_ADDITIVE"
    COMPATIBLE_VALUE_CHANGE = "COMPATIBLE_VALUE_CHANGE"
    INCOMPATIBLE_MISSING_FIELD = "INCOMPATIBLE_MISSING_FIELD"
    INCOMPATIBLE_TYPE_CHANGE = "INCOMPATIBLE_TYPE_CHANGE"
    INCOMPATIBLE_ENUM_CHANGE = "INCOMPATIBLE_ENUM_CHANGE"
    UNKNOWN_SCHEMA_CHANGE = "UNKNOWN_SCHEMA_CHANGE"


COMPATIBLE_DRIFT = frozenset({
    SchemaDrift.COMPATIBLE_ADDITIVE, SchemaDrift.COMPATIBLE_VALUE_CHANGE,
})
INCOMPATIBLE_DRIFT = frozenset({
    SchemaDrift.INCOMPATIBLE_MISSING_FIELD, SchemaDrift.INCOMPATIBLE_TYPE_CHANGE,
    SchemaDrift.INCOMPATIBLE_ENUM_CHANGE, SchemaDrift.UNKNOWN_SCHEMA_CHANGE,
})


# ── Safe events + incident types ─────────────────────────────────────────────
EXTERNAL_PROVIDER_EVENTS = frozenset({
    "provider.external_review_started",
    "provider.external_candidate_rejected",
    "provider.external_selected",
    "provider.external_verification_started",
    "provider.external_verification_succeeded",
    "provider.external_verification_failed",
    "provider.external_verification_stale",
    "provider.endpoint_blocked",
    "provider.dns_blocked",
    "provider.tls_failed",
    "provider.redirect_blocked",
    "provider.schema_drift_detected",
    "provider.external_rate_limited",
    "provider.external_quarantined",
})

EXTERNAL_PROVIDER_INCIDENTS = frozenset({
    "external_provider_ssrf_attempt",
    "external_provider_tls_policy_violation",
    "external_provider_redirect_violation",
    "external_provider_schema_break",
    "external_provider_secret_exposure",
    "external_provider_response_oversized",
    "external_provider_unapproved_write",
    "external_provider_terms_uncertain",
    "external_provider_identity_mismatch",
    "external_provider_fixture_leak",
})


# ── Terms review status ──────────────────────────────────────────────────────
class TermsReviewStatus(str, Enum):
    REVIEWED_ACCEPTABLE = "REVIEWED_ACCEPTABLE"
    UNREVIEWED = "UNREVIEWED"
    UNCERTAIN = "UNCERTAIN"
    REJECTED = "REJECTED"


# Only this status is admissible; anything else fails closed.
ADMISSIBLE_TERMS = frozenset({TermsReviewStatus.REVIEWED_ACCEPTABLE})


@dataclass
class ExternalProviderProfile:
    """Canonical, secret-free external provider description. Endpoint is fixed here."""

    provider_id: str
    provider_display_name: str
    provider_owner: str
    official_documentation_reference: str
    environment: str                    # sandbox|dev|test (production disabled)
    endpoint_reference: str             # canonical HTTPS URL — never caller-supplied
    endpoint_class: str = EndpointClass.HTTPS_EXTERNAL.value
    hostname_allowlist: tuple[str, ...] = ()
    allowed_ports: tuple[int, ...] = (443,)
    auth_profile: str = "none"
    operation: str = "get_meta"
    method: str = "GET"
    canonical_path: str = "/"
    operation_set: tuple[str, ...] = ()
    side_effect_class: str = ProviderSideEffectClass.READ_ONLY.value
    data_classification: str = DataClassification.PUBLIC.value
    rate_limit_profile: str = "conservative"
    schema_version: str = "v1"
    adapter_version: str = "1.0.0"
    verification_mode: str = "SHADOW"
    network_required: bool = True
    terms_review_status: str = TermsReviewStatus.REVIEWED_ACCEPTABLE.value
    redirect_limit: int = 0
    response_limit_bytes: int = 256 * 1024
    deadline_seconds: float = 5.0
    connector_id: str = "gov.http"

    def __post_init__(self) -> None:
        if isinstance(self.hostname_allowlist, list):
            self.hostname_allowlist = tuple(self.hostname_allowlist)
        if isinstance(self.allowed_ports, list):
            self.allowed_ports = tuple(self.allowed_ports)
        if isinstance(self.operation_set, list):
            self.operation_set = tuple(self.operation_set)
        if not self.operation_set:
            self.operation_set = (self.operation,)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExternalProfileError(ValueError):
    """Raised when an external provider profile fails closed."""


def validate_external_profile(profile: ExternalProviderProfile) -> None:
    """Fail closed on any unsafe external profile. Raises ExternalProfileError."""
    reason = provider_is_prohibited(profile.provider_id, capabilities=profile.operation_set)
    if reason:
        raise ExternalProfileError(f"prohibited_provider:{reason}")

    env = (profile.environment or "").strip().lower()
    if env in ("production", "prod", "live"):
        raise ExternalProfileError(f"environment_disabled:{env}")
    if env not in ("sandbox", "dev", "test", "local"):
        raise ExternalProfileError(f"unknown_environment:{env}")

    # method ceiling — read-only only
    m = (profile.method or "").strip().upper()
    if m not in M33_ALLOWED_METHODS:
        raise ExternalProfileError(f"method_not_read_only:{m or 'none'}")

    # side-effect ceiling
    try:
        sec = ProviderSideEffectClass(profile.side_effect_class)
    except ValueError:
        raise ExternalProfileError(f"unknown_side_effect_class:{profile.side_effect_class}")
    if sec not in (ProviderSideEffectClass.NONE, ProviderSideEffectClass.READ_ONLY):
        raise ExternalProfileError(f"side_effect_not_permitted:{sec.value}")

    # data classification ceiling
    try:
        dc = DataClassification(profile.data_classification)
    except ValueError:
        raise ExternalProfileError(f"unknown_data_classification:{profile.data_classification}")
    if dc not in (DataClassification.PUBLIC, DataClassification.INTERNAL):
        raise ExternalProfileError(f"data_classification_not_permitted:{dc.value}")

    # auth must be credential-free for the pilot
    if (profile.auth_profile or "none").lower() not in ("none", "public", "sandbox_none"):
        raise ExternalProfileError(f"auth_profile_requires_secret:{profile.auth_profile}")

    # terms must be explicitly reviewed-acceptable — unknown/uncertain fails closed
    try:
        ts = TermsReviewStatus(profile.terms_review_status)
    except ValueError:
        raise ExternalProfileError(f"unknown_terms_status:{profile.terms_review_status}")
    if ts not in ADMISSIBLE_TERMS:
        raise ExternalProfileError(f"terms_not_acceptable:{ts.value}")

    if not profile.hostname_allowlist:
        raise ExternalProfileError("hostname_allowlist_required")

    # redirect ceiling for M33
    if int(profile.redirect_limit) > 2:
        raise ExternalProfileError(f"redirect_limit_too_high:{profile.redirect_limit}")
