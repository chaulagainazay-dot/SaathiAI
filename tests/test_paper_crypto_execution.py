"""PAPER-CRYPTO-1 — ambiguous-transport paper execution invariants.

Proves the four constitution-critical properties for 24/7 crypto paper execution:
duplicate idempotency, fail-closed on UNKNOWN/TIMEOUT/DISCONNECT (no auto-retry),
no silent healing of a reconcile-required order, and clean terminal outcomes.
"""
import pytest

from saathi.platform.tg.paper_activation.crypto_execution import (
    CryptoPaperExecutionSimulator,
    PaperExecEvent,
    PaperExecOutcome,
)


def _sim():
    return CryptoPaperExecutionSimulator()


def test_clean_terminal_outcomes():
    s = _sim()
    assert s.handle("o1", 1, PaperExecEvent.ACK).outcome == PaperExecOutcome.ACKNOWLEDGED
    assert s.handle("o1", 2, PaperExecEvent.PARTIAL_FILL, filled_qty=0.3).outcome == PaperExecOutcome.PARTIALLY_FILLED
    assert s.handle("o1", 3, PaperExecEvent.FILL, filled_qty=0.7).outcome == PaperExecOutcome.FILLED
    assert s.handle("o2", 1, PaperExecEvent.REJECT).outcome == PaperExecOutcome.REJECTED
    assert s.handle("o3", 1, PaperExecEvent.CANCEL).outcome == PaperExecOutcome.CANCELLED


@pytest.mark.parametrize("ambiguous", [
    PaperExecEvent.TIMEOUT, PaperExecEvent.DISCONNECT, PaperExecEvent.UNKNOWN,
])
def test_ambiguous_events_fail_closed_to_reconcile(ambiguous):
    s = _sim()
    r = s.handle("o1", 1, ambiguous)
    assert r.outcome == PaperExecOutcome.RECONCILE_REQUIRED
    assert r.reconcile is True
    assert "o1" in s.pending_reconciliation()


def test_duplicate_event_is_idempotent_no_second_fill():
    s = _sim()
    first = s.handle("o1", 1, PaperExecEvent.FILL, filled_qty=1.0)
    assert first.outcome == PaperExecOutcome.FILLED
    # same (order_id, seq) redelivered
    dup = s.handle("o1", 1, PaperExecEvent.FILL, filled_qty=1.0)
    assert dup.outcome == PaperExecOutcome.IGNORED_DUPLICATE


def test_explicit_duplicate_event_ignored():
    s = _sim()
    r = s.handle("o1", 5, PaperExecEvent.DUPLICATE)
    assert r.outcome == PaperExecOutcome.IGNORED_DUPLICATE
    assert r.reconcile is False


def test_reconcile_required_not_silently_healed():
    s = _sim()
    # order goes ambiguous -> reconcile required
    s.handle("o1", 1, PaperExecEvent.TIMEOUT)
    # a later FILL must NOT silently mark it healthy/filled
    later = s.handle("o1", 2, PaperExecEvent.FILL, filled_qty=1.0)
    assert later.outcome == PaperExecOutcome.RECONCILE_REQUIRED
    assert "o1" in s.pending_reconciliation()


def test_reconcile_locked_order_can_still_be_cancelled_or_rejected():
    s = _sim()
    s.handle("o1", 1, PaperExecEvent.DISCONNECT)
    # explicit terminal resolution is allowed (operator/venue confirms cancel)
    r = s.handle("o1", 2, PaperExecEvent.CANCEL)
    assert r.outcome == PaperExecOutcome.CANCELLED


def test_no_auto_retry_signalled():
    s = _sim()
    r = s.handle("o9", 1, PaperExecEvent.UNKNOWN)
    assert "no_auto_retry" in r.detail.get("reason", "")
