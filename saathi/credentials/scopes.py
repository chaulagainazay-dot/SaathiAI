"""M31 — Scope governance and provider-neutral auth profiles.

Scope rules are declarative and fail-closed:
  * requested scopes must be a subset of a profile's allowed set;
  * no prohibited (trading/financial/etc.) scope may ever be requested or granted;
  * a provider may never grant a scope that was not requested (no expansion);
  * an operation is authorized only if the granted scopes cover the operation's
    required scopes.

No profile here authorizes a live provider; profiles are contracts, not clients.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from saathi.credentials.models import (
    AuthProfile,
    AuthProfileType,
    StorageBackendKind,
    is_prohibited_scope,
)


class ScopeError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass
class ScopeDecision:
    allowed: bool
    reason: str = "ok"
    prohibited: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    expanded: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "prohibited": list(self.prohibited),
            "unknown": list(self.unknown),
            "missing": list(self.missing),
            "expanded": list(self.expanded),
        }


# ── Provider-neutral auth-profile catalog ──────────────────────────────────
# These describe *shapes* of authentication, never a concrete live provider.

_PROFILES: dict[str, AuthProfile] = {
    "none": AuthProfile(profile_type=AuthProfileType.NONE.value),
    "api_key_reference": AuthProfile(
        profile_type=AuthProfileType.API_KEY.value,
        credential_fields=("api_key",),
        secret_fields=("api_key",),
        allowed_storage_backends=(
            StorageBackendKind.ENVIRONMENT_REFERENCE.value,
            StorageBackendKind.IN_MEMORY_TEST.value,
        ),
        expiration_behavior="fail_closed",
        environments=("test", "dev", "local"),
    ),
    "oauth2_pkce": AuthProfile(
        profile_type=AuthProfileType.OAUTH2_PKCE.value,
        credential_fields=("access_token", "refresh_token"),
        secret_fields=("access_token", "refresh_token"),
        allowed_storage_backends=(
            StorageBackendKind.IN_MEMORY_TEST.value,
            StorageBackendKind.ENCRYPTED_LOCAL_TEST.value,
        ),
        rotation_required=True,
        refresh_support=True,
        expiration_behavior="fail_closed",
        minimum_scopes=(),
        optional_scopes=(),
        prohibited_scopes=(
            "trade", "trading", "order:write", "withdraw", "transfer_funds",
            "payment", "wallet:withdraw",
        ),
        account_link_required=True,
        environments=("test", "dev", "local"),
    ),
    "bearer_reference": AuthProfile(
        profile_type=AuthProfileType.BEARER_TOKEN_REFERENCE.value,
        credential_fields=("bearer_token",),
        secret_fields=("bearer_token",),
        allowed_storage_backends=(
            StorageBackendKind.ENVIRONMENT_REFERENCE.value,
            StorageBackendKind.IN_MEMORY_TEST.value,
        ),
        expiration_behavior="fail_closed",
        environments=("test", "dev", "local"),
    ),
    "local_socket": AuthProfile(
        profile_type=AuthProfileType.LOCAL_SOCKET.value,
        environments=("test", "dev", "local"),
    ),
}


def get_profile(name: str) -> AuthProfile:
    prof = _PROFILES.get(name)
    if prof is None:
        raise ScopeError("unknown_auth_profile", name)
    return prof


def list_profiles() -> dict[str, dict[str, Any]]:
    return {k: v.to_dict() for k, v in sorted(_PROFILES.items())}


def register_profile(name: str, profile: AuthProfile, *, overwrite: bool = False) -> None:
    """Register a test/fixture profile. CUSTOM_PROHIBITED type is rejected."""
    if profile.profile_type == AuthProfileType.CUSTOM_PROHIBITED.value:
        raise ScopeError("custom_auth_profile_prohibited", name)
    if name in _PROFILES and not overwrite:
        raise ScopeError("auth_profile_exists", name)
    _PROFILES[name] = profile


# ── Governance checks ──────────────────────────────────────────────────────

def _allowed_universe(profile: AuthProfile, extra_allowed: tuple[str, ...]) -> set[str]:
    return set(profile.minimum_scopes) | set(profile.optional_scopes) | set(extra_allowed)


def validate_requested_scopes(
    requested: tuple[str, ...],
    *,
    profile: Optional[AuthProfile] = None,
    allowed_scopes: tuple[str, ...] = (),
) -> ScopeDecision:
    """Requested scopes must contain no prohibited scope and (if an allowed
    universe is declared) be a subset of it. Fail-closed."""
    prohibited = tuple(s for s in requested if is_prohibited_scope(s))
    if profile is not None:
        prohibited = tuple(sorted(set(prohibited) | {
            s for s in requested if s in set(profile.prohibited_scopes)
        }))
    if prohibited:
        return ScopeDecision(False, "prohibited_scope_requested", prohibited=prohibited)

    universe: set[str] = set(allowed_scopes)
    if profile is not None:
        universe |= _allowed_universe(profile, allowed_scopes)
    # An empty universe means "no explicit allowlist declared" → allow non-prohibited.
    if universe:
        unknown = tuple(sorted(s for s in requested if s not in universe))
        if unknown:
            return ScopeDecision(False, "scope_not_in_allowlist", unknown=unknown)

    if profile is not None and profile.minimum_scopes:
        missing = tuple(sorted(s for s in profile.minimum_scopes if s not in requested))
        if missing:
            return ScopeDecision(False, "minimum_scopes_missing", missing=missing)
    return ScopeDecision(True, "ok")


def validate_granted_scopes(
    requested: tuple[str, ...],
    granted: tuple[str, ...],
) -> ScopeDecision:
    """A provider may not grant a scope that was not requested (no expansion),
    and may not grant a prohibited scope. Narrowing is allowed."""
    prohibited = tuple(sorted(s for s in granted if is_prohibited_scope(s)))
    if prohibited:
        return ScopeDecision(False, "prohibited_scope_granted", prohibited=prohibited)
    expanded = tuple(sorted(s for s in granted if s not in set(requested)))
    if expanded:
        return ScopeDecision(False, "scope_expansion_blocked", expanded=expanded)
    return ScopeDecision(True, "ok")


def scopes_for_operation(profile: AuthProfile, operation: str) -> tuple[str, ...]:
    return tuple((profile.operation_scope_map or {}).get(operation, ()))


def check_operation_authorized(
    *,
    operation: str,
    granted_scopes: tuple[str, ...],
    profile: Optional[AuthProfile] = None,
    required_scopes: tuple[str, ...] = (),
) -> ScopeDecision:
    """Authorize an operation iff granted scopes cover the required set for it."""
    required: set[str] = set(required_scopes)
    if profile is not None:
        required |= set(scopes_for_operation(profile, operation))
    # Prohibited requirement can never be satisfied — fail closed.
    bad = tuple(sorted(s for s in required if is_prohibited_scope(s)))
    if bad:
        return ScopeDecision(False, "operation_requires_prohibited_scope", prohibited=bad)
    granted = set(granted_scopes)
    missing = tuple(sorted(s for s in required if s not in granted))
    if missing:
        return ScopeDecision(False, "insufficient_scope", missing=missing)
    return ScopeDecision(True, "ok")
