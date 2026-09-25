"""M328 centralized system health framework.

One health engine. Every domain registers a probe; the engine rolls child states up
into a single platform verdict. Health is observation only — a FAILED component
never unlocks, activates, remediates, or escalates any authority.
"""
from __future__ import annotations

from threading import RLock
from typing import Any, Callable, Mapping

from saathi.platform.tg.production_readiness.errors import (
    OperationsError,
    OperationsErrorCode,
)
from saathi.platform.tg.production_readiness.models import (
    BOUNDARY_VALUES,
    HEALTH_RANK,
    SCHEMA_VERSION,
    DeterministicClock,
    HealthCheck,
    HealthDomain,
    HealthState,
    digest,
    worst_health,
)

Probe = Callable[[], HealthCheck]

# Domains that must be present for the framework to be considered complete. This
# mirrors the M328 deliverable list exactly.
REQUIRED_DOMAINS = (
    HealthDomain.PLATFORM,
    HealthDomain.MODULE,
    HealthDomain.DEPENDENCY,
    HealthDomain.STORAGE,
    HealthDomain.SCHEDULER,
    HealthDomain.REPLAY,
    HealthDomain.PROVIDER_REGISTRY,
)


class HealthEngine:
    def __init__(self, clock: DeterministicClock | None = None):
        self.clock = clock or DeterministicClock()
        self._lock = RLock()
        self._probes: dict[str, tuple[HealthDomain, Probe]] = {}
        self._overrides: dict[str, HealthState] = {}
        self._maintenance: set[str] = set()

    # ── registration ────────────────────────────────────────────────────────
    def register(self, component_id: str, domain: HealthDomain, probe: Probe) -> None:
        if not component_id:
            raise OperationsError(
                OperationsErrorCode.INVALID_REQUEST,
                "Health component requires an identifier",
            )
        with self._lock:
            self._probes[component_id] = (domain, probe)

    def registered_components(self) -> list[str]:
        with self._lock:
            return sorted(self._probes)

    def set_maintenance(self, component_id: str, enabled: bool = True) -> dict[str, Any]:
        with self._lock:
            if component_id not in self._probes:
                raise OperationsError(
                    OperationsErrorCode.COMPONENT_UNKNOWN,
                    "Unknown health component",
                    details={"component_id": component_id},
                )
            if enabled:
                self._maintenance.add(component_id)
            else:
                self._maintenance.discard(component_id)
        return {
            "ok": True,
            "component_id": component_id,
            "maintenance": enabled,
            "grants_authority": False,
        }

    def force_state(self, component_id: str, state: HealthState | str | None) -> dict[str, Any]:
        """Test/drill hook: pin a component state so degradation paths are provable."""
        with self._lock:
            if component_id not in self._probes:
                raise OperationsError(
                    OperationsErrorCode.COMPONENT_UNKNOWN,
                    "Unknown health component",
                    details={"component_id": component_id},
                )
            if state is None:
                self._overrides.pop(component_id, None)
            else:
                self._overrides[component_id] = (
                    state if isinstance(state, HealthState) else HealthState(state)
                )
        return {"ok": True, "component_id": component_id, "forced_state": str(state or "cleared")}

    # ── evaluation ──────────────────────────────────────────────────────────
    def _evaluate_component(self, component_id: str) -> HealthCheck:
        domain, probe = self._probes[component_id]
        try:
            check = probe()
        except Exception as exc:  # a probe fault is itself a FAILED signal
            return HealthCheck(
                component_id=component_id,
                domain=domain,
                state=HealthState.FAILED,
                reason="probe_raised",
                detail={"exception": type(exc).__name__},
                observed_at=self.clock.now(),
            )
        if component_id in self._maintenance:
            return HealthCheck(
                component_id=component_id,
                domain=domain,
                state=HealthState.MAINTENANCE,
                reason="planned_maintenance",
                detail=dict(check.detail),
                observed_at=self.clock.now(),
            )
        forced = self._overrides.get(component_id)
        if forced is not None:
            return HealthCheck(
                component_id=component_id,
                domain=domain,
                state=forced,
                reason="forced_state_drill",
                detail=dict(check.detail),
                observed_at=self.clock.now(),
            )
        return check

    def component(self, component_id: str) -> dict[str, Any]:
        with self._lock:
            if component_id not in self._probes:
                raise OperationsError(
                    OperationsErrorCode.COMPONENT_UNKNOWN,
                    "Unknown health component",
                    details={"component_id": component_id},
                )
            check = self._evaluate_component(component_id)
        return {"ok": True, "component": check.to_dict(), **BOUNDARY_VALUES}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            component_ids = sorted(self._probes)
            checks = [self._evaluate_component(cid) for cid in component_ids]

        by_domain: dict[str, dict[str, Any]] = {}
        for check in checks:
            bucket = by_domain.setdefault(check.domain.value, {
                "domain": check.domain.value,
                "components": [],
                "states": [],
            })
            bucket["components"].append(check.to_dict())
            bucket["states"].append(check.state)
        for bucket in by_domain.values():
            rolled = worst_health(bucket["states"])
            bucket["state"] = rolled.value
            bucket["rank"] = HEALTH_RANK[rolled]
            bucket["component_count"] = len(bucket["components"])
            bucket.pop("states")

        overall = worst_health([check.state for check in checks])
        counts = {state.value: 0 for state in HealthState}
        for check in checks:
            counts[check.state.value] += 1
        missing = [
            domain.value for domain in REQUIRED_DOMAINS if domain.value not in by_domain
        ]
        return {
            "ok": True,
            "milestone": "M328",
            "schema_version": SCHEMA_VERSION,
            "overall_state": overall.value,
            "overall_rank": HEALTH_RANK[overall],
            "component_count": len(checks),
            "counts": counts,
            "supported_states": [state.value for state in HealthState],
            "domains": [by_domain[key] for key in sorted(by_domain)],
            "required_domains": [domain.value for domain in REQUIRED_DOMAINS],
            "missing_required_domains": missing,
            "domain_coverage_complete": not missing,
            "maintenance_components": sorted(self._maintenance),
            "degradation_triggers_remediation": False,
            "health_grants_authority": False,
            "observed_at": self.clock.now(),
            "fingerprint": digest([check.to_dict() for check in checks]),
            **BOUNDARY_VALUES,
        }

    def rollup_proof(self) -> dict[str, Any]:
        """Prove the reduction: the worst child state always wins at the parent."""
        cases = [
            ([HealthState.HEALTHY, HealthState.HEALTHY], HealthState.HEALTHY),
            ([HealthState.HEALTHY, HealthState.MAINTENANCE], HealthState.MAINTENANCE),
            ([HealthState.MAINTENANCE, HealthState.WARNING], HealthState.WARNING),
            ([HealthState.WARNING, HealthState.DEGRADED], HealthState.DEGRADED),
            ([HealthState.DEGRADED, HealthState.FAILED], HealthState.FAILED),
            ([HealthState.FAILED, HealthState.HEALTHY], HealthState.FAILED),
            ([], HealthState.HEALTHY),
        ]
        proofs = []
        for children, expected in cases:
            actual = worst_health(list(children))
            proofs.append({
                "children": [child.value for child in children],
                "expected": expected.value,
                "actual": actual.value,
                "correct": actual is expected,
            })
        return {
            "ok": all(proof["correct"] for proof in proofs),
            "proofs": proofs,
            "ranking": {state.value: rank for state, rank in HEALTH_RANK.items()},
            "worst_state_wins": True,
        }


def build_health_engine(
    service: Any,
    clock: DeterministicClock | None = None,
) -> HealthEngine:
    """Wire the required M328 domains onto the composed operations service."""
    engine = HealthEngine(clock=clock)
    now = engine.clock.now

    def platform_probe() -> HealthCheck:
        locks_ok = service.authority_locks_ok()
        return HealthCheck(
            component_id="platform.core",
            domain=HealthDomain.PLATFORM,
            state=HealthState.HEALTHY if locks_ok else HealthState.FAILED,
            reason="authority_locks_intact" if locks_ok else "authority_lock_breach",
            detail={"schema_version": SCHEMA_VERSION, "offline_only": True},
            observed_at=now(),
        )

    def module_probe() -> HealthCheck:
        modules = service.module_inventory()
        loaded = [name for name, ok in modules.items() if ok]
        missing = [name for name, ok in modules.items() if not ok]
        if missing:
            state = HealthState.DEGRADED if loaded else HealthState.FAILED
        else:
            state = HealthState.HEALTHY
        return HealthCheck(
            component_id="platform.modules",
            domain=HealthDomain.MODULE,
            state=state,
            reason="modules_loaded" if not missing else "modules_missing",
            detail={"loaded": sorted(loaded), "missing": sorted(missing)},
            observed_at=now(),
        )

    def dependency_probe() -> HealthCheck:
        deps = service.dependency_inventory()
        unmet = [name for name, ok in deps.items() if not ok]
        return HealthCheck(
            component_id="platform.dependencies",
            domain=HealthDomain.DEPENDENCY,
            state=HealthState.HEALTHY if not unmet else HealthState.DEGRADED,
            reason="dependencies_satisfied" if not unmet else "dependencies_unmet",
            detail={"checked": sorted(deps), "unmet": sorted(unmet), "network_dependencies": 0},
            observed_at=now(),
        )

    def storage_probe() -> HealthCheck:
        report = service.storage_health()
        return HealthCheck(
            component_id="platform.storage",
            domain=HealthDomain.STORAGE,
            state=HealthState.HEALTHY if report["ok"] else HealthState.FAILED,
            reason=report["reason"],
            detail=report["detail"],
            observed_at=now(),
        )

    def scheduler_probe() -> HealthCheck:
        report = service.scheduler_health()
        if report["ok"]:
            state = HealthState.WARNING if report["backlog"] else HealthState.HEALTHY
        else:
            state = HealthState.DEGRADED
        return HealthCheck(
            component_id="platform.scheduler",
            domain=HealthDomain.SCHEDULER,
            state=state,
            reason=report["reason"],
            detail=report["detail"],
            observed_at=now(),
        )

    def replay_probe() -> HealthCheck:
        report = service.replay_health()
        return HealthCheck(
            component_id="platform.replay_engine",
            domain=HealthDomain.REPLAY,
            state=HealthState.HEALTHY if report["ok"] else HealthState.DEGRADED,
            reason=report["reason"],
            detail=report["detail"],
            observed_at=now(),
        )

    def registry_probe() -> HealthCheck:
        report = service.provider_registry_health()
        return HealthCheck(
            component_id="platform.provider_registry",
            domain=HealthDomain.PROVIDER_REGISTRY,
            state=HealthState.HEALTHY if report["ok"] else HealthState.DEGRADED,
            reason=report["reason"],
            detail=report["detail"],
            observed_at=now(),
        )

    engine.register("platform.core", HealthDomain.PLATFORM, platform_probe)
    engine.register("platform.modules", HealthDomain.MODULE, module_probe)
    engine.register("platform.dependencies", HealthDomain.DEPENDENCY, dependency_probe)
    engine.register("platform.storage", HealthDomain.STORAGE, storage_probe)
    engine.register("platform.scheduler", HealthDomain.SCHEDULER, scheduler_probe)
    engine.register("platform.replay_engine", HealthDomain.REPLAY, replay_probe)
    engine.register("platform.provider_registry", HealthDomain.PROVIDER_REGISTRY, registry_probe)
    return engine


def health_to_alert_severity(state: HealthState | str) -> str | None:
    """Map a health state onto the M331 severity ladder. HEALTHY raises nothing."""
    state = state if isinstance(state, HealthState) else HealthState(state)
    if state is HealthState.HEALTHY:
        return None
    if state is HealthState.MAINTENANCE:
        return "INFORMATIONAL"
    if state is HealthState.WARNING:
        return "WARNING"
    return "CRITICAL"


def summarize(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "overall_state": snapshot.get("overall_state"),
        "component_count": snapshot.get("component_count"),
        "counts": snapshot.get("counts"),
        "domain_coverage_complete": snapshot.get("domain_coverage_complete"),
    }
