"""T-NEXT-4 — execution integrity: submission disposition and reconciliation authority.

This module adds the two safety properties the existing paper trading chain did
not have:

1. **Submission disposition.** An ambiguous submission outcome must never be
   retried automatically. Only an outcome that is *provably* untransmitted is
   safe to retry; everything else reconciles first or stops.

2. **ReconciliationAuthority.** A deterministic verdict on whether OMS, external
   adapter, and canonical ledger state agree. It certifies consistency; it never
   authorises a trade. Anything short of RECONCILED denies readiness, with one
   explicit exception: TEMPORARILY_PENDING may be opted into via
   ``allow_execution_while_pending=True``. It defaults to denying. MISMATCH,
   UNKNOWN, and DATA_INSUFFICIENT deny unconditionally and cannot be opted into.

Authority boundary — this module:
  * holds no execution authority; it cannot submit, cancel, or approve anything
  * holds no risk authority; it never overrides PortfolioRiskEngine
  * holds no veto authority over Trading Guardian; it only denies readiness
  * never mutates the canonical ledger
  * has no LLM dependency and no network dependency

Deterministic: no randomness, no implicit clock in any decision path. Timestamps
are recorded for evidence only and are injectable for tests.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time as _time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = [
    "SubmissionOutcome",
    "RetryDisposition",
    "classify_submission",
    "SubmissionAttemptStore",
    "ExecutionReadiness",
    "readiness_permits",
    "OmsSnapshot",
    "ExternalOrderSnapshot",
    "LedgerSnapshot",
    "ReconciliationVerdict",
    "ReconciliationAuthority",
]


# ══════════════════════════════════════════════════════════════════════════
# Phase 4 — submission outcome classification
# ══════════════════════════════════════════════════════════════════════════

class SubmissionOutcome(str, Enum):
    """What the execution adapter told us about a submission attempt."""

    ACKNOWLEDGED = "ACKNOWLEDGED"                # broker confirmed receipt
    REJECTED = "REJECTED"                        # broker refused; definitely not working
    TIMEOUT_BEFORE_SEND = "TIMEOUT_BEFORE_SEND"  # provably never left this process
    TIMEOUT_AFTER_SEND = "TIMEOUT_AFTER_SEND"    # may or may not have been received
    CONNECTION_LOST = "CONNECTION_LOST"          # may or may not have been received
    UNKNOWN = "UNKNOWN"                          # no information at all


class RetryDisposition(str, Enum):
    """What we are permitted to do next."""

    SAFE_TO_RETRY = "SAFE_TO_RETRY"
    DO_NOT_RETRY = "DO_NOT_RETRY"
    RECONCILE_FIRST = "RECONCILE_FIRST"


# Only an outcome that proves the request never reached the wire is retryable.
# Everything else — including anything unrecognised — reconciles first.
_DISPOSITION: dict[SubmissionOutcome, RetryDisposition] = {
    SubmissionOutcome.ACKNOWLEDGED: RetryDisposition.DO_NOT_RETRY,
    SubmissionOutcome.REJECTED: RetryDisposition.DO_NOT_RETRY,
    SubmissionOutcome.TIMEOUT_BEFORE_SEND: RetryDisposition.SAFE_TO_RETRY,
    SubmissionOutcome.TIMEOUT_AFTER_SEND: RetryDisposition.RECONCILE_FIRST,
    SubmissionOutcome.CONNECTION_LOST: RetryDisposition.RECONCILE_FIRST,
    SubmissionOutcome.UNKNOWN: RetryDisposition.RECONCILE_FIRST,
}


def classify_submission(outcome: SubmissionOutcome | str | None) -> RetryDisposition:
    """Map a submission outcome to what we may do next. Fails closed.

    An outcome this function does not recognise is treated as UNKNOWN, never as
    retryable. A future adapter that invents a new outcome therefore cannot
    accidentally unlock automatic resubmission.
    """
    try:
        key = outcome if isinstance(outcome, SubmissionOutcome) else SubmissionOutcome(outcome)
    except (ValueError, KeyError, TypeError):
        return RetryDisposition.RECONCILE_FIRST
    return _DISPOSITION.get(key, RetryDisposition.RECONCILE_FIRST)


_ATTEMPT_SCHEMA = """
CREATE TABLE IF NOT EXISTS submission_attempts (
    request_id          TEXT PRIMARY KEY,
    client_order_id     TEXT NOT NULL,
    idempotency_key     TEXT NOT NULL,
    attempt             INTEGER NOT NULL,
    outcome             TEXT NOT NULL,
    disposition         TEXT NOT NULL,
    broker_adapter_ref  TEXT NOT NULL DEFAULT '',
    correlation_id      TEXT NOT NULL DEFAULT '',
    evidence_ref        TEXT NOT NULL DEFAULT '',
    recorded_at         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_attempts_key ON submission_attempts(idempotency_key);

CREATE TABLE IF NOT EXISTS submission_reconciliations (
    idempotency_key       TEXT PRIMARY KEY,
    external_order_found  INTEGER NOT NULL,
    resolved_outcome      TEXT NOT NULL,
    evidence_ref          TEXT NOT NULL DEFAULT '',
    recorded_at           REAL NOT NULL
);
"""


class SubmissionAttemptStore:
    """Durable, append-only record of every submission attempt.

    The store is the authority on whether a given idempotency key may be
    submitted again. It answers three questions and nothing else:
    may_submit / already_submitted / requires_reconciliation.
    """

    def __init__(self, path: str | Path, *, clock=None) -> None:
        self._path = str(path)
        self._clock = clock or _time.time
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_ATTEMPT_SCHEMA)
        self._conn.commit()

    # ── writes ────────────────────────────────────────────────────────────

    def record(
        self,
        *,
        request_id: str,
        client_order_id: str,
        idempotency_key: str,
        attempt: int,
        outcome: SubmissionOutcome | str,
        broker_adapter_ref: str = "",
        correlation_id: str = "",
        evidence_ref: str = "",
    ) -> dict[str, Any]:
        """Record one attempt. Idempotent on ``request_id``."""
        disposition = classify_submission(outcome)
        outcome_value = outcome.value if isinstance(outcome, SubmissionOutcome) else str(outcome)
        row = {
            "request_id": request_id,
            "client_order_id": client_order_id,
            "idempotency_key": idempotency_key,
            "attempt": int(attempt),
            "outcome": outcome_value,
            "disposition": disposition.value,
            "broker_adapter_ref": broker_adapter_ref,
            "correlation_id": correlation_id,
            "evidence_ref": evidence_ref,
            "recorded_at": float(self._clock()),
        }
        # Atomic idempotency on request_id. A check-then-insert would race: two
        # concurrent callers could both pass the SELECT and the second would
        # raise IntegrityError instead of returning the existing row.
        with self._lock:
            self._conn.execute(
                "INSERT INTO submission_attempts "
                "(request_id, client_order_id, idempotency_key, attempt, outcome, disposition,"
                " broker_adapter_ref, correlation_id, evidence_ref, recorded_at) "
                "VALUES (:request_id, :client_order_id, :idempotency_key, :attempt, :outcome,"
                " :disposition, :broker_adapter_ref, :correlation_id, :evidence_ref, :recorded_at) "
                "ON CONFLICT(request_id) DO NOTHING",
                row,
            )
            self._conn.commit()
            stored = self._conn.execute(
                "SELECT * FROM submission_attempts WHERE request_id = ?", (request_id,)
            ).fetchone()
        return dict(stored) if stored is not None else row

    def record_reconciliation(
        self,
        *,
        idempotency_key: str,
        external_order_found: bool,
        resolved_outcome: SubmissionOutcome | str,
        evidence_ref: str = "",
    ) -> dict[str, Any]:
        """Record the outcome of reconciling an ambiguous submission.

        This is the ONLY way an ambiguous attempt becomes actionable again, and
        it only unblocks resubmission when reconciliation proved no external
        order exists.
        """
        resolved = resolved_outcome.value if isinstance(resolved_outcome, SubmissionOutcome) else str(resolved_outcome)
        row = {
            "idempotency_key": idempotency_key,
            "external_order_found": 1 if external_order_found else 0,
            "resolved_outcome": resolved,
            "evidence_ref": evidence_ref,
            "recorded_at": float(self._clock()),
        }
        with self._lock:
            self._conn.execute(
                "INSERT INTO submission_reconciliations "
                "(idempotency_key, external_order_found, resolved_outcome, evidence_ref, recorded_at) "
                "VALUES (:idempotency_key, :external_order_found, :resolved_outcome, :evidence_ref, :recorded_at) "
                "ON CONFLICT(idempotency_key) DO UPDATE SET "
                " external_order_found=excluded.external_order_found,"
                " resolved_outcome=excluded.resolved_outcome,"
                " evidence_ref=excluded.evidence_ref,"
                " recorded_at=excluded.recorded_at",
                row,
            )
            self._conn.commit()
        return row

    def finalize(self, request_id: str, outcome: SubmissionOutcome | str) -> dict[str, Any] | None:
        """Complete a previously recorded intent without changing its identity."""
        disposition = classify_submission(outcome)
        outcome_value = outcome.value if isinstance(outcome, SubmissionOutcome) else str(outcome)
        with self._lock:
            self._conn.execute(
                "UPDATE submission_attempts SET outcome=?, disposition=? WHERE request_id=?",
                (outcome_value, disposition.value, request_id),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM submission_attempts WHERE request_id=?", (request_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    # ── reads ─────────────────────────────────────────────────────────────

    def attempts_for(self, idempotency_key: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM submission_attempts WHERE idempotency_key = ? ORDER BY attempt ASC, recorded_at ASC",
            (idempotency_key,),
        ).fetchall()
        return [dict(r) for r in rows]

    def unresolved_keys(self) -> list[str]:
        """Return keys whose latest known outcome still requires reconciliation."""
        rows = self._conn.execute(
            "SELECT DISTINCT idempotency_key FROM submission_attempts"
        ).fetchall()
        return [
            str(r["idempotency_key"])
            for r in rows
            if self.requires_reconciliation(str(r["idempotency_key"]))
        ]

    def _reconciliation(self, idempotency_key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM submission_reconciliations WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return dict(row) if row is not None else None

    def already_submitted(self, idempotency_key: str) -> bool:
        """True when we know an order for this key reached the venue."""
        recon = self._reconciliation(idempotency_key)
        if recon is not None and recon["external_order_found"]:
            return True
        for a in self.attempts_for(idempotency_key):
            if a["outcome"] == SubmissionOutcome.ACKNOWLEDGED.value:
                return True
        return False

    def requires_reconciliation(self, idempotency_key: str) -> bool:
        """True when an attempt ended ambiguously and has not been resolved."""
        if self._reconciliation(idempotency_key) is not None:
            return False
        return any(
            a["disposition"] == RetryDisposition.RECONCILE_FIRST.value
            for a in self.attempts_for(idempotency_key)
        )

    def may_submit(self, idempotency_key: str) -> bool:
        """Fail-closed gate on (re)submission for this idempotency key."""
        # Order matters. The reconciliation table is consulted BEFORE the
        # "no attempts recorded" shortcut: a reconciliation row can exist for a
        # key with no attempt row (attempt written under a different key, row
        # lost, or reconciliation performed out of band). Short-circuiting on an
        # empty attempt list would then permit a duplicate against an order we
        # know reached the venue.
        if self.already_submitted(idempotency_key):
            return False                      # would duplicate a live order
        if self.requires_reconciliation(idempotency_key):
            return False                      # ambiguous, unresolved

        attempts = self.attempts_for(idempotency_key)
        recon = self._reconciliation(idempotency_key)
        if recon is not None:
            # Reconciliation proved nothing reached the venue.
            return classify_submission(recon["resolved_outcome"]) is RetryDisposition.SAFE_TO_RETRY

        if not attempts:
            return True                       # never attempted, nothing reconciled

        # No ambiguity: retry only if the latest attempt was provably untransmitted.
        latest = attempts[-1]
        return latest["disposition"] == RetryDisposition.SAFE_TO_RETRY.value

    def close(self) -> None:
        self._conn.close()


# ══════════════════════════════════════════════════════════════════════════
# Phase 8 — ReconciliationAuthority
# ══════════════════════════════════════════════════════════════════════════

class ExecutionReadiness(str, Enum):
    RECONCILED = "RECONCILED"
    TEMPORARILY_PENDING = "TEMPORARILY_PENDING"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


def readiness_permits(readiness: ExecutionReadiness, *, allow_execution_while_pending: bool = False) -> bool:
    """Only RECONCILED permits execution. TEMPORARILY_PENDING is configurable."""
    if readiness is ExecutionReadiness.RECONCILED:
        return True
    if readiness is ExecutionReadiness.TEMPORARILY_PENDING:
        return bool(allow_execution_while_pending)
    return False


# States that mean "this order is still in flight" rather than "something is wrong".
_IN_FLIGHT_STATES = frozenset({
    "PROPOSED", "RISK_CHECKED", "AWAITING_APPROVAL", "APPROVED",
    "SUBMISSION_PENDING", "SUBMITTED", "ACKNOWLEDGED", "PENDING_VALIDATION",
    "ACCEPTED", "OPEN", "PARTIALLY_FILLED", "CANCEL_PENDING",
})
_AMBIGUOUS_STATES = frozenset({"UNKNOWN", "RECONCILIATION_REQUIRED"})


@dataclass(frozen=True)
class OmsSnapshot:
    orders: Sequence[Mapping[str, Any]]
    fills: Sequence[Mapping[str, Any]]
    as_of: float


@dataclass(frozen=True)
class ExternalOrderSnapshot:
    """Authoritative external view. In PAPER mode this is the simulated venue.

    A future broker snapshot implements the same shape, so the authority does
    not change when a real venue appears.
    """
    orders: Sequence[Mapping[str, Any]]
    fills: Sequence[Mapping[str, Any]]
    as_of: float
    available: bool = True


@dataclass(frozen=True)
class LedgerSnapshot:
    cash: str
    positions: Mapping[str, str]
    as_of: float


@dataclass(frozen=True)
class ReconciliationVerdict:
    readiness: ExecutionReadiness
    permits_new_execution: bool
    findings: tuple[str, ...] = ()
    evaluated_at: float = 0.0
    correlation_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "readiness": self.readiness.value,
            "permits_new_execution": self.permits_new_execution,
            "findings": list(self.findings),
            "evaluated_at": self.evaluated_at,
            "correlation_id": self.correlation_id,
        }


def _dec(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


class ReconciliationAuthority:
    """Deterministic verdict on OMS / external / ledger consistency.

    It certifies state consistency or denies readiness. It has no method that
    authorises, approves, submits, or executes anything — by design and by test.
    """

    def __init__(self, *, allow_execution_while_pending: bool = False, clock=None) -> None:
        self._allow_pending = bool(allow_execution_while_pending)
        self._clock = clock or _time.time

    def evaluate(
        self,
        *,
        oms: OmsSnapshot,
        external: ExternalOrderSnapshot,
        ledger: LedgerSnapshot,
        expected_cash: str | None,
        expected_positions: Mapping[str, str] | None,
        order_original_quantities: Mapping[str, str] | None = None,
        correlation_id: str = "",
    ) -> ReconciliationVerdict:
        findings: list[str] = []

        # ── data sufficiency comes first; we cannot judge what we cannot see ──
        if not external.available:
            return self._verdict(
                ExecutionReadiness.DATA_INSUFFICIENT,
                ("external snapshot unavailable",),
                correlation_id,
            )
        if expected_cash is None or expected_positions is None:
            return self._verdict(
                ExecutionReadiness.DATA_INSUFFICIENT,
                ("expected cash or positions not supplied",),
                correlation_id,
            )

        oms_by_id = {str(o.get("order_id")): o for o in oms.orders}
        ext_by_id = {str(o.get("order_id")): o for o in external.orders}

        # ── ambiguous order state dominates everything ───────────────────────
        # Each side is checked independently. Merging the two dicts would let the
        # external snapshot's state overwrite the OMS state for the same order id,
        # hiding an OMS-side UNKNOWN behind a healthy-looking venue state — the
        # exact failure this module exists to prevent.
        ambiguous = sorted({
            oid
            for side in (oms_by_id, ext_by_id)
            for oid, o in side.items()
            if str(o.get("state", "")).upper() in _AMBIGUOUS_STATES
        })
        if ambiguous:
            return self._verdict(
                ExecutionReadiness.UNKNOWN,
                tuple(f"order {oid} is in an ambiguous state" for oid in ambiguous),
                correlation_id,
            )

        # ── order-set agreement ──────────────────────────────────────────────
        for oid in sorted(set(oms_by_id) - set(ext_by_id)):
            findings.append(f"order {oid} present in OMS but absent externally")
        for oid in sorted(set(ext_by_id) - set(oms_by_id)):
            findings.append(f"order {oid} present externally but unknown to OMS")

        # ── per-order filled-quantity agreement and overfill ─────────────────
        originals = order_original_quantities or {}
        for oid in sorted(set(oms_by_id) & set(ext_by_id)):
            a = _dec(oms_by_id[oid].get("filled_quantity", "0"))
            b = _dec(ext_by_id[oid].get("filled_quantity", "0"))
            if a is None or b is None:
                findings.append(f"order {oid} has unparseable filled quantity")
            elif a != b:
                findings.append(f"order {oid} filled quantity differs: oms={a} external={b}")
            original = _dec(originals.get(oid)) if oid in originals else None
            if original is not None and a is not None and a > original:
                findings.append(f"order {oid} overfilled: filled={a} original={original}")

        # ── fill-set agreement ───────────────────────────────────────────────
        oms_fill_ids = {str(f.get("fill_id")) for f in oms.fills}
        ext_fill_ids = {str(f.get("fill_id")) for f in external.fills}
        for fid in sorted(oms_fill_ids - ext_fill_ids):
            findings.append(f"fill {fid} present in OMS but absent externally")
        for fid in sorted(ext_fill_ids - oms_fill_ids):
            findings.append(f"fill {fid} present externally but unknown to OMS")

        # ── ledger agreement ─────────────────────────────────────────────────
        ledger_cash, want_cash = _dec(ledger.cash), _dec(expected_cash)
        if ledger_cash is None or want_cash is None:
            findings.append("cash values unparseable")
        elif ledger_cash != want_cash:
            findings.append(f"ledger cash {ledger_cash} != expected {want_cash}")

        for symbol in sorted(set(ledger.positions) | set(expected_positions)):
            have = _dec(ledger.positions.get(symbol, "0"))
            want = _dec(expected_positions.get(symbol, "0"))
            if have is None or want is None:
                findings.append(f"position {symbol} unparseable")
            elif have != want:
                findings.append(f"position {symbol}: ledger {have} != expected {want}")

        if findings:
            return self._verdict(ExecutionReadiness.MISMATCH, tuple(findings), correlation_id)

        # ── consistent, but is anything still in flight? ─────────────────────
        in_flight = [
            oid for oid, o in oms_by_id.items()
            if str(o.get("state", "")).upper() in _IN_FLIGHT_STATES
        ]
        if in_flight:
            return self._verdict(
                ExecutionReadiness.TEMPORARILY_PENDING,
                tuple(f"order {oid} still in flight" for oid in sorted(in_flight)),
                correlation_id,
            )

        return self._verdict(ExecutionReadiness.RECONCILED, (), correlation_id)

    def _verdict(
        self,
        readiness: ExecutionReadiness,
        findings: tuple[str, ...],
        correlation_id: str,
    ) -> ReconciliationVerdict:
        return ReconciliationVerdict(
            readiness=readiness,
            permits_new_execution=readiness_permits(
                readiness, allow_execution_while_pending=self._allow_pending
            ),
            findings=findings,
            evaluated_at=float(self._clock()),
            correlation_id=correlation_id,
        )
