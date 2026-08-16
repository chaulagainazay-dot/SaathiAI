"""CORS preflight vs. authentication enforcement.

The `_auth` HTTP middleware is registered last and is therefore the OUTERMOST
middleware, wrapping `CORSMiddleware`. A credentialed browser preflight
(`OPTIONS` + `Access-Control-Request-Method`) consequently reaches the auth gate
before `CORSMiddleware` can answer it, and used to be rejected with a bare 401
carrying no CORS headers — which browsers surface as a CORS failure.

`_auth` now lets `OPTIONS` through so `CORSMiddleware` answers the preflight.
These tests pin both halves of that contract:

  1. Preflight succeeds for allowlisted origins and is refused for others.
  2. The bypass did NOT make authentication optional. Every protected route
     still rejects unauthenticated non-OPTIONS requests, from any origin and
     from no origin at all.

(2) is the load-bearing assertion: widening the middleware bypass list is the
mechanism by which a protected route would silently become anonymous.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from saathi.server import app

ALLOWED_ORIGIN = "http://localhost:3000"
DENIED_ORIGIN = "http://evil.example.com"

# Protected read endpoints that are NOT in the `_auth` bypass allowlist.
PROTECTED_GET_PATHS = [
    "/api/v1/auth/sessions",
    "/api/v1/auth/audit",
    "/api/v1/security/timeline",
    "/api/v1/security/health",
    "/api/v1/security/tokens",
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _preflight(client: TestClient, path: str, origin: str):
    return client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )


class TestPreflightReachesCors:
    @pytest.mark.parametrize("path", PROTECTED_GET_PATHS)
    def test_allowed_origin_preflight_is_answered(self, client, path):
        r = _preflight(client, path, ALLOWED_ORIGIN)
        assert r.status_code == 200, f"{path} preflight was not answered by CORSMiddleware"
        assert r.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN

    @pytest.mark.parametrize("path", PROTECTED_GET_PATHS)
    def test_denied_origin_preflight_gets_no_authorization(self, client, path):
        r = _preflight(client, path, DENIED_ORIGIN)
        assert r.headers.get("access-control-allow-origin") is None
        assert r.status_code != 200


class TestBypassDidNotWeakenAuth:
    """The OPTIONS bypass must not leak into any other method."""

    @pytest.mark.parametrize("path", PROTECTED_GET_PATHS)
    @pytest.mark.parametrize("origin", [ALLOWED_ORIGIN, DENIED_ORIGIN])
    def test_unauthenticated_get_is_rejected_with_origin(self, client, path, origin):
        r = client.get(path, headers={"Origin": origin})
        assert r.status_code == 401, f"{path} answered an unauthenticated GET"

    @pytest.mark.parametrize("path", PROTECTED_GET_PATHS)
    def test_unauthenticated_get_is_rejected_without_origin(self, client, path):
        r = client.get(path)
        assert r.status_code == 401, f"{path} answered an unauthenticated GET"

    @pytest.mark.parametrize("path", PROTECTED_GET_PATHS)
    def test_unauthenticated_post_is_rejected(self, client, path):
        r = client.post(path, headers={"Origin": ALLOWED_ORIGIN}, json={})
        assert r.status_code != 200, f"{path} answered an unauthenticated POST"


class TestMiddlewareOrderIsRecorded:
    """Documents the ordering that makes the OPTIONS bypass necessary.

    If CORSMiddleware is ever moved outermost, the bypass can be deleted and
    this test should be updated together with that change.
    """

    def test_auth_middleware_wraps_cors_middleware(self):
        names = [m.cls.__name__ for m in app.user_middleware]
        assert names.index("BaseHTTPMiddleware") < names.index("CORSMiddleware")
