"""M62.7 — circuit-breaker safety domain (durable, deterministic, PAPER-only).

Automated operational safety on top of the M62.5 paper broker and the M62.6
reconciliation engine. Breakers may HALT, FREEZE, REJECT, ACKNOWLEDGE and (under
fail-closed policy) RESET a scope. They NEVER repair financial state, never touch
fills/positions/cash/ledger, and never enable any live/production/broker capability.

Everything here is a pure data + state-machine definition. Nothing opens a socket,
holds a secret, or reaches a real broker.
"""
from __future__ import annotations

import hashlib
import json
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from saathi.platform.trading_models import D, Environment
from saathi.platform.paper_trading.models import (
    PROHIBITED_CONFIG_TOKENS, PaperSafetyError, q2,
)

SAFETY_ENGINE_VERSION = "paper-safety/1.0.0"
DEFAULT_CALENDAR = "DEFAULT_24_5"
DEFAULT_TIMEZONE = "UTC"

# M62.7 extends the M62.5 prohibited set with a few operational tokens. A breaker
# definition or config that references any of these fails closed at construction.
PROHIBITED_SAFETY_TOKENS = PROHIBITED_CONFIG_TOKENS | frozenset({
    "AUTONOMOUS_CAPITAL", "EXTERNAL_EXECUTION", "PRODUCTION",
})


def assert_safety_safe(config: dict | None = None, *, environment: Environment | str | None = None) -> None:
    """Fail closed: refuse any prohibited capability or non-PAPER environment."""
    if environment is not None:
        env = environment if isinstance(environment, Environment) else Environment(str(environment))
        if env != Environment.PAPER:
            raise PaperSafetyError(f"safety subsystem operates only in PAPER (got {env.value})")
    cfg = config or {}
    for key, value in cfg.items():
        token = str(key).upper()
        if token in PROHIBITED_SAFETY_TOKENS and bool(value):
            raise PaperSafetyError(f"prohibited capability enabled: {token}")
        if isinstance(value, str) and value.upper() in PROHIBITED_SAFETY_TOKENS:
            raise PaperSafetyError(f"prohibited capability referenced: {value.upper()}")


# ── deterministic hashing ──────────────────────────────────────────────────────
def shash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


# ── timezone-aware trading-day boundary ─────────────────────────────────────────
def resolve_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, KeyError, ValueError) as exc:
        raise PaperSafetyError(f"unknown timezone: {name}") from exc


def trading_day(ts: float | None, *, tz_name: str = DEFAULT_TIMEZONE) -> dict[str, Any]:
    """Deterministic trading-day window for an epoch timestamp in a named tz.

    Fails closed on a missing timestamp (naive/None). Returns the day key plus the
    epoch [start, end) boundaries so daily loss windows never drift with wall-clock.
    """
    if ts is None:
        raise PaperSafetyError("trading-day boundary requires an explicit timestamp (naive/None rejected)")
    tz = resolve_tz(tz_name)
    dt = datetime.fromtimestamp(float(ts), tz=tz)
    start_local = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = start_local.timestamp()
    # end = start of next day (exclusive)
    next_day = datetime.fromtimestamp(day_start + 86400 + 3600, tz=tz).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return {"day": start_local.strftime("%Y-%m-%d"), "tz": tz_name,
            "start": day_start, "end": next_day.timestamp()}


def assert_aware_epoch(ts: Any) -> float:
    """Reject naive/None; a bare float epoch is treated as UTC-anchored and OK."""
    if ts is None:
        raise PaperSafetyError("timestamp required (naive/None rejected)")
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            raise PaperSafetyError("naive datetime rejected; timezone-aware required")
        return ts.timestamp()
    return float(ts)


# ── enums ───────────────────────────────────────────────────────────────────────
class BreakerType(str, Enum):
    DAILY_REALIZED_LOSS = "DAILY_REALIZED_LOSS"
    DAILY_TOTAL_LOSS = "DAILY_TOTAL_LOSS"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    GROSS_EXPOSURE = "GROSS_EXPOSURE"
    POSITION_CONCENTRATION = "POSITION_CONCENTRATION"
    OPEN_ORDER_COUNT = "OPEN_ORDER_COUNT"
    ORDER_REJECTION_RATE = "ORDER_REJECTION_RATE"
    PROCESSING_FAILURE = "PROCESSING_FAILURE"
    RECONCILIATION_CRITICAL = "RECONCILIATION_CRITICAL"
    RECONCILIATION_ERROR_STREAK = "RECONCILIATION_ERROR_STREAK"
    STALE_MARKET_DATA = "STALE_MARKET_DATA"
    INVALID_MARKET_DATA = "INVALID_MARKET_DATA"
    ACCOUNTING_INVARIANT = "ACCOUNTING_INVARIANT"
    MANUAL_KILL_SWITCH = "MANUAL_KILL_SWITCH"


class BreakerScope(str, Enum):
    GLOBAL_PAPER = "GLOBAL_PAPER"
    TENANT = "TENANT"
    WORKSPACE = "WORKSPACE"
    PAPER_ACCOUNT = "PAPER_ACCOUNT"
    STRATEGY_VERSION = "STRATEGY_VERSION"
    INSTRUMENT = "INSTRUMENT"
    MARKET_DATA_SOURCE = "MARKET_DATA_SOURCE"
    PAPER_BROKER_PROCESSOR = "PAPER_BROKER_PROCESSOR"


# scopes whose manual trip requires owner/admin (broad blast radius)
BROAD_SCOPES = frozenset({BreakerScope.GLOBAL_PAPER, BreakerScope.TENANT})


class BreakerState(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    TRIPPED = "TRIPPED"          # threshold detected, halt being enforced
    HALTED = "HALTED"            # scope actively blocked
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESET_PENDING = "RESET_PENDING"
    RESET = "RESET"             # transient terminal → returns to NORMAL


# states in which the scope is actively blocked (Guardian must veto)
BLOCKING_STATES = frozenset({BreakerState.TRIPPED, BreakerState.HALTED,
                             BreakerState.ACKNOWLEDGED, BreakerState.RESET_PENDING})

BREAKER_TRANSITIONS: dict[BreakerState, frozenset[BreakerState]] = {
    BreakerState.NORMAL: frozenset({BreakerState.WARNING, BreakerState.TRIPPED}),
    BreakerState.WARNING: frozenset({BreakerState.NORMAL, BreakerState.TRIPPED}),
    BreakerState.TRIPPED: frozenset({BreakerState.HALTED}),
    BreakerState.HALTED: frozenset({BreakerState.ACKNOWLEDGED, BreakerState.HALTED}),
    BreakerState.ACKNOWLEDGED: frozenset({BreakerState.RESET_PENDING, BreakerState.HALTED}),
    BreakerState.RESET_PENDING: frozenset({BreakerState.RESET, BreakerState.HALTED, BreakerState.ACKNOWLEDGED}),
    BreakerState.RESET: frozenset({BreakerState.NORMAL, BreakerState.TRIPPED}),
}


def can_breaker_transition(cur: BreakerState | str, tgt: BreakerState | str) -> bool:
    c = cur if isinstance(cur, BreakerState) else BreakerState(cur)
    t = tgt if isinstance(tgt, BreakerState) else BreakerState(tgt)
    return t in BREAKER_TRANSITIONS.get(c, frozenset())


class OpenOrderPolicy(str, Enum):
    FREEZE_OPEN_ORDERS = "FREEZE_OPEN_ORDERS"
    CANCEL_REMAINING_QUANTITY = "CANCEL_REMAINING_QUANTITY"


class AlertLevel(str, Enum):
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SweepStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# default alert level + open-order policy per breaker type (deterministic, versioned)
_INTEGRITY_TYPES = frozenset({
    BreakerType.RECONCILIATION_CRITICAL, BreakerType.ACCOUNTING_INVARIANT,
    BreakerType.PROCESSING_FAILURE, BreakerType.INVALID_MARKET_DATA,
})


def default_open_order_policy(btype: BreakerType) -> OpenOrderPolicy:
    # Integrity / processor / corrupted-data / emergency → freeze (don't touch orders);
    # loss / drawdown / exposure / concentration / rejection → cancel remaining qty.
    if btype in _INTEGRITY_TYPES or btype in (
            BreakerType.STALE_MARKET_DATA, BreakerType.RECONCILIATION_ERROR_STREAK,
            BreakerType.MANUAL_KILL_SWITCH):
        return OpenOrderPolicy.FREEZE_OPEN_ORDERS
    return OpenOrderPolicy.CANCEL_REMAINING_QUANTITY


def default_alert_level(btype: BreakerType) -> AlertLevel:
    if btype in (BreakerType.RECONCILIATION_CRITICAL, BreakerType.ACCOUNTING_INVARIANT,
                 BreakerType.INVALID_MARKET_DATA):
        return AlertLevel.CRITICAL
    return AlertLevel.ERROR


# ── durable breaker definition ───────────────────────────────────────────────────
@dataclass
class CircuitBreakerDefinition:
    id: str
    org_id: str
    breaker_type: BreakerType
    scope: BreakerScope
    scope_ref: str = ""                       # account id / symbol / source / strategy version / ""
    workspace_id: str = ""
    threshold: Decimal = field(default_factory=lambda: Decimal("0"))
    warning_threshold: Decimal | None = None  # optional soft threshold → WARNING
    window_seconds: int = 0                   # 0 = point-in-time / daily
    min_samples: int = 0                      # min denominator for rate/window breakers
    severity: Severity = Severity.ERROR
    auto_trip: bool = True
    open_order_policy: OpenOrderPolicy = OpenOrderPolicy.FREEZE_OPEN_ORDERS
    timezone: str = DEFAULT_TIMEZONE
    calendar: str = DEFAULT_CALENDAR
    enabled: bool = True
    requires_config: bool = False             # True → inert until a threshold is set
    created_by: str = ""
    created_at: float = field(default_factory=_time.time)
    updated_at: float = field(default_factory=_time.time)
    version: int = 1

    def def_hash(self) -> str:
        return shash({"type": self.breaker_type.value, "scope": self.scope.value, "ref": self.scope_ref,
                      "threshold": str(self.threshold), "warn": str(self.warning_threshold),
                      "window": self.window_seconds, "min_samples": self.min_samples,
                      "policy": self.open_order_policy.value, "tz": self.timezone, "version": self.version})

    def to_public(self) -> dict[str, Any]:
        return {"id": self.id, "org_id": self.org_id, "breaker_type": self.breaker_type.value,
                "scope": self.scope.value, "scope_ref": self.scope_ref, "workspace_id": self.workspace_id,
                "threshold": str(self.threshold),
                "warning_threshold": (str(self.warning_threshold) if self.warning_threshold is not None else None),
                "window_seconds": self.window_seconds, "min_samples": self.min_samples,
                "severity": self.severity.value, "auto_trip": self.auto_trip,
                "open_order_policy": self.open_order_policy.value, "timezone": self.timezone,
                "calendar": self.calendar, "enabled": self.enabled, "requires_config": self.requires_config,
                "created_by": self.created_by, "created_at": self.created_at, "updated_at": self.updated_at,
                "version": self.version, "definition_hash": self.def_hash()}


@dataclass
class CircuitBreakerState:
    definition_id: str
    org_id: str
    scope: BreakerScope
    scope_ref: str
    state: BreakerState = BreakerState.NORMAL
    last_evaluated_at: float = 0.0
    last_metric_json: dict[str, Any] = field(default_factory=dict)
    last_trip_id: str = ""
    trip_count: int = 0
    acknowledged_at: float = 0.0
    reset_requested_at: float = 0.0
    reset_at: float = 0.0
    peak_equity: Decimal = field(default_factory=lambda: Decimal("0"))  # for drawdown, restart-safe
    version: int = 1

    def is_blocking(self) -> bool:
        return self.state in BLOCKING_STATES

    def to_public(self) -> dict[str, Any]:
        return {"definition_id": self.definition_id, "org_id": self.org_id, "scope": self.scope.value,
                "scope_ref": self.scope_ref, "state": self.state.value,
                "last_evaluated_at": self.last_evaluated_at, "last_metric": self.last_metric_json,
                "last_trip_id": self.last_trip_id, "trip_count": self.trip_count,
                "acknowledged_at": self.acknowledged_at, "reset_requested_at": self.reset_requested_at,
                "reset_at": self.reset_at, "peak_equity": str(q2(self.peak_equity)),
                "blocking": self.is_blocking(), "version": self.version}


@dataclass
class SafetyMetricSnapshot:
    definition_id: str
    org_id: str
    breaker_type: BreakerType
    scope: BreakerScope
    scope_ref: str
    ts: float
    value: Decimal
    threshold: Decimal
    numerator: Decimal = field(default_factory=lambda: Decimal("0"))
    denominator: Decimal = field(default_factory=lambda: Decimal("0"))
    sample_sufficient: bool = True
    window: dict[str, Any] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)

    def snapshot_hash(self) -> str:
        return shash({"type": self.breaker_type.value, "scope": self.scope.value, "ref": self.scope_ref,
                      "value": str(self.value), "threshold": str(self.threshold),
                      "num": str(self.numerator), "den": str(self.denominator),
                      "sample_ok": self.sample_sufficient, "window": self.window, "detail": self.detail})

    def to_public(self) -> dict[str, Any]:
        return {"definition_id": self.definition_id, "breaker_type": self.breaker_type.value,
                "scope": self.scope.value, "scope_ref": self.scope_ref, "ts": self.ts,
                "value": str(self.value), "threshold": str(self.threshold),
                "numerator": str(self.numerator), "denominator": str(self.denominator),
                "sample_sufficient": self.sample_sufficient, "window": self.window,
                "detail": self.detail, "snapshot_hash": self.snapshot_hash()}


@dataclass
class SafetyFinding:
    definition_id: str
    breaker_type: BreakerType
    scope: BreakerScope
    scope_ref: str
    severity: Severity
    breached: bool
    reason_codes: list[str]
    message: str
    snapshot: SafetyMetricSnapshot

    def to_public(self) -> dict[str, Any]:
        return {"definition_id": self.definition_id, "breaker_type": self.breaker_type.value,
                "scope": self.scope.value, "scope_ref": self.scope_ref, "severity": self.severity.value,
                "breached": self.breached, "reason_codes": list(self.reason_codes), "message": self.message,
                "snapshot": self.snapshot.to_public()}


@dataclass
class CircuitBreakerTrip:
    trip_id: str
    org_id: str
    definition_id: str
    breaker_type: BreakerType
    scope: BreakerScope
    scope_ref: str
    severity: Severity
    alert_level: AlertLevel
    ts: float
    reason_codes: list[str]
    message: str
    metric_snapshot: dict[str, Any]
    threshold: str
    open_order_policy: OpenOrderPolicy
    open_order_actions: list[dict[str, Any]]
    reconciliation_run_id: str
    correlation_id: str
    manual: bool
    tripped_by: str
    trip_hash: str

    def to_public(self) -> dict[str, Any]:
        return {"trip_id": self.trip_id, "org_id": self.org_id, "definition_id": self.definition_id,
                "breaker_type": self.breaker_type.value, "scope": self.scope.value, "scope_ref": self.scope_ref,
                "severity": self.severity.value, "alert_level": self.alert_level.value, "ts": self.ts,
                "reason_codes": list(self.reason_codes), "message": self.message,
                "metric_snapshot": self.metric_snapshot, "threshold": self.threshold,
                "open_order_policy": self.open_order_policy.value, "open_order_actions": self.open_order_actions,
                "reconciliation_run_id": self.reconciliation_run_id, "correlation_id": self.correlation_id,
                "manual": self.manual, "tripped_by": self.tripped_by, "trip_hash": self.trip_hash}


@dataclass
class BreakerAcknowledgement:
    ack_id: str
    org_id: str
    trip_id: str
    definition_id: str
    acknowledged_by: str
    acknowledged_at: float
    note: str
    evidence_reviewed: bool
    version: int = 1

    def to_public(self) -> dict[str, Any]:
        return {"ack_id": self.ack_id, "trip_id": self.trip_id, "definition_id": self.definition_id,
                "acknowledged_by": self.acknowledged_by, "acknowledged_at": self.acknowledged_at,
                "note": self.note, "evidence_reviewed": self.evidence_reviewed, "version": self.version}


@dataclass
class BreakerResetRequest:
    request_id: str
    org_id: str
    trip_id: str
    definition_id: str
    scope: BreakerScope
    scope_ref: str
    requested_by: str
    requested_at: float
    reason: str
    idempotency_key: str
    breaker_version: int
    approval_id: str = ""
    payload_hash: str = ""
    status: str = "REQUESTED"        # REQUESTED | EXECUTED | REJECTED

    def to_public(self) -> dict[str, Any]:
        return {"request_id": self.request_id, "trip_id": self.trip_id, "definition_id": self.definition_id,
                "scope": self.scope.value, "scope_ref": self.scope_ref, "requested_by": self.requested_by,
                "requested_at": self.requested_at, "reason": self.reason, "breaker_version": self.breaker_version,
                "approval_id": self.approval_id, "payload_hash": self.payload_hash, "status": self.status}


@dataclass
class BreakerResetDecision:
    decision_id: str
    org_id: str
    request_id: str
    trip_id: str
    definition_id: str
    allowed: bool
    ts: float
    checks: list[dict[str, Any]]
    reason_codes: list[str]
    decided_by: str
    reconciliation_run_id: str = ""
    approval_id: str = ""

    def to_public(self) -> dict[str, Any]:
        return {"decision_id": self.decision_id, "request_id": self.request_id, "trip_id": self.trip_id,
                "definition_id": self.definition_id, "allowed": self.allowed, "ts": self.ts,
                "checks": self.checks, "reason_codes": list(self.reason_codes), "decided_by": self.decided_by,
                "reconciliation_run_id": self.reconciliation_run_id, "approval_id": self.approval_id}


# ── agent-actor guard (human-only mutations) ─────────────────────────────────────
def is_agent_actor(ctx) -> bool:
    """Heuristic, fail-closed marker: an actor is an agent when its authority marks
    autonomous/agent execution, or its identity is an agent principal. Human operators
    run with a human role and a non-agent identity."""
    authority = str(getattr(ctx, "authority", "") or "").upper()
    if "AGENT" in authority or "AUTONOMOUS" in authority:
        return True
    uid = str(getattr(ctx, "user_id", "") or "").lower()
    return uid.startswith("agent:") or uid.startswith("agent-") or uid.startswith("bot:")
