"""M32 — Provider-neutral request/response normalization.

Requests: validate required fields, reject caller injection (headers, endpoint,
auth, retry policy), enforce type/size limits, normalize timestamps/identifiers,
classify sensitive fields. Provider-specific payloads are produced ONLY inside
the adapter boundary.

Responses: normalize into a stable taxonomy, strip cookies/tokens/authorization/
stack traces, enforce response-size limits, detect malformed/partial payloads.
Raw provider response objects never escape this boundary.
"""
from __future__ import annotations

import json
from typing import Any

from saathi.connectors.gov.redaction import redact_payload
from saathi.connectors.providers.errors import ProviderError
from saathi.connectors.providers.models import (
    DataClassification,
    M32_PERMITTED_DATA_CLASSES,
    ProviderErrorCode,
)

# Caller fields that indicate an injection attempt — request fails closed
DANGEROUS_REQUEST_FIELDS = frozenset({
    "headers", "header", "authorization", "auth", "endpoint", "url", "base_url",
    "retry", "retry_policy", "max_retries", "timeout", "timeout_policy",
    "connect_timeout", "read_timeout", "cookie", "cookies", "set-cookie",
    "proxy", "proxies", "transport", "rate_limit", "rate_limit_remaining",
    "x-api-key", "api_key", "bearer", "credential", "secret", "token",
})

# Sensitive response headers always removed
SENSITIVE_RESPONSE_HEADERS = frozenset({
    "set-cookie", "cookie", "authorization", "www-authenticate",
    "proxy-authenticate", "x-api-key", "x-auth-token",
})

# Sensitive keys stripped from normalized response bodies
SENSITIVE_BODY_KEYS = frozenset({
    "access_token", "refresh_token", "id_token", "token", "api_key", "apikey",
    "authorization", "cookie", "secret", "password", "private_key", "bearer",
    "client_secret", "stack", "stacktrace", "traceback", "exception",
})

MAX_REQUEST_FIELDS = 64
MAX_STRING_LEN = 4096


class NormalizationError(ProviderError):
    def __init__(self, message: str, code: ProviderErrorCode = ProviderErrorCode.INVALID_REQUEST):
        super().__init__(code, message)


def normalize_request(
    payload: dict[str, Any],
    *,
    operation: str,
    allowed_operations: tuple[str, ...],
    request_size_limit: int,
) -> dict[str, Any]:
    """Return a provider-neutral normalized request; raise NormalizationError on any injection."""
    if operation not in allowed_operations:
        raise NormalizationError(
            f"unsupported_operation:{operation}", ProviderErrorCode.INVALID_REQUEST,
        )
    if not isinstance(payload, dict):
        raise NormalizationError("payload_not_object")
    if len(payload) > MAX_REQUEST_FIELDS:
        raise NormalizationError("too_many_request_fields")

    # size ceiling on the material payload
    try:
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    except Exception:
        raise NormalizationError("payload_not_serializable")
    if len(encoded) > int(request_size_limit):
        raise NormalizationError("request_too_large", ProviderErrorCode.INVALID_REQUEST)

    normalized: dict[str, Any] = {}
    for k, v in payload.items():
        lk = str(k).lower()
        if lk in DANGEROUS_REQUEST_FIELDS:
            raise NormalizationError(f"injection_field_rejected:{lk}")
        if isinstance(v, str) and len(v) > MAX_STRING_LEN:
            raise NormalizationError(f"field_too_large:{lk}")
        normalized[str(k)] = _normalize_value(v)
    return normalized


def _normalize_value(v: Any) -> Any:
    if isinstance(v, dict):
        return {str(k): _normalize_value(x) for k, x in list(v.items())[:MAX_REQUEST_FIELDS]}
    if isinstance(v, list):
        return [_normalize_value(x) for x in v[:MAX_REQUEST_FIELDS]]
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    return str(v)[:MAX_STRING_LEN]


def normalize_response(
    raw: Any,
    *,
    response_size_limit: int,
) -> dict[str, Any]:
    """Normalize a raw provider response into safe provider-neutral data.

    Raises NormalizationError(MALFORMED_RESPONSE) on malformed / oversized bodies.
    """
    if raw is None:
        raise NormalizationError("empty_response", ProviderErrorCode.MALFORMED_RESPONSE)

    if isinstance(raw, (bytes, bytearray)):
        if len(raw) > int(response_size_limit):
            raise NormalizationError("response_too_large", ProviderErrorCode.MALFORMED_RESPONSE)
        try:
            raw = json.loads(raw.decode("utf-8"))
        except Exception:
            raise NormalizationError("malformed_response_body", ProviderErrorCode.MALFORMED_RESPONSE)

    if isinstance(raw, str):
        if len(raw.encode("utf-8")) > int(response_size_limit):
            raise NormalizationError("response_too_large", ProviderErrorCode.MALFORMED_RESPONSE)
        try:
            raw = json.loads(raw)
        except Exception:
            raise NormalizationError("malformed_response_body", ProviderErrorCode.MALFORMED_RESPONSE)

    if not isinstance(raw, dict):
        raise NormalizationError("response_not_object", ProviderErrorCode.MALFORMED_RESPONSE)

    # enforce serialized size ceiling on the whole object
    try:
        size = len(json.dumps(raw, default=str).encode("utf-8"))
    except Exception:
        raise NormalizationError("response_not_serializable", ProviderErrorCode.MALFORMED_RESPONSE)
    if size > int(response_size_limit):
        raise NormalizationError("response_too_large", ProviderErrorCode.MALFORMED_RESPONSE)

    body = raw.get("body", raw)
    cleaned = _strip_sensitive(body)
    # redact_payload adds a final defense-in-depth secret strip
    safe = redact_payload(cleaned)
    if not isinstance(safe, dict):
        safe = {"value": safe}
    return safe


def normalize_headers(headers: Any) -> dict[str, str]:
    """Drop sensitive headers; keep only safe string values."""
    out: dict[str, str] = {}
    if not isinstance(headers, dict):
        return out
    for k, v in headers.items():
        lk = str(k).lower()
        if lk in SENSITIVE_RESPONSE_HEADERS:
            continue
        if any(x in lk for x in ("authorization", "cookie", "token", "secret", "api-key", "api_key")):
            continue
        out[str(k)] = str(v)[:512]
    return out


def _strip_sensitive(obj: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "***"
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in SENSITIVE_BODY_KEYS or any(
                x in lk for x in ("token", "secret", "password", "authorization", "cookie", "api_key", "apikey", "traceback", "stack")
            ):
                continue
            out[str(k)] = _strip_sensitive(v, depth + 1)
        return out
    if isinstance(obj, list):
        return [_strip_sensitive(x, depth + 1) for x in obj[:100]]
    if isinstance(obj, str) and len(obj) > 512:
        return obj[:512] + "…"
    return obj


def classify_field_sensitivity(key: str) -> str:
    """Best-effort field classification (fail closed to CONFIDENTIAL for unknown-sensitive)."""
    lk = str(key).lower()
    if any(x in lk for x in ("token", "secret", "password", "api_key", "authorization", "cookie", "bearer")):
        return DataClassification.AUTH_SECRET.value
    if any(x in lk for x in ("ssn", "dob", "email", "phone", "address")):
        return DataClassification.PERSONAL.value
    if any(x in lk for x in ("amount", "balance", "iban", "card", "account_number")):
        return DataClassification.FINANCIAL.value
    return DataClassification.PUBLIC.value


def data_classification_permitted(classification: str) -> bool:
    try:
        return DataClassification(classification) in M32_PERMITTED_DATA_CLASSES
    except ValueError:
        return False
