"""M49.1 secret-field detection and redaction for tool payloads."""
from __future__ import annotations

import re
from typing import Any

# Key names that look like credentials (context-aware; not bare "key")
_SECRET_KEY_RE = re.compile(
    r"(^|[_-])(password|secret|api[_-]?key|private[_-]?key|token|authorization|"
    r"bearer|cookie|credential|access[_-]?key|client[_-]?secret)([_-]|$)",
    re.I,
)
# Standalone exact secret-ish keys
_SECRET_KEY_EXACT = frozenset({
    "password", "secret", "token", "authorization", "cookie", "credential",
    "api_key", "apikey", "private_key", "access_token", "refresh_token",
    "client_secret", "auth_token", "bearer",
})

_SECRET_VALUE_RE = re.compile(
    r"^(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
    r"-----BEGIN |xox[baprs]-)",
)

REDACTED = "***REDACTED***"


def is_secret_key(key: str) -> bool:
    k = (key or "").strip()
    if not k:
        return False
    if k.lower() in _SECRET_KEY_EXACT:
        return True
    return bool(_SECRET_KEY_RE.search(k))


def looks_like_secret_value(val: Any) -> bool:
    if not isinstance(val, str):
        return False
    s = val.strip()
    if len(s) < 12:
        return False
    return bool(_SECRET_VALUE_RE.match(s))


def find_secret_violations(obj: Any, *, path: str = "") -> list[str]:
    """Return dotted paths of secret-like fields (for rejection, not redaction)."""
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            if is_secret_key(str(k)):
                found.append(p)
            elif looks_like_secret_value(v):
                found.append(p)
            else:
                found.extend(find_secret_violations(v, path=p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(find_secret_violations(v, path=f"{path}[{i}]"))
    return found


def redact(obj: Any, *, max_chars: int = 4000) -> Any:
    """Deep-copy redaction for evidence/events."""
    out = _redact(obj)
    try:
        import json

        s = json.dumps(out, default=str)
        if len(s) > max_chars:
            return {"_truncated": True, "preview": s[:max_chars]}
    except Exception:
        pass
    return out


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        res = {}
        for k, v in obj.items():
            if is_secret_key(str(k)) or looks_like_secret_value(v):
                res[k] = REDACTED
            else:
                res[k] = _redact(v)
        return res
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    if isinstance(obj, str) and looks_like_secret_value(obj):
        return REDACTED
    return obj
