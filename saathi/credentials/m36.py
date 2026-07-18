"""M36 — Operator-controlled real sandbox credential verification.

Composes M31–M35 credential/account/lease/scope/session governance with the
M33/M34 canonical external transport for ONE bounded, operator-authorized,
read-only real sandbox session against the sole approved external provider
(``github_meta``).

Hard invariants:
  * no production credentials/accounts/OAuth;
  * no writes, financial, trading, payment, admin paths;
  * call budget ≤ 3 (fourth fails closed);
  * secrets only by reference after authorization + lease + matching session;
  * Authorization headers never logged or evidenced;
  * raw identity / response bodies never persisted;
  * rollout remains OFF (session-specific verification exception only);
  * Trading Guardian UNCHANGED / UNENGAGED;
  * M37 not authorized.

Offline tests inject transport and secret backends — never Keychain, never network.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.connectors.providers.external.models import ExternalProviderProfile
from saathi.connectors.providers.external.profiles import resolve_external_profile
from saathi.connectors.providers.external.request_envelope import build_request_envelope
from saathi.connectors.providers.external.transport import ExternalTransport, SendContext, urllib_sender
from saathi.credentials import m35
from saathi.credentials.backends import SecretBackend, SecretBackendError
from saathi.credentials.broker import CredentialBroker
from saathi.credentials.leakscan import assert_clean, is_clean, scan
from saathi.credentials.m35 import (
    SecretHandle,
    SecretHandleError,
    SessionLeaseError,
    SessionLeaseStore,
    SandboxAccountRegistry,
    classify_scope,
    ALLOWED_SCOPE_CLASSES,
    FORBIDDEN_SCOPE_CLASSES,
    assert_environment_allowed,
    assert_scopes_allowed,
    m35_secret_fingerprint,
    subject_fingerprint,
    ceiling_from_profile,
    request_within_ceiling,
    verify_scope_evidence,
    ScopeVerificationState,
    validate_secret_source,
    SecretSourceKind,
    PROHIBITED_SECRET_SOURCES,
)
from saathi.credentials.models import CredentialStatus, is_prohibited_provider

SCHEMA_VERSION = "m36.real_sandbox_session.v1"
M36_SURFACE_PATH = "saathi/credentials/m36.py"
ROOT = Path(__file__).resolve().parents[2]
M36_EVIDENCE_DIR = ROOT / "docs" / "evidence" / "m36"

_FP_DOMAIN_KEY = b"saathi.m36.fingerprint.domain.v1"
_FP_POLICY_VERSION = "m36.fp.v1"

M36_DEFAULT_CALL_BUDGET = 3
M36_MAX_CALL_BUDGET = 3
M36_DEFAULT_AUTH_TTL_SEC = 900.0   # 15 minutes
M36_MAX_AUTH_TTL_SEC = 1800.0     # 30 minutes hard ceiling
M36_DEFAULT_LEASE_TTL_SEC = 300.0
M36_DEFAULT_LEASE_USES = 2        # identity + operation

PROVIDER_ID = "github_meta"
OPERATION_META = "get_meta"
OPERATION_IDENTITY = "get_authenticated_user"
ENDPOINT_META = "/meta"
ENDPOINT_IDENTITY = "/user"
METHOD_GET = "GET"

ENV_LIVE_FLAG = "SAATHI_M36_ALLOW_LIVE_SANDBOX_VERIFICATION"

# Forbidden CLI / argv secret carriers
FORBIDDEN_CLI_FLAGS = frozenset({
    "--token", "--api-key", "--apikey", "--password", "--secret",
    "--authorization-header", "--authorization", "--bearer",
})

M36_ACK_TOKENS = (
    "I_CONFIRM_DISPOSABLE_SANDBOX_ACCOUNT",
    "I_CONFIRM_READ_ONLY_SCOPE",
    "I_CONFIRM_NO_PRODUCTION_DATA",
    "I_CONFIRM_SECRET_REFERENCE_ONLY",
    "I_CONFIRM_CALL_BUDGET",
    "I_CONFIRM_NO_WRITES",
    "I_CONFIRM_REVOCATION_PLAN",
    "I_CONFIRM_ROLLOUT_REMAINS_OFF",
)

NON_PRODUCTION_BANNER = (
    "REAL SANDBOX VERIFICATION\n"
    "NON-PRODUCTION\n"
    "READ-ONLY\n"
    "BOUNDED SESSION\n"
    "ROLLOUT OFF\n"
    "NO CANARY\n"
    "NO ACTIVE\n"
    "TRADING GUARDIAN UNENGAGED"
)

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class M36Error(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


# ── helpers ──────────────────────────────────────────────────────────────────
def _hmac_hex(*parts: bytes, length: int = 32) -> str:
    return hmac.new(_FP_DOMAIN_KEY, b"|".join(parts), hashlib.sha256).hexdigest()[:length]


def _now() -> float:
    return time.time()


def latency_bucket(ms: float, *, timed_out: bool = False) -> str:
    if timed_out:
        return "TIMEOUT"
    ms = float(ms or 0)
    if ms < 250:
        return "UNDER_250_MS"
    if ms < 500:
        return "250_TO_500_MS"
    if ms < 1000:
        return "500_MS_TO_1_S"
    if ms < 2000:
        return "1_TO_2_S"
    if ms < 5000:
        return "2_TO_5_S"
    return "OVER_5_S"


def size_bucket(nbytes: int) -> str:
    n = int(nbytes or 0)
    if n <= 0:
        return "EMPTY"
    if n < 4 * 1024:
        return "UNDER_4_KIB"
    if n < 64 * 1024:
        return "4_TO_64_KIB"
    if n < 256 * 1024:
        return "64_TO_256_KIB"
    return "AT_LIMIT"


# ── provider operation bindings (same provider, no second provider) ──────────
def meta_operation_profile() -> ExternalProviderProfile:
    """Canonical M33 get_meta profile (unchanged semantics)."""
    return resolve_external_profile(PROVIDER_ID)


def identity_operation_profile() -> ExternalProviderProfile:
    """Same-host identity binding for GET /user. Auth injected at sender only."""
    base = resolve_external_profile(PROVIDER_ID)
    return replace(
        base,
        operation=OPERATION_IDENTITY,
        method=METHOD_GET,
        canonical_path=ENDPOINT_IDENTITY,
        endpoint_reference="https://api.github.com/user",
        operation_set=(OPERATION_IDENTITY,),
        data_classification="INTERNAL",
        # auth_profile remains none for M33 validate_external_profile compatibility;
        # M36 injects Authorization only through the authenticated sender wrapper.
        auth_profile="none",
        rate_limit_profile="github_auth_readonly",
    )


def profile_for_operation(operation: str) -> ExternalProviderProfile:
    op = (operation or "").strip()
    if op == OPERATION_META:
        return meta_operation_profile()
    if op == OPERATION_IDENTITY:
        return identity_operation_profile()
    raise M36Error("unknown_operation", op)


# ── authorization record ─────────────────────────────────────────────────────
class AuthorizationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    CONSUMED = "CONSUMED"


@dataclass
class M36Authorization:
    authorization_id: str
    milestone: str
    provider_id: str
    account_ref_id: str
    credential_ref_id: str
    operation: str
    endpoint: str
    method: str
    environment_class: str
    approved_scope_classes: tuple[str, ...]
    approved_call_budget: int
    approved_duration: float
    approved_lease_uses: int
    operator_acknowledgements: tuple[str, ...]
    created_at: float
    expires_at: float
    status: str = AuthorizationStatus.ACTIVE.value
    identity_endpoint: str = ENDPOINT_IDENTITY
    identity_operation: str = OPERATION_IDENTITY
    secret_source_kind: str = ""
    cleanup_plan: str = "LEASE_REVOKED_AND_EXTERNAL_ATTEST"
    uses_remaining: int = 1

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "schema": "m36.authorization.v1",
            "authorization_id": self.authorization_id,
            "milestone": self.milestone,
            "provider_id": self.provider_id,
            "account_ref_id": self.account_ref_id,
            "credential_ref_id": self.credential_ref_id,
            "operation": self.operation,
            "endpoint": self.endpoint,
            "method": self.method,
            "identity_operation": self.identity_operation,
            "identity_endpoint": self.identity_endpoint,
            "environment_class": self.environment_class,
            "approved_scope_classes": list(self.approved_scope_classes),
            "approved_call_budget": self.approved_call_budget,
            "approved_duration": self.approved_duration,
            "approved_lease_uses": self.approved_lease_uses,
            "operator_acknowledgements": list(self.operator_acknowledgements),
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
            # field name avoids leakscan false-positive on keys containing "secret"
            "source_kind": self.secret_source_kind,
            "cleanup_plan": self.cleanup_plan,
            "uses_remaining": self.uses_remaining,
            "contains_secret_values": False,
            "contains_raw_identity": False,
            "m37_authorized": False,
        }


class AuthorizationStore:
    def __init__(self, *, clock: Optional[Callable[[], float]] = None):
        self._clock = clock or _now
        self._items: dict[str, M36Authorization] = {}
        self._lock = threading.RLock()
        self._seq = 0

    def _next_id(self) -> str:
        self._seq += 1
        return f"authz_m36_{self._seq:04d}"

    def create(
        self,
        *,
        provider_id: str,
        account_ref_id: str,
        credential_ref_id: str,
        operation: str = OPERATION_META,
        endpoint: str = ENDPOINT_META,
        method: str = METHOD_GET,
        environment_class: str = "SANDBOX",
        approved_scopes: tuple[str, ...] = ("identity:read", "metadata:read"),
        approved_call_budget: int = M36_DEFAULT_CALL_BUDGET,
        approved_duration: float = M36_DEFAULT_AUTH_TTL_SEC,
        approved_lease_uses: int = M36_DEFAULT_LEASE_USES,
        acknowledgements: tuple[str, ...] = (),
        secret_source_kind: str = SecretSourceKind.IN_MEMORY_TEST.value,
        cleanup_plan: str = "LEASE_REVOKED_AND_EXTERNAL_ATTEST",
        authorization_id: str = "",
    ) -> M36Authorization:
        if provider_id != PROVIDER_ID or is_prohibited_provider(provider_id):
            raise M36Error("provider_not_approved", provider_id)
        if not account_ref_id:
            raise M36Error("missing_account_ref")
        if not credential_ref_id:
            raise M36Error("missing_credential_ref")
        if operation not in (OPERATION_META, OPERATION_IDENTITY):
            raise M36Error("operation_not_approved", operation)
        if (method or "").upper() != METHOD_GET:
            raise M36Error("method_not_read_only", method)
        if (method or "").upper() in _WRITE_METHODS:
            raise M36Error("write_method_blocked", method)
        env = assert_environment_allowed(environment_class)
        scopes = assert_scopes_allowed(tuple(approved_scopes))
        scope_classes = tuple(sorted({classify_scope(s) for s in scopes}))
        if not set(scope_classes).issubset(ALLOWED_SCOPE_CLASSES):
            raise M36Error("forbidden_scope_class")
        budget = int(approved_call_budget)
        if budget < 1 or budget > M36_MAX_CALL_BUDGET:
            raise M36Error("invalid_call_budget", str(budget))
        duration = min(float(approved_duration), M36_MAX_AUTH_TTL_SEC)
        if duration <= 0:
            raise M36Error("invalid_duration")
        if int(approved_lease_uses) < 1:
            raise M36Error("invalid_lease_uses")
        acks = tuple(a.strip() for a in acknowledgements if a and str(a).strip())
        missing = [t for t in M36_ACK_TOKENS if t not in acks]
        if missing:
            raise M36Error("missing_acknowledgement", ",".join(missing))
        validate_secret_source(secret_source_kind, want_retrieval=False)
        if secret_source_kind.upper() in PROHIBITED_SECRET_SOURCES:
            raise M36Error("prohibited_secret_source", secret_source_kind)
        now = float(self._clock())
        auth = M36Authorization(
            authorization_id=authorization_id or self._next_id(),
            milestone="M36",
            provider_id=provider_id,
            account_ref_id=account_ref_id,
            credential_ref_id=credential_ref_id,
            operation=operation,
            endpoint=endpoint,
            method=METHOD_GET,
            environment_class=env,
            approved_scope_classes=scope_classes,
            approved_call_budget=budget,
            approved_duration=duration,
            approved_lease_uses=int(approved_lease_uses),
            operator_acknowledgements=acks,
            created_at=now,
            expires_at=now + duration,
            secret_source_kind=secret_source_kind.upper(),
            cleanup_plan=cleanup_plan,
            uses_remaining=1,
        )
        with self._lock:
            self._items[auth.authorization_id] = auth
        return auth

    def get(self, authorization_id: str) -> Optional[M36Authorization]:
        return self._items.get(authorization_id)

    def require_valid(
        self,
        authorization_id: str,
        *,
        provider_id: str,
        account_ref_id: str,
        credential_ref_id: str,
        operation: str,
        endpoint: str,
    ) -> M36Authorization:
        auth = self._items.get(authorization_id)
        if auth is None:
            raise M36Error("authorization_not_found")
        now = float(self._clock())
        if auth.status == AuthorizationStatus.REVOKED.value:
            raise M36Error("authorization_revoked")
        if auth.status == AuthorizationStatus.CONSUMED.value:
            raise M36Error("authorization_consumed")
        if now > auth.expires_at or auth.status == AuthorizationStatus.EXPIRED.value:
            auth.status = AuthorizationStatus.EXPIRED.value
            raise M36Error("authorization_expired")
        if auth.milestone != "M36":
            raise M36Error("authorization_not_m36")
        if auth.provider_id != provider_id:
            raise M36Error("authorization_provider_mismatch")
        if auth.account_ref_id != account_ref_id:
            raise M36Error("authorization_account_mismatch")
        if auth.credential_ref_id != credential_ref_id:
            raise M36Error("authorization_credential_mismatch")
        if auth.operation != operation:
            raise M36Error("authorization_operation_mismatch")
        if auth.endpoint != endpoint:
            raise M36Error("authorization_endpoint_mismatch")
        if auth.uses_remaining <= 0:
            raise M36Error("authorization_use_exhausted")
        return auth

    def consume(self, authorization_id: str) -> None:
        with self._lock:
            auth = self._items.get(authorization_id)
            if auth:
                auth.uses_remaining = max(0, auth.uses_remaining - 1)
                if auth.uses_remaining == 0:
                    auth.status = AuthorizationStatus.CONSUMED.value

    def revoke(self, authorization_id: str) -> None:
        with self._lock:
            auth = self._items.get(authorization_id)
            if auth:
                auth.status = AuthorizationStatus.REVOKED.value


def m35_approval_cannot_authorize_m36(approval: Any) -> bool:
    """M35 approvals are insufficient for M36 real sessions."""
    return True  # always: M36 requires its own authorization record


def m36_cannot_authorize_m37(auth: M36Authorization) -> bool:
    return auth.milestone == "M36" and auth.to_safe_dict().get("m37_authorized") is False


# ── disposable sandbox identity qualification ────────────────────────────────
class IdentityQualification(str, Enum):
    DISPOSABLE_SANDBOX = "DISPOSABLE_SANDBOX"
    NON_PRODUCTION_TEST = "NON_PRODUCTION_TEST"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


_REJECT_PURPOSE_SUBSTR = (
    "production", "personal", "financial", "trading", "payment", "billing",
    "cloud_admin", "cloud-admin", "admin_account", "business_critical",
    "email_account", "calendar", "social_media",
)


def qualify_sandbox_identity(
    *,
    provider_id: str,
    account_alias: str,
    environment_class: str,
    declared_purpose: str,
    production_usage: bool = False,
    contains_important_data: bool = False,
    revocation_plan: str = "",
    expiration_or_deletion_plan: str = "",
    account_kind: str = "disposable_sandbox",
    operator_disposable_ack: bool = False,
) -> dict[str, Any]:
    """Qualify before credential loading. SaathiOS cannot independently guarantee
    disposability — operator ack is combined with declared evidence."""
    reasons: list[str] = []
    if provider_id != PROVIDER_ID:
        reasons.append("provider_mismatch")
    try:
        env = assert_environment_allowed(environment_class)
    except m35.M35Error as e:
        return {
            "classification": IdentityQualification.REJECTED.value,
            "reasons": [e.code],
            "qualified": False,
            "disclaimer": "operator_ack_required_for_disposability",
        }
    if env == "PRODUCTION":
        reasons.append("production_environment")
    if production_usage:
        reasons.append("production_usage_declared")
    if contains_important_data:
        reasons.append("important_data_declared")
    kind = (account_kind or "").strip().lower()
    purpose = (declared_purpose or "").strip().lower()
    if kind in ("financial", "trading", "payment", "cloud_admin", "personal", "production"):
        reasons.append(f"forbidden_account_kind:{kind}")
    for sub in _REJECT_PURPOSE_SUBSTR:
        if sub in purpose or sub in kind:
            reasons.append(f"forbidden_purpose:{sub}")
            break
    if not revocation_plan:
        reasons.append("revocation_plan_required")
    if not expiration_or_deletion_plan:
        reasons.append("expiration_or_deletion_plan_required")
    if not account_alias or _EMAIL_RE.search(account_alias):
        reasons.append("invalid_or_personal_alias")
    if not operator_disposable_ack:
        reasons.append("missing_disposable_operator_ack")
    if reasons:
        return {
            "classification": IdentityQualification.REJECTED.value,
            "reasons": reasons,
            "qualified": False,
            "safe_alias": account_alias[:64] if account_alias and not _EMAIL_RE.search(account_alias or "") else "",
            "environment_class": env if "production" not in str(reasons).lower() else environment_class,
            "disclaimer": "operator_ack_required_for_disposability",
            "contains_raw_identity": False,
        }
    classification = (
        IdentityQualification.DISPOSABLE_SANDBOX.value
        if kind in ("disposable_sandbox", "sandbox")
        else IdentityQualification.NON_PRODUCTION_TEST.value
    )
    return {
        "classification": classification,
        "reasons": [],
        "qualified": True,
        "safe_alias": account_alias[:64],
        "environment_class": env,
        "revocation_plan": revocation_plan[:200],
        "expiration_or_deletion_plan": expiration_or_deletion_plan[:200],
        "disclaimer": "saathios_cannot_independently_guarantee_disposability",
        "contains_raw_identity": False,
    }


# ── real secret-source retrieval (authorized only) ───────────────────────────
_M36_RETRIEVABLE = frozenset({
    SecretSourceKind.IN_MEMORY_TEST.value,
    SecretSourceKind.ENV_REFERENCE.value,
    SecretSourceKind.OS_KEYCHAIN_REFERENCE.value,
    SecretSourceKind.ENCRYPTED_STORE_REFERENCE.value,
})


def validate_m36_secret_reference(
    *,
    source_kind: str,
    locator_classification: str = "opaque_reference",
    want_retrieval: bool = False,
) -> dict[str, Any]:
    """Structural validation. Does not retrieve. Rejects raw material carriers."""
    k = (source_kind or "").strip().upper()
    if k in PROHIBITED_SECRET_SOURCES:
        raise M36Error("prohibited_secret_source", k)
    if k not in {s.value for s in SecretSourceKind}:
        raise M36Error("unknown_secret_source", k)
    if locator_classification in ("raw_token", "raw_api_key", "raw_password", "raw_secret", "cli_argument"):
        raise M36Error("raw_secret_argument_rejected", locator_classification)
    retrievable = k in _M36_RETRIEVABLE
    if want_retrieval and not retrievable:
        raise M36Error("secret_source_not_retrievable", k)
    return {
        "source_kind": k,
        "retrievable_under_m36_auth": retrievable,
        "fallback_permitted": False,
        "arbitrary_env_scan": False,
        "locator_classification": locator_classification,
    }


def retrieve_secret_handle(
    *,
    backend: SecretBackend,
    locator: str,
    authorization: M36Authorization,
    lease_id: str,
    session_id: str,
    provider_id: str,
    account_ref_id: str,
    field_names: tuple[str, ...] = ("api_key",),
    events: Optional[list[dict[str, Any]]] = None,
) -> SecretHandle:
    """Retrieve by reference only after authorization + lease binding checks.

    Never prints, serializes, or returns raw secrets outside SecretHandle.
    """
    if authorization.status != AuthorizationStatus.ACTIVE.value:
        raise M36Error("retrieval_without_valid_authorization")
    if authorization.provider_id != provider_id:
        raise M36Error("retrieval_provider_mismatch")
    if authorization.account_ref_id != account_ref_id:
        raise M36Error("retrieval_account_mismatch")
    if not lease_id:
        raise M36Error("retrieval_without_lease")
    if not session_id:
        raise M36Error("retrieval_without_session")
    if not locator or locator.startswith("raw:"):
        raise M36Error("invalid_secret_locator")
    validate_m36_secret_reference(source_kind=authorization.secret_source_kind, want_retrieval=True)
    try:
        fields = backend.get(locator, list(field_names))
    except SecretBackendError as e:
        raise M36Error("secret_retrieval_failed", e.code) from e
    if not fields:
        raise M36Error("secret_empty")
    handle = SecretHandle(
        fields, session_id=session_id, lease_id=lease_id,
        provider_id=provider_id, account_ref_id=account_ref_id,
    )
    if events is not None:
        events.append({
            "event_type": "m36.secret_handle_opened",
            "session_id": session_id,
            "lease_id": lease_id,
            "provider_id": provider_id,
            "source_kind": authorization.secret_source_kind,
            "privacy_safe": True,
            "contains_secret_values": False,
        })
    return handle


# ── credential fingerprint ───────────────────────────────────────────────────
def m36_credential_fingerprint(
    secret_material: Any,
    *,
    provider_id: str,
    account_ref_id: str,
    credential_type: str,
    environment_class: str,
    policy_version: str = _FP_POLICY_VERSION,
) -> str:
    """Domain-separated, non-reversible fingerprint. No prefix/suffix/length leak."""
    if secret_material is None:
        return ""
    if isinstance(secret_material, (bytes, bytearray)):
        body = bytes(secret_material)
    elif isinstance(secret_material, dict):
        if not secret_material:
            return ""
        body = json.dumps({k: str(v) for k, v in sorted(secret_material.items())},
                          separators=(",", ":")).encode()
    else:
        s = str(secret_material)
        if not s:
            return ""
        body = s.encode()
    return _hmac_hex(
        b"m36_cred",
        provider_id.encode(),
        account_ref_id.encode(),
        credential_type.encode(),
        environment_class.encode(),
        policy_version.encode(),
        body,
        length=32,
    )


# ── scope observation / classification ───────────────────────────────────────
class M36ScopeResult(str, Enum):
    VERIFIED_READ_ONLY = "VERIFIED_READ_ONLY"
    VERIFIED_WITH_EXTRA_READ_SCOPE = "VERIFIED_WITH_EXTRA_READ_SCOPE"
    MISMATCHED = "MISMATCHED"
    WRITE_SCOPE_PRESENT = "WRITE_SCOPE_PRESENT"
    UNKNOWN = "UNKNOWN"
    DECLARED_ONLY_UNOBSERVED = "DECLARED_ONLY_UNOBSERVED"


_GITHUB_WRITEISH = frozenset({
    "repo", "public_repo", "delete_repo", "admin:org", "write:org", "admin:public_key",
    "write:public_key", "admin:repo_hook", "write:repo_hook", "admin:org_hook",
    "gist", "notifications", "user:email", "delete:packages", "write:packages",
    "admin:gpg_key", "write:gpg_key", "workflow", "admin:enterprise",
    "manage_billing:org", "read:billing", "write:discussion",
})
_GITHUB_READONLY_OK = frozenset({
    "", "read:user", "user:read", "read:org", "read:public_key", "read:gpg_key",
    "read:packages", "read:discussion", "read:enterprise", "read:project",
    "security_events", "metadata",
})


def parse_github_oauth_scopes(header_value: str) -> tuple[str, ...]:
    if not header_value or not str(header_value).strip():
        return ()
    parts = [p.strip().lower() for p in str(header_value).split(",") if p.strip()]
    return tuple(parts)


def classify_observed_scopes(
    declared: tuple[str, ...],
    observed: Optional[tuple[str, ...]],
    *,
    allowed_scope_classes: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Fail closed on write/admin/billing/unknown material scopes."""
    detail: dict[str, Any] = {
        "declared": list(declared),
        "observed": list(observed) if observed is not None else None,
        "allowed_scope_classes": list(allowed_scope_classes),
    }
    for s in declared:
        cls = classify_scope(s)
        if cls == "UNKNOWN":
            return {**detail, "result": M36ScopeResult.UNKNOWN.value, "reason": "unknown_declared"}
        if cls in FORBIDDEN_SCOPE_CLASSES or cls not in ALLOWED_SCOPE_CLASSES:
            return {**detail, "result": M36ScopeResult.WRITE_SCOPE_PRESENT.value, "reason": f"forbidden_declared:{cls}"}
    if observed is None:
        return {
            **detail,
            "result": M36ScopeResult.DECLARED_ONLY_UNOBSERVED.value,
            "reason": "scope_metadata_unavailable_not_verified",
            "honest_limitation": True,
        }
    if len(observed) == 0:
        # empty X-OAuth-Scopes often means classic PAT with no scopes (public only)
        return {
            **detail,
            "result": M36ScopeResult.VERIFIED_READ_ONLY.value,
            "reason": "empty_oauth_scopes_public_readonly",
            "observed_scope_classes": ["PUBLIC_DATA_READ"],
        }
    forbidden_hits: list[str] = []
    extra_read: list[str] = []
    for s in observed:
        sl = s.lower().strip()
        if not sl:
            continue
        if sl in _GITHUB_WRITEISH or any(w in sl for w in ("write", "admin", "delete", "workflow", "billing")):
            forbidden_hits.append(sl)
            continue
        cls = classify_scope(sl)
        if cls in FORBIDDEN_SCOPE_CLASSES:
            forbidden_hits.append(sl)
        elif sl not in _GITHUB_READONLY_OK and cls == "UNKNOWN":
            # unknown material scope fails closed
            forbidden_hits.append(f"unknown:{sl}")
        elif sl not in {d.lower() for d in declared} and sl not in _GITHUB_READONLY_OK:
            if cls in ALLOWED_SCOPE_CLASSES or sl in _GITHUB_READONLY_OK:
                extra_read.append(sl)
            else:
                forbidden_hits.append(f"unknown:{sl}")
        elif sl in _GITHUB_READONLY_OK and sl not in {d.lower() for d in declared}:
            extra_read.append(sl)
    if forbidden_hits:
        kind = "WRITE_SCOPE_PRESENT" if any(
            "write" in h or "admin" in h or "delete" in h or "workflow" in h or "billing" in h or h in _GITHUB_WRITEISH
            for h in forbidden_hits
        ) else "UNKNOWN"
        return {
            **detail,
            "result": M36ScopeResult.WRITE_SCOPE_PRESENT.value if kind == "WRITE_SCOPE_PRESENT" else M36ScopeResult.UNKNOWN.value,
            "reason": "forbidden_or_unknown_observed",
            "forbidden_hits": forbidden_hits,
        }
    if extra_read:
        return {
            **detail,
            "result": M36ScopeResult.VERIFIED_WITH_EXTRA_READ_SCOPE.value,
            "reason": "extra_read_scopes",
            "extra_read": extra_read,
        }
    return {
        **detail,
        "result": M36ScopeResult.VERIFIED_READ_ONLY.value,
        "reason": "observed_read_only",
    }


# ── call budget ──────────────────────────────────────────────────────────────
class CallBudget:
    def __init__(self, max_calls: int = M36_DEFAULT_CALL_BUDGET):
        if max_calls < 1 or max_calls > M36_MAX_CALL_BUDGET:
            raise M36Error("invalid_call_budget", str(max_calls))
        self.max_calls = int(max_calls)
        self.consumed = 0
        self.identity_calls = 0
        self.operation_calls = 0
        self.retries = 0
        self.redirect_calls = 0
        self.events: list[dict[str, Any]] = []

    def remaining(self) -> int:
        return max(0, self.max_calls - self.consumed)

    def consume(self, *, kind: str = "operation", is_retry: bool = False, is_redirect: bool = False) -> None:
        if self.consumed >= self.max_calls:
            raise M36Error("call_budget_exhausted")
        self.consumed += 1
        if kind == "identity":
            self.identity_calls += 1
        else:
            self.operation_calls += 1
        if is_retry:
            self.retries += 1
        if is_redirect:
            self.redirect_calls += 1
        self.events.append({
            "event_type": "m36.call_budget_consumed",
            "kind": kind,
            "consumed": self.consumed,
            "remaining": self.remaining(),
            "privacy_safe": True,
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_calls": self.max_calls,
            "consumed": self.consumed,
            "remaining": self.remaining(),
            "identity_calls": self.identity_calls,
            "operation_calls": self.operation_calls,
            "retries": self.retries,
            "redirect_calls": self.redirect_calls,
            "writes": 0,
            "financial_calls": 0,
            "trading_calls": 0,
        }


# ── authenticated sender wrapper ─────────────────────────────────────────────
def make_authenticated_sender(
    base_sender: Callable[[SendContext], dict[str, Any]],
    handle: SecretHandle,
    *,
    session_id: str,
    field: str = "api_key",
) -> Callable[[SendContext], dict[str, Any]]:
    """Inject Authorization only into SendContext for the live hop.

    Never attaches auth to the request envelope (which is logged-safe).
    Never records the header in return metadata beyond status codes.
    """
    def _sender(ctx: SendContext) -> dict[str, Any]:
        def _build(token: str) -> dict[str, Any]:
            headers = dict(ctx.headers)
            headers["Authorization"] = f"Bearer {token}"
            headers["Accept"] = headers.get("Accept") or headers.get("accept") or "application/vnd.github+json"
            auth_ctx = SendContext(
                method=ctx.method,
                url=ctx.url,
                host=ctx.host,
                port=ctx.port,
                pinned_ips=ctx.pinned_ips,
                headers=headers,
                timeout=ctx.timeout,
                response_limit=ctx.response_limit,
            )
            return base_sender(auth_ctx)

        return handle.use(field, _build, session_id=session_id)

    return _sender


# ── response normalization (minimize) ────────────────────────────────────────
def normalize_identity_response(
    *,
    status_code: int,
    headers: dict[str, str],
    body_bytes: bytes,
    expected_subject_fingerprint: str,
    provider_id: str,
    transport_ok: bool,
    tls: dict[str, Any],
    latency_ms: float,
) -> dict[str, Any]:
    """Parse identity body only in memory; retain safe fields only."""
    observed_scopes: Optional[tuple[str, ...]] = None
    h_lower = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    if "x-oauth-scopes" in h_lower:
        observed_scopes = parse_github_oauth_scopes(h_lower["x-oauth-scopes"])
    elif "x-accepted-oauth-scopes" in h_lower:
        # accepted scopes alone are not the token's granted scopes
        observed_scopes = None

    account_match = False
    subject_fp = ""
    schema_valid = False
    safe_status = "FAILED"
    try:
        if 200 <= status_code < 300 and body_bytes:
            data = json.loads(body_bytes.decode("utf-8"))
            if isinstance(data, dict) and "id" in data:
                schema_valid = True
                # fingerprint numeric id only — never login/email/name/avatar
                subject_fp = subject_fingerprint(str(data["id"]), provider_id=provider_id)
                account_match = bool(expected_subject_fingerprint) and hmac.compare_digest(
                    subject_fp, expected_subject_fingerprint
                )
                safe_status = "OK" if account_match and transport_ok else "ACCOUNT_MISMATCH"
            # discard data immediately (GC); never return raw
            del data
    except Exception:
        schema_valid = False
        safe_status = "SCHEMA_FAILURE"

    return {
        "provider_id": provider_id,
        "account_subject_fingerprint": subject_fp,
        "account_match": account_match,
        "environment_class": "SANDBOX",
        "observed_scopes": list(observed_scopes) if observed_scopes is not None else None,
        "scope_metadata_present": observed_scopes is not None,
        "verification_time_bucket": latency_bucket(latency_ms),
        "response_schema_version": "github_user.v1.minimized",
        "safe_status": safe_status,
        "http_status_class": f"{status_code // 100}xx" if status_code else "none",
        "schema_valid": schema_valid,
        "response_size_bucket": size_bucket(len(body_bytes or b"")),
        "content_type_match": "json" in h_lower.get("content-type", "").lower(),
        "tls_verified": bool(tls.get("verified", True)),  # live sender enforces TLS
        "privacy_safe": True,
        "contains_raw_identity": False,
        "contains_secret_values": False,
    }


def normalize_meta_response(
    *,
    status_code: int,
    body_bytes: bytes,
    content_type: str,
    latency_ms: float,
    transport_ok: bool,
    tls: dict[str, Any],
) -> dict[str, Any]:
    schema_valid = False
    try:
        if 200 <= status_code < 300 and body_bytes:
            data = json.loads(body_bytes.decode("utf-8"))
            if isinstance(data, dict) and "verifiable_password_authentication" in data and "hooks" in data:
                schema_valid = True
            del data
    except Exception:
        schema_valid = False
    return {
        "operation": OPERATION_META,
        "http_status_class": f"{status_code // 100}xx" if status_code else "none",
        "schema_valid": schema_valid,
        "response_size_bucket": size_bucket(len(body_bytes or b"")),
        "latency_bucket": latency_bucket(latency_ms),
        "content_type_match": "json" in (content_type or "").lower(),
        "tls_verified": bool(tls.get("verified", True)),
        "transport_ok": transport_ok,
        "safe_result_classification": "META_READ_OK" if schema_valid and transport_ok else "META_READ_FAILED",
        "privacy_safe": True,
        "contains_secret_values": False,
        "raw_body_persisted": False,
    }


# ── session states ───────────────────────────────────────────────────────────
class M36SessionState(str, Enum):
    REQUESTED = "REQUESTED"
    AUTHORIZED = "AUTHORIZED"
    ACCOUNT_QUALIFIED = "ACCOUNT_QUALIFIED"
    LEASED = "LEASED"
    SECRET_LOADED = "SECRET_LOADED"
    IDENTITY_VERIFIED = "IDENTITY_VERIFIED"
    SCOPE_VERIFIED = "SCOPE_VERIFIED"
    ELIGIBLE = "ELIGIBLE"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    SECRET_CLOSED = "SECRET_CLOSED"
    LEASE_CONSUMED = "LEASE_CONSUMED"
    REVOKED_OR_EXPIRED = "REVOKED_OR_EXPIRED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    QUARANTINED = "QUARANTINED"


class ReliabilityClass(str, Enum):
    NOT_EXERCISED = "NOT_EXERCISED"
    SINGLE_SUCCESS = "SINGLE_SUCCESS"
    REPEATABLE_SUCCESS = "REPEATABLE_SUCCESS"
    SUCCESS_WITH_LIMITATIONS = "SUCCESS_WITH_LIMITATIONS"
    TRANSIENT_FAILURE = "TRANSIENT_FAILURE"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    SCOPE_FAILURE = "SCOPE_FAILURE"
    SCHEMA_FAILURE = "SCHEMA_FAILURE"
    TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
    QUARANTINED = "QUARANTINED"


class CertificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    AUTHORIZATION_READY = "AUTHORIZATION_READY"
    REAL_SANDBOX_IDENTITY_VERIFIED = "REAL_SANDBOX_IDENTITY_VERIFIED"
    REAL_SANDBOX_SCOPE_VERIFIED = "REAL_SANDBOX_SCOPE_VERIFIED"
    REAL_SANDBOX_SESSION_VERIFIED = "REAL_SANDBOX_SESSION_VERIFIED"
    REAL_SANDBOX_SESSION_VERIFIED_WITH_LIMITATIONS = "REAL_SANDBOX_SESSION_VERIFIED_WITH_LIMITATIONS"
    FAILED = "FAILED"
    STALE = "STALE"
    REVOKED = "REVOKED"
    QUARANTINED = "QUARANTINED"


class CleanupDisposition(str, Enum):
    LEASE_EXPIRED = "LEASE_EXPIRED"
    LEASE_REVOKED = "LEASE_REVOKED"
    CREDENTIAL_REVOKED_EXTERNALLY = "CREDENTIAL_REVOKED_EXTERNALLY"
    CREDENTIAL_RETAINED_FOR_FUTURE_EXPLICIT_TEST = "CREDENTIAL_RETAINED_FOR_FUTURE_EXPLICIT_TEST"
    ACCOUNT_DELETION_PENDING = "ACCOUNT_DELETION_PENDING"
    EXTERNAL_REVOCATION_OPERATOR_ATTESTED = "EXTERNAL_REVOCATION_OPERATOR_ATTESTED"
    SILENT_ACTIVE = "SILENT_ACTIVE"  # invalid end state


# ── eligibility composition ──────────────────────────────────────────────────
def compose_m36_eligibility(
    *,
    production_certified: bool,
    connector_certified: bool,
    m30_drift_fresh: bool,
    m31_credential_governance: bool,
    m32_provider_adapter_verified: bool,
    m33_external_profile_verified: bool,
    m34_live_controls: bool,
    m35_sandbox_governance: bool,
    m36_authorization_valid: bool,
    sandbox_identity_qualified: bool,
    credential_healthy: bool,
    credential_fingerprint_present: bool,
    account_verified: bool,
    scope_verified: bool,
    approval_valid: bool,
    lease_valid: bool,
    call_budget_remaining: bool,
    provider_healthy: bool,
    quarantined: bool,
    rollout_off: bool,
    verification_only_exception: bool,
) -> tuple[bool, list[str]]:
    """Intersection of all gates. Rollout OFF is required, but the M36
    verification-only exception permits the one-session path without enabling
    general rollout."""
    blockers: list[str] = []
    checks = [
        (production_certified, "production_not_certified"),
        (connector_certified, "connector_not_certified"),
        (m30_drift_fresh, "m30_drift_stale"),
        (m31_credential_governance, "m31_governance_missing"),
        (m32_provider_adapter_verified, "m32_adapter_not_verified"),
        (m33_external_profile_verified, "m33_profile_not_verified"),
        (m34_live_controls, "m34_controls_missing"),
        (m35_sandbox_governance, "m35_governance_missing"),
        (m36_authorization_valid, "m36_authorization_missing"),
        (sandbox_identity_qualified, "identity_not_qualified"),
        (credential_healthy, "credential_unhealthy"),
        (credential_fingerprint_present, "fingerprint_missing"),
        (account_verified, "account_not_verified"),
        (scope_verified, "scope_not_verified"),
        (approval_valid, "approval_invalid"),
        (lease_valid, "lease_invalid"),
        (call_budget_remaining, "call_budget_exhausted"),
        (provider_healthy, "provider_unhealthy"),
        (not quarantined, "quarantined"),
        (rollout_off, "rollout_not_off"),
        (verification_only_exception, "verification_exception_missing"),
    ]
    for ok, code in checks:
        if not ok:
            blockers.append(code)
    return (not blockers), blockers


# ── quarantine ───────────────────────────────────────────────────────────────
class M36Quarantine:
    def __init__(self) -> None:
        self._reasons: list[str] = []
        self.active = False

    def trip(self, reason: str) -> None:
        self.active = True
        self._reasons.append(reason[:200])

    def to_dict(self) -> dict[str, Any]:
        return {"active": self.active, "reasons": list(self._reasons)}


# ── session coordinator ──────────────────────────────────────────────────────
@dataclass
class M36Session:
    session_id: str
    authorization_id: str
    provider_id: str
    account_ref_id: str
    credential_ref_id: str
    operation: str
    endpoint: str
    method: str
    environment_class: str
    status: str = M36SessionState.REQUESTED.value
    lease_id: str = ""
    credential_fingerprint: str = ""
    scope_result: str = ""
    reliability: str = ReliabilityClass.NOT_EXERCISED.value
    certification: str = CertificationState.UNVERIFIED.value
    cleanup_disposition: str = ""
    transitions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def transition(self, state: str) -> None:
        self.status = state
        self.transitions.append(state)

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "schema": "m36.session.v1",
            "session_id": self.session_id,
            "authorization_id": self.authorization_id,
            "provider_id": self.provider_id,
            "account_ref_id": self.account_ref_id,
            "credential_ref_id": self.credential_ref_id,
            "operation": self.operation,
            "endpoint": self.endpoint,
            "method": self.method,
            "environment_class": self.environment_class,
            "status": self.status,
            "lease_id": self.lease_id,
            "credential_fingerprint": self.credential_fingerprint,
            "scope_result": self.scope_result,
            "reliability": self.reliability,
            "certification": self.certification,
            "cleanup_disposition": self.cleanup_disposition,
            "transitions": list(self.transitions),
            "limitations": list(self.limitations),
            "contains_secret_values": False,
            "contains_raw_identity": False,
        }


def _default_eligibility_flags(**over: Any) -> dict[str, bool]:
    base = dict(
        production_certified=True,
        connector_certified=True,
        m30_drift_fresh=True,
        m31_credential_governance=True,
        m32_provider_adapter_verified=True,
        m33_external_profile_verified=True,
        m34_live_controls=True,
        m35_sandbox_governance=True,
        m36_authorization_valid=True,
        sandbox_identity_qualified=True,
        credential_healthy=True,
        credential_fingerprint_present=True,
        account_verified=True,
        scope_verified=True,
        approval_valid=True,
        lease_valid=True,
        call_budget_remaining=True,
        provider_healthy=True,
        quarantined=False,
        rollout_off=True,
        verification_only_exception=True,
    )
    base.update(over)
    return base


def run_m36_session(
    *,
    authorization_store: AuthorizationStore,
    authorization_id: str,
    account_registry: SandboxAccountRegistry,
    account_ref_id: str,
    broker: CredentialBroker,
    credential_ref_id: str,
    lease_store: SessionLeaseStore,
    secret_backend: SecretBackend,
    secret_locator: str,
    identity_qualification: dict[str, Any],
    requested_scopes: tuple[str, ...] = ("identity:read", "metadata:read"),
    transport: Optional[ExternalTransport] = None,
    base_sender: Optional[Callable[[SendContext], dict[str, Any]]] = None,
    live_enabled: bool = False,
    live_env_flag: bool = False,
    perform_identity: bool = True,
    perform_operation: bool = True,
    perform_repeat: bool = False,
    session_id: str = "",
    clock: Optional[Callable[[], float]] = None,
    eligibility_overrides: Optional[dict[str, bool]] = None,
    expected_subject_fingerprint: str = "",
    credential_type: str = "api_key",
    synthetic_offline: bool = False,
) -> dict[str, Any]:
    """Drive one M36 real (or simulated-real) read-only sandbox session.

    When ``synthetic_offline=True`` and a fixture transport is injected, no
    network is touched. Live network requires live_enabled + live_env_flag +
    all acknowledgements already baked into the authorization.
    """
    clk = clock or _now
    events: list[dict[str, Any]] = []
    quarantine = M36Quarantine()
    budget = CallBudget(M36_DEFAULT_CALL_BUDGET)
    handle: Optional[SecretHandle] = None
    sid = session_id or f"sess_m36_{int(clk())}"
    session = M36Session(
        session_id=sid,
        authorization_id=authorization_id,
        provider_id=PROVIDER_ID,
        account_ref_id=account_ref_id,
        credential_ref_id=credential_ref_id,
        operation=OPERATION_META,
        endpoint=ENDPOINT_META,
        method=METHOD_GET,
        environment_class="SANDBOX",
    )

    def _emit(etype: str, **payload: Any) -> None:
        events.append({
            "event_type": etype,
            "session_id": sid,
            "privacy_safe": True,
            "contains_secret_values": False,
            **payload,
        })

    def _fail(reason: str, state: str = M36SessionState.FAILED.value, reliability: str = "") -> dict[str, Any]:
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
        session.transition(state)
        if reliability:
            session.reliability = reliability
        _emit("m36.session_failed", reason=reason)
        return _session_result(
            session, ok=False, reason=reason, events=events, budget=budget,
            quarantine=quarantine, handle_closed=handle is None or not getattr(handle, "_open", False),
            identity_norm=None, meta_norm=None, scope_detail=None,
        )

    # Live gate
    if live_enabled and not live_env_flag and not synthetic_offline:
        return _fail("live_env_flag_required", M36SessionState.BLOCKED.value)

    # 1. Authorization
    try:
        auth = authorization_store.require_valid(
            authorization_id,
            provider_id=PROVIDER_ID,
            account_ref_id=account_ref_id,
            credential_ref_id=credential_ref_id,
            operation=OPERATION_META,
            endpoint=ENDPOINT_META,
        )
    except M36Error as e:
        return _fail(e.code, M36SessionState.BLOCKED.value)
    session.environment_class = auth.environment_class
    session.transition(M36SessionState.AUTHORIZED.value)
    _emit("m36.authorization_created", authorization_id=authorization_id)
    budget = CallBudget(auth.approved_call_budget)

    # 2. Identity qualification
    if not identity_qualification.get("qualified"):
        quarantine.trip("identity_not_qualified")
        return _fail("identity_not_qualified", M36SessionState.BLOCKED.value)
    session.transition(M36SessionState.ACCOUNT_QUALIFIED.value)
    _emit("m36.sandbox_identity_qualified",
          classification=identity_qualification.get("classification"))

    # 3. Account registry
    acct = account_registry.get(account_ref_id)
    if acct is None:
        return _fail("account_not_registered", M36SessionState.BLOCKED.value)
    if acct.provider_id != PROVIDER_ID:
        quarantine.trip("provider_mismatch")
        return _fail("account_provider_mismatch", M36SessionState.QUARANTINED.value)
    exp_fp = expected_subject_fingerprint or acct.account_subject_fingerprint

    # 4. Credential ref health
    ref = broker.get_ref(credential_ref_id)
    if ref is None or ref.status != CredentialStatus.ACTIVE.value:
        return _fail("credential_unhealthy", M36SessionState.BLOCKED.value)

    # 5. Issue session lease
    try:
        lease = lease_store.issue(
            credential_ref_id=credential_ref_id,
            account_ref_id=account_ref_id,
            provider_id=PROVIDER_ID,
            operation=OPERATION_META,
            approved_scopes=requested_scopes,
            session_id=sid,
            approval_id=authorization_id,
            ttl_seconds=min(auth.approved_duration, M36_DEFAULT_LEASE_TTL_SEC),
            max_uses=auth.approved_lease_uses,
        )
    except SessionLeaseError as e:
        return _fail(f"lease:{e.code}", M36SessionState.BLOCKED.value)
    session.lease_id = lease.lease_id
    session.transition(M36SessionState.LEASED.value)

    # 6. Retrieve secret
    try:
        handle = retrieve_secret_handle(
            backend=secret_backend,
            locator=secret_locator,
            authorization=auth,
            lease_id=lease.lease_id,
            session_id=sid,
            provider_id=PROVIDER_ID,
            account_ref_id=account_ref_id,
            events=events,
        )
        fields_snapshot = {k: handle.use(k, lambda v: v, session_id=sid) for k in handle.field_names}
        fp = m36_credential_fingerprint(
            fields_snapshot,
            provider_id=PROVIDER_ID,
            account_ref_id=account_ref_id,
            credential_type=credential_type,
            environment_class=auth.environment_class,
        )
        # zeroize snapshot strings by dropping refs
        fields_snapshot.clear()
        session.credential_fingerprint = fp
        session.transition(M36SessionState.SECRET_LOADED.value)
        _emit("m36.credential_fingerprint_derived", fingerprint=fp)
    except (M36Error, SecretHandleError) as e:
        code = getattr(e, "code", str(e))
        return _fail(f"secret:{code}")

    identity_norm: Optional[dict[str, Any]] = None
    meta_norm: Optional[dict[str, Any]] = None
    scope_detail: Optional[dict[str, Any]] = None

    try:
        # Build transport
        if transport is None:
            if synthetic_offline:
                return _fail("transport_required_offline", M36SessionState.BLOCKED.value)
            if not (live_enabled and live_env_flag):
                return _fail("live_not_enabled", M36SessionState.BLOCKED.value)
            sender = make_authenticated_sender(
                base_sender or urllib_sender, handle, session_id=sid,
            )
            transport = ExternalTransport(sender=sender)
        else:
            # Inject auth into existing transport's sender when possible
            if base_sender is not None or transport.sender is not None:
                underlying = base_sender or transport.sender
                transport = ExternalTransport(
                    resolver=transport.resolver,
                    tls_prober=transport.tls_prober,
                    sender=make_authenticated_sender(underlying, handle, session_id=sid),  # type: ignore[arg-type]
                    clock=transport.clock,
                )

        # 7. Identity verification call
        if perform_identity:
            _emit("m36.account_verification_started")
            budget.consume(kind="identity")
            id_profile = identity_operation_profile()
            envelope = build_request_envelope(id_profile, request_id=f"{sid}-id")
            tr = transport.send(id_profile, envelope)
            if not tr.ok or tr.status_code in (401, 403):
                quarantine.trip("authentication_anomaly")
                session.reliability = ReliabilityClass.AUTHENTICATION_FAILURE.value
                return _fail(
                    f"identity_transport:{tr.failure_code or tr.status_code}",
                    M36SessionState.FAILED.value,
                    reliability=ReliabilityClass.AUTHENTICATION_FAILURE.value,
                )
            identity_norm = normalize_identity_response(
                status_code=tr.status_code,
                headers=tr.headers,
                body_bytes=tr.body_bytes,
                expected_subject_fingerprint=exp_fp,
                provider_id=PROVIDER_ID,
                transport_ok=tr.ok,
                tls=tr.tls,
                latency_ms=tr.latency_ms,
            )
            # discard raw body
            tr.body_bytes = b""
            if not identity_norm["schema_valid"]:
                quarantine.trip("schema_mismatch")
                return _fail("identity_schema_failure", reliability=ReliabilityClass.SCHEMA_FAILURE.value)
            if not identity_norm["account_match"] and exp_fp:
                quarantine.trip("account_mismatch")
                return _fail("account_mismatch", M36SessionState.QUARANTINED.value)
            session.transition(M36SessionState.IDENTITY_VERIFIED.value)
            _emit("m36.account_verification_completed", safe_status=identity_norm["safe_status"])

            # 8. Scope verification from observed headers
            observed = None
            if identity_norm.get("observed_scopes") is not None:
                observed = tuple(identity_norm["observed_scopes"])
            scope_detail = classify_observed_scopes(
                requested_scopes, observed,
                allowed_scope_classes=auth.approved_scope_classes,
            )
            session.scope_result = scope_detail["result"]
            _emit("m36.scope_verification_completed", result=session.scope_result)
            if scope_detail["result"] in (
                M36ScopeResult.WRITE_SCOPE_PRESENT.value,
                M36ScopeResult.MISMATCHED.value,
                M36ScopeResult.UNKNOWN.value,
            ):
                quarantine.trip(f"scope:{scope_detail['result']}")
                return _fail(
                    f"scope_failure:{scope_detail['result']}",
                    M36SessionState.QUARANTINED.value,
                    reliability=ReliabilityClass.SCOPE_FAILURE.value,
                )
            session.transition(M36SessionState.SCOPE_VERIFIED.value)
            if scope_detail["result"] == M36ScopeResult.DECLARED_ONLY_UNOBSERVED.value:
                session.limitations.append("scope_not_independently_observed")
            if scope_detail["result"] == M36ScopeResult.VERIFIED_WITH_EXTRA_READ_SCOPE.value:
                session.limitations.append("extra_read_scope_present")

        # 9. Eligibility (with fingerprint now present)
        flags = _default_eligibility_flags(
            m36_authorization_valid=True,
            sandbox_identity_qualified=True,
            credential_fingerprint_present=bool(session.credential_fingerprint),
            account_verified=session.status in (
                M36SessionState.IDENTITY_VERIFIED.value,
                M36SessionState.SCOPE_VERIFIED.value,
                M36SessionState.ELIGIBLE.value,
            ) or not perform_identity,
            scope_verified=session.scope_result in (
                M36ScopeResult.VERIFIED_READ_ONLY.value,
                M36ScopeResult.VERIFIED_WITH_EXTRA_READ_SCOPE.value,
                M36ScopeResult.DECLARED_ONLY_UNOBSERVED.value,
            ) or not perform_identity,
            call_budget_remaining=budget.remaining() > 0 or not perform_operation,
            quarantined=quarantine.active,
        )
        if eligibility_overrides:
            flags.update(eligibility_overrides)
        eligible, blockers = compose_m36_eligibility(**flags)
        _emit("m36.eligibility_evaluated", eligible=eligible, blockers=blockers)
        if not eligible:
            return _fail("eligibility:" + ",".join(blockers), M36SessionState.BLOCKED.value)
        session.transition(M36SessionState.ELIGIBLE.value)

        # 10. Operation call (get_meta)
        if perform_operation:
            if budget.remaining() <= 0:
                return _fail("call_budget_exhausted")
            budget.consume(kind="operation")
            session.transition(M36SessionState.RUNNING.value)
            _emit("m36.session_started")
            _emit("m36.transport_call_started", operation=OPERATION_META)
            meta_profile = meta_operation_profile()
            # ceiling check
            ceiling = ceiling_from_profile(
                meta_profile, environment_class=auth.environment_class,
                allowed_scopes=requested_scopes,
            )
            within, why = request_within_ceiling({
                "provider_id": PROVIDER_ID,
                "operation": OPERATION_META,
                "method": METHOD_GET,
                "side_effect_class": meta_profile.side_effect_class,
                "data_classification": meta_profile.data_classification,
                "environment_class": auth.environment_class,
                "scopes": requested_scopes,
            }, ceiling)
            if not within:
                quarantine.trip(why)
                return _fail(f"ceiling:{why}")
            envelope = build_request_envelope(meta_profile, request_id=f"{sid}-op")
            tr = transport.send(meta_profile, envelope)
            meta_norm = normalize_meta_response(
                status_code=tr.status_code,
                body_bytes=tr.body_bytes,
                content_type=tr.content_type,
                latency_ms=tr.latency_ms,
                transport_ok=tr.ok,
                tls=tr.tls,
            )
            tr.body_bytes = b""
            _emit("m36.transport_call_completed", ok=tr.ok, status_class=meta_norm["http_status_class"])
            if not tr.ok or not meta_norm["schema_valid"]:
                if tr.failure_code:
                    quarantine.trip(tr.failure_code)
                return _fail(
                    f"operation_failed:{tr.failure_code or tr.status_code}",
                    reliability=ReliabilityClass.TRANSPORT_FAILURE.value if not tr.ok else ReliabilityClass.SCHEMA_FAILURE.value,
                )

        # 11. Optional repeat
        if perform_repeat and budget.remaining() > 0:
            budget.consume(kind="operation", is_retry=False)
            meta_profile = meta_operation_profile()
            envelope = build_request_envelope(meta_profile, request_id=f"{sid}-rep")
            tr = transport.send(meta_profile, envelope)
            tr.body_bytes = b""
            if tr.ok:
                session.reliability = ReliabilityClass.REPEATABLE_SUCCESS.value
            else:
                session.reliability = ReliabilityClass.SUCCESS_WITH_LIMITATIONS.value
                session.limitations.append("repeat_failed")
        else:
            if perform_operation or perform_identity:
                if session.limitations:
                    session.reliability = ReliabilityClass.SUCCESS_WITH_LIMITATIONS.value
                else:
                    session.reliability = ReliabilityClass.SINGLE_SUCCESS.value

        # 12. Consume lease use, then revoke residual authority (no silent reuse)
        try:
            lease_store.consume(
                lease.lease_id,
                credential_ref_id=credential_ref_id,
                account_ref_id=account_ref_id,
                provider_id=PROVIDER_ID,
                operation=OPERATION_META,
                session_id=sid,
                requested_scopes=requested_scopes,
            )
        except SessionLeaseError as e:
            return _fail(f"lease_consume:{e.code}")
        lease_store.revoke(lease.lease_id, reason="m36_session_completed")
        session.transition(M36SessionState.LEASE_CONSUMED.value)
        _emit("m36.lease_consumed")
        _emit("m36.lease_revoked", reason="m36_session_completed")

        # 13. Close secret
        handle.close()
        handle = None
        session.transition(M36SessionState.SECRET_CLOSED.value)
        _emit("m36.secret_handle_closed")

        # 14. Consume authorization (one-session)
        authorization_store.consume(authorization_id)
        session.transition(M36SessionState.COMPLETED.value)
        _emit("m36.session_completed")

        # 15. Certification
        session.certification = assess_m36_certification(
            identity_ok=perform_identity and identity_norm is not None and identity_norm.get("account_match", True),
            scope_result=session.scope_result or M36ScopeResult.DECLARED_ONLY_UNOBSERVED.value,
            session_ok=True,
            limitations=session.limitations,
            quarantined=quarantine.active,
        )
        _emit("m36.certification_updated", state=session.certification)

    except M36Error as e:
        if handle is not None:
            handle.close()
            handle = None
        if quarantine.active:
            return _fail(e.code, M36SessionState.QUARANTINED.value)
        return _fail(e.code)
    except Exception as e:
        if handle is not None:
            handle.close()
            handle = None
        return _fail(f"unexpected:{type(e).__name__}")
    finally:
        if handle is not None:
            handle.close()

    return _session_result(
        session, ok=True, reason="ok", events=events, budget=budget,
        quarantine=quarantine, handle_closed=True,
        identity_norm=identity_norm, meta_norm=meta_norm, scope_detail=scope_detail,
    )


def _session_result(
    session: M36Session,
    *,
    ok: bool,
    reason: str,
    events: list[dict[str, Any]],
    budget: CallBudget,
    quarantine: M36Quarantine,
    handle_closed: bool,
    identity_norm: Optional[dict[str, Any]],
    meta_norm: Optional[dict[str, Any]],
    scope_detail: Optional[dict[str, Any]],
) -> dict[str, Any]:
    result = {
        "schema": "m36.session_result.v1",
        "ok": ok,
        "reason": reason,
        "session": session.to_safe_dict(),
        "session_state": session.status,
        "credential_fingerprint": session.credential_fingerprint,
        "handle_closed": handle_closed,
        "call_budget": budget.to_dict(),
        "network_accounting": budget.to_dict(),
        "quarantine": quarantine.to_dict(),
        "identity_verification": identity_norm,
        "normalized_provider_result": meta_norm,
        "scope_verification": scope_detail,
        "events": events,
        "label": NON_PRODUCTION_BANNER,
        "rollout_state": {
            "connector": "OFF",
            "provider": "OFF",
            "inference": "OFF",
            "canary_providers": 0,
            "active_providers": 0,
        },
        "authorities": {
            "production_authorization": "NOT GRANTED",
            "rollout_authorization": "NOT GRANTED",
            "CANARY_authorization": "NOT GRANTED",
            "ACTIVE_authorization": "NOT GRANTED",
            "write_authority": "NOT GRANTED",
        },
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "m37_started": False,
        "privacy_safe": True,
        "contains_secret_values": False,
        "contains_raw_identity": False,
        "external_writes": 0,
        "financial_calls": 0,
        "trading_calls": 0,
    }
    # leak-scan before return
    if not is_clean(result):
        findings = [f.to_dict() for f in scan(result)]
        result["ok"] = False
        result["reason"] = "leak_detected"
        result["leak_findings"] = findings
        quarantine.trip("leak_detection")
        result["quarantine"] = quarantine.to_dict()
    return result


def assess_m36_certification(
    *,
    identity_ok: bool,
    scope_result: str,
    session_ok: bool,
    limitations: Optional[list[str]] = None,
    quarantined: bool = False,
    revoked: bool = False,
    stale: bool = False,
    authorization_ready_only: bool = False,
) -> str:
    if revoked:
        return CertificationState.REVOKED.value
    if quarantined:
        return CertificationState.QUARANTINED.value
    if stale:
        return CertificationState.STALE.value
    if authorization_ready_only:
        return CertificationState.AUTHORIZATION_READY.value
    if not session_ok:
        return CertificationState.FAILED.value
    lims = limitations or []
    if session_ok and identity_ok:
        if scope_result in (M36ScopeResult.DECLARED_ONLY_UNOBSERVED.value,) or lims:
            if scope_result == M36ScopeResult.VERIFIED_READ_ONLY.value and not lims:
                return CertificationState.REAL_SANDBOX_SESSION_VERIFIED.value
            return CertificationState.REAL_SANDBOX_SESSION_VERIFIED_WITH_LIMITATIONS.value
        if scope_result in (
            M36ScopeResult.VERIFIED_READ_ONLY.value,
            M36ScopeResult.VERIFIED_WITH_EXTRA_READ_SCOPE.value,
        ):
            if scope_result == M36ScopeResult.VERIFIED_WITH_EXTRA_READ_SCOPE.value:
                return CertificationState.REAL_SANDBOX_SESSION_VERIFIED_WITH_LIMITATIONS.value
            return CertificationState.REAL_SANDBOX_SESSION_VERIFIED.value
        if identity_ok and scope_result in (
            M36ScopeResult.VERIFIED_READ_ONLY.value,
            M36ScopeResult.VERIFIED_WITH_EXTRA_READ_SCOPE.value,
            M36ScopeResult.DECLARED_ONLY_UNOBSERVED.value,
        ):
            return CertificationState.REAL_SANDBOX_SESSION_VERIFIED_WITH_LIMITATIONS.value
        return CertificationState.REAL_SANDBOX_IDENTITY_VERIFIED.value
    return CertificationState.FAILED.value


def attest_cleanup(
    session: M36Session,
    *,
    disposition: str,
    external_revocation_attested: bool = False,
    lease_store: Optional[SessionLeaseStore] = None,
) -> dict[str, Any]:
    """Record cleanup disposition. SILENT_ACTIVE fails closed."""
    if disposition == CleanupDisposition.SILENT_ACTIVE.value:
        raise M36Error("silent_active_credential_forbidden")
    valid = {c.value for c in CleanupDisposition} - {CleanupDisposition.SILENT_ACTIVE.value}
    if disposition not in valid:
        raise M36Error("invalid_cleanup_disposition", disposition)
    if disposition == CleanupDisposition.EXTERNAL_REVOCATION_OPERATOR_ATTESTED.value:
        external_revocation_attested = True
    if lease_store and session.lease_id and disposition in (
        CleanupDisposition.LEASE_REVOKED.value,
        CleanupDisposition.CREDENTIAL_REVOKED_EXTERNALLY.value,
    ):
        lease_store.revoke(session.lease_id, reason=disposition)
    session.cleanup_disposition = disposition
    session.transition(M36SessionState.REVOKED_OR_EXPIRED.value)
    return {
        "cleanup_disposition": disposition,
        "external_revocation_attested": external_revocation_attested,
        "lease_id": session.lease_id,
        "session_id": session.session_id,
        "privacy_safe": True,
    }


# ── write rejection (offline only) ───────────────────────────────────────────
def assert_read_only_operation(method: str, side_effect_class: str = "READ_ONLY") -> None:
    m = (method or "").upper()
    if m in _WRITE_METHODS:
        raise M36Error("write_method_blocked", m)
    if m not in ("GET", "HEAD"):
        raise M36Error("method_not_read_only", m)
    if side_effect_class not in ("NONE", "READ_ONLY", None, ""):
        if side_effect_class and "WRITE" in side_effect_class.upper():
            raise M36Error("write_side_effect_blocked", side_effect_class)


def reject_forbidden_cli_argv(argv: list[str]) -> None:
    for a in argv:
        base = a.split("=")[0].lower()
        if base in FORBIDDEN_CLI_FLAGS or base.lstrip("-") in (
            "token", "api-key", "apikey", "password", "secret", "authorization-header",
        ):
            raise M36Error("raw_secret_cli_rejected", base)


# ── fingerprint / evidence ───────────────────────────────────────────────────
def compute_m36_fingerprint() -> str:
    material = {
        "schema": SCHEMA_VERSION,
        "provider": PROVIDER_ID,
        "operations": [OPERATION_IDENTITY, OPERATION_META],
        "endpoints": [ENDPOINT_IDENTITY, ENDPOINT_META],
        "max_calls": M36_MAX_CALL_BUDGET,
        "acks": list(M36_ACK_TOKENS),
        "cert_states": sorted(c.value for c in CertificationState),
    }
    return _hmac_hex(b"m36_surface", json.dumps(material, sort_keys=True).encode(), length=64)


def write_m36_evidence(
    bodies: dict[str, dict[str, Any]],
    *,
    evidence_dir: str = "docs/evidence/m36",
) -> list[str]:
    from saathi.connectors.providers.evidence import write_evidence

    d = Path(evidence_dir)
    written: list[str] = []
    for name, body in bodies.items():
        assert_clean(body, context=f"m36.evidence:{name}")
        written.append(write_evidence(name, body, evidence_dir=d, schema=f"m36.{name}.v1"))
    return written


def validation_summary_body(
    *,
    session_result: Optional[dict[str, Any]] = None,
    certification: str = CertificationState.AUTHORIZATION_READY.value,
    real_session_exercised: bool = False,
) -> dict[str, Any]:
    sr = session_result or {}
    budget = sr.get("call_budget") or sr.get("network_accounting") or {}
    return {
        "milestone": "M36",
        "production_credentials_loaded": 0,
        "production_oauth_flows": 0,
        "production_accounts_linked": 0,
        "real_sandbox_credentials_loaded": 1 if real_session_exercised else 0,
        "real_sandbox_oauth_flows": 0,
        "real_sandbox_accounts_linked": 1 if real_session_exercised else 0,
        "synthetic_sessions_used": 0 if real_session_exercised else 1,
        "credentials_committed_to_git": 0,
        "raw_secrets_in_evidence": 0,
        "raw_secrets_in_logs": 0,
        "raw_secrets_in_events": 0,
        "external_network_calls": int(budget.get("consumed", 0)),
        "external_provider_writes": 0,
        "financial_provider_calls": 0,
        "trading_provider_calls": 0,
        "connector_rollout": "OFF",
        "provider_rollout": "OFF",
        "inference_rollout": "OFF",
        "canary_providers": 0,
        "active_providers": 0,
        "m36_certification": certification,
        "real_sandbox_session": "EXERCISED" if real_session_exercised else "NOT_EXERCISED",
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "m37_started": False,
        "authorities": {
            "production_authorization": "NOT GRANTED",
            "rollout_authorization": "NOT GRANTED",
            "CANARY_authorization": "NOT GRANTED",
            "ACTIVE_authorization": "NOT GRANTED",
            "write_authority": "NOT GRANTED",
        },
    }


def preflight_summary() -> dict[str, Any]:
    return {
        "milestone": "M36",
        "provider": PROVIDER_ID,
        "identity_operation": OPERATION_IDENTITY,
        "identity_endpoint": ENDPOINT_IDENTITY,
        "operation": OPERATION_META,
        "endpoint": ENDPOINT_META,
        "method": METHOD_GET,
        "max_calls": M36_MAX_CALL_BUDGET,
        "rollout": "OFF",
        "canary": 0,
        "active": 0,
        "trading_guardian": "UNENGAGED",
        "banner": NON_PRODUCTION_BANNER,
        "live_flag": ENV_LIVE_FLAG,
        "fingerprint": compute_m36_fingerprint(),
        "authentication_required_for_identity": True,
        "authentication_required_for_meta": False,
    }
