"""M328–M335 production readiness, observability and operational resilience models.

Offline-only. This module grants no provider, broker, credential, OAuth, account,
balance, position, order, canary, deployment, or live-trading authority. It is an
observation and diagnostics layer composed onto the existing governance stack.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from saathi.platform.tg.connectivity_governance.models import (
    AUTHORITY_VALUES as GOVERNANCE_AUTHORITY_VALUES,
)
from saathi.platform.tg.provider_contracts.models import (
    AUTHORITY_LOCKS as PROVIDER_AUTHORITY_LOCKS,
)

SCHEMA_VERSION = "m328.production_readiness.v1"
ENGINE_VERSION = "m328.production_readiness.engine.v1"
TERMINAL_VERDICT = (
    "PRODUCTION_READINESS_AND_OPERATIONAL_RESILIENCE_CERTIFIED_WITH_LIMITATIONS"
)
NOT_CERTIFIED_VERDICT = "PRODUCTION_READINESS_NOT_CERTIFIED"
MAX_STATE = "OPERATIONALLY_READY_OFFLINE"
CURRENT_MATURITY = "OPERATIONALLY_READY_OFFLINE"
BROWSER_CERT_VERDICT = (
    "PRODUCTION_READINESS_OPERATIONAL_RESILIENCE_BROWSER_CERT_PASSED_WITH_LIMITATIONS"
)

# Deterministic epoch used by every offline engine in this milestone. No wall clock
# is read anywhere in the M328–M335 surface, so repeated runs are byte-identical.
DETERMINISTIC_EPOCH = 1_767_225_600.0  # 2026-01-01T00:00:00Z
DETERMINISTIC_TICK_SECONDS = 0.25

HARD_AUTHORITY_KEYS = (
    "REAL_CONNECTIVITY_AUTHORIZED",
    "BROKER_CONNECTIVITY_AUTHORIZED",
    "OAUTH_AUTHORIZED",
    "CREDENTIAL_PROVISIONING_AUTHORIZED",
    "ACCOUNT_ACCESS_AUTHORIZED",
    "BALANCE_READ_AUTHORIZED",
    "POSITION_READ_AUTHORIZED",
    "ORDER_SUBMISSION_AUTHORIZED",
    "ORDER_EXECUTION_AUTHORIZED",
    "CANARY_ACTIVATION_AUTHORIZED",
    "LIVE_TRADING_AUTHORIZED",
)

# Inherited locks that must also stay false while this milestone is active.
INHERITED_AUTHORITY_KEYS = tuple(sorted(PROVIDER_AUTHORITY_LOCKS))

AUTHORITY_LOCKS = {key: False for key in HARD_AUTHORITY_KEYS}
INHERITED_AUTHORITY_LOCKS = {key: False for key in INHERITED_AUTHORITY_KEYS}

OPERATIONAL_ASSERTIONS = {
    "OFFLINE_OBSERVABILITY_ONLY": True,
    "NO_EXTERNAL_TELEMETRY": True,
    "NO_CLOUD_MONITORING": True,
    "NO_EMAIL_ALERTS": True,
    "NO_SMS_ALERTS": True,
    "NO_PUSH_ALERTS": True,
    "NO_CLOUD_BACKUP": True,
    "NO_DEPLOYMENT_CONTROL": True,
    "NO_EXECUTION_CONTROL": True,
    "READ_ONLY_OPERATIONS_DASHBOARD": True,
    "DETERMINISTIC_ENGINE": True,
}

BOUNDARY_VALUES = {
    **AUTHORITY_LOCKS,
    **INHERITED_AUTHORITY_LOCKS,
    **OPERATIONAL_ASSERTIONS,
    "PRODUCTION_AUTHORIZED": False,
    "DEPLOYMENT_AUTHORIZED": False,
    "EXTERNAL_TELEMETRY_AUTHORIZED": False,
    "CLOUD_MONITORING_AUTHORIZED": False,
    "CLOUD_BACKUP_AUTHORIZED": False,
    "PAPER_EXECUTION_AUTHORIZED": False,
    "real_connectivity": False,
    "authenticated": False,
    "credentials_present": False,
    "network_transport_available": False,
    "offline_only": True,
    "read_only": True,
    "deterministic": True,
    "current_maturity": CURRENT_MATURITY,
    "max_state": MAX_STATE,
}

TERMINAL_STATEMENTS = (
    "OFFLINE OPERATIONS DATA",
    "READ-ONLY OPERATIONS DASHBOARD",
    "NO EXECUTION CONTROLS",
    "NO DEPLOYMENT CONTROLS",
    "NO PROVIDER CONNECTION",
    "NO ACCOUNT ACCESS",
    "NO ORDER EXECUTION",
    "NO EXTERNAL TELEMETRY OR CLOUD MONITORING",
    "NO EMAIL, SMS, OR PUSH ALERTING",
    "NO CLOUD BACKUP",
    "DETERMINISTIC OFFLINE MEASUREMENTS ONLY",
)


class HealthState(str, Enum):
    """The five health states required by M328, ordered worst-last for reduction."""

    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    MAINTENANCE = "MAINTENANCE"


# Severity ordering used when rolling child health up into a parent. MAINTENANCE is
# deliberately ranked above HEALTHY but below WARNING: a component under planned
# maintenance is not healthy, but it is not an incident either.
HEALTH_RANK = {
    HealthState.HEALTHY: 0,
    HealthState.MAINTENANCE: 1,
    HealthState.WARNING: 2,
    HealthState.DEGRADED: 3,
    HealthState.FAILED: 4,
}


def worst_health(states: list[HealthState]) -> HealthState:
    if not states:
        return HealthState.HEALTHY
    return max(states, key=lambda state: HEALTH_RANK[state])


class HealthDomain(str, Enum):
    PLATFORM = "platform"
    MODULE = "module"
    DEPENDENCY = "dependency"
    STORAGE = "storage"
    SCHEDULER = "scheduler"
    REPLAY = "replay"
    PROVIDER_REGISTRY = "provider_registry"


class AlertSeverity(str, Enum):
    INFORMATIONAL = "INFORMATIONAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


ALERT_SEVERITY_RANK = {
    AlertSeverity.INFORMATIONAL: 0,
    AlertSeverity.WARNING: 1,
    AlertSeverity.CRITICAL: 2,
}


class AlertDestination(str, Enum):
    CONTROL_CENTER = "control_center"
    LOCAL_LOG = "local_log"
    AUDIT_HISTORY = "audit_history"


FORBIDDEN_ALERT_DESTINATIONS = frozenset({
    "email",
    "smtp",
    "sms",
    "twilio",
    "push",
    "apns",
    "fcm",
    "webhook",
    "slack",
    "pagerduty",
    "opsgenie",
    "discord",
    "telegram",
})


class AlertState(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class MetricKind(str, Enum):
    API_LATENCY = "api_latency"
    TASK_DURATION = "task_duration"
    QUEUE_DEPTH = "queue_depth"
    CACHE_PERFORMANCE = "cache_performance"
    REPLAY_PERFORMANCE = "replay_performance"
    UI_PERFORMANCE = "ui_performance"
    DATABASE_PERFORMANCE = "database_performance"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class DiagnosticStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


class BackupKind(str, Enum):
    CONFIGURATION = "configuration"
    REPLAY_SNAPSHOT = "replay_snapshot"
    DATABASE = "database"


class RecoveryOutcome(str, Enum):
    SIMULATED_SUCCESS = "SIMULATED_SUCCESS"
    SIMULATED_FAILURE = "SIMULATED_FAILURE"
    INTEGRITY_MISMATCH = "INTEGRITY_MISMATCH"


# Fields that may never appear in a log record, metric label, alert payload,
# diagnostic report, or backup manifest emitted by this milestone.
FORBIDDEN_OBSERVABILITY_FIELDS = frozenset({
    "access_token",
    "account",
    "account_id",
    "api_key",
    "api_secret",
    "balance",
    "bearer_token",
    "client_secret",
    "credential",
    "credentials",
    "fill_id",
    "oauth",
    "oauth_code",
    "order",
    "order_id",
    "passphrase",
    "password",
    "position",
    "private_key",
    "refresh_token",
    "secret",
    "session_cookie",
    "token",
})

REDACTION_MARKER = "[REDACTED]"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def short_digest(value: Any, size: int = 16) -> str:
    return digest(value)[:size]


def authority_locks_intact() -> bool:
    """Every hard authority key must be false here, in governance and in contracts."""
    for key in HARD_AUTHORITY_KEYS:
        if AUTHORITY_LOCKS[key] is not False:
            return False
        if GOVERNANCE_AUTHORITY_VALUES.get(key, False) is not False:
            return False
    for key, value in PROVIDER_AUTHORITY_LOCKS.items():
        if value is not False:
            return False
        if INHERITED_AUTHORITY_LOCKS.get(key, False) is not False:
            return False
    return True


def redact(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Recursively replace forbidden field values with a redaction marker."""
    if not payload:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if str(key).lower() in FORBIDDEN_OBSERVABILITY_FIELDS:
            cleaned[key] = REDACTION_MARKER
        elif isinstance(value, Mapping):
            cleaned[key] = redact(value)
        elif isinstance(value, (list, tuple)):
            cleaned[key] = [
                redact(item) if isinstance(item, Mapping) else item for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned


class DeterministicClock:
    """Monotonic, wall-clock-free clock so every emitted artefact is reproducible."""

    def __init__(self, epoch: float = DETERMINISTIC_EPOCH, tick: float = DETERMINISTIC_TICK_SECONDS):
        self._epoch = float(epoch)
        self._tick = float(tick)
        self._ticks = 0

    @property
    def epoch(self) -> float:
        return self._epoch

    def now(self) -> float:
        return round(self._epoch + (self._ticks * self._tick), 6)

    def advance(self, ticks: int = 1) -> float:
        self._ticks += int(ticks)
        return self.now()

    def reset(self) -> None:
        self._ticks = 0

    def snapshot(self) -> dict[str, Any]:
        return {
            "epoch": self._epoch,
            "tick_seconds": self._tick,
            "ticks_elapsed": self._ticks,
            "now": self.now(),
            "wall_clock_used": False,
            "deterministic": True,
        }


@dataclass(frozen=True)
class HealthCheck:
    component_id: str
    domain: HealthDomain
    state: HealthState
    reason: str
    detail: Mapping[str, Any] = field(default_factory=dict)
    observed_at: float = DETERMINISTIC_EPOCH

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "domain": self.domain.value,
            "state": self.state.value,
            "rank": HEALTH_RANK[self.state],
            "reason": self.reason,
            "detail": redact(self.detail),
            "observed_at": self.observed_at,
            "actionable": self.state
            in (HealthState.WARNING, HealthState.DEGRADED, HealthState.FAILED),
            "grants_authority": False,
        }


@dataclass(frozen=True)
class LogRecord:
    record_id: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    level: LogLevel
    component: str
    operation: str
    message: str
    fields: Mapping[str, Any]
    sequence: int
    emitted_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "level": self.level.value,
            "component": self.component,
            "operation": self.operation,
            "message": self.message,
            "fields": redact(self.fields),
            "sequence": self.sequence,
            "emitted_at": self.emitted_at,
            "schema_version": SCHEMA_VERSION,
            "exported_externally": False,
            "local_only": True,
        }


@dataclass(frozen=True)
class MetricSample:
    metric_id: str
    kind: MetricKind
    name: str
    value: float
    unit: str
    labels: Mapping[str, Any]
    recorded_at: float
    sequence: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "kind": self.kind.value,
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "labels": redact(self.labels),
            "recorded_at": self.recorded_at,
            "sequence": self.sequence,
            "cloud_exported": False,
            "local_only": True,
        }


@dataclass(frozen=True)
class Alert:
    alert_id: str
    severity: AlertSeverity
    state: AlertState
    source: str
    title: str
    detail: Mapping[str, Any]
    destinations: tuple[AlertDestination, ...]
    trace_id: str
    raised_at: float
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "severity": self.severity.value,
            "severity_rank": ALERT_SEVERITY_RANK[self.severity],
            "state": self.state.value,
            "source": self.source,
            "title": self.title,
            "detail": redact(self.detail),
            "destinations": [destination.value for destination in self.destinations],
            "trace_id": self.trace_id,
            "raised_at": self.raised_at,
            "updated_at": self.updated_at,
            "email_sent": False,
            "sms_sent": False,
            "push_sent": False,
            "external_delivery": False,
            "triggers_execution": False,
        }


@dataclass(frozen=True)
class BackupSnapshot:
    snapshot_id: str
    kind: BackupKind
    label: str
    payload_digest: str
    item_count: int
    size_bytes: int
    created_at: float
    manifest: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "kind": self.kind.value,
            "label": self.label,
            "payload_digest": self.payload_digest,
            "item_count": self.item_count,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
            "manifest": redact(self.manifest),
            "storage_location": "local_offline",
            "cloud_replicated": False,
            "contains_credentials": False,
            "contains_account_data": False,
        }


@dataclass(frozen=True)
class DiagnosticResult:
    check_id: str
    subsystem: str
    status: DiagnosticStatus
    summary: str
    detail: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "subsystem": self.subsystem,
            "status": self.status.value,
            "summary": self.summary,
            "detail": redact(self.detail),
            "remediates_automatically": False,
        }
