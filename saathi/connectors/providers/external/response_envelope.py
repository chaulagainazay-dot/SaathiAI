"""M33 — External response envelope (bounded, sanitized; raw never escapes).

Only bounded, normalized fields are captured. Body size and decompressed size are
bounded, content-type and charset are validated, cookies / authorization echoes /
stack traces are removed, and the raw client/socket object never leaves the
transport boundary. Redirect chains are recorded only in sanitized form.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from saathi.connectors.providers.external.models import ExternalFailure
from saathi.connectors.providers.normalization import (
    normalize_headers,
    normalize_response,
)
from saathi.connectors.providers.ratelimit import parse_rate_limit, safe_rate_limit_evidence

ACCEPTED_CONTENT_TYPES = ("application/json", "text/json", "application/vnd.github+json")


class ResponseEnvelopeError(ValueError):
    def __init__(self, code: ExternalFailure, message: str = ""):
        self.code = code
        super().__init__(f"{code.value}:{message[:80]}")


@dataclass
class ExternalResponseEnvelope:
    status_code: int
    safe_headers: dict[str, str] = field(default_factory=dict)
    body_bytes_bounded: int = 0
    content_type: str = ""
    content_length_safe: Optional[int] = None
    provider_request_id_safe: str = ""
    latency_ms: float = 0.0
    rate_limit: dict[str, Any] = field(default_factory=dict)
    redirect_chain_safe: list[dict[str, Any]] = field(default_factory=list)
    transport_classification: str = "ok"
    normalized_data: dict[str, Any] = field(default_factory=dict)
    raw_parsed: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _content_type_ok(ct: str) -> bool:
    base = (ct or "").split(";", 1)[0].strip().lower()
    return base in ACCEPTED_CONTENT_TYPES


def build_response_envelope(
    raw: dict[str, Any],
    *,
    response_limit: int,
    method: str = "GET",
) -> ExternalResponseEnvelope:
    """Normalize a bounded raw transport result into a safe response envelope.

    ``raw`` is the transport's bounded dict — NEVER a live client/socket object.
    Expected keys: status_code, headers, body_bytes (bytes), decompressed_size
    (optional int), content_type, latency_ms, redirect_chain (list of safe dicts).
    """
    if not isinstance(raw, dict):
        raise ResponseEnvelopeError(ExternalFailure.MALFORMED_ENCODING, "raw_not_dict")

    status = int(raw.get("status_code", 0))
    headers_in = raw.get("headers") or {}
    safe_headers = normalize_headers(headers_in)
    content_type = str(raw.get("content_type") or headers_in.get("content-type") or headers_in.get("Content-Type") or "")
    latency = round(float(raw.get("latency_ms", 0.0)), 3)
    rl = parse_rate_limit(headers_in, now=0.0)
    redirect_chain = list(raw.get("redirect_chain") or [])

    body = raw.get("body_bytes")
    if body is None:
        body = b""
    if isinstance(body, str):
        body = body.encode("utf-8", errors="strict")
    if not isinstance(body, (bytes, bytearray)):
        raise ResponseEnvelopeError(ExternalFailure.MALFORMED_ENCODING, "body_not_bytes")

    # raw-body ceiling first, then decompressed-size ceiling (a small compressed
    # body may still decompress past the limit → distinct failure)
    if len(body) > int(response_limit):
        raise ResponseEnvelopeError(ExternalFailure.RESPONSE_TOO_LARGE, "body_over_limit")
    decompressed_size = int(raw.get("decompressed_size", len(body)))
    if decompressed_size > int(response_limit):
        raise ResponseEnvelopeError(ExternalFailure.DECOMPRESSION_LIMIT_EXCEEDED, "decompressed_over_limit")

    # provider request id (safe, bounded) — GitHub uses x-github-request-id
    prid = ""
    for k in ("x-github-request-id", "x-request-id", "x-amzn-requestid"):
        v = safe_headers.get(k) or safe_headers.get(k.title())
        if v:
            prid = str(v)[:64]
            break

    normalized: dict[str, Any] = {}
    raw_parsed: dict[str, Any] = {}
    if method.upper() != "HEAD" and body:
        if not _content_type_ok(content_type):
            raise ResponseEnvelopeError(ExternalFailure.UNSUPPORTED_CONTENT_TYPE, f"content_type:{content_type[:40]}")
        try:
            text = body.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise ResponseEnvelopeError(ExternalFailure.MALFORMED_ENCODING, "utf8_decode_failed")
        try:
            parsed = json.loads(text)
        except (ValueError, json.JSONDecodeError):
            raise ResponseEnvelopeError(ExternalFailure.MALFORMED_ENCODING, "json_parse_failed")
        # bound the parsed object independently (schema validation reads field
        # names/types only — it never emits values, so public flags survive)
        if len(json.dumps(parsed, default=str).encode("utf-8")) > int(response_limit):
            raise ResponseEnvelopeError(ExternalFailure.RESPONSE_TOO_LARGE, "parsed_over_limit")
        raw_parsed = parsed if isinstance(parsed, dict) else {"value": parsed}
        # M32 normalizer strips cookies/tokens/stack traces and bounds size
        normalized = normalize_response(parsed, response_size_limit=int(response_limit))

    return ExternalResponseEnvelope(
        status_code=status,
        safe_headers=safe_headers,
        body_bytes_bounded=len(body),
        content_type=(content_type or "")[:80],
        content_length_safe=len(body),
        provider_request_id_safe=prid,
        latency_ms=latency,
        rate_limit=safe_rate_limit_evidence(rl),
        redirect_chain_safe=[_safe_redirect(r) for r in redirect_chain],
        transport_classification=str(raw.get("transport_classification") or "ok")[:32],
        normalized_data=normalized if isinstance(normalized, dict) else {"value": normalized},
        raw_parsed=raw_parsed,
    )


def _safe_redirect(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {"host": "", "status": 0}
    return {
        "host": str(entry.get("host") or "")[:128],
        "status": int(entry.get("status") or 0),
        "scheme": str(entry.get("scheme") or "")[:8],
    }
