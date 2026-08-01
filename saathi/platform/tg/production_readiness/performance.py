"""M334 offline performance and load validation.

Load is *modelled*, not generated: no threads are spawned, no sockets opened, no
sleeps taken. Each profile is a closed-form deterministic queueing model, so the same
profile always yields identical numbers — which is exactly what "deterministic
repeatability" requires for a certification gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from saathi.platform.tg.production_readiness.errors import (
    OperationsError,
    OperationsErrorCode,
)
from saathi.platform.tg.production_readiness.metrics import percentile
from saathi.platform.tg.production_readiness.models import (
    BOUNDARY_VALUES,
    SCHEMA_VERSION,
    DeterministicClock,
    digest,
)


@dataclass(frozen=True)
class LoadProfile:
    profile_id: str
    label: str
    dimension: str
    concurrency: int
    iterations: int
    base_cost_ms: float
    contention_ms: float
    service_capacity: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "label": self.label,
            "dimension": self.dimension,
            "concurrency": self.concurrency,
            "iterations": self.iterations,
            "base_cost_ms": self.base_cost_ms,
            "contention_ms": self.contention_ms,
            "service_capacity": self.service_capacity,
            "real_network_calls": 0,
            "real_threads_spawned": 0,
        }


LOAD_PROFILES = (
    LoadProfile(
        profile_id="load.concurrent_users",
        label="Concurrent operator sessions",
        dimension="concurrent_users",
        concurrency=25,
        iterations=40,
        base_cost_ms=18.0,
        contention_ms=0.65,
        service_capacity=16,
    ),
    LoadProfile(
        profile_id="load.multiple_agents",
        label="Multiple research agents",
        dimension="multiple_agents",
        concurrency=8,
        iterations=30,
        base_cost_ms=140.0,
        contention_ms=6.5,
        service_capacity=4,
    ),
    LoadProfile(
        profile_id="load.replay_workload",
        label="Replay fixture workload",
        dimension="replay_workload",
        concurrency=12,
        iterations=60,
        base_cost_ms=9.0,
        contention_ms=0.4,
        service_capacity=8,
    ),
    LoadProfile(
        profile_id="load.dashboard_refresh",
        label="Operations dashboard refresh",
        dimension="dashboard_refresh",
        concurrency=20,
        iterations=45,
        base_cost_ms=86.0,
        contention_ms=1.8,
        service_capacity=12,
    ),
    LoadProfile(
        profile_id="load.api_concurrency",
        label="Read-only API concurrency",
        dimension="api_concurrency",
        concurrency=32,
        iterations=50,
        base_cost_ms=21.0,
        contention_ms=0.9,
        service_capacity=20,
    ),
)

PROFILES_BY_ID = {profile.profile_id: profile for profile in LOAD_PROFILES}

# Advisory service objectives. A breach colours the dashboard and raises an offline
# alert; it never throttles, scales, or restarts anything.
LATENCY_OBJECTIVE_MS = {
    "concurrent_users": 120.0,
    "multiple_agents": 900.0,
    "replay_workload": 60.0,
    "dashboard_refresh": 400.0,
    "api_concurrency": 160.0,
}


def _simulate_latencies(profile: LoadProfile) -> list[float]:
    """Closed-form deterministic latency model.

    Each virtual request i is assigned to a service slot; queueing depth is how many
    prior requests share that slot. Cost grows with queue depth and with the excess of
    concurrency over capacity. No randomness, no wall clock, no I/O.
    """
    overload = max(0, profile.concurrency - profile.service_capacity)
    latencies: list[float] = []
    for index in range(profile.iterations):
        slot = index % profile.service_capacity
        queue_depth = (profile.concurrency - slot - 1) // profile.service_capacity
        # A small bounded phase term keeps the distribution non-degenerate while
        # staying fully reproducible.
        phase = ((index * 7) % 11) / 10.0
        latency = (
            profile.base_cost_ms
            + (queue_depth * profile.contention_ms * profile.service_capacity)
            + (overload * profile.contention_ms)
            + (phase * profile.contention_ms)
        )
        latencies.append(round(latency, 6))
    return latencies


def run_profile(profile_id: str, *, clock: DeterministicClock | None = None) -> dict[str, Any]:
    profile = PROFILES_BY_ID.get(profile_id)
    if profile is None:
        raise OperationsError(
            OperationsErrorCode.LOAD_PROFILE_UNKNOWN,
            "Unknown load profile",
            details={"profile_id": profile_id},
        )
    latencies = _simulate_latencies(profile)
    p95 = percentile(latencies, 0.95)
    objective = LATENCY_OBJECTIVE_MS[profile.dimension]
    total_ms = round(sum(latencies), 6)
    result = {
        "ok": True,
        "profile": profile.to_dict(),
        "sample_count": len(latencies),
        "min_ms": round(min(latencies), 6),
        "max_ms": round(max(latencies), 6),
        "mean_ms": round(sum(latencies) / len(latencies), 6),
        "p50_ms": percentile(latencies, 0.50),
        "p95_ms": p95,
        "p99_ms": percentile(latencies, 0.99),
        "total_modelled_ms": total_ms,
        "throughput_per_modelled_second": round(
            (len(latencies) * 1000.0) / total_ms, 6
        ) if total_ms else 0.0,
        "objective_ms": objective,
        "within_objective": p95 <= objective,
        "classification": "OK" if p95 <= objective else "BREACH",
        "latencies": latencies,
        "simulation_only": True,
        "wall_clock_sleep_used": False,
        "network_requests_issued": 0,
        "orders_submitted": 0,
        **BOUNDARY_VALUES,
    }
    result["fingerprint"] = digest({
        "profile_id": profile_id,
        "latencies": latencies,
    })
    if clock is not None:
        result["completed_at"] = clock.advance()
    return result


def run_all(*, clock: DeterministicClock | None = None) -> dict[str, Any]:
    runs = [run_profile(profile.profile_id, clock=clock) for profile in LOAD_PROFILES]
    breaches = [run["profile"]["profile_id"] for run in runs if not run["within_objective"]]
    dimensions = sorted({run["profile"]["dimension"] for run in runs})
    return {
        "ok": not breaches,
        "milestone": "M334",
        "name": "Offline Performance and Load Validation",
        "schema_version": SCHEMA_VERSION,
        "profile_count": len(runs),
        "dimensions": dimensions,
        "required_dimensions": sorted(LATENCY_OBJECTIVE_MS),
        "coverage_complete": dimensions == sorted(LATENCY_OBJECTIVE_MS),
        "runs": runs,
        "breaches": breaches,
        "deterministic": True,
        "simulation_only": True,
        "fingerprint": digest([run["fingerprint"] for run in runs]),
        **BOUNDARY_VALUES,
    }


def prove_repeatability(repetitions: int = 3) -> dict[str, Any]:
    """Run the full suite N times and prove the fingerprints are identical."""
    if repetitions < 2:
        raise OperationsError(
            OperationsErrorCode.INVALID_REQUEST,
            "Repeatability proof requires at least two repetitions",
        )
    fingerprints = [run_all()["fingerprint"] for _ in range(repetitions)]
    identical = len(set(fingerprints)) == 1
    return {
        "ok": identical,
        "repetitions": repetitions,
        "fingerprints": fingerprints,
        "identical": identical,
        "deterministic_repeatability": identical,
    }


def metric_entries(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Fold a load report into M330 metric samples so both surfaces agree."""
    entries: list[dict[str, Any]] = []
    for run in report.get("runs", []):
        entries.append({
            "kind": "task_duration",
            "name": f"tg.load.{run['profile']['dimension']}",
            "value": run["p95_ms"],
            "labels": {"source": "offline_load_model", "profile": run["profile"]["profile_id"]},
        })
    return entries
