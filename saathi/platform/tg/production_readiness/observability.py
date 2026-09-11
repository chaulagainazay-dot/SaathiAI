"""M329 unified offline observability — structured logs, correlation, traces, timelines.

Everything stays in-process and on local disk. No external telemetry exporter, no
OTLP endpoint, no cloud sink, and no network transport is reachable from here.
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
    FORBIDDEN_OBSERVABILITY_FIELDS,
    REDACTION_MARKER,
    SCHEMA_VERSION,
    DeterministicClock,
    LogLevel,
    LogRecord,
    digest,
    redact,
    short_digest,
)

MAX_RECORDS = 2000
MAX_TIMELINE_OPERATIONS = 500

# Telemetry exporters that must never be importable from the observability surface.
FORBIDDEN_TELEMETRY_MODULES = frozenset({
    "azure",
    "boto3",
    "datadog",
    "ddtrace",
    "elasticapm",
    "google",
    "honeycomb",
    "logging_loki",
    "newrelic",
    "opencensus",
    "opentelemetry",
    "prometheus_client",
    "rollbar",
    "sentry_sdk",
    "statsd",
})


class TraceContext:
    """A correlation scope. Trace and span identifiers are content-derived, not random."""

    def __init__(
        self,
        trace_id: str,
        span_id: str,
        parent_span_id: str | None,
        operation: str,
        component: str,
    ):
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.operation = operation
        self.component = component

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "operation": self.operation,
            "component": self.component,
        }


class ObservabilityEngine:
    """Single local sink for structured logs, correlation and operation timelines."""

    def __init__(self, clock: DeterministicClock | None = None):
        self.clock = clock or DeterministicClock()
        self._lock = RLock()
        self._records: deque[LogRecord] = deque(maxlen=MAX_RECORDS)
        self._sequence = 0
        self._timelines: dict[str, list[dict[str, Any]]] = {}
        self._timeline_order: deque[str] = deque(maxlen=MAX_TIMELINE_OPERATIONS)

    # ── correlation ─────────────────────────────────────────────────────────
    def start_trace(
        self,
        operation: str,
        component: str,
        *,
        parent: TraceContext | None = None,
        correlation_key: str | None = None,
    ) -> TraceContext:
        """Derive a trace deterministically from its operation, component and lineage."""
        if not operation or not component:
            raise OperationsError(
                OperationsErrorCode.INVALID_REQUEST,
                "Trace requires an operation and a component",
            )
        trace_id = parent.trace_id if parent else "trace_" + short_digest({
            "operation": operation,
            "component": component,
            "correlation_key": correlation_key or operation,
        })
        span_id = "span_" + short_digest({
            "trace_id": trace_id,
            "operation": operation,
            "component": component,
            "parent": parent.span_id if parent else None,
            "sequence": self._sequence,
        }, 12)
        return TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent.span_id if parent else None,
            operation=operation,
            component=component,
        )

    # ── structured logging ──────────────────────────────────────────────────
    def log(
        self,
        level: LogLevel | str,
        message: str,
        *,
        trace: TraceContext,
        fields: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        level = LogLevel(level) if not isinstance(level, LogLevel) else level
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
            emitted_at = self.clock.advance()
            record = LogRecord(
                record_id="log_" + short_digest({
                    "trace_id": trace.trace_id,
                    "span_id": trace.span_id,
                    "sequence": sequence,
                }, 14),
                trace_id=trace.trace_id,
                span_id=trace.span_id,
                parent_span_id=trace.parent_span_id,
                level=level,
                component=trace.component,
                operation=trace.operation,
                message=message,
                fields=redact(fields),
                sequence=sequence,
                emitted_at=emitted_at,
            )
            self._records.append(record)
            self._append_timeline(record)
            return record.to_dict()

    def _append_timeline(self, record: LogRecord) -> None:
        entries = self._timelines.setdefault(record.operation, [])
        if record.operation not in self._timeline_order:
            self._timeline_order.append(record.operation)
        entries.append({
            "sequence": record.sequence,
            "trace_id": record.trace_id,
            "span_id": record.span_id,
            "parent_span_id": record.parent_span_id,
            "level": record.level.value,
            "component": record.component,
            "message": record.message,
            "at": record.emitted_at,
        })

    # ── reads ───────────────────────────────────────────────────────────────
    def records(
        self,
        *,
        limit: int = 200,
        level: LogLevel | str | None = None,
        component: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            rows = list(self._records)
        if level is not None:
            wanted = LogLevel(level) if not isinstance(level, LogLevel) else level
            rows = [row for row in rows if row.level is wanted]
        if component:
            rows = [row for row in rows if row.component == component]
        if trace_id:
            rows = [row for row in rows if row.trace_id == trace_id]
        rows = rows[-int(limit):] if limit else rows
        return {
            "ok": True,
            "count": len(rows),
            "records": [row.to_dict() for row in rows],
            "schema_version": SCHEMA_VERSION,
            "sink": "local_process_ring_buffer",
            "external_exporters": [],
            **BOUNDARY_VALUES,
        }

    def trace(self, trace_id: str) -> dict[str, Any]:
        with self._lock:
            rows = [row for row in self._records if row.trace_id == trace_id]
        if not rows:
            raise OperationsError(
                OperationsErrorCode.INVALID_REQUEST,
                "No correlated records exist for the requested trace",
                details={"trace_id": trace_id},
            )
        spans: dict[str, dict[str, Any]] = {}
        for row in rows:
            span = spans.setdefault(row.span_id, {
                "span_id": row.span_id,
                "parent_span_id": row.parent_span_id,
                "operation": row.operation,
                "component": row.component,
                "first_sequence": row.sequence,
                "last_sequence": row.sequence,
                "started_at": row.emitted_at,
                "ended_at": row.emitted_at,
                "record_count": 0,
            })
            span["last_sequence"] = row.sequence
            span["ended_at"] = row.emitted_at
            span["record_count"] += 1
        for span in spans.values():
            span["duration_seconds"] = round(span["ended_at"] - span["started_at"], 6)
        ordered = sorted(spans.values(), key=lambda span: span["first_sequence"])
        return {
            "ok": True,
            "trace_id": trace_id,
            "span_count": len(ordered),
            "record_count": len(rows),
            "spans": ordered,
            "records": [row.to_dict() for row in rows],
            "root_spans": [span for span in ordered if span["parent_span_id"] is None],
            **BOUNDARY_VALUES,
        }

    def timelines(self, *, limit: int = 50) -> dict[str, Any]:
        with self._lock:
            operations = list(self._timeline_order)[-int(limit):]
            payload = []
            for operation in operations:
                entries = self._timelines.get(operation, [])
                payload.append({
                    "operation": operation,
                    "entry_count": len(entries),
                    "first_at": entries[0]["at"] if entries else None,
                    "last_at": entries[-1]["at"] if entries else None,
                    "duration_seconds": round(entries[-1]["at"] - entries[0]["at"], 6)
                    if entries else 0.0,
                    "entries": entries[-40:],
                })
        return {
            "ok": True,
            "count": len(payload),
            "timelines": payload,
            **BOUNDARY_VALUES,
        }

    def execution_history(self, *, limit: int = 100) -> dict[str, Any]:
        """Operation-level history. Execution here means engine operations, never orders."""
        with self._lock:
            rows = list(self._records)[-int(limit):]
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            entry = grouped.setdefault(row.trace_id, {
                "trace_id": row.trace_id,
                "operations": [],
                "components": [],
                "levels": [],
                "started_at": row.emitted_at,
                "ended_at": row.emitted_at,
                "record_count": 0,
            })
            if row.operation not in entry["operations"]:
                entry["operations"].append(row.operation)
            if row.component not in entry["components"]:
                entry["components"].append(row.component)
            if row.level.value not in entry["levels"]:
                entry["levels"].append(row.level.value)
            entry["ended_at"] = row.emitted_at
            entry["record_count"] += 1
        history = sorted(grouped.values(), key=lambda item: item["started_at"])
        for entry in history:
            entry["duration_seconds"] = round(entry["ended_at"] - entry["started_at"], 6)
            entry["order_execution"] = False
            entry["provider_calls"] = 0
        return {
            "ok": True,
            "count": len(history),
            "history": history,
            "order_execution_records": 0,
            **BOUNDARY_VALUES,
        }

    def audit_visualization(self, audit_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        """Fold governance audit rows into a render-ready, redacted timeline."""
        rows = list(audit_rows)
        by_kind: dict[str, int] = {}
        by_actor: dict[str, int] = {}
        lanes: list[dict[str, Any]] = []
        for row in rows:
            kind = str(row.get("kind", "unknown"))
            actor = str(row.get("actor", "unknown"))
            by_kind[kind] = by_kind.get(kind, 0) + 1
            by_actor[actor] = by_actor.get(actor, 0) + 1
            lanes.append({
                "id": row.get("id"),
                "kind": kind,
                "actor": actor,
                "subject": row.get("subject", ""),
                "evidence_hash": row.get("evidence_hash"),
                "created_at": row.get("created_at"),
                "detail": redact(row.get("detail") or {}),
            })
        lanes.sort(key=lambda lane: (lane.get("created_at") or 0))
        return {
            "ok": True,
            "count": len(lanes),
            "lanes": lanes,
            "by_kind": dict(sorted(by_kind.items())),
            "by_actor": dict(sorted(by_actor.items())),
            "distinct_kinds": len(by_kind),
            "distinct_actors": len(by_actor),
            "render_mode": "read_only_local_visualization",
            **BOUNDARY_VALUES,
        }

    # ── integrity ───────────────────────────────────────────────────────────
    def redaction_scan(self) -> dict[str, Any]:
        """Prove no forbidden field value survived into any retained record."""
        findings: list[dict[str, Any]] = []
        with self._lock:
            rows = list(self._records)
        for row in rows:
            for key, value in row.fields.items():
                if str(key).lower() in FORBIDDEN_OBSERVABILITY_FIELDS and value != REDACTION_MARKER:
                    findings.append({"record_id": row.record_id, "field": key})
        return {
            "ok": not findings,
            "records_scanned": len(rows),
            "findings": findings,
            "forbidden_fields": sorted(FORBIDDEN_OBSERVABILITY_FIELDS),
            "redaction_marker": REDACTION_MARKER,
        }

    def posture(self) -> dict[str, Any]:
        with self._lock:
            record_count = len(self._records)
            sequence = self._sequence
        return {
            "ok": True,
            "milestone": "M329",
            "name": "Unified Offline Observability",
            "record_count": record_count,
            "sequence": sequence,
            "capacity": MAX_RECORDS,
            "levels": [level.value for level in LogLevel],
            "sink": "local_process_ring_buffer",
            "external_telemetry_providers": [],
            "forbidden_telemetry_modules": sorted(FORBIDDEN_TELEMETRY_MODULES),
            "trace_id_source": "content_derived_deterministic",
            "clock": self.clock.snapshot(),
            **BOUNDARY_VALUES,
        }

    def fingerprint(self) -> str:
        with self._lock:
            return digest([
                {
                    "sequence": row.sequence,
                    "trace_id": row.trace_id,
                    "operation": row.operation,
                    "level": row.level.value,
                    "message": row.message,
                }
                for row in self._records
            ])
