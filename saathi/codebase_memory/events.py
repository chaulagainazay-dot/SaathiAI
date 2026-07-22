"""Privacy-safe observability for codebase memory indexing/retrieval."""
from __future__ import annotations

from typing import Any

from saathi.mcp_governance.redaction import redact_obj, safe_summary

_RECENT: list[dict] = []
_MAX = 200

EVENT_TYPES = frozenset({
    "index_started", "index_completed", "index_failed", "index_disabled",
    "index_stale", "index_corrupt", "incremental_refresh_completed",
    "query_completed", "query_degraded", "query_denied",
    "namespace_mismatch", "secret_exclusion", "rebuild_required",
    "resource_limit_reached",
})


def emit(event_type: str, payload: dict | None = None) -> dict:
    body = safe_summary(redact_obj(payload or {}))
    for banned in ("content", "text", "secret", "password", "token", "body"):
        body.pop(banned, None)
    rec = {"type": event_type, "source": "codebase_memory", "payload": body}
    _RECENT.append(rec)
    if len(_RECENT) > _MAX:
        del _RECENT[: len(_RECENT) - _MAX]
    try:
        from saathi.mcp_governance import events as gov
        # map to mcp_* where useful
        gov.emit(f"mcp_{event_type}" if not event_type.startswith("mcp_") else event_type, body)
    except Exception:
        pass
    return rec


def recent(limit: int = 40) -> list[dict]:
    return list(_RECENT[-limit:])


def clear() -> None:
    _RECENT.clear()
