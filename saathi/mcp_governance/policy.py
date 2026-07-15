"""Project MCP enable/disable, timeout, and retry policy.

Secrets are never stored here — only env var *names* and bounded defaults.
"""
from __future__ import annotations

import os
import threading
from typing import Any

# Env disable switch (project-wide for codebase memory MCP)
ENV_DISABLE = "SAATHI_MCP_CODEBASE_MEMORY_DISABLED"
ENV_CONNECT_TIMEOUT = "SAATHI_MCP_CONNECT_TIMEOUT_SEC"
ENV_REQUEST_TIMEOUT = "SAATHI_MCP_REQUEST_TIMEOUT_SEC"
ENV_MAX_RETRIES = "SAATHI_MCP_MAX_RETRIES"

# Bounded defaults (seconds / counts)
DEFAULT_CONNECT_TIMEOUT_SEC = 5.0
DEFAULT_REQUEST_TIMEOUT_SEC = 30.0
DEFAULT_MAX_RETRIES = 2  # total attempts = 1 + retries for idempotent reads
MAX_CONNECT_TIMEOUT_SEC = 30.0
MAX_REQUEST_TIMEOUT_SEC = 120.0
MAX_RETRIES_CAP = 3

# Retryable categories for *idempotent reads only*
RETRYABLE_CATEGORIES = frozenset({
    "timeout",
    "connection",
    "temporary",
    "unavailable",
})

# Non-idempotent write ops — never blindly retried
NON_IDEMPOTENT_OPS = frozenset({
    "write_verified_lesson",
    "delete_or_archive_lesson",
    "rebuild_index",
})

_lock = threading.RLock()
_runtime_enabled: dict[str, bool] = {}


def is_enabled(mcp_id: str = "saathi-codebase-memory") -> bool:
    """Return whether the MCP is enabled (env + runtime switch)."""
    if os.getenv(ENV_DISABLE, "").strip().lower() in ("1", "true", "yes", "on"):
        return False
    with _lock:
        if mcp_id in _runtime_enabled:
            return _runtime_enabled[mcp_id]
    return True


def set_enabled(enabled: bool, mcp_id: str = "saathi-codebase-memory") -> None:
    """Runtime enable/disable (tests + Control Center). Does not write secrets."""
    with _lock:
        _runtime_enabled[mcp_id] = bool(enabled)


def reset_policy_state() -> None:
    """Test helper: clear runtime enable overrides."""
    with _lock:
        _runtime_enabled.clear()


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


def timeout_policy() -> dict[str, float]:
    """Bounded connection + request timeouts."""
    return {
        "connect_timeout_sec": _clamp_float(
            os.getenv(ENV_CONNECT_TIMEOUT),
            DEFAULT_CONNECT_TIMEOUT_SEC, 0.5, MAX_CONNECT_TIMEOUT_SEC,
        ),
        "request_timeout_sec": _clamp_float(
            os.getenv(ENV_REQUEST_TIMEOUT),
            DEFAULT_REQUEST_TIMEOUT_SEC, 1.0, MAX_REQUEST_TIMEOUT_SEC,
        ),
    }


def retry_policy(*, operation: str = "search") -> dict[str, Any]:
    """Retry policy: reads may retry; non-idempotent writes must not."""
    max_retries = _clamp_int(
        os.getenv(ENV_MAX_RETRIES), DEFAULT_MAX_RETRIES, 0, MAX_RETRIES_CAP,
    )
    op = (operation or "").strip().lower()
    if op in NON_IDEMPOTENT_OPS:
        return {
            "max_retries": 0,
            "retryable_categories": [],
            "non_idempotent": True,
            "operation": op,
            "blind_retry_forbidden": True,
        }
    return {
        "max_retries": max_retries,
        "retryable_categories": sorted(RETRYABLE_CATEGORIES),
        "non_idempotent": False,
        "operation": op,
        "blind_retry_forbidden": False,
    }


def should_retry(error_category: str, *, operation: str, attempt: int) -> bool:
    """Whether another attempt is allowed for this op/error/attempt."""
    pol = retry_policy(operation=operation)
    if pol["non_idempotent"] or pol["blind_retry_forbidden"]:
        return False
    if attempt >= int(pol["max_retries"]):
        return False
    return (error_category or "").lower() in RETRYABLE_CATEGORIES


# Project vs user-level placement policy (documentation + tests)
PROJECT_MCP_POLICY: dict[str, Any] = {
    "project_config_files": [
        "SaathiAI/.grok/config.toml",
        "docs/MCP_INVENTORY.md",
        "docs/EXTERNAL_CAPABILITY_STATUS.md",
    ],
    "user_level_ok": [
        "codebase-memory (home agent session)",
        "context7 (docs lookup)",
        "hosted OAuth MCP (GitHub/Gmail) — session only",
    ],
    "project_level_required_for_product": [
        "saathi-codebase-memory (via mcp_governance adapter)",
    ],
    "forbidden_in_project": [
        "unrestricted shell MCP",
        "live trading MCP",
        "production DB write MCP",
        "home-directory filesystem MCP",
        "continuum until BLOCKED_LICENSE cleared",
    ],
    "secrets": "reference env var names only; never commit values",
    "staging_vs_production": (
        "staging may enable experimental MCP with enabled=false default; "
        "production requires health + focused tests + disable switch"
    ),
    "unavailable_effect": (
        "core SaathiOS continues; search returns degraded; "
        "missions must not claim memory was consulted"
    ),
    "clients": {
        "grok": ".grok/config.toml + home ~/.grok/config.toml",
        "claude_code": "~/.claude.json (session) + project skills",
        "codex": "user MCP; project policy in docs",
        "opencode": "user MCP; project policy in docs",
        "saathios_native": "saathi.mcp_governance.CodebaseMemoryService",
    },
}
