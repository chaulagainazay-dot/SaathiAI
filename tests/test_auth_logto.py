"""Logto auth tests (Stage 2) — JWT verification + RBAC, offline via local RSA key."""
import time
import pytest
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from saathi.auth_logto import (
    verify_access_token, authorize, bearer_from_header, AuthError, Principal,
)

ISS = "https://saathi.logto.app/oidc"
AUD = "https://api.saathi.local"

_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_priv = _key.private_bytes(
    encoding=__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.PEM,
    format=__import__("cryptography.hazmat.primitives.serialization", fromlist=["PrivateFormat"]).PrivateFormat.PKCS8,
    encryption_algorithm=__import__("cryptography.hazmat.primitives.serialization", fromlist=["NoEncryption"]).NoEncryption(),
)
_pub = _key.public_key()


def _resolver(_token):
    return _pub


def _token(**over):
    now = int(time.time())
    payload = {"sub": "user_ajay", "iss": ISS, "aud": AUD, "exp": now + 3600,
               "iat": now, "scope": "ceo:read ceo:approve"}
    payload.update(over)
    return jwt.encode(payload, _priv, algorithm="RS256")


def _verify(tok, **kw):
    return verify_access_token(tok, key_resolver=_resolver,
                               expected_issuer=ISS, expected_audience=AUD, **kw)


# ── header parsing ─────────────────────────────────────────────────────────
def test_bearer_extraction():
    assert bearer_from_header("Bearer abc.def.ghi") == "abc.def.ghi"
    with pytest.raises(AuthError):
        bearer_from_header(None)
    with pytest.raises(AuthError):
        bearer_from_header("Token xyz")


# ── valid token → principal with scopes ────────────────────────────────────
def test_valid_token_yields_principal():
    p = _verify(_token())
    assert isinstance(p, Principal)
    assert p.subject == "user_ajay"
    assert p.scopes == ["ceo:read", "ceo:approve"]
    assert p.has_scopes(["ceo:read"]) and p.has_scopes(["ceo:read", "ceo:approve"])
    assert not p.has_scopes(["ceo:admin"])


# ── organization claim carried through ─────────────────────────────────────
def test_organization_token():
    p = _verify(_token(organization_id="org_hospital"))
    assert p.organization_id == "org_hospital"


# ── expired / wrong issuer / wrong audience / tampered all rejected ────────
def test_expired_token_rejected():
    with pytest.raises(AuthError):
        _verify(_token(exp=int(time.time()) - 10))

def test_wrong_issuer_rejected():
    with pytest.raises(AuthError):
        _verify(_token(iss="https://evil.example/oidc"))

def test_wrong_audience_rejected():
    with pytest.raises(AuthError):
        _verify(_token(aud="https://other.api"))

def test_tampered_signature_rejected():
    tok = _token()
    tampered = tok[:-3] + ("aaa" if tok[-3:] != "aaa" else "bbb")
    with pytest.raises(AuthError):
        _verify(tampered)


# ── RBAC gate through authorize() ──────────────────────────────────────────
def test_authorize_enforces_scopes():
    hdr = f"Bearer {_token()}"
    p = authorize(hdr, required_scopes=["ceo:approve"], key_resolver=_resolver,
                  expected_issuer=ISS, expected_audience=AUD)
    assert p.subject == "user_ajay"
    with pytest.raises(AuthError):
        authorize(hdr, required_scopes=["ceo:admin"], key_resolver=_resolver,
                  expected_issuer=ISS, expected_audience=AUD)
