"""T-NEXT-4 Phase 8 — ReconciliationAuthority.

Invariant tests written BEFORE implementation (TDD).

The authority certifies state consistency. It never authorises a trade: its
only outputs are a readiness verdict and a reason. Anything short of RECONCILED
denies readiness — fail closed.
"""
from __future__ import annotations

import pytest

from saathi.platform.paper_trading.execution_integrity import (
    ExecutionReadiness,
    ExternalOrderSnapshot,
    LedgerSnapshot,
    OmsSnapshot,
    ReconciliationAuthority,
)


def _oms(orders=None, fills=None):
    return OmsSnapshot(
        orders=orders if orders is not None else [],
        fills=fills if fills is not None else [],
        as_of=1000.0,
    )


def _ext(orders=None, fills=None, as_of=1000.0, available=True):
    return ExternalOrderSnapshot(
        orders=orders if orders is not None else [],
        fills=fills if fills is not None else [],
        as_of=as_of,
        available=available,
    )


def _ledger(cash="1000.00", positions=None, as_of=1000.0):
    return LedgerSnapshot(
        cash=cash,
        positions=positions if positions is not None else {},
        as_of=as_of,
    )


ORDER = {"order_id": "o1", "client_order_id": "c1", "state": "FILLED", "filled_quantity": "10"}
FILL = {"fill_id": "f1", "order_id": "o1", "quantity": "10", "price": "5.00", "side": "BUY"}


@pytest.fixture()
def authority():
    return ReconciliationAuthority()


# ── happy path ─────────────────────────────────────────────────────────────

def test_fully_consistent_state_is_reconciled(authority):
    r = authority.evaluate(
        oms=_oms([ORDER], [FILL]),
        external=_ext([ORDER], [FILL]),
        ledger=_ledger(cash="950.00", positions={"AAPL": "10"}),
        expected_cash="950.00",
        expected_positions={"AAPL": "10"},
    )
    assert r.readiness is ExecutionReadiness.RECONCILED
    assert r.permits_new_execution is True


def test_empty_but_consistent_state_is_reconciled(authority):
    r = authority.evaluate(
        oms=_oms(), external=_ext(), ledger=_ledger(),
        expected_cash="1000.00", expected_positions={},
    )
    assert r.readiness is ExecutionReadiness.RECONCILED


# ── every non-reconciled verdict must deny ─────────────────────────────────

def test_order_missing_externally_is_mismatch_and_blocks(authority):
    r = authority.evaluate(
        oms=_oms([ORDER], [FILL]),
        external=_ext([], []),
        ledger=_ledger(cash="950.00", positions={"AAPL": "10"}),
        expected_cash="950.00", expected_positions={"AAPL": "10"},
    )
    assert r.readiness is ExecutionReadiness.MISMATCH
    assert r.permits_new_execution is False


def test_unknown_external_order_is_mismatch_and_blocks(authority):
    ghost = {"order_id": "ghost", "client_order_id": "cX", "state": "FILLED", "filled_quantity": "5"}
    r = authority.evaluate(
        oms=_oms(), external=_ext([ghost], []), ledger=_ledger(),
        expected_cash="1000.00", expected_positions={},
    )
    assert r.readiness is ExecutionReadiness.MISMATCH
    assert r.permits_new_execution is False
    assert any("ghost" in str(f) for f in r.findings)


def test_ledger_cash_drift_is_mismatch_and_blocks(authority):
    r = authority.evaluate(
        oms=_oms([ORDER], [FILL]), external=_ext([ORDER], [FILL]),
        ledger=_ledger(cash="999.99", positions={"AAPL": "10"}),
        expected_cash="950.00", expected_positions={"AAPL": "10"},
    )
    assert r.readiness is ExecutionReadiness.MISMATCH
    assert r.permits_new_execution is False


def test_position_drift_is_mismatch_and_blocks(authority):
    r = authority.evaluate(
        oms=_oms([ORDER], [FILL]), external=_ext([ORDER], [FILL]),
        ledger=_ledger(cash="950.00", positions={"AAPL": "9"}),
        expected_cash="950.00", expected_positions={"AAPL": "10"},
    )
    assert r.readiness is ExecutionReadiness.MISMATCH
    assert r.permits_new_execution is False


def test_unavailable_external_snapshot_is_data_insufficient_and_blocks(authority):
    r = authority.evaluate(
        oms=_oms([ORDER], [FILL]), external=_ext(available=False),
        ledger=_ledger(cash="950.00", positions={"AAPL": "10"}),
        expected_cash="950.00", expected_positions={"AAPL": "10"},
    )
    assert r.readiness is ExecutionReadiness.DATA_INSUFFICIENT
    assert r.permits_new_execution is False


def test_missing_expectations_are_data_insufficient_and_block(authority):
    r = authority.evaluate(
        oms=_oms(), external=_ext(), ledger=_ledger(),
        expected_cash=None, expected_positions=None,
    )
    assert r.readiness is ExecutionReadiness.DATA_INSUFFICIENT
    assert r.permits_new_execution is False


def test_in_flight_order_is_temporarily_pending(authority):
    inflight = {"order_id": "o2", "client_order_id": "c2", "state": "SUBMITTED", "filled_quantity": "0"}
    r = authority.evaluate(
        oms=_oms([inflight]), external=_ext([inflight]), ledger=_ledger(),
        expected_cash="1000.00", expected_positions={},
    )
    assert r.readiness is ExecutionReadiness.TEMPORARILY_PENDING


def test_temporarily_pending_fails_closed_by_default(authority):
    inflight = {"order_id": "o2", "client_order_id": "c2", "state": "SUBMITTED", "filled_quantity": "0"}
    r = authority.evaluate(
        oms=_oms([inflight]), external=_ext([inflight]), ledger=_ledger(),
        expected_cash="1000.00", expected_positions={},
    )
    assert r.permits_new_execution is False


def test_temporarily_pending_can_be_configured_permissive(authority):
    permissive = ReconciliationAuthority(allow_execution_while_pending=True)
    inflight = {"order_id": "o2", "client_order_id": "c2", "state": "SUBMITTED", "filled_quantity": "0"}
    r = permissive.evaluate(
        oms=_oms([inflight]), external=_ext([inflight]), ledger=_ledger(),
        expected_cash="1000.00", expected_positions={},
    )
    assert r.readiness is ExecutionReadiness.TEMPORARILY_PENDING
    assert r.permits_new_execution is True


def test_unknown_order_state_is_unknown_and_blocks(authority):
    murky = {"order_id": "o3", "client_order_id": "c3", "state": "UNKNOWN", "filled_quantity": "0"}
    r = authority.evaluate(
        oms=_oms([murky]), external=_ext([murky]), ledger=_ledger(),
        expected_cash="1000.00", expected_positions={},
    )
    assert r.readiness is ExecutionReadiness.UNKNOWN
    assert r.permits_new_execution is False


def test_overfill_is_mismatch_and_blocks(authority):
    over = {"order_id": "o1", "client_order_id": "c1", "state": "FILLED", "filled_quantity": "12"}
    r = authority.evaluate(
        oms=_oms([over], [FILL]), external=_ext([over], [FILL]),
        ledger=_ledger(cash="950.00", positions={"AAPL": "10"}),
        expected_cash="950.00", expected_positions={"AAPL": "10"},
        order_original_quantities={"o1": "10"},
    )
    assert r.readiness is ExecutionReadiness.MISMATCH
    assert r.permits_new_execution is False


# ── authority boundary ─────────────────────────────────────────────────────

def test_authority_never_authorises_a_trade(authority):
    r = authority.evaluate(
        oms=_oms(), external=_ext(), ledger=_ledger(),
        expected_cash="1000.00", expected_positions={},
    )
    # It exposes readiness only. It must expose nothing that looks like approval.
    for forbidden in ("approve", "authorize", "authorise", "submit", "execute", "place_order"):
        assert not hasattr(r, forbidden)
        assert not hasattr(authority, forbidden)


def test_verdict_is_immutable(authority):
    r = authority.evaluate(
        oms=_oms(), external=_ext(), ledger=_ledger(),
        expected_cash="1000.00", expected_positions={},
    )
    with pytest.raises((AttributeError, TypeError)):
        r.readiness = ExecutionReadiness.RECONCILED


def test_verdict_carries_evidence(authority):
    r = authority.evaluate(
        oms=_oms([ORDER], [FILL]), external=_ext([], []),
        ledger=_ledger(cash="950.00", positions={"AAPL": "10"}),
        expected_cash="950.00", expected_positions={"AAPL": "10"},
    )
    assert r.findings, "a mismatch verdict must explain itself"
    assert r.evaluated_at > 0
    d = r.to_dict()
    assert d["readiness"] == ExecutionReadiness.MISMATCH.value
    assert d["permits_new_execution"] is False


def test_only_reconciled_permits_execution(authority):
    """Exhaustive: no readiness other than RECONCILED may permit execution."""
    from saathi.platform.paper_trading.execution_integrity import readiness_permits
    for readiness in ExecutionReadiness:
        permitted = readiness_permits(readiness, allow_execution_while_pending=False)
        assert permitted is (readiness is ExecutionReadiness.RECONCILED)


# ── regression for defect found by fresh-context review ────────────────────

def test_oms_ambiguity_is_not_masked_by_healthy_external_state(authority):
    """R2: an OMS order in UNKNOWN must force UNKNOWN even when the external
    snapshot reports the same order id as healthy. Merging the two views let the
    external state overwrite the OMS state and fall through to RECONCILED."""
    oms_view = {"order_id": "o1", "client_order_id": "c1", "state": "UNKNOWN", "filled_quantity": "0"}
    ext_view = {"order_id": "o1", "client_order_id": "c1", "state": "OPEN", "filled_quantity": "0"}
    r = authority.evaluate(
        oms=OmsSnapshot(orders=[oms_view], fills=[], as_of=1.0),
        external=ExternalOrderSnapshot(orders=[ext_view], fills=[], as_of=1.0),
        ledger=LedgerSnapshot(cash="1000.00", positions={}, as_of=1.0),
        expected_cash="1000.00", expected_positions={},
    )
    assert r.readiness is ExecutionReadiness.UNKNOWN
    assert r.permits_new_execution is False


def test_external_ambiguity_is_not_masked_by_healthy_oms_state(authority):
    """The symmetric case: external UNKNOWN must not be hidden by a healthy OMS view."""
    oms_view = {"order_id": "o1", "client_order_id": "c1", "state": "OPEN", "filled_quantity": "0"}
    ext_view = {"order_id": "o1", "client_order_id": "c1", "state": "UNKNOWN", "filled_quantity": "0"}
    r = authority.evaluate(
        oms=OmsSnapshot(orders=[oms_view], fills=[], as_of=1.0),
        external=ExternalOrderSnapshot(orders=[ext_view], fills=[], as_of=1.0),
        ledger=LedgerSnapshot(cash="1000.00", positions={}, as_of=1.0),
        expected_cash="1000.00", expected_positions={},
    )
    assert r.readiness is ExecutionReadiness.UNKNOWN
    assert r.permits_new_execution is False
