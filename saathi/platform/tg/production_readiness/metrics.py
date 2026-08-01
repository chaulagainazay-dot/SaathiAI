"""M330 local metrics engine.

Deterministic, in-process, local-only. No Prometheus scrape endpoint, no StatsD
socket, no cloud monitoring agent. Percentiles are computed with the nearest-rank
method so a given sample set always yields identical numbers.
"""
from __future__ import annotations

from collections import deque
from threading import RLock
from typing import Any, Iterable, Mapping

from saathi.platform.tg.production_readiness.errors import (
    OperationsError,
    OperationsErrorCode,
)
from saathi.platform.tg.production_readiness.models import (
    BOUNDARY_VALUES,
    SCHEMA_VERSION,
    DeterministicClock,
    MetricKind,
    MetricSample,
    digest,
    redact,
    short_digest,
)

MAX_SAMPLES_PER_SERIES = 512

METRIC_UNITS = {
    MetricKind.API_LATENCY: "milliseconds",
    MetricKind.TASK_DURATION: "milliseconds",
    MetricKind.QUEUE_DEPTH: "items",
    MetricKind.CACHE_PERFORMANCE: "ratio",
    MetricKind.REPLAY_PERFORMANCE: "milliseconds",
    MetricKind.UI_PERFORMANCE: "milliseconds",
    MetricKind.DATABASE_PERFORMANCE: "milliseconds",
}

# Thresholds are advisory only: crossing one raises an offline alert and colours a
# dashboard cell. Nothing is throttled, scaled, restarted, or executed.
METRIC_THRESHOLDS = {
    MetricKind.API_LATENCY: {"warning": 250.0, "critical": 750.0, "direction": "above"},
    MetricKind.TASK_DURATION: {"warning": 1500.0, "critical": 5000.0, "direction": "above"},
    MetricKind.QUEUE_DEPTH: {"warning": 25.0, "critical": 100.0, "direction": "above"},
    MetricKind.CACHE_PERFORMANCE: {"warning": 0.80, "critical": 0.50, "direction": "below"},
    MetricKind.REPLAY_PERFORMANCE: {"warning": 120.0, "critical": 400.0, "direction": "above"},
    MetricKind.UI_PERFORMANCE: {"warning": 200.0, "critical": 600.0, "direction": "above"},
    MetricKind.DATABASE_PERFORMANCE: {"warning": 50.0, "critical": 200.0, "direction": "above"},
}

FORBIDDEN_METRIC_EXPORTERS = frozenset({
    "cloudwatch",
    "datadog",
    "dynatrace",
    "grafana_cloud",
    "influxdb",
    "newrelic",
    "opentelemetry",
    "prometheus",
    "signalfx",
    "stackdriver",
    "statsd",
})


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile — deterministic and interpolation-free."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, min(len(ordered), int(round(fraction * len(ordered) + 0.5))))
    return round(ordered[rank - 1], 6)


def classify(kind: MetricKind, value: float) -> str:
    threshold = METRIC_THRESHOLDS[kind]
    if threshold["direction"] == "above":
        if value >= threshold["critical"]:
            return "CRITICAL"
        if value >= threshold["warning"]:
            return "WARNING"
        return "OK"
    if value <= threshold["critical"]:
        return "CRITICAL"
    if value <= threshold["warning"]:
        return "WARNING"
    return "OK"


class MetricsEngine:
    def __init__(self, clock: DeterministicClock | None = None):
        self.clock = clock or DeterministicClock()
        self._lock = RLock()
        self._series: dict[tuple[str, str], deque[MetricSample]] = {}
        self._sequence = 0

    def record(
        self,
        kind: MetricKind | str,
        name: str,
        value: float,
        *,
        labels: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        kind = MetricKind(kind) if not isinstance(kind, MetricKind) else kind
        if not name:
            raise OperationsError(
                OperationsErrorCode.INVALID_REQUEST,
                "Metric requires a name",
            )
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise OperationsError(
                OperationsErrorCode.INVALID_REQUEST,
                "Metric value must be numeric",
                details={"name": name},
            ) from exc
        with self._lock:
            self._sequence += 1
            sample = MetricSample(
                metric_id="metric_" + short_digest({
                    "kind": kind.value,
                    "name": name,
                    "sequence": self._sequence,
                }, 14),
                kind=kind,
                name=name,
                value=round(numeric, 6),
                unit=METRIC_UNITS[kind],
                labels=redact(labels),
                recorded_at=self.clock.advance(),
                sequence=self._sequence,
            )
            key = (kind.value, name)
            series = self._series.setdefault(key, deque(maxlen=MAX_SAMPLES_PER_SERIES))
            series.append(sample)
        return {
            "ok": True,
            "sample": sample.to_dict(),
            "classification": classify(kind, sample.value),
            **BOUNDARY_VALUES,
        }

    def record_many(self, entries: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        recorded = [
            self.record(
                entry["kind"],
                entry["name"],
                entry["value"],
                labels=entry.get("labels"),
            )
            for entry in entries
        ]
        return {"ok": True, "count": len(recorded), "samples": recorded}

    def series(self, kind: MetricKind | str, name: str) -> dict[str, Any]:
        kind = MetricKind(kind) if not isinstance(kind, MetricKind) else kind
        with self._lock:
            samples = list(self._series.get((kind.value, name), ()))
        if not samples:
            raise OperationsError(
                OperationsErrorCode.INVALID_REQUEST,
                "No samples recorded for the requested series",
                details={"kind": kind.value, "name": name},
            )
        return {"ok": True, **self._summarize(kind, name, samples), **BOUNDARY_VALUES}

    def _summarize(
        self,
        kind: MetricKind,
        name: str,
        samples: list[MetricSample],
    ) -> dict[str, Any]:
        values = [sample.value for sample in samples]
        p95 = percentile(values, 0.95)
        return {
            "kind": kind.value,
            "name": name,
            "unit": METRIC_UNITS[kind],
            "count": len(values),
            "min": round(min(values), 6),
            "max": round(max(values), 6),
            "mean": round(sum(values) / len(values), 6),
            "p50": percentile(values, 0.50),
            "p95": p95,
            "p99": percentile(values, 0.99),
            "last": values[-1],
            "threshold": METRIC_THRESHOLDS[kind],
            "classification": classify(kind, p95),
            "samples": [sample.to_dict() for sample in samples[-25:]],
        }

    def summary(self) -> dict[str, Any]:
        with self._lock:
            keys = sorted(self._series)
            series = [
                self._summarize(MetricKind(kind), name, list(self._series[(kind, name)]))
                for kind, name in keys
            ]
        by_kind: dict[str, list[dict[str, Any]]] = {}
        for entry in series:
            by_kind.setdefault(entry["kind"], []).append(entry)
        breaches = [
            {"kind": entry["kind"], "name": entry["name"], "classification": entry["classification"]}
            for entry in series
            if entry["classification"] != "OK"
        ]
        covered = sorted(by_kind)
        missing = [kind.value for kind in MetricKind if kind.value not in by_kind]
        return {
            "ok": True,
            "milestone": "M330",
            "schema_version": SCHEMA_VERSION,
            "series_count": len(series),
            "sample_count": sum(entry["count"] for entry in series),
            "kinds": [kind.value for kind in MetricKind],
            "covered_kinds": covered,
            "missing_kinds": missing,
            "coverage_complete": not missing,
            "by_kind": {kind: by_kind[kind] for kind in covered},
            "threshold_breaches": breaches,
            "breach_count": len(breaches),
            "thresholds_are_advisory": True,
            "autoscaling_triggered": False,
            "cloud_monitoring_exporters": [],
            "forbidden_exporters": sorted(FORBIDDEN_METRIC_EXPORTERS),
            "clock": self.clock.snapshot(),
            "fingerprint": digest(series),
            **BOUNDARY_VALUES,
        }

    def reset(self) -> None:
        with self._lock:
            self._series.clear()
            self._sequence = 0


# Deterministic synthetic workload used to populate every required metric kind so
# the dashboard and certification have real series without touching a network.
BASELINE_WORKLOAD = (
    (MetricKind.API_LATENCY, "tg.operations.health", (18.0, 21.5, 19.25, 24.0, 31.75, 22.5)),
    (MetricKind.API_LATENCY, "tg.provider_contracts.request", (12.0, 14.5, 13.25, 16.0, 15.5)),
    (MetricKind.TASK_DURATION, "tg.replay.fixture_verify", (140.0, 155.0, 148.5, 162.0)),
    (MetricKind.TASK_DURATION, "tg.diagnostics.full_run", (620.0, 655.0, 640.0)),
    (MetricKind.QUEUE_DEPTH, "tg.research_orchestrator.queue", (0.0, 1.0, 2.0, 1.0, 0.0)),
    (MetricKind.QUEUE_DEPTH, "tg.alerts.pending", (0.0, 0.0, 1.0)),
    (MetricKind.CACHE_PERFORMANCE, "tg.fixtures.hit_ratio", (0.94, 0.96, 0.95, 0.97)),
    (MetricKind.CACHE_PERFORMANCE, "tg.capabilities.hit_ratio", (0.88, 0.91, 0.9)),
    (MetricKind.REPLAY_PERFORMANCE, "tg.replay.quote_dispatch", (8.5, 9.25, 8.75, 10.0)),
    (MetricKind.REPLAY_PERFORMANCE, "tg.replay.manifest_load", (21.0, 23.5, 22.0)),
    (MetricKind.UI_PERFORMANCE, "tg.ui.operations_dashboard_render", (86.0, 94.5, 90.0, 101.0)),
    (MetricKind.UI_PERFORMANCE, "tg.ui.health_panel_render", (42.0, 45.5, 44.0)),
    (MetricKind.DATABASE_PERFORMANCE, "tg.storage.audit_read", (3.5, 4.25, 3.75, 5.0)),
    (MetricKind.DATABASE_PERFORMANCE, "tg.storage.snapshot_write", (11.0, 12.5, 11.75)),
)


def seed_baseline(engine: MetricsEngine) -> dict[str, Any]:
    """Populate all seven metric kinds with reproducible offline observations."""
    for kind, name, values in BASELINE_WORKLOAD:
        for value in values:
            engine.record(kind, name, value, labels={"source": "offline_deterministic"})
    return engine.summary()
