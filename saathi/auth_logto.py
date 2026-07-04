"""Logto authentication & authorization (Stage 2) — JWT / RBAC / Organizations.

The CEO Gateway is protected by verifying Logto-issued access tokens against
Logto's JWKS (RS256), checking issuer + audience (the API resource indicator),
and enforcing RBAC via the ``scope`` claim. Organization-scoped tokens carry an
``organization_id`` claim (audience ``urn:logto:organization:<id>``).

Env-gated: inert until ``LOGTO_ENDPOINT`` is set, so existing token/session auth
keeps working. When configured, a valid Bearer JWT becomes an accepted identity.

Contract (per Logto docs):
  JWKS      = {LOGTO_ENDPOINT}/oidc/jwks
  issuer    = {LOGTO_ENDPOINT}/oidc
  audience  = LOGTO_API_RESOURCE   (your API resource indicator)
  scopes    = space-separated ``scope`` claim
  org       = ``organization_id`` claim

Deterministic core (AP-17): verification takes an injectable key resolver, so
tests run with a local RSA key and never touch the network (AP-12).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import jwt


def _endpoint() -> str:
    return os.getenv("LOGTO_ENDPOINT", "").rstrip("/")


def enabled() -> bool:
    return bool(_endpoint())


def issuer() -> str:
    return f"{_endpoint()}/oidc"


def jwks_url() -> str:
    return f"{_endpoint()}/oidc/jwks"


def api_resource() -> str | None:
    return os.getenv("LOGTO_API_RESOURCE") or None


class AuthError(Exception):
    """Raised when a token is missing/invalid/insufficient."""


@dataclass
class Principal:
    subject: str
    scopes: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    organization_id: str | None = None
    claims: dict = field(default_factory=dict)

    def has_scopes(self, required: list[str]) -> bool:
        s = set(self.scopes)
        return all(scope in s for scope in required)


def bearer_from_header(authorization: str | None) -> str:
    if not authorization:
        raise AuthError("authorization header missing")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise AuthError("expected Bearer token")
    return authorization[len(prefix):].strip()


# lazy JWKS client (network) — replaced in tests by a fake resolver
_jwk_client = None
def _signing_key(token: str):
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = jwt.PyJWKClient(jwks_url())
    return _jwk_client.get_signing_key_from_jwt(token).key


def verify_access_token(token: str, *, key_resolver=None,
                        expected_issuer: str | None = None,
                        expected_audience: str | None = None) -> Principal:
    """Verify a Logto access token and return the Principal. Raises AuthError."""
    resolver = key_resolver or _signing_key
    iss = expected_issuer if expected_issuer is not None else issuer()
    aud = expected_audience if expected_audience is not None else api_resource()
    try:
        key = resolver(token)
        options = {"require": ["exp", "iss", "sub"]}
        payload = jwt.decode(
            token, key, algorithms=["RS256"], issuer=iss,
            audience=aud if aud else None,
            options={**options, "verify_aud": bool(aud)})
    except AuthError:
        raise
    except Exception as exc:  # signature / exp / iss / aud failures
        raise AuthError(f"token verification failed: {exc}") from exc

    scopes = payload.get("scope", "").split() if payload.get("scope") else []
    roles = payload.get("roles") or payload.get("role") or []
    if isinstance(roles, str):
        roles = [roles]
    return Principal(subject=payload.get("sub", ""), scopes=scopes, roles=list(roles),
                     organization_id=payload.get("organization_id"), claims=payload)


def authorize(authorization: str | None, *, required_scopes: list[str] | None = None,
              **verify_kwargs) -> Principal:
    """Full gate: extract bearer, verify, enforce RBAC scopes. Raises AuthError."""
    principal = verify_access_token(bearer_from_header(authorization), **verify_kwargs)
    if required_scopes and not principal.has_scopes(required_scopes):
        raise AuthError("insufficient scope")
    return principal
