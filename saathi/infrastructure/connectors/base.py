"""Connector contract — SaathiAI's OS drivers for external services.

Every connector (Telegram, GitHub, n8n, YouTube, Runway, Binance, …) implements
the SAME interface and declares a capability manifest. Departments never import
an SDK; they call `registry.execute(capability=..., **payload)` and the registry
picks the best healthy connector — exactly like the Model Router picks a model.

Design mirrors `model_router`: declarative metadata (capabilities, cost, latency,
reliability), health-aware selection, injectable side-effects (HTTP transport,
event bus) so the whole layer is testable with no network.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


# ── standardized health events (published to the Event Fabric) ──────────────
class ConnectorEvent(str, Enum):
    CONNECTED = "connector.connected"
    FAILED = "connector.failed"
    RATE_LIMITED = "connector.rate_limited"
    AUTH_REQUIRED = "connector.auth_required"
    DEGRADED = "connector.degraded"


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


_LATENCY_RANK = {"low": 1, "medium": 2, "high": 3}


# ── exceptions ──────────────────────────────────────────────────────────────
class ConnectorError(Exception): ...
class AuthRequired(ConnectorError): ...
class RateLimited(ConnectorError): ...
class CapabilityUnsupported(ConnectorError): ...


# ── value types ─────────────────────────────────────────────────────────────
@dataclass
class Health:
    status: Status
    detail: str = ""
    metrics: dict = field(default_factory=dict)   # e.g. {"quota_pct": 83}
    checked_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ConnectorMetadata:
    id: str
    capabilities: frozenset[str]
    permissions: frozenset[str] = frozenset()      # e.g. {"outbound", "webhook"}
    requires_auth: bool = True
    cost: float = 0.0                               # relative $ per call
    latency: str = "low"                            # low | medium | high
    reliability: float = 0.95                       # 0..1
    rate_limits: str = ""                           # human-readable, e.g. "30/sec"

    @property
    def latency_rank(self) -> int:
        return _LATENCY_RANK.get(self.latency, 2)


# ── the contract ────────────────────────────────────────────────────────────
class Connector(ABC):
    id: str

    @abstractmethod
    def metadata(self) -> ConnectorMetadata: ...

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

    # derived — connectors rarely override these
    def capabilities(self) -> frozenset[str]:
        return self.metadata().capabilities

    def supports(self, capability: str) -> bool:
        return capability in self.metadata().capabilities

    def rate_limits(self) -> dict:
        return {"policy": self.metadata().rate_limits}

    def diagnostics(self) -> dict:
        m = self.metadata()
        h = self.health()
        return {"id": m.id, "status": h.status.value, "light": h.status.light,
                "detail": h.detail, "metrics": h.metrics,
                "authenticated": self.authenticate(),
                "capabilities": sorted(m.capabilities),
                "latency": m.latency, "cost": m.cost, "reliability": m.reliability}

    def _require(self, capability: str) -> None:
        if not self.supports(capability):
            raise CapabilityUnsupported(f"{self.id} cannot {capability!r}")
        if self.metadata().requires_auth and not self.authenticate():
            raise AuthRequired(f"{self.id} is not authenticated")
