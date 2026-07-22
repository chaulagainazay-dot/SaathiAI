"""M31 — Credential reference model (metadata only; never secret values)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


SCHEMA_VERSION = "m31.credentials.v1"


class CredentialType(str, Enum):
    OAUTH_ACCESS = "oauth_access"
    OAUTH_REFRESH = "oauth_refresh"
    OAUTH_TOKEN_SET = "oauth_token_set"
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    CLIENT_CREDENTIAL = "client_credential"
    SESSION = "session"
    GENERIC = "generic"


class CredentialStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRING = "EXPIRING"
    EXPIRED = "EXPIRED"
    ROTATION_REQUIRED = "ROTATION_REQUIRED"
    QUARANTINED = "QUARANTINED"
    REVOKED = "REVOKED"
    DELETED = "DELETED"
    UNAVAILABLE = "UNAVAILABLE"


class RotationState(str, Enum):
    NONE = "NONE"
    REQUIRED = "REQUIRED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"


class RevocationState(str, Enum):
    NONE = "NONE"
    REVOKED = "REVOKED"
    DELETED = "DELETED"


class StorageBackendKind(str, Enum):
    IN_MEMORY_TEST = "in_memory_test"
    ENCRYPTED_LOCAL_TEST = "encrypted_local_test"
    ENVIRONMENT_REFERENCE = "environment_reference"
    UNAVAILABLE = "unavailable"
    # Future — not operator-approved for live in M31
    KEYCHAIN = "keychain"
    CLOUD_SECRET_MANAGER = "cloud_secret_manager"


class AuthProfileType(str, Enum):
    NONE = "NONE"
    API_KEY = "API_KEY"
    OAUTH2_AUTHORIZATION_CODE = "OAUTH2_AUTHORIZATION_CODE"
    OAUTH2_PKCE = "OAUTH2_PKCE"
    BEARER_TOKEN_REFERENCE = "BEARER_TOKEN_REFERENCE"
    LOCAL_SOCKET = "LOCAL_SOCKET"
    MUTUAL_TLS_REFERENCE = "MUTUAL_TLS_REFERENCE"
    CUSTOM_PROHIBITED = "CUSTOM_PROHIBITED"


class OAuthLifecycleState(str, Enum):
    UNLINKED = "UNLINKED"
    LINK_REQUESTED = "LINK_REQUESTED"
    AUTHORIZATION_PENDING = "AUTHORIZATION_PENDING"
    CALLBACK_RECEIVED = "CALLBACK_RECEIVED"
    TOKEN_EXCHANGE_PENDING = "TOKEN_EXCHANGE_PENDING"
    LINKED = "LINKED"
    REFRESH_REQUIRED = "REFRESH_REQUIRED"
    REFRESHING = "REFRESHING"
    EXPIRED = "EXPIRED"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    REVOKING = "REVOKING"
    REVOKED = "REVOKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AccountLinkStatus(str, Enum):
    UNLINKED = "UNLINKED"
    LINK_REQUESTED = "LINK_REQUESTED"
    AUTHORIZATION_PENDING = "AUTHORIZATION_PENDING"
    LINKED = "LINKED"
    EXPIRED = "EXPIRED"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    REVOKED = "REVOKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SCOPE_BLOCKED = "SCOPE_BLOCKED"


class AccountLinkReadiness(str, Enum):
    READY = "READY"
    UNLINKED = "UNLINKED"
    AUTHORIZATION_PENDING = "AUTHORIZATION_PENDING"
    SCOPE_BLOCKED = "SCOPE_BLOCKED"
    CREDENTIAL_EXPIRED = "CREDENTIAL_EXPIRED"
    CREDENTIAL_QUARANTINED = "CREDENTIAL_QUARANTINED"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    REVOKED = "REVOKED"


class LeaseStatus(str, Enum):
    ISSUED = "ISSUED"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    INVALID = "INVALID"


# Secret field names that must never appear in metadata / evidence
FORBIDDEN_SECRET_FIELD_NAMES = frozenset({
    "access_token", "refresh_token", "api_key", "password", "client_secret",
    "cookie", "authorization", "bearer", "private_key", "recovery_code",
    "id_token", "session_token", "bot_token", "authorization_code",
    "pkce_verifier", "code_verifier",
})

# Financial / trading provider or scope tokens — fail closed
PROHIBITED_PROVIDER_SUBSTRINGS = frozenset({
    "trade", "order", "broker", "exchange", "wallet", "withdraw", "transfer",
    "payment", "bank", "financial", "leverage", "margin", "futures", "binance",
    "stripe", "fonepay",
})

PROHIBITED_SCOPES = frozenset({
    "trade", "trading", "order:write", "withdraw", "withdrawal", "transfer_funds",
    "payment", "payments", "bank:write", "financial:execute", "leverage",
    "margin", "futures", "wallet:withdraw",
})


@dataclass
class CredentialReference:
    """Opaque non-secret credential reference — never holds secret values."""

    credential_ref_id: str
    credential_type: str = CredentialType.GENERIC.value
    provider_id: str = ""
    account_link_id: str = ""
    owner_scope: str = ""  # e.g. user:test or org:acme
    environment: str = "test"
    storage_backend: str = StorageBackendKind.IN_MEMORY_TEST.value
    secret_fields_present: tuple[str, ...] = ()  # field NAMES only
    scopes: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    expires_at: str = ""
    rotation_state: str = RotationState.NONE.value
    revocation_state: str = RevocationState.NONE.value
    status: str = CredentialStatus.ACTIVE.value
    metadata_safe: dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""
    # Internal backend key name (env var name / vault path) — not a secret value
    backend_locator: str = ""
    quarantine_reason: str = ""
    connector_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.secret_fields_present, list):
            self.secret_fields_present = tuple(self.secret_fields_present)
        if isinstance(self.scopes, list):
            self.scopes = tuple(self.scopes)
        if isinstance(self.connector_ids, list):
            self.connector_ids = tuple(self.connector_ids)
        # Strip any accidental secret-like keys from metadata
        if self.metadata_safe:
            self.metadata_safe = {
                k: v for k, v in self.metadata_safe.items()
                if str(k).lower() not in FORBIDDEN_SECRET_FIELD_NAMES
                and not any(x in str(k).lower() for x in ("secret", "token", "password", "cookie"))
            }

    def to_safe_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Double-check no secret-looking values
        for k in list(d.keys()):
            if str(k).lower() in FORBIDDEN_SECRET_FIELD_NAMES:
                d.pop(k, None)
        d["schema"] = SCHEMA_VERSION
        d["contains_secret_values"] = False
        return d

    def compute_fingerprint(self) -> str:
        material = {
            "id": self.credential_ref_id,
            "type": self.credential_type,
            "provider": self.provider_id,
            "owner": self.owner_scope,
            "backend": self.storage_backend,
            "fields": list(self.secret_fields_present),
            "scopes": list(self.scopes),
            "status": self.status,
        }
        return hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass
class SecretLease:
    lease_id: str
    credential_ref_id: str
    request_id: str
    connector_id: str
    operation: str
    actor: str
    purpose: str = "execution_injection"
    issued_at: float = 0.0
    expires_at: float = 0.0
    single_use: bool = True
    status: str = LeaseStatus.ISSUED.value
    request_fingerprint: str = ""
    allowed_fields: tuple[str, ...] = ()

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "credential_ref_id": self.credential_ref_id,
            "request_id": self.request_id,
            "connector_id": self.connector_id,
            "operation": self.operation,
            "actor": self.actor,
            "purpose": self.purpose,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "single_use": self.single_use,
            "status": self.status,
            "request_fingerprint": self.request_fingerprint,
            "allowed_fields": list(self.allowed_fields),
            "contains_secret_values": False,
        }


@dataclass
class AuthProfile:
    """Provider-neutral authentication profile declaration."""

    profile_type: str = AuthProfileType.NONE.value
    credential_fields: tuple[str, ...] = ()
    secret_fields: tuple[str, ...] = ()
    non_secret_fields: tuple[str, ...] = ()
    allowed_storage_backends: tuple[str, ...] = (
        StorageBackendKind.IN_MEMORY_TEST.value,
        StorageBackendKind.ENVIRONMENT_REFERENCE.value,
    )
    rotation_required: bool = False
    expiration_behavior: str = "fail_closed"
    refresh_support: bool = False
    minimum_scopes: tuple[str, ...] = ()
    optional_scopes: tuple[str, ...] = ()
    prohibited_scopes: tuple[str, ...] = ()
    operation_scope_map: dict[str, tuple[str, ...]] = field(default_factory=dict)
    account_link_required: bool = False
    environments: tuple[str, ...] = ("test", "dev", "local")
    evidence_policy: str = "redacted"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["operation_scope_map"] = {
            k: list(v) for k, v in (self.operation_scope_map or {}).items()
        }
        return d


def is_prohibited_provider(provider_id: str) -> bool:
    p = (provider_id or "").lower()
    return any(x in p for x in PROHIBITED_PROVIDER_SUBSTRINGS)


def is_prohibited_scope(scope: str) -> bool:
    s = (scope or "").lower()
    if s in PROHIBITED_SCOPES:
        return True
    return any(x in s for x in ("withdraw", "trade", "leverage", "margin", "futures", "payment"))
