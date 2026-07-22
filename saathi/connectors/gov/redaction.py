"""M27 — Payload/event redaction for connectors (reuse MCP patterns)."""
from __future__ import annotations

from typing import Any

from saathi.connectors.gov.models import FORBIDDEN_PAYLOAD_KEYS

try:
    from saathi.mcp_governance.redaction import redact_obj as mcp_redact_obj
    from saathi.mcp_governance.redaction import redact_text as mcp_redact_text
except Exception:  # pragma: no cover
    mcp_redact_obj = None
    mcp_redact_text = None


def redact_text(text: str, *, max_len: int = 1000) -> str:
    if mcp_redact_text:
        return mcp_redact_text(text, max_len=max_len)
    if not isinstance(text, str):
        text = str(text)
    return text[:max_len]


def redact_payload(obj: Any) -> Any:
    """Redact secrets; never pass through forbidden keys."""
    if mcp_redact_obj:
        cleaned = mcp_redact_obj(obj)
    else:
        cleaned = obj
    return _strip_forbidden(cleaned)


def _strip_forbidden(obj: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "***"
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in FORBIDDEN_PAYLOAD_KEYS or any(
                x in lk for x in ("secret", "password", "token", "authorization", "cookie")
            ):
                continue
            out[k] = _strip_forbidden(v, depth + 1)
        out["privacy_safe"] = True
        return out
    if isinstance(obj, list):
        return [_strip_forbidden(x, depth + 1) for x in obj[:50]]
    if isinstance(obj, str) and len(obj) > 500:
        return obj[:500] + "…"
    return obj
