"""M35 — Governed sandbox credential & read-only session governance.

Extends the M31 credential architecture (broker, leases, scopes, backends,
leakscan) and composes it with the M33/M34 external-provider capability ceiling.
Never a parallel secret / lease / account / audit system: secret material only
ever flows through the M31 ``CredentialBroker`` + ``SecretBackend``; this module
adds the sandbox governance layered on top.

Hard invariants enforced here (all fail-closed):
  * environment class ``PRODUCTION`` is never permitted;
  * only the ``IN_MEMORY_TEST`` secret source is retrievable — others validate
    structurally only; no fallback between sources; no automatic secret search;
  * no raw secret is ever accepted, returned, serialized, logged, or persisted;
  * scopes must classify to a read-only allow-list; unknown scopes fail closed;
  * a session request must be a subset of the composed capability ceiling;
  * no network call, no write, no rollout mutation, Trading Guardian untouched.

Nothing in this module contacts a provider, opens a socket, reads an arbitrary
environment variable, or touches the OS keychain.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.credentials.backends import InMemoryTestSecretBackend
from saathi.credentials.broker import CredentialBroker
from saathi.credentials.leakscan import assert_clean, is_clean, scan
from saathi.credentials.models import (
    CredentialStatus,
    is_prohibited_provider,
    is_prohibited_scope,
)

SCHEMA_VERSION = "m35.sandbox_credentials.v1"
M35_SURFACE_PATH = "saathi/credentials/m35.py"
ROOT = Path(__file__).resolve().parents[2]
M35_EVIDENCE_DIR = ROOT / "docs" / "evidence" / "m35"

# Domain-separation key for non-reversible fingerprints. NOT a secret and never
# usable as authentication material — it only separates fingerprint domains.
_FP_DOMAIN_KEY = b"saathi.m35.fingerprint.domain.v1"

# Test defaults (NOT production policy).
M35_DEFAULT_LEASE_TTL_SEC = 300.0   # 5 minutes
M35_DEFAULT_MAX_USES = 1
M35_MAX_LEASE_TTL_SEC = 900.0       # hard ceiling: 15 minutes


class M35Error(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


# ── environment classification ───────────────────────────────────────────────
class EnvironmentClass(str, Enum):
    SYNTHETIC = "SYNTHETIC"
    LOCAL_TEST = "LOCAL_TEST"
    SANDBOX = "SANDBOX"
    PRODUCTION = "PRODUCTION"


_ALLOWED_ENVIRONMENTS = frozenset({
    EnvironmentClass.SYNTHETIC.value,
    EnvironmentClass.LOCAL_TEST.value,
    EnvironmentClass.SANDBOX.value,
})
# Free-form M31 environment strings mapped to M35 classes.
_ENV_ALIASES = {
    "synthetic": EnvironmentClass.SYNTHETIC.value,
    "test": EnvironmentClass.LOCAL_TEST.value,
    "local": EnvironmentClass.LOCAL_TEST.value,
    "local_test": EnvironmentClass.LOCAL_TEST.value,
    "dev": EnvironmentClass.LOCAL_TEST.value,
    "sandbox": EnvironmentClass.SANDBOX.value,
    "prod": EnvironmentClass.PRODUCTION.value,
    "production": EnvironmentClass.PRODUCTION.value,
    "live": EnvironmentClass.PRODUCTION.value,
}


def classify_environment(value: str) -> str:
    v = (value or "").strip()
    if v in EnvironmentClass.__members__ or v in {e.value for e in EnvironmentClass}:
        return v
    alias = _ENV_ALIASES.get(v.lower())
    if alias:
        return alias
    raise M35Error("unknown_environment", v)


def assert_environment_allowed(value: str) -> str:
    ec = classify_environment(value)
    if ec == EnvironmentClass.PRODUCTION.value:
        raise M35Error("production_environment_forbidden", value)
    if ec not in _ALLOWED_ENVIRONMENTS:
        raise M35Error("environment_not_allowed", value)
    return ec


# ── secret-source policy ─────────────────────────────────────────────────────
class SecretSourceKind(str, Enum):
    IN_MEMORY_TEST = "IN_MEMORY_TEST"
    ENV_REFERENCE = "ENV_REFERENCE"
    OS_KEYCHAIN_REFERENCE = "OS_KEYCHAIN_REFERENCE"
    ENCRYPTED_STORE_REFERENCE = "ENCRYPTED_STORE_REFERENCE"
    EXTERNAL_SECRET_MANAGER_REFERENCE = "EXTERNAL_SECRET_MANAGER_REFERENCE"


# Only in-memory synthetic secrets may actually be retrieved in M35.
_RETRIEVABLE_SOURCES = frozenset({SecretSourceKind.IN_MEMORY_TEST.value})

# Sources that are never acceptable — a caller offering one is an incident.
PROHIBITED_SECRET_SOURCES = frozenset({
    "PLAINTEXT", "REPOSITORY_FILE", "COMMAND_LINE_VALUE", "LOG_EMBEDDED",
    "EVIDENCE_EMBEDDED", "CALLER_RAW_SECRET",
})


def validate_secret_source(kind: str, *, want_retrieval: bool = False) -> dict[str, Any]:
    """Classify a secret source. Fail-closed on prohibited/unknown sources and on
    any request to retrieve from a non-retrievable source. No fallback."""
    k = (kind or "").strip().upper()
    if k in PROHIBITED_SECRET_SOURCES:
        raise M35Error("prohibited_secret_source", k)
    if k not in {s.value for s in SecretSourceKind}:
        raise M35Error("unknown_secret_source", k)
    retrievable = k in _RETRIEVABLE_SOURCES
    if want_retrieval and not retrievable:
        raise M35Error("secret_source_not_retrievable", k)
    return {
        "source_kind": k,
        "retrievable": retrievable,
        "structural_only": not retrievable,
        "fallback_permitted": False,
    }


# ── non-reversible fingerprints ──────────────────────────────────────────────
def _hmac_hex(*parts: bytes, length: int = 32) -> str:
    mac = hmac.new(_FP_DOMAIN_KEY, b"|".join(parts), hashlib.sha256)
    return mac.hexdigest()[:length]


def _canonical_secret_bytes(secret_material: Any) -> bytes:
    if secret_material is None:
        return b""
    if isinstance(secret_material, (bytes, bytearray)):
        return bytes(secret_material)
    if isinstance(secret_material, dict):
        if not secret_material:
            return b""
        return json.dumps({k: str(v) for k, v in sorted(secret_material.items())},
                          separators=(",", ":")).encode()
    s = str(secret_material)
    return s.encode() if s else b""


def m35_secret_fingerprint(
    secret_material: Any,
    *,
    provider_id: str,
    account_ref_id: str = "",
) -> str:
    """Provider/account-bound, non-reversible, fixed-width fingerprint of secret
    material. Empty string when no secret is loaded. Reveals no length, prefix, or
    suffix, and cannot be used to authenticate."""
    body = _canonical_secret_bytes(secret_material)
    if not body:
        return ""
    return _hmac_hex(
        b"secret", provider_id.encode(), account_ref_id.encode(), body,
    )


def subject_fingerprint(subject: str, *, provider_id: str = "") -> str:
    """Non-reversible fingerprint of an account subject (never store raw subject)."""
    if not subject:
        return ""
    return _hmac_hex(b"subject", provider_id.encode(), str(subject).encode())


# ── secret-handle boundary ───────────────────────────────────────────────────
class SecretHandleError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class SecretHandle:
    """Bounded container for secret material. Non-printable, non-serializable,
    zeroizing, use-after-close-safe, and bound to one session/lease/provider/
    account. Secret bytes never appear in repr/str/json/logs/tracebacks."""

    __slots__ = ("_open", "_fields", "_session_id", "_lease_id", "_provider_id", "_account_ref_id")

    def __init__(
        self,
        fields: dict[str, str],
        *,
        session_id: str,
        lease_id: str,
        provider_id: str,
        account_ref_id: str = "",
    ) -> None:
        object.__setattr__(self, "_open", True)
        object.__setattr__(self, "_fields", {k: bytearray(str(v).encode()) for k, v in fields.items()})
        object.__setattr__(self, "_session_id", session_id)
        object.__setattr__(self, "_lease_id", lease_id)
        object.__setattr__(self, "_provider_id", provider_id)
        object.__setattr__(self, "_account_ref_id", account_ref_id)

    # representation never reveals secret material
    def __repr__(self) -> str:
        n = len(self._fields) if self._open else 0
        return f"<SecretHandle open={self._open} fields={n} session={self._session_id} REDACTED>"

    __str__ = __repr__

    def __reduce__(self):  # block pickling
        raise SecretHandleError("handle_not_serializable")

    def __getstate__(self):  # block pickling/copy
        raise SecretHandleError("handle_not_serializable")

    def to_json(self) -> str:
        raise SecretHandleError("handle_not_serializable")

    def __eq__(self, other: Any) -> bool:  # identity only — never compares secret
        return other is self

    def __hash__(self) -> int:
        return id(self)

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._fields)) if self._open else ()

    def _guard(self, session_id: str) -> None:
        if not self._open:
            raise SecretHandleError("handle_closed")
        if session_id != self._session_id:
            raise SecretHandleError("session_mismatch")

    def use(self, field: str, consumer: Callable[[str], Any], *, session_id: str) -> Any:
        """Expose one field's value to a consumer callable inside the session. The
        raw value never leaves this method except through the caller's consumer."""
        self._guard(session_id)
        if field not in self._fields:
            raise SecretHandleError("unknown_field")
        return consumer(self._fields[field].decode())

    def matches_fingerprint(self, fingerprint: str, *, provider_id: str, account_ref_id: str = "", session_id: str) -> bool:
        """Constant-time compare against a fingerprint without exposing the secret."""
        self._guard(session_id)
        current = {k: bytes(v).decode() for k, v in self._fields.items()}
        fp = m35_secret_fingerprint(current, provider_id=provider_id, account_ref_id=account_ref_id)
        return hmac.compare_digest(fp, fingerprint or "")

    def close(self) -> None:
        """Zeroize mutable buffers and mark closed. Idempotent."""
        if not self._open:
            return
        for buf in self._fields.values():
            for i in range(len(buf)):
                buf[i] = 0
        self._fields.clear()
        object.__setattr__(self, "_open", False)

    def __enter__(self) -> "SecretHandle":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


# ── least-privilege scope classes ────────────────────────────────────────────
class M35ScopeClass(str, Enum):
    IDENTITY_READ = "IDENTITY_READ"
    METADATA_READ = "METADATA_READ"
    PUBLIC_DATA_READ = "PUBLIC_DATA_READ"
    SANDBOX_RESOURCE_READ = "SANDBOX_RESOURCE_READ"


ALLOWED_SCOPE_CLASSES = frozenset({c.value for c in M35ScopeClass})

FORBIDDEN_SCOPE_CLASSES = frozenset({
    "WRITE", "ADMIN", "OWNER", "BILLING", "PAYMENT", "TRANSFER", "WITHDRAWAL",
    "TRADING", "ORDER_ENTRY", "PORTFOLIO_CONTROL", "SECRET_MANAGEMENT",
    "USER_MANAGEMENT", "REPOSITORY_WRITE", "EMAIL_SEND", "CALENDAR_WRITE",
    "SOCIAL_PUBLISH", "CLOUD_ADMIN",
})

# concrete scope token → allowed class
_ALLOWED_SCOPE_TOKENS = {
    "identity:read": M35ScopeClass.IDENTITY_READ.value,
    "identity.read": M35ScopeClass.IDENTITY_READ.value,
    "user:read": M35ScopeClass.IDENTITY_READ.value,
    "read:user": M35ScopeClass.IDENTITY_READ.value,
    "metadata:read": M35ScopeClass.METADATA_READ.value,
    "meta:read": M35ScopeClass.METADATA_READ.value,
    "read:meta": M35ScopeClass.METADATA_READ.value,
    "public:read": M35ScopeClass.PUBLIC_DATA_READ.value,
    "public_data:read": M35ScopeClass.PUBLIC_DATA_READ.value,
    "read:public": M35ScopeClass.PUBLIC_DATA_READ.value,
    "sandbox:read": M35ScopeClass.SANDBOX_RESOURCE_READ.value,
    "sandbox_resource:read": M35ScopeClass.SANDBOX_RESOURCE_READ.value,
    "read:sandbox": M35ScopeClass.SANDBOX_RESOURCE_READ.value,
}

# substring → forbidden class (fail-closed on anything write/privileged)
_FORBIDDEN_SCOPE_SUBSTR = [
    ("withdraw", "WITHDRAWAL"), ("transfer", "TRANSFER"), ("payment", "PAYMENT"),
    ("billing", "BILLING"), ("trade", "TRADING"), ("trading", "TRADING"),
    ("order", "ORDER_ENTRY"), ("portfolio", "PORTFOLIO_CONTROL"),
    ("secret", "SECRET_MANAGEMENT"), ("user_management", "USER_MANAGEMENT"),
    ("usermgmt", "USER_MANAGEMENT"), ("repo:write", "REPOSITORY_WRITE"),
    ("repository:write", "REPOSITORY_WRITE"), ("email:send", "EMAIL_SEND"),
    ("mail.send", "EMAIL_SEND"), ("calendar:write", "CALENDAR_WRITE"),
    ("social:publish", "SOCIAL_PUBLISH"), ("publish", "SOCIAL_PUBLISH"),
    ("cloud:admin", "CLOUD_ADMIN"), ("admin", "ADMIN"), ("owner", "OWNER"),
    ("write", "WRITE"),
]


def classify_scope(scope: str) -> str:
    """Return the scope class name, a FORBIDDEN class, or 'UNKNOWN' (fail-closed)."""
    s = (scope or "").strip().lower()
    if not s:
        return "UNKNOWN"
    if s in _ALLOWED_SCOPE_TOKENS:
        return _ALLOWED_SCOPE_TOKENS[s]
    up = s.upper()
    if up in ALLOWED_SCOPE_CLASSES:
        return up
    if up in FORBIDDEN_SCOPE_CLASSES:
        return up
    if is_prohibited_scope(s):
        return "TRADING" if any(x in s for x in ("trade", "leverage", "margin", "futures")) else "PAYMENT"
    for sub, cls in _FORBIDDEN_SCOPE_SUBSTR:
        if sub in s:
            return cls
    return "UNKNOWN"


def scope_is_allowed(scope: str) -> bool:
    return classify_scope(scope) in ALLOWED_SCOPE_CLASSES


def assert_scopes_allowed(scopes: tuple[str, ...]) -> tuple[str, ...]:
    """Every scope must classify to an allowed read-only class. Fail-closed."""
    bad: list[str] = []
    unknown: list[str] = []
    for s in scopes:
        cls = classify_scope(s)
        if cls == "UNKNOWN":
            unknown.append(s)
        elif cls not in ALLOWED_SCOPE_CLASSES:
            bad.append(s)
    if unknown:
        raise M35Error("unknown_scope", ",".join(sorted(unknown)))
    if bad:
        raise M35Error("forbidden_scope", ",".join(sorted(bad)))
    return tuple(scopes)


class ScopeVerificationState(str, Enum):
    DECLARED = "DECLARED"
    OBSERVED = "OBSERVED"
    VERIFIED = "VERIFIED"
    MISMATCHED = "MISMATCHED"
    UNKNOWN = "UNKNOWN"


def verify_scope_evidence(
    declared: tuple[str, ...],
    observed: Optional[tuple[str, ...]],
    *,
    synthetic: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Classify scope verification. A declared read-only scope alone is not
    sufficient; verified evidence or an explicit synthetic classification is."""
    detail: dict[str, Any] = {"declared": list(declared), "observed": list(observed or [])}
    for s in declared:
        if classify_scope(s) == "UNKNOWN":
            return ScopeVerificationState.UNKNOWN.value, {**detail, "reason": "unknown_declared_scope"}
    if synthetic:
        return ScopeVerificationState.VERIFIED.value, {**detail, "reason": "synthetic_test_classification"}
    if observed is None:
        return ScopeVerificationState.DECLARED.value, {**detail, "reason": "declared_only_insufficient"}
    for s in observed:
        if classify_scope(s) == "UNKNOWN":
            return ScopeVerificationState.UNKNOWN.value, {**detail, "reason": "unknown_observed_scope"}
    dset, oset = set(declared), set(observed)
    if oset - dset:
        return ScopeVerificationState.MISMATCHED.value, {**detail, "reason": "observed_broadens_declared", "extra": sorted(oset - dset)}
    if dset - oset:
        return ScopeVerificationState.MISMATCHED.value, {**detail, "reason": "observed_missing_declared", "missing": sorted(dset - oset)}
    return ScopeVerificationState.VERIFIED.value, {**detail, "reason": "observed_matches_declared"}


# ── capability ceiling ───────────────────────────────────────────────────────
@dataclass(frozen=True)
class CapabilityCeiling:
    provider_id: str
    operation: str
    method: str
    side_effect_class: str
    data_classification: str
    environment_class: str
    allowed_scopes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["allowed_scopes"] = list(self.allowed_scopes)
        return d


def ceiling_from_profile(profile: Any, *, environment_class: str, allowed_scopes: tuple[str, ...]) -> CapabilityCeiling:
    env = assert_environment_allowed(environment_class)
    assert_scopes_allowed(tuple(allowed_scopes))
    return CapabilityCeiling(
        provider_id=profile.provider_id,
        operation=profile.operation,
        method=(profile.method or "").upper(),
        side_effect_class=profile.side_effect_class,
        data_classification=profile.data_classification,
        environment_class=env,
        allowed_scopes=tuple(allowed_scopes),
    )


def intersect_ceilings(*ceilings: CapabilityCeiling) -> CapabilityCeiling:
    """Every ceiling must agree on provider/operation/method/side-effect/data/env;
    scopes intersect. Any disagreement fails closed."""
    cs = [c for c in ceilings if c is not None]
    if not cs:
        raise M35Error("no_ceiling")
    base = cs[0]
    scopes = set(base.allowed_scopes)
    for c in cs[1:]:
        for fld in ("provider_id", "operation", "method", "side_effect_class",
                    "data_classification", "environment_class"):
            if getattr(c, fld) != getattr(base, fld):
                raise M35Error("ceiling_conflict", fld)
        scopes &= set(c.allowed_scopes)
    return CapabilityCeiling(
        provider_id=base.provider_id, operation=base.operation, method=base.method,
        side_effect_class=base.side_effect_class, data_classification=base.data_classification,
        environment_class=base.environment_class, allowed_scopes=tuple(sorted(scopes)),
    )


_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def request_within_ceiling(request: dict[str, Any], ceiling: CapabilityCeiling) -> tuple[bool, str]:
    """A session request must be a subset of the ceiling. Any broadening or
    substitution fails closed."""
    if request.get("provider_id") != ceiling.provider_id:
        return False, "provider_substitution"
    if request.get("operation") != ceiling.operation:
        return False, "operation_broadening"
    method = (request.get("method") or "").upper()
    if method != ceiling.method:
        return False, "method_broadening"
    if method in _WRITE_METHODS:
        return False, "write_method_blocked"
    if request.get("side_effect_class") not in (None, ceiling.side_effect_class):
        return False, "side_effect_escalation"
    if request.get("data_classification") not in (None, ceiling.data_classification):
        return False, "data_classification_broadening"
    if request.get("environment_class") not in (None, ceiling.environment_class):
        return False, "environment_broadening"
    req_scopes = set(request.get("scopes", ()) or ())
    if not req_scopes.issubset(set(ceiling.allowed_scopes)):
        return False, "scope_broadening"
    return True, "ok"


# ── sandbox account registry ─────────────────────────────────────────────────
class AccountVerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    SYNTHETIC_VERIFIED = "SYNTHETIC_VERIFIED"
    VERIFIED = "VERIFIED"
    MISMATCHED = "MISMATCHED"
    FAILED = "FAILED"
    REVOKED = "REVOKED"


class DriftState(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISMATCHED = "MISMATCHED"
    REVOKED = "REVOKED"
    UNKNOWN = "UNKNOWN"


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\s-]?){9,15}(?!\d)")
_FORBIDDEN_ACCOUNT_KEYS = frozenset({
    "password", "access_token", "refresh_token", "token", "cookie", "billing",
    "payment", "card", "iban", "account_number", "ssn", "private_key",
    "email", "phone", "phone_number",
})


def _reject_personal_or_secret(mapping: dict[str, Any], *, context: str) -> None:
    for k, v in (mapping or {}).items():
        lk = str(k).lower()
        if lk in _FORBIDDEN_ACCOUNT_KEYS or any(s in lk for s in ("secret", "token", "password", "cookie")):
            raise M35Error("forbidden_account_field", f"{context}:{lk}")
        if isinstance(v, str) and (_EMAIL_RE.search(v) or _PHONE_RE.search(v)):
            raise M35Error("raw_personal_identifier", f"{context}:{lk}")


@dataclass
class SandboxAccount:
    account_ref_id: str
    provider_id: str
    environment_class: str
    account_subject_fingerprint: str
    display_alias: str = ""
    declared_scopes: tuple[str, ...] = ()
    verified_scopes: tuple[str, ...] = ()
    capability_ceiling: dict[str, Any] = field(default_factory=dict)
    verification_state: str = AccountVerificationState.UNVERIFIED.value
    verified_at: str = ""
    expires_at: str = ""
    revoked_at: str = ""
    drift_state: str = DriftState.UNKNOWN.value
    metadata_safe: dict[str, Any] = field(default_factory=dict)

    def to_safe_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["declared_scopes"] = list(self.declared_scopes)
        d["verified_scopes"] = list(self.verified_scopes)
        d["schema"] = "m35.sandbox_account.v1"
        d["contains_secret_values"] = False
        return d

    def drift_fingerprint(self) -> str:
        material = {
            "provider": self.provider_id,
            "env": self.environment_class,
            "subject": self.account_subject_fingerprint,
            "scopes": sorted(self.declared_scopes),
            "ceiling": self.capability_ceiling,
        }
        return _hmac_hex(b"account_drift", json.dumps(material, sort_keys=True, default=str).encode())


class SandboxAccountRegistry:
    """Metadata-only sandbox account registry. Never stores raw subject identity,
    secrets, or financial data. Production accounts fail closed."""

    def __init__(self, *, clock: Optional[Callable[[], float]] = None):
        self._clock = clock or (lambda: 0.0)
        self._accounts: dict[str, SandboxAccount] = {}
        self._lock = threading.RLock()
        self._events: list[dict[str, Any]] = []
        self._seq = 0

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        self._events.append({
            "schema": "m35.account_event.v1", "event_type": event_type,
            "payload": payload, "privacy_safe": True, "contains_secret_values": False,
        })

    def _next_id(self, explicit: str = "") -> str:
        if explicit:
            return explicit
        self._seq += 1
        return f"acct_m35_{self._seq:04d}"

    def register_sandbox(
        self,
        *,
        provider_id: str,
        environment_class: str,
        subject: str,
        display_alias: str = "",
        declared_scopes: tuple[str, ...] = (),
        capability_ceiling: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
        account_ref_id: str = "",
    ) -> SandboxAccount:
        if not provider_id:
            raise M35Error("provider_required")
        if is_prohibited_provider(provider_id):
            raise M35Error("prohibited_provider", provider_id)
        env = assert_environment_allowed(environment_class)  # PRODUCTION fails here
        assert_scopes_allowed(tuple(declared_scopes))
        if display_alias and (_EMAIL_RE.search(display_alias) or _PHONE_RE.search(display_alias)):
            raise M35Error("raw_personal_identifier", "display_alias")
        _reject_personal_or_secret(metadata or {}, context="account_metadata")
        acct = SandboxAccount(
            account_ref_id=self._next_id(account_ref_id),
            provider_id=provider_id,
            environment_class=env,
            account_subject_fingerprint=subject_fingerprint(subject, provider_id=provider_id),
            display_alias=display_alias,
            declared_scopes=tuple(declared_scopes),
            capability_ceiling=capability_ceiling or {},
            verification_state=AccountVerificationState.UNVERIFIED.value,
            drift_state=DriftState.FRESH.value,
            metadata_safe=dict(metadata or {}),
        )
        with self._lock:
            self._accounts[acct.account_ref_id] = acct
        self._emit("account.sandbox_registered", {"account_ref_id": acct.account_ref_id, "provider_id": provider_id})
        return acct

    def get(self, account_ref_id: str) -> Optional[SandboxAccount]:
        return self._accounts.get(account_ref_id)

    def _require(self, account_ref_id: str) -> SandboxAccount:
        a = self._accounts.get(account_ref_id)
        if a is None:
            raise M35Error("unknown_account")
        return a

    def verify(
        self,
        account_ref_id: str,
        *,
        observed_scopes: Optional[tuple[str, ...]] = None,
        synthetic: bool = False,
        verified_at: str = "",
    ) -> SandboxAccount:
        a = self._require(account_ref_id)
        if a.verification_state == AccountVerificationState.REVOKED.value:
            raise M35Error("account_revoked")
        state, _detail = verify_scope_evidence(a.declared_scopes, observed_scopes, synthetic=synthetic)
        if state == ScopeVerificationState.VERIFIED.value:
            a.verification_state = (AccountVerificationState.SYNTHETIC_VERIFIED.value if synthetic
                                    else AccountVerificationState.VERIFIED.value)
            a.verified_scopes = tuple(observed_scopes) if observed_scopes is not None else tuple(a.declared_scopes)
        elif state == ScopeVerificationState.MISMATCHED.value:
            a.verification_state = AccountVerificationState.MISMATCHED.value
        else:
            a.verification_state = AccountVerificationState.FAILED.value
        a.verified_at = verified_at or str(int(self._clock()))
        a.drift_state = DriftState.FRESH.value
        self._emit("account.verified" if a.verification_state in (
            AccountVerificationState.VERIFIED.value, AccountVerificationState.SYNTHETIC_VERIFIED.value,
        ) else "account.verification_failed", {"account_ref_id": account_ref_id, "state": a.verification_state})
        return a

    def check_drift(self, account_ref_id: str, *, expected_fingerprint: str = "") -> dict[str, Any]:
        a = self._accounts.get(account_ref_id)
        if a is None:
            return {"account_ref_id": account_ref_id, "drift_state": DriftState.UNKNOWN.value, "drifted": True}
        if a.verification_state == AccountVerificationState.REVOKED.value:
            return {"account_ref_id": account_ref_id, "drift_state": DriftState.REVOKED.value, "drifted": True}
        current = a.drift_fingerprint()
        drifted = bool(expected_fingerprint) and expected_fingerprint != current
        return {
            "account_ref_id": account_ref_id,
            "drift_state": DriftState.MISMATCHED.value if drifted else DriftState.FRESH.value,
            "drifted": drifted, "current_fingerprint": current,
        }

    def mark_stale(self, account_ref_id: str) -> SandboxAccount:
        a = self._require(account_ref_id)
        a.drift_state = DriftState.STALE.value
        return a

    def revoke(self, account_ref_id: str, *, reason: str = "", revoked_at: str = "") -> SandboxAccount:
        a = self._require(account_ref_id)
        a.verification_state = AccountVerificationState.REVOKED.value
        a.drift_state = DriftState.REVOKED.value
        a.revoked_at = revoked_at or str(int(self._clock()))
        a.metadata_safe = {**a.metadata_safe, "revoke_reason": reason[:200]}
        self._emit("account.revoked", {"account_ref_id": account_ref_id, "reason": reason[:200]})
        return a

    def is_verified(self, account_ref_id: str) -> bool:
        a = self._accounts.get(account_ref_id)
        return bool(a and a.verification_state in (
            AccountVerificationState.VERIFIED.value, AccountVerificationState.SYNTHETIC_VERIFIED.value,
        ))

    def list_metadata(self) -> list[dict[str, Any]]:
        return [a.to_safe_dict() for a in self._accounts.values()]


# ── approval envelope ────────────────────────────────────────────────────────
_APPROVAL_ACKS = ("read_only_acknowledged", "sandbox_acknowledged",
                  "secret_access_acknowledged", "non_production_acknowledged")


@dataclass
class ApprovalEnvelope:
    approval_id: str
    purpose: str
    provider_id: str
    account_ref_id: str
    credential_ref_id: str
    operation: str
    environment_class: str
    approved_scopes: tuple[str, ...]
    approved_duration: float
    approved_uses: int
    read_only_acknowledged: bool
    sandbox_acknowledged: bool
    secret_access_acknowledged: bool
    non_production_acknowledged: bool
    write_prohibited: bool
    created_at: str = ""
    expires_at: str = ""
    status: str = "APPROVED"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["approved_scopes"] = list(self.approved_scopes)
        d["contains_secret_values"] = False
        return d

    def missing_acks(self) -> list[str]:
        return [a for a in _APPROVAL_ACKS if not getattr(self, a)]


def build_approval(
    *,
    purpose: str,
    provider_id: str,
    account_ref_id: str,
    credential_ref_id: str,
    operation: str,
    environment_class: str,
    approved_scopes: tuple[str, ...],
    approved_duration: float = M35_DEFAULT_LEASE_TTL_SEC,
    approved_uses: int = M35_DEFAULT_MAX_USES,
    read_only_acknowledged: bool = False,
    sandbox_acknowledged: bool = False,
    secret_access_acknowledged: bool = False,
    non_production_acknowledged: bool = False,
    write_prohibited: bool = True,
    created_at: str = "approval-time",
    approval_id: str = "appr_m35_0001",
) -> ApprovalEnvelope:
    """Build an explicit, bounded approval. Fail-closed on any missing element."""
    if not purpose:
        raise M35Error("missing_purpose")
    if not provider_id:
        raise M35Error("missing_provider")
    if not account_ref_id:
        raise M35Error("missing_account")
    if not credential_ref_id:
        raise M35Error("missing_credential")
    if not operation:
        raise M35Error("missing_operation")
    if not approved_scopes:
        raise M35Error("missing_scope")
    if not approved_duration or approved_duration <= 0:
        raise M35Error("missing_duration")
    if not approved_uses or approved_uses <= 0:
        raise M35Error("missing_uses")
    if not write_prohibited:
        raise M35Error("write_prohibition_required")
    env = assert_environment_allowed(environment_class)
    assert_scopes_allowed(tuple(approved_scopes))
    duration = min(float(approved_duration), M35_MAX_LEASE_TTL_SEC)
    a = ApprovalEnvelope(
        approval_id=approval_id, purpose=purpose, provider_id=provider_id,
        account_ref_id=account_ref_id, credential_ref_id=credential_ref_id,
        operation=operation, environment_class=env, approved_scopes=tuple(approved_scopes),
        approved_duration=duration, approved_uses=int(approved_uses),
        read_only_acknowledged=read_only_acknowledged, sandbox_acknowledged=sandbox_acknowledged,
        secret_access_acknowledged=secret_access_acknowledged,
        non_production_acknowledged=non_production_acknowledged, write_prohibited=write_prohibited,
        created_at=created_at,
    )
    missing = a.missing_acks()
    if missing:
        raise M35Error("missing_acknowledgement", ",".join(missing))
    return a


def approval_permits(
    approval: ApprovalEnvelope,
    *,
    provider_id: str,
    account_ref_id: str,
    operation: str,
    scopes: tuple[str, ...],
    now: Optional[float] = None,
) -> tuple[bool, str]:
    if approval.status == "REVOKED":
        return False, "approval_revoked"
    if approval.status == "EXPIRED":
        return False, "approval_expired"
    if approval.provider_id != provider_id:
        return False, "provider_mismatch"
    if approval.account_ref_id != account_ref_id:
        return False, "account_mismatch"
    if approval.operation != operation:
        return False, "operation_mismatch"
    if not set(scopes).issubset(set(approval.approved_scopes)):
        return False, "scope_mismatch"
    return True, "ok"


# ── session leases (compose M31 lease semantics; add uses/session binding) ────
class SessionLeaseStatus(str, Enum):
    ISSUED = "ISSUED"
    CONSUMED = "CONSUMED"
    EXHAUSTED = "EXHAUSTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    INVALID = "INVALID"


@dataclass
class SessionLease:
    lease_id: str
    credential_ref_id: str
    account_ref_id: str
    provider_id: str
    operation: str
    approved_scopes: tuple[str, ...]
    issued_at: float
    expires_at: float
    max_uses: int
    uses_remaining: int
    session_id: str
    approval_id: str
    status: str = SessionLeaseStatus.ISSUED.value
    revocation_reason: str = ""

    def to_safe_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["approved_scopes"] = list(self.approved_scopes)
        d["contains_secret_values"] = False
        return d


class SessionLeaseError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class SessionLeaseStore:
    """M35 lease store: bounded duration + use count, session/approval bound.
    Delegates nothing about secret material — retrieval stays in the M31 broker."""

    def __init__(self, *, clock: Optional[Callable[[], float]] = None):
        self._clock = clock or (lambda: 0.0)
        self._leases: dict[str, SessionLease] = {}
        self._lock = threading.RLock()
        self._seq = 0

    def _next_id(self, explicit: str = "") -> str:
        if explicit:
            return explicit
        self._seq += 1
        return f"lease_m35_{self._seq:04d}"

    def issue(
        self,
        *,
        credential_ref_id: str,
        account_ref_id: str,
        provider_id: str,
        operation: str,
        approved_scopes: tuple[str, ...],
        session_id: str,
        approval_id: str,
        ttl_seconds: float,
        max_uses: int,
        credential_expires_at: Optional[float] = None,
        approval_expires_at: Optional[float] = None,
        lease_id: str = "",
    ) -> SessionLease:
        if ttl_seconds <= 0:
            raise SessionLeaseError("invalid_duration")
        if max_uses <= 0:
            raise SessionLeaseError("invalid_uses")
        now = float(self._clock())
        ttl = min(float(ttl_seconds), M35_MAX_LEASE_TTL_SEC)
        expires = now + ttl
        if credential_expires_at is not None:
            expires = min(expires, float(credential_expires_at))
        if approval_expires_at is not None:
            expires = min(expires, float(approval_expires_at))
        if expires <= now:
            raise SessionLeaseError("lease_would_be_expired")
        lease = SessionLease(
            lease_id=self._next_id(lease_id), credential_ref_id=credential_ref_id,
            account_ref_id=account_ref_id, provider_id=provider_id, operation=operation,
            approved_scopes=tuple(approved_scopes), issued_at=now, expires_at=expires,
            max_uses=int(max_uses), uses_remaining=int(max_uses),
            session_id=session_id, approval_id=approval_id,
        )
        with self._lock:
            self._leases[lease.lease_id] = lease
        return lease

    def get(self, lease_id: str) -> Optional[SessionLease]:
        return self._leases.get(lease_id)

    def peek(self, lease_id: str) -> dict[str, Any]:
        """Non-consuming read — never decrements uses."""
        lease = self._leases.get(lease_id)
        if lease is None:
            return {"valid": False, "reason": "lease_not_found"}
        now = float(self._clock())
        expired = now > lease.expires_at
        return {
            "valid": lease.status == SessionLeaseStatus.ISSUED.value and not expired and lease.uses_remaining > 0,
            "status": lease.status, "uses_remaining": lease.uses_remaining, "expired": expired,
        }

    def consume(
        self,
        lease_id: str,
        *,
        credential_ref_id: str,
        account_ref_id: str,
        provider_id: str,
        operation: str,
        session_id: str,
        requested_scopes: tuple[str, ...] = (),
    ) -> SessionLease:
        with self._lock:
            lease = self._leases.get(lease_id)
            if lease is None:
                raise SessionLeaseError("lease_not_found")
            now = float(self._clock())
            if lease.status == SessionLeaseStatus.REVOKED.value:
                raise SessionLeaseError("lease_revoked")
            if lease.status in (SessionLeaseStatus.CONSUMED.value, SessionLeaseStatus.EXHAUSTED.value):
                raise SessionLeaseError("lease_exhausted")
            if now > lease.expires_at:
                lease.status = SessionLeaseStatus.EXPIRED.value
                raise SessionLeaseError("lease_expired")
            if lease.credential_ref_id != credential_ref_id:
                raise SessionLeaseError("credential_mismatch")
            if lease.account_ref_id != account_ref_id:
                raise SessionLeaseError("account_mismatch")
            if lease.provider_id != provider_id:
                raise SessionLeaseError("provider_mismatch")
            if lease.operation != operation:
                raise SessionLeaseError("operation_mismatch")
            if lease.session_id != session_id:
                raise SessionLeaseError("session_mismatch")
            if requested_scopes and not set(requested_scopes).issubset(set(lease.approved_scopes)):
                raise SessionLeaseError("scope_broadening")
            if lease.uses_remaining <= 0:
                lease.status = SessionLeaseStatus.EXHAUSTED.value
                raise SessionLeaseError("lease_exhausted")
            lease.uses_remaining -= 1
            if lease.uses_remaining == 0:
                lease.status = SessionLeaseStatus.EXHAUSTED.value
            return lease

    def revoke(self, lease_id: str, *, reason: str = "") -> None:
        with self._lock:
            lease = self._leases.get(lease_id)
            if lease:
                lease.status = SessionLeaseStatus.REVOKED.value
                lease.revocation_reason = reason[:200]

    def revoke_for_credential(self, credential_ref_id: str) -> int:
        n = 0
        with self._lock:
            for lease in self._leases.values():
                if lease.credential_ref_id == credential_ref_id and lease.status == SessionLeaseStatus.ISSUED.value:
                    lease.status = SessionLeaseStatus.REVOKED.value
                    n += 1
        return n


# ── credential health (metadata-only) ────────────────────────────────────────
class CredentialHealthState(str, Enum):
    HEALTHY = "HEALTHY"
    EXPIRING = "EXPIRING"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    ACCOUNT_MISMATCH = "ACCOUNT_MISMATCH"
    PROVIDER_MISMATCH = "PROVIDER_MISMATCH"
    SECRET_SOURCE_UNAVAILABLE = "SECRET_SOURCE_UNAVAILABLE"
    ROTATION_REQUIRED = "ROTATION_REQUIRED"
    QUARANTINED = "QUARANTINED"
    UNKNOWN = "UNKNOWN"


def credential_health(
    ref: Any,
    *,
    expected_provider_id: str = "",
    expected_account_ref_id: str = "",
    now: float = 0.0,
    expires_at: Optional[float] = None,
    expiring_window: float = 60.0,
    secret_source_available: bool = True,
) -> dict[str, Any]:
    """Metadata-only health. Never retrieves a secret, consumes a lease, contacts
    a provider, or mutates verification timestamps."""
    if ref is None:
        return {"state": CredentialHealthState.UNKNOWN.value, "reason": "unknown_credential"}
    status = getattr(ref, "status", "")
    if status == CredentialStatus.REVOKED.value or status == CredentialStatus.DELETED.value:
        return {"state": CredentialHealthState.REVOKED.value, "reason": "revoked"}
    if status == CredentialStatus.QUARANTINED.value:
        return {"state": CredentialHealthState.QUARANTINED.value, "reason": "quarantined"}
    if status == CredentialStatus.ROTATION_REQUIRED.value:
        return {"state": CredentialHealthState.ROTATION_REQUIRED.value, "reason": "rotation_required"}
    if status == CredentialStatus.EXPIRED.value:
        return {"state": CredentialHealthState.EXPIRED.value, "reason": "expired"}
    if not secret_source_available:
        return {"state": CredentialHealthState.SECRET_SOURCE_UNAVAILABLE.value, "reason": "secret_source_unavailable"}
    if expected_provider_id and getattr(ref, "provider_id", "") != expected_provider_id:
        return {"state": CredentialHealthState.PROVIDER_MISMATCH.value, "reason": "provider_mismatch"}
    if expected_account_ref_id and getattr(ref, "account_link_id", "") not in ("", expected_account_ref_id):
        return {"state": CredentialHealthState.ACCOUNT_MISMATCH.value, "reason": "account_mismatch"}
    if expires_at is not None:
        if now >= expires_at:
            return {"state": CredentialHealthState.EXPIRED.value, "reason": "expired"}
        if expires_at - now <= expiring_window:
            return {"state": CredentialHealthState.EXPIRING.value, "reason": "expiring_soon"}
    return {"state": CredentialHealthState.HEALTHY.value, "reason": "ok"}


# ── credential drift ─────────────────────────────────────────────────────────
def credential_drift_fingerprint(
    *,
    provider_id: str,
    environment_class: str,
    credential_type: str,
    secret_source: str,
    scopes: tuple[str, ...],
    capability_ceiling: dict[str, Any],
    account_ref_id: str = "",
    adapter_version: str = "",
    policy_version: str = SCHEMA_VERSION,
) -> str:
    material = {
        "provider": provider_id, "env": environment_class, "type": credential_type,
        "source": secret_source, "scopes": sorted(scopes), "ceiling": capability_ceiling,
        "account": account_ref_id, "adapter": adapter_version, "policy": policy_version,
    }
    return _hmac_hex(b"credential_drift", json.dumps(material, sort_keys=True, default=str).encode())


def check_credential_drift(*, current_fingerprint: str, expected_fingerprint: str, revoked: bool = False) -> dict[str, Any]:
    if revoked:
        return {"drift_state": DriftState.REVOKED.value, "drifted": True}
    if not expected_fingerprint or not current_fingerprint:
        return {"drift_state": DriftState.UNKNOWN.value, "drifted": True}
    drifted = current_fingerprint != expected_fingerprint
    return {
        "drift_state": DriftState.MISMATCHED.value if drifted else DriftState.FRESH.value,
        "drifted": drifted,
    }


# ── rotation guard ───────────────────────────────────────────────────────────
def validate_rotation(
    *,
    old_provider_id: str,
    new_provider_id: str,
    old_account_ref_id: str,
    new_account_ref_id: str,
    old_environment: str,
    new_environment: str,
    old_scopes: tuple[str, ...],
    new_scopes: tuple[str, ...],
    old_fingerprint: str,
    new_fingerprint: str,
    new_expires_at: Optional[float] = None,
    now: float = 0.0,
    new_valid: bool = True,
) -> tuple[bool, str]:
    """Guard a rotation. Fail-closed on same-secret reuse, mismatch, broadening,
    or an invalid/expired replacement."""
    if new_fingerprint and old_fingerprint and new_fingerprint == old_fingerprint:
        return False, "same_secret_reuse"
    if new_provider_id != old_provider_id:
        return False, "provider_mismatch"
    if new_account_ref_id != old_account_ref_id:
        return False, "account_mismatch"
    if classify_environment(new_environment) != classify_environment(old_environment):
        return False, "environment_mismatch"
    if set(new_scopes) - set(old_scopes):
        return False, "scope_broadening"
    if not new_valid:
        return False, "invalid_replacement"
    if new_expires_at is not None and now >= new_expires_at:
        return False, "expired_replacement"
    return True, "ok"


# ── sandbox-session certification ────────────────────────────────────────────
class SandboxCertificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    SYNTHETIC_VERIFIED = "SYNTHETIC_VERIFIED"
    SANDBOX_GOVERNANCE_VERIFIED = "SANDBOX_GOVERNANCE_VERIFIED"
    SANDBOX_SESSION_CERTIFIED = "SANDBOX_SESSION_CERTIFIED"  # requires real cred+account — never claimed offline
    STALE = "STALE"
    REVOKED = "REVOKED"
    FAILED = "FAILED"


# Maximum state reachable without a real sandbox credential + live sandbox account.
M35_MAX_CERTIFICATION_STATE = SandboxCertificationState.SANDBOX_GOVERNANCE_VERIFIED.value


def assess_sandbox_certification(
    *,
    governance_ok: bool,
    synthetic_session_ok: bool,
    real_credential_loaded: bool = False,
    real_account_linked: bool = False,
    revoked: bool = False,
    fresh: bool = True,
) -> tuple[str, list[str]]:
    """Certification is capped at SANDBOX_GOVERNANCE_VERIFIED offline. The certified
    state is never claimed without a real credential and a real sandbox account."""
    limitations = [
        "synthetic_credentials_only", "no_live_secret_source", "no_real_sandbox_account",
        "no_oauth", "no_live_provider_session", "no_write_authority",
    ]
    if revoked:
        return SandboxCertificationState.REVOKED.value, limitations
    if not governance_ok:
        return SandboxCertificationState.FAILED.value, limitations
    if not fresh:
        return SandboxCertificationState.STALE.value, limitations
    if real_credential_loaded and real_account_linked and synthetic_session_ok:
        # Would be SANDBOX_SESSION_CERTIFIED — but this path is operator-only and
        # never reached offline. Cap defensively.
        return M35_MAX_CERTIFICATION_STATE, limitations
    if synthetic_session_ok:
        return SandboxCertificationState.SANDBOX_GOVERNANCE_VERIFIED.value, limitations
    return SandboxCertificationState.SYNTHETIC_VERIFIED.value, limitations


# ── read-only session lifecycle ──────────────────────────────────────────────
class SessionState(str, Enum):
    REQUESTED = "REQUESTED"
    AUTHORIZED = "AUTHORIZED"
    LEASED = "LEASED"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


@dataclass
class ReadOnlySession:
    session_id: str
    provider_id: str
    operation: str
    credential_ref_id: str
    account_ref_id: str
    lease_id: str = ""
    approval_id: str = ""
    environment_class: str = ""
    verified_scopes: tuple[str, ...] = ()
    capability_ceiling: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    deadline: str = ""
    ended_at: str = ""
    status: str = SessionState.REQUESTED.value
    safe_result_classification: str = ""

    def to_safe_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["verified_scopes"] = list(self.verified_scopes)
        d["schema"] = "m35.read_only_session.v1"
        d["contains_secret_values"] = False
        return d


NON_PRODUCTION_LABEL = (
    "SANDBOX GOVERNANCE — NON-PRODUCTION — NO LIVE SECRET LOADED — "
    "NO EXTERNAL CALL — NO WRITE AUTHORITY — ROLLOUT REMAINS OFF"
)


def run_sandbox_session(
    *,
    provider_id: str,
    profile: Any,
    account_registry: SandboxAccountRegistry,
    account_ref_id: str,
    broker: CredentialBroker,
    credential_ref_id: str,
    approval: ApprovalEnvelope,
    lease_store: SessionLeaseStore,
    environment_class: str,
    requested_scopes: tuple[str, ...],
    observed_scopes: Optional[tuple[str, ...]] = None,
    synthetic: bool = True,
    connector_id: str = "gov.http",
    session_id: str = "sess_m35_0001",
    clock: Optional[Callable[[], float]] = None,
) -> dict[str, Any]:
    """Drive one bounded, read-only synthetic session end-to-end, OFFLINE.

    authorize → verify account → verify scope → issue lease → retrieve secret
    (into a SecretHandle) → derive fingerprint → compose eligibility → bounded
    session → release secret → consume lease → end → sanitized result.

    Never performs a network call, a write, or a rollout change.
    """
    clk = clock or (lambda: 0.0)
    session = ReadOnlySession(
        session_id=session_id, provider_id=provider_id, operation=profile.operation,
        credential_ref_id=credential_ref_id, account_ref_id=account_ref_id,
        approval_id=approval.approval_id, environment_class="", status=SessionState.REQUESTED.value,
    )
    blockers: list[str] = []

    def _fail(reason: str, state: str = SessionState.FAILED.value) -> dict[str, Any]:
        session.status = state
        return _session_result(session, ok=False, reason=reason, blockers=blockers or [reason],
                               secret_fingerprint="", handle_closed=True)

    # 1. environment ceiling (PRODUCTION fails closed)
    try:
        env = assert_environment_allowed(environment_class)
    except M35Error as e:
        blockers.append(e.code)
        return _fail(e.code, SessionState.ABORTED.value)
    session.environment_class = env

    # 2. provider / method read-only ceiling
    if is_prohibited_provider(provider_id) or provider_id != profile.provider_id:
        return _fail("provider_invalid", SessionState.ABORTED.value)
    if (profile.method or "").upper() in _WRITE_METHODS:
        return _fail("write_method_blocked", SessionState.ABORTED.value)

    # 3. approval must permit this exact request
    ok, reason = approval_permits(
        approval, provider_id=provider_id, account_ref_id=account_ref_id,
        operation=profile.operation, scopes=requested_scopes,
    )
    if not ok:
        return _fail(f"approval:{reason}", SessionState.ABORTED.value)
    session.status = SessionState.AUTHORIZED.value

    # 4. verify account + scope
    acct = account_registry.get(account_ref_id)
    if acct is None or not account_registry.is_verified(account_ref_id):
        return _fail("account_not_verified")
    scope_state, _sd = verify_scope_evidence(requested_scopes, observed_scopes, synthetic=synthetic)
    if scope_state != ScopeVerificationState.VERIFIED.value:
        return _fail(f"scope_not_verified:{scope_state}")
    session.verified_scopes = tuple(observed_scopes) if observed_scopes is not None else tuple(requested_scopes)

    # 5. compose the capability ceiling and check the request is a subset
    ceiling = ceiling_from_profile(profile, environment_class=env, allowed_scopes=requested_scopes)
    session.capability_ceiling = ceiling.to_dict()
    within, why = request_within_ceiling({
        "provider_id": provider_id, "operation": profile.operation, "method": (profile.method or "").upper(),
        "side_effect_class": profile.side_effect_class, "data_classification": profile.data_classification,
        "environment_class": env, "scopes": requested_scopes,
    }, ceiling)
    if not within:
        return _fail(f"ceiling:{why}", SessionState.ABORTED.value)

    # 6. issue the session lease
    ref = broker.get_ref(credential_ref_id)
    if ref is None:
        return _fail("unknown_credential", SessionState.ABORTED.value)
    if ref.status != CredentialStatus.ACTIVE.value:
        return _fail(f"credential_{ref.status.lower()}", SessionState.ABORTED.value)
    try:
        lease = lease_store.issue(
            credential_ref_id=credential_ref_id, account_ref_id=account_ref_id,
            provider_id=provider_id, operation=profile.operation, approved_scopes=approval.approved_scopes,
            session_id=session_id, approval_id=approval.approval_id,
            ttl_seconds=approval.approved_duration, max_uses=approval.approved_uses,
        )
    except SessionLeaseError as e:
        return _fail(f"lease:{e.code}")
    session.lease_id = lease.lease_id
    session.status = SessionState.LEASED.value

    # 7. retrieve the secret through the M31 broker into a bounded handle
    handle: Optional[SecretHandle] = None
    secret_fp = ""
    try:
        m31_lease = broker.issue_lease(
            credential_ref_id=credential_ref_id, request_id=session_id, connector_id=connector_id,
            operation=profile.operation, actor="m35_session", owner_scope=ref.owner_scope,
        )
        secrets = broker.inject_secrets(
            lease_id=m31_lease["lease_id"], credential_ref_id=credential_ref_id, request_id=session_id,
            connector_id=connector_id, operation=profile.operation,
        )
        handle = SecretHandle(secrets, session_id=session_id, lease_id=lease.lease_id,
                              provider_id=provider_id, account_ref_id=account_ref_id)
        secret_fp = m35_secret_fingerprint(
            {k: handle.use(k, lambda v: v, session_id=session_id) for k in handle.field_names},
            provider_id=provider_id, account_ref_id=account_ref_id,
        )
        session.status = SessionState.READY.value

        # 8. consume the M35 session lease (this is where a provider call WOULD happen)
        lease_store.consume(
            lease.lease_id, credential_ref_id=credential_ref_id, account_ref_id=account_ref_id,
            provider_id=provider_id, operation=profile.operation, session_id=session_id,
            requested_scopes=requested_scopes,
        )
        session.status = SessionState.RUNNING.value
        # NO NETWORK CALL. The read-only operation is simulated as a no-op.
        session.safe_result_classification = "SANDBOX_READ_ONLY_SIMULATED"
        session.status = SessionState.COMPLETED.value
    except (SessionLeaseError, Exception) as e:  # fail-closed; secret still released
        code = getattr(e, "code", type(e).__name__)
        blockers.append(str(code))
        return _finalize(session, handle, ok=False, reason=str(code), blockers=blockers, secret_fingerprint=secret_fp)
    finally:
        if handle is not None:
            handle.close()

    return _finalize(session, handle, ok=True, reason="ok", blockers=[], secret_fingerprint=secret_fp)


def _finalize(session: ReadOnlySession, handle: Optional[SecretHandle], *, ok: bool, reason: str,
              blockers: list[str], secret_fingerprint: str) -> dict[str, Any]:
    handle_closed = handle is None or not handle._open  # noqa: SLF001 (internal check)
    return _session_result(session, ok=ok, reason=reason, blockers=blockers,
                           secret_fingerprint=secret_fingerprint, handle_closed=handle_closed)


def _session_result(session: ReadOnlySession, *, ok: bool, reason: str, blockers: list[str],
                    secret_fingerprint: str, handle_closed: bool) -> dict[str, Any]:
    return {
        "schema": "m35.session_result.v1",
        "ok": ok,
        "reason": reason,
        "blockers": blockers,
        "session": session.to_safe_dict(),
        "session_state": session.status,
        "credential_fingerprint": secret_fingerprint,   # non-reversible; may be "" on failure
        "handle_closed": handle_closed,
        "external_calls": 0,
        "external_writes": 0,
        "label": NON_PRODUCTION_LABEL,
        "rollout_state": {"connector": "OFF", "provider": "OFF", "inference": "OFF",
                          "canary_providers": 0, "active_providers": 0},
        "trading_guardian": "UNCHANGED / UNENGAGED",
        "privacy_safe": True,
        "contains_secret_values": False,
    }


# ── composed eligibility (metadata only; non-mutating) ───────────────────────
def compose_session_eligibility(
    *,
    production_certified: bool,
    connector_certified: bool,
    provider_simulation_fresh: bool,
    external_profile_fresh: bool,
    credential_valid: bool,
    secret_source_ready: bool,
    environment_class: str,
    account_verified: bool,
    scope_verified: bool,
    within_ceiling: bool,
    credential_healthy: bool,
    lease_valid: bool,
    approval_valid: bool,
    provider_healthy: bool,
    quarantined: bool,
    rollout_off: bool,
) -> tuple[bool, list[str]]:
    """AND every governance gate. Real sandbox session stays blocked; provider
    rollout stays OFF. Fail-closed on any denial. Does not mutate any state."""
    blockers: list[str] = []
    try:
        env = assert_environment_allowed(environment_class)
    except M35Error as e:
        return False, [e.code]
    checks = [
        (production_certified, "production_not_certified"),
        (connector_certified, "connector_not_certified"),
        (provider_simulation_fresh, "provider_simulation_stale"),
        (external_profile_fresh, "external_profile_stale"),
        (credential_valid, "credential_invalid"),
        (secret_source_ready, "secret_source_not_ready"),
        (account_verified, "account_not_verified"),
        (scope_verified, "scope_not_verified"),
        (within_ceiling, "request_exceeds_ceiling"),
        (credential_healthy, "credential_unhealthy"),
        (lease_valid, "lease_invalid"),
        (approval_valid, "approval_invalid"),
        (provider_healthy, "provider_unhealthy"),
        (not quarantined, "provider_quarantined"),
        (rollout_off, "rollout_not_off"),
    ]
    for ok, code in checks:
        if not ok:
            blockers.append(code)
    allowed = not blockers and env in _ALLOWED_ENVIRONMENTS
    return allowed, blockers


# ── deterministic milestone fingerprint ──────────────────────────────────────
def compute_m35_fingerprint(profile: Any) -> str:
    """Deterministic surface fingerprint for M35 governance (drift anchor)."""
    material = {
        "schema": SCHEMA_VERSION,
        "provider": profile.provider_id,
        "operation": profile.operation,
        "method": (profile.method or "").upper(),
        "allowed_env": sorted(_ALLOWED_ENVIRONMENTS),
        "retrievable_sources": sorted(_RETRIEVABLE_SOURCES),
        "allowed_scope_classes": sorted(ALLOWED_SCOPE_CLASSES),
        "forbidden_scope_classes": sorted(FORBIDDEN_SCOPE_CLASSES),
        "max_certification": M35_MAX_CERTIFICATION_STATE,
    }
    return _hmac_hex(b"m35_surface", json.dumps(material, sort_keys=True).encode(), length=64)


# ── evidence writer (leak-scanned, atomic — via M32 write_evidence) ──────────
def write_m35_evidence(bodies: dict[str, dict[str, Any]], *, evidence_dir: str = "docs/evidence/m35") -> list[str]:
    """Write the M35 evidence set. Every body is leak-scanned before write."""
    from saathi.connectors.providers.evidence import write_evidence

    d = Path(evidence_dir)
    written: list[str] = []
    for name, body in bodies.items():
        # defence in depth — refuse to write secret-shaped material
        assert_clean(body, context=f"m35.evidence:{name}")
        written.append(write_evidence(name, body, evidence_dir=d, schema=f"m35.{name}.v1"))
    return written


def validation_summary_body(*, session_result: dict[str, Any], certification: str) -> dict[str, Any]:
    return {
        "milestone": "M35",
        "production_credentials_loaded": 0,
        "production_oauth_flows": 0,
        "production_accounts_linked": 0,
        "real_sandbox_credentials_loaded": 0,
        "real_sandbox_oauth_flows": 0,
        "real_sandbox_accounts_linked": 0,
        "synthetic_credentials_used": 1,
        "credentials_committed_to_git": 0,
        "raw_secrets_in_evidence": 0,
        "raw_secrets_in_logs": 0,
        "raw_secrets_in_events": 0,
        "external_network_calls": session_result.get("external_calls", 0),
        "external_provider_writes": session_result.get("external_writes", 0),
        "financial_provider_calls": 0,
        "trading_provider_calls": 0,
        "connector_rollout": "OFF",
        "provider_rollout": "OFF",
        "inference_rollout": "OFF",
        "canary_providers": 0,
        "active_providers": 0,
        "sandbox_certification": certification,
        "max_certification_state": M35_MAX_CERTIFICATION_STATE,
        "real_sandbox_session": "NOT_EXERCISED",
        "trading_guardian": "UNCHANGED / UNENGAGED",
    }
