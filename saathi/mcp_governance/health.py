"""MCP health adapter and CEO/Control Center summaries."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from saathi.mcp_governance import events as ev
from saathi.mcp_governance.inventory import CANONICAL_CODEBASE_MEMORY_ID, continuum_status
from saathi.mcp_governance.policy import is_enabled, timeout_policy

if TYPE_CHECKING:
    from saathi.mcp_governance.contract import CodebaseMemoryService


@dataclass
class McpHealth:
    configured: bool = False
    enabled: bool = False
    reachable: bool = False
    transport: str = ""
    latency_ms: float = 0.0
    backend_identity: str = ""
    namespace_available: bool = False
    read_test_result: str = "not_run"  # pass | fail | skipped | not_run
    write_test: str = "disabled"  # disabled | enabled | pass | fail
    last_error_category: str = ""
    last_successful_check: float = 0.0
    degraded_reason: str = ""
    mcp_id: str = CANONICAL_CODEBASE_MEMORY_ID
    continuum_status: str = "BLOCKED_LICENSE"
    status: str = "unknown"  # ok | degraded | unavailable | disabled

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def build_health(service: "CodebaseMemoryService") -> McpHealth:
    """Run a bounded health check against the service backend."""
    h = McpHealth(
        configured=service.backend is not None,
        enabled=is_enabled(CANONICAL_CODEBASE_MEMORY_ID),
        transport=getattr(service.backend, "identity", None) and "inprocess"
        or "stdio",
        write_test="disabled",
        continuum_status=continuum_status()["status"],
        mcp_id=CANONICAL_CODEBASE_MEMORY_ID,
    )
    if not h.enabled:
        h.status = "disabled"
        h.degraded_reason = "disabled by policy"
        h.read_test_result = "skipped"
        ev.emit(ev.MCP_HEALTH_CHECKED, h.to_dict())
        return h

    t0 = time.time()
    try:
        ping = service.backend.ping()
        h.reachable = bool(ping.get("ok", True))
        h.backend_identity = str(ping.get("backend_identity", ""))[:80]
        h.transport = str(ping.get("transport", h.transport))[:40]
        h.latency_ms = round((time.time() - t0) * 1000, 2)
        # namespace bound present
        h.namespace_available = bool(service.bound_namespace)
        # lightweight read test
        try:
            service.backend.search(service.bound_namespace, "", top_k=1)
            h.read_test_result = "pass"
        except Exception as e:
            h.read_test_result = "fail"
            h.last_error_category = type(e).__name__[:40]
        h.last_successful_check = time.time() if h.reachable else 0.0
        h.status = "ok" if h.reachable and h.read_test_result == "pass" else "degraded"
        if h.status != "ok":
            h.degraded_reason = h.last_error_category or "read_test_failed"
    except Exception as e:
        h.reachable = False
        h.status = "unavailable"
        h.degraded_reason = str(e)[:200]
        h.last_error_category = type(e).__name__[:40]
        h.read_test_result = "fail"
        h.latency_ms = round((time.time() - t0) * 1000, 2)
        ev.emit(ev.MCP_UNAVAILABLE, {"error_category": h.last_error_category})

    # honour timeouts in report
    h_to = timeout_policy()
    _ = h_to  # documented on health consumers via policy.timeout_policy()
    ev.emit(ev.MCP_HEALTH_CHECKED, {
        "status": h.status,
        "reachable": h.reachable,
        "latency_ms": h.latency_ms,
        "backend_identity": h.backend_identity,
    })
    return h


def health_snapshot(
    service: "CodebaseMemoryService | None" = None,
) -> dict[str, Any]:
    """Control Center / ops entry point."""
    if service is None:
        from saathi.mcp_governance.contract import default_memory_service
        service = default_memory_service()
    h = build_health(service)
    d = h.to_dict()
    d["timeouts"] = timeout_policy()
    d["bound_namespace"] = service.bound_namespace
    d["include_in_ceo_brief"] = h.status not in ("ok", "disabled") or bool(
        h.degraded_reason and h.status == "degraded"
    )
    # disabled is intentional — suppress CEO noise unless ops want it
    if h.status == "disabled":
        d["include_in_ceo_brief"] = False
    if h.status == "ok":
        d["include_in_ceo_brief"] = False
    return d


def ceo_mcp_summary(
    service: "CodebaseMemoryService | None" = None,
) -> dict[str, Any]:
    """CEO OS brief fragment — only when operationally relevant."""
    snap = health_snapshot(service)
    if not snap.get("include_in_ceo_brief"):
        return {"include_in_ceo_brief": False, "status": snap.get("status")}
    return {
        "include_in_ceo_brief": True,
        "status": snap.get("status"),
        "mcp_id": snap.get("mcp_id"),
        "degraded_reason": (snap.get("degraded_reason") or "")[:120],
        "last_error_category": snap.get("last_error_category") or "",
        "reachable": snap.get("reachable"),
        "continuum_status": snap.get("continuum_status"),
    }
