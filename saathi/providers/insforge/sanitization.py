"""Redaction and payload bounding for InsForge responses."""
from __future__ import annotations

from typing import Any

from saathi.mcp_governance.redaction import redact_obj, redact_text, REDACTED

_SENSITIVE_KEYS = frozenset({
    "password", "token", "secret", "api_key", "apikey", "authorization",
    "access_token", "refresh_token", "private_key", "client_secret",
    "cookie", "session", "jwt", "bearer", "encryption_key",
})


def sanitize_value(obj: Any, *, max_str: int = 500, depth: int = 0) -> Any:
    if depth > 6:
        return REDACTED
    if isinstance(obj, dict):
        out = {}
        for k, v in list(obj.items())[:80]:
            ks = str(k)
            if any(s in ks.lower() for s in _SENSITIVE_KEYS):
                out[ks] = REDACTED
            else:
                out[ks] = sanitize_value(v, max_str=max_str, depth=depth + 1)
        return out
    if isinstance(obj, list):
        return [sanitize_value(x, max_str=max_str, depth=depth + 1) for x in obj[:100]]
    if isinstance(obj, str):
        return redact_text(obj, max_len=max_str)
    if isinstance(obj, (int, float, bool)) or obj is None:
        return obj
    return redact_text(str(obj), max_len=max_str)


def sanitize_logs(records: list[Any], *, max_records: int = 50) -> list[dict]:
    out: list[dict] = []
    for row in records[:max_records]:
        if isinstance(row, dict):
            out.append(sanitize_value(row, max_str=400))
        else:
            out.append({"message": redact_text(str(row), max_len=400)})
    return out


def summarize_for_audit(operation: str, result: dict | None, *, error: str = "") -> dict:
    """Bounded audit summary — no full bodies."""
    r = result or {}
    return sanitize_value({
        "operation": operation,
        "ok": r.get("ok"),
        "provider": "insforge",
        "keys": sorted(str(k) for k in r.keys() if k not in ("raw", "body"))[:20],
        "count": r.get("count"),
        "status": r.get("status"),
        "error": (error or r.get("error_category") or "")[:120],
    })
