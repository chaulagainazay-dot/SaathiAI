"""M33 — Canonical external provider profiles + schema contracts (fail closed).

The endpoint of every external provider lives here, not in runtime input. Unknown
profiles fail closed; prohibited (financial/trading/social/etc.) providers can
never resolve. Exactly one provider is registered for the M33 pilot: ``github_meta``.
"""
from __future__ import annotations

from typing import Optional

from saathi.connectors.providers.external.models import (
    EndpointClass,
    ExternalProfileError,
    ExternalProviderProfile,
    TermsReviewStatus,
    validate_external_profile,
)
from saathi.connectors.providers.external.schema import SchemaContract, SchemaField
from saathi.connectors.providers.models import (
    DataClassification,
    ProviderSideEffectClass,
    provider_is_prohibited,
)

GITHUB_META = ExternalProviderProfile(
    provider_id="github_meta",
    provider_display_name="GitHub Meta (public infrastructure metadata)",
    provider_owner="GitHub, Inc.",
    official_documentation_reference="https://docs.github.com/en/rest/meta/meta#get-github-meta-information",
    environment="sandbox",
    endpoint_reference="https://api.github.com/meta",
    endpoint_class=EndpointClass.HTTPS_EXTERNAL.value,
    hostname_allowlist=("api.github.com",),
    allowed_ports=(443,),
    auth_profile="none",
    operation="get_meta",
    method="GET",
    canonical_path="/meta",
    operation_set=("get_meta",),
    side_effect_class=ProviderSideEffectClass.READ_ONLY.value,
    data_classification=DataClassification.PUBLIC.value,
    rate_limit_profile="github_unauth",
    schema_version="v1",
    adapter_version="1.0.0",
    verification_mode="SHADOW",
    network_required=True,
    terms_review_status=TermsReviewStatus.REVIEWED_ACCEPTABLE.value,
    redirect_limit=0,
    response_limit_bytes=256 * 1024,
    deadline_seconds=5.0,
    connector_id="gov.http",
)

GITHUB_META_SCHEMA = SchemaContract(
    provider_id="github_meta",
    schema_version="v1",
    fields=(
        SchemaField("verifiable_password_authentication", "bool", required=True),
        SchemaField("hooks", "array<str>", required=True),
        SchemaField("pages", "array<str>", required=True),
        SchemaField("api", "array<str>", required=False),
        SchemaField("web", "array<str>", required=False),
        SchemaField("git", "array<str>", required=False),
        SchemaField("packages", "array<str>", required=False),
        SchemaField("importer", "array<str>", required=False),
        SchemaField("actions", "array<str>", required=False),
        SchemaField("dependabot", "array<str>", required=False),
        SchemaField("ssh_key_fingerprints", "object", required=False),
        SchemaField("ssh_keys", "array<str>", required=False),
        SchemaField("domains", "object", required=False),
    ),
)

_EXTERNAL_PROFILES: dict[str, ExternalProviderProfile] = {
    GITHUB_META.provider_id: GITHUB_META,
}

_SCHEMAS: dict[str, SchemaContract] = {
    GITHUB_META.provider_id: GITHUB_META_SCHEMA,
}


def resolve_external_profile(provider_id: str) -> ExternalProviderProfile:
    """Resolve a canonical external profile. Unknown/prohibited fail closed."""
    pid = (provider_id or "").strip().lower()
    if not pid:
        raise ExternalProfileError("empty_provider_id")
    reason = provider_is_prohibited(pid)
    if reason:
        raise ExternalProfileError(f"prohibited_provider:{reason}")
    profile = _EXTERNAL_PROFILES.get(pid)
    if profile is None:
        raise ExternalProfileError(f"unknown_external_provider:{pid}")
    validate_external_profile(profile)  # defense in depth on every resolve
    return profile


def schema_for(provider_id: str) -> SchemaContract:
    s = _SCHEMAS.get((provider_id or "").strip().lower())
    if s is None:
        raise ExternalProfileError(f"unknown_external_schema:{provider_id}")
    return s


def list_external_profiles() -> list[str]:
    return sorted(_EXTERNAL_PROFILES)


def is_external_candidate(provider_id: str) -> bool:
    try:
        resolve_external_profile(provider_id)
        return True
    except ExternalProfileError:
        return False
