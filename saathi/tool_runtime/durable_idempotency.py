"""M49.2 durable tool-call idempotency — SQLite, restart-safe.

Not a second event ledger. Additive store under data/tool_runtime/.
Replaces process-local IdempotencyStore for production paths while keeping
the same begin/complete/fail_release surface used by ToolExecutionService.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from saathi.tool_runtime.idempotency import fingerprint  # re-export stable API

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = ROOT / "data" / "tool_runtime" / "idempotency.db"

# Durable statuses
RESERVED = "RESERVED"
IN_PROGRESS = "IN_PROGRESS"
SUCCESS_CONFIRMED = "SUCCESS_CONFIRMED"
FAILURE_CONFIRMED = "FAILURE_CONFIRMED"
CANCELLED_CONFIRMED = "CANCELLED_CONFIRMED"
TIMEOUT_CONFIRMED = "TIMEOUT_CONFIRMED"
OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
REQUIRES_REVIEW = "REQUIRES_REVIEW"

TERMINAL = frozenset({
    SUCCESS_CONFIRMED,
    FAILURE_CONFIRMED,
    CANCELLED_CONFIRMED,
    TIMEOUT_CONFIRMED,
    OUTCOME_UNKNOWN,
    REQUIRES_REVIEW,
})

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_idempotency (
  scope TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  tool_id TEXT NOT NULL DEFAULT '',
  tool_version TEXT NOT NULL DEFAULT '',
  run_id TEXT NOT NULL DEFAULT '',
  call_id TEXT NOT NULL DEFAULT '',
  authority TEXT NOT NULL DEFAULT '',
  side_effect_class TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  attempt INTEGER NOT NULL DEFAULT 1,
  result_json TEXT NOT NULL DEFAULT '',
  error_code TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  lease_owner TEXT NOT NULL DEFAULT '',
  lease_expires_at REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (scope, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_tool_idemp_status ON tool_idempotency(status);
CREATE INDEX IF NOT EXISTS idx_tool_idemp_lease ON tool_idempotency(lease_expires_at);
"""

_lock = threading.RLock()


def _worker_id() -> str:
    return f"pid{os.getpid()}-{uuid.uuid4().hex[:8]}"


class DurableIdempotencyStore:
    """SQLite-backed idempotency with lease ownership and recovery."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        *,
        lease_sec: float = 120.0,
    ):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lease_sec = float(lease_sec)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    def _conn(self):
        c = sqlite3.connect(str(self.db_path), timeout=15, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=10000")
        return c

    def begin(
        self,
        scope: str,
        key: str,
        fp: str,
        *,
        tool_id: str = "",
        tool_version: str = "",
        run_id: str = "",
        call_id: str = "",
        authority: str = "",
        side_effect_class: str = "",
        attempt: int = 1,
        owner: str | None = None,
    ) -> dict:
        owner = owner or _worker_id()
        now = time.time()
        with _lock, self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                row = c.execute(
                    "SELECT * FROM tool_idempotency WHERE scope=? AND idempotency_key=?",
                    (scope, key),
                ).fetchone()
                if row is None:
                    c.execute(
                        """INSERT INTO tool_idempotency(
                            scope, idempotency_key, fingerprint, tool_id, tool_version,
                            run_id, call_id, authority, side_effect_class, status, attempt,
                            result_json, error_code, created_at, updated_at,
                            lease_owner, lease_expires_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            scope,
                            key,
                            fp,
                            tool_id,
                            tool_version,
                            run_id,
                            call_id,
                            authority,
                            side_effect_class,
                            IN_PROGRESS,
                            attempt,
                            "",
                            "",
                            now,
                            now,
                            owner,
                            now + self.lease_sec,
                        ),
                    )
                    c.execute("COMMIT")
                    return {
                        "status": "acquired",
                        "fingerprint": fp,
                        "owner": owner,
                        "durable_status": IN_PROGRESS,
                    }

                if row["fingerprint"] != fp:
                    c.execute("COMMIT")
                    return {
                        "status": "conflict",
                        "fingerprint": row["fingerprint"],
                        "message": "same key different fingerprint",
                        "durable_status": row["status"],
                    }

                st = row["status"]
                if st == SUCCESS_CONFIRMED and row["result_json"]:
                    c.execute("COMMIT")
                    return {
                        "status": "replay",
                        "fingerprint": fp,
                        "result": json.loads(row["result_json"]),
                        "durable_status": st,
                    }

                if st in TERMINAL and st != SUCCESS_CONFIRMED:
                    # allow safe re-acquire only for pure failures without mutation uncertainty
                    if st in (FAILURE_CONFIRMED, CANCELLED_CONFIRMED) and side_effect_class in (
                        "",
                        "NO_SIDE_EFFECT",
                        "LOCAL_REVERSIBLE",
                    ):
                        c.execute(
                            """UPDATE tool_idempotency SET status=?, attempt=?, call_id=?,
                               lease_owner=?, lease_expires_at=?, updated_at=?, error_code='',
                               result_json='' WHERE scope=? AND idempotency_key=?""",
                            (
                                IN_PROGRESS,
                                attempt,
                                call_id,
                                owner,
                                now + self.lease_sec,
                                now,
                                scope,
                                key,
                            ),
                        )
                        c.execute("COMMIT")
                        return {
                            "status": "acquired",
                            "fingerprint": fp,
                            "owner": owner,
                            "durable_status": IN_PROGRESS,
                            "recovered_from": st,
                        }
                    c.execute("COMMIT")
                    return {
                        "status": "replay",
                        "fingerprint": fp,
                        "result": json.loads(row["result_json"] or "{}") or {
                            "status": "failed",
                            "outcome_class": st,
                            "error_code": row["error_code"],
                            "safe_message": "prior terminal outcome",
                            "tool_id": row["tool_id"],
                            "tool_version": row["tool_version"],
                            "call_id": row["call_id"],
                            "data": {},
                            "retryable": False,
                            "side_effect_confirmed": False,
                            "cancellation_confirmed": st == CANCELLED_CONFIRMED,
                            "timeout_detected": st == TIMEOUT_CONFIRMED,
                            "evidence_references": [],
                            "started_at": row["created_at"],
                            "finished_at": row["updated_at"],
                            "duration_ms": 0,
                            "events": [],
                            "retry_class": "",
                            "authority_class": row["authority"],
                            "side_effect_class": row["side_effect_class"],
                            "adapter_invoked": False,
                        },
                        "durable_status": st,
                    }

                # IN_PROGRESS / RESERVED
                lease_exp = float(row["lease_expires_at"] or 0)
                lease_owner = row["lease_owner"] or ""
                if lease_owner and lease_exp > now and lease_owner != owner:
                    c.execute("COMMIT")
                    return {
                        "status": "in_progress",
                        "fingerprint": fp,
                        "owner": lease_owner,
                        "durable_status": st,
                    }

                # stale or same owner — take over
                c.execute(
                    """UPDATE tool_idempotency SET status=?, lease_owner=?, lease_expires_at=?,
                       updated_at=?, call_id=?, attempt=? WHERE scope=? AND idempotency_key=?""",
                    (
                        IN_PROGRESS,
                        owner,
                        now + self.lease_sec,
                        now,
                        call_id,
                        attempt,
                        scope,
                        key,
                    ),
                )
                c.execute("COMMIT")
                return {
                    "status": "acquired",
                    "fingerprint": fp,
                    "owner": owner,
                    "durable_status": IN_PROGRESS,
                    "stale_takeover": lease_exp <= now,
                }
            except Exception:
                try:
                    c.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def complete(self, scope: str, key: str, result: dict) -> None:
        now = time.time()
        outcome = str(result.get("outcome_class") or "")
        if outcome in ("SUCCESS_CONFIRMED",):
            st = SUCCESS_CONFIRMED
        elif outcome in ("CANCELLED_CONFIRMED",):
            st = CANCELLED_CONFIRMED
        elif outcome in ("TIMEOUT_CONFIRMED",):
            st = TIMEOUT_CONFIRMED
        elif outcome in ("SIDE_EFFECT_UNKNOWN", "TOOL_OUTCOME_UNKNOWN", "REQUIRES_REVIEW"):
            st = OUTCOME_UNKNOWN if "UNKNOWN" in outcome else REQUIRES_REVIEW
        elif outcome in ("PROHIBITED", "BLOCKED"):
            st = FAILURE_CONFIRMED
        else:
            st = FAILURE_CONFIRMED if result.get("error_code") else SUCCESS_CONFIRMED
        # bound payload
        raw = json.dumps(result, default=str)
        if len(raw) > 50_000:
            raw = json.dumps(
                {
                    "status": result.get("status"),
                    "outcome_class": result.get("outcome_class"),
                    "error_code": result.get("error_code"),
                    "safe_message": (result.get("safe_message") or "")[:500],
                    "tool_id": result.get("tool_id"),
                    "tool_version": result.get("tool_version"),
                    "call_id": result.get("call_id"),
                    "data": {"_truncated": True},
                    "adapter_invoked": result.get("adapter_invoked"),
                    "authority_class": result.get("authority_class"),
                    "side_effect_class": result.get("side_effect_class"),
                    "retryable": False,
                    "side_effect_confirmed": result.get("side_effect_confirmed"),
                    "cancellation_confirmed": result.get("cancellation_confirmed"),
                    "timeout_detected": result.get("timeout_detected"),
                    "evidence_references": result.get("evidence_references") or [],
                    "started_at": result.get("started_at"),
                    "finished_at": result.get("finished_at"),
                    "duration_ms": result.get("duration_ms"),
                    "events": result.get("events") or [],
                    "retry_class": result.get("retry_class") or "",
                },
                default=str,
            )
        with _lock, self._conn() as c:
            c.execute(
                """UPDATE tool_idempotency SET status=?, result_json=?, error_code=?,
                   updated_at=?, lease_owner='', lease_expires_at=0
                   WHERE scope=? AND idempotency_key=?""",
                (
                    st,
                    raw,
                    str(result.get("error_code") or ""),
                    now,
                    scope,
                    key,
                ),
            )

    def fail_release(self, scope: str, key: str, *, error_code: str = "") -> None:
        """Release safe in-progress (read-only/reversible) for retry; mutations → OUTCOME_UNKNOWN."""
        now = time.time()
        with _lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM tool_idempotency WHERE scope=? AND idempotency_key=?",
                (scope, key),
            ).fetchone()
            if not row or row["status"] not in (IN_PROGRESS, RESERVED):
                return
            se = row["side_effect_class"] or ""
            if se in ("", "NO_SIDE_EFFECT", "LOCAL_REVERSIBLE"):
                c.execute(
                    "DELETE FROM tool_idempotency WHERE scope=? AND idempotency_key=?",
                    (scope, key),
                )
            else:
                c.execute(
                    """UPDATE tool_idempotency SET status=?, error_code=?, updated_at=?,
                       lease_owner='', lease_expires_at=0 WHERE scope=? AND idempotency_key=?""",
                    (OUTCOME_UNKNOWN, error_code or "TOOL_OUTCOME_UNKNOWN", now, scope, key),
                )

    def heartbeat(self, scope: str, key: str, owner: str) -> bool:
        now = time.time()
        with _lock, self._conn() as c:
            cur = c.execute(
                """UPDATE tool_idempotency SET lease_expires_at=?, updated_at=?
                   WHERE scope=? AND idempotency_key=? AND lease_owner=? AND status=?""",
                (now + self.lease_sec, now, scope, key, owner, IN_PROGRESS),
            )
            return cur.rowcount > 0

    def list_stale(self, *, now: float | None = None, limit: int = 100) -> list[dict]:
        now = now if now is not None else time.time()
        with _lock, self._conn() as c:
            rows = c.execute(
                """SELECT * FROM tool_idempotency
                   WHERE status IN (?,?) AND lease_expires_at > 0 AND lease_expires_at < ?
                   ORDER BY lease_expires_at ASC LIMIT ?""",
                (IN_PROGRESS, RESERVED, now, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def reconcile_stale(self, *, now: float | None = None) -> dict:
        """Classify stale leases: safe retry vs REQUIRES_REVIEW."""
        now = now if now is not None else time.time()
        events = []
        recovered = 0
        review = 0
        for row in self.list_stale(now=now):
            se = row.get("side_effect_class") or ""
            scope, key = row["scope"], row["idempotency_key"]
            if se in ("", "NO_SIDE_EFFECT", "LOCAL_REVERSIBLE") or (
                se and "FINANCIAL" not in se and row.get("status") == IN_PROGRESS
                and se == "NO_SIDE_EFFECT"
            ):
                # safe: delete so next begin can re-acquire
                with _lock, self._conn() as c:
                    c.execute(
                        "DELETE FROM tool_idempotency WHERE scope=? AND idempotency_key=? AND status IN (?,?)",
                        (scope, key, IN_PROGRESS, RESERVED),
                    )
                recovered += 1
                events.append({"scope": scope, "key": key, "action": "released_for_retry", "side_effect": se})
            elif "FINANCIAL" in se:
                with _lock, self._conn() as c:
                    c.execute(
                        """UPDATE tool_idempotency SET status=?, error_code=?, updated_at=?,
                           lease_owner='', lease_expires_at=0 WHERE scope=? AND idempotency_key=?""",
                        (REQUIRES_REVIEW, "TOOL_FINANCIAL_EXECUTION_PROHIBITED", now, scope, key),
                    )
                review += 1
                events.append({"scope": scope, "key": key, "action": "financial_review", "side_effect": se})
            else:
                with _lock, self._conn() as c:
                    c.execute(
                        """UPDATE tool_idempotency SET status=?, error_code=?, updated_at=?,
                           lease_owner='', lease_expires_at=0 WHERE scope=? AND idempotency_key=?""",
                        (OUTCOME_UNKNOWN, "TOOL_OUTCOME_UNKNOWN", now, scope, key),
                    )
                review += 1
                events.append({"scope": scope, "key": key, "action": "outcome_unknown", "side_effect": se})
        return {
            "ok": True,
            "recovered": recovered,
            "requires_review": review,
            "events": events,
        }


_DEFAULT: DurableIdempotencyStore | None = None


def default_durable_idempotency_store() -> DurableIdempotencyStore:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = DurableIdempotencyStore()
    return _DEFAULT


def reset_durable_idempotency_for_tests(tmp_path: Path | None = None) -> DurableIdempotencyStore:
    global _DEFAULT
    if tmp_path is None:
        import tempfile

        tmp_path = Path(tempfile.mkdtemp()) / "idemp.db"
    _DEFAULT = DurableIdempotencyStore(tmp_path)
    return _DEFAULT
