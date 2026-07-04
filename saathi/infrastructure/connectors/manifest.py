"""Connector Manifest — declarative, versioned capability description.

A manifest is data, not code: Diagnostics, Executive Intelligence, the registry,
and the UI all consume the SAME description. Adding an integration is writing a
driver + a manifest, never touching business logic or the registry.

    Manifest(
        id="telegram", display_name="Telegram", version=1, category="messaging",
        capabilities={"send_text", "send_photo", "send_video", "webhook"},
        permissions={"outbound", "inbound"},
        requires_auth=True, cost=0.0, latency="low", reliability=0.99,
        rate_limits={"requests_per_second": 30},
        health_checks={"token", "api"},
    )

`from_dict` accepts the nested YAML-style shape (supports/priority/cost blocks).
"""
from __future__ import annotations

from dataclasses import dataclass, field

_LATENCY_RANK = {"low": 1, "medium": 2, "high": 3}


@dataclass(frozen=True)
class Manifest:
    id: str
    capabilities: frozenset[str]
    display_name: str = ""
    version: int = 1
    category: str = "general"
    permissions: frozenset[str] = frozenset()
    requires_auth: bool = True
    cost: float = 0.0                          # relative $ per request (ranking)
    latency: str = "low"                       # low | medium | high
    reliability: float = 0.95                  # 0..1
    rate_limits: dict = field(default_factory=dict)     # {"requests_per_second": 30}
    health_checks: frozenset[str] = frozenset()          # {"token", "api"}

    @property
    def latency_rank(self) -> int:
        return _LATENCY_RANK.get(self.latency, 2)

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def as_dict(self) -> dict:
        return {
            "id": self.id, "display_name": self.display_name or self.id,
            "version": self.version, "category": self.category,
            "capabilities": sorted(self.capabilities),
            "permissions": sorted(self.permissions),
            "requires_auth": self.requires_auth,
            "cost": {"per_request": self.cost},
            "priority": {"reliability": self.reliability, "latency": self.latency},
            "rate_limits": self.rate_limits,
            "health_checks": sorted(self.health_checks),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Manifest":
        """Build from the nested YAML-style shape."""
        priority = d.get("priority", {})
        cost = d.get("cost", {})
        return cls(
            id=d["id"],
            capabilities=frozenset(d.get("supports") or d.get("capabilities") or []),
            display_name=d.get("display_name", ""),
            version=int(d.get("version", 1)),
            category=d.get("category", "general"),
            permissions=frozenset(d.get("permissions") or []),
            requires_auth=bool(d.get("requires_auth", True)),
            cost=float(cost.get("per_request", d.get("cost", 0.0)) if isinstance(cost, dict) else cost),
            latency=priority.get("latency", d.get("latency", "low")),
            reliability=float(priority.get("reliability", d.get("reliability", 0.95))),
            rate_limits=d.get("rate_limits", {}) or {},
            health_checks=frozenset(d.get("health_checks") or []),
        )


# Backward-compatible alias — the registry/base speak "manifest"; older code
# that said ConnectorMetadata keeps working (same fields).
ConnectorMetadata = Manifest
