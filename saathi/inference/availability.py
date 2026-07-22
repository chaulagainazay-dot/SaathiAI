"""M21.2 — Canonical provider availability and readiness model.

Separates configured / enabled / reachable / healthy / capability-compatible /
policy-eligible / production-certified. Live network probes are injectable;
unit tests use fakes (no live HTTP by default).
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class AvailabilityState(str, Enum):
    """Runtime availability (distinct from static M21.0 ProviderAvailability)."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    KILLED = "killed"
    MISCONFIGURED = "misconfigured"
    CIRCUIT_OPEN = "circuit_open"
    UNCERTIFIED = "uncertified"
    TEST_ONLY = "test_only"
    UNKNOWN = "unknown"
    FAKE = "fake"


# Deterministic precedence (lowest index wins / most severe).
AVAILABILITY_PRECEDENCE: tuple[AvailabilityState, ...] = (
    AvailabilityState.KILLED,
    AvailabilityState.DISABLED,
    AvailabilityState.MISCONFIGURED,
    AvailabilityState.CIRCUIT_OPEN,
    AvailabilityState.UNCERTIFIED,
    AvailabilityState.UNAVAILABLE,
    AvailabilityState.FAKE,
    AvailabilityState.TEST_ONLY,
    AvailabilityState.DEGRADED,
    AvailabilityState.AVAILABLE,
    AvailabilityState.UNKNOWN,
)

_PRECEDENCE_RANK = {s: i for i, s in enumerate(AVAILABILITY_PRECEDENCE)}


class HealthEvidenceTier(str, Enum):
    NONE = "none"
    POLICY = "policy"
    CONFIG = "config"
    INJECTED = "injected"
    PROBE = "probe"
    LIVE = "live"


@dataclass(frozen=True)
class ReadinessAxes:
    """Non-interchangeable readiness dimensions."""

    configured: bool = False
    enabled: bool = False
    reachable: Optional[bool] = None  # None = not probed
    healthy: Optional[bool] = None
    capability_compatible: bool = False
    policy_eligible: bool = False
    production_certified: bool = False
    credential_present: Optional[bool] = None
    kill_active: bool = False
    circuit_open: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AvailabilityDecision:
    """Explainable availability outcome for one provider."""

    provider_id: str
    state: AvailabilityState
    reason_code: str
    explanation: str  # redacted, operator-safe
    evidence_tier: str
    checked_at: float
    retry_allowed: bool
    failover_allowed: bool
    axes: ReadinessAxes = field(default_factory=ReadinessAxes)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        d["axes"] = self.axes.to_dict()
        return d


def most_severe_state(*states: AvailabilityState) -> AvailabilityState:
    """Return highest-severity (lowest rank) state among inputs."""
    if not states:
        return AvailabilityState.UNKNOWN
    return min(states, key=lambda s: _PRECEDENCE_RANK.get(s, 999))


def state_allows_attempt(state: AvailabilityState) -> bool:
    return state in {AvailabilityState.AVAILABLE, AvailabilityState.DEGRADED}


def state_retry_default(state: AvailabilityState) -> bool:
    return state in {
        AvailabilityState.UNAVAILABLE,
        AvailabilityState.DEGRADED,
        AvailabilityState.UNKNOWN,
    }


def state_failover_default(state: AvailabilityState) -> bool:
    """Soft availability issues may failover; hard policy states must not."""
    return state in {
        AvailabilityState.UNAVAILABLE,
        AvailabilityState.DEGRADED,
        AvailabilityState.CIRCUIT_OPEN,  # another provider may still be eligible
        AvailabilityState.UNKNOWN,
    }


HealthProbe = Callable[[str], dict[str, Any]]
# probe returns: {"reachable": bool, "healthy": bool, "reason": str, "tier": str}


def default_health_probe(_provider_id: str) -> dict[str, Any]:
    """No live network — unknown health (fail closed for production selection)."""
    return {
        "reachable": None,
        "healthy": None,
        "reason": "no_live_probe",
        "tier": HealthEvidenceTier.NONE.value,
    }


def evaluate_availability(
    provider_id: str,
    *,
    policy_enabled: bool,
    configured: bool,
    credential_required: bool,
    credential_present: Optional[bool],
    production_supported: bool,
    production_context: bool,
    provider_class: str,
    killed: bool,
    circuit_open: bool,
    capability_compatible: bool = True,
    policy_eligible: bool = True,
    degraded: bool = False,
    health_probe: Optional[HealthProbe] = None,
    now: Optional[float] = None,
) -> AvailabilityDecision:
    """Deterministic availability evaluation. Fail closed on unknowns when production."""
    checked = float(now if now is not None else time.time())
    pid = (provider_id or "").strip().lower() or "unknown"
    pclass = (provider_class or "").strip().lower()

    axes = ReadinessAxes(
        configured=configured,
        enabled=policy_enabled,
        capability_compatible=capability_compatible,
        policy_eligible=policy_eligible,
        production_certified=production_supported and production_context is False,
        # production_certified remains false globally; axis means "supported for prod path"
        credential_present=credential_present,
        kill_active=killed,
        circuit_open=circuit_open,
    )
    # Clarify certification axis: "eligible under production_supported flag"
    axes = ReadinessAxes(
        configured=configured,
        enabled=policy_enabled,
        capability_compatible=capability_compatible,
        policy_eligible=policy_eligible,
        production_certified=bool(production_supported),
        credential_present=credential_present,
        kill_active=killed,
        circuit_open=circuit_open,
    )

    if killed:
        return AvailabilityDecision(
            provider_id=pid,
            state=AvailabilityState.KILLED,
            reason_code="kill_switch_active",
            explanation="Provider or master kill switch is active",
            evidence_tier=HealthEvidenceTier.POLICY.value,
            checked_at=checked,
            retry_allowed=False,
            failover_allowed=False,
            axes=axes,
        )

    if not policy_enabled:
        return AvailabilityDecision(
            provider_id=pid,
            state=AvailabilityState.DISABLED,
            reason_code="policy_disabled",
            explanation="Provider disabled by policy or master flags",
            evidence_tier=HealthEvidenceTier.POLICY.value,
            checked_at=checked,
            retry_allowed=False,
            failover_allowed=False,
            axes=axes,
        )

    if pclass == "fake":
        if production_context:
            return AvailabilityDecision(
                provider_id=pid,
                state=AvailabilityState.FAKE,
                reason_code="fake_not_production",
                explanation="Fake provider cannot be selected in production posture",
                evidence_tier=HealthEvidenceTier.POLICY.value,
                checked_at=checked,
                retry_allowed=False,
                failover_allowed=False,
                axes=axes,
            )
        return AvailabilityDecision(
            provider_id=pid,
            state=AvailabilityState.TEST_ONLY,
            reason_code="fake_test_only",
            explanation="Fake provider allowed only in non-production environments",
            evidence_tier=HealthEvidenceTier.POLICY.value,
            checked_at=checked,
            retry_allowed=True,
            failover_allowed=False,
            axes=axes,
        )

    if not configured:
        return AvailabilityDecision(
            provider_id=pid,
            state=AvailabilityState.MISCONFIGURED,
            reason_code="not_configured",
            explanation="Provider configuration incomplete",
            evidence_tier=HealthEvidenceTier.CONFIG.value,
            checked_at=checked,
            retry_allowed=False,
            failover_allowed=True,
            axes=axes,
        )

    if credential_required and credential_present is False:
        return AvailabilityDecision(
            provider_id=pid,
            state=AvailabilityState.MISCONFIGURED,
            reason_code="credential_absent",
            explanation="Required credentials are not present (names redacted)",
            evidence_tier=HealthEvidenceTier.CONFIG.value,
            checked_at=checked,
            retry_allowed=False,
            failover_allowed=True,
            axes=axes,
        )

    if credential_required and credential_present is None:
        return AvailabilityDecision(
            provider_id=pid,
            state=AvailabilityState.MISCONFIGURED,
            reason_code="credential_state_unknown",
            explanation="Credential state unknown — fail closed",
            evidence_tier=HealthEvidenceTier.CONFIG.value,
            checked_at=checked,
            retry_allowed=False,
            failover_allowed=False,
            axes=axes,
        )

    if circuit_open:
        return AvailabilityDecision(
            provider_id=pid,
            state=AvailabilityState.CIRCUIT_OPEN,
            reason_code="circuit_open",
            explanation="Circuit breaker is open for this provider",
            evidence_tier=HealthEvidenceTier.POLICY.value,
            checked_at=checked,
            retry_allowed=False,
            failover_allowed=True,
            axes=axes,
        )

    if production_context and not production_supported:
        return AvailabilityDecision(
            provider_id=pid,
            state=AvailabilityState.UNCERTIFIED,
            reason_code="production_uncertified",
            explanation="Provider not production-supported under current certification",
            evidence_tier=HealthEvidenceTier.POLICY.value,
            checked_at=checked,
            retry_allowed=False,
            failover_allowed=False,
            axes=axes,
        )

    if not capability_compatible:
        return AvailabilityDecision(
            provider_id=pid,
            state=AvailabilityState.UNAVAILABLE,
            reason_code="capability_incompatible",
            explanation="Provider does not support required capability profile",
            evidence_tier=HealthEvidenceTier.POLICY.value,
            checked_at=checked,
            retry_allowed=False,
            failover_allowed=True,
            axes=axes,
        )

    if not policy_eligible:
        return AvailabilityDecision(
            provider_id=pid,
            state=AvailabilityState.DISABLED,
            reason_code="policy_ineligible",
            explanation="Caller/privacy/cost policy excludes this provider",
            evidence_tier=HealthEvidenceTier.POLICY.value,
            checked_at=checked,
            retry_allowed=False,
            failover_allowed=False,
            axes=axes,
        )

    # Health (injectable; default unknown)
    probe = health_probe or default_health_probe
    try:
        hr = probe(pid) or {}
    except Exception:
        hr = {
            "reachable": False,
            "healthy": False,
            "reason": "probe_error",
            "tier": HealthEvidenceTier.INJECTED.value,
        }

    reachable = hr.get("reachable")
    healthy = hr.get("healthy")
    tier = str(hr.get("tier") or HealthEvidenceTier.NONE.value)
    reason = str(hr.get("reason") or "health_checked")

    axes = ReadinessAxes(
        configured=configured,
        enabled=policy_enabled,
        reachable=reachable if isinstance(reachable, bool) else None,
        healthy=healthy if isinstance(healthy, bool) else None,
        capability_compatible=capability_compatible,
        policy_eligible=policy_eligible,
        production_certified=bool(production_supported),
        credential_present=credential_present,
        kill_active=killed,
        circuit_open=circuit_open,
    )

    if reachable is False or healthy is False:
        return AvailabilityDecision(
            provider_id=pid,
            state=AvailabilityState.UNAVAILABLE,
            reason_code="health_failed",
            explanation=f"Provider health failed ({reason})",
            evidence_tier=tier,
            checked_at=checked,
            retry_allowed=True,
            failover_allowed=True,
            axes=axes,
        )

    if reachable is None and healthy is None:
        # Unknown health: pilot/local may be degraded; production fails closed
        if production_context:
            return AvailabilityDecision(
                provider_id=pid,
                state=AvailabilityState.UNKNOWN,
                reason_code="health_unknown_production",
                explanation="Health unknown in production posture — not treated as available",
                evidence_tier=tier,
                checked_at=checked,
                retry_allowed=True,
                failover_allowed=True,
                axes=axes,
            )
        # Non-production / unit: allow degraded selection when policy says enabled
        if degraded:
            return AvailabilityDecision(
                provider_id=pid,
                state=AvailabilityState.DEGRADED,
                reason_code="health_unknown_degraded",
                explanation="Health not probed; marked degraded",
                evidence_tier=tier,
                checked_at=checked,
                retry_allowed=True,
                failover_allowed=True,
                axes=axes,
            )
        return AvailabilityDecision(
            provider_id=pid,
            state=AvailabilityState.DEGRADED,
            reason_code="health_not_probed",
            explanation="No live health probe; degraded for pilot selection only",
            evidence_tier=tier,
            checked_at=checked,
            retry_allowed=True,
            failover_allowed=True,
            axes=axes,
            metadata={"pilot_degraded_ok": True},
        )

    if degraded:
        return AvailabilityDecision(
            provider_id=pid,
            state=AvailabilityState.DEGRADED,
            reason_code="explicit_degraded",
            explanation="Provider marked degraded",
            evidence_tier=tier,
            checked_at=checked,
            retry_allowed=True,
            failover_allowed=True,
            axes=axes,
        )

    return AvailabilityDecision(
        provider_id=pid,
        state=AvailabilityState.AVAILABLE,
        reason_code="available",
        explanation="Provider available under policy and readiness checks",
        evidence_tier=tier,
        checked_at=checked,
        retry_allowed=True,
        failover_allowed=True,
        axes=axes,
    )
