"""M24 — Canonical durable provider-governance store (SQLite).

One authority for:
  * provider circuit state + transition history
  * cost usage ledger
  * budget reservations + settlement
  * operator reset/override audit
  * stale reservation recovery

Follows SaathiOS SQLite conventions (run_ledger / connectors store):
  data/*.db, BEGIN IMMEDIATE, row_factory, CAS on version, no secrets.

Money is stored as fixed-precision TEXT decimal strings (never binary float).
Timestamps are UTC epoch seconds. Budget-day keys use governance_clock.day_key.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.inference.governance_clock import (
    Clock,
    budget_day_timezone_name,
    day_key,
    utc_now,
)
from saathi.inference.governance_errors import GovernanceError, GovernanceErrorCode

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "provider_governance.db"
SCHEMA_VERSION = 1
_QUANT = Decimal("0.00000001")
_MONEY_MAX = Decimal("1000000")

# Circuit states
CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"
DISABLED = "disabled"

# Reservation / usage statuses
RESERVED = "reserved"
SETTLED = "settled"
RELEASED = "released"
EXPIRED = "expired"
CANCELLED = "cancelled"
FAILED = "failed"
RECONCILIATION = "reconciliation_required"
ESTIMATED = "estimated"
ACTUAL = "actual"
ZERO = "zero"

# Stale classifications
SAFE_RELEASE = "safe_release"
NEEDS_RECONCILIATION = "needs_reconciliation"
PROVIDER_ATTEMPT_UNKNOWN = "provider_attempt_unknown"
ALREADY_SETTLED = "already_settled"
INVALID_STATE = "invalid_state"

# Audit event types
EVT_CIRCUIT_OPENED = "CIRCUIT_OPENED"
EVT_CIRCUIT_HALF_OPENED = "CIRCUIT_HALF_OPENED"
EVT_CIRCUIT_CLOSED = "CIRCUIT_CLOSED"
EVT_CIRCUIT_RESET = "CIRCUIT_RESET"
EVT_RESERVATION_CREATED = "RESERVATION_CREATED"
EVT_RESERVATION_SETTLED = "RESERVATION_SETTLED"
EVT_RESERVATION_RELEASED = "RESERVATION_RELEASED"
EVT_RESERVATION_EXPIRED = "RESERVATION_EXPIRED"
EVT_RESERVATION_RECONCILIATION = "RESERVATION_RECONCILIATION_REQUIRED"
EVT_BUDGET_DENIED = "BUDGET_DENIED"
EVT_OVERRIDE_CREATED = "OPERATOR_OVERRIDE_CREATED"
EVT_OVERRIDE_REVOKED = "OPERATOR_OVERRIDE_REVOKED"
EVT_USAGE_RECORDED = "USAGE_RECORDED"

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS governance_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_circuit (
  provider_id TEXT NOT NULL,
  model_scope TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT '{CLOSED}',
  failure_count INTEGER NOT NULL DEFAULT 0,
  success_count INTEGER NOT NULL DEFAULT 0,
  opened_at REAL,
  open_until REAL,
  half_open_probe_owner TEXT,
  half_open_probe_lease_until REAL,
  half_open_probes INTEGER NOT NULL DEFAULT 0,
  last_failure_code TEXT DEFAULT '',
  last_transition_at REAL,
  last_success_at REAL,
  last_failure_at REAL,
  last_reason TEXT DEFAULT '',
  version INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL,
  PRIMARY KEY (provider_id, model_scope)
);

CREATE TABLE IF NOT EXISTS circuit_transition (
  transition_id TEXT PRIMARY KEY,
  provider_id TEXT NOT NULL,
  model_scope TEXT NOT NULL DEFAULT '',
  from_state TEXT NOT NULL,
  to_state TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  attempt_id TEXT DEFAULT '',
  actor_type TEXT NOT NULL DEFAULT 'system',
  actor_id TEXT NOT NULL DEFAULT 'governance',
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_circuit_transition_provider
  ON circuit_transition(provider_id, created_at);

CREATE TABLE IF NOT EXISTS cost_usage (
  usage_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL,
  reservation_id TEXT DEFAULT '',
  caller_id TEXT NOT NULL DEFAULT '',
  provider_id TEXT NOT NULL,
  model_id TEXT NOT NULL DEFAULT '',
  currency TEXT NOT NULL DEFAULT 'USD',
  estimated_cost TEXT NOT NULL DEFAULT '0',
  actual_cost TEXT,
  input_units INTEGER NOT NULL DEFAULT 0,
  output_units INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  occurred_at REAL NOT NULL,
  settled_at REAL,
  idempotency_key TEXT NOT NULL,
  day_key TEXT NOT NULL,
  attempt_number INTEGER NOT NULL DEFAULT 1,
  notes TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_idempotency ON cost_usage(idempotency_key);
CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_attempt ON cost_usage(attempt_id);
CREATE INDEX IF NOT EXISTS idx_usage_day_caller ON cost_usage(day_key, caller_id);
CREATE INDEX IF NOT EXISTS idx_usage_request ON cost_usage(request_id);

CREATE TABLE IF NOT EXISTS budget_reservation (
  reservation_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL,
  attempt_id TEXT NOT NULL,
  caller_id TEXT NOT NULL DEFAULT '',
  budget_scope TEXT NOT NULL DEFAULT 'caller_daily',
  provider_id TEXT NOT NULL,
  model_id TEXT NOT NULL DEFAULT '',
  currency TEXT NOT NULL DEFAULT 'USD',
  reserved_amount TEXT NOT NULL,
  settled_amount TEXT,
  status TEXT NOT NULL,
  expires_at REAL NOT NULL,
  created_at REAL NOT NULL,
  settled_at REAL,
  released_at REAL,
  idempotency_key TEXT NOT NULL,
  day_key TEXT NOT NULL,
  attempt_started INTEGER NOT NULL DEFAULT 0,
  provider_outcome TEXT DEFAULT '',
  notes TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_reservation_idempotency
  ON budget_reservation(idempotency_key);
CREATE UNIQUE INDEX IF NOT EXISTS idx_reservation_attempt
  ON budget_reservation(attempt_id);
CREATE INDEX IF NOT EXISTS idx_reservation_status
  ON budget_reservation(status, expires_at);
CREATE INDEX IF NOT EXISTS idx_reservation_day_caller
  ON budget_reservation(day_key, caller_id);

CREATE TABLE IF NOT EXISTS daily_spend_agg (
  day_key TEXT NOT NULL,
  caller_id TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  settled_total TEXT NOT NULL DEFAULT '0',
  reserved_total TEXT NOT NULL DEFAULT '0',
  version INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL,
  PRIMARY KEY (day_key, caller_id, currency)
);

CREATE TABLE IF NOT EXISTS governance_audit (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  actor_type TEXT NOT NULL DEFAULT 'system',
  actor_id TEXT NOT NULL DEFAULT 'governance',
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  reason_code TEXT NOT NULL DEFAULT '',
  request_id TEXT DEFAULT '',
  attempt_id TEXT DEFAULT '',
  old_state TEXT DEFAULT '',
  new_state TEXT DEFAULT '',
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_type_time ON governance_audit(event_type, created_at);

CREATE TABLE IF NOT EXISTS operator_override (
  override_id TEXT PRIMARY KEY,
  override_type TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{{}}',
  reason_code TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  revoked_at REAL,
  revoked_by TEXT DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_override_active
  ON operator_override(active, target_type, target_id);
"""

_DOWNGRADE = """
DROP TABLE IF EXISTS operator_override;
DROP TABLE IF EXISTS governance_audit;
DROP TABLE IF EXISTS daily_spend_agg;
DROP TABLE IF EXISTS budget_reservation;
DROP TABLE IF EXISTS cost_usage;
DROP TABLE IF EXISTS circuit_transition;
DROP TABLE IF EXISTS provider_circuit;
DROP TABLE IF EXISTS governance_meta;
"""


def _id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex}" if prefix else uuid.uuid4().hex


def _money(value: Any) -> Decimal:
    """Parse money as Decimal. Rejects bare float (binary risk) unless already Decimal/str/int."""
    if value is None:
        raise GovernanceError(
            GovernanceErrorCode.FLOAT_MONEY_REJECTED,
            "money value is required",
        )
    if isinstance(value, float):
        # Explicit rejection of binary float money
        raise GovernanceError(
            GovernanceErrorCode.FLOAT_MONEY_REJECTED,
            "binary float money rejected — use Decimal or decimal string",
        )
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise GovernanceError(
            GovernanceErrorCode.FLOAT_MONEY_REJECTED,
            f"invalid money value: {value!r}",
        ) from e
    if d < 0:
        raise GovernanceError(
            GovernanceErrorCode.FLOAT_MONEY_REJECTED,
            "negative money rejected",
        )
    if d > _MONEY_MAX:
        raise GovernanceError(
            GovernanceErrorCode.FLOAT_MONEY_REJECTED,
            "extreme money rejected",
        )
    return d.quantize(_QUANT, rounding=ROUND_HALF_UP)


def _money_str(value: Any) -> str:
    return str(_money(value))


def _d_str(s: Optional[str]) -> Decimal:
    if s is None or s == "":
        return Decimal("0")
    return Decimal(str(s))


class DurableGovernanceStore:
    """Authoritative durable store for circuits, costs, reservations, audit."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        clock: Optional[Clock] = None,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        half_open_max_probes: int = 1,
        half_open_lease_seconds: float = 30.0,
        reservation_ttl_seconds: float = 300.0,
    ) -> None:
        raw = str(db_path) if db_path is not None else str(DEFAULT_DB)
        self._is_memory = raw == ":memory:" or raw.startswith("file:memdb")
        self.path = Path(raw) if not self._is_memory else Path(":memory:")
        if not self._is_memory:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock: Clock = clock or utc_now
        self.failure_threshold = int(failure_threshold)
        self.cooldown_seconds = float(cooldown_seconds)
        self.half_open_max_probes = int(half_open_max_probes)
        self.half_open_lease_seconds = float(half_open_lease_seconds)
        self.reservation_ttl_seconds = float(reservation_ttl_seconds)
        self._lock = threading.RLock()
        conn_target = ":memory:" if self._is_memory else str(self.path)
        self._conn = sqlite3.connect(conn_target, check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.upgrade()

    # ── clock / lifecycle ─────────────────────────────────────────────────

    def set_clock(self, clock: Clock) -> None:
        self._clock = clock

    def now(self) -> float:
        return float(self._clock())

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def schema_ready(self) -> bool:
        try:
            row = self._conn.execute(
                "SELECT value FROM governance_meta WHERE key='schema_version'"
            ).fetchone()
            if not row:
                return False
            return int(row["value"]) == SCHEMA_VERSION
        except Exception:
            return False

    def upgrade(self) -> dict[str, Any]:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.execute(
                "INSERT INTO governance_meta(key,value) VALUES('schema_version',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )
            self._conn.execute(
                "INSERT INTO governance_meta(key,value) VALUES('upgraded_at',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(self.now()),),
            )
            self._conn.commit()
        return {"ok": True, "schema_version": SCHEMA_VERSION, "path": str(self.path)}

    def downgrade(self) -> dict[str, Any]:
        """Reversible: drops M24 governance tables (destructive to governance data only)."""
        with self._lock:
            self._conn.executescript(_DOWNGRADE)
            self._conn.commit()
        return {"ok": True, "schema_version": 0, "path": str(self.path)}

    # ── internals ─────────────────────────────────────────────────────────

    def _begin(self) -> sqlite3.Connection:
        c = self._conn
        c.execute("BEGIN IMMEDIATE")
        return c

    def _audit(
        self,
        c: sqlite3.Connection,
        *,
        event_type: str,
        target_type: str,
        target_id: str,
        reason_code: str = "",
        actor_type: str = "system",
        actor_id: str = "governance",
        request_id: str = "",
        attempt_id: str = "",
        old_state: str = "",
        new_state: str = "",
    ) -> str:
        eid = _id("evt_")
        c.execute(
            "INSERT INTO governance_audit("
            "event_id,event_type,actor_type,actor_id,target_type,target_id,"
            "reason_code,request_id,attempt_id,old_state,new_state,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                eid,
                event_type,
                actor_type,
                actor_id,
                target_type,
                target_id,
                reason_code,
                request_id,
                attempt_id,
                old_state[:500] if old_state else "",
                new_state[:500] if new_state else "",
                self.now(),
            ),
        )
        return eid

    def _ensure_circuit_row(
        self, c: sqlite3.Connection, provider_id: str, model_scope: str = ""
    ) -> sqlite3.Row:
        pid = (provider_id or "").strip().lower() or "unknown"
        ms = model_scope or ""
        row = c.execute(
            "SELECT * FROM provider_circuit WHERE provider_id=? AND model_scope=?",
            (pid, ms),
        ).fetchone()
        if row:
            return row
        now = self.now()
        c.execute(
            "INSERT INTO provider_circuit(provider_id,model_scope,state,updated_at,version)"
            " VALUES(?,?,?,?,0)",
            (pid, ms, CLOSED, now),
        )
        return c.execute(
            "SELECT * FROM provider_circuit WHERE provider_id=? AND model_scope=?",
            (pid, ms),
        ).fetchone()

    def _refresh_open(self, c: sqlite3.Connection, row: sqlite3.Row) -> sqlite3.Row:
        """OPEN → HALF_OPEN when open_until elapsed (durable expiry)."""
        if row["state"] != OPEN:
            return row
        now = self.now()
        open_until = row["open_until"]
        if open_until is None and row["opened_at"] is not None:
            open_until = float(row["opened_at"]) + self.cooldown_seconds
        if open_until is not None and now >= float(open_until):
            c.execute(
                "UPDATE provider_circuit SET state=?, half_open_probes=0,"
                " half_open_probe_owner=NULL, half_open_probe_lease_until=NULL,"
                " last_transition_at=?, last_reason=?, version=version+1, updated_at=?"
                " WHERE provider_id=? AND model_scope=? AND version=?",
                (
                    HALF_OPEN,
                    now,
                    "cooldown_elapsed",
                    now,
                    row["provider_id"],
                    row["model_scope"],
                    row["version"],
                ),
            )
            c.execute(
                "INSERT INTO circuit_transition("
                "transition_id,provider_id,model_scope,from_state,to_state,"
                "reason_code,actor_type,actor_id,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    _id("tr_"),
                    row["provider_id"],
                    row["model_scope"],
                    OPEN,
                    HALF_OPEN,
                    "cooldown_elapsed",
                    "system",
                    "governance",
                    now,
                ),
            )
            self._audit(
                c,
                event_type=EVT_CIRCUIT_HALF_OPENED,
                target_type="circuit",
                target_id=row["provider_id"],
                reason_code="cooldown_elapsed",
                old_state=OPEN,
                new_state=HALF_OPEN,
            )
            return c.execute(
                "SELECT * FROM provider_circuit WHERE provider_id=? AND model_scope=?",
                (row["provider_id"], row["model_scope"]),
            ).fetchone()
        return row

    # ── circuit API ───────────────────────────────────────────────────────

    def circuit_snapshot(
        self, provider_id: str, *, model_scope: str = ""
    ) -> dict[str, Any]:
        with self._lock:
            try:
                c = self._begin()
                row = self._ensure_circuit_row(c, provider_id, model_scope)
                row = self._refresh_open(c, row)
                c.commit()
            except Exception:
                self._conn.rollback()
                raise
            return self._circuit_dict(row)

    def _circuit_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "provider_id": row["provider_id"],
            "model_scope": row["model_scope"],
            "state": row["state"],
            "failure_count": int(row["failure_count"]),
            "success_count": int(row["success_count"]),
            "opened_at": row["opened_at"],
            "open_until": row["open_until"],
            "half_open_probe_owner": row["half_open_probe_owner"],
            "half_open_probe_lease_until": row["half_open_probe_lease_until"],
            "half_open_probes": int(row["half_open_probes"] or 0),
            "last_failure_code": row["last_failure_code"] or "",
            "last_transition_at": row["last_transition_at"],
            "last_success_at": row["last_success_at"],
            "last_failure_at": row["last_failure_at"],
            "last_reason": row["last_reason"] or "",
            "version": int(row["version"]),
            "updated_at": row["updated_at"],
            "process_local": False,
            "persistent": True,
            "config": {
                "failure_threshold": self.failure_threshold,
                "cooldown_seconds": self.cooldown_seconds,
                "half_open_max_probes": self.half_open_max_probes,
                "process_local": False,
                "persistent": True,
            },
        }

    def allow_request(
        self,
        provider_id: str,
        *,
        model_scope: str = "",
        probe_owner: Optional[str] = None,
    ) -> tuple[bool, str, dict[str, Any]]:
        """Transactional allow. HALF_OPEN claims a lease-bound probe slot."""
        owner = probe_owner or _id("probe_")
        with self._lock:
            try:
                c = self._begin()
                row = self._ensure_circuit_row(c, provider_id, model_scope)
                row = self._refresh_open(c, row)
                state = row["state"]
                now = self.now()

                if state == CLOSED:
                    c.commit()
                    return True, "closed", self._circuit_dict(row)

                if state == OPEN:
                    c.commit()
                    return False, "circuit_open", self._circuit_dict(row)

                if state == HALF_OPEN:
                    # Expire abandoned probe lease
                    lease = row["half_open_probe_lease_until"]
                    probes = int(row["half_open_probes"] or 0)
                    if (
                        row["half_open_probe_owner"]
                        and lease is not None
                        and now > float(lease)
                    ):
                        c.execute(
                            "UPDATE provider_circuit SET half_open_probe_owner=NULL,"
                            " half_open_probe_lease_until=NULL, half_open_probes=MAX(0,half_open_probes-1),"
                            " version=version+1, updated_at=? WHERE provider_id=? AND model_scope=?",
                            (now, row["provider_id"], row["model_scope"]),
                        )
                        row = c.execute(
                            "SELECT * FROM provider_circuit WHERE provider_id=? AND model_scope=?",
                            (row["provider_id"], row["model_scope"]),
                        ).fetchone()
                        probes = int(row["half_open_probes"] or 0)

                    if probes >= self.half_open_max_probes and row["half_open_probe_owner"]:
                        # Existing active probe — only same owner may proceed (replay)
                        if row["half_open_probe_owner"] == owner:
                            c.commit()
                            return True, "half_open_probe", self._circuit_dict(row)
                        c.commit()
                        return False, "half_open_probe_exhausted", self._circuit_dict(row)

                    lease_until = now + self.half_open_lease_seconds
                    cur = c.execute(
                        "UPDATE provider_circuit SET half_open_probes=half_open_probes+1,"
                        " half_open_probe_owner=?, half_open_probe_lease_until=?,"
                        " version=version+1, updated_at=?"
                        " WHERE provider_id=? AND model_scope=? AND state=?"
                        " AND (half_open_probes < ? OR half_open_probe_owner IS NULL"
                        "      OR half_open_probe_lease_until < ?)",
                        (
                            owner,
                            lease_until,
                            now,
                            row["provider_id"],
                            row["model_scope"],
                            HALF_OPEN,
                            self.half_open_max_probes,
                            now,
                        ),
                    )
                    if cur.rowcount != 1:
                        c.commit()
                        snap = self._circuit_dict(
                            c.execute(
                                "SELECT * FROM provider_circuit WHERE provider_id=? AND model_scope=?",
                                (row["provider_id"], row["model_scope"]),
                            ).fetchone()
                        )
                        return False, "half_open_probe_exhausted", snap
                    c.commit()
                    snap = self.circuit_snapshot(provider_id, model_scope=model_scope)
                    return True, "half_open_probe", snap

                c.commit()
                return True, "disabled", self._circuit_dict(row)
            except Exception:
                self._conn.rollback()
                raise

    def record_success(
        self,
        provider_id: str,
        *,
        model_scope: str = "",
        attempt_id: str = "",
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        with self._lock:
            try:
                c = self._begin()
                row = self._ensure_circuit_row(c, provider_id, model_scope)
                row = self._refresh_open(c, row)
                now = self.now()
                prev = row["state"]
                c.execute(
                    "UPDATE provider_circuit SET state=?, failure_count=0,"
                    " success_count=success_count+1, opened_at=NULL, open_until=NULL,"
                    " half_open_probes=0, half_open_probe_owner=NULL,"
                    " half_open_probe_lease_until=NULL, last_success_at=?,"
                    " last_transition_at=?, last_reason=?, version=version+1, updated_at=?"
                    " WHERE provider_id=? AND model_scope=?",
                    (
                        CLOSED,
                        now,
                        now,
                        "success",
                        now,
                        row["provider_id"],
                        row["model_scope"],
                    ),
                )
                if prev != CLOSED:
                    c.execute(
                        "INSERT INTO circuit_transition("
                        "transition_id,provider_id,model_scope,from_state,to_state,"
                        "reason_code,attempt_id,actor_type,actor_id,created_at)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            _id("tr_"),
                            row["provider_id"],
                            row["model_scope"],
                            prev,
                            CLOSED,
                            "success",
                            attempt_id,
                            "system",
                            "governance",
                            now,
                        ),
                    )
                    self._audit(
                        c,
                        event_type=EVT_CIRCUIT_CLOSED,
                        target_type="circuit",
                        target_id=row["provider_id"],
                        reason_code="success",
                        attempt_id=attempt_id,
                        old_state=prev,
                        new_state=CLOSED,
                    )
                c.commit()
            except Exception:
                self._conn.rollback()
                raise
            return self.circuit_snapshot(provider_id, model_scope=model_scope)

    def record_failure(
        self,
        provider_id: str,
        *,
        reason: str = "provider_failure",
        counts: bool = True,
        model_scope: str = "",
        attempt_id: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            try:
                c = self._begin()
                row = self._ensure_circuit_row(c, provider_id, model_scope)
                row = self._refresh_open(c, row)
                now = self.now()
                if not counts:
                    c.execute(
                        "UPDATE provider_circuit SET last_reason=?, updated_at=?"
                        " WHERE provider_id=? AND model_scope=?",
                        (f"ignored:{reason}", now, row["provider_id"], row["model_scope"]),
                    )
                    c.commit()
                    return self.circuit_snapshot(provider_id, model_scope=model_scope)

                prev = row["state"]
                fc = int(row["failure_count"]) + 1
                new_state = prev
                open_until = row["open_until"]
                opened_at = row["opened_at"]
                reason_code = reason

                if prev == HALF_OPEN:
                    new_state = OPEN
                    opened_at = now
                    open_until = now + self.cooldown_seconds
                    reason_code = f"half_open_failed:{reason}"
                elif fc >= self.failure_threshold:
                    new_state = OPEN
                    opened_at = now
                    open_until = now + self.cooldown_seconds
                    reason_code = reason

                c.execute(
                    "UPDATE provider_circuit SET state=?, failure_count=?,"
                    " opened_at=?, open_until=?,"
                    " half_open_probes=0, half_open_probe_owner=NULL,"
                    " half_open_probe_lease_until=NULL,"
                    " last_failure_at=?, last_failure_code=?, last_reason=?,"
                    " last_transition_at=?, version=version+1, updated_at=?"
                    " WHERE provider_id=? AND model_scope=?",
                    (
                        new_state,
                        fc,
                        opened_at,
                        open_until,
                        now,
                        reason,
                        reason_code,
                        now if new_state != prev else row["last_transition_at"],
                        now,
                        row["provider_id"],
                        row["model_scope"],
                    ),
                )
                if new_state != prev:
                    c.execute(
                        "INSERT INTO circuit_transition("
                        "transition_id,provider_id,model_scope,from_state,to_state,"
                        "reason_code,attempt_id,actor_type,actor_id,created_at)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            _id("tr_"),
                            row["provider_id"],
                            row["model_scope"],
                            prev,
                            new_state,
                            reason_code,
                            attempt_id,
                            "system",
                            "governance",
                            now,
                        ),
                    )
                    self._audit(
                        c,
                        event_type=EVT_CIRCUIT_OPENED if new_state == OPEN else EVT_CIRCUIT_HALF_OPENED,
                        target_type="circuit",
                        target_id=row["provider_id"],
                        reason_code=reason_code,
                        attempt_id=attempt_id,
                        old_state=prev,
                        new_state=new_state,
                    )
                c.commit()
            except Exception:
                self._conn.rollback()
                raise
            return self.circuit_snapshot(provider_id, model_scope=model_scope)

    def manual_reset(
        self,
        provider_id: str,
        *,
        model_scope: str = "",
        actor_id: str = "operator",
        reason_code: str = "manual_reset",
        confirm: bool = False,
    ) -> dict[str, Any]:
        if not confirm:
            raise GovernanceError(
                GovernanceErrorCode.OPERATOR_AUTH_REQUIRED,
                "circuit reset requires confirm=True",
            )
        with self._lock:
            try:
                c = self._begin()
                row = self._ensure_circuit_row(c, provider_id, model_scope)
                now = self.now()
                prev = row["state"]
                c.execute(
                    "UPDATE provider_circuit SET state=?, failure_count=0,"
                    " half_open_probes=0, half_open_probe_owner=NULL,"
                    " half_open_probe_lease_until=NULL, opened_at=NULL, open_until=NULL,"
                    " last_transition_at=?, last_reason=?, version=version+1, updated_at=?"
                    " WHERE provider_id=? AND model_scope=?",
                    (
                        CLOSED,
                        now,
                        reason_code,
                        now,
                        row["provider_id"],
                        row["model_scope"],
                    ),
                )
                c.execute(
                    "INSERT INTO circuit_transition("
                    "transition_id,provider_id,model_scope,from_state,to_state,"
                    "reason_code,actor_type,actor_id,created_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        _id("tr_"),
                        row["provider_id"],
                        row["model_scope"],
                        prev,
                        CLOSED,
                        reason_code,
                        "operator",
                        actor_id,
                        now,
                    ),
                )
                self._audit(
                    c,
                    event_type=EVT_CIRCUIT_RESET,
                    target_type="circuit",
                    target_id=row["provider_id"],
                    reason_code=reason_code,
                    actor_type="operator",
                    actor_id=actor_id,
                    old_state=prev,
                    new_state=CLOSED,
                )
                c.commit()
            except Exception:
                self._conn.rollback()
                raise
            return self.circuit_snapshot(provider_id, model_scope=model_scope)

    def force_open(
        self,
        provider_id: str,
        *,
        actor_id: str = "operator",
        reason_code: str = "force_open",
        confirm: bool = False,
        model_scope: str = "",
        open_seconds: Optional[float] = None,
    ) -> dict[str, Any]:
        if not confirm:
            raise GovernanceError(
                GovernanceErrorCode.OPERATOR_AUTH_REQUIRED,
                "force-open requires confirm=True",
            )
        with self._lock:
            try:
                c = self._begin()
                row = self._ensure_circuit_row(c, provider_id, model_scope)
                now = self.now()
                prev = row["state"]
                secs = float(open_seconds if open_seconds is not None else self.cooldown_seconds)
                c.execute(
                    "UPDATE provider_circuit SET state=?, opened_at=?, open_until=?,"
                    " half_open_probes=0, half_open_probe_owner=NULL,"
                    " half_open_probe_lease_until=NULL, last_transition_at=?,"
                    " last_reason=?, version=version+1, updated_at=?"
                    " WHERE provider_id=? AND model_scope=?",
                    (
                        OPEN,
                        now,
                        now + secs,
                        now,
                        reason_code,
                        now,
                        row["provider_id"],
                        row["model_scope"],
                    ),
                )
                self._audit(
                    c,
                    event_type=EVT_CIRCUIT_OPENED,
                    target_type="circuit",
                    target_id=row["provider_id"],
                    reason_code=reason_code,
                    actor_type="operator",
                    actor_id=actor_id,
                    old_state=prev,
                    new_state=OPEN,
                )
                c.commit()
            except Exception:
                self._conn.rollback()
                raise
            return self.circuit_snapshot(provider_id, model_scope=model_scope)

    def all_circuit_snapshots(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT provider_id, model_scope FROM provider_circuit ORDER BY provider_id"
            ).fetchall()
        return [
            self.circuit_snapshot(r["provider_id"], model_scope=r["model_scope"])
            for r in rows
        ]

    # ── budget / reservation ──────────────────────────────────────────────

    def get_daily_spend(
        self, caller_id: str, day: Optional[str] = None, *, currency: str = "USD"
    ) -> Decimal:
        dk = day or day_key(self.now())
        cur = (currency or "USD").upper()
        with self._lock:
            row = self._conn.execute(
                "SELECT settled_total, reserved_total FROM daily_spend_agg"
                " WHERE day_key=? AND caller_id=? AND currency=?",
                (dk, caller_id, cur),
            ).fetchone()
            if not row:
                return Decimal("0")
            return _d_str(row["settled_total"]) + _d_str(row["reserved_total"])

    def get_settled_daily_spend(
        self, caller_id: str, day: Optional[str] = None, *, currency: str = "USD"
    ) -> Decimal:
        dk = day or day_key(self.now())
        cur = (currency or "USD").upper()
        with self._lock:
            row = self._conn.execute(
                "SELECT settled_total FROM daily_spend_agg"
                " WHERE day_key=? AND caller_id=? AND currency=?",
                (dk, caller_id, cur),
            ).fetchone()
            return _d_str(row["settled_total"]) if row else Decimal("0")

    def _agg_touch(
        self,
        c: sqlite3.Connection,
        *,
        day: str,
        caller_id: str,
        currency: str,
        reserved_delta: Decimal = Decimal("0"),
        settled_delta: Decimal = Decimal("0"),
    ) -> None:
        cur = currency.upper()
        now = self.now()
        row = c.execute(
            "SELECT * FROM daily_spend_agg WHERE day_key=? AND caller_id=? AND currency=?",
            (day, caller_id, cur),
        ).fetchone()
        if not row:
            c.execute(
                "INSERT INTO daily_spend_agg("
                "day_key,caller_id,currency,settled_total,reserved_total,version,updated_at)"
                " VALUES(?,?,?,?,?,0,?)",
                (
                    day,
                    caller_id,
                    cur,
                    str(settled_delta.quantize(_QUANT)),
                    str(reserved_delta.quantize(_QUANT)),
                    now,
                ),
            )
            return
        new_settled = _d_str(row["settled_total"]) + settled_delta
        new_reserved = _d_str(row["reserved_total"]) + reserved_delta
        if new_settled < 0 or new_reserved < 0:
            raise GovernanceError(
                GovernanceErrorCode.GOVERNANCE_STATE_CONFLICT,
                "daily aggregate would go negative",
            )
        c.execute(
            "UPDATE daily_spend_agg SET settled_total=?, reserved_total=?,"
            " version=version+1, updated_at=? WHERE day_key=? AND caller_id=? AND currency=?",
            (
                str(new_settled.quantize(_QUANT)),
                str(new_reserved.quantize(_QUANT)),
                now,
                day,
                caller_id,
                cur,
            ),
        )

    def reserve_budget(
        self,
        *,
        request_id: str,
        attempt_id: str,
        caller_id: str,
        provider_id: str,
        model_id: str = "",
        currency: str = "USD",
        amount: Any,
        budget_scope: str = "caller_daily",
        daily_budget: Optional[Any] = None,
        idempotency_key: Optional[str] = None,
        expires_at: Optional[float] = None,
        zero_cost: bool = False,
    ) -> dict[str, Any]:
        """Transactional reservation. Concurrent workers cannot overspend."""
        cur = (currency or "USD").upper()
        if cur != "USD":
            raise GovernanceError(
                GovernanceErrorCode.COST_CURRENCY_MISMATCH,
                f"unsupported currency {cur}",
            )
        amt = Decimal("0") if zero_cost else _money(amount)
        idem = idempotency_key or f"res:{attempt_id}"
        now = self.now()
        exp = float(expires_at if expires_at is not None else now + self.reservation_ttl_seconds)
        dk = day_key(now)
        rid = _id("rsv_")

        with self._lock:
            try:
                c = self._begin()
                existing = c.execute(
                    "SELECT * FROM budget_reservation WHERE idempotency_key=?",
                    (idem,),
                ).fetchone()
                if existing:
                    c.commit()
                    return dict(existing)

                existing_attempt = c.execute(
                    "SELECT * FROM budget_reservation WHERE attempt_id=?",
                    (attempt_id,),
                ).fetchone()
                if existing_attempt:
                    c.commit()
                    return dict(existing_attempt)

                # Check budget under lock (settled + reserved + new)
                if daily_budget is not None and not zero_cost:
                    bud = _money(daily_budget)
                    if bud > 0:
                        spent = Decimal("0")
                        row = c.execute(
                            "SELECT settled_total, reserved_total FROM daily_spend_agg"
                            " WHERE day_key=? AND caller_id=? AND currency=?",
                            (dk, caller_id, cur),
                        ).fetchone()
                        if row:
                            spent = _d_str(row["settled_total"]) + _d_str(row["reserved_total"])
                        if spent + amt > bud:
                            self._audit(
                                c,
                                event_type=EVT_BUDGET_DENIED,
                                target_type="budget",
                                target_id=caller_id,
                                reason_code="daily_budget",
                                request_id=request_id,
                                attempt_id=attempt_id,
                                old_state=str(spent),
                                new_state=str(spent + amt),
                            )
                            c.commit()
                            raise GovernanceError(
                                GovernanceErrorCode.BUDGET_DENIED,
                                "Daily caller budget would be exceeded",
                                details={
                                    "spent": str(spent),
                                    "requested": str(amt),
                                    "budget": str(bud),
                                    "day_key": dk,
                                },
                            )

                c.execute(
                    "INSERT INTO budget_reservation("
                    "reservation_id,request_id,attempt_id,caller_id,budget_scope,"
                    "provider_id,model_id,currency,reserved_amount,status,"
                    "expires_at,created_at,idempotency_key,day_key,attempt_started)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
                    (
                        rid,
                        request_id,
                        attempt_id,
                        caller_id,
                        budget_scope,
                        provider_id,
                        model_id,
                        cur,
                        str(amt),
                        RESERVED,
                        exp,
                        now,
                        idem,
                        dk,
                    ),
                )
                if amt > 0:
                    self._agg_touch(
                        c,
                        day=dk,
                        caller_id=caller_id,
                        currency=cur,
                        reserved_delta=amt,
                    )
                self._audit(
                    c,
                    event_type=EVT_RESERVATION_CREATED,
                    target_type="reservation",
                    target_id=rid,
                    reason_code="reserved",
                    request_id=request_id,
                    attempt_id=attempt_id,
                    new_state=str(amt),
                )
                c.commit()
            except GovernanceError:
                raise
            except Exception:
                self._conn.rollback()
                raise
            return self.get_reservation(rid)  # type: ignore[return-value]

    def get_reservation(self, reservation_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM budget_reservation WHERE reservation_id=?",
                (reservation_id,),
            ).fetchone()
            return dict(row) if row else None

    def mark_attempt_started(self, reservation_id: str) -> dict[str, Any]:
        with self._lock:
            try:
                c = self._begin()
                row = c.execute(
                    "SELECT * FROM budget_reservation WHERE reservation_id=?",
                    (reservation_id,),
                ).fetchone()
                if not row:
                    raise GovernanceError(
                        GovernanceErrorCode.RESERVATION_INVALID_STATE,
                        "reservation not found",
                    )
                if row["status"] != RESERVED:
                    raise GovernanceError(
                        GovernanceErrorCode.RESERVATION_INVALID_STATE,
                        f"cannot start from status {row['status']}",
                    )
                now = self.now()
                if now > float(row["expires_at"]):
                    raise GovernanceError(
                        GovernanceErrorCode.RESERVATION_EXPIRED,
                        "reservation expired before execution",
                    )
                c.execute(
                    "UPDATE budget_reservation SET attempt_started=1 WHERE reservation_id=?",
                    (reservation_id,),
                )
                c.commit()
            except GovernanceError:
                self._conn.rollback()
                raise
            except Exception:
                self._conn.rollback()
                raise
            return self.get_reservation(reservation_id)  # type: ignore[return-value]

    def settle_reservation(
        self,
        reservation_id: str,
        *,
        actual_cost: Any,
        input_units: int = 0,
        output_units: int = 0,
        usage_status: str = ACTUAL,
        idempotency_key: Optional[str] = None,
        notes: str = "",
    ) -> dict[str, Any]:
        actual = _money(actual_cost)
        with self._lock:
            try:
                c = self._begin()
                row = c.execute(
                    "SELECT * FROM budget_reservation WHERE reservation_id=?",
                    (reservation_id,),
                ).fetchone()
                if not row:
                    raise GovernanceError(
                        GovernanceErrorCode.RESERVATION_INVALID_STATE,
                        "reservation not found",
                    )
                if row["status"] == SETTLED:
                    # Idempotent: return existing usage
                    usage = c.execute(
                        "SELECT * FROM cost_usage WHERE reservation_id=?",
                        (reservation_id,),
                    ).fetchone()
                    c.commit()
                    return {
                        "reservation": dict(row),
                        "usage": dict(usage) if usage else None,
                        "idempotent": True,
                    }
                if row["status"] in {RELEASED, EXPIRED, CANCELLED}:
                    raise GovernanceError(
                        GovernanceErrorCode.RESERVATION_INVALID_STATE,
                        f"cannot settle reservation in status {row['status']}",
                    )
                if row["status"] != RESERVED and row["status"] != RECONCILIATION:
                    raise GovernanceError(
                        GovernanceErrorCode.RESERVATION_INVALID_STATE,
                        f"invalid settle status {row['status']}",
                    )

                reserved = _d_str(row["reserved_amount"])
                if actual > reserved and reserved > 0:
                    # Soft overage: still settle but note (policy may have used estimate)
                    notes = (notes + ";overage").strip(";")

                now = self.now()
                usage_id = _id("usg_")
                u_idem = idempotency_key or f"usg:{row['attempt_id']}"

                existing_u = c.execute(
                    "SELECT * FROM cost_usage WHERE idempotency_key=?", (u_idem,)
                ).fetchone()
                if existing_u:
                    c.commit()
                    return {
                        "reservation": dict(row),
                        "usage": dict(existing_u),
                        "idempotent": True,
                    }

                c.execute(
                    "INSERT INTO cost_usage("
                    "usage_id,request_id,attempt_id,reservation_id,caller_id,"
                    "provider_id,model_id,currency,estimated_cost,actual_cost,"
                    "input_units,output_units,status,occurred_at,settled_at,"
                    "idempotency_key,day_key,attempt_number,notes)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        usage_id,
                        row["request_id"],
                        row["attempt_id"],
                        reservation_id,
                        row["caller_id"],
                        row["provider_id"],
                        row["model_id"],
                        row["currency"],
                        row["reserved_amount"],
                        str(actual),
                        int(input_units),
                        int(output_units),
                        usage_status,
                        now,
                        now,
                        u_idem,
                        row["day_key"],
                        1,
                        notes,
                    ),
                )
                c.execute(
                    "UPDATE budget_reservation SET status=?, settled_amount=?,"
                    " settled_at=?, provider_outcome='completed' WHERE reservation_id=?",
                    (SETTLED, str(actual), now, reservation_id),
                )
                # Move reserved → settled in aggregate
                if reserved > 0:
                    self._agg_touch(
                        c,
                        day=row["day_key"],
                        caller_id=row["caller_id"],
                        currency=row["currency"],
                        reserved_delta=-reserved,
                        settled_delta=actual,
                    )
                elif actual > 0:
                    self._agg_touch(
                        c,
                        day=row["day_key"],
                        caller_id=row["caller_id"],
                        currency=row["currency"],
                        settled_delta=actual,
                    )
                self._audit(
                    c,
                    event_type=EVT_RESERVATION_SETTLED,
                    target_type="reservation",
                    target_id=reservation_id,
                    reason_code="settled",
                    request_id=row["request_id"],
                    attempt_id=row["attempt_id"],
                    old_state=row["status"],
                    new_state=SETTLED,
                )
                self._audit(
                    c,
                    event_type=EVT_USAGE_RECORDED,
                    target_type="usage",
                    target_id=usage_id,
                    reason_code=usage_status,
                    request_id=row["request_id"],
                    attempt_id=row["attempt_id"],
                    new_state=str(actual),
                )
                c.commit()
            except GovernanceError:
                self._conn.rollback()
                raise
            except Exception:
                self._conn.rollback()
                raise
            return {
                "reservation": self.get_reservation(reservation_id),
                "usage": self.get_usage_by_attempt(row["attempt_id"]),
                "idempotent": False,
            }

    def release_reservation(
        self,
        reservation_id: str,
        *,
        reason_code: str = "released",
        status: str = RELEASED,
    ) -> dict[str, Any]:
        with self._lock:
            try:
                c = self._begin()
                row = c.execute(
                    "SELECT * FROM budget_reservation WHERE reservation_id=?",
                    (reservation_id,),
                ).fetchone()
                if not row:
                    raise GovernanceError(
                        GovernanceErrorCode.RESERVATION_INVALID_STATE,
                        "reservation not found",
                    )
                if row["status"] in {SETTLED, RELEASED, EXPIRED, CANCELLED}:
                    c.commit()
                    return dict(row)  # idempotent
                if row["status"] not in {RESERVED, RECONCILIATION, FAILED}:
                    raise GovernanceError(
                        GovernanceErrorCode.RESERVATION_INVALID_STATE,
                        f"cannot release from {row['status']}",
                    )
                now = self.now()
                reserved = _d_str(row["reserved_amount"])
                c.execute(
                    "UPDATE budget_reservation SET status=?, released_at=?,"
                    " provider_outcome=? WHERE reservation_id=?",
                    (status, now, reason_code, reservation_id),
                )
                if reserved > 0 and row["status"] == RESERVED:
                    self._agg_touch(
                        c,
                        day=row["day_key"],
                        caller_id=row["caller_id"],
                        currency=row["currency"],
                        reserved_delta=-reserved,
                    )
                evt = (
                    EVT_RESERVATION_EXPIRED
                    if status == EXPIRED
                    else EVT_RESERVATION_RELEASED
                )
                self._audit(
                    c,
                    event_type=evt,
                    target_type="reservation",
                    target_id=reservation_id,
                    reason_code=reason_code,
                    request_id=row["request_id"],
                    attempt_id=row["attempt_id"],
                    old_state=row["status"],
                    new_state=status,
                )
                c.commit()
            except GovernanceError:
                self._conn.rollback()
                raise
            except Exception:
                self._conn.rollback()
                raise
            return self.get_reservation(reservation_id)  # type: ignore[return-value]

    def get_usage_by_attempt(self, attempt_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM cost_usage WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            return dict(row) if row else None

    def request_usage_total(self, request_id: str) -> Decimal:
        with self._lock:
            rows = self._conn.execute(
                "SELECT actual_cost, estimated_cost FROM cost_usage WHERE request_id=?",
                (request_id,),
            ).fetchall()
            total = Decimal("0")
            for r in rows:
                if r["actual_cost"] is not None:
                    total += _d_str(r["actual_cost"])
                else:
                    total += _d_str(r["estimated_cost"])
            return total

    # ── recovery ──────────────────────────────────────────────────────────

    def classify_stale_reservation(self, row: dict[str, Any] | sqlite3.Row) -> str:
        status = row["status"]
        if status == SETTLED:
            return ALREADY_SETTLED
        if status in {RELEASED, EXPIRED, CANCELLED}:
            return ALREADY_SETTLED  # terminal non-charge
        if status == RECONCILIATION:
            return NEEDS_RECONCILIATION
        if status != RESERVED and status != FAILED:
            return INVALID_STATE
        now = self.now()
        expired = now > float(row["expires_at"])
        started = bool(row["attempt_started"])
        outcome = (row["provider_outcome"] or "").strip()
        if outcome == "completed":
            return ALREADY_SETTLED  # should have been settled
        if not started and (expired or outcome in {"", "not_started", "pre_transport"}):
            return SAFE_RELEASE
        if started and not outcome:
            return PROVIDER_ATTEMPT_UNKNOWN
        if outcome in {"failed_pre_transport", "not_started"}:
            return SAFE_RELEASE
        if outcome == "unknown":
            return PROVIDER_ATTEMPT_UNKNOWN
        return NEEDS_RECONCILIATION

    def recover_stale_reservations(self, *, limit: int = 200) -> dict[str, Any]:
        """Idempotent recovery. Does not call providers. Does not fabricate usage."""
        results: list[dict[str, Any]] = []
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM budget_reservation WHERE status IN (?,?,?)"
                " ORDER BY created_at ASC LIMIT ?",
                (RESERVED, RECONCILIATION, FAILED, int(limit)),
            ).fetchall()
        for row in rows:
            d = dict(row)
            cls = self.classify_stale_reservation(d)
            action = "none"
            if cls == SAFE_RELEASE:
                self.release_reservation(
                    d["reservation_id"],
                    reason_code="recovery_safe_release",
                    status=EXPIRED if self.now() > float(d["expires_at"]) else RELEASED,
                )
                action = "released"
            elif cls in {PROVIDER_ATTEMPT_UNKNOWN, NEEDS_RECONCILIATION}:
                with self._lock:
                    try:
                        c = self._begin()
                        c.execute(
                            "UPDATE budget_reservation SET status=? WHERE reservation_id=? AND status=?",
                            (RECONCILIATION, d["reservation_id"], d["status"]),
                        )
                        self._audit(
                            c,
                            event_type=EVT_RESERVATION_RECONCILIATION,
                            target_type="reservation",
                            target_id=d["reservation_id"],
                            reason_code=cls,
                            request_id=d["request_id"],
                            attempt_id=d["attempt_id"],
                            old_state=d["status"],
                            new_state=RECONCILIATION,
                        )
                        c.commit()
                        action = "reconciliation_required"
                    except Exception:
                        self._conn.rollback()
                        action = "error"
            elif cls == ALREADY_SETTLED:
                action = "noop"
            results.append(
                {
                    "reservation_id": d["reservation_id"],
                    "classification": cls,
                    "action": action,
                }
            )
        unresolved = self.list_unresolved_reservations()
        return {
            "schema": "m24.reservation_recovery.v1",
            "processed": len(results),
            "results": results,
            "unresolved_count": len(unresolved),
            "unresolved": unresolved,
        }

    def list_unresolved_reservations(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT reservation_id,request_id,attempt_id,caller_id,provider_id,"
                "status,reserved_amount,currency,expires_at,attempt_started,provider_outcome"
                " FROM budget_reservation WHERE status=?"
                " ORDER BY created_at ASC",
                (RECONCILIATION,),
            ).fetchall()
            return [dict(r) for r in rows]

    def operator_resolve_reservation(
        self,
        reservation_id: str,
        *,
        resolution: str,
        actor_id: str,
        reason_code: str,
        actual_cost: Any = None,
        confirm: bool = False,
    ) -> dict[str, Any]:
        if not confirm:
            raise GovernanceError(
                GovernanceErrorCode.OPERATOR_AUTH_REQUIRED,
                "operator resolution requires confirm=True",
            )
        if not reason_code:
            raise GovernanceError(
                GovernanceErrorCode.OPERATOR_OVERRIDE_INVALID,
                "reason_code required",
            )
        resolution = resolution.lower().strip()
        if resolution == "release":
            return self.release_reservation(
                reservation_id, reason_code=reason_code, status=RELEASED
            )
        if resolution == "settle":
            if actual_cost is None:
                raise GovernanceError(
                    GovernanceErrorCode.OPERATOR_OVERRIDE_INVALID,
                    "actual_cost required for settle resolution",
                )
            return self.settle_reservation(
                reservation_id,
                actual_cost=actual_cost,
                notes=f"operator_resolve:{actor_id}",
            )
        raise GovernanceError(
            GovernanceErrorCode.OPERATOR_OVERRIDE_INVALID,
            f"unknown resolution {resolution}",
        )

    # ── overrides ─────────────────────────────────────────────────────────

    def create_override(
        self,
        *,
        override_type: str,
        target_type: str,
        target_id: str,
        payload: dict[str, Any],
        reason_code: str,
        actor_id: str,
        expires_at: float,
        confirm: bool = False,
    ) -> dict[str, Any]:
        if not confirm:
            raise GovernanceError(
                GovernanceErrorCode.OPERATOR_AUTH_REQUIRED,
                "override create requires confirm=True",
            )
        if not reason_code or not actor_id:
            raise GovernanceError(
                GovernanceErrorCode.OPERATOR_OVERRIDE_INVALID,
                "reason_code and actor_id required",
            )
        # Hard bans
        if override_type in {
            "enable_cloud_fallback",
            "production_certified",
            "bypass_kill_switch",
            "trading_guardian",
        }:
            raise GovernanceError(
                GovernanceErrorCode.OPERATOR_OVERRIDE_INVALID,
                f"override type forbidden: {override_type}",
            )
        now = self.now()
        if float(expires_at) <= now:
            raise GovernanceError(
                GovernanceErrorCode.OPERATOR_OVERRIDE_INVALID,
                "override expires_at must be in the future",
            )
        oid = _id("ovr_")
        with self._lock:
            try:
                c = self._begin()
                c.execute(
                    "INSERT INTO operator_override("
                    "override_id,override_type,target_type,target_id,payload_json,"
                    "reason_code,actor_id,created_at,expires_at,active)"
                    " VALUES(?,?,?,?,?,?,?,?,?,1)",
                    (
                        oid,
                        override_type,
                        target_type,
                        target_id,
                        json.dumps(payload or {}),
                        reason_code,
                        actor_id,
                        now,
                        float(expires_at),
                    ),
                )
                self._audit(
                    c,
                    event_type=EVT_OVERRIDE_CREATED,
                    target_type=target_type,
                    target_id=target_id,
                    reason_code=reason_code,
                    actor_type="operator",
                    actor_id=actor_id,
                    new_state=override_type,
                )
                c.commit()
            except Exception:
                self._conn.rollback()
                raise
            return self.get_override(oid)  # type: ignore[return-value]

    def get_override(self, override_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM operator_override WHERE override_id=?",
                (override_id,),
            ).fetchone()
            return dict(row) if row else None

    def revoke_override(
        self,
        override_id: str,
        *,
        actor_id: str,
        reason_code: str = "revoked",
        confirm: bool = False,
    ) -> dict[str, Any]:
        if not confirm:
            raise GovernanceError(
                GovernanceErrorCode.OPERATOR_AUTH_REQUIRED,
                "override revoke requires confirm=True",
            )
        with self._lock:
            try:
                c = self._begin()
                row = c.execute(
                    "SELECT * FROM operator_override WHERE override_id=?",
                    (override_id,),
                ).fetchone()
                if not row:
                    raise GovernanceError(
                        GovernanceErrorCode.OPERATOR_OVERRIDE_INVALID,
                        "override not found",
                    )
                now = self.now()
                c.execute(
                    "UPDATE operator_override SET active=0, revoked_at=?, revoked_by=?"
                    " WHERE override_id=?",
                    (now, actor_id, override_id),
                )
                self._audit(
                    c,
                    event_type=EVT_OVERRIDE_REVOKED,
                    target_type=row["target_type"],
                    target_id=row["target_id"],
                    reason_code=reason_code,
                    actor_type="operator",
                    actor_id=actor_id,
                    old_state="active",
                    new_state="revoked",
                )
                c.commit()
            except GovernanceError:
                self._conn.rollback()
                raise
            except Exception:
                self._conn.rollback()
                raise
            return self.get_override(override_id)  # type: ignore[return-value]

    def list_audit(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM governance_audit ORDER BY created_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]

    def readiness(self) -> dict[str, Any]:
        ok = self.schema_ready()
        try:
            self._conn.execute("SELECT 1 FROM provider_circuit LIMIT 1")
            store_ok = True
        except Exception as e:
            store_ok = False
            ok = False
            err = type(e).__name__
        else:
            err = ""
        return {
            "schema": "m24.governance_readiness.v1",
            "schema_ready": self.schema_ready(),
            "store_available": store_ok,
            "schema_version": SCHEMA_VERSION,
            "path": str(self.path),
            "budget_day_tz": budget_day_timezone_name(),
            "ok": ok and store_ok,
            "error": err,
            "process_local_authority": False,
        }


# ── global singleton ──────────────────────────────────────────────────────

_GLOBAL: Optional[DurableGovernanceStore] = None
_GLOBAL_LOCK = threading.Lock()


def get_governance_store(
    *,
    reset: bool = False,
    db_path: str | Path | None = None,
    clock: Optional[Clock] = None,
    **kwargs: Any,
) -> DurableGovernanceStore:
    """Canonical durable governance store singleton.

    Production uses DEFAULT_DB. Tests should call ``reset_governance_store_for_tests``.
    """
    global _GLOBAL
    with _GLOBAL_LOCK:
        if reset:
            if _GLOBAL is not None:
                try:
                    _GLOBAL.close()
                except Exception:
                    pass
                _GLOBAL = None
        if _GLOBAL is None:
            path = db_path if db_path is not None else DEFAULT_DB
            _GLOBAL = DurableGovernanceStore(path, clock=clock, **kwargs)
            return _GLOBAL
        if clock is not None:
            _GLOBAL.set_clock(clock)
        return _GLOBAL


def reset_governance_store_for_tests(
    db_path: str | Path,
    *,
    clock: Optional[Clock] = None,
    **kwargs: Any,
) -> DurableGovernanceStore:
    """Test helper — always installs a fresh store at db_path as global."""
    return get_governance_store(reset=True, db_path=db_path, clock=clock, **kwargs)
