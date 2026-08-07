"""M62.7 — durable SQLite persistence for the safety circuit-breaker subsystem.

Shares the M62.5 ``PaperStore`` connection (single-host SQLite) so a breaker trip,
the protective account halt it triggers, and its alert all commit in ONE atomic
transaction on the same DB file. Tenant-scoped by ``org_id``. Trips, metric
snapshots, findings, alerts, acknowledgements and reset decisions are immutable
once written. Not multi-node safe; no distributed lock is claimed.
"""
from __future__ import annotations

import json
import sqlite3
import time as _time
from typing import Any

from saathi.platform.paper_trading.store import PaperStore
from saathi.platform.safety.models import (
    BreakerScope, BreakerState, BreakerType, OpenOrderPolicy, Severity,
    CircuitBreakerDefinition, CircuitBreakerState, CircuitBreakerTrip,
    BreakerAcknowledgement, BreakerResetRequest,
)
from saathi.platform.trading_models import D


def _dumps(obj) -> str:
    return json.dumps(obj, default=str, sort_keys=True)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS safety_breakers (
    id TEXT PRIMARY KEY, org_id TEXT NOT NULL, breaker_type TEXT NOT NULL, scope TEXT NOT NULL,
    scope_ref TEXT NOT NULL DEFAULT '', workspace_id TEXT NOT NULL DEFAULT '',
    threshold TEXT NOT NULL DEFAULT '0', warning_threshold TEXT, window_seconds INTEGER NOT NULL DEFAULT 0,
    min_samples INTEGER NOT NULL DEFAULT 0, severity TEXT NOT NULL DEFAULT 'ERROR',
    auto_trip INTEGER NOT NULL DEFAULT 1, open_order_policy TEXT NOT NULL DEFAULT 'FREEZE_OPEN_ORDERS',
    timezone TEXT NOT NULL DEFAULT 'UTC', calendar TEXT NOT NULL DEFAULT 'DEFAULT_24_5',
    enabled INTEGER NOT NULL DEFAULT 1, requires_config INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(org_id, breaker_type, scope, scope_ref)
);
CREATE TABLE IF NOT EXISTS safety_breaker_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, definition_id TEXT NOT NULL, org_id TEXT NOT NULL,
    version INTEGER NOT NULL, snapshot_json TEXT NOT NULL, ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS safety_breaker_states (
    definition_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, scope TEXT NOT NULL, scope_ref TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'NORMAL', last_evaluated_at REAL NOT NULL DEFAULT 0,
    last_metric_json TEXT NOT NULL DEFAULT '{}', last_trip_id TEXT NOT NULL DEFAULT '',
    trip_count INTEGER NOT NULL DEFAULT 0, acknowledged_at REAL NOT NULL DEFAULT 0,
    reset_requested_at REAL NOT NULL DEFAULT 0, reset_at REAL NOT NULL DEFAULT 0,
    peak_equity TEXT NOT NULL DEFAULT '0', version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS safety_trips (
    trip_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, definition_id TEXT NOT NULL, breaker_type TEXT NOT NULL,
    scope TEXT NOT NULL, scope_ref TEXT NOT NULL DEFAULT '', severity TEXT NOT NULL, alert_level TEXT NOT NULL,
    ts REAL NOT NULL, reason_codes_json TEXT NOT NULL DEFAULT '[]', message TEXT NOT NULL DEFAULT '',
    metric_json TEXT NOT NULL DEFAULT '{}', threshold TEXT NOT NULL DEFAULT '0',
    open_order_policy TEXT NOT NULL DEFAULT 'FREEZE_OPEN_ORDERS', open_order_actions_json TEXT NOT NULL DEFAULT '[]',
    reconciliation_run_id TEXT NOT NULL DEFAULT '', correlation_id TEXT NOT NULL DEFAULT '',
    manual INTEGER NOT NULL DEFAULT 0, tripped_by TEXT NOT NULL DEFAULT '', trip_hash TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS safety_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT NOT NULL, definition_id TEXT NOT NULL,
    breaker_type TEXT NOT NULL, scope TEXT NOT NULL, scope_ref TEXT NOT NULL DEFAULT '', ts REAL NOT NULL,
    value TEXT NOT NULL, threshold TEXT NOT NULL, numerator TEXT NOT NULL DEFAULT '0',
    denominator TEXT NOT NULL DEFAULT '0', sample_sufficient INTEGER NOT NULL DEFAULT 1,
    snapshot_hash TEXT NOT NULL DEFAULT '', detail_json TEXT NOT NULL DEFAULT '{}', sweep_id TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS safety_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT NOT NULL, sweep_id TEXT NOT NULL DEFAULT '',
    definition_id TEXT NOT NULL, breaker_type TEXT NOT NULL, scope TEXT NOT NULL, scope_ref TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL, breached INTEGER NOT NULL DEFAULT 0, reason_codes_json TEXT NOT NULL DEFAULT '[]',
    message TEXT NOT NULL DEFAULT '', ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS safety_sweeps (
    sweep_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, engine_version TEXT NOT NULL, status TEXT NOT NULL,
    started_at REAL NOT NULL, completed_at REAL NOT NULL DEFAULT 0, manifest_json TEXT NOT NULL DEFAULT '{}',
    result_hash TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS safety_alerts (
    alert_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, trip_id TEXT NOT NULL DEFAULT '', definition_id TEXT NOT NULL,
    level TEXT NOT NULL, breaker_type TEXT NOT NULL, scope TEXT NOT NULL, scope_ref TEXT NOT NULL DEFAULT '',
    ts REAL NOT NULL, message TEXT NOT NULL DEFAULT '', payload_json TEXT NOT NULL DEFAULT '{}',
    correlation_id TEXT NOT NULL DEFAULT '', acknowledged INTEGER NOT NULL DEFAULT 0, blocking INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS safety_acks (
    ack_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, trip_id TEXT NOT NULL, definition_id TEXT NOT NULL,
    acknowledged_by TEXT NOT NULL, acknowledged_at REAL NOT NULL, note TEXT NOT NULL DEFAULT '',
    evidence_reviewed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS safety_reset_requests (
    request_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, trip_id TEXT NOT NULL, definition_id TEXT NOT NULL,
    scope TEXT NOT NULL, scope_ref TEXT NOT NULL DEFAULT '', requested_by TEXT NOT NULL, requested_at REAL NOT NULL,
    reason TEXT NOT NULL DEFAULT '', idempotency_key TEXT NOT NULL DEFAULT '', breaker_version INTEGER NOT NULL DEFAULT 1,
    approval_id TEXT NOT NULL DEFAULT '', payload_hash TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'REQUESTED'
);
CREATE TABLE IF NOT EXISTS safety_reset_decisions (
    decision_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, request_id TEXT NOT NULL, trip_id TEXT NOT NULL,
    definition_id TEXT NOT NULL, allowed INTEGER NOT NULL, ts REAL NOT NULL, checks_json TEXT NOT NULL DEFAULT '[]',
    reason_codes_json TEXT NOT NULL DEFAULT '[]', decided_by TEXT NOT NULL DEFAULT '',
    reconciliation_run_id TEXT NOT NULL DEFAULT '', approval_id TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS safety_idempotency (
    org_id TEXT NOT NULL, scope TEXT NOT NULL, key TEXT NOT NULL, payload_hash TEXT NOT NULL,
    result_json TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY (org_id, scope, key)
);
CREATE TABLE IF NOT EXISTS safety_failure_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT NOT NULL, scope TEXT NOT NULL, scope_ref TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL, ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS safety_scheduler (
    name TEXT PRIMARY KEY, org_id TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 0,
    interval_seconds INTEGER NOT NULL DEFAULT 0, last_run_at REAL NOT NULL DEFAULT 0,
    lease_owner TEXT NOT NULL DEFAULT '', lease_expires_at REAL NOT NULL DEFAULT 0, registered_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sb_org ON safety_breakers(org_id, scope, scope_ref);
CREATE INDEX IF NOT EXISTS idx_st_org ON safety_trips(org_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_st_def ON safety_trips(org_id, definition_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_sm_def ON safety_metrics(org_id, definition_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_sal_org ON safety_alerts(org_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_sfe_scope ON safety_failure_events(org_id, scope, scope_ref, ts DESC);
"""


class SafetyStore:
    """Owns the safety tables; reuses the PaperStore connection + lock for atomicity."""

    def __init__(self, paper_store: PaperStore):
        self.paper = paper_store
        self._conn = paper_store._conn
        self._lock = paper_store._lock
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)

    def _now(self) -> float:
        return _time.time()

    # ── serialization ──────────────────────────────────────────────────────────
    @staticmethod
    def _def(r: sqlite3.Row) -> CircuitBreakerDefinition:
        return CircuitBreakerDefinition(
            id=r["id"], org_id=r["org_id"], breaker_type=BreakerType(r["breaker_type"]),
            scope=BreakerScope(r["scope"]), scope_ref=r["scope_ref"], workspace_id=r["workspace_id"],
            threshold=D(r["threshold"]),
            warning_threshold=(D(r["warning_threshold"]) if r["warning_threshold"] is not None else None),
            window_seconds=r["window_seconds"], min_samples=r["min_samples"], severity=Severity(r["severity"]),
            auto_trip=bool(r["auto_trip"]), open_order_policy=OpenOrderPolicy(r["open_order_policy"]),
            timezone=r["timezone"], calendar=r["calendar"], enabled=bool(r["enabled"]),
            requires_config=bool(r["requires_config"]), created_by=r["created_by"], created_at=r["created_at"],
            updated_at=r["updated_at"], version=r["version"])

    @staticmethod
    def _state(r: sqlite3.Row) -> CircuitBreakerState:
        return CircuitBreakerState(
            definition_id=r["definition_id"], org_id=r["org_id"], scope=BreakerScope(r["scope"]),
            scope_ref=r["scope_ref"], state=BreakerState(r["state"]), last_evaluated_at=r["last_evaluated_at"],
            last_metric_json=json.loads(r["last_metric_json"] or "{}"), last_trip_id=r["last_trip_id"],
            trip_count=r["trip_count"], acknowledged_at=r["acknowledged_at"],
            reset_requested_at=r["reset_requested_at"], reset_at=r["reset_at"],
            peak_equity=D(r["peak_equity"]), version=r["version"])

    def _write_def(self, cur, d: CircuitBreakerDefinition) -> None:
        cur.execute(
            "INSERT OR REPLACE INTO safety_breakers (id,org_id,breaker_type,scope,scope_ref,workspace_id,threshold,"
            "warning_threshold,window_seconds,min_samples,severity,auto_trip,open_order_policy,timezone,calendar,"
            "enabled,requires_config,created_by,created_at,updated_at,version) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (d.id, d.org_id, d.breaker_type.value, d.scope.value, d.scope_ref, d.workspace_id, str(d.threshold),
             (str(d.warning_threshold) if d.warning_threshold is not None else None), d.window_seconds,
             d.min_samples, d.severity.value, 1 if d.auto_trip else 0, d.open_order_policy.value, d.timezone,
             d.calendar, 1 if d.enabled else 0, 1 if d.requires_config else 0, d.created_by, d.created_at,
             d.updated_at, d.version))
        cur.execute("INSERT INTO safety_breaker_revisions (definition_id,org_id,version,snapshot_json,ts) "
                    "VALUES (?,?,?,?,?)", (d.id, d.org_id, d.version, _dumps(d.to_public()), self._now()))

    def _write_state(self, cur, s: CircuitBreakerState) -> None:
        cur.execute(
            "INSERT OR REPLACE INTO safety_breaker_states (definition_id,org_id,scope,scope_ref,state,"
            "last_evaluated_at,last_metric_json,last_trip_id,trip_count,acknowledged_at,reset_requested_at,"
            "reset_at,peak_equity,version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (s.definition_id, s.org_id, s.scope.value, s.scope_ref, s.state.value, s.last_evaluated_at,
             _dumps(s.last_metric_json), s.last_trip_id, s.trip_count, s.acknowledged_at, s.reset_requested_at,
             s.reset_at, str(s.peak_equity), s.version))

    # ── definitions ──────────────────────────────────────────────────────────────
    def upsert_definition(self, d: CircuitBreakerDefinition) -> None:
        with self._lock, self._conn:
            self._write_def(self._conn, d)
            # ensure a state row exists
            if not self.get_state(d.org_id, d.id):
                self._write_state(self._conn, CircuitBreakerState(
                    definition_id=d.id, org_id=d.org_id, scope=d.scope, scope_ref=d.scope_ref))

    def get_definition(self, org_id: str, definition_id: str) -> CircuitBreakerDefinition | None:
        r = self._conn.execute("SELECT * FROM safety_breakers WHERE org_id=? AND id=?",
                               (org_id, definition_id)).fetchone()
        return self._def(r) if r else None

    def find_definition(self, org_id, breaker_type: BreakerType, scope: BreakerScope, scope_ref: str
                        ) -> CircuitBreakerDefinition | None:
        r = self._conn.execute(
            "SELECT * FROM safety_breakers WHERE org_id=? AND breaker_type=? AND scope=? AND scope_ref=?",
            (org_id, breaker_type.value, scope.value, scope_ref)).fetchone()
        return self._def(r) if r else None

    def list_definitions(self, org_id: str, *, limit: int = 500) -> list[CircuitBreakerDefinition]:
        rows = self._conn.execute("SELECT * FROM safety_breakers WHERE org_id=? ORDER BY created_at LIMIT ?",
                                  (org_id, int(limit))).fetchall()
        return [self._def(r) for r in rows]

    def definition_revisions(self, org_id: str, definition_id: str) -> list[dict]:
        rows = self._conn.execute("SELECT version,snapshot_json,ts FROM safety_breaker_revisions "
                                  "WHERE org_id=? AND definition_id=? ORDER BY version",
                                  (org_id, definition_id)).fetchall()
        return [{"version": r["version"], "ts": r["ts"], "snapshot": json.loads(r["snapshot_json"])} for r in rows]

    # ── states ───────────────────────────────────────────────────────────────────
    def get_state(self, org_id: str, definition_id: str) -> CircuitBreakerState | None:
        r = self._conn.execute("SELECT * FROM safety_breaker_states WHERE org_id=? AND definition_id=?",
                               (org_id, definition_id)).fetchone()
        return self._state(r) if r else None

    def list_states(self, org_id: str, *, limit: int = 500) -> list[CircuitBreakerState]:
        rows = self._conn.execute("SELECT * FROM safety_breaker_states WHERE org_id=? ORDER BY definition_id LIMIT ?",
                                  (org_id, int(limit))).fetchall()
        return [self._state(r) for r in rows]

    def save_state(self, s: CircuitBreakerState) -> None:
        with self._lock, self._conn:
            self._write_state(self._conn, s)

    # ── trips (immutable) ─────────────────────────────────────────────────────────
    def get_trip(self, org_id: str, trip_id: str) -> dict | None:
        r = self._conn.execute("SELECT * FROM safety_trips WHERE org_id=? AND trip_id=?",
                               (org_id, trip_id)).fetchone()
        return self._trip_row(r) if r else None

    @staticmethod
    def _trip_row(r: sqlite3.Row) -> dict:
        return {"trip_id": r["trip_id"], "org_id": r["org_id"], "definition_id": r["definition_id"],
                "breaker_type": r["breaker_type"], "scope": r["scope"], "scope_ref": r["scope_ref"],
                "severity": r["severity"], "alert_level": r["alert_level"], "ts": r["ts"],
                "reason_codes": json.loads(r["reason_codes_json"] or "[]"), "message": r["message"],
                "metric_snapshot": json.loads(r["metric_json"] or "{}"), "threshold": r["threshold"],
                "open_order_policy": r["open_order_policy"],
                "open_order_actions": json.loads(r["open_order_actions_json"] or "[]"),
                "reconciliation_run_id": r["reconciliation_run_id"], "correlation_id": r["correlation_id"],
                "manual": bool(r["manual"]), "tripped_by": r["tripped_by"], "trip_hash": r["trip_hash"]}

    def list_trips(self, org_id: str, *, definition_id: str | None = None, limit: int = 200) -> list[dict]:
        if definition_id:
            rows = self._conn.execute("SELECT * FROM safety_trips WHERE org_id=? AND definition_id=? "
                                      "ORDER BY ts DESC LIMIT ?", (org_id, definition_id, int(limit))).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM safety_trips WHERE org_id=? ORDER BY ts DESC LIMIT ?",
                                      (org_id, int(limit))).fetchall()
        return [self._trip_row(r) for r in rows]

    # ── generic reads ──────────────────────────────────────────────────────────────
    def list_alerts(self, org_id: str, *, limit: int = 200) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM safety_alerts WHERE org_id=? ORDER BY ts DESC LIMIT ?",
                                  (org_id, int(limit))).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["payload"] = json.loads(d.pop("payload_json") or "{}"); out.append(d)
        return out

    def list_metrics(self, org_id: str, definition_id: str, *, limit: int = 100) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM safety_metrics WHERE org_id=? AND definition_id=? "
                                  "ORDER BY ts DESC LIMIT ?", (org_id, definition_id, int(limit))).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["detail"] = json.loads(d.pop("detail_json") or "{}"); out.append(d)
        return out

    def get_ack_for_trip(self, org_id: str, trip_id: str) -> dict | None:
        r = self._conn.execute("SELECT * FROM safety_acks WHERE org_id=? AND trip_id=?",
                               (org_id, trip_id)).fetchone()
        return dict(r) if r else None

    def get_reset_request(self, org_id: str, request_id: str) -> BreakerResetRequest | None:
        r = self._conn.execute("SELECT * FROM safety_reset_requests WHERE org_id=? AND request_id=?",
                               (org_id, request_id)).fetchone()
        if not r:
            return None
        return BreakerResetRequest(
            request_id=r["request_id"], org_id=r["org_id"], trip_id=r["trip_id"], definition_id=r["definition_id"],
            scope=BreakerScope(r["scope"]), scope_ref=r["scope_ref"], requested_by=r["requested_by"],
            requested_at=r["requested_at"], reason=r["reason"], idempotency_key=r["idempotency_key"],
            breaker_version=r["breaker_version"], approval_id=r["approval_id"], payload_hash=r["payload_hash"],
            status=r["status"])

    def get_sweep(self, org_id: str, sweep_id: str) -> dict | None:
        r = self._conn.execute("SELECT * FROM safety_sweeps WHERE org_id=? AND sweep_id=?",
                               (org_id, sweep_id)).fetchone()
        if not r:
            return None
        return {"sweep_id": r["sweep_id"], "status": r["status"], "engine_version": r["engine_version"],
                "started_at": r["started_at"], "completed_at": r["completed_at"],
                "manifest": json.loads(r["manifest_json"] or "{}"), "result_hash": r["result_hash"]}

    def list_sweeps(self, org_id: str, *, limit: int = 100) -> list[dict]:
        rows = self._conn.execute("SELECT sweep_id,status,started_at,completed_at,result_hash FROM safety_sweeps "
                                  "WHERE org_id=? ORDER BY started_at DESC LIMIT ?", (org_id, int(limit))).fetchall()
        return [dict(r) for r in rows]

    # ── failure-event window (processing-failure breaker) ───────────────────────────
    def record_failure_event(self, org_id, scope: BreakerScope, scope_ref, kind: str, ts: float) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO safety_failure_events (org_id,scope,scope_ref,kind,ts) VALUES (?,?,?,?,?)",
                               (org_id, scope.value, scope_ref, kind, ts))

    def count_failures(self, org_id, scope: BreakerScope, scope_ref, *, since: float) -> int:
        r = self._conn.execute("SELECT COUNT(*) c FROM safety_failure_events WHERE org_id=? AND scope=? AND "
                               "scope_ref=? AND ts>=?", (org_id, scope.value, scope_ref, since)).fetchone()
        return int(r["c"])

    # ── scheduler registration (idempotent, lease) ─────────────────────────────────
    def register_sweep_schedule(self, name: str, *, org_id: str = "", enabled: bool, interval_seconds: int) -> dict:
        with self._lock, self._conn:
            r = self._conn.execute("SELECT name FROM safety_scheduler WHERE name=?", (name,)).fetchone()
            if r:
                self._conn.execute("UPDATE safety_scheduler SET enabled=?, interval_seconds=? WHERE name=?",
                                   (1 if enabled else 0, int(interval_seconds), name))
            else:
                self._conn.execute("INSERT INTO safety_scheduler (name,org_id,enabled,interval_seconds,registered_at) "
                                   "VALUES (?,?,?,?,?)", (name, org_id, 1 if enabled else 0, int(interval_seconds),
                                                          self._now()))
        return self.get_schedule(name)

    def get_schedule(self, name: str) -> dict | None:
        r = self._conn.execute("SELECT * FROM safety_scheduler WHERE name=?", (name,)).fetchone()
        return dict(r) if r else None

    def acquire_lease(self, name: str, *, owner: str, ttl: float, now: float) -> bool:
        """Overlap prevention: only one holder while the lease is live."""
        with self._lock, self._conn:
            r = self._conn.execute("SELECT lease_owner,lease_expires_at FROM safety_scheduler WHERE name=?",
                                   (name,)).fetchone()
            if r and r["lease_expires_at"] > now and r["lease_owner"] and r["lease_owner"] != owner:
                return False
            self._conn.execute("UPDATE safety_scheduler SET lease_owner=?, lease_expires_at=? WHERE name=?",
                               (owner, now + ttl, name))
            return True

    def release_lease(self, name: str, *, owner: str, last_run_at: float) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE safety_scheduler SET lease_owner='', lease_expires_at=0, last_run_at=? "
                               "WHERE name=? AND lease_owner=?", (last_run_at, name, owner))

    # ── ATOMIC: trip (metric + finding + state + trip + halt + alert) ───────────────
    def persist_trip(self, *, trip: CircuitBreakerTrip, state: CircuitBreakerState,
                     metric: dict, finding: dict, alert: dict, halt_account_id: str = "",
                     idem_scope: str = "", idem_key: str = "", idem_payload_hash: str = "",
                     idem_result: dict | None = None) -> dict:
        """One atomic transaction. If it raises anywhere, the whole trip rolls back —
        no partial halt, no orphan alert. Trips and metric snapshots are immutable."""
        with self._lock, self._conn:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO safety_metrics (org_id,definition_id,breaker_type,scope,scope_ref,ts,value,threshold,"
                "numerator,denominator,sample_sufficient,snapshot_hash,detail_json,sweep_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (trip.org_id, trip.definition_id, trip.breaker_type.value, trip.scope.value, trip.scope_ref,
                 trip.ts, metric["value"], metric["threshold"], metric.get("numerator", "0"),
                 metric.get("denominator", "0"), 1 if metric.get("sample_sufficient", True) else 0,
                 metric.get("snapshot_hash", ""), _dumps(metric.get("detail", {})), metric.get("sweep_id", "")))
            cur.execute(
                "INSERT INTO safety_findings (org_id,sweep_id,definition_id,breaker_type,scope,scope_ref,severity,"
                "breached,reason_codes_json,message,ts) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (trip.org_id, finding.get("sweep_id", ""), trip.definition_id, trip.breaker_type.value,
                 trip.scope.value, trip.scope_ref, finding["severity"], 1 if finding["breached"] else 0,
                 _dumps(finding.get("reason_codes", [])), finding.get("message", ""), trip.ts))
            cur.execute(
                "INSERT INTO safety_trips (trip_id,org_id,definition_id,breaker_type,scope,scope_ref,severity,"
                "alert_level,ts,reason_codes_json,message,metric_json,threshold,open_order_policy,"
                "open_order_actions_json,reconciliation_run_id,correlation_id,manual,tripped_by,trip_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (trip.trip_id, trip.org_id, trip.definition_id, trip.breaker_type.value, trip.scope.value,
                 trip.scope_ref, trip.severity.value, trip.alert_level.value, trip.ts,
                 _dumps(trip.reason_codes), trip.message, _dumps(trip.metric_snapshot), trip.threshold,
                 trip.open_order_policy.value, _dumps(trip.open_order_actions), trip.reconciliation_run_id,
                 trip.correlation_id, 1 if trip.manual else 0, trip.tripped_by, trip.trip_hash))
            self._write_state(cur, state)
            # protective halt (direct write, same transaction; never a financial mutation)
            if halt_account_id:
                cur.execute("UPDATE paper_accounts SET status='HALTED', halt_reason=?, version=version+1, "
                            "updated_at=? WHERE org_id=? AND id=? AND status='ACTIVE'",
                            (f"safety:{trip.breaker_type.value}:{trip.trip_id}"[:200], self._now(),
                             trip.org_id, halt_account_id))
            cur.execute(
                "INSERT INTO safety_alerts (alert_id,org_id,trip_id,definition_id,level,breaker_type,scope,scope_ref,"
                "ts,message,payload_json,correlation_id,acknowledged,blocking) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (alert["alert_id"], trip.org_id, trip.trip_id, trip.definition_id, alert["level"],
                 trip.breaker_type.value, trip.scope.value, trip.scope_ref, trip.ts, alert.get("message", ""),
                 _dumps(alert.get("payload", {})), trip.correlation_id, 0, 1 if alert.get("blocking", True) else 0))
            if idem_key:
                cur.execute("INSERT OR REPLACE INTO safety_idempotency (org_id,scope,key,payload_hash,result_json,"
                            "created_at) VALUES (?,?,?,?,?,?)",
                            (trip.org_id, idem_scope, idem_key, idem_payload_hash,
                             _dumps(idem_result or {}), self._now()))
        return self._trip_row(self._conn.execute("SELECT * FROM safety_trips WHERE trip_id=?",
                                                 (trip.trip_id,)).fetchone())

    # ── WARNING-only posture write (no trip) ────────────────────────────────────────
    def persist_warning(self, *, state: CircuitBreakerState, metric: dict, finding: dict, alert: dict | None) -> None:
        with self._lock, self._conn:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO safety_metrics (org_id,definition_id,breaker_type,scope,scope_ref,ts,value,threshold,"
                "numerator,denominator,sample_sufficient,snapshot_hash,detail_json,sweep_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (state.org_id, state.definition_id, finding["breaker_type"], state.scope.value, state.scope_ref,
                 finding["ts"], metric["value"], metric["threshold"], metric.get("numerator", "0"),
                 metric.get("denominator", "0"), 1 if metric.get("sample_sufficient", True) else 0,
                 metric.get("snapshot_hash", ""), _dumps(metric.get("detail", {})), finding.get("sweep_id", "")))
            cur.execute(
                "INSERT INTO safety_findings (org_id,sweep_id,definition_id,breaker_type,scope,scope_ref,severity,"
                "breached,reason_codes_json,message,ts) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (state.org_id, finding.get("sweep_id", ""), state.definition_id, finding["breaker_type"],
                 state.scope.value, state.scope_ref, finding["severity"], 0,
                 _dumps(finding.get("reason_codes", [])), finding.get("message", ""), finding["ts"]))
            self._write_state(cur, state)
            if alert:
                cur.execute(
                    "INSERT INTO safety_alerts (alert_id,org_id,trip_id,definition_id,level,breaker_type,scope,"
                    "scope_ref,ts,message,payload_json,correlation_id,acknowledged,blocking) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (alert["alert_id"], state.org_id, "", state.definition_id, alert["level"],
                     finding["breaker_type"], state.scope.value, state.scope_ref, finding["ts"],
                     alert.get("message", ""), _dumps(alert.get("payload", {})), "", 0, 0))

    # ── ATOMIC: acknowledgement ──────────────────────────────────────────────────────
    def persist_ack(self, *, ack: BreakerAcknowledgement, state: CircuitBreakerState) -> dict:
        with self._lock, self._conn:
            cur = self._conn.cursor()
            cur.execute("INSERT INTO safety_acks (ack_id,org_id,trip_id,definition_id,acknowledged_by,"
                        "acknowledged_at,note,evidence_reviewed) VALUES (?,?,?,?,?,?,?,?)",
                        (ack.ack_id, ack.org_id, ack.trip_id, ack.definition_id, ack.acknowledged_by,
                         ack.acknowledged_at, ack.note, 1 if ack.evidence_reviewed else 0))
            cur.execute("UPDATE safety_alerts SET acknowledged=1 WHERE org_id=? AND trip_id=?",
                        (ack.org_id, ack.trip_id))
            self._write_state(cur, state)
        return ack.to_public()

    def persist_reset_request(self, req: BreakerResetRequest, state: CircuitBreakerState) -> dict:
        with self._lock, self._conn:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO safety_reset_requests (request_id,org_id,trip_id,definition_id,scope,scope_ref,"
                "requested_by,requested_at,reason,idempotency_key,breaker_version,approval_id,payload_hash,status) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (req.request_id, req.org_id, req.trip_id, req.definition_id, req.scope.value, req.scope_ref,
                 req.requested_by, req.requested_at, req.reason, req.idempotency_key, req.breaker_version,
                 req.approval_id, req.payload_hash, req.status))
            self._write_state(cur, state)
        return req.to_public()

    # ── ATOMIC: reset (decision + state transition + unhalt + approval consume) ────────
    def persist_reset(self, *, decision, request: BreakerResetRequest, state: CircuitBreakerState,
                      unhalt_account_id: str = "", consume_approval=None) -> dict:
        """One atomic transaction. On any failure the breaker stays HALTED/ACKNOWLEDGED
        and no account is unhalted. Consumes the approval atomically with the transition."""
        with self._lock, self._conn:
            cur = self._conn.cursor()
            if consume_approval is not None and not consume_approval(cur):
                raise ValueError("approval not consumable (missing/expired/used/foreign)")
            cur.execute(
                "INSERT INTO safety_reset_decisions (decision_id,org_id,request_id,trip_id,definition_id,allowed,ts,"
                "checks_json,reason_codes_json,decided_by,reconciliation_run_id,approval_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (decision.decision_id, decision.org_id, decision.request_id, decision.trip_id,
                 decision.definition_id, 1 if decision.allowed else 0, decision.ts, _dumps(decision.checks),
                 _dumps(decision.reason_codes), decision.decided_by, decision.reconciliation_run_id,
                 decision.approval_id))
            self._write_state(cur, state)
            cur.execute("UPDATE safety_reset_requests SET status=? WHERE org_id=? AND request_id=?",
                        (request.status, request.org_id, request.request_id))
            if unhalt_account_id:
                cur.execute("UPDATE paper_accounts SET status='ACTIVE', halt_reason='', version=version+1, "
                            "updated_at=? WHERE org_id=? AND id=? AND status='HALTED'",
                            (self._now(), request.org_id, unhalt_account_id))
        return decision.to_public()

    def save_sweep(self, org_id, sweep_id, *, engine_version, status, started_at, completed_at=0.0,
                   manifest=None, result_hash="") -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO safety_sweeps (sweep_id,org_id,engine_version,status,started_at,"
                "completed_at,manifest_json,result_hash) VALUES (?,?,?,?,?,?,?,?)",
                (sweep_id, org_id, engine_version, status, started_at, completed_at,
                 _dumps(manifest or {}), result_hash))

    # ── idempotency ─────────────────────────────────────────────────────────────
    def idem_lookup(self, org_id, scope, key, payload_hash) -> dict | None:
        if not key:
            return None
        r = self._conn.execute("SELECT payload_hash,result_json FROM safety_idempotency "
                               "WHERE org_id=? AND scope=? AND key=?", (org_id, scope, key)).fetchone()
        if not r:
            return None
        if r["payload_hash"] != payload_hash:
            from saathi.platform.paper_trading.store import IdempotencyConflict
            raise IdempotencyConflict(f"safety idempotency key {key} reused with different payload")
        return json.loads(r["result_json"])
