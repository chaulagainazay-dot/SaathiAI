"""Obtain a platform session the way the product now does.

Before D15 a test got one in two anonymous steps:

    client.post("/api/v1/platform/bootstrap", json={"email": "x@local"})
    token = client.post("/api/v1/platform/auth/login",
                        json={"email": "x@local"}).json()["token"]

Neither step authenticated anything. The first created the platform owner from
a caller-supplied body; the second took the "M50 passwordless path (existing
users without credentials)" and minted a full session for whoever named the
email. Together they were a complete anonymous path to platform authority, and
they are both closed.

The supported route is now an exchange: be the canonical D14 owner, hold a live
canonical session, and ask the platform to provision the identity that belongs
to that owner. This helper performs exactly that, so suites that are *about*
missions, modules, voice or operations can keep describing those things instead
of re-testing authentication.

Do not use this in a test *of* platform provisioning — see
tests/test_d15_platform_identity.py, which drives the route directly.
"""
from __future__ import annotations

CANONICAL_PASSWORD = "T3st!Platform#Pw"


def canonical_owner_session(security_store=None) -> str:
    """Put the canonical store into ACTIVE and return an owner session token."""
    from saathi import sessions
    from saathi.security.store import get_store

    from support.auth_state import make_active

    store = security_store or get_store()
    make_active(store, password=CANONICAL_PASSWORD)
    return sessions.create(ua="pytest", ip="127.0.0.1", kind="password")


def platform_token(client, security_store=None) -> str:
    """A platform session token derived from the canonical owner.

    Returns the raw token for use as ``X-Platform-Token``. The identity is the
    canonical owner's; nothing about it is caller-selectable, which is why this
    helper takes no email, name or organisation.
    """
    canonical = canonical_owner_session(security_store)
    r = client.post("/api/v1/platform/bootstrap", json={},
                    headers={"x-baadar-session": canonical})
    if r.status_code != 200:
        raise AssertionError(
            f"platform provisioning failed: {r.status_code} {r.text[:200]}"
        )
    return r.json()["token"]


def platform_headers(client, security_store=None) -> dict:
    return {"X-Platform-Token": platform_token(client, security_store)}
