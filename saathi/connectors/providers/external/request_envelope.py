"""M33 — External request envelope (built only inside the adapter boundary).

The envelope carries only bounded, provider-neutral fields. Method is restricted
to GET/HEAD; path comes from the profile (no caller path, no traversal); query is
bounded and CRLF-free; headers are constructed internally with no caller
Authorization / Cookie / Host / Content-Length / Transfer-Encoding / X-Forwarded /
proxy headers. Any injection attempt fails closed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from saathi.connectors.providers.external.models import (
    ExternalFailure,
    ExternalProviderProfile,
    M33_ALLOWED_METHODS,
)

# Headers a caller may never set (constructed internally only).
FORBIDDEN_REQUEST_HEADERS = frozenset({
    "authorization", "cookie", "set-cookie", "host", "content-length",
    "transfer-encoding", "proxy-authorization", "proxy-connection", "forwarded",
    "via", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto",
    "x-forwarded-port", "x-real-ip", "x-api-key", "x-auth-token", "expect",
    "connection", "upgrade", "te",
})

SAFE_DEFAULT_HEADERS = {
    "accept": "application/json",
    "user-agent": "SaathiOS-M33-external-verify/1.0 (read-only; non-production)",
}

MAX_QUERY_PARAMS = 8
MAX_QUERY_KEY_LEN = 64
MAX_QUERY_VALUE_LEN = 256


class RequestEnvelopeError(ValueError):
    def __init__(self, code: ExternalFailure, message: str = ""):
        self.code = code
        super().__init__(f"{code.value}:{message[:80]}")


def _has_crlf(s: str) -> bool:
    low = s.lower()
    return any(t in s for t in ("\r", "\n")) or any(t in low for t in ("%0d", "%0a", "%0d%0a"))


def _has_traversal(path: str) -> bool:
    low = path.lower()
    return (
        ".." in path
        or "%2e%2e" in low
        or "%2e." in low
        or ".%2e" in low
        or "\\" in path
    )


@dataclass
class ExternalRequestEnvelope:
    request_id: str
    idempotency_key: str
    operation: str
    method: str
    canonical_path: str
    safe_query: dict[str, str] = field(default_factory=dict)
    safe_headers: dict[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    deadline: float = 5.0
    response_limit: int = 256 * 1024
    redirect_limit: int = 0
    classification: str = "PUBLIC"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["body"] = None if self.body is None else f"<{len(self.body)}b>"
        return d

    def url(self, host: str, port: int = 443) -> str:
        base = f"https://{host}" if port == 443 else f"https://{host}:{port}"
        path = self.canonical_path or "/"
        if not self.safe_query:
            return base + path
        from urllib.parse import urlencode

        return base + path + "?" + urlencode(self.safe_query)


def build_request_envelope(
    profile: ExternalProviderProfile,
    *,
    request_id: str,
    idempotency_key: str = "",
    query: Optional[dict[str, Any]] = None,
    extra_headers: Optional[dict[str, str]] = None,
) -> ExternalRequestEnvelope:
    """Construct a validated read-only request envelope. Raises on any injection."""
    method = (profile.method or "GET").upper()
    if method not in M33_ALLOWED_METHODS:
        raise RequestEnvelopeError(ExternalFailure.REQUEST_CONTRACT_VIOLATION, f"method_forbidden:{method}")

    path = profile.canonical_path or "/"
    if _has_traversal(path) or _has_crlf(path):
        raise RequestEnvelopeError(ExternalFailure.REQUEST_CONTRACT_VIOLATION, "path_unsafe")

    # bounded, CRLF-free query
    safe_query: dict[str, str] = {}
    q = query or {}
    if not isinstance(q, dict):
        raise RequestEnvelopeError(ExternalFailure.REQUEST_CONTRACT_VIOLATION, "query_not_object")
    if len(q) > MAX_QUERY_PARAMS:
        raise RequestEnvelopeError(ExternalFailure.REQUEST_CONTRACT_VIOLATION, "query_amplification")
    for k, v in q.items():
        ks, vs = str(k), str(v)
        if len(ks) > MAX_QUERY_KEY_LEN or len(vs) > MAX_QUERY_VALUE_LEN:
            raise RequestEnvelopeError(ExternalFailure.REQUEST_CONTRACT_VIOLATION, "query_field_too_large")
        if _has_crlf(ks) or _has_crlf(vs):
            raise RequestEnvelopeError(ExternalFailure.REQUEST_CONTRACT_VIOLATION, "crlf_in_query")
        if isinstance(v, (list, tuple, dict)):
            raise RequestEnvelopeError(ExternalFailure.REQUEST_CONTRACT_VIOLATION, "unbounded_list_param")
        safe_query[ks] = vs

    # headers are internal-only; reject any forbidden caller header
    headers = dict(SAFE_DEFAULT_HEADERS)
    for k, v in (extra_headers or {}).items():
        lk = str(k).lower()
        if lk in FORBIDDEN_REQUEST_HEADERS or any(
            x in lk for x in ("authorization", "cookie", "token", "secret", "api-key", "api_key", "x-forwarded")
        ):
            raise RequestEnvelopeError(ExternalFailure.REQUEST_CONTRACT_VIOLATION, f"forbidden_header:{lk}")
        vs = str(v)
        if _has_crlf(lk) or _has_crlf(vs):
            raise RequestEnvelopeError(ExternalFailure.REQUEST_CONTRACT_VIOLATION, "crlf_in_header")
        headers[lk] = vs[:512]

    return ExternalRequestEnvelope(
        request_id=str(request_id)[:64],
        idempotency_key=str(idempotency_key)[:64],
        operation=profile.operation,
        method=method,
        canonical_path=path,
        safe_query=safe_query,
        safe_headers=headers,
        body=None,  # read-only: never a request body
        deadline=float(profile.deadline_seconds),
        response_limit=int(profile.response_limit_bytes),
        redirect_limit=int(profile.redirect_limit),
        classification=profile.data_classification,
    )
