"""M51 provider-neutral identity contract + local-alpha authentication.

Can later be replaced by a production IdP without replacing platform users,
memberships, RBAC, sessions, approvals, or audit.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AuthenticationMethod(str, Enum):
    LOCAL_PASSWORD = "LOCAL_PASSWORD"
    LOCAL_MAGIC_CODE_FIXTURE = "LOCAL_MAGIC_CODE_FIXTURE"
    DEVELOPMENT_BOOTSTRAP = "DEVELOPMENT_BOOTSTRAP"
    # Future production (not implemented in M51):
    # EXTERNAL_OIDC = "EXTERNAL_OIDC"


class IdentityProviderKind(str, Enum):
    LOCAL = "local"
    EXTERNAL = "external"  # reserved for production IdP adapters


@dataclass
class IdentityAssertion:
    """Normalized identity claim after successful authentication."""

    subject: str  # stable local user_id or external subject
    email: str = ""
    display_name: str = ""
    method: str = AuthenticationMethod.LOCAL_PASSWORD.value
    provider: str = IdentityProviderKind.LOCAL.value
    external_subject: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class CredentialVerificationResult:
    ok: bool
    reason: str = ""
    needs_password_reset: bool = False
    user_id: str = ""


@dataclass
class AuthenticationResult:
    ok: bool
    assertion: IdentityAssertion | None = None
    reason: str = "auth_failed"  # always generic to callers
    internal_reason: str = ""


# ── password hashing: scrypt (stdlib; no new dependency) ──────────────────
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_MIN_PASSWORD_LEN = 12

_TRIVIAL = frozenset(
    {
        "password",
        "password123",
        "password1234",
        "123456789012",
        "qwertyuiop12",
        "letmein12345",
        "adminadmin12",
        "changeme1234",
        "saathi123456",
        "privatealpha1",
    }
)


def hash_password_scrypt(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=bytes.fromhex(salt),
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt}${dk.hex()}"


def verify_password_scrypt(password: str, stored: str) -> bool:
    if not stored or not password:
        return False
    try:
        if stored.startswith("scrypt$"):
            _, n, r, p, salt, want = stored.split("$")
            dk = hashlib.scrypt(
                password.encode("utf-8"),
                salt=bytes.fromhex(salt),
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=_SCRYPT_DKLEN,
            )
            return hmac.compare_digest(dk.hex(), want)
        # Accept existing authsec PBKDF2 for migration compatibility
        if stored.startswith("pbkdf2$"):
            from saathi.authsec import verify_password

            return verify_password(password, stored)
    except Exception:
        return False
    return False


def password_policy_check(password: str) -> tuple[bool, str]:
    if not password or len(password) < _MIN_PASSWORD_LEN:
        return False, "password_too_short"
    if password.lower() in _TRIVIAL:
        return False, "password_trivial"
    if password.isdigit() or password.isalpha():
        return False, "password_complexity"
    classes = 0
    if re.search(r"[a-z]", password):
        classes += 1
    if re.search(r"[A-Z]", password):
        classes += 1
    if re.search(r"\d", password):
        classes += 1
    if re.search(r"[^A-Za-z0-9]", password):
        classes += 1
    if classes < 3:
        return False, "password_complexity"
    return True, "ok"


class IdentityProvider(ABC):
    """Provider-neutral authentication surface."""

    kind: IdentityProviderKind = IdentityProviderKind.LOCAL

    @abstractmethod
    def authenticate(self, **credentials: Any) -> AuthenticationResult:
        ...

    @abstractmethod
    def method_supported(self) -> list[AuthenticationMethod]:
        ...


class LocalAlphaIdentityProvider(IdentityProvider):
    """LOCAL_PASSWORD / MAGIC_CODE_FIXTURE / DEVELOPMENT_BOOTSTRAP.

    Password verification delegates to a credential store callback so the
    PlatformStore remains the single user store.
    """

    kind = IdentityProviderKind.LOCAL

    def __init__(
        self,
        *,
        get_credential,
        get_user_by_email,
        magic_code_verifier=None,
    ):
        self._get_credential = get_credential
        self._get_user_by_email = get_user_by_email
        self._magic_code_verifier = magic_code_verifier

    def method_supported(self) -> list[AuthenticationMethod]:
        return [
            AuthenticationMethod.LOCAL_PASSWORD,
            AuthenticationMethod.LOCAL_MAGIC_CODE_FIXTURE,
            AuthenticationMethod.DEVELOPMENT_BOOTSTRAP,
        ]

    def authenticate(self, **credentials: Any) -> AuthenticationResult:
        method = str(credentials.get("method") or AuthenticationMethod.LOCAL_PASSWORD.value)
        email = str(credentials.get("email") or "").strip().lower()
        if method == AuthenticationMethod.LOCAL_PASSWORD.value:
            return self._auth_password(email, str(credentials.get("password") or ""))
        if method == AuthenticationMethod.LOCAL_MAGIC_CODE_FIXTURE.value:
            return self._auth_magic(email, str(credentials.get("code") or ""))
        if method == AuthenticationMethod.DEVELOPMENT_BOOTSTRAP.value:
            # Only valid when explicitly flagged by service for empty-store bootstrap
            if not credentials.get("bootstrap_authorized"):
                return AuthenticationResult(
                    ok=False, reason="auth_failed", internal_reason="bootstrap_denied"
                )
            user = self._get_user_by_email(email)
            if not user:
                return AuthenticationResult(
                    ok=False, reason="auth_failed", internal_reason="user_missing"
                )
            return AuthenticationResult(
                ok=True,
                assertion=IdentityAssertion(
                    subject=user.user_id,
                    email=user.email,
                    display_name=user.name,
                    method=AuthenticationMethod.DEVELOPMENT_BOOTSTRAP.value,
                ),
            )
        return AuthenticationResult(
            ok=False, reason="auth_failed", internal_reason="method_unsupported"
        )

    def _auth_password(self, email: str, password: str) -> AuthenticationResult:
        user = self._get_user_by_email(email) if email else None
        # Generic failure — do not disclose existence
        fail = AuthenticationResult(
            ok=False, reason="auth_failed", internal_reason="bad_credentials"
        )
        if not user or user.status != "active":
            # burn time approximately
            verify_password_scrypt(password or "x", hash_password_scrypt("dummy-check"))
            return fail
        cred = self._get_credential(user.user_id)
        if not cred or not cred.get("password_hash"):
            return fail
        if not verify_password_scrypt(password, cred["password_hash"]):
            return fail
        return AuthenticationResult(
            ok=True,
            assertion=IdentityAssertion(
                subject=user.user_id,
                email=user.email,
                display_name=user.name,
                method=AuthenticationMethod.LOCAL_PASSWORD.value,
            ),
            internal_reason="ok",
        )

    def _auth_magic(self, email: str, code: str) -> AuthenticationResult:
        fail = AuthenticationResult(
            ok=False, reason="auth_failed", internal_reason="bad_magic"
        )
        if not self._magic_code_verifier:
            return fail
        user = self._get_user_by_email(email) if email else None
        if not user or not self._magic_code_verifier(user.user_id, code):
            return fail
        return AuthenticationResult(
            ok=True,
            assertion=IdentityAssertion(
                subject=user.user_id,
                email=user.email,
                display_name=user.name,
                method=AuthenticationMethod.LOCAL_MAGIC_CODE_FIXTURE.value,
            ),
        )


def hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_recovery_code() -> str:
    """PRIVATE_ALPHA_ONLY / NOT_PRODUCTION_RECOVERY — local fixture code."""
    return f"PA-REC-{secrets.token_hex(8).upper()}"
