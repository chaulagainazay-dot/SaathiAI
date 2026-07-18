"""M32 — Bounded rate-limit awareness.

Rate-limit metadata is parsed ONLY through adapter policy from provider headers.
Unreasonable values are clamped; malformed values are ignored safely; callers can
never spoof rate-limit metadata (caller-supplied values are dropped). Retry-After
is honored only when bounded and within the deadline. No sleeping past the
deadline, no background retry storm. Evidence carries no sensitive headers.
"""
from __future__ import annotations

from typing import Any, Optional

from saathi.connectors.providers.models import RateLimit

# Clamp ceilings (defensive against provider or spoofed values)
MAX_LIMIT = 1_000_000
MAX_RETRY_AFTER = 3600.0
MAX_RESET_HORIZON = 24 * 3600.0

_LIMIT_HEADERS = ("x-ratelimit-limit", "ratelimit-limit", "x-rate-limit-limit")
_REMAINING_HEADERS = ("x-ratelimit-remaining", "ratelimit-remaining", "x-rate-limit-remaining")
_RESET_HEADERS = ("x-ratelimit-reset", "ratelimit-reset", "x-rate-limit-reset")
_RETRY_AFTER_HEADERS = ("retry-after", "x-retry-after")


def _to_int(v: Any) -> Optional[int]:
    try:
        n = int(float(str(v).strip()))
        return n if n >= 0 else None
    except (ValueError, TypeError):
        return None


def _to_float(v: Any) -> Optional[float]:
    try:
        f = float(str(v).strip())
        return f if f >= 0 else None
    except (ValueError, TypeError):
        return None


def parse_rate_limit(
    headers: Any,
    *,
    now: float = 0.0,
    max_retry_after: float = MAX_RETRY_AFTER,
) -> RateLimit:
    """Parse rate-limit metadata from provider headers only. Fail safe → source=none."""
    rl = RateLimit(source="none", confidence="unknown")
    if not isinstance(headers, dict):
        return rl
    lower = {str(k).lower(): v for k, v in headers.items()}

    got = False
    for h in _LIMIT_HEADERS:
        if h in lower:
            n = _to_int(lower[h])
            if n is not None:
                rl.limit = min(n, MAX_LIMIT)
                got = True
            break
    for h in _REMAINING_HEADERS:
        if h in lower:
            n = _to_int(lower[h])
            if n is not None:
                rl.remaining = min(n, MAX_LIMIT)
                got = True
            break
    for h in _RESET_HEADERS:
        if h in lower:
            f = _to_float(lower[h])
            if f is not None:
                # clamp reset to a sane horizon relative to now
                rl.reset_at = now + min(f, MAX_RESET_HORIZON) if f < MAX_RESET_HORIZON else now + MAX_RESET_HORIZON
                got = True
            break
    for h in _RETRY_AFTER_HEADERS:
        if h in lower:
            f = _to_float(lower[h])
            if f is not None:
                rl.retry_after = min(f, max_retry_after, MAX_RETRY_AFTER)
                got = True
            break

    if got:
        rl.source = "header"
        rl.confidence = "high" if rl.limit is not None or rl.retry_after is not None else "low"
    return rl


def honored_retry_after(
    rl: RateLimit, *, remaining_deadline: float, max_retry_after: float = 10.0,
) -> Optional[float]:
    """Return a bounded Retry-After to honor, or None if it must not be honored."""
    if rl.retry_after is None:
        return None
    if rl.retry_after < 0:
        return None
    if rl.retry_after > max_retry_after:
        return None
    if rl.retry_after > remaining_deadline:
        return None
    return float(rl.retry_after)


def safe_rate_limit_evidence(rl: RateLimit) -> dict[str, Any]:
    """Rate-limit evidence with no sensitive headers — numeric/enum fields only."""
    return {
        "limit": rl.limit,
        "remaining": rl.remaining,
        "reset_at": rl.reset_at,
        "retry_after": rl.retry_after,
        "source": rl.source,
        "confidence": rl.confidence,
        "privacy_safe": True,
    }
