"""CORS preflight vs. authentication enforcement.

`CORSMiddleware` is the outermost middleware (see
`saathi.server._install_outermost_cors`). It therefore answers a credentialed
browser preflight before the request reaches the `_auth` gate, and it labels
every response — including an authentication rejection — with the correct
origin headers.

That ordering is what allows the auth gate to carry no `OPTIONS` bypass. These
tests pin the whole contract so the bypass cannot quietly return and so the
ordering cannot be reversed without a failure:

  1. Allowed origin: preflight is answered 200 with the right ACAO, and an
     unauthenticated protected GET is 401 *with* the right ACAO — a real
     authentication failure must be legible as one in the browser console.
  2. Disallowed origin: no ACAO on anything, preflight refused, and that
     decision is reached without consulting authentication.
  3. Authentication did not become optional. Every protected route still
     rejects unauthenticated non-preflight requests, from any origin, from no
     origin, and over `OPTIONS` itself.

(3) is the load-bearing assertion: relaxing the middleware bypass list is the
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


class TestAllowedOriginKeepsCorsHeadersOnAuthFailure:
    """A 401 must still be a labelled 401, not an opaque CORS failure."""

    @pytest.mark.parametrize("path", PROTECTED_GET_PATHS)
    def test_unauthenticated_get_401_carries_acao(self, client, path):
        r = client.get(path, headers={"Origin": ALLOWED_ORIGIN})
        assert r.status_code == 401
        assert r.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN, (
            f"{path} returned a 401 with no CORS headers; the browser would "
            "report this as a CORS error and hide the real cause"
        )

    @pytest.mark.parametrize("path", PROTECTED_GET_PATHS)
    def test_denied_origin_401_carries_no_acao(self, client, path):
        r = client.get(path, headers={"Origin": DENIED_ORIGIN})
        assert r.status_code == 401
        assert r.headers.get("access-control-allow-origin") is None


class TestOptionsBypassIsGone:
    """Deleting the `request.method == "OPTIONS"` bypass must not regress
    allowed-origin preflight, and must not leave a hole of its own."""

    def test_auth_gate_has_no_options_bypass(self):
        import inspect

        from saathi import server

        source = inspect.getsource(server._auth)
        assert 'request.method == "OPTIONS"' not in source, (
            "the temporary OPTIONS bypass is back; CORS ordering makes it "
            "unnecessary and it widens the unauthenticated surface"
        )

    @pytest.mark.parametrize("path", PROTECTED_GET_PATHS)
    def test_allowed_origin_preflight_still_answered_without_the_bypass(
        self, client, path
    ):
        r = _preflight(client, path, ALLOWED_ORIGIN)
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN

    @pytest.mark.parametrize("path", PROTECTED_GET_PATHS)
    def test_non_preflight_options_is_authenticated(self, client, path):
        """An `OPTIONS` without `Access-Control-Request-Method` is not a
        preflight. CORSMiddleware passes it through, so `_auth` must gate it."""
        r = client.options(path, headers={"Origin": ALLOWED_ORIGIN})
        assert r.status_code == 401, (
            f"{path} answered an unauthenticated non-preflight OPTIONS"
        )


class TestMiddlewareOrderIsEnforced:
    """CORS outermost is the architecture, not an accident of import order."""

    def test_cors_middleware_is_outermost(self):
        from saathi.server import app as live_app

        names = [m.cls.__name__ for m in live_app.user_middleware]
        assert names[0] == "CORSMiddleware", (
            "CORSMiddleware must be the outermost middleware so that "
            f"authentication rejections stay CORS-labelled; stack is {names}"
        )

    def test_auth_gate_runs_inside_cors(self):
        from saathi.server import app as live_app

        names = [m.cls.__name__ for m in live_app.user_middleware]
        assert names.index("CORSMiddleware") < names.index("BaseHTTPMiddleware")
