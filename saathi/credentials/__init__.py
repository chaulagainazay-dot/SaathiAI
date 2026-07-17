"""M31 — Credential and account-linking control plane.

A governed, metadata-only credential control plane for the connector runtime.
Secret *values* live only in backends and are surfaced solely through bounded,
single-use leases at the narrow injection boundary. This package never stores,
logs, or serializes real credentials, and never performs a real OAuth flow or
links a live account — fake providers only.

Public surface (import from here, not submodules):

    models      — CredentialReference, SecretLease, AuthProfile, enums, guards
    backends    — SecretBackend contract + test/in-memory/env-ref/unavailable
    lease       — LeaseStore, request_fingerprint
    broker      — CredentialBroker (control plane), get_broker/reset_broker
    scopes      — auth-profile catalog + scope governance
    leakscan    — synthetic secret-leak detector
    oauth       — provider-neutral PKCE lifecycle
    account_links — AccountLinkRegistry
    injection   — SecretInjectionContext (narrow, scrub-guaranteed)
    eligibility — M31 connector credential eligibility (composable with M30)
    evidence    — leak-scanned, metadata-only evidence writer
"""
from __future__ import annotations

from saathi.credentials.models import (
    SCHEMA_VERSION,
    AccountLinkReadiness,
    AccountLinkStatus,
    AuthProfile,
    AuthProfileType,
    CredentialReference,
    CredentialStatus,
    CredentialType,
    LeaseStatus,
    OAuthLifecycleState,
    RevocationState,
    RotationState,
    SecretLease,
    StorageBackendKind,
    is_prohibited_provider,
    is_prohibited_scope,
)

__all__ = [
    "SCHEMA_VERSION",
    "AccountLinkReadiness",
    "AccountLinkStatus",
    "AuthProfile",
    "AuthProfileType",
    "CredentialReference",
    "CredentialStatus",
    "CredentialType",
    "LeaseStatus",
    "OAuthLifecycleState",
    "RevocationState",
    "RotationState",
    "SecretLease",
    "StorageBackendKind",
    "is_prohibited_provider",
    "is_prohibited_scope",
]
