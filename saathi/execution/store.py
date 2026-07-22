"""M17.22 durable store for universal ExecutionGateway records.

SQLite, restart-safe, secret-free. Supports idempotency lookup by digest /
idempotency_key and CAS-style status transitions.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from saathi.execution.execution_state import (
    ExecutionState,
    assert_transition,
    is_terminal,
)
from saathi.execution.record import ExecutionRecord, safe_summary

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = ROOT / "data" / "execution_gateway" / "executions.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS execution_record (
  execution_id TEXT PRIMARY KEY,
  tool_intent_digest TEXT NOT NULL,
  intent_id TEXT NOT NULL,
  actor TEXT NOT NULL,
  target TEXT NOT NULL,
  family TEXT NOT NULL DEFAULT 'connector',
  created REAL NOT NULL,
  started REAL,
  finished REAL,
  status TEXT NOT NULL,
  approval TEXT NOT NULL DEFAULT 'none',
  risk TEXT NOT NULL DEFAULT 'medium',
  evidence_id TEXT DEFAULT '',
  result_summary TEXT DEFAULT '',
  failure_category TEXT DEFAULT '',
  retry_count INTEGER NOT NULL DEFAULT 0,
  retryable INTEGER NOT NULL DEFAULT 0,
  next_retry_at REAL,
  ledger_run_id TEXT DEFAULT '',
  security_event_id TEXT DEFAULT '',
  approval_id TEXT DEFAULT '',
  idempotency_key TEXT DEFAULT '',
  correlation_id TEXT DEFAULT '',
  transition_log TEXT NOT NULL DEFAULT '[]',
  metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_exec_digest ON execution_record(tool_intent_digest);
CREATE INDEX IF NOT EXISTS idx_exec_idem ON execution_record(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_exec_status ON execution_record(status);
CREATE INDEX IF NOT EXISTS idx_exec_created ON execution_record(created);

CREATE TABLE IF NOT EXISTS approval_binding (
  approval_id TEXT PRIMARY KEY,
  tool_intent_digest TEXT NOT NULL,
  actor TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'approved',
  created REAL NOT NULL,
  expires_at REAL,
  used INTEGER NOT NULL DEFAULT 0,
  max_uses INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_appr_digest ON approval_binding(tool_intent_digest);
"""

_lock = threading.RLock()


class ExecutionStore:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self):
        c = sqlite3.connect(str(self.db_path), timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=8000")
        return c

    def insert(self, rec: ExecutionRecord) -> ExecutionRecord:
        payload = rec.to_row_payload()
        with _lock, self._conn() as c:
            c.execute(
                """INSERT INTO execution_record (
                    execution_id, tool_intent_digest, intent_id, actor, target, family,
                    created, started, finished, status, approval, risk, evidence_id,
                    result_summary, failure_category, retry_count, retryable, next_retry_at,
                    ledger_run_id, security_event_id, approval_id, idempotency_key,
                    correlation_id, transition_log, metadata
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    payload["execution_id"], payload["tool_intent_digest"],
                    payload["intent_id"], payload["actor"], payload["target"],
                    payload["family"], payload["created"], payload["started"],
                    payload["finished"], payload["status"], payload["approval"],
                    payload["risk"], payload["evidence_id"],
                    safe_summary(payload["result_summary"]),
                    payload["failure_category"], payload["retry_count"],
                    1 if payload["retryable"] else 0, payload["next_retry_at"],
                    payload["ledger_run_id"], payload["security_event_id"],
                    payload["approval_id"], payload["idempotency_key"],
                    payload["correlation_id"],
                    json.dumps(payload["transition_log"] or []),
                    json.dumps(payload["metadata"] or {}),
                ),
            )
        return rec

    def get(self, execution_id: str) -> Optional[ExecutionRecord]:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM execution_record WHERE execution_id=?",
                (execution_id,),
            ).fetchone()
        return ExecutionRecord.from_row(dict(row)) if row else None

    def find_by_idempotency(self, key: str) -> Optional[ExecutionRecord]:
        if not key:
            return None
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM execution_record WHERE idempotency_key=? "
                "ORDER BY created DESC LIMIT 1",
                (key,),
            ).fetchone()
        return ExecutionRecord.from_row(dict(row)) if row else None

    def find_by_digest(self, digest: str, *, terminal_only: bool = False) -> Optional[ExecutionRecord]:
        if not digest:
            return None
        with self._conn() as c:
            if terminal_only:
                row = c.execute(
                    "SELECT * FROM execution_record WHERE tool_intent_digest=? "
                    "AND status IN ('succeeded','failed','denied','cancelled','expired') "
                    "ORDER BY created DESC LIMIT 1",
                    (digest,),
                ).fetchone()
            else:
                row = c.execute(
                    "SELECT * FROM execution_record WHERE tool_intent_digest=? "
                    "ORDER BY created DESC LIMIT 1",
                    (digest,),
                ).fetchone()
        return ExecutionRecord.from_row(dict(row)) if row else None

    def transition(
        self,
        execution_id: str,
        to_state: ExecutionState | str,
        *,
        reason: str = "",
        extra: Optional[dict] = None,
    ) -> ExecutionRecord:
        to_s = ExecutionState(to_state) if not isinstance(to_state, ExecutionState) else to_state
        with _lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM execution_record WHERE execution_id=?",
                (execution_id,),
            ).fetchone()
            if not row:
                raise KeyError(f"unknown execution_id {execution_id}")
            rec = ExecutionRecord.from_row(dict(row))
            from_s = ExecutionState(rec.status)
            assert_transition(from_s, to_s)
            now = time.time()
            log = list(rec.transition_log or [])
            log.append({
                "from": from_s.value,
                "to": to_s.value,
                "at": now,
                "reason": safe_summary(reason, maxlen=120),
            })
            started = rec.started
            finished = rec.finished
            if to_s == ExecutionState.RUNNING and started is None:
                started = now
            if is_terminal(to_s):
                finished = now
            fields = {
                "status": to_s.value,
                "started": started,
                "finished": finished,
                "transition_log": json.dumps(log),
            }
            if extra:
                for k, v in extra.items():
                    if k in (
                        "approval", "risk", "evidence_id", "result_summary",
                        "failure_category", "retry_count", "retryable",
                        "next_retry_at", "ledger_run_id", "security_event_id",
                        "approval_id",
                    ):
                        if k == "result_summary":
                            v = safe_summary(v)
                        if k == "retryable":
                            v = 1 if v else 0
                        fields[k] = v
            sets = ", ".join(f"{k}=?" for k in fields)
            c.execute(
                f"UPDATE execution_record SET {sets} WHERE execution_id=?",
                (*fields.values(), execution_id),
            )
            row2 = c.execute(
                "SELECT * FROM execution_record WHERE execution_id=?",
                (execution_id,),
            ).fetchone()
        return ExecutionRecord.from_row(dict(row2))

    def update_fields(self, execution_id: str, **fields) -> ExecutionRecord:
        if not fields:
            rec = self.get(execution_id)
            if not rec:
                raise KeyError(execution_id)
            return rec
        if "result_summary" in fields:
            fields["result_summary"] = safe_summary(fields["result_summary"])
        if "retryable" in fields:
            fields["retryable"] = 1 if fields["retryable"] else 0
        if "metadata" in fields and not isinstance(fields["metadata"], str):
            fields["metadata"] = json.dumps(fields["metadata"])
        if "transition_log" in fields and not isinstance(fields["transition_log"], str):
            fields["transition_log"] = json.dumps(fields["transition_log"])
        with _lock, self._conn() as c:
            sets = ", ".join(f"{k}=?" for k in fields)
            c.execute(
                f"UPDATE execution_record SET {sets} WHERE execution_id=?",
                (*fields.values(), execution_id),
            )
        rec = self.get(execution_id)
        if not rec:
            raise KeyError(execution_id)
        return rec

    # ── approval bindings (reuse store; not a new approval engine) ─────────
    def bind_approval(
        self,
        approval_id: str,
        *,
        digest: str,
        actor: str,
        expires_at: float | None = None,
        max_uses: int = 1,
    ) -> dict:
        now = time.time()
        with _lock, self._conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO approval_binding
                   (approval_id, tool_intent_digest, actor, status, created, expires_at, used, max_uses)
                   VALUES (?,?,?,?,?,?,0,?)""",
                (approval_id, digest, actor, "approved", now, expires_at, max_uses),
            )
        return {
            "approval_id": approval_id,
            "tool_intent_digest": digest,
            "actor": actor,
            "expires_at": expires_at,
        }

    def find_valid_approval(self, digest: str, *, actor: str = "") -> Optional[dict]:
        now = time.time()
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM approval_binding WHERE tool_intent_digest=? AND status='approved'",
                (digest,),
            ).fetchall()
        for row in rows:
            d = dict(row)
            if actor and d.get("actor") and d["actor"] != actor:
                continue
            if d.get("expires_at") and float(d["expires_at"]) < now:
                continue
            if int(d.get("used") or 0) >= int(d.get("max_uses") or 1):
                continue
            return d
        return None

    def consume_approval(self, approval_id: str) -> bool:
        with _lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM approval_binding WHERE approval_id=?",
                (approval_id,),
            ).fetchone()
            if not row:
                return False
            d = dict(row)
            if int(d.get("used") or 0) >= int(d.get("max_uses") or 1):
                return False
            c.execute(
                "UPDATE approval_binding SET used=used+1 WHERE approval_id=?",
                (approval_id,),
            )
            return True

    def reject_approval(self, approval_id: str) -> None:
        with _lock, self._conn() as c:
            c.execute(
                "UPDATE approval_binding SET status='rejected' WHERE approval_id=?",
                (approval_id,),
            )

    # ── observability ─────────────────────────────────────────────────────
    def metrics(self, *, since: float | None = None, limit_failures: int = 20) -> dict:
        since = since if since is not None else time.time() - 86400
        with self._conn() as c:
            rows = c.execute(
                "SELECT status, COUNT(*) AS n, AVG("
                "CASE WHEN started IS NOT NULL AND finished IS NOT NULL "
                "THEN finished-started ELSE NULL END) AS avg_rt, "
                "SUM(retry_count) AS retries "
                "FROM execution_record WHERE created>=? GROUP BY status",
                (since,),
            ).fetchall()
            by_status = {r["status"]: int(r["n"]) for r in rows}
            avg_runtime = 0.0
            total_retries = 0
            n_rt = 0
            for r in rows:
                if r["avg_rt"] is not None:
                    avg_runtime += float(r["avg_rt"]) * int(r["n"])
                    n_rt += int(r["n"])
                total_retries += int(r["retries"] or 0)
            avg_runtime = (avg_runtime / n_rt) if n_rt else 0.0
            fails = c.execute(
                "SELECT execution_id, target, status, failure_category, result_summary, "
                "created, retry_count FROM execution_record "
                "WHERE created>=? AND status IN ('failed','denied') "
                "ORDER BY created DESC LIMIT ?",
                (since, limit_failures),
            ).fetchall()
            pending_appr = c.execute(
                "SELECT COUNT(*) AS n FROM execution_record "
                "WHERE status='approval_required' AND created>=?",
                (since,),
            ).fetchone()["n"]
            running = by_status.get("running", 0)
            queued = by_status.get("queued", 0)
        return {
            "running": running,
            "queued": queued,
            "succeeded": by_status.get("succeeded", 0),
            "failed": by_status.get("failed", 0),
            "denied": by_status.get("denied", 0),
            "approval_required": int(pending_appr),
            "cancelled": by_status.get("cancelled", 0),
            "expired": by_status.get("expired", 0),
            "by_status": by_status,
            "average_runtime_sec": round(avg_runtime, 4),
            "retry_count": total_retries,
            "recent_failures": [
                {
                    "execution_id": f["execution_id"],
                    "target": f["target"],
                    "status": f["status"],
                    "failure_category": f["failure_category"],
                    "result_summary": safe_summary(f["result_summary"]),
                    "created": f["created"],
                    "retry_count": f["retry_count"],
                }
                for f in fails
            ],
            "window_start": since,
        }

    def list_recent(self, *, limit: int = 50, status: str | None = None) -> list[ExecutionRecord]:
        with self._conn() as c:
            if status:
                rows = c.execute(
                    "SELECT * FROM execution_record WHERE status=? ORDER BY created DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM execution_record ORDER BY created DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [ExecutionRecord.from_row(dict(r)) for r in rows]

    def recover_stale_running(self, *, older_than_sec: float = 3600) -> list[str]:
        """Restart safety: mark long-running as failed (non-retryable) if stuck."""
        cutoff = time.time() - older_than_sec
        recovered = []
        with _lock, self._conn() as c:
            rows = c.execute(
                "SELECT execution_id FROM execution_record "
                "WHERE status IN ('running','queued') AND created<?",
                (cutoff,),
            ).fetchall()
        for r in rows:
            eid = r["execution_id"]
            try:
                self.transition(
                    eid,
                    ExecutionState.FAILED,
                    reason="restart_recovery_stale",
                    extra={
                        "failure_category": "stale_after_restart",
                        "result_summary": "recovered after restart; marked failed",
                        "retryable": False,
                    },
                )
                recovered.append(eid)
            except Exception:
                # may already be terminal / race — ignore
                pass
        return recovered


_DEFAULT: Optional[ExecutionStore] = None
_DEFAULT_LOCK = threading.Lock()


def default_store(db_path: Path | str | None = None) -> ExecutionStore:
    global _DEFAULT
    if db_path is not None:
        return ExecutionStore(db_path)
    with _DEFAULT_LOCK:
        if _DEFAULT is None:
            _DEFAULT = ExecutionStore()
        return _DEFAULT


def reset_default_store() -> None:
    global _DEFAULT
    with _DEFAULT_LOCK:
        _DEFAULT = None
