"""M17.9 durable run ledger — transactional, ownership-safe, concurrency-proof.

Upgrades M17.8's single-process append-only JSONL journal into a SQLite-backed
run ledger with an explicit state machine, optimistic-concurrency (compare-and-set
on `state_version`) transitions, terminal-state immutability, ownership-gated
cancellation, exactly-once crash reconciliation, bounded heartbeats, and recovery
operations. It does NOT add a second execution engine: every process still runs
through the ONE ApplicationHarnessAdapter boundary — the ledger is the durable
state + recovery layer beneath it.

Follows the canonical SaathiOS SQLite store pattern (see
`saathi/connectors/platform/store.py`): `data/*.db`, `_SCHEMA` executescript,
row_factory, unique indexes for idempotency, and event-bus emission. No raw
secrets are ever stored — metadata is sanitized on the way in.

Transactional guarantees (all proven live + multi-process in the M17.9 tests):
- one claimant per run: `claim()` is a CAS on (state=queued, state_version) inside
  a `BEGIN IMMEDIATE` txn, so exactly one process wins;
- terminal immutability: a run in a terminal state can never return to running;
- stale writers fail closed: a transition with an out-of-date `state_version` is
  rejected, never silently applied;
- cancellation/completion races resolve deterministically: whoever commits first
  wins; the loser sees a non-active state and is rejected (no double side effect);
- crash recovery is exactly-once + idempotent: a dead PID is reconciled to
  `crash_recovered` once; repeat reconciles are no-ops; a live PID is untouched.

Truthful classification (documented, not pretended):
- transactional *run state* is not exactly-once *external* side effects — an
  uncertain outcome is recorded as `stop_uncertain`, never blindly retried;
- recovery never reruns a non-idempotent operation.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = ROOT / "data" / "application_harness_runs" / "ledger.db"

# ── canonical states ────────────────────────────────────────────────────────
QUEUED = "queued"
STARTING = "starting"
RUNNING = "running"
CANCEL_REQ = "cancellation_requested"
CANCELLED = "cancelled"
SUCCEEDED = "succeeded"
FAILED = "failed"
TIMED_OUT = "timed_out"
CRASH_RECOVERED = "crash_recovered"
BLOCKED = "blocked"
STOP_UNCERTAIN = "stop_uncertain"

ACTIVE = {QUEUED, STARTING, RUNNING, CANCEL_REQ}
TERMINAL = {CANCELLED, SUCCEEDED, FAILED, TIMED_OUT, CRASH_RECOVERED, BLOCKED,
            STOP_UNCERTAIN}
ALL_STATES = ACTIVE | TERMINAL

# explicit transition graph — anything not listed is rejected (fail closed)
VALID: dict[str, set[str]] = {
    QUEUED: {STARTING, CANCELLED, BLOCKED, STOP_UNCERTAIN},
    STARTING: {RUNNING, FAILED, TIMED_OUT, CANCELLED, BLOCKED, CRASH_RECOVERED,
               STOP_UNCERTAIN},
    RUNNING: {SUCCEEDED, FAILED, TIMED_OUT, CANCEL_REQ, CRASH_RECOVERED,
              STOP_UNCERTAIN},
    CANCEL_REQ: {CANCELLED, SUCCEEDED, FAILED, TIMED_OUT, CRASH_RECOVERED,
                 STOP_UNCERTAIN},
}

# legacy (M17.8 JSONL) → ledger terminal names
_LEGACY_STATE = {"success": SUCCEEDED, "failed": FAILED, "timeout": TIMED_OUT,
                 "cancelled": CANCELLED, "crash_recovered": CRASH_RECOVERED,
                 "running": RUNNING, "blocked": BLOCKED}

_TRANSITION_HISTORY_CAP = 500     # bound exposed history (DoS / unbounded probe)

# secret-shaped metadata is refused entry — the ledger never stores secrets
_SECRET_KEY = re.compile(r"(?i)(secret|password|passwd|api[_-]?key|token|"
                         r"authorization|bearer|private[_-]?key|credential)")
_SECRET_VAL = re.compile(r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{12,}|ghp_[A-Za-z0-9]{20,}|"
                         r"xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class LedgerError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


class LedgerTransitionError(LedgerError):
    pass


class LedgerConcurrencyError(LedgerError):
    pass


class LedgerSecurityError(LedgerError):
    pass


def _now() -> float:
    return round(time.time(), 3)


def _pid_alive(pid) -> bool:
    if pid is None:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # exists but not ours
    except Exception:
        return False


def _reject_secrets(obj, *, where: str) -> None:
    """Fail closed if any key/value looks like a secret. Recurses dict/list."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and _SECRET_KEY.search(k):
                raise LedgerSecurityError("LEDGER_SECRET_REJECTED",
                                          f"secret-shaped key in {where}: {k}")
            _reject_secrets(v, where=where)
    elif isinstance(obj, list):
        for v in obj:
            _reject_secrets(v, where=where)
    elif isinstance(obj, str):
        if _SECRET_VAL.search(obj):
            raise LedgerSecurityError("LEDGER_SECRET_REJECTED",
                                      f"secret-shaped value in {where}")


def _clean_str(v, *, field: str, maxlen: int = 512) -> str:
    s = "" if v is None else str(v)
    if _CTRL.search(s):
        raise LedgerSecurityError("LEDGER_FIELD_REJECTED",
                                  f"control char in {field}")
    return s[:maxlen]


def _mission_params(raw) -> dict:
    """Decode the owner-safe params JSON blob back to a dict (never raises)."""
    try:
        d = json.loads(raw) if isinstance(raw, str) else (raw or {})
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _validate_db_path(path: Path) -> Path:
    """Reject NUL/traversal and symlink substitution of the ledger file."""
    raw = str(path)
    if "\x00" in raw:
        raise LedgerSecurityError("LEDGER_DB_PATH_REJECTED", "nul in path")
    p = Path(path)
    if p.is_symlink():
        raise LedgerSecurityError("LEDGER_DB_PATH_REJECTED", "ledger db is a symlink")
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.parent.is_symlink():
        raise LedgerSecurityError("LEDGER_DB_PATH_REJECTED", "ledger dir is a symlink")
    return p


_SCHEMA = """
CREATE TABLE IF NOT EXISTS run(
  run_id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  device TEXT DEFAULT 'local',
  os_user TEXT DEFAULT '',
  session TEXT DEFAULT '',
  harness_id TEXT DEFAULT '',
  installation_id TEXT DEFAULT '',
  operation_id TEXT DEFAULT '',
  intent_digest TEXT DEFAULT '',
  approval_id TEXT DEFAULT '',
  idempotency_key TEXT DEFAULT '',
  pid INTEGER,
  pgid INTEGER,
  state TEXT NOT NULL,
  state_version INTEGER NOT NULL DEFAULT 0,
  created_at REAL,
  started_at REAL DEFAULT 0,
  heartbeat_at REAL DEFAULT 0,
  cancel_requested_at REAL DEFAULT 0,
  terminal_at REAL DEFAULT 0,
  exit_code INTEGER,
  signal INTEGER,
  timeout REAL DEFAULT 0,
  failure_code TEXT DEFAULT '',
  verification_status TEXT DEFAULT 'unverified',
  artifact_refs TEXT DEFAULT '[]',
  recovery_status TEXT DEFAULT 'none',
  correlation_id TEXT DEFAULT '',
  origin TEXT DEFAULT 'ledger');
CREATE TABLE IF NOT EXISTS run_transition(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  from_state TEXT,
  to_state TEXT NOT NULL,
  state_version INTEGER,
  actor TEXT DEFAULT '',
  reason TEXT DEFAULT '',
  ts REAL);
CREATE TABLE IF NOT EXISTS run_alert(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  alert_class TEXT NOT NULL,
  severity TEXT NOT NULL,
  state_key TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  owner TEXT DEFAULT '',
  detail TEXT DEFAULT '',
  created_at REAL,
  acknowledged_at REAL DEFAULT 0,
  acknowledged_by TEXT DEFAULT '',
  resolved_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS run_alert_delivery(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alert_id INTEGER NOT NULL,
  owner TEXT DEFAULT '',
  channel TEXT NOT NULL,
  destination_key TEXT DEFAULT '',
  payload_fingerprint TEXT NOT NULL,
  idem_key TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempt_count INTEGER DEFAULT 0,
  max_attempts INTEGER DEFAULT 5,
  next_attempt_at REAL DEFAULT 0,
  first_attempt_at REAL DEFAULT 0,
  last_attempt_at REAL DEFAULT 0,
  delivered_at REAL DEFAULT 0,
  terminal_failed_at REAL DEFAULT 0,
  last_error_code TEXT DEFAULT '',
  last_error_summary TEXT DEFAULT '',
  claim_owner TEXT DEFAULT '',
  claim_at REAL DEFAULT 0,
  created_at REAL,
  updated_at REAL,
  FOREIGN KEY(alert_id) REFERENCES run_alert(id));
CREATE TABLE IF NOT EXISTS pipeline_run(
  pipeline_id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  name TEXT DEFAULT '',
  state TEXT NOT NULL DEFAULT 'pending',
  step_count INTEGER DEFAULT 0,
  failed_step INTEGER DEFAULT -1,
  failure_code TEXT DEFAULT '',
  correlation_id TEXT DEFAULT '',
  created_at REAL,
  started_at REAL DEFAULT 0,
  terminal_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS pipeline_step(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pipeline_id TEXT NOT NULL,
  step_index INTEGER NOT NULL,
  step_name TEXT DEFAULT '',
  harness_id TEXT DEFAULT '',
  operation_id TEXT DEFAULT '',
  run_id TEXT DEFAULT '',
  status TEXT DEFAULT '',
  error_code TEXT DEFAULT '',
  artifact TEXT DEFAULT '',
  recorded_at REAL,
  UNIQUE(pipeline_id, step_index),
  FOREIGN KEY(pipeline_id) REFERENCES pipeline_run(pipeline_id));
CREATE TABLE IF NOT EXISTS mission(
  mission_id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  title TEXT DEFAULT '',
  objective TEXT DEFAULT '',
  mission_type TEXT DEFAULT 'manual',
  trigger TEXT DEFAULT 'manual',
  priority TEXT DEFAULT 'normal',
  risk INTEGER DEFAULT 0,
  approval_required INTEGER DEFAULT 0,
  template TEXT DEFAULT '',
  params TEXT DEFAULT '{}',
  schedule TEXT DEFAULT '',
  state TEXT NOT NULL DEFAULT 'draft',
  run_count INTEGER DEFAULT 0,
  last_pipeline_id TEXT DEFAULT '',
  failure_code TEXT DEFAULT '',
  correlation_id TEXT DEFAULT '',
  created_at REAL,
  approved_at REAL DEFAULT 0,
  approved_by TEXT DEFAULT '',
  queued_at REAL DEFAULT 0,
  started_at REAL DEFAULT 0,
  terminal_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS mission_run(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  mission_id TEXT NOT NULL,
  attempt INTEGER NOT NULL,
  pipeline_id TEXT DEFAULT '',
  state TEXT DEFAULT 'running',
  failure_code TEXT DEFAULT '',
  steps_run INTEGER DEFAULT 0,
  started_at REAL,
  terminal_at REAL DEFAULT 0,
  UNIQUE(mission_id, attempt),
  FOREIGN KEY(mission_id) REFERENCES mission(mission_id));
CREATE TABLE IF NOT EXISTS mission_schedule(
  schedule_id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  mission_template_id TEXT NOT NULL,
  schedule_type TEXT NOT NULL,
  timezone TEXT DEFAULT 'UTC',
  expression TEXT DEFAULT '{}',
  params TEXT DEFAULT '{}',
  enabled INTEGER DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'active',
  description TEXT DEFAULT '',
  retry_policy TEXT DEFAULT 'default',
  version INTEGER DEFAULT 1,
  next_due_at REAL DEFAULT 0,
  last_due_at REAL DEFAULT 0,
  last_occurrence_id TEXT DEFAULT '',
  created_at REAL,
  updated_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS mission_occurrence(
  occurrence_id TEXT PRIMARY KEY,
  schedule_id TEXT NOT NULL,
  owner TEXT NOT NULL,
  due_at REAL NOT NULL,
  dedup_key TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending',
  claim_owner TEXT DEFAULT '',
  lease_expires_at REAL DEFAULT 0,
  attempt_count INTEGER DEFAULT 0,
  next_attempt_at REAL DEFAULT 0,
  mission_id TEXT DEFAULT '',
  mission_run_id TEXT DEFAULT '',
  failure_category TEXT DEFAULT '',
  failure_summary TEXT DEFAULT '',
  created_at REAL,
  started_at REAL DEFAULT 0,
  completed_at REAL DEFAULT 0,
  UNIQUE(dedup_key));
CREATE TABLE IF NOT EXISTS mission_event_trigger(
  trigger_id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  event_type TEXT NOT NULL,
  mission_template_id TEXT NOT NULL,
  params TEXT DEFAULT '{}',
  payload_map TEXT DEFAULT '{}',
  enabled INTEGER DEFAULT 1,
  cooldown_sec REAL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  description TEXT DEFAULT '',
  created_at REAL,
  updated_at REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS mission_event_receipt(
  receipt_id TEXT PRIMARY KEY,
  trigger_id TEXT DEFAULT '',
  owner TEXT DEFAULT '',
  event_type TEXT DEFAULT '',
  source_event_id TEXT DEFAULT '',
  dedup_key TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'accepted',
  mission_id TEXT DEFAULT '',
  rejection_category TEXT DEFAULT '',
  received_at REAL,
  UNIQUE(dedup_key));
CREATE UNIQUE INDEX IF NOT EXISTS idx_run_idem ON run(idempotency_key)
  WHERE idempotency_key != '';
CREATE INDEX IF NOT EXISTS idx_run_owner ON run(owner, state);
CREATE INDEX IF NOT EXISTS idx_run_state ON run(state);
CREATE INDEX IF NOT EXISTS idx_trans_run ON run_transition(run_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_dedup ON run_alert(state_key)
  WHERE status != 'resolved';
CREATE INDEX IF NOT EXISTS idx_alert_open ON run_alert(status, owner);
CREATE INDEX IF NOT EXISTS idx_alert_run ON run_alert(run_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_delivery_idem ON run_alert_delivery(idem_key);
CREATE INDEX IF NOT EXISTS idx_delivery_status ON run_alert_delivery(status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_delivery_alert ON run_alert_delivery(alert_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_owner ON pipeline_run(owner, state);
CREATE INDEX IF NOT EXISTS idx_pipeline_step ON pipeline_step(pipeline_id, step_index);
CREATE INDEX IF NOT EXISTS idx_mission_owner ON mission(owner, state);
CREATE INDEX IF NOT EXISTS idx_mission_run ON mission_run(mission_id, attempt);
CREATE INDEX IF NOT EXISTS idx_schedule_owner ON mission_schedule(owner, status);
CREATE INDEX IF NOT EXISTS idx_schedule_due ON mission_schedule(status, next_due_at);
CREATE INDEX IF NOT EXISTS idx_occurrence_sched ON mission_occurrence(schedule_id);
CREATE INDEX IF NOT EXISTS idx_occurrence_state ON mission_occurrence(state, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_occurrence_owner ON mission_occurrence(owner, state);
CREATE INDEX IF NOT EXISTS idx_trigger_owner ON mission_event_trigger(owner, event_type);
CREATE INDEX IF NOT EXISTS idx_trigger_event ON mission_event_trigger(event_type, status);
CREATE INDEX IF NOT EXISTS idx_receipt_owner ON mission_event_receipt(owner, received_at);
"""

# M17.12 governed multi-harness pipeline states (sequential, fail-closed)
PIPELINE_PENDING = "pending"
PIPELINE_RUNNING = "running"
PIPELINE_SUCCEEDED = "succeeded"
PIPELINE_FAILED = "failed"
PIPELINE_TERMINAL = {PIPELINE_SUCCEEDED, PIPELINE_FAILED}
# owner-safe pipeline fields (never argv / output / secrets)
_PIPELINE_SAFE_FIELDS = ("pipeline_id", "owner", "name", "state", "step_count",
                         "failed_step", "failure_code", "correlation_id",
                         "created_at", "started_at", "terminal_at")

# M17.13 autonomous mission states — Mission is ABOVE the pipeline; it never
# executes tools, only delegates one governed pipeline. Fail-closed, no partial
# success. Terminal states are immutable (never resurrected).
MISSION_DRAFT = "draft"
MISSION_APPROVAL_REQUIRED = "approval_required"
MISSION_APPROVED = "approved"
MISSION_QUEUED = "queued"
MISSION_RUNNING = "running"
MISSION_COMPLETED = "completed"
MISSION_FAILED = "failed"
MISSION_CANCELLED = "cancelled"
MISSION_BLOCKED = "blocked"
MISSION_ACTIVE = {MISSION_DRAFT, MISSION_APPROVAL_REQUIRED, MISSION_APPROVED,
                  MISSION_QUEUED, MISSION_RUNNING}
MISSION_TERMINAL = {MISSION_COMPLETED, MISSION_FAILED, MISSION_CANCELLED,
                    MISSION_BLOCKED}
MISSION_RUN_TERMINAL = {MISSION_COMPLETED, MISSION_FAILED, MISSION_BLOCKED}
# explicit transition graph — anything not listed is rejected (fail closed)
_MISSION_VALID: dict[str, set[str]] = {
    MISSION_DRAFT: {MISSION_APPROVAL_REQUIRED, MISSION_APPROVED,
                    MISSION_CANCELLED, MISSION_BLOCKED},
    MISSION_APPROVAL_REQUIRED: {MISSION_APPROVED, MISSION_CANCELLED,
                                MISSION_BLOCKED},
    MISSION_APPROVED: {MISSION_QUEUED, MISSION_CANCELLED, MISSION_BLOCKED},
    MISSION_QUEUED: {MISSION_RUNNING, MISSION_CANCELLED, MISSION_BLOCKED},
    MISSION_RUNNING: {MISSION_COMPLETED, MISSION_FAILED, MISSION_CANCELLED,
                      MISSION_BLOCKED},
}
# owner-safe mission fields (never raw argv / output / secrets — params are
# secret-rejected at write time, so the declared inputs are safe to surface)
_MISSION_SAFE_FIELDS = ("mission_id", "owner", "title", "objective",
                        "mission_type", "trigger", "priority", "risk",
                        "approval_required", "template", "params", "schedule",
                        "state", "run_count", "last_pipeline_id", "failure_code",
                        "correlation_id", "created_at", "approved_at",
                        "approved_by", "queued_at", "started_at", "terminal_at")

# M17.14 governed mission scheduler + trusted event triggers. The scheduler sits
# ABOVE the MissionEngine; it NEVER executes tools — it only creates/claims a valid
# occurrence and delegates to the existing MissionEngine. Fail-closed everywhere.
SCHEDULE_ACTIVE = "active"
SCHEDULE_PAUSED = "paused"
SCHEDULE_COMPLETED = "completed"
SCHEDULE_DISABLED = "disabled"
SCHEDULE_INVALID = "invalid"
SCHEDULE_TERMINAL = {SCHEDULE_COMPLETED, SCHEDULE_DISABLED, SCHEDULE_INVALID}
SCHEDULE_GENERATING = {SCHEDULE_ACTIVE}          # only these emit occurrences
_SCHEDULE_VALID: dict[str, set[str]] = {
    SCHEDULE_ACTIVE: {SCHEDULE_PAUSED, SCHEDULE_COMPLETED, SCHEDULE_DISABLED,
                      SCHEDULE_INVALID},
    SCHEDULE_PAUSED: {SCHEDULE_ACTIVE, SCHEDULE_DISABLED, SCHEDULE_INVALID},
}
SCHEDULE_TYPES = {"one_time", "interval", "daily", "weekly"}
_SCHEDULE_SAFE_FIELDS = ("schedule_id", "owner", "mission_template_id",
                         "schedule_type", "timezone", "expression", "params",
                         "enabled", "status", "description", "retry_policy",
                         "version", "next_due_at", "last_due_at",
                         "last_occurrence_id", "created_at", "updated_at")

# occurrence lifecycle — success reflects the LINKED mission result, never "created"
OCC_PENDING = "pending"
OCC_CLAIMED = "claimed"
OCC_RUNNING = "running"
OCC_RETRY_WAIT = "retry_wait"
OCC_SUCCEEDED = "succeeded"
OCC_FAILED = "failed"
OCC_BLOCKED = "blocked"
OCC_APPROVAL_REQUIRED = "approval_required"
OCC_CANCELLED = "cancelled"
OCC_EXPIRED = "expired"
OCC_ACTIVE = {OCC_PENDING, OCC_CLAIMED, OCC_RUNNING, OCC_RETRY_WAIT}
OCC_TERMINAL = {OCC_SUCCEEDED, OCC_FAILED, OCC_BLOCKED, OCC_APPROVAL_REQUIRED,
                OCC_CANCELLED, OCC_EXPIRED}
OCC_DISPATCHABLE = {OCC_PENDING, OCC_RETRY_WAIT}
_OCC_VALID: dict[str, set[str]] = {
    OCC_PENDING: {OCC_CLAIMED, OCC_CANCELLED, OCC_EXPIRED},
    OCC_CLAIMED: {OCC_RUNNING, OCC_RETRY_WAIT, OCC_FAILED, OCC_BLOCKED,
                  OCC_APPROVAL_REQUIRED, OCC_CANCELLED, OCC_PENDING},
    OCC_RUNNING: {OCC_SUCCEEDED, OCC_FAILED, OCC_BLOCKED, OCC_APPROVAL_REQUIRED,
                  OCC_CANCELLED},
    OCC_RETRY_WAIT: {OCC_PENDING, OCC_CLAIMED, OCC_FAILED, OCC_CANCELLED},
}
_OCC_SAFE_FIELDS = ("occurrence_id", "schedule_id", "owner", "due_at", "state",
                    "claim_owner", "lease_expires_at", "attempt_count",
                    "next_attempt_at", "mission_id", "mission_run_id",
                    "failure_category", "failure_summary", "created_at",
                    "started_at", "completed_at")

# trusted internal event allowlist — ONLY these event types may drive a trigger.
# Arbitrary/external event names are rejected (fail closed).
TRUSTED_EVENT_TYPES = {
    "harness.pipeline.failed", "harness.pipeline.succeeded",
    "harness.mission.completed", "harness.mission.failed",
    "harness.notification.terminal_failed", "system.daily_rollover",
    "ceo.review.requested",
}
_TRIGGER_SAFE_FIELDS = ("trigger_id", "owner", "event_type",
                        "mission_template_id", "params", "payload_map",
                        "enabled", "cooldown_sec", "status", "description",
                        "created_at", "updated_at")
_RECEIPT_SAFE_FIELDS = ("receipt_id", "trigger_id", "owner", "event_type",
                        "source_event_id", "state", "mission_id",
                        "rejection_category", "received_at")

# M17.10 stuck-run alert classes + deterministic severity
ALERT_SEVERITY = {"process_missing": "high", "cancellation_stuck": "high",
                  "heartbeat_stale": "medium"}
ALERTABLE = set(ALERT_SEVERITY)

# M17.11 notification-delivery states + bounded deterministic retry schedule
DELIVERY_PENDING = "pending"
DELIVERY_ATTEMPTING = "attempting"
DELIVERY_DELIVERED = "delivered"
DELIVERY_RETRY_WAIT = "retry_wait"
DELIVERY_SUPPRESSED = "suppressed"
DELIVERY_TERMINAL_FAILED = "terminal_failed"
DELIVERY_CANCELLED = "cancelled"
DELIVERY_TERMINAL = {DELIVERY_DELIVERED, DELIVERY_TERMINAL_FAILED, DELIVERY_CANCELLED,
                     DELIVERY_SUPPRESSED}
DELIVERY_DISPATCHABLE = {DELIVERY_PENDING, DELIVERY_RETRY_WAIT}
# seconds before attempt N (index = attempt_count so far); beyond → terminal_failed
RETRY_SCHEDULE = (0.0, 60.0, 300.0, 900.0, 3600.0)
MAX_DELIVERY_ATTEMPTS = len(RETRY_SCHEDULE)


def retry_delay(attempt_count: int) -> float:
    """Deterministic delay before the next attempt (no jitter)."""
    if attempt_count < 0:
        attempt_count = 0
    if attempt_count >= len(RETRY_SCHEDULE):
        return RETRY_SCHEDULE[-1]
    return RETRY_SCHEDULE[attempt_count]

# fields exposed in owner-safe read models (never args / output / secrets)
_SAFE_FIELDS = ("run_id", "owner", "harness_id", "operation_id", "state",
                "state_version", "created_at", "started_at", "heartbeat_at",
                "cancel_requested_at", "terminal_at", "exit_code", "signal",
                "failure_code", "verification_status", "recovery_status",
                "correlation_id", "origin", "timeout")


class RunLedger:
    def __init__(self, db_path=None):
        self.db_path = _validate_db_path(Path(db_path) if db_path else DEFAULT_DB)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    # ── connection / txn ────────────────────────────────────────────────────
    def _conn(self):
        c = sqlite3.connect(str(self.db_path), timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=8000")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    def _event(self, name, payload):
        try:
            from saathi.events import bus
            bus.publish_sync(name, payload)
        except Exception:
            pass

    # ── core transactional transition (CAS on state_version) ────────────────
    def _transition(self, run_id, to_state, *, expected_version=None, actor="",
                    reason="", allow_terminal_noop=True, require_from=None,
                    **fields) -> dict:
        """Move a run to `to_state` under a write lock. Rejects: unknown run,
        terminal resurrection, illegal edge, wrong source state, stale version.
        Exactly one caller can win each transition (BEGIN IMMEDIATE + CAS).
        `require_from` (a set) disables the same-state no-op shortcut and asserts
        the current state — used by claim() so a second claim genuinely fails."""
        if to_state not in ALL_STATES:
            raise LedgerTransitionError("unknown_state", to_state)
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT state, state_version FROM run WHERE run_id=?",
                            (run_id,)).fetchone()
            if row is None:
                c.execute("ROLLBACK")
                raise LedgerError("unknown_run", run_id)
            cur, ver = row["state"], row["state_version"]
            if require_from is not None and cur not in require_from:
                c.execute("ROLLBACK")
                raise LedgerTransitionError("wrong_state", f"{cur} not in {require_from}")
            if cur in TERMINAL:
                c.execute("ROLLBACK")
                if to_state == cur and allow_terminal_noop:
                    return {"ok": True, "noop": True, "state": cur, "version": ver}
                raise LedgerTransitionError("terminal_immutable",
                                            f"{cur}->{to_state}")
            if to_state not in VALID.get(cur, set()):
                c.execute("ROLLBACK")
                if to_state == cur and require_from is None:
                    return {"ok": True, "noop": True, "state": cur, "version": ver}
                raise LedgerTransitionError("invalid_transition",
                                            f"{cur}->{to_state}")
            if expected_version is not None and int(expected_version) != int(ver):
                c.execute("ROLLBACK")
                raise LedgerConcurrencyError("stale_version",
                                             f"{expected_version}!={ver}")
            sets = ["state=?", "state_version=state_version+1"]
            args: list = [to_state]
            for k, v in fields.items():
                sets.append(f"{k}=?"); args.append(v)
            args.extend([run_id, ver])
            n = c.execute(f"UPDATE run SET {','.join(sets)} WHERE run_id=? AND "
                          "state_version=?", args).rowcount
            if n != 1:                       # someone moved it between read & write
                c.execute("ROLLBACK")
                raise LedgerConcurrencyError("cas_lost", run_id)
            c.execute("INSERT INTO run_transition(run_id,from_state,to_state,"
                      "state_version,actor,reason,ts) VALUES(?,?,?,?,?,?,?)",
                      (run_id, cur, to_state, ver + 1, actor[:120], reason[:200], _now()))
            c.execute("COMMIT")
            return {"ok": True, "noop": False, "from": cur, "state": to_state,
                    "version": ver + 1}
        finally:
            c.close()

    # ── creation ────────────────────────────────────────────────────────────
    def create_run(self, run_id, *, owner, harness_id="", operation_id="",
                   installation_id="", intent_digest="", approval_id="",
                   idempotency_key="", correlation_id="", timeout=0.0,
                   device="local", os_user="", session="", metadata=None) -> dict:
        """Insert a run in `queued`. Idempotency-key-unique: a duplicate key
        returns the existing run (no second row, no second side effect)."""
        owner = _clean_str(owner, field="owner")
        if not owner:
            raise LedgerSecurityError("LEDGER_FIELD_REJECTED", "empty owner")
        run_id = _clean_str(run_id, field="run_id", maxlen=128)
        idempotency_key = _clean_str(idempotency_key, field="idempotency_key")
        if metadata is not None:
            _reject_secrets(metadata, where="metadata")
        # sanitize free-text identity fields too (heartbeat/recovery forgery via
        # smuggled control chars, secret smuggling into correlation ids, etc.)
        for f, v in (("harness_id", harness_id), ("operation_id", operation_id),
                     ("correlation_id", correlation_id), ("session", session),
                     ("os_user", os_user), ("device", device),
                     ("approval_id", approval_id), ("intent_digest", intent_digest),
                     ("installation_id", installation_id)):
            _clean_str(v, field=f)
        _reject_secrets({"correlation_id": correlation_id,
                         "approval_id": approval_id}, where="identity")
        now = _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            if idempotency_key:
                ex = c.execute("SELECT run_id FROM run WHERE idempotency_key=?",
                               (idempotency_key,)).fetchone()
                if ex:
                    c.execute("ROLLBACK")
                    return {"run_id": ex["run_id"], "created": False,
                            "reason": "idempotency_duplicate"}
            try:
                c.execute(
                    "INSERT INTO run(run_id,owner,device,os_user,session,harness_id,"
                    "installation_id,operation_id,intent_digest,approval_id,"
                    "idempotency_key,state,state_version,created_at,timeout,"
                    "correlation_id,origin) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,?)",
                    (run_id, owner, device, os_user, session, harness_id,
                     installation_id, operation_id, intent_digest, approval_id,
                     idempotency_key, QUEUED, now, float(timeout), correlation_id,
                     "ledger"))
            except sqlite3.IntegrityError as e:
                c.execute("ROLLBACK")
                if idempotency_key and "idempotency" in str(e):
                    ex = self.inspect(run_id) or {}
                    return {"run_id": run_id, "created": False,
                            "reason": "idempotency_duplicate"}
                raise LedgerError("duplicate_run_id", run_id)
            c.execute("INSERT INTO run_transition(run_id,from_state,to_state,"
                      "state_version,actor,reason,ts) VALUES(?,?,?,?,?,?,?)",
                      (run_id, None, QUEUED, 0, owner, "create", now))
            c.execute("COMMIT")
        finally:
            c.close()
        self._event("harness.run.created", {"run_id": run_id, "owner": owner,
                                            "harness_id": harness_id})
        return {"run_id": run_id, "created": True}

    # ── lifecycle ───────────────────────────────────────────────────────────
    def claim(self, run_id, *, pid=None, pgid=None, os_user=None, device=None,
              session=None) -> bool:
        """Atomically move queued→starting. Exactly one process wins; every
        other caller gets False (already claimed / not queued)."""
        fields = {"started_at": _now()}
        if pid is not None:
            fields["pid"] = int(pid)
        if pgid is not None:
            fields["pgid"] = int(pgid)
        if os_user is not None:
            fields["os_user"] = _clean_str(os_user, field="os_user")
        if device is not None:
            fields["device"] = _clean_str(device, field="device")
        if session is not None:
            fields["session"] = _clean_str(session, field="session")
        try:
            self._transition(run_id, STARTING, actor="claim", reason="claim",
                             require_from={QUEUED}, **fields)
            return True
        except (LedgerTransitionError, LedgerConcurrencyError):
            return False

    def mark_running(self, run_id, *, pid=None, pgid=None) -> dict:
        fields = {"heartbeat_at": _now()}
        if pid is not None:
            fields["pid"] = int(pid)
        if pgid is not None:
            fields["pgid"] = int(pgid)
        return self._transition(run_id, RUNNING, actor="run", reason="running",
                                **fields)

    def request_cancellation(self, run_id, *, requester) -> dict:
        """Ownership-gated. A run may only be cancelled by its owner. Duplicate
        requests are safe (idempotent no-op)."""
        run = self.inspect(run_id)
        if run is None:
            return {"cancelled": False, "reason": "unknown_run"}
        if run["owner"] != requester:
            self._event("harness.run.cancel_denied",
                        {"run_id": run_id, "requester": requester})
            return {"cancelled": False,
                    "reason": "HARNESS_PERMISSION_BLOCKED:ownership"}
        if run["state"] in TERMINAL:
            return {"cancelled": False, "reason": "already_terminal",
                    "state": run["state"]}
        if run["state"] == CANCEL_REQ:
            return {"cancelled": True, "reason": "already_requested",
                    "run_id": run_id}
        try:
            self._transition(run_id, CANCEL_REQ, actor=requester,
                             reason="cancel_requested",
                             cancel_requested_at=_now())
            self._event("harness.run.cancel_requested",
                        {"run_id": run_id, "requester": requester})
            return {"cancelled": True, "run_id": run_id}
        except LedgerTransitionError:
            # raced to terminal between read and write — completion won
            return {"cancelled": False, "reason": "raced_terminal",
                    "state": (self.inspect(run_id) or {}).get("state")}

    def admin_cancel(self, run_id, *, operator) -> dict:
        """Administrative (maintenance) cancellation — NOT owner-gated. The
        `operator` identity MUST come from a trusted context (verified local OS
        identity / authenticated operator), NEVER from untrusted request data.
        Respects terminal-state protection + the state machine, and is
        audit-logged with the operator id. Used only by admin-maintenance
        surfaces; the ownership-gated path for end users is
        request_cancellation()."""
        operator = _clean_str(operator, field="operator")
        if not operator:
            raise LedgerSecurityError("LEDGER_FIELD_REJECTED", "empty operator")
        run = self.inspect(run_id)
        if run is None:
            return {"cancelled": False, "reason": "unknown_run"}
        if run["state"] in TERMINAL:
            return {"cancelled": False, "reason": "already_terminal",
                    "state": run["state"]}
        if run["state"] == CANCEL_REQ:
            return {"cancelled": True, "reason": "already_requested", "run_id": run_id}
        try:
            self._transition(run_id, CANCEL_REQ, actor=f"admin:{operator}",
                             reason="admin_cancel", cancel_requested_at=_now())
            self._event("harness.run.admin_cancel",
                        {"run_id": run_id, "operator": operator})
            return {"cancelled": True, "run_id": run_id, "operator": operator}
        except LedgerTransitionError:
            return {"cancelled": False, "reason": "raced_terminal",
                    "state": (self.inspect(run_id) or {}).get("state")}

    def complete(self, run_id, *, state, exit_code=None, signal=None,
                 failure_code="", verification_status=None,
                 artifact_refs=None) -> dict:
        if state not in TERMINAL:
            raise LedgerTransitionError("not_terminal", state)
        fields: dict = {"terminal_at": _now(), "exit_code": exit_code,
                        "signal": signal, "failure_code": failure_code[:120]}
        if verification_status is not None:
            fields["verification_status"] = _clean_str(verification_status,
                                                       field="verification_status")
        if artifact_refs is not None:
            _reject_secrets(artifact_refs, where="artifact_refs")
            fields["artifact_refs"] = json.dumps(artifact_refs)[:4000]
        res = self._transition(run_id, state, actor="complete", reason=state,
                               **fields)
        if not res.get("noop"):
            self.resolve_alerts(run_id)       # terminal → clear open alerts
            self._event("harness.run.completed", {"run_id": run_id, "state": state})
        return res

    def record_heartbeat(self, run_id) -> bool:
        """Bounded heartbeat for an active run. No-op (returns False) for a
        terminal run — a dead run cannot forge a fresh heartbeat."""
        c = self._conn()
        try:
            n = c.execute("UPDATE run SET heartbeat_at=? WHERE run_id=? AND "
                          f"state IN ({','.join('?'*len(ACTIVE))})",
                          (_now(), run_id, *sorted(ACTIVE))).rowcount
            return n == 1
        finally:
            c.close()

    # ── reads ───────────────────────────────────────────────────────────────
    def inspect(self, run_id) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM run WHERE run_id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_active(self, owner: str | None = None) -> list[dict]:
        q = f"SELECT * FROM run WHERE state IN ({','.join('?'*len(ACTIVE))})"
        args = list(sorted(ACTIVE))
        if owner:
            q += " AND owner=?"; args.append(owner)
        q += " ORDER BY created_at"
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    def latest_state(self, run_id) -> str | None:
        r = self.inspect(run_id)
        return r["state"] if r else None

    def transitions(self, run_id, *, limit: int = _TRANSITION_HISTORY_CAP) -> list[dict]:
        limit = max(1, min(int(limit), _TRANSITION_HISTORY_CAP))
        with self._conn() as c:
            rows = c.execute("SELECT from_state,to_state,state_version,actor,reason,ts "
                             "FROM run_transition WHERE run_id=? ORDER BY id LIMIT ?",
                             (run_id, limit)).fetchall()
        return [dict(r) for r in rows]

    # ── heartbeat / stuck-run classification ────────────────────────────────
    def classify(self, run: dict, *, now: float | None = None, stale_sec: float = 30.0,
                 cancel_stuck_sec: float = 60.0, is_alive=None) -> str:
        """active | heartbeat_stale | process_missing | cancellation_stuck |
        terminal. A single missed heartbeat never means 'failed'."""
        now = now if now is not None else _now()
        alive = is_alive or _pid_alive
        st = run["state"]
        if st in TERMINAL:
            return "terminal"
        pid = run.get("pid")
        if st in (RUNNING, CANCEL_REQ) and pid is not None and not alive(pid):
            return "process_missing"
        if st == CANCEL_REQ:
            req = run.get("cancel_requested_at") or 0
            if req and (now - req) > cancel_stuck_sec:
                return "cancellation_stuck"
            return "active"
        hb = run.get("heartbeat_at") or run.get("started_at") or 0
        if st == RUNNING and hb and (now - hb) > stale_sec:
            return "heartbeat_stale"
        return "active"

    # ── recovery operations ─────────────────────────────────────────────────
    def reconcile_run(self, run_id, *, is_alive=None) -> dict:
        """Reconcile ONE run: if it is active but its process is gone, record it
        as crash_recovered exactly once. A live process is never overwritten.
        Idempotent — a second call on a terminal run is a no-op."""
        alive = is_alive or _pid_alive
        run = self.inspect(run_id)
        if run is None:
            return {"reconciled": False, "reason": "unknown_run"}
        if run["state"] in TERMINAL:
            return {"reconciled": False, "reason": "already_terminal",
                    "state": run["state"]}
        pid = run.get("pid")
        if pid is not None and alive(pid):
            return {"reconciled": False, "reason": "process_alive", "pid": pid}
        try:
            self._transition(run_id, CRASH_RECOVERED, actor="reconcile",
                             reason="pid_dead", terminal_at=_now(),
                             recovery_status="crash_reconciled")
            self.resolve_alerts(run_id)       # terminal → clear open alerts
            self._event("harness.run.crash_recovered", {"run_id": run_id})
            return {"reconciled": True, "run_id": run_id, "state": CRASH_RECOVERED}
        except (LedgerTransitionError, LedgerConcurrencyError) as e:
            return {"reconciled": False, "reason": e.code}

    def reconcile_stale(self, *, is_alive=None, now=None, stale_sec: float = 30.0,
                        cancel_stuck_sec: float = 60.0) -> dict:
        """Sweep active runs. Reconcile process_missing runs to crash_recovered;
        surface heartbeat_stale / cancellation_stuck as attention items WITHOUT
        repeating any side effect."""
        alive = is_alive or _pid_alive
        now = now if now is not None else _now()
        recovered, attention = [], []
        for run in self.list_active():
            klass = self.classify(run, now=now, stale_sec=stale_sec,
                                   cancel_stuck_sec=cancel_stuck_sec, is_alive=alive)
            if klass == "process_missing":
                r = self.reconcile_run(run["run_id"], is_alive=alive)
                if r.get("reconciled"):
                    recovered.append(run["run_id"])
            elif klass in ("heartbeat_stale", "cancellation_stuck"):
                attention.append({"run_id": run["run_id"], "owner": run["owner"],
                                  "class": klass, "state": run["state"]})
        if recovered or attention:
            self._event("harness.runs.reconciled",
                        {"recovered": recovered, "attention": len(attention)})
        return {"recovered": recovered, "attention": attention}

    def mark_recovery(self, run_id, *, evidence: str, status: str = "recovered") -> dict:
        """Attach recovery evidence to a run (does NOT rerun work). Records the
        operator's recovery finding for audit."""
        _reject_secrets({"evidence": evidence}, where="recovery_evidence")
        evidence = _clean_str(evidence, field="evidence", maxlen=400)
        status = _clean_str(status, field="recovery_status")
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT run_id FROM run WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                c.execute("ROLLBACK")
                return {"ok": False, "reason": "unknown_run"}
            c.execute("UPDATE run SET recovery_status=? WHERE run_id=?", (status, run_id))
            c.execute("INSERT INTO run_transition(run_id,from_state,to_state,"
                      "state_version,actor,reason,ts) VALUES(?,?,?,?,?,?,?)",
                      (run_id, None, "recovery_note", None, "operator",
                       f"{status}:{evidence}", _now()))
            c.execute("COMMIT")
        finally:
            c.close()
        return {"ok": True, "run_id": run_id, "recovery_status": status}

    # ── M17.10 stuck-run alerts (deduplicated, self-resolving) ──────────────
    def raise_alert(self, run_id, *, alert_class, severity=None, owner="",
                    detail="") -> dict:
        """Raise a stuck-run alert. Deduplicated: at most ONE non-resolved alert
        per (run_id, alert_class) — a repeat raise is an idempotent no-op, so a
        monitor sweep can run every tick without alert storms or replay dupes."""
        if alert_class not in ALERTABLE:
            raise LedgerError("unknown_alert_class", alert_class)
        severity = severity or ALERT_SEVERITY[alert_class]
        detail = _clean_str(detail, field="alert_detail", maxlen=300)
        owner = _clean_str(owner, field="owner")
        state_key = f"{run_id}:{alert_class}"
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            n = c.execute(
                "INSERT OR IGNORE INTO run_alert(run_id,alert_class,severity,"
                "state_key,status,owner,detail,created_at) "
                "VALUES(?,?,?,?,'open',?,?,?)",
                (run_id, alert_class, severity, state_key, owner, detail, _now())
            ).rowcount
            c.execute("COMMIT")
        finally:
            c.close()
        if n == 1:
            self._event("harness.run.alert", {"run_id": run_id,
                        "alert_class": alert_class, "severity": severity})
        return {"raised": n == 1, "run_id": run_id, "alert_class": alert_class}

    def resolve_alerts(self, run_id, *, alert_class=None) -> int:
        """Resolve open/acknowledged alerts for a run (optionally one class).
        Called on every terminal transition + crash reconcile + self-heal, so
        alerts always reflect current truth."""
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            sel = "SELECT id FROM run_alert WHERE run_id=? AND status!='resolved'"
            sargs = [run_id]
            if alert_class is not None:
                sel += " AND alert_class=?"; sargs.append(alert_class)
            ids = [r["id"] for r in c.execute(sel, sargs).fetchall()]
            q = ("UPDATE run_alert SET status='resolved', resolved_at=? "
                 "WHERE run_id=? AND status!='resolved'")
            args = [_now(), run_id]
            if alert_class is not None:
                q += " AND alert_class=?"; args.append(alert_class)
            n = c.execute(q, args).rowcount
            c.execute("COMMIT")
        finally:
            c.close()
        # a resolved alert must not deliver a stale unresolved-alert notification
        for aid in ids:
            self.suppress_deliveries_for_alert(aid, reason="alert_resolved")
        return n

    def open_alerts(self, owner: str | None = None, *, limit: int = 200) -> list[dict]:
        """Owner-safe list of non-resolved alerts (no argv/output/secrets)."""
        limit = max(1, min(int(limit), 1000))
        q = ("SELECT id,run_id,owner,alert_class,severity,status,detail,created_at,"
             "acknowledged_at,acknowledged_by FROM run_alert WHERE status!='resolved'")
        args: list = []
        if owner:
            q += " AND owner=?"; args.append(owner)
        q += " ORDER BY created_at DESC LIMIT ?"; args.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    def alert_by_id(self, alert_id) -> Optional[dict]:
        """Owner-safe single alert (no argv/output/secrets)."""
        with self._conn() as c:
            row = c.execute(
                "SELECT id,run_id,owner,alert_class,severity,status,detail,created_at,"
                "acknowledged_at,acknowledged_by,resolved_at FROM run_alert WHERE id=?",
                (alert_id,)).fetchone()
        return dict(row) if row else None

    def acknowledge_alert(self, alert_id, *, operator) -> dict:
        """Admin-audited acknowledge. `operator` MUST come from a trusted context
        (verified OS identity), never untrusted request data. Fails closed for an
        unknown or already-resolved alert."""
        operator = _clean_str(operator, field="operator")
        if not operator:
            raise LedgerSecurityError("LEDGER_FIELD_REJECTED", "empty operator")
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT status, run_id FROM run_alert WHERE id=?",
                            (alert_id,)).fetchone()
            if row is None:
                c.execute("ROLLBACK")
                return {"ok": False, "reason": "unknown_alert"}
            if row["status"] != "open":
                c.execute("ROLLBACK")
                return {"ok": False, "reason": f"not_open:{row['status']}"}
            c.execute("UPDATE run_alert SET status='acknowledged', "
                      "acknowledged_at=?, acknowledged_by=? WHERE id=? AND status='open'",
                      (_now(), f"admin:{operator}", alert_id))
            c.execute("COMMIT")
        finally:
            c.close()
        # acknowledged: suppress any pending UNSENT delivery (delivered ones stay
        # historically delivered; escalation is not enabled in this milestone).
        self.suppress_deliveries_for_alert(alert_id, reason="alert_acknowledged")
        self._event("harness.run.alert_ack", {"alert_id": alert_id, "operator": operator})
        return {"ok": True, "alert_id": alert_id, "operator": operator}

    # ── M17.11 notification deliveries (durable, deduplicated, retryable) ────
    def create_delivery(self, alert_id, *, channel, payload_fingerprint,
                        owner="", destination_key="",
                        max_attempts: int = MAX_DELIVERY_ATTEMPTS, now=None) -> dict:
        """Create a delivery for an alert. Deduplicated by
        idem_key=alert:channel:dest:fingerprint — a repeat is an idempotent no-op
        (one active delivery per alert+channel+destination+payload version)."""
        channel = _clean_str(channel, field="channel", maxlen=64)
        payload_fingerprint = _clean_str(payload_fingerprint, field="fingerprint", maxlen=128)
        destination_key = _clean_str(destination_key, field="destination_key", maxlen=256)
        owner = _clean_str(owner, field="owner")
        if not channel or not payload_fingerprint:
            raise LedgerError("delivery_field_missing")
        now = now if now is not None else _now()
        idem = f"{alert_id}:{channel}:{destination_key}:{payload_fingerprint}"
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            if c.execute("SELECT 1 FROM run_alert WHERE id=?", (alert_id,)).fetchone() is None:
                c.execute("ROLLBACK")
                return {"created": False, "reason": "unknown_alert"}
            n = c.execute(
                "INSERT OR IGNORE INTO run_alert_delivery(alert_id,owner,channel,"
                "destination_key,payload_fingerprint,idem_key,status,attempt_count,"
                "max_attempts,next_attempt_at,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,0,?,?,?,?)",
                (alert_id, owner, channel, destination_key, payload_fingerprint, idem,
                 DELIVERY_PENDING, int(max_attempts), now, now, now)).rowcount
            did = None
            if n == 1:
                did = c.execute("SELECT id FROM run_alert_delivery WHERE idem_key=?",
                                (idem,)).fetchone()["id"]
            c.execute("COMMIT")
        finally:
            c.close()
        if n == 1:
            self._event("harness.notification.queued",
                        {"delivery_id": did, "alert_id": alert_id, "channel": channel})
        return {"created": n == 1, "delivery_id": did, "idem_key": idem}

    def claim_delivery(self, delivery_id, *, worker, now=None, lease_sec: float = 120.0) -> bool:
        """Lease-claim a dispatchable (or stale-attempting) delivery. CAS on the
        observed status — exactly one worker wins; a not-yet-due retry is skipped."""
        worker = _clean_str(worker, field="worker", maxlen=120)
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT status,next_attempt_at,claim_at FROM "
                            "run_alert_delivery WHERE id=?", (delivery_id,)).fetchone()
            if row is None:
                c.execute("ROLLBACK"); return False
            st = row["status"]
            claimable = st in DELIVERY_DISPATCHABLE or (
                st == DELIVERY_ATTEMPTING and (row["claim_at"] or 0) < now - lease_sec)
            if not claimable or (row["next_attempt_at"] or 0) > now:
                c.execute("ROLLBACK"); return False
            n = c.execute("UPDATE run_alert_delivery SET status=?, claim_owner=?, "
                          "claim_at=?, updated_at=? WHERE id=? AND status=?",
                          (DELIVERY_ATTEMPTING, worker, now, now, delivery_id, st)).rowcount
            if n != 1:
                c.execute("ROLLBACK"); return False
            c.execute("COMMIT")
            return True
        finally:
            c.close()

    def mark_delivered(self, delivery_id, *, now=None) -> dict:
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            n = c.execute(
                "UPDATE run_alert_delivery SET status=?, delivered_at=?, "
                "attempt_count=attempt_count+1, last_attempt_at=?, "
                "first_attempt_at=CASE WHEN first_attempt_at=0 THEN ? ELSE first_attempt_at END, "
                "claim_owner='', updated_at=? WHERE id=? AND status=?",
                (DELIVERY_DELIVERED, now, now, now, now, delivery_id, DELIVERY_ATTEMPTING)).rowcount
            c.execute("COMMIT")
        finally:
            c.close()
        if n == 1:
            self._event("harness.notification.delivered", {"delivery_id": delivery_id})
        return {"ok": n == 1, "delivery_id": delivery_id}

    def mark_attempt_failed(self, delivery_id, *, error_code="", error_summary="",
                            now=None) -> dict:
        """attempting → retry_wait (deterministic next_attempt_at) or → terminal_failed
        when max attempts are exhausted."""
        now = now if now is not None else _now()
        error_code = _clean_str(error_code, field="error_code", maxlen=80)
        error_summary = _clean_str(error_summary, field="error_summary", maxlen=300)
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT attempt_count,max_attempts FROM run_alert_delivery "
                            "WHERE id=? AND status=?",
                            (delivery_id, DELIVERY_ATTEMPTING)).fetchone()
            if row is None:
                c.execute("ROLLBACK")
                return {"ok": False, "reason": "not_attempting"}
            new_count = (row["attempt_count"] or 0) + 1
            if new_count >= (row["max_attempts"] or MAX_DELIVERY_ATTEMPTS):
                status, nxt, term = DELIVERY_TERMINAL_FAILED, 0, now
            else:
                status, nxt, term = DELIVERY_RETRY_WAIT, now + retry_delay(new_count), 0
            c.execute("UPDATE run_alert_delivery SET status=?, attempt_count=?, "
                      "next_attempt_at=?, last_attempt_at=?, terminal_failed_at=?, "
                      "last_error_code=?, last_error_summary=?, "
                      "first_attempt_at=CASE WHEN first_attempt_at=0 THEN ? ELSE first_attempt_at END, "
                      "claim_owner='', updated_at=? WHERE id=? AND status=?",
                      (status, new_count, nxt, now, term, error_code, error_summary,
                       now, now, delivery_id, DELIVERY_ATTEMPTING))
            c.execute("COMMIT")
        finally:
            c.close()
        if status == DELIVERY_TERMINAL_FAILED:
            self._event("harness.notification.terminal_failed",
                        {"delivery_id": delivery_id, "error_code": error_code})
        else:
            self._event("harness.notification.retry_scheduled",
                        {"delivery_id": delivery_id, "attempt": new_count})
        return {"ok": True, "status": status, "attempt_count": new_count}

    def suppress_deliveries_for_alert(self, alert_id, *, reason="alert_closed", now=None) -> int:
        """Suppress (not deliver) any pending/retry_wait deliveries for an alert —
        used when its alert is resolved or acknowledged."""
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            n = c.execute(
                f"UPDATE run_alert_delivery SET status=?, last_error_code=?, "
                f"updated_at=? WHERE alert_id=? AND status IN "
                f"({','.join('?'*len(DELIVERY_DISPATCHABLE))})",
                (DELIVERY_SUPPRESSED, _clean_str(reason, field="reason", maxlen=80), now,
                 alert_id, *sorted(DELIVERY_DISPATCHABLE))).rowcount
            c.execute("COMMIT")
        finally:
            c.close()
        if n:
            self._event("harness.notification.suppressed",
                        {"alert_id": alert_id, "count": n, "reason": reason})
        return n

    def reclaim_stale_deliveries(self, *, now=None, lease_sec: float = 120.0) -> list[int]:
        """Return attempting deliveries whose lease expired (crash-after-claim) to
        retry_wait so they can be re-dispatched (transport idempotency dedups)."""
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            ids = [r["id"] for r in c.execute(
                "SELECT id FROM run_alert_delivery WHERE status=? AND claim_at>0 "
                "AND claim_at<?", (DELIVERY_ATTEMPTING, now - lease_sec)).fetchall()]
            for did in ids:
                c.execute("UPDATE run_alert_delivery SET status=?, next_attempt_at=?, "
                          "claim_owner='', updated_at=? WHERE id=? AND status=?",
                          (DELIVERY_RETRY_WAIT, now, now, did, DELIVERY_ATTEMPTING))
            c.execute("COMMIT")
        finally:
            c.close()
        return ids

    def admin_retry_delivery(self, delivery_id, *, operator, now=None) -> dict:
        """Admin-audited retry of a terminal_failed delivery. `operator` MUST come
        from a trusted context (verified OS identity). Fails closed otherwise."""
        operator = _clean_str(operator, field="operator")
        if not operator:
            raise LedgerSecurityError("LEDGER_FIELD_REJECTED", "empty operator")
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            n = c.execute("UPDATE run_alert_delivery SET status=?, next_attempt_at=?, "
                          "last_error_code='admin_retry', updated_at=? WHERE id=? AND status=?",
                          (DELIVERY_RETRY_WAIT, now, now, delivery_id,
                           DELIVERY_TERMINAL_FAILED)).rowcount
            c.execute("COMMIT")
        finally:
            c.close()
        if n != 1:
            return {"ok": False, "reason": "not_terminal_failed"}
        self._event("harness.notification.admin_retry",
                    {"delivery_id": delivery_id, "operator": operator})
        return {"ok": True, "delivery_id": delivery_id, "operator": operator}

    def delivery(self, delivery_id) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM run_alert_delivery WHERE id=?",
                            (delivery_id,)).fetchone()
        return dict(row) if row else None

    def deliveries_for_alert(self, alert_id) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM run_alert_delivery WHERE alert_id=? ORDER BY id",
                (alert_id,)).fetchall()]

    def pending_dispatchable(self, *, now=None, limit: int = 100) -> list[dict]:
        now = now if now is not None else _now()
        limit = max(1, min(int(limit), 1000))
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                f"SELECT * FROM run_alert_delivery WHERE status IN "
                f"({','.join('?'*len(DELIVERY_DISPATCHABLE))}) AND next_attempt_at<=? "
                "ORDER BY next_attempt_at LIMIT ?",
                (*sorted(DELIVERY_DISPATCHABLE), now, limit)).fetchall()]

    def open_deliveries(self, owner: str | None = None, *, limit: int = 200) -> list[dict]:
        """Deliveries still needing attention — hides delivered/suppressed/cancelled
        but KEEPS terminal_failed (operator-actionable via admin retry)."""
        limit = max(1, min(int(limit), 1000))
        hidden = (DELIVERY_DELIVERED, DELIVERY_SUPPRESSED, DELIVERY_CANCELLED)
        q = ("SELECT id,alert_id,owner,channel,status,attempt_count,max_attempts,"
             "next_attempt_at,last_error_code,created_at,delivered_at,terminal_failed_at "
             "FROM run_alert_delivery WHERE status NOT IN "
             f"({','.join('?'*len(hidden))})")
        args: list = list(hidden)
        if owner:
            q += " AND owner=?"; args.append(owner)
        q += " ORDER BY created_at DESC LIMIT ?"; args.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    def delivery_health(self, *, now=None) -> dict:
        now = now if now is not None else _now()
        with self._conn() as c:
            by_status = {r["status"]: r["n"] for r in c.execute(
                "SELECT status, COUNT(*) n FROM run_alert_delivery GROUP BY status").fetchall()}
            oldest = c.execute(
                f"SELECT MIN(created_at) m FROM run_alert_delivery WHERE status IN "
                f"({','.join('?'*len(DELIVERY_DISPATCHABLE))})",
                tuple(sorted(DELIVERY_DISPATCHABLE))).fetchone()["m"]
        return {"by_status": by_status,
                "pending": by_status.get(DELIVERY_PENDING, 0),
                "retry_wait": by_status.get(DELIVERY_RETRY_WAIT, 0),
                "delivered": by_status.get(DELIVERY_DELIVERED, 0),
                "terminal_failed": by_status.get(DELIVERY_TERMINAL_FAILED, 0),
                "oldest_pending_age_sec": round(now - oldest, 2) if oldest else None}

    # ── M17.12 governed multi-harness pipeline (sequential, fail-closed) ─────
    def create_pipeline(self, pipeline_id, *, owner, name="", step_count=0,
                        correlation_id="", now=None) -> dict:
        """Insert a pipeline in `pending`. pipeline_id is PRIMARY-KEY-unique — a
        duplicate is rejected (no second run). Owner is mandatory + sanitized."""
        owner = _clean_str(owner, field="owner")
        if not owner:
            raise LedgerSecurityError("LEDGER_FIELD_REJECTED", "empty owner")
        pipeline_id = _clean_str(pipeline_id, field="pipeline_id", maxlen=128)
        name = _clean_str(name, field="name", maxlen=200)
        correlation_id = _clean_str(correlation_id, field="correlation_id")
        _reject_secrets({"name": name, "correlation_id": correlation_id},
                        where="pipeline_identity")
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            try:
                c.execute("INSERT INTO pipeline_run(pipeline_id,owner,name,state,"
                          "step_count,correlation_id,created_at) VALUES(?,?,?,?,?,?,?)",
                          (pipeline_id, owner, name, PIPELINE_PENDING,
                           int(step_count), correlation_id, now))
            except sqlite3.IntegrityError:
                c.execute("ROLLBACK")
                return {"created": False, "reason": "duplicate_pipeline_id",
                        "pipeline_id": pipeline_id}
            c.execute("COMMIT")
        finally:
            c.close()
        self._event("harness.pipeline.created",
                    {"pipeline_id": pipeline_id, "owner": owner, "steps": int(step_count)})
        return {"created": True, "pipeline_id": pipeline_id}

    def start_pipeline(self, pipeline_id, *, now=None) -> dict:
        """pending → running. Idempotent no-op if already running; fails closed on
        an unknown or already-terminal pipeline (never resurrect)."""
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT state FROM pipeline_run WHERE pipeline_id=?",
                            (pipeline_id,)).fetchone()
            if row is None:
                c.execute("ROLLBACK"); return {"ok": False, "reason": "unknown_pipeline"}
            if row["state"] in PIPELINE_TERMINAL:
                c.execute("ROLLBACK")
                return {"ok": False, "reason": f"terminal:{row['state']}"}
            if row["state"] == PIPELINE_RUNNING:
                c.execute("ROLLBACK"); return {"ok": True, "noop": True}
            c.execute("UPDATE pipeline_run SET state=?, started_at=? WHERE "
                      "pipeline_id=? AND state=?",
                      (PIPELINE_RUNNING, now, pipeline_id, PIPELINE_PENDING))
            c.execute("COMMIT")
        finally:
            c.close()
        self._event("harness.pipeline.started", {"pipeline_id": pipeline_id})
        return {"ok": True}

    def record_pipeline_step(self, pipeline_id, *, step_index, step_name="",
                             harness_id="", operation_id="", run_id="",
                             status="", error_code="", artifact="", now=None) -> dict:
        """Record (upsert) one step's outcome. Free-text fields are sanitized;
        no argv/output is ever stored — `artifact` is a workspace-relative name."""
        now = now if now is not None else _now()
        step_name = _clean_str(step_name, field="step_name", maxlen=120)
        harness_id = _clean_str(harness_id, field="harness_id", maxlen=120)
        operation_id = _clean_str(operation_id, field="operation_id", maxlen=120)
        run_id = _clean_str(run_id, field="run_id", maxlen=128)
        status = _clean_str(status, field="status", maxlen=40)
        error_code = _clean_str(error_code, field="error_code", maxlen=120)
        artifact = _clean_str(artifact, field="artifact", maxlen=256)
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            c.execute(
                "INSERT INTO pipeline_step(pipeline_id,step_index,step_name,"
                "harness_id,operation_id,run_id,status,error_code,artifact,recorded_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(pipeline_id,step_index) DO UPDATE SET "
                "step_name=excluded.step_name,harness_id=excluded.harness_id,"
                "operation_id=excluded.operation_id,run_id=excluded.run_id,"
                "status=excluded.status,error_code=excluded.error_code,"
                "artifact=excluded.artifact,recorded_at=excluded.recorded_at",
                (pipeline_id, int(step_index), step_name, harness_id, operation_id,
                 run_id, status, error_code, artifact, now))
            c.execute("COMMIT")
        finally:
            c.close()
        self._event("harness.pipeline.step_recorded",
                    {"pipeline_id": pipeline_id, "step_index": int(step_index),
                     "status": status})
        return {"ok": True}

    def complete_pipeline(self, pipeline_id, *, state, failed_step=-1,
                          failure_code="", now=None) -> dict:
        """running → succeeded | failed. Terminal is immutable (never resurrect)."""
        if state not in PIPELINE_TERMINAL:
            raise LedgerError("bad_pipeline_state", state)
        failure_code = _clean_str(failure_code, field="failure_code", maxlen=120)
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT state FROM pipeline_run WHERE pipeline_id=?",
                            (pipeline_id,)).fetchone()
            if row is None:
                c.execute("ROLLBACK"); return {"ok": False, "reason": "unknown_pipeline"}
            if row["state"] in PIPELINE_TERMINAL:
                c.execute("ROLLBACK")
                return {"ok": False, "reason": f"already_terminal:{row['state']}"}
            c.execute("UPDATE pipeline_run SET state=?, failed_step=?, failure_code=?, "
                      "terminal_at=? WHERE pipeline_id=? AND state NOT IN (?,?)",
                      (state, int(failed_step), failure_code, now, pipeline_id,
                       PIPELINE_SUCCEEDED, PIPELINE_FAILED))
            c.execute("COMMIT")
        finally:
            c.close()
        self._event(f"harness.pipeline.{state}",
                    {"pipeline_id": pipeline_id, "failed_step": int(failed_step),
                     "failure_code": failure_code})
        return {"ok": True, "state": state}

    def inspect_pipeline(self, pipeline_id, *, owner: str | None = None) -> Optional[dict]:
        """Owner-safe pipeline record + its steps. If `owner` is given and does not
        match, returns None (no cross-owner disclosure)."""
        with self._conn() as c:
            row = c.execute("SELECT * FROM pipeline_run WHERE pipeline_id=?",
                            (pipeline_id,)).fetchone()
            if row is None:
                return None
            if owner is not None and row["owner"] != owner:
                return None
            steps = [dict(r) for r in c.execute(
                "SELECT step_index,step_name,harness_id,operation_id,run_id,status,"
                "error_code,artifact,recorded_at FROM pipeline_step WHERE pipeline_id=? "
                "ORDER BY step_index", (pipeline_id,)).fetchall()]
        out = {k: row[k] for k in _PIPELINE_SAFE_FIELDS}
        out["steps"] = steps
        return out

    def list_pipelines(self, owner: str | None = None, *, limit: int = 100) -> list[dict]:
        """Owner-safe recent pipelines (no argv/output)."""
        limit = max(1, min(int(limit), 1000))
        q = f"SELECT {','.join(_PIPELINE_SAFE_FIELDS)} FROM pipeline_run"
        args: list = []
        if owner:
            q += " WHERE owner=?"; args.append(owner)
        q += " ORDER BY created_at DESC LIMIT ?"; args.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    def pipeline_health(self, owner: str | None = None) -> dict:
        """Pipeline state census (owner-scoped when owner given)."""
        where, args = "", []
        if owner:
            where, args = " WHERE owner=?", [owner]
        with self._conn() as c:
            by_state = {r["state"]: r["n"] for r in c.execute(
                f"SELECT state, COUNT(*) n FROM pipeline_run{where} GROUP BY state",
                args).fetchall()}
        return {"by_state": by_state,
                "running": by_state.get(PIPELINE_RUNNING, 0),
                "succeeded": by_state.get(PIPELINE_SUCCEEDED, 0),
                "failed": by_state.get(PIPELINE_FAILED, 0),
                "total": sum(by_state.values())}

    # ── M17.13 autonomous mission records (ABOVE the pipeline) ──────────────
    def create_mission(self, mission_id, *, owner, title="", objective="",
                       mission_type="manual", trigger="manual", priority="normal",
                       risk=0, approval_required=False, template="", params=None,
                       schedule="", correlation_id="", now=None) -> dict:
        """Insert a mission in `draft`. mission_id is PRIMARY-KEY-unique — a
        duplicate is rejected (no second mission). Owner is mandatory + sanitized;
        params are secret-rejected and stored as owner-safe JSON (never argv)."""
        owner = _clean_str(owner, field="owner")
        if not owner:
            raise LedgerSecurityError("LEDGER_FIELD_REJECTED", "empty owner")
        mission_id = _clean_str(mission_id, field="mission_id", maxlen=128)
        title = _clean_str(title, field="title", maxlen=200)
        objective = _clean_str(objective, field="objective", maxlen=500)
        mission_type = _clean_str(mission_type, field="mission_type", maxlen=40)
        trigger = _clean_str(trigger, field="trigger", maxlen=60)
        priority = _clean_str(priority, field="priority", maxlen=20)
        template = _clean_str(template, field="template", maxlen=120)
        schedule = _clean_str(schedule, field="schedule", maxlen=200)
        correlation_id = _clean_str(correlation_id, field="correlation_id")
        params = params or {}
        _reject_secrets({"title": title, "objective": objective,
                         "schedule": schedule, "params": params},
                        where="mission_identity")
        params_json = json.dumps(params, sort_keys=True, default=str)[:4000]
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            try:
                c.execute(
                    "INSERT INTO mission(mission_id,owner,title,objective,"
                    "mission_type,trigger,priority,risk,approval_required,template,"
                    "params,schedule,state,correlation_id,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (mission_id, owner, title, objective, mission_type, trigger,
                     priority, int(risk), 1 if approval_required else 0, template,
                     params_json, schedule, MISSION_DRAFT, correlation_id, now))
            except sqlite3.IntegrityError:
                c.execute("ROLLBACK")
                return {"created": False, "reason": "duplicate_mission_id",
                        "mission_id": mission_id}
            c.execute("COMMIT")
        finally:
            c.close()
        self._event("harness.mission.created",
                    {"mission_id": mission_id, "owner": owner,
                     "template": template, "approval_required": bool(approval_required)})
        return {"created": True, "mission_id": mission_id}

    def _mission_state(self, c, mission_id):
        row = c.execute("SELECT state FROM mission WHERE mission_id=?",
                        (mission_id,)).fetchone()
        return row["state"] if row else None

    def _mission_transition(self, mission_id, to_state, *, extra_sql="",
                            extra_args=(), event="", now=None) -> dict:
        """CAS-style mission state transition inside a BEGIN IMMEDIATE txn. Rejects
        an unknown mission, a terminal (immutable) mission, and any move not in the
        explicit transition graph (fail closed). Idempotent no-op if already in
        `to_state`."""
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            cur = self._mission_state(c, mission_id)
            if cur is None:
                c.execute("ROLLBACK"); return {"ok": False, "reason": "unknown_mission"}
            if cur == to_state:
                c.execute("ROLLBACK"); return {"ok": True, "noop": True, "state": cur}
            if cur in MISSION_TERMINAL:
                c.execute("ROLLBACK")
                return {"ok": False, "reason": f"terminal:{cur}"}
            if to_state not in _MISSION_VALID.get(cur, set()):
                c.execute("ROLLBACK")
                return {"ok": False, "reason": f"invalid_transition:{cur}->{to_state}"}
            sets = "state=?"
            args = [to_state]
            if extra_sql:
                sets += ", " + extra_sql
                args.extend(extra_args)
            args.append(mission_id)
            c.execute(f"UPDATE mission SET {sets} WHERE mission_id=?", args)
            c.execute("COMMIT")
        finally:
            c.close()
        if event:
            self._event(event, {"mission_id": mission_id, "state": to_state})
        return {"ok": True, "state": to_state}

    def mark_mission_approval_required(self, mission_id, *, now=None) -> dict:
        return self._mission_transition(mission_id, MISSION_APPROVAL_REQUIRED,
                                        event="harness.mission.approval_required",
                                        now=now)

    def approve_mission(self, mission_id, *, approver, now=None) -> dict:
        approver = _clean_str(approver, field="approver", maxlen=120)
        now = now if now is not None else _now()
        return self._mission_transition(
            mission_id, MISSION_APPROVED,
            extra_sql="approved_at=?, approved_by=?", extra_args=(now, approver),
            event="harness.mission.approved", now=now)

    def enqueue_mission(self, mission_id, *, now=None) -> dict:
        now = now if now is not None else _now()
        return self._mission_transition(
            mission_id, MISSION_QUEUED, extra_sql="queued_at=?", extra_args=(now,),
            event="harness.mission.queued", now=now)

    def cancel_mission(self, mission_id, *, requester="", now=None) -> dict:
        now = now if now is not None else _now()
        return self._mission_transition(
            mission_id, MISSION_CANCELLED, extra_sql="terminal_at=?",
            extra_args=(now,), event="harness.mission.cancelled", now=now)

    def block_mission(self, mission_id, *, reason="", now=None) -> dict:
        reason = _clean_str(reason, field="reason", maxlen=120)
        now = now if now is not None else _now()
        return self._mission_transition(
            mission_id, MISSION_BLOCKED,
            extra_sql="terminal_at=?, failure_code=?", extra_args=(now, reason),
            event="harness.mission.blocked", now=now)

    def begin_mission_run(self, mission_id, *, now=None) -> dict:
        """queued → running; open a mission_run attempt row. Returns the attempt
        number. Fail-closed on a non-queued mission (never double-run)."""
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT state, run_count FROM mission WHERE mission_id=?",
                            (mission_id,)).fetchone()
            if row is None:
                c.execute("ROLLBACK"); return {"ok": False, "reason": "unknown_mission"}
            if row["state"] != MISSION_QUEUED:
                c.execute("ROLLBACK")
                return {"ok": False, "reason": f"not_queued:{row['state']}"}
            attempt = int(row["run_count"]) + 1
            c.execute("UPDATE mission SET state=?, run_count=?, started_at=? "
                      "WHERE mission_id=? AND state=?",
                      (MISSION_RUNNING, attempt, now, mission_id, MISSION_QUEUED))
            c.execute("INSERT INTO mission_run(mission_id,attempt,state,started_at) "
                      "VALUES(?,?,?,?)",
                      (mission_id, attempt, MISSION_RUNNING, now))
            c.execute("COMMIT")
        finally:
            c.close()
        self._event("harness.mission.started",
                    {"mission_id": mission_id, "attempt": attempt})
        return {"ok": True, "attempt": attempt}

    def finish_mission_run(self, mission_id, *, attempt, state, pipeline_id="",
                           failure_code="", steps_run=0, now=None) -> dict:
        """running → completed | failed | blocked. Records the run attempt outcome
        AND the mission terminal state atomically. Terminal is immutable."""
        if state not in MISSION_RUN_TERMINAL:
            raise LedgerError("bad_mission_state", state)
        pipeline_id = _clean_str(pipeline_id, field="pipeline_id", maxlen=128)
        failure_code = _clean_str(failure_code, field="failure_code", maxlen=160)
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT state FROM mission WHERE mission_id=?",
                            (mission_id,)).fetchone()
            if row is None:
                c.execute("ROLLBACK"); return {"ok": False, "reason": "unknown_mission"}
            if row["state"] in MISSION_TERMINAL:
                c.execute("ROLLBACK")
                return {"ok": False, "reason": f"already_terminal:{row['state']}"}
            c.execute("UPDATE mission_run SET state=?, pipeline_id=?, failure_code=?, "
                      "steps_run=?, terminal_at=? WHERE mission_id=? AND attempt=?",
                      (state, pipeline_id, failure_code, int(steps_run), now,
                       mission_id, int(attempt)))
            c.execute("UPDATE mission SET state=?, last_pipeline_id=?, failure_code=?, "
                      "terminal_at=? WHERE mission_id=? AND state=?",
                      (state, pipeline_id, failure_code, now, mission_id,
                       MISSION_RUNNING))
            c.execute("COMMIT")
        finally:
            c.close()
        self._event(f"harness.mission.{state}",
                    {"mission_id": mission_id, "attempt": int(attempt),
                     "pipeline_id": pipeline_id, "failure_code": failure_code})
        return {"ok": True, "state": state}

    def inspect_mission(self, mission_id, *, owner: str | None = None) -> Optional[dict]:
        """Owner-safe mission record + its run history. If `owner` is given and does
        not match, returns None (no cross-owner disclosure)."""
        with self._conn() as c:
            row = c.execute("SELECT * FROM mission WHERE mission_id=?",
                            (mission_id,)).fetchone()
            if row is None:
                return None
            if owner is not None and row["owner"] != owner:
                return None
            runs = [dict(r) for r in c.execute(
                "SELECT attempt,pipeline_id,state,failure_code,steps_run,started_at,"
                "terminal_at FROM mission_run WHERE mission_id=? ORDER BY attempt",
                (mission_id,)).fetchall()]
        out = {k: row[k] for k in _MISSION_SAFE_FIELDS}
        out["approval_required"] = bool(out["approval_required"])
        out["params"] = _mission_params(out["params"])
        out["runs"] = runs
        return out

    def list_missions(self, owner: str | None = None, *, limit: int = 100) -> list[dict]:
        """Owner-safe recent missions (no argv/output)."""
        limit = max(1, min(int(limit), 1000))
        q = f"SELECT {','.join(_MISSION_SAFE_FIELDS)} FROM mission"
        args: list = []
        if owner:
            q += " WHERE owner=?"; args.append(owner)
        q += " ORDER BY created_at DESC LIMIT ?"; args.append(limit)
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(q, args).fetchall()]
        for r in rows:
            r["approval_required"] = bool(r["approval_required"])
            r["params"] = _mission_params(r["params"])
        return rows

    def mission_history(self, mission_id, *, owner: str | None = None) -> list[dict]:
        """Owner-safe execution history (run attempts) for one mission."""
        with self._conn() as c:
            m = c.execute("SELECT owner FROM mission WHERE mission_id=?",
                          (mission_id,)).fetchone()
            if m is None or (owner is not None and m["owner"] != owner):
                return []
            return [dict(r) for r in c.execute(
                "SELECT attempt,pipeline_id,state,failure_code,steps_run,started_at,"
                "terminal_at FROM mission_run WHERE mission_id=? ORDER BY attempt",
                (mission_id,)).fetchall()]

    def mission_health(self, owner: str | None = None) -> dict:
        """Mission state census (owner-scoped when owner given)."""
        where, args = "", []
        if owner:
            where, args = " WHERE owner=?", [owner]
        with self._conn() as c:
            by_state = {r["state"]: r["n"] for r in c.execute(
                f"SELECT state, COUNT(*) n FROM mission{where} GROUP BY state",
                args).fetchall()}
        return {"by_state": by_state,
                "running": by_state.get(MISSION_RUNNING, 0),
                "queued": by_state.get(MISSION_QUEUED, 0),
                "completed": by_state.get(MISSION_COMPLETED, 0),
                "failed": by_state.get(MISSION_FAILED, 0),
                "approval_required": by_state.get(MISSION_APPROVAL_REQUIRED, 0),
                "total": sum(by_state.values())}

    # ── M17.14 mission SCHEDULES (durable definitions; scheduler is above) ───
    def create_schedule(self, schedule_id, *, owner, mission_template_id,
                        schedule_type, timezone="UTC", expression=None, params=None,
                        description="", retry_policy="default", next_due_at=0.0,
                        version=1, now=None) -> dict:
        owner = _clean_str(owner, field="owner")
        if not owner:
            raise LedgerSecurityError("LEDGER_FIELD_REJECTED", "empty owner")
        schedule_id = _clean_str(schedule_id, field="schedule_id", maxlen=128)
        mission_template_id = _clean_str(mission_template_id,
                                         field="mission_template_id", maxlen=120)
        schedule_type = _clean_str(schedule_type, field="schedule_type", maxlen=40)
        timezone = _clean_str(timezone, field="timezone", maxlen=64)
        description = _clean_str(description, field="description", maxlen=300)
        retry_policy = _clean_str(retry_policy, field="retry_policy", maxlen=40)
        expression = expression or {}
        params = params or {}
        _reject_secrets({"description": description, "params": params,
                         "expression": expression}, where="schedule_identity")
        expr_json = json.dumps(expression, sort_keys=True, default=str)[:1000]
        params_json = json.dumps(params, sort_keys=True, default=str)[:4000]
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            try:
                c.execute(
                    "INSERT INTO mission_schedule(schedule_id,owner,"
                    "mission_template_id,schedule_type,timezone,expression,params,"
                    "enabled,status,description,retry_policy,version,next_due_at,"
                    "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (schedule_id, owner, mission_template_id, schedule_type, timezone,
                     expr_json, params_json, 1, SCHEDULE_ACTIVE, description,
                     retry_policy, int(version), float(next_due_at), now, now))
            except sqlite3.IntegrityError:
                c.execute("ROLLBACK")
                return {"created": False, "reason": "duplicate_schedule_id",
                        "schedule_id": schedule_id}
            c.execute("COMMIT")
        finally:
            c.close()
        self._event("harness.schedule.created",
                    {"schedule_id": schedule_id, "owner": owner,
                     "template": mission_template_id, "type": schedule_type})
        return {"created": True, "schedule_id": schedule_id}

    def set_schedule_status(self, schedule_id, *, to_status, now=None) -> dict:
        """Explicit, validated schedule state transition. Terminal/disabled states
        never silently reactivate; anything unlisted is rejected (fail closed)."""
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT status FROM mission_schedule WHERE schedule_id=?",
                            (schedule_id,)).fetchone()
            if row is None:
                c.execute("ROLLBACK"); return {"ok": False, "reason": "unknown_schedule"}
            cur = row["status"]
            if cur == to_status:
                c.execute("ROLLBACK"); return {"ok": True, "noop": True, "status": cur}
            if cur in SCHEDULE_TERMINAL:
                c.execute("ROLLBACK"); return {"ok": False, "reason": f"terminal:{cur}"}
            if to_status not in _SCHEDULE_VALID.get(cur, set()):
                c.execute("ROLLBACK")
                return {"ok": False, "reason": f"invalid_transition:{cur}->{to_status}"}
            enabled = 1 if to_status == SCHEDULE_ACTIVE else 0
            c.execute("UPDATE mission_schedule SET status=?, enabled=?, updated_at=? "
                      "WHERE schedule_id=?", (to_status, enabled, now, schedule_id))
            c.execute("COMMIT")
        finally:
            c.close()
        self._event("harness.schedule.status", {"schedule_id": schedule_id,
                                                 "status": to_status})
        return {"ok": True, "status": to_status}

    def update_schedule_due(self, schedule_id, *, next_due_at, last_due_at=None,
                            last_occurrence_id=None, now=None) -> dict:
        """Advance a schedule's due bookkeeping. Only touches an ACTIVE schedule
        (never resurrect a paused/terminal one)."""
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT status FROM mission_schedule WHERE schedule_id=?",
                            (schedule_id,)).fetchone()
            if row is None or row["status"] != SCHEDULE_ACTIVE:
                c.execute("ROLLBACK")
                return {"ok": False, "reason": "not_active"}
            sets, args = ["next_due_at=?", "updated_at=?"], [float(next_due_at), now]
            if last_due_at is not None:
                sets.append("last_due_at=?"); args.append(float(last_due_at))
            if last_occurrence_id is not None:
                sets.append("last_occurrence_id=?")
                args.append(_clean_str(last_occurrence_id, field="occ", maxlen=128))
            args.append(schedule_id)
            c.execute(f"UPDATE mission_schedule SET {','.join(sets)} WHERE schedule_id=?",
                      args)
            c.execute("COMMIT")
        finally:
            c.close()
        return {"ok": True}

    def get_schedule(self, schedule_id, *, owner: str | None = None) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM mission_schedule WHERE schedule_id=?",
                            (schedule_id,)).fetchone()
        if row is None or (owner is not None and row["owner"] != owner):
            return None
        out = {k: row[k] for k in _SCHEDULE_SAFE_FIELDS}
        out["enabled"] = bool(out["enabled"])
        out["expression"] = _mission_params(out["expression"])
        out["params"] = _mission_params(out["params"])
        return out

    def list_schedules(self, owner: str | None = None, *, limit: int = 200) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        q = f"SELECT {','.join(_SCHEDULE_SAFE_FIELDS)} FROM mission_schedule"
        args: list = []
        if owner:
            q += " WHERE owner=?"; args.append(owner)
        q += " ORDER BY created_at DESC LIMIT ?"; args.append(limit)
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(q, args).fetchall()]
        for r in rows:
            r["enabled"] = bool(r["enabled"])
            r["expression"] = _mission_params(r["expression"])
            r["params"] = _mission_params(r["params"])
        return rows

    def due_schedules(self, *, now=None, limit: int = 200) -> list[dict]:
        """ACTIVE schedules whose next_due_at has arrived (owner-safe rows)."""
        now = now if now is not None else _now()
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(
                f"SELECT {','.join(_SCHEDULE_SAFE_FIELDS)} FROM mission_schedule "
                "WHERE status=? AND enabled=1 AND next_due_at>0 AND next_due_at<=? "
                "ORDER BY next_due_at LIMIT ?",
                (SCHEDULE_ACTIVE, now, max(1, min(int(limit), 1000)))).fetchall()]
        for r in rows:
            r["enabled"] = bool(r["enabled"])
            r["expression"] = _mission_params(r["expression"])
            r["params"] = _mission_params(r["params"])
        return rows

    def schedule_health(self, owner: str | None = None) -> dict:
        where, args = "", []
        if owner:
            where, args = " WHERE owner=?", [owner]
        with self._conn() as c:
            by = {r["status"]: r["n"] for r in c.execute(
                f"SELECT status, COUNT(*) n FROM mission_schedule{where} "
                "GROUP BY status", args).fetchall()}
        return {"by_status": by, "active": by.get(SCHEDULE_ACTIVE, 0),
                "paused": by.get(SCHEDULE_PAUSED, 0),
                "disabled": by.get(SCHEDULE_DISABLED, 0),
                "completed": by.get(SCHEDULE_COMPLETED, 0),
                "invalid": by.get(SCHEDULE_INVALID, 0),
                "total": sum(by.values())}

    # ── M17.14 mission OCCURRENCES (one per due time; lease-claimed) ─────────
    def create_occurrence(self, occurrence_id, *, schedule_id, owner, due_at,
                          dedup_key, now=None) -> dict:
        """Idempotent create — the UNIQUE(dedup_key) makes concurrent creators
        resolve to exactly one winner (no duplicate occurrence, no duplicate
        mission downstream)."""
        owner = _clean_str(owner, field="owner")
        if not owner:
            raise LedgerSecurityError("LEDGER_FIELD_REJECTED", "empty owner")
        occurrence_id = _clean_str(occurrence_id, field="occurrence_id", maxlen=160)
        schedule_id = _clean_str(schedule_id, field="schedule_id", maxlen=128)
        dedup_key = _clean_str(dedup_key, field="dedup_key", maxlen=200)
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            try:
                c.execute(
                    "INSERT INTO mission_occurrence(occurrence_id,schedule_id,owner,"
                    "due_at,dedup_key,state,created_at) VALUES(?,?,?,?,?,?,?)",
                    (occurrence_id, schedule_id, owner, float(due_at), dedup_key,
                     OCC_PENDING, now))
            except sqlite3.IntegrityError:
                c.execute("ROLLBACK")
                return {"created": False, "reason": "duplicate_occurrence"}
            c.execute("COMMIT")
        finally:
            c.close()
        self._event("harness.occurrence.created",
                    {"occurrence_id": occurrence_id, "schedule_id": schedule_id})
        return {"created": True, "occurrence_id": occurrence_id}

    def claim_occurrence(self, occurrence_id, *, worker, now=None,
                         lease_sec: float = 120.0) -> bool:
        """Atomic lease claim: pending/retry_wait → claimed, only if unleased or the
        lease has expired. An ACTIVE lease is NOT stealable. Exactly one winner."""
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT state, lease_expires_at, next_attempt_at "
                            "FROM mission_occurrence WHERE occurrence_id=?",
                            (occurrence_id,)).fetchone()
            if row is None:
                c.execute("ROLLBACK"); return False
            if row["state"] not in OCC_DISPATCHABLE:
                c.execute("ROLLBACK"); return False
            if row["state"] == OCC_RETRY_WAIT and (row["next_attempt_at"] or 0) > now:
                c.execute("ROLLBACK"); return False
            if (row["lease_expires_at"] or 0) > now:      # active lease → not stealable
                c.execute("ROLLBACK"); return False
            c.execute("UPDATE mission_occurrence SET state=?, claim_owner=?, "
                      "lease_expires_at=?, started_at=CASE WHEN started_at=0 THEN ? "
                      "ELSE started_at END WHERE occurrence_id=? AND state IN (?,?)",
                      (OCC_CLAIMED, _clean_str(worker, field="worker", maxlen=80),
                       now + float(lease_sec), now, occurrence_id,
                       OCC_PENDING, OCC_RETRY_WAIT))
            c.execute("COMMIT")
        finally:
            c.close()
        return True

    def _occ_transition(self, occurrence_id, to_state, *, extra_sql="",
                        extra_args=(), event="", now=None) -> dict:
        """Validated occurrence state transition (fail-closed graph, immutable
        terminals). `extra_sql` is an optional trailing SET clause (no state)."""
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT state FROM mission_occurrence WHERE occurrence_id=?",
                            (occurrence_id,)).fetchone()
            if row is None:
                c.execute("ROLLBACK"); return {"ok": False, "reason": "unknown_occurrence"}
            cur = row["state"]
            if cur in OCC_TERMINAL:
                c.execute("ROLLBACK"); return {"ok": False, "reason": f"terminal:{cur}"}
            if to_state not in _OCC_VALID.get(cur, set()):
                c.execute("ROLLBACK")
                return {"ok": False, "reason": f"invalid_transition:{cur}->{to_state}"}
            clause = "state=?" + (", " + extra_sql if extra_sql else "")
            args = [to_state, *extra_args, occurrence_id]
            c.execute(f"UPDATE mission_occurrence SET {clause} WHERE occurrence_id=?",
                      args)
            c.execute("COMMIT")
        finally:
            c.close()
        if event:
            self._event(event, {"occurrence_id": occurrence_id, "state": to_state})
        return {"ok": True, "state": to_state}

    def link_occurrence_mission(self, occurrence_id, *, mission_id, now=None) -> dict:
        """claimed → running, binding the (deterministic) mission_id. Idempotent if
        already running with the same mission_id (crash-recovery safe)."""
        mission_id = _clean_str(mission_id, field="mission_id", maxlen=160)
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT state, mission_id FROM mission_occurrence "
                            "WHERE occurrence_id=?", (occurrence_id,)).fetchone()
            if row is None:
                c.execute("ROLLBACK"); return {"ok": False, "reason": "unknown_occurrence"}
            if row["state"] in OCC_TERMINAL:
                c.execute("ROLLBACK"); return {"ok": False, "reason": f"terminal:{row['state']}"}
            if row["state"] == OCC_RUNNING and row["mission_id"] == mission_id:
                c.execute("ROLLBACK"); return {"ok": True, "noop": True}
            if row["state"] not in (OCC_CLAIMED, OCC_RUNNING):
                c.execute("ROLLBACK")
                return {"ok": False, "reason": f"not_claimed:{row['state']}"}
            c.execute("UPDATE mission_occurrence SET state=?, mission_id=? "
                      "WHERE occurrence_id=?", (OCC_RUNNING, mission_id, occurrence_id))
            c.execute("COMMIT")
        finally:
            c.close()
        self._event("harness.occurrence.mission_created",
                    {"occurrence_id": occurrence_id, "mission_id": mission_id})
        return {"ok": True, "state": OCC_RUNNING}

    def finish_occurrence(self, occurrence_id, *, state, mission_run_id="",
                          failure_category="", failure_summary="", now=None) -> dict:
        """Move an occurrence to a terminal state that REFLECTS the linked mission
        result. Terminal is immutable."""
        if state not in OCC_TERMINAL:
            raise LedgerError("bad_occurrence_state", state)
        failure_category = _clean_str(failure_category, field="failure_category", maxlen=80)
        failure_summary = _clean_str(failure_summary, field="failure_summary", maxlen=200)
        mission_run_id = _clean_str(mission_run_id, field="mission_run_id", maxlen=64)
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT state FROM mission_occurrence WHERE occurrence_id=?",
                            (occurrence_id,)).fetchone()
            if row is None:
                c.execute("ROLLBACK"); return {"ok": False, "reason": "unknown_occurrence"}
            if row["state"] in OCC_TERMINAL:
                c.execute("ROLLBACK")
                return {"ok": False, "reason": f"already_terminal:{row['state']}"}
            c.execute("UPDATE mission_occurrence SET state=?, mission_run_id=?, "
                      "failure_category=?, failure_summary=?, lease_expires_at=0, "
                      "completed_at=? WHERE occurrence_id=?",
                      (state, mission_run_id, failure_category, failure_summary,
                       now, occurrence_id))
            c.execute("COMMIT")
        finally:
            c.close()
        self._event(f"harness.occurrence.{state}",
                    {"occurrence_id": occurrence_id, "failure_category": failure_category})
        return {"ok": True, "state": state}

    def occurrence_retry(self, occurrence_id, *, reason="", max_attempts=None,
                         now=None) -> dict:
        """Infrastructure-failure retry: attempt++, next_attempt_at via the shared
        deterministic RETRY_SCHEDULE, state → retry_wait. Past the bound → failed
        terminal (never unbounded). NOT used for approval/owner/param/mission
        outcomes — those go straight to their terminal state."""
        max_attempts = max_attempts if max_attempts is not None else MAX_DELIVERY_ATTEMPTS
        reason = _clean_str(reason, field="reason", maxlen=120)
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT state, attempt_count FROM mission_occurrence "
                            "WHERE occurrence_id=?", (occurrence_id,)).fetchone()
            if row is None:
                c.execute("ROLLBACK"); return {"ok": False, "reason": "unknown_occurrence"}
            if row["state"] in OCC_TERMINAL:
                c.execute("ROLLBACK"); return {"ok": False, "reason": "terminal"}
            attempt = int(row["attempt_count"]) + 1
            if attempt >= int(max_attempts):
                c.execute("UPDATE mission_occurrence SET state=?, attempt_count=?, "
                          "failure_category=?, failure_summary=?, lease_expires_at=0, "
                          "completed_at=? WHERE occurrence_id=?",
                          (OCC_FAILED, attempt, "infrastructure",
                           f"retry_exhausted:{reason}"[:200], now, occurrence_id))
                c.execute("COMMIT")
                self._event("harness.occurrence.failed",
                            {"occurrence_id": occurrence_id, "failure_category": "infrastructure"})
                return {"ok": True, "state": OCC_FAILED, "terminal": True}
            delay = retry_delay(attempt)
            c.execute("UPDATE mission_occurrence SET state=?, attempt_count=?, "
                      "next_attempt_at=?, lease_expires_at=0, claim_owner='' "
                      "WHERE occurrence_id=?",
                      (OCC_RETRY_WAIT, attempt, now + delay, occurrence_id))
            c.execute("COMMIT")
        finally:
            c.close()
        return {"ok": True, "state": OCC_RETRY_WAIT, "attempt": attempt,
                "next_attempt_at": now + delay}

    def pending_due_occurrences(self, *, now=None, limit: int = 100) -> list[dict]:
        """Dispatchable occurrences: pending, or retry_wait whose next_attempt_at
        has arrived. Deterministic ordering (due_at, occurrence_id)."""
        now = now if now is not None else _now()
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM mission_occurrence WHERE (state=? OR "
                "(state=? AND next_attempt_at<=?)) ORDER BY due_at, occurrence_id "
                "LIMIT ?", (OCC_PENDING, OCC_RETRY_WAIT, now,
                            max(1, min(int(limit), 1000)))).fetchall()]
        return rows

    def reclaim_stale_occurrences(self, *, now=None, lease_sec: float = 120.0) -> list[dict]:
        """Return CLAIMED/RUNNING occurrences whose lease expired — for the
        reconciler to inspect (crash recovery). Does not itself create missions."""
        now = now if now is not None else _now()
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM mission_occurrence WHERE state IN (?,?) "
                "AND lease_expires_at>0 AND lease_expires_at<?",
                (OCC_CLAIMED, OCC_RUNNING, now)).fetchall()]

    def requeue_occurrence(self, occurrence_id, *, now=None) -> dict:
        """A crashed CLAIMED occurrence with NO mission yet → back to pending."""
        return self._occ_transition(occurrence_id, OCC_PENDING,
                                    extra_sql="lease_expires_at=0, claim_owner=''",
                                    event="harness.occurrence.requeued", now=now)

    def inspect_occurrence(self, occurrence_id, *, owner: str | None = None) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM mission_occurrence WHERE occurrence_id=?",
                            (occurrence_id,)).fetchone()
        if row is None or (owner is not None and row["owner"] != owner):
            return None
        return {k: row[k] for k in _OCC_SAFE_FIELDS}

    def list_occurrences(self, owner: str | None = None, *, schedule_id=None,
                         limit: int = 200) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        q = f"SELECT {','.join(_OCC_SAFE_FIELDS)} FROM mission_occurrence"
        conds, args = [], []
        if owner:
            conds.append("owner=?"); args.append(owner)
        if schedule_id:
            conds.append("schedule_id=?"); args.append(schedule_id)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY due_at DESC LIMIT ?"; args.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    def occurrence_health(self, owner: str | None = None, *, now=None) -> dict:
        now = now if now is not None else _now()
        where, args = "", []
        if owner:
            where, args = " WHERE owner=?", [owner]
        with self._conn() as c:
            by = {r["state"]: r["n"] for r in c.execute(
                f"SELECT state, COUNT(*) n FROM mission_occurrence{where} "
                "GROUP BY state", args).fetchall()}
            stale = c.execute(
                "SELECT COUNT(*) n FROM mission_occurrence WHERE state IN (?,?) "
                "AND lease_expires_at>0 AND lease_expires_at<?",
                (OCC_CLAIMED, OCC_RUNNING, now)).fetchone()["n"]
        return {"by_state": by, "pending": by.get(OCC_PENDING, 0),
                "claimed": by.get(OCC_CLAIMED, 0), "running": by.get(OCC_RUNNING, 0),
                "retry_wait": by.get(OCC_RETRY_WAIT, 0),
                "succeeded": by.get(OCC_SUCCEEDED, 0), "failed": by.get(OCC_FAILED, 0),
                "approval_required": by.get(OCC_APPROVAL_REQUIRED, 0),
                "stale_leases": stale, "total": sum(by.values())}

    # ── M17.14 trusted event TRIGGERS + receipts (allowlist, dedup) ─────────
    def create_trigger(self, trigger_id, *, owner, event_type, mission_template_id,
                       params=None, payload_map=None, cooldown_sec=0.0,
                       description="", now=None) -> dict:
        owner = _clean_str(owner, field="owner")
        if not owner:
            raise LedgerSecurityError("LEDGER_FIELD_REJECTED", "empty owner")
        trigger_id = _clean_str(trigger_id, field="trigger_id", maxlen=128)
        event_type = _clean_str(event_type, field="event_type", maxlen=80)
        mission_template_id = _clean_str(mission_template_id,
                                         field="mission_template_id", maxlen=120)
        description = _clean_str(description, field="description", maxlen=300)
        params = params or {}
        payload_map = payload_map or {}
        _reject_secrets({"params": params, "payload_map": payload_map,
                         "description": description}, where="trigger_identity")
        p_json = json.dumps(params, sort_keys=True, default=str)[:4000]
        m_json = json.dumps(payload_map, sort_keys=True, default=str)[:2000]
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            try:
                c.execute(
                    "INSERT INTO mission_event_trigger(trigger_id,owner,event_type,"
                    "mission_template_id,params,payload_map,enabled,cooldown_sec,"
                    "status,description,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (trigger_id, owner, event_type, mission_template_id, p_json,
                     m_json, 1, float(cooldown_sec), SCHEDULE_ACTIVE, description,
                     now, now))
            except sqlite3.IntegrityError:
                c.execute("ROLLBACK")
                return {"created": False, "reason": "duplicate_trigger_id"}
            c.execute("COMMIT")
        finally:
            c.close()
        self._event("harness.trigger.created",
                    {"trigger_id": trigger_id, "owner": owner, "event_type": event_type})
        return {"created": True, "trigger_id": trigger_id}

    def set_trigger_status(self, trigger_id, *, to_status, now=None) -> dict:
        now = now if now is not None else _now()
        if to_status not in (SCHEDULE_ACTIVE, SCHEDULE_PAUSED, SCHEDULE_DISABLED):
            return {"ok": False, "reason": "bad_status"}
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT status FROM mission_event_trigger WHERE trigger_id=?",
                            (trigger_id,)).fetchone()
            if row is None:
                c.execute("ROLLBACK"); return {"ok": False, "reason": "unknown_trigger"}
            if row["status"] == SCHEDULE_DISABLED:
                c.execute("ROLLBACK"); return {"ok": False, "reason": "terminal:disabled"}
            enabled = 1 if to_status == SCHEDULE_ACTIVE else 0
            c.execute("UPDATE mission_event_trigger SET status=?, enabled=?, updated_at=? "
                      "WHERE trigger_id=?", (to_status, enabled, now, trigger_id))
            c.execute("COMMIT")
        finally:
            c.close()
        self._event("harness.trigger.status", {"trigger_id": trigger_id, "status": to_status})
        return {"ok": True, "status": to_status}

    def triggers_for_event(self, event_type, *, now=None) -> list[dict]:
        """ACTIVE, enabled triggers bound to an allowlisted event type."""
        if event_type not in TRUSTED_EVENT_TYPES:
            return []
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM mission_event_trigger WHERE event_type=? AND status=? "
                "AND enabled=1", (event_type, SCHEDULE_ACTIVE)).fetchall()]
        for r in rows:
            r["params"] = _mission_params(r["params"])
            r["payload_map"] = _mission_params(r["payload_map"])
        return rows

    def get_trigger(self, trigger_id, *, owner: str | None = None) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM mission_event_trigger WHERE trigger_id=?",
                            (trigger_id,)).fetchone()
        if row is None or (owner is not None and row["owner"] != owner):
            return None
        out = {k: row[k] for k in _TRIGGER_SAFE_FIELDS}
        out["enabled"] = bool(out["enabled"])
        out["params"] = _mission_params(out["params"])
        out["payload_map"] = _mission_params(out["payload_map"])
        return out

    def list_triggers(self, owner: str | None = None, *, limit: int = 200) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        q = f"SELECT {','.join(_TRIGGER_SAFE_FIELDS)} FROM mission_event_trigger"
        args: list = []
        if owner:
            q += " WHERE owner=?"; args.append(owner)
        q += " ORDER BY created_at DESC LIMIT ?"; args.append(limit)
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(q, args).fetchall()]
        for r in rows:
            r["enabled"] = bool(r["enabled"])
            r["params"] = _mission_params(r["params"])
            r["payload_map"] = _mission_params(r["payload_map"])
        return rows

    def create_receipt(self, receipt_id, *, trigger_id, owner, event_type,
                       source_event_id, dedup_key, state="accepted", mission_id="",
                       rejection_category="", now=None) -> dict:
        """Durable trigger receipt. UNIQUE(dedup_key) makes a repeated source event
        a no-op (no duplicate mission)."""
        receipt_id = _clean_str(receipt_id, field="receipt_id", maxlen=160)
        dedup_key = _clean_str(dedup_key, field="dedup_key", maxlen=200)
        owner = _clean_str(owner, field="owner")
        now = now if now is not None else _now()
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            try:
                c.execute(
                    "INSERT INTO mission_event_receipt(receipt_id,trigger_id,owner,"
                    "event_type,source_event_id,dedup_key,state,mission_id,"
                    "rejection_category,received_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (receipt_id, _clean_str(trigger_id, field="trigger_id", maxlen=128),
                     owner, _clean_str(event_type, field="event_type", maxlen=80),
                     _clean_str(source_event_id, field="source_event_id", maxlen=160),
                     dedup_key, state,
                     _clean_str(mission_id, field="mission_id", maxlen=160),
                     _clean_str(rejection_category, field="rejection_category", maxlen=80),
                     now))
            except sqlite3.IntegrityError:
                c.execute("ROLLBACK")
                return {"created": False, "reason": "duplicate_receipt"}
            c.execute("COMMIT")
        finally:
            c.close()
        self._event("harness.trigger.receipt",
                    {"receipt_id": receipt_id, "trigger_id": trigger_id, "state": state})
        return {"created": True, "receipt_id": receipt_id}

    def update_receipt(self, receipt_id, *, state, mission_id=None,
                       rejection_category=None) -> dict:
        sets, args = ["state=?"], [state]
        if mission_id is not None:
            sets.append("mission_id=?")
            args.append(_clean_str(mission_id, field="mission_id", maxlen=160))
        if rejection_category is not None:
            sets.append("rejection_category=?")
            args.append(_clean_str(rejection_category, field="rej", maxlen=80))
        args.append(receipt_id)
        with self._conn() as c:
            c.execute(f"UPDATE mission_event_receipt SET {','.join(sets)} "
                      "WHERE receipt_id=?", args)
        return {"ok": True}

    def list_receipts(self, owner: str | None = None, *, limit: int = 200) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        q = f"SELECT {','.join(_RECEIPT_SAFE_FIELDS)} FROM mission_event_receipt"
        args: list = []
        if owner:
            q += " WHERE owner=?"; args.append(owner)
        q += " ORDER BY received_at DESC LIMIT ?"; args.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    def cleanup(self, *, retention_sec: float, now=None) -> dict:
        """Delete terminal runs (and their transitions) older than the retention
        window. Active runs are never touched."""
        now = now if now is not None else _now()
        cutoff = now - float(retention_sec)
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
            ids = [r["run_id"] for r in c.execute(
                f"SELECT run_id FROM run WHERE state IN ({','.join('?'*len(TERMINAL))}) "
                "AND terminal_at>0 AND terminal_at<?",
                (*sorted(TERMINAL), cutoff)).fetchall()]
            for rid in ids:
                c.execute("DELETE FROM run_transition WHERE run_id=?", (rid,))
                c.execute("DELETE FROM run_alert WHERE run_id=?", (rid,))
                c.execute("DELETE FROM run WHERE run_id=?", (rid,))
            c.execute("COMMIT")
        finally:
            c.close()
        return {"deleted": len(ids), "run_ids": ids}

    # ── owner-safe Control Center read model ────────────────────────────────
    def read_model(self, owner: str | None = None, *, now=None, is_alive=None,
                   limit: int = 50) -> dict:
        """Bounded, owner-safe view for the Control Center harness cell. Exposes
        state/duration/heartbeat/recovery — NEVER raw argv, output, or secrets."""
        now = now if now is not None else _now()
        active = self.list_active(owner)[:limit]
        rows, attention = [], []
        for r in active:
            klass = self.classify(r, now=now, is_alive=is_alive)
            dur = round(now - (r.get("started_at") or r.get("created_at") or now), 2)
            hb = r.get("heartbeat_at") or 0
            rows.append({
                "run_id": r["run_id"], "owner": r["owner"],
                "harness_id": r["harness_id"], "operation_id": r["operation_id"],
                "state": r["state"], "duration_sec": max(dur, 0.0),
                "last_heartbeat_age_sec": round(now - hb, 2) if hb else None,
                "class": klass,
                "cancellation": (r["state"] == CANCEL_REQ),
                "recovery_status": r["recovery_status"],
                "verification_status": r["verification_status"],
                "failure_code": r["failure_code"]})
            if klass in ("heartbeat_stale", "process_missing", "cancellation_stuck"):
                attention.append({"run_id": r["run_id"], "class": klass})
        return {"active_runs": rows, "active_count": len(rows),
                "attention": attention, "generated_at": now}

    def health(self) -> dict:
        """Ledger integrity + state census (`ledger-health`)."""
        with self._conn() as c:
            integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
            census = {r["state"]: r["n"] for r in c.execute(
                "SELECT state, COUNT(*) n FROM run GROUP BY state").fetchall()}
            total = c.execute("SELECT COUNT(*) n FROM run").fetchone()["n"]
            trans = c.execute("SELECT COUNT(*) n FROM run_transition").fetchone()["n"]
            dupes = c.execute("SELECT COUNT(*) n FROM (SELECT idempotency_key, "
                              "COUNT(*) c FROM run WHERE idempotency_key!='' "
                              "GROUP BY idempotency_key HAVING c>1)").fetchone()["n"]
            open_alerts = c.execute("SELECT COUNT(*) n FROM run_alert "
                                    "WHERE status!='resolved'").fetchone()["n"]
            pipelines = c.execute("SELECT COUNT(*) n FROM pipeline_run").fetchone()["n"]
            missions = c.execute("SELECT COUNT(*) n FROM mission").fetchone()["n"]
            schedules = c.execute("SELECT COUNT(*) n FROM mission_schedule").fetchone()["n"]
            occurrences = c.execute("SELECT COUNT(*) n FROM mission_occurrence").fetchone()["n"]
            occ_dupes = c.execute("SELECT COUNT(*) n FROM (SELECT dedup_key, "
                                  "COUNT(*) c FROM mission_occurrence GROUP BY "
                                  "dedup_key HAVING c>1)").fetchone()["n"]
        return {"integrity": integrity,
                "ok": integrity == "ok" and dupes == 0 and occ_dupes == 0,
                "total_runs": total, "by_state": census, "transitions": trans,
                "active": sum(census.get(s, 0) for s in ACTIVE),
                "idempotency_collisions": dupes, "open_alerts": open_alerts,
                "pipelines": pipelines, "missions": missions,
                "schedules": schedules, "occurrences": occurrences,
                "occurrence_collisions": occ_dupes, "db_path": str(self.db_path)}

    # ── M17.8 journal drop-in (adapter compatibility, no adapter changes) ───
    # The ApplicationHarnessAdapter calls journal.record_start / record_end;
    # a RunLedger passed as `journal=` durably ledgers the same lifecycle.
    def record_start(self, run_id, *, harness_id, owner, pid, pgid) -> None:
        run = self.inspect(run_id)
        if run is None:                       # adapter-direct run (no pre-claim)
            self.create_run(run_id, owner=owner, harness_id=harness_id)
            self.claim(run_id, pid=pid, pgid=pgid)
            self.mark_running(run_id, pid=pid, pgid=pgid)
        elif run["state"] == QUEUED:
            self.claim(run_id, pid=pid, pgid=pgid)
            self.mark_running(run_id, pid=pid, pgid=pgid)
        elif run["state"] == STARTING:
            self.mark_running(run_id, pid=pid, pgid=pgid)
        else:                                 # already running — refresh heartbeat
            self.record_heartbeat(run_id)

    def record_end(self, run_id, state, exit_code) -> None:
        term = _LEGACY_STATE.get(state, state)
        if term not in TERMINAL:
            term = FAILED
        try:
            # the adapter has already killed the process on cancellation, so
            # route running/starting → cancellation_requested → cancelled to
            # honour the state machine (no direct running→cancelled edge).
            if term == CANCELLED:
                cur = self.latest_state(run_id)
                if cur == RUNNING:            # starting→cancelled is already legal
                    self._transition(run_id, CANCEL_REQ, actor="adapter",
                                     reason="adapter_cancel", cancel_requested_at=_now())
            self.complete(run_id, state=term, exit_code=exit_code)
        except LedgerError:
            pass                              # already terminal — never resurrect

    def active_runs(self) -> list[dict]:
        return self.list_active()

    def reconcile(self, *, is_alive=None) -> list[str]:
        return self.reconcile_stale(is_alive=is_alive)["recovered"]


_default: Optional[RunLedger] = None


def default_ledger() -> RunLedger:
    global _default
    if _default is None:
        _default = RunLedger()
    return _default
