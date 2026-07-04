"""Connector contract — SaathiAI's OS drivers for external services.

Every connector (Telegram, GitHub, n8n, YouTube, Filesystem, …) implements the
SAME interface and declares a Manifest. Departments never import an SDK; they
call `registry.execute(capability=..., **payload)` and the registry picks the
best healthy connector — exactly like the Model Router picks a model.

Layering: Infrastructure *Services* (registry, diagnostics) are SaathiAI's
abstractions; *Drivers* under `drivers/` are the only place SDK/provider details
live. Swapping an SDK touches one driver, never the service layer.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from .manifest import Manifest, ConnectorMetadata  # noqa: F401  (re-export)


# ── standardized health/lifecycle events (published to the Event Fabric) ────
class ConnectorEvent(str, Enum):
    CONNECTED = "connector.connected"
    DISCONNECTED = "connector.disconnected"
    FAILED = "connector.failed"
    DEGRADED = "connector.degraded"
    RATE_LIMITED = "connector.rate_limited"
    AUTH_REQUIRED = "connector.auth_required"
    QUOTA_WARNING = "connector.quota_warning"
    EXECUTED = "connector.executed"


class Status(str, Enum):
    OK = "ok"                 # 🟢
    DEGRADED = "degraded"     # 🟡  (quota high, partial)
    DOWN = "down"             # 🔴
    AUTH_REQUIRED = "auth"    # 🔴  (missing/expired credentials)
    UNKNOWN = "unknown"

    @property
    def light(self) -> str:
        return {"ok": "🟢", "degraded": "🟡", "down": "🔴",
                "auth": "🔴", "unknown": "⚪"}[self.value]

    @property
    def usable(self) -> bool:
        return self in (Status.OK, Status.DEGRADED)


# ── exceptions ──────────────────────────────────────────────────────────────
class ConnectorError(Exception): ...
class AuthRequired(ConnectorError): ...
class RateLimited(ConnectorError): ...
class CapabilityUnsupported(ConnectorError): ...


# ── health value type ───────────────────────────────────────────────────────
@dataclass
class Health:
    status: Status
    detail: str = ""
    metrics: dict = field(default_factory=dict)   # e.g. {"quota_remaining": 82}
    checked_at: float = field(default_factory=time.time)


# ── the contract ────────────────────────────────────────────────────────────
class Connector(ABC):
    id: str
    # diagnostic state — the registry stamps these around execute()
    _last_success: float | None = None
    _last_error: str | None = None

    @abstractmethod
    def manifest(self) -> Manifest: ...

    @abstractmethod
    def authenticate(self) -> bool:
        """True if usable credentials are present. Cheap, no network."""

    @abstractmethod
    def health(self) -> Health:
        """Live status. May hit the network; catch and map failures to Status."""

    @abstractmethod
    def execute(self, capability: str, **payload):
        """Run one capability. Raise CapabilityUnsupported / AuthRequired /
        RateLimited / ConnectorError as appropriate."""

    # ── derived — connectors rarely override these ──────────────────────
    def metadata(self) -> Manifest:            # legacy alias
        return self.manifest()

    def capabilities(self) -> frozenset[str]:
        return self.manifest().capabilities

    def supports(self, capability: str) -> bool:
        return capability in self.manifest().capabilities

    def rate_limits(self) -> dict:
        return self.manifest().rate_limits

    def diagnostics(self) -> dict:
        """First-class, uniform health snapshot the dashboard aggregates."""
        t0 = time.monotonic()
        h = self.health()
        latency_ms = round((time.monotonic() - t0) * 1000)
        m = self.manifest()
        return {
            "id": m.id,
            "display_name": m.display_name or m.id,
            "category": m.category,
            "healthy": h.status.usable,
            "status": h.status.value,
            "light": h.status.light,
            "detail": h.detail,
            "latency_ms": latency_ms,
            "quota_remaining": h.metrics.get("quota_remaining"),
            "authenticated": self.authenticate(),
            "last_success": self._last_success,
            "last_error": self._last_error,
            "capabilities": sorted(m.capabilities),
        }

    def _require(self, capability: str) -> None:
        if not self.supports(capability):
            raise CapabilityUnsupported(f"{self.id} cannot {capability!r}")
        if self.manifest().requires_auth and not self.authenticate():
            raise AuthRequired(f"{self.id} is not authenticated")
