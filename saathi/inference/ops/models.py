"""M26 — Inference operations state models."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class RolloutMode(str, Enum):
    OFF = "OFF"
    SHADOW = "SHADOW"
    CANARY = "CANARY"
    ACTIVE = "ACTIVE"
    DRAINING = "DRAINING"


class HealthStatus(str, Enum):
    """Is the SaathiOS inference operations process functioning?"""

    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    STOPPED = "STOPPED"


class ReadinessStatus(str, Enum):
    """Can the system safely accept a new governed inference request now?"""

    READY = "READY"
    DEGRADED = "DEGRADED"
    ENVIRONMENT_BLOCKED = "ENVIRONMENT_BLOCKED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    DRAINING = "DRAINING"
    UNHEALTHY = "UNHEALTHY"


class ProviderOpsState(str, Enum):
    """SaathiOS view of provider *session* readiness — not Ollama PID ownership."""

    UNKNOWN = "UNKNOWN"
    STARTING = "STARTING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    COOLDOWN = "COOLDOWN"
    DRAINING = "DRAINING"
    STOPPED = "STOPPED"


class ServicePhase(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DRAINING = "DRAINING"
    STOPPING = "STOPPING"
    RECOVERING = "RECOVERING"


# Valid rollout transitions (closed by default; invalid transitions fail closed)
VALID_MODE_TRANSITIONS: dict[RolloutMode, frozenset[RolloutMode]] = {
    RolloutMode.OFF: frozenset({
        RolloutMode.SHADOW, RolloutMode.CANARY, RolloutMode.ACTIVE, RolloutMode.OFF,
    }),
    RolloutMode.SHADOW: frozenset({
        RolloutMode.OFF, RolloutMode.CANARY, RolloutMode.ACTIVE,
        RolloutMode.DRAINING, RolloutMode.SHADOW,
    }),
    RolloutMode.CANARY: frozenset({
        RolloutMode.OFF, RolloutMode.SHADOW, RolloutMode.ACTIVE,
        RolloutMode.DRAINING, RolloutMode.CANARY,
    }),
    RolloutMode.ACTIVE: frozenset({
        RolloutMode.OFF, RolloutMode.DRAINING, RolloutMode.CANARY,
        RolloutMode.SHADOW, RolloutMode.ACTIVE,
    }),
    RolloutMode.DRAINING: frozenset({RolloutMode.OFF, RolloutMode.DRAINING}),
}


@dataclass
class CheckResult:
    check_id: str
    ok: bool
    detail: str = ""
    blocking: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HealthReport:
    status: HealthStatus
    phase: ServicePhase
    detail: str = ""
    checks: list[CheckResult] = field(default_factory=list)
    ownership: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "phase": self.phase.value,
            "detail": self.detail,
            "checks": [c.to_dict() for c in self.checks],
            "ownership": self.ownership,
        }


@dataclass
class ReadinessReport:
    status: ReadinessStatus
    ready: bool
    production_certified: bool
    rollout_mode: RolloutMode
    provider_state: ProviderOpsState
    checks: list[CheckResult] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    resources: dict[str, Any] = field(default_factory=dict)
    certification: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "ready": self.ready,
            "production_certified": self.production_certified,
            "rollout_mode": self.rollout_mode.value,
            "provider_state": self.provider_state.value,
            "checks": [c.to_dict() for c in self.checks],
            "blockers": list(self.blockers),
            "recommendations": list(self.recommendations),
            "resources": self.resources,
            "certification": self.certification,
        }


@dataclass
class IncidentRecord:
    incident_id: str
    incident_type: str
    severity: str  # low|medium|high|critical
    state: str  # open|resolved
    opened_at: str
    updated_at: str
    resolved_at: Optional[str] = None
    provider: str = "ollama"
    model: str = ""
    check_ids: list[str] = field(default_factory=list)
    safe_summary: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    recommended_action: str = ""
    resolution: str = ""
    fingerprint: str = ""  # for dedupe
    privacy_safe: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


INCIDENT_TYPES = frozenset({
    "provider_unreachable",
    "model_unavailable",
    "memory_pressure",
    "disk_pressure",
    "repeated_timeout",
    "invalid_provider_response",
    "reservation_reconciliation_failed",
    "circuit_open",
    "startup_failed",
    "shutdown_failed",
})

# Provider state transitions (session-level)
VALID_PROVIDER_TRANSITIONS: dict[ProviderOpsState, frozenset[ProviderOpsState]] = {
    ProviderOpsState.UNKNOWN: frozenset({
        ProviderOpsState.STARTING, ProviderOpsState.READY, ProviderOpsState.UNAVAILABLE,
        ProviderOpsState.STOPPED, ProviderOpsState.DEGRADED, ProviderOpsState.COOLDOWN,
    }),
    ProviderOpsState.STARTING: frozenset({
        ProviderOpsState.READY, ProviderOpsState.UNAVAILABLE, ProviderOpsState.STOPPED,
        ProviderOpsState.COOLDOWN, ProviderOpsState.DEGRADED,
    }),
    ProviderOpsState.READY: frozenset({
        ProviderOpsState.DEGRADED, ProviderOpsState.UNAVAILABLE, ProviderOpsState.COOLDOWN,
        ProviderOpsState.DRAINING, ProviderOpsState.STOPPED, ProviderOpsState.READY,
    }),
    ProviderOpsState.DEGRADED: frozenset({
        ProviderOpsState.READY, ProviderOpsState.UNAVAILABLE, ProviderOpsState.COOLDOWN,
        ProviderOpsState.DRAINING, ProviderOpsState.STOPPED, ProviderOpsState.DEGRADED,
    }),
    ProviderOpsState.UNAVAILABLE: frozenset({
        ProviderOpsState.STARTING, ProviderOpsState.READY, ProviderOpsState.COOLDOWN,
        ProviderOpsState.STOPPED, ProviderOpsState.UNAVAILABLE, ProviderOpsState.DEGRADED,
    }),
    ProviderOpsState.COOLDOWN: frozenset({
        ProviderOpsState.STARTING, ProviderOpsState.READY, ProviderOpsState.UNAVAILABLE,
        ProviderOpsState.STOPPED, ProviderOpsState.COOLDOWN, ProviderOpsState.DEGRADED,
    }),
    ProviderOpsState.DRAINING: frozenset({
        ProviderOpsState.STOPPED, ProviderOpsState.READY, ProviderOpsState.UNAVAILABLE,
        ProviderOpsState.DRAINING,
    }),
    ProviderOpsState.STOPPED: frozenset({
        ProviderOpsState.STARTING, ProviderOpsState.UNKNOWN, ProviderOpsState.STOPPED,
        ProviderOpsState.UNAVAILABLE,
    }),
}
