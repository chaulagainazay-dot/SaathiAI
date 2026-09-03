"""Crypto paper execution — ambiguous-transport event handling (PAPER-CRYPTO-1).

The existing OrderSimulator already models submission, ack, partial/full fills,
reject, cancel, fees, spread, slippage, liquidity, and staleness. This layer adds
the transport-ambiguity events a real 24/7 crypto venue produces — TIMEOUT,
DISCONNECT, DUPLICATE, UNKNOWN — and resolves them under the SaathiOS invariants:

  * UNKNOWN / TIMEOUT / DISCONNECT -> RECONCILE_REQUIRED (fail closed). Never an
    automatic retry, never silently "healthy".
  * DUPLICATE event on an already-seen (order_id, seq) -> IGNORED_DUPLICATE.
    Idempotent: a duplicate never applies a second fill.
  * ACK/FILL/PARTIAL/REJECT/CANCEL -> the corresponding deterministic outcome.

Deterministic, side-effect free, offline. No private Binance API, no real order.
It classifies events into safe outcomes; it does not itself talk to any venue and
holds no execution authority — ExecutionGateway remains canonical upstream.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PaperExecEvent(str, Enum):
    ACK = "ACK"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILL = "FILL"
    REJECT = "REJECT"
    CANCEL = "CANCEL"
    TIMEOUT = "TIMEOUT"
    DISCONNECT = "DISCONNECT"
    DUPLICATE = "DUPLICATE"
    UNKNOWN = "UNKNOWN"


class PaperExecOutcome(str, Enum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"   # ambiguous — fail closed
    IGNORED_DUPLICATE = "IGNORED_DUPLICATE"


# Events whose truth is unknown to us: we must not assume success or failure.
_AMBIGUOUS = {PaperExecEvent.TIMEOUT, PaperExecEvent.DISCONNECT, PaperExecEvent.UNKNOWN}

_TERMINAL_OUTCOMES = {
    PaperExecOutcome.FILLED,
    PaperExecOutcome.REJECTED,
    PaperExecOutcome.CANCELLED,
}


@dataclass
class ExecEventResult:
    order_id: str
    seq: int
    event: PaperExecEvent
    outcome: PaperExecOutcome
    reconcile: bool
    detail: dict = field(default_factory=dict)


class CryptoPaperExecutionSimulator:
    """Idempotent, fail-closed classifier for paper crypto execution events."""

    def __init__(self) -> None:
        # (order_id, seq) already applied -> its outcome (for duplicate detection).
        self._seen: dict[tuple[str, int], PaperExecOutcome] = {}
        # order_id -> True once it reached a terminal or reconcile-required state.
        self._locked: dict[str, PaperExecOutcome] = {}

    def _apply(self, order_id: str, outcome: PaperExecOutcome) -> None:
        if outcome in _TERMINAL_OUTCOMES or outcome == PaperExecOutcome.RECONCILE_REQUIRED:
            self._locked[order_id] = outcome

    def handle(
        self,
        order_id: str,
        seq: int,
        event: PaperExecEvent,
        *,
        filled_qty: float | None = None,
    ) -> ExecEventResult:
        key = (str(order_id), int(seq))

        # Idempotency: a re-delivered (order_id, seq) never applies twice.
        if key in self._seen or event == PaperExecEvent.DUPLICATE:
            prior = self._seen.get(key)
            return ExecEventResult(
                order_id, seq, event, PaperExecOutcome.IGNORED_DUPLICATE, reconcile=False,
                detail={"prior_outcome": prior.value if prior else None},
            )

        # Once an order is reconcile-required, no later event silently heals it;
        # ambiguity must be explicitly resolved by ReconciliationAuthority.
        locked = self._locked.get(str(order_id))
        if locked == PaperExecOutcome.RECONCILE_REQUIRED and event not in (
            PaperExecEvent.REJECT, PaperExecEvent.CANCEL,
        ):
            res = ExecEventResult(
                order_id, seq, event, PaperExecOutcome.RECONCILE_REQUIRED, reconcile=True,
                detail={"reason": "order_locked_awaiting_reconciliation"},
            )
            self._seen[key] = res.outcome
            return res

        if event in _AMBIGUOUS:
            outcome = PaperExecOutcome.RECONCILE_REQUIRED
            reconcile = True
            detail = {"reason": f"{event.value.lower()}_no_auto_retry"}
        elif event == PaperExecEvent.ACK:
            outcome, reconcile, detail = PaperExecOutcome.ACKNOWLEDGED, False, {}
        elif event == PaperExecEvent.PARTIAL_FILL:
            outcome, reconcile, detail = PaperExecOutcome.PARTIALLY_FILLED, False, {"filled_qty": filled_qty}
        elif event == PaperExecEvent.FILL:
            outcome, reconcile, detail = PaperExecOutcome.FILLED, False, {"filled_qty": filled_qty}
        elif event == PaperExecEvent.REJECT:
            outcome, reconcile, detail = PaperExecOutcome.REJECTED, False, {}
        elif event == PaperExecEvent.CANCEL:
            outcome, reconcile, detail = PaperExecOutcome.CANCELLED, False, {}
        else:  # unreachable given the enum, but fail closed rather than assume
            outcome, reconcile, detail = PaperExecOutcome.RECONCILE_REQUIRED, True, {"reason": "unclassified_event"}

        res = ExecEventResult(order_id, seq, event, outcome, reconcile, detail)
        self._seen[key] = outcome
        self._apply(str(order_id), outcome)
        return res

    def pending_reconciliation(self) -> list[str]:
        """Order ids currently locked awaiting explicit reconciliation."""
        return sorted(oid for oid, o in self._locked.items() if o == PaperExecOutcome.RECONCILE_REQUIRED)
