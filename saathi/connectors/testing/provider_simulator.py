"""M32 — Deterministic provider simulator.

In-process / loopback-only. NEVER contacts the public internet. Produces a fixed,
deterministic response (or raises a deterministic error) per scenario so the
provider-adapter governance path can be validated without any live dependency.

Raw responses are shaped like an HTTP response: {status_code, headers, body}.
The adapter is responsible for normalization/redaction — the simulator may emit
forbidden sensitive headers on purpose to prove they are stripped.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

SIMULATOR_VERSION = "m32.provider_simulator.v1"

# Canonical scenario names
SCENARIOS = frozenset({
    "success",
    "delayed",
    "timeout",
    "connection_failure",
    "rate_limited",
    "server_error",
    "malformed_json",
    "oversized",
    "partial_success",
    "duplicate",
    "idempotency_replay",
    "auth_failure",
    "authz_failure",
    "scope_failure",
    "cancellation",
    "shutdown",
    "forbidden_headers",
})


class SimulatorCancelled(Exception):
    """Raised for the cancellation scenario."""


class SimulatorShutdown(Exception):
    """Raised when the simulator is shut down mid-execution."""


@dataclass
class RawResponse:
    status_code: int
    headers: dict[str, str]
    body: Any

    def to_transport_dict(self) -> dict[str, Any]:
        return {"status_code": self.status_code, "headers": self.headers, "body": self.body}


# A body large enough to exceed the response-size ceiling deterministically
_OVERSIZED_BODY = {"data": "x" * (300 * 1024)}

# Headers that MUST be stripped by the adapter (present on purpose)
_FORBIDDEN_HEADERS = {
    "set-cookie": "session=synthetic-abc; Path=/",
    "authorization": "Bearer synthetic-token-value",
    "x-api-key": "synthetic-api-key-value",
    "www-authenticate": "Bearer",
}

_SAFE_HEADERS = {
    "content-type": "application/json",
    "x-request-id": "sim-req-0001",
    "x-ratelimit-limit": "60",
    "x-ratelimit-remaining": "59",
}


class ProviderSimulator:
    """Deterministic provider. Bound to loopback/in-process only."""

    def __init__(self, *, provider_id: str = "saathi.echo.v1", clock: Optional[Any] = None):
        self.provider_id = provider_id
        self.version = SIMULATOR_VERSION
        self.clock = clock  # optional deterministic clock; unused for real sleeps
        self._shutdown = False
        self._seen_requests: set[str] = set()

    def shutdown(self) -> None:
        self._shutdown = True

    def execute(self, scenario: str, request: dict[str, Any]) -> dict[str, Any]:
        """Return a raw transport response dict or raise a deterministic error."""
        if self._shutdown:
            raise SimulatorShutdown("simulator_shutdown")
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown_scenario:{scenario}")

        rid = str(request.get("request_id") or request.get("idempotency_key") or "")

        if scenario == "timeout":
            raise TimeoutError("simulated_timeout")
        if scenario == "connection_failure":
            raise ConnectionError("simulated_connection_failure")
        if scenario == "cancellation":
            raise SimulatorCancelled("simulated_cancellation")
        if scenario == "shutdown":
            self._shutdown = True
            raise SimulatorShutdown("simulated_shutdown_during_execution")

        if scenario == "rate_limited":
            return RawResponse(
                429,
                {**_SAFE_HEADERS, "retry-after": "2", "x-ratelimit-remaining": "0"},
                {"error": "rate_limited"},
            ).to_transport_dict()
        if scenario == "server_error":
            return RawResponse(500, dict(_SAFE_HEADERS), {"error": "internal"}).to_transport_dict()
        if scenario == "auth_failure":
            return RawResponse(401, dict(_SAFE_HEADERS), {"error": "unauthenticated"}).to_transport_dict()
        if scenario == "authz_failure":
            return RawResponse(403, dict(_SAFE_HEADERS), {"error": "forbidden"}).to_transport_dict()
        if scenario == "scope_failure":
            return RawResponse(403, dict(_SAFE_HEADERS), {"error": "insufficient_scope"}).to_transport_dict()
        if scenario == "malformed_json":
            # body is a non-JSON string that will fail to parse
            return RawResponse(200, dict(_SAFE_HEADERS), "{not-valid-json,,,").to_transport_dict()
        if scenario == "oversized":
            return RawResponse(200, dict(_SAFE_HEADERS), dict(_OVERSIZED_BODY)).to_transport_dict()
        if scenario == "partial_success":
            return RawResponse(
                206,
                dict(_SAFE_HEADERS),
                {"partial": True, "items": [{"id": "a"}], "missing": ["b"]},
            ).to_transport_dict()
        if scenario == "forbidden_headers":
            return RawResponse(
                200,
                {**_SAFE_HEADERS, **_FORBIDDEN_HEADERS},
                {"ok": True, "echo": _safe_echo(request)},
            ).to_transport_dict()

        # duplicate / idempotency_replay share state tracking
        if scenario in ("duplicate", "idempotency_replay"):
            duplicate = rid in self._seen_requests
            self._seen_requests.add(rid)
            return RawResponse(
                200,
                {**_SAFE_HEADERS, "x-duplicate": "true" if duplicate else "false"},
                {"ok": True, "duplicate": duplicate, "echo": _safe_echo(request)},
            ).to_transport_dict()

        # success / delayed
        headers = dict(_SAFE_HEADERS)
        if scenario == "delayed":
            headers["x-simulated-delay-ms"] = "50"
        return RawResponse(
            200, headers, {"ok": True, "echo": _safe_echo(request)},
        ).to_transport_dict()


def _safe_echo(request: dict[str, Any]) -> dict[str, Any]:
    """Echo back only safe, non-secret request fields."""
    out: dict[str, Any] = {}
    for k, v in (request.get("payload") or {}).items():
        lk = str(k).lower()
        if any(x in lk for x in ("token", "secret", "password", "authorization", "cookie", "key")):
            continue
        out[str(k)] = v if isinstance(v, (int, float, bool)) else str(v)[:200]
    return out
