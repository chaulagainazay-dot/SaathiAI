"""Bounded MCP observability events. Never emit full memory content."""
from __future__ import annotations

from typing import Any

from saathi.mcp_governance.redaction import redact_obj, safe_summary

# Stable event type names (also used in SecurityStore audit detail)
MCP_HEALTH_CHECKED = "mcp_health_checked"
MCP_UNAVAILABLE = "mcp_unavailable"
MCP_SEARCH_SUCCEEDED = "mcp_search_succeeded"
MCP_SEARCH_FAILED = "mcp_search_failed"
MCP_WRITE_REQUESTED = "mcp_write_requested"
MCP_WRITE_DENIED = "mcp_write_denied"
MCP_WRITE_SUCCEEDED = "mcp_write_succeeded"
MCP_SECRET_REJECTED = "mcp_secret_rejected"
MCP_NAMESPACE_VIOLATION = "mcp_namespace_violation"

ALL_EVENT_TYPES = frozenset({
    MCP_HEALTH_CHECKED,
    MCP_UNAVAILABLE,
    MCP_SEARCH_SUCCEEDED,
    MCP_SEARCH_FAILED,
    MCP_WRITE_REQUESTED,
    MCP_WRITE_DENIED,
    MCP_WRITE_SUCCEEDED,
    MCP_SECRET_REJECTED,
    MCP_NAMESPACE_VIOLATION,
})

# In-process ring for tests when bus is unavailable
_RECENT: list[dict] = []
_RECENT_MAX = 100


def recent_events(limit: int = 40) -> list[dict]:
    return list(_RECENT[-limit:])


def clear_events() -> None:
    _RECENT.clear()


def emit(event_type: str, payload: dict | None = None, *, source: str = "mcp_governance") -> dict:
    """Emit a bounded, redacted event to the platform bus when available."""
    if event_type not in ALL_EVENT_TYPES:
        event_type = str(event_type)[:64]
    body = safe_summary(redact_obj(payload or {}))
    # Hard ban full lesson/content fields
    for banned in ("content", "lesson", "raw", "full_text", "body"):
        body.pop(banned, None)
    record = {"type": event_type, "source": source, "payload": body}
    _RECENT.append(record)
    if len(_RECENT) > _RECENT_MAX:
        del _RECENT[: len(_RECENT) - _RECENT_MAX]
    try:
        from saathi.events import bus as bus_mod
        b = getattr(bus_mod, "default_bus", None)
        if callable(b):
            b().emit(event_type, source, body)
        elif hasattr(bus_mod, "bus") and hasattr(bus_mod.bus, "emit"):
            bus_mod.bus.emit(event_type, source, body)
    except Exception:
        pass
    return record


def audit_security(event: str, *, ok: bool = True, detail: str = "", user_id: str = "") -> None:
    """Record denial/failure in SecurityStore when available."""
    try:
        from saathi.security.store import get_store
        store = get_store()
        store.audit(
            event,
            ok=ok,
            user_id=user_id or "system",
            detail=(detail or "")[:400],
        )
    except Exception:
        pass
    try:
        from saathi.security.timeline import Timeline
        # best-effort; timeline API may vary
        tl = Timeline()
        if hasattr(tl, "record"):
            tl.record(user_id or "system", event, event, detail=detail[:200])
    except Exception:
        pass
