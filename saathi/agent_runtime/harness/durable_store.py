"""FM-I3 HarnessDurableStore — isolated SQLite session + event persistence.

Not a RunStore, ExecutionStore, Approval store, or Audit store.
Injected into HarnessSessionController; no process-default singleton DB.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import json
import sqlite3
import threading
import time

from saathi.agent_runtime.harness.errors import HarnessError, HarnessErrorCode
from saathi.agent_runtime.harness.persistence import (
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    DurableEventRecord,
    DurableSessionRecord,
    RecoveryDisposition,
    RecoveryResult,
    RetentionClass,
    TerminalOutcome,
    default_retention_seconds,
    sanitize_payload,
)
from saathi.agent_runtime.harness.types import HarnessEvent, HarnessEventType
from saathi.agent_runtime.models import RunState


_SCHEMA = """
CREATE TABLE IF NOT EXISTS harness_meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS harness_session(
  session_id TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  harness_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  mission_id TEXT NOT NULL,
  organization_id TEXT NOT NULL DEFAULT '',
  workspace_id TEXT NOT NULL DEFAULT '',
  actor_id TEXT NOT NULL DEFAULT '',
  projected_harness_state TEXT NOT NULL,
  authoritative_run_state_snapshot TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  last_event_sequence INTEGER NOT NULL DEFAULT 0,
  last_event_id TEXT NOT NULL DEFAULT '',
  pending_tool_proposal_id TEXT NOT NULL DEFAULT '',
  pending_execution_id TEXT NOT NULL DEFAULT '',
  pending_approval_reference TEXT NOT NULL DEFAULT '',
  cancellation_requested_at REAL NOT NULL DEFAULT 0,
  cancellation_acknowledged_at REAL NOT NULL DEFAULT 0,
  quarantine_reason TEXT NOT NULL DEFAULT '',
  quarantined INTEGER NOT NULL DEFAULT 0,
  resource_usage_snapshot TEXT NOT NULL DEFAULT '{}',
  terminal_outcome TEXT NOT NULL DEFAULT 'none',
  retention_class TEXT NOT NULL DEFAULT 'active',
  expires_at REAL NOT NULL DEFAULT 0,
  closed INTEGER NOT NULL DEFAULT 0,
  integrity_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS harness_event(
  event_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  sequence_number INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  harness_id TEXT NOT NULL,
  timestamp REAL NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}',
  turn_id TEXT NOT NULL DEFAULT '',
  run_id TEXT NOT NULL DEFAULT '',
  mission_id TEXT NOT NULL DEFAULT '',
  organization_id TEXT NOT NULL DEFAULT '',
  workspace_id TEXT NOT NULL DEFAULT '',
  correlation_id TEXT NOT NULL DEFAULT '',
  causation_id TEXT NOT NULL DEFAULT '',
  classification TEXT NOT NULL DEFAULT 'INTERNAL',
  redaction_state TEXT NOT NULL DEFAULT 'NONE',
  schema_version TEXT NOT NULL,
  integrity_hash TEXT NOT NULL,
  UNIQUE(session_id, sequence_number)
);
CREATE INDEX IF NOT EXISTS idx_he_session_seq
  ON harness_event(session_id, sequence_number);
"""


class HarnessDurableStore:
    """Session + event store with explicit transactions and integrity checks."""

    def __init__(self, db_path: str | Path, *, stale_after_sec: float = 3600.0) -> None:
        path = Path(db_path)
        if str(path) in (":memory:",):
            # sqlite :memory: is per-connection; use shared URI for thread safety
            self.db_path = path
            self._uri = "file:harness_mem?mode=memory&cache=shared"
            self._use_uri = True
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = path
            self._uri = str(path)
            self._use_uri = False
        self.stale_after_sec = float(stale_after_sec)
        self._lock = threading.RLock()
        with self._conn() as c:
            c.executescript(_SCHEMA)
            c.execute(
                "INSERT OR REPLACE INTO harness_meta(key, value) VALUES(?, ?)",
                ("schema_version", SCHEMA_VERSION),
            )

    def _conn(self) -> sqlite3.Connection:
        if self._use_uri:
            c = sqlite3.connect(self._uri, uri=True, timeout=30)
        else:
            c = sqlite3.connect(str(self.db_path), timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        return c

    # ── Session CRUD ────────────────────────────────────────────────────────

    def create_session(self, rec: DurableSessionRecord) -> DurableSessionRecord:
        with self._lock:
            if rec.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
                raise HarnessError(
                    HarnessErrorCode.INVALID_REQUEST,
                    f"unsupported schema_version {rec.schema_version}",
                    session_id=rec.session_id,
                )
            rec.updated_at = time.time()
            if not rec.expires_at:
                try:
                    rc = RetentionClass(rec.retention_class)
                except ValueError:
                    rc = RetentionClass.ACTIVE
                rec.expires_at = rec.created_at + default_retention_seconds(rc)
            rec.seal()
            with self._conn() as c:
                try:
                    c.execute(
                        """INSERT INTO harness_session(
                          session_id, schema_version, harness_id, run_id, mission_id,
                          organization_id, workspace_id, actor_id, projected_harness_state,
                          authoritative_run_state_snapshot, created_at, updated_at,
                          last_event_sequence, last_event_id, pending_tool_proposal_id,
                          pending_execution_id, pending_approval_reference,
                          cancellation_requested_at, cancellation_acknowledged_at,
                          quarantine_reason, quarantined, resource_usage_snapshot,
                          terminal_outcome, retention_class, expires_at, closed, integrity_hash
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        self._session_row(rec),
                    )
                    c.commit()
                except sqlite3.IntegrityError as exc:
                    raise HarnessError(
                        HarnessErrorCode.IDEMPOTENCY_CONFLICT,
                        f"session already exists: {rec.session_id}",
                        session_id=rec.session_id,
                    ) from exc
            return rec

    def get_session(self, session_id: str) -> Optional[DurableSessionRecord]:
        with self._lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM harness_session WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_session(row)

    def update_session(self, rec: DurableSessionRecord) -> DurableSessionRecord:
        with self._lock:
            rec.updated_at = time.time()
            rec.seal()
            with self._conn() as c:
                cur = c.execute(
                    """UPDATE harness_session SET
                      schema_version=?, harness_id=?, run_id=?, mission_id=?,
                      organization_id=?, workspace_id=?, actor_id=?,
                      projected_harness_state=?, authoritative_run_state_snapshot=?,
                      updated_at=?, last_event_sequence=?, last_event_id=?,
                      pending_tool_proposal_id=?, pending_execution_id=?,
                      pending_approval_reference=?, cancellation_requested_at=?,
                      cancellation_acknowledged_at=?, quarantine_reason=?, quarantined=?,
                      resource_usage_snapshot=?, terminal_outcome=?, retention_class=?,
                      expires_at=?, closed=?, integrity_hash=?
                    WHERE session_id=?""",
                    (
                        rec.schema_version,
                        rec.harness_id,
                        rec.run_id,
                        rec.mission_id,
                        rec.organization_id or "",
                        rec.workspace_id or "",
                        rec.actor_id or "",
                        rec.projected_harness_state,
                        rec.authoritative_run_state_snapshot or "",
                        rec.updated_at,
                        rec.last_event_sequence,
                        rec.last_event_id or "",
                        rec.pending_tool_proposal_id or "",
                        rec.pending_execution_id or "",
                        rec.pending_approval_reference or "",
                        rec.cancellation_requested_at or 0.0,
                        rec.cancellation_acknowledged_at or 0.0,
                        rec.quarantine_reason or "",
                        1 if rec.quarantined else 0,
                        json.dumps(rec.resource_usage_snapshot or {}, sort_keys=True),
                        rec.terminal_outcome or TerminalOutcome.NONE.value,
                        rec.retention_class or RetentionClass.ACTIVE.value,
                        rec.expires_at or 0.0,
                        1 if rec.closed else 0,
                        rec.integrity_hash,
                        rec.session_id,
                    ),
                )
                if cur.rowcount != 1:
                    raise HarnessError(
                        HarnessErrorCode.UNKNOWN_SESSION,
                        f"session not found for update: {rec.session_id}",
                        session_id=rec.session_id,
                    )
                c.commit()
            return rec

    def list_session_ids(self) -> List[str]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT session_id FROM harness_session ORDER BY created_at"
            ).fetchall()
            return [r["session_id"] for r in rows]

    # ── Events (transactional with watermark) ───────────────────────────────

    def append_event(
        self,
        session_id: str,
        event: DurableEventRecord,
        *,
        projected_harness_state: Optional[str] = None,
        authoritative_run_state_snapshot: Optional[str] = None,
        resource_usage_snapshot: Optional[Dict[str, Any]] = None,
        terminal_outcome: Optional[str] = None,
        quarantine_reason: Optional[str] = None,
        quarantined: Optional[bool] = None,
        closed: Optional[bool] = None,
        pending_execution_id: Optional[str] = None,
        pending_approval_reference: Optional[str] = None,
        pending_tool_proposal_id: Optional[str] = None,
        cancellation_requested_at: Optional[float] = None,
        cancellation_acknowledged_at: Optional[float] = None,
        retention_class: Optional[str] = None,
    ) -> Tuple[DurableEventRecord, DurableSessionRecord]:
        """Atomically insert event and advance session watermark / projection."""
        with self._lock:
            if event.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
                raise HarnessError(
                    HarnessErrorCode.INVALID_REQUEST,
                    f"unsupported event schema {event.schema_version}",
                    session_id=session_id,
                )
            try:
                event.payload = sanitize_payload(event.payload)
            except ValueError as exc:
                raise HarnessError(
                    HarnessErrorCode.PROTOCOL_VIOLATION,
                    str(exc),
                    session_id=session_id,
                ) from exc
            event.session_id = session_id
            event.seal()

            with self._conn() as c:
                c.execute("BEGIN IMMEDIATE")
                try:
                    srow = c.execute(
                        "SELECT * FROM harness_session WHERE session_id=?",
                        (session_id,),
                    ).fetchone()
                    if not srow:
                        raise HarnessError(
                            HarnessErrorCode.UNKNOWN_SESSION,
                            f"unknown session {session_id}",
                            session_id=session_id,
                        )
                    sess = self._row_to_session(srow)
                    if not sess.verify_integrity():
                        raise HarnessError(
                            HarnessErrorCode.PROTOCOL_VIOLATION,
                            "session integrity failure before append",
                            session_id=session_id,
                        )
                    if sess.closed and event.event_type != HarnessEventType.SESSION_CLOSED.value:
                        raise HarnessError(
                            HarnessErrorCode.TERMINAL_SESSION,
                            "cannot append event after close",
                            session_id=session_id,
                        )
                    if sess.quarantined:
                        raise HarnessError(
                            HarnessErrorCode.QUARANTINED,
                            sess.quarantine_reason or "session quarantined",
                            session_id=session_id,
                        )
                    # Scope bind
                    if event.organization_id and sess.organization_id and event.organization_id != sess.organization_id:
                        raise HarnessError(
                            HarnessErrorCode.SCOPE_MISMATCH,
                            "event organization mismatch",
                            session_id=session_id,
                        )
                    if event.workspace_id and sess.workspace_id and event.workspace_id != sess.workspace_id:
                        raise HarnessError(
                            HarnessErrorCode.SCOPE_MISMATCH,
                            "event workspace mismatch",
                            session_id=session_id,
                        )
                    if event.run_id and sess.run_id and event.run_id != sess.run_id:
                        raise HarnessError(
                            HarnessErrorCode.SCOPE_MISMATCH,
                            "event run_id mismatch",
                            session_id=session_id,
                        )
                    expected_seq = sess.last_event_sequence + 1
                    if event.sequence_number != expected_seq:
                        raise HarnessError(
                            HarnessErrorCode.PROTOCOL_VIOLATION,
                            f"sequence must be {expected_seq}, got {event.sequence_number}",
                            session_id=session_id,
                            details={
                                "expected": expected_seq,
                                "got": event.sequence_number,
                            },
                        )
                    # Insert event
                    c.execute(
                        """INSERT INTO harness_event(
                          event_id, session_id, sequence_number, event_type, harness_id,
                          timestamp, payload, turn_id, run_id, mission_id, organization_id,
                          workspace_id, correlation_id, causation_id, classification,
                          redaction_state, schema_version, integrity_hash
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        self._event_row(event),
                    )
                    # Update session watermark + optional projection fields
                    sess.last_event_sequence = event.sequence_number
                    sess.last_event_id = event.event_id
                    sess.updated_at = time.time()
                    if projected_harness_state is not None:
                        sess.projected_harness_state = projected_harness_state
                    if authoritative_run_state_snapshot is not None:
                        sess.authoritative_run_state_snapshot = authoritative_run_state_snapshot
                    if resource_usage_snapshot is not None:
                        sess.resource_usage_snapshot = dict(resource_usage_snapshot)
                    if terminal_outcome is not None:
                        sess.terminal_outcome = terminal_outcome
                    if quarantine_reason is not None:
                        sess.quarantine_reason = quarantine_reason
                    if quarantined is not None:
                        sess.quarantined = bool(quarantined)
                    if closed is not None:
                        sess.closed = bool(closed)
                    if pending_execution_id is not None:
                        sess.pending_execution_id = pending_execution_id
                    if pending_approval_reference is not None:
                        sess.pending_approval_reference = pending_approval_reference
                    if pending_tool_proposal_id is not None:
                        sess.pending_tool_proposal_id = pending_tool_proposal_id
                    if cancellation_requested_at is not None:
                        sess.cancellation_requested_at = float(cancellation_requested_at)
                    if cancellation_acknowledged_at is not None:
                        sess.cancellation_acknowledged_at = float(cancellation_acknowledged_at)
                    if retention_class is not None:
                        sess.retention_class = retention_class
                    sess.seal()
                    c.execute(
                        """UPDATE harness_session SET
                          projected_harness_state=?, authoritative_run_state_snapshot=?,
                          updated_at=?, last_event_sequence=?, last_event_id=?,
                          pending_tool_proposal_id=?, pending_execution_id=?,
                          pending_approval_reference=?, cancellation_requested_at=?,
                          cancellation_acknowledged_at=?, quarantine_reason=?, quarantined=?,
                          resource_usage_snapshot=?, terminal_outcome=?, retention_class=?,
                          expires_at=?, closed=?, integrity_hash=?
                        WHERE session_id=?""",
                        (
                            sess.projected_harness_state,
                            sess.authoritative_run_state_snapshot,
                            sess.updated_at,
                            sess.last_event_sequence,
                            sess.last_event_id,
                            sess.pending_tool_proposal_id,
                            sess.pending_execution_id,
                            sess.pending_approval_reference,
                            sess.cancellation_requested_at,
                            sess.cancellation_acknowledged_at,
                            sess.quarantine_reason,
                            1 if sess.quarantined else 0,
                            json.dumps(sess.resource_usage_snapshot, sort_keys=True),
                            sess.terminal_outcome,
                            sess.retention_class,
                            sess.expires_at,
                            1 if sess.closed else 0,
                            sess.integrity_hash,
                            session_id,
                        ),
                    )
                    c.commit()
                except Exception:
                    c.rollback()
                    raise
            return event, sess

    def list_events(
        self,
        session_id: str,
        *,
        after_seq: int = 0,
        until_seq: Optional[int] = None,
    ) -> List[DurableEventRecord]:
        with self._lock, self._conn() as c:
            if until_seq is None:
                rows = c.execute(
                    """SELECT * FROM harness_event
                       WHERE session_id=? AND sequence_number>?
                       ORDER BY sequence_number ASC""",
                    (session_id, after_seq),
                ).fetchall()
            else:
                rows = c.execute(
                    """SELECT * FROM harness_event
                       WHERE session_id=? AND sequence_number>? AND sequence_number<=?
                       ORDER BY sequence_number ASC""",
                    (session_id, after_seq, until_seq),
                ).fetchall()
            return [self._row_to_event(r) for r in rows]

    def event_count(self, session_id: str) -> int:
        with self._lock, self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM harness_event WHERE session_id=?",
                (session_id,),
            ).fetchone()
            return int(row["n"] if row else 0)

    # ── Replay (inspection only) ────────────────────────────────────────────

    def replay_timeline(self, session_id: str) -> Dict[str, Any]:
        """Deterministic inspection reconstruction — no execution side effects."""
        sess = self.get_session(session_id)
        if sess is None:
            raise HarnessError(
                HarnessErrorCode.UNKNOWN_SESSION,
                f"unknown session {session_id}",
                session_id=session_id,
            )
        events = self.list_events(session_id, after_seq=0)
        # Integrity
        if not sess.verify_integrity():
            return {
                "ok": False,
                "error": "session_integrity_failure",
                "session_id": session_id,
                "can_execute": False,
            }
        bad_events = [e.event_id for e in events if not e.verify_integrity()]
        if bad_events:
            return {
                "ok": False,
                "error": "event_integrity_failure",
                "bad_event_ids": bad_events,
                "session_id": session_id,
                "can_execute": False,
            }
        # Sequence continuity
        for i, e in enumerate(events, start=1):
            if e.sequence_number != i:
                return {
                    "ok": False,
                    "error": "sequence_gap",
                    "expected": i,
                    "got": e.sequence_number,
                    "session_id": session_id,
                    "can_execute": False,
                }
        if sess.last_event_sequence != len(events):
            return {
                "ok": False,
                "error": "watermark_mismatch",
                "watermark": sess.last_event_sequence,
                "events": len(events),
                "session_id": session_id,
                "can_execute": False,
            }
        return {
            "ok": True,
            "session_id": session_id,
            "schema_version": sess.schema_version,
            "projected_harness_state": sess.projected_harness_state,
            "authoritative_run_state_snapshot": sess.authoritative_run_state_snapshot,
            "terminal_outcome": sess.terminal_outcome,
            "quarantined": sess.quarantined,
            "quarantine_reason": sess.quarantine_reason,
            "pending_execution_id": sess.pending_execution_id,
            "pending_approval_reference": sess.pending_approval_reference,
            "cancellation_requested_at": sess.cancellation_requested_at,
            "cancellation_acknowledged_at": sess.cancellation_acknowledged_at,
            "resource_usage_snapshot": dict(sess.resource_usage_snapshot),
            "event_count": len(events),
            "events": [
                {
                    "sequence_number": e.sequence_number,
                    "event_id": e.event_id,
                    "event_type": e.event_type,
                    "payload": dict(e.payload),
                    "turn_id": e.turn_id,
                    "correlation_id": e.correlation_id,
                    "timestamp": e.timestamp,
                }
                for e in events
            ],
            "can_execute": False,  # inspection replay never executes
            "replay_kind": "inspection",
        }

    # ── Recovery ────────────────────────────────────────────────────────────

    def recover_session(
        self,
        session_id: str,
        *,
        authoritative_run_state: Optional[str] = None,
        execution_exists: Optional[bool] = None,
        approval_valid: Optional[bool] = None,
        now: Optional[float] = None,
    ) -> RecoveryResult:
        """Controlled recovery. Never auto-resumes model/tool work."""
        now = time.time() if now is None else now
        sess = self.get_session(session_id)
        if sess is None:
            return RecoveryResult(
                disposition=RecoveryDisposition.ABANDON_ORPHANED,
                reason="session_not_found",
            )
        if sess.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            return RecoveryResult(
                disposition=RecoveryDisposition.QUARANTINE_CORRUPT,
                session=sess,
                reason=f"unsupported_schema:{sess.schema_version}",
            )
        if not sess.verify_integrity():
            return RecoveryResult(
                disposition=RecoveryDisposition.QUARANTINE_CORRUPT,
                session=sess,
                reason="integrity_hash_mismatch",
            )
        events = self.list_events(session_id)
        for e in events:
            if not e.verify_integrity():
                return RecoveryResult(
                    disposition=RecoveryDisposition.QUARANTINE_CORRUPT,
                    session=sess,
                    reason=f"event_integrity:{e.event_id}",
                    events_count=len(events),
                )
        if sess.last_event_sequence != len(events):
            return RecoveryResult(
                disposition=RecoveryDisposition.QUARANTINE_CORRUPT,
                session=sess,
                reason="watermark_event_count_mismatch",
                events_count=len(events),
            )
        # Sequence continuity
        for i, e in enumerate(events, start=1):
            if e.sequence_number != i:
                return RecoveryResult(
                    disposition=RecoveryDisposition.QUARANTINE_CORRUPT,
                    session=sess,
                    reason="sequence_gap",
                    events_count=len(events),
                )

        if sess.quarantined:
            return RecoveryResult(
                disposition=RecoveryDisposition.QUARANTINE_CORRUPT
                if "corrupt" in (sess.quarantine_reason or "").lower()
                else RecoveryDisposition.QUARANTINE_STALE,
                session=sess,
                reason=sess.quarantine_reason or "already_quarantined",
                events_count=len(events),
                can_continue=False,
            )

        # Orphan: missing scope
        if not sess.run_id or not sess.session_id:
            return RecoveryResult(
                disposition=RecoveryDisposition.ABANDON_ORPHANED,
                session=sess,
                reason="missing_run_or_session",
                events_count=len(events),
            )

        # Authority conflict with RunState snapshot
        if authoritative_run_state is not None:
            snap = sess.authoritative_run_state_snapshot
            # Terminal conflict: durable cancelled vs run completed etc.
            term_run = authoritative_run_state in {
                RunState.CANCELLED.value,
                RunState.FAILED.value,
                RunState.COMPLETED.value,
                RunState.TIMED_OUT.value,
            }
            if (
                sess.terminal_outcome not in (TerminalOutcome.NONE.value, "")
                and term_run
                and snap
                and snap != authoritative_run_state
                and {snap, authoritative_run_state}
                == {RunState.CANCELLED.value, RunState.COMPLETED.value}
            ):
                return RecoveryResult(
                    disposition=RecoveryDisposition.QUARANTINE_AUTHORITY_CONFLICT,
                    session=sess,
                    reason=f"run_state_conflict:{snap}!={authoritative_run_state}",
                    events_count=len(events),
                )

        # Pending execution reconciliation
        if sess.pending_execution_id and execution_exists is False:
            return RecoveryResult(
                disposition=RecoveryDisposition.QUARANTINE_AUTHORITY_CONFLICT,
                session=sess,
                reason="pending_execution_missing",
                events_count=len(events),
            )
        if sess.pending_approval_reference and approval_valid is False:
            return RecoveryResult(
                disposition=RecoveryDisposition.QUARANTINE_AUTHORITY_CONFLICT,
                session=sess,
                reason="pending_approval_invalid",
                events_count=len(events),
            )

        # Stale detection
        age = now - float(sess.updated_at or sess.created_at)
        if age > self.stale_after_sec and sess.terminal_outcome in (
            TerminalOutcome.NONE.value,
            "",
        ):
            return RecoveryResult(
                disposition=RecoveryDisposition.QUARANTINE_STALE,
                session=sess,
                reason=f"stale_after_{int(age)}s",
                events_count=len(events),
                can_continue=False,
            )

        # Terminal / cancelled
        if sess.terminal_outcome == TerminalOutcome.CANCELLED.value or (
            sess.cancellation_acknowledged_at and sess.projected_harness_state == "CANCELLED"
        ):
            return RecoveryResult(
                disposition=RecoveryDisposition.RECOVER_CANCELLED,
                session=sess,
                reason="cancelled",
                events_count=len(events),
                can_continue=False,
            )
        if sess.terminal_outcome not in (TerminalOutcome.NONE.value, "") or sess.closed:
            return RecoveryResult(
                disposition=RecoveryDisposition.RECOVER_TERMINAL,
                session=sess,
                reason=sess.terminal_outcome or "closed",
                events_count=len(events),
                can_continue=False,
            )
        if sess.pending_approval_reference or sess.projected_harness_state in (
            "WAITING_FOR_APPROVAL",
        ):
            return RecoveryResult(
                disposition=RecoveryDisposition.RECOVER_WAITING_FOR_APPROVAL,
                session=sess,
                reason="awaiting_approval",
                events_count=len(events),
                can_continue=False,  # explicit action required
            )
        if sess.projected_harness_state in ("RUNNING", "WAITING_FOR_TOOL", "CANCELLING"):
            return RecoveryResult(
                disposition=RecoveryDisposition.RECOVER_RUNNING_AS_PAUSED,
                session=sess,
                reason="active_driver_not_restored",
                events_count=len(events),
                can_continue=False,  # no auto-resume
            )
        if sess.projected_harness_state in ("READY", "CREATED", "INITIALIZING"):
            return RecoveryResult(
                disposition=RecoveryDisposition.RECOVER_READY,
                session=sess,
                reason="ready",
                events_count=len(events),
                can_continue=False,  # still needs explicit controller rebind
            )
        return RecoveryResult(
            disposition=RecoveryDisposition.QUARANTINE_STALE,
            session=sess,
            reason=f"unhandled_state:{sess.projected_harness_state}",
            events_count=len(events),
        )

    def mark_quarantine(self, session_id: str, reason: str) -> DurableSessionRecord:
        sess = self.get_session(session_id)
        if sess is None:
            raise HarnessError(
                HarnessErrorCode.UNKNOWN_SESSION,
                f"unknown session {session_id}",
                session_id=session_id,
            )
        sess.quarantined = True
        sess.quarantine_reason = reason
        sess.retention_class = RetentionClass.QUARANTINED.value
        sess.terminal_outcome = TerminalOutcome.QUARANTINED.value
        return self.update_session(sess)

    def detect_stale_sessions(self, *, now: Optional[float] = None) -> List[str]:
        now = time.time() if now is None else now
        stale = []
        for sid in self.list_session_ids():
            sess = self.get_session(sid)
            if not sess or sess.closed or sess.terminal_outcome not in (
                TerminalOutcome.NONE.value,
                "",
            ):
                continue
            if now - float(sess.updated_at) > self.stale_after_sec:
                stale.append(sid)
        return stale

    def purge_expired(
        self,
        *,
        now: Optional[float] = None,
        allow_quarantined: bool = False,
    ) -> List[str]:
        """Purge expired sessions that have no pending approval/execution refs."""
        now = time.time() if now is None else now
        purged: List[str] = []
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT * FROM harness_session").fetchall()
            for row in rows:
                sess = self._row_to_session(row)
                if sess.expires_at and now < float(sess.expires_at):
                    continue
                if sess.pending_execution_id or sess.pending_approval_reference:
                    continue
                if sess.quarantined and not allow_quarantined:
                    continue
                if sess.retention_class == RetentionClass.CERTIFICATION_EVIDENCE.value:
                    continue
                c.execute("DELETE FROM harness_event WHERE session_id=?", (sess.session_id,))
                c.execute("DELETE FROM harness_session WHERE session_id=?", (sess.session_id,))
                purged.append(sess.session_id)
            c.commit()
        return purged

    # ── Helpers ─────────────────────────────────────────────────────────────

    def event_from_harness_event(self, ev: HarnessEvent) -> DurableEventRecord:
        try:
            payload = sanitize_payload(ev.safe_payload())
        except ValueError as exc:
            raise HarnessError(
                HarnessErrorCode.PROTOCOL_VIOLATION,
                str(exc),
                session_id=ev.session_id,
            ) from exc
        return DurableEventRecord(
            event_id=ev.event_id,
            session_id=ev.session_id,
            sequence_number=ev.sequence_number,
            event_type=ev.event_type.value if hasattr(ev.event_type, "value") else str(ev.event_type),
            harness_id=ev.harness_id,
            timestamp=float(ev.timestamp),
            payload=payload,
            turn_id=ev.turn_id or "",
            run_id=ev.run_id or "",
            mission_id=ev.mission_id or "",
            organization_id=ev.organization_id or "",
            workspace_id=ev.workspace_id or "",
            correlation_id=ev.correlation_id or "",
            causation_id=ev.causation_id or "",
            classification=ev.classification.value if hasattr(ev.classification, "value") else str(ev.classification),
            redaction_state=ev.redaction_state.value if hasattr(ev.redaction_state, "value") else str(ev.redaction_state),
        )

    def _session_row(self, rec: DurableSessionRecord) -> tuple:
        return (
            rec.session_id,
            rec.schema_version,
            rec.harness_id,
            rec.run_id,
            rec.mission_id,
            rec.organization_id or "",
            rec.workspace_id or "",
            rec.actor_id or "",
            rec.projected_harness_state,
            rec.authoritative_run_state_snapshot or "",
            rec.created_at,
            rec.updated_at,
            rec.last_event_sequence,
            rec.last_event_id or "",
            rec.pending_tool_proposal_id or "",
            rec.pending_execution_id or "",
            rec.pending_approval_reference or "",
            rec.cancellation_requested_at or 0.0,
            rec.cancellation_acknowledged_at or 0.0,
            rec.quarantine_reason or "",
            1 if rec.quarantined else 0,
            json.dumps(rec.resource_usage_snapshot or {}, sort_keys=True),
            rec.terminal_outcome or TerminalOutcome.NONE.value,
            rec.retention_class or RetentionClass.ACTIVE.value,
            rec.expires_at or 0.0,
            1 if rec.closed else 0,
            rec.integrity_hash,
        )

    def _event_row(self, rec: DurableEventRecord) -> tuple:
        return (
            rec.event_id,
            rec.session_id,
            rec.sequence_number,
            rec.event_type,
            rec.harness_id,
            rec.timestamp,
            json.dumps(rec.payload or {}, sort_keys=True),
            rec.turn_id or "",
            rec.run_id or "",
            rec.mission_id or "",
            rec.organization_id or "",
            rec.workspace_id or "",
            rec.correlation_id or "",
            rec.causation_id or "",
            rec.classification or "INTERNAL",
            rec.redaction_state or "NONE",
            rec.schema_version,
            rec.integrity_hash,
        )

    def _row_to_session(self, row: sqlite3.Row) -> DurableSessionRecord:
        return DurableSessionRecord(
            session_id=row["session_id"],
            schema_version=row["schema_version"],
            harness_id=row["harness_id"],
            run_id=row["run_id"],
            mission_id=row["mission_id"],
            organization_id=row["organization_id"],
            workspace_id=row["workspace_id"],
            actor_id=row["actor_id"],
            projected_harness_state=row["projected_harness_state"],
            authoritative_run_state_snapshot=row["authoritative_run_state_snapshot"],
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            last_event_sequence=int(row["last_event_sequence"]),
            last_event_id=row["last_event_id"] or "",
            pending_tool_proposal_id=row["pending_tool_proposal_id"] or "",
            pending_execution_id=row["pending_execution_id"] or "",
            pending_approval_reference=row["pending_approval_reference"] or "",
            cancellation_requested_at=float(row["cancellation_requested_at"] or 0),
            cancellation_acknowledged_at=float(row["cancellation_acknowledged_at"] or 0),
            quarantine_reason=row["quarantine_reason"] or "",
            quarantined=bool(row["quarantined"]),
            resource_usage_snapshot=json.loads(row["resource_usage_snapshot"] or "{}"),
            terminal_outcome=row["terminal_outcome"] or TerminalOutcome.NONE.value,
            retention_class=row["retention_class"] or RetentionClass.ACTIVE.value,
            expires_at=float(row["expires_at"] or 0),
            closed=bool(row["closed"]),
            integrity_hash=row["integrity_hash"] or "",
        )

    def _row_to_event(self, row: sqlite3.Row) -> DurableEventRecord:
        return DurableEventRecord(
            event_id=row["event_id"],
            session_id=row["session_id"],
            sequence_number=int(row["sequence_number"]),
            event_type=row["event_type"],
            harness_id=row["harness_id"],
            timestamp=float(row["timestamp"]),
            payload=json.loads(row["payload"] or "{}"),
            turn_id=row["turn_id"] or "",
            run_id=row["run_id"] or "",
            mission_id=row["mission_id"] or "",
            organization_id=row["organization_id"] or "",
            workspace_id=row["workspace_id"] or "",
            correlation_id=row["correlation_id"] or "",
            causation_id=row["causation_id"] or "",
            classification=row["classification"] or "INTERNAL",
            redaction_state=row["redaction_state"] or "NONE",
            schema_version=row["schema_version"],
            integrity_hash=row["integrity_hash"] or "",
        )
