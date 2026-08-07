"""Bounded CORS origin allowlist (M47.6).

Rules:
- No wildcard for credentialed APIs.
- Production/staging fail closed unless SAATHI_CORS_ORIGINS is set.
- Development defaults cover documented UI ports only.
"""
from __future__ import annotations

import os

# Documented local UI / cert ports for SaathiOS Next + Playwright harness.
_DEV_DEFAULT_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3100",
    "http://127.0.0.1:3100",
    "http://localhost:3110",
    "http://127.0.0.1:3110",
    "http://localhost:3112",
    "http://127.0.0.1:3112",
    "http://localhost:8765",
    "http://127.0.0.1:8765",
)

_PROD_ENVS = frozenset({"production", "prod", "staging", "canary"})

# Bounded CORS methods (no "*")
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]

# Bounded headers used by the UI client (afetch + content-type)
CORS_ALLOW_HEADERS = [
    "Accept",
    "Accept-Language",
    "Content-Type",
    "Authorization",
    "X-Requested-With",
    "x-baadar-session",
    "X-Baadar-Session",
    # Platform console session header (M50+). Required for the split-origin
    # private-alpha browser workflow certified in M54.
    "X-Platform-Token",
    "x-platform-token",
]


def resolve_environment(explicit: str | None = None) -> str:
    raw = (
        explicit
        or os.getenv("SAATHI_ENV")
        or os.getenv("SAATHI_ENVIRONMENT")
        or os.getenv("ENVIRONMENT")
        or "development"
    )
    return str(raw).strip().lower() or "development"


def parse_cors_origins(raw: str | None) -> list[str]:
    """Parse comma-separated origins; reject wildcards."""
    if not raw or not str(raw).strip():
        return []
    out: list[str] = []
    for part in str(raw).split(","):
        o = part.strip()
        if not o:
            continue
        if o == "*":
            # Never allow wildcard with credentialed API
            continue
        out.append(o)
    return out


def resolve_cors_origins(
    env_value: str | None = None,
    *,
    environment: str | None = None,
) -> list[str]:
    """
    Resolve allowlist.

    - If SAATHI_CORS_ORIGINS set: use it (minus wildcards).
    - If production/staging/canary and unset: empty (fail closed).
    - Else development defaults.
    """
    raw = env_value if env_value is not None else os.getenv("SAATHI_CORS_ORIGINS", "")
    parsed = parse_cors_origins(raw)
    if parsed:
        return parsed
    env = resolve_environment(environment)
    if env in _PROD_ENVS:
        return []
    return list(_DEV_DEFAULT_ORIGINS)


def origin_allowed(origin: str | None, allowlist: list[str]) -> bool:
    if not origin:
        return False
    return origin in allowlist
