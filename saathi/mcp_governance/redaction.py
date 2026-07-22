"""Secret and privacy redaction for MCP requests/responses and lesson content."""
from __future__ import annotations

import re
from typing import Any

# Key-name patterns (case-insensitive)
_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|secret|token|password|passwd|authorization|auth|"
    r"bearer|cookie|session|private[_-]?key|access[_-]?key|"
    r"exchange[_-]?cred|patient|ssn|credit[_-]?card)",
    re.IGNORECASE,
)

# Value-shaped secrets (bounded; avoid catastrophic backtracking)
_SECRET_VALUE_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}\b", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)password\s*[:=]\s*\S+"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*\S+"),
    re.compile(r"(?i)secret\s*[:=]\s*\S+"),
    re.compile(r"(?i)authorization\s*[:=]\s*\S+"),
]

REDACTED = "***REDACTED***"


def contains_secret_like(text: str) -> bool:
    """True if *text* appears to contain secret-like material."""
    if not text:
        return False
    if _SECRET_KEY_RE.search(text) and re.search(
        r"[:=]\s*\S{8,}|['\"][^'\"]{8,}['\"]", text
    ):
        return True
    for pat in _SECRET_VALUE_PATTERNS:
        if pat.search(text):
            return True
    return False


def redact_text(text: str, *, max_len: int = 2000) -> str:
    """Redact secret-like substrings; bound length for logs/events."""
    if not isinstance(text, str):
        text = str(text)
    out = text
    for pat in _SECRET_VALUE_PATTERNS:
        out = pat.sub(REDACTED, out)
    if len(out) > max_len:
        out = out[: max_len - 3] + "..."
    return out


def redact_obj(obj: Any, *, depth: int = 0) -> Any:
    """Recursively redact dict keys that look secret and scrub string values."""
    if depth > 8:
        return REDACTED
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _SECRET_KEY_RE.search(str(k)):
                out[str(k)] = REDACTED
            else:
                out[str(k)] = redact_obj(v, depth=depth + 1)
        return out
    if isinstance(obj, list):
        return [redact_obj(x, depth=depth + 1) for x in obj[:50]]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


def safe_summary(obj: Any, *, max_keys: int = 12) -> dict:
    """Bounded, redacted summary suitable for Evidence / Control Center."""
    cleaned = redact_obj(obj)
    if not isinstance(cleaned, dict):
        return {"summary": redact_text(str(cleaned), max_len=400)}
    keys = list(cleaned.keys())[:max_keys]
    return {k: cleaned[k] for k in keys}
