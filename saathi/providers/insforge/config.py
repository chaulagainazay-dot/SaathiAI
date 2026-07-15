"""InsForge pilot configuration — disabled by default, no secrets in code."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

# Environment variable names (values never logged)
ENV_ENABLED = "SAATHI_INSFORGE_ENABLED"
ENV_BASE_URL = "SAATHI_INSFORGE_BASE_URL"
ENV_API_KEY = "SAATHI_INSFORGE_API_KEY"  # optional read credential (ik_… or bearer)
ENV_TIMEOUT = "SAATHI_INSFORGE_TIMEOUT_SEC"
ENV_MAX_BYTES = "SAATHI_INSFORGE_MAX_RESPONSE_BYTES"
ENV_MAX_LOGS = "SAATHI_INSFORGE_MAX_LOG_RECORDS"
ENV_TLS_VERIFY = "SAATHI_INSFORGE_TLS_VERIFY"
ENV_ALLOW_LOOPBACK = "SAATHI_INSFORGE_ALLOW_LOOPBACK"
ENV_WRITES_ENABLED = "SAATHI_INSFORGE_WRITES_ENABLED"

DEFAULT_TIMEOUT_SEC = 10.0
MAX_TIMEOUT_SEC = 30.0
DEFAULT_MAX_RESPONSE_BYTES = 512_000  # 500 KiB
MAX_MAX_RESPONSE_BYTES = 2_000_000
DEFAULT_MAX_LOG_RECORDS = 50
MAX_MAX_LOG_RECORDS = 200

# Strict path allowlist (relative to API root). Methods: GET only (reads).
ALLOWED_PATHS: frozenset[str] = frozenset({
    "/api/health",
    "/api/metadata",
    "/api/database/tables",
    "/api/functions",
    "/api/storage/buckets",
    "/api/logs",
})

# Write / high-risk path prefixes — blocked for GET; POST migration is separate gate
BLOCKED_PATH_PREFIXES: tuple[str, ...] = (
    "/api/secrets",
    "/api/memory",
    "/api/schedules",
    "/api/ai",
    "/api/deployments",
    "/api/payments",
    "/api/compute",
    "/api/auth",
    "/functions/",
)

ALLOWED_SCHEMES = frozenset({"http", "https"})


@dataclass(frozen=True)
class InsForgeConfig:
    enabled: bool = False
    base_url: str = ""
    api_key: str = ""
    timeout_sec: float = DEFAULT_TIMEOUT_SEC
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    max_log_records: int = DEFAULT_MAX_LOG_RECORDS
    tls_verify: bool = True
    allow_loopback: bool = False
    writes_enabled: bool = False  # M18.4: separate from enabled; still default false

    def public_dict(self) -> dict[str, Any]:
        """Safe summary — never includes api_key."""
        return {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "has_api_key": bool(self.api_key),
            "timeout_sec": self.timeout_sec,
            "max_response_bytes": self.max_response_bytes,
            "max_log_records": self.max_log_records,
            "tls_verify": self.tls_verify,
            "allow_loopback": self.allow_loopback,
            "allowed_paths": sorted(ALLOWED_PATHS),
            "pilot": "governed_migration_write" if self.writes_enabled else "read_only",
            "writes_enabled": bool(self.writes_enabled),
        }


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


def _clamp_float(raw: str | None, default: float, lo: float, hi: float) -> float:
    try:
        v = float(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        v = default
    return max(lo, min(hi, v))


def _clamp_int(raw: str | None, default: int, lo: int, hi: int) -> int:
    try:
        v = int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        v = default
    return max(lo, min(hi, v))


def load_config(*, env: dict | None = None) -> InsForgeConfig:
    e = env if env is not None else os.environ
    return InsForgeConfig(
        enabled=_truthy(e.get(ENV_ENABLED)),
        base_url=(e.get(ENV_BASE_URL) or "").strip().rstrip("/"),
        api_key=(e.get(ENV_API_KEY) or "").strip(),
        timeout_sec=_clamp_float(e.get(ENV_TIMEOUT), DEFAULT_TIMEOUT_SEC, 1.0, MAX_TIMEOUT_SEC),
        max_response_bytes=_clamp_int(
            e.get(ENV_MAX_BYTES), DEFAULT_MAX_RESPONSE_BYTES, 1024, MAX_MAX_RESPONSE_BYTES,
        ),
        max_log_records=_clamp_int(
            e.get(ENV_MAX_LOGS), DEFAULT_MAX_LOG_RECORDS, 1, MAX_MAX_LOG_RECORDS,
        ),
        tls_verify=_truthy(e.get(ENV_TLS_VERIFY) or "1"),
        allow_loopback=_truthy(e.get(ENV_ALLOW_LOOPBACK)),
        writes_enabled=_truthy(e.get(ENV_WRITES_ENABLED)),
    )


def validate_base_url(url: str, *, allow_loopback: bool = False) -> tuple[bool, str]:
    """Return (ok, reason). Fail closed on unsafe schemes / hosts."""
    if not url or not url.strip():
        return False, "base_url_missing"
    try:
        p = urlparse(url.strip())
    except Exception:
        return False, "base_url_unparseable"
    if p.scheme not in ALLOWED_SCHEMES:
        return False, f"scheme_denied:{p.scheme or 'empty'}"
    if p.username or p.password:
        return False, "userinfo_in_url_denied"
    host = (p.hostname or "").lower()
    if not host:
        return False, "host_missing"
    # Block cloud metadata and link-local by default
    if host in ("metadata.google.internal", "metadata") or host.endswith(".internal"):
        return False, "metadata_host_denied"
    if host in ("0.0.0.0",):
        return False, "host_denied"
    is_loop = host in ("localhost", "127.0.0.1", "::1") or host.startswith("127.")
    if is_loop and not allow_loopback:
        return False, "loopback_denied_set_SAATHI_INSFORGE_ALLOW_LOOPBACK"
    # Private ranges require explicit loopback/private allow (reuse allow_loopback for pilot)
    if _is_private_ip(host) and not allow_loopback and not is_loop:
        return False, "private_host_denied"
    if p.path and p.path not in ("", "/"):
        # base URL must be origin only
        return False, "base_url_must_be_origin_only"
    return True, "ok"


def _is_private_ip(host: str) -> bool:
    import ipaddress
    try:
        ip = ipaddress.ip_address(host)
        return bool(ip.is_private or ip.is_link_local or ip.is_reserved)
    except ValueError:
        return False


def is_path_allowed(path: str) -> bool:
    """True only for exact allowlisted GET paths (query stripped)."""
    if not path or not path.startswith("/"):
        return False
    clean = path.split("?", 1)[0].split("#", 1)[0]
    # normalize trailing slash
    if clean != "/" and clean.endswith("/"):
        clean = clean.rstrip("/")
    if clean in ALLOWED_PATHS:
        return True
    # /api/logs may take query only on exact path
    if clean == "/api/logs":
        return True
    return False


def is_path_blocked(path: str) -> bool:
    clean = (path or "").split("?", 1)[0]
    low = clean.lower()
    return any(low.startswith(p) or p.rstrip("/") == low for p in BLOCKED_PATH_PREFIXES)
