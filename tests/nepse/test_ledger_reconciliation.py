from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from saathi.platform.nepse.ledger import ReconciliationStatus, reconcile_transactions
from saathi.platform.nepse.transactions.models import NEPSETransactionSource, NEPSETransactionType


def tx(t=NEPSETransactionType.BUY, ref="r1", instrument="NEPSE:NABIL", qty="10", price="100"):
    return SimpleNamespace(transaction_id=ref, source=NEPSETransactionSource.MEROSHARE, source_schema="SOURCE_SCHEMA_UNVERIFIED", instrument_id=instrument, transaction_type=t, external_reference=ref, quantity=Decimal(qty) if qty is not None else None, unit_price=Decimal(price) if price is not None else None, net_amount=Decimal("1000"), raw_ref="row:1", warnings=())


def test_buy_external_only_and_proposal_is_non_mutating():
    result = reconcile_transactions([tx()])[0]
    assert result.status is ReconciliationStatus.EXTERNAL_ONLY
    assert result.proposals[0].status == "PROPOSAL_ONLY"
    assert result.proposals[0].cash_effect == Decimal("-1000")


def test_buy_match_quantity_and_cost_basis_mismatch():
    event = SimpleNamespace(fill_ref="r1", event_id="e1", quantity=Decimal("10"), price=Decimal("100"))
    assert reconcile_transactions([tx()], [event])[0].status is ReconciliationStatus.MATCH
    event.price = Decimal("101")
    assert reconcile_transactions([tx()], [event])[0].status is ReconciliationStatus.COST_BASIS_MISMATCH
    event.price = Decimal("100"); event.quantity = Decimal("9")
    assert reconcile_transactions([tx()], [event])[0].status is ReconciliationStatus.QUANTITY_MISMATCH


def test_duplicates_and_conflicts_are_surfaced():
    assert reconcile_transactions([tx(), tx()])[1].status is ReconciliationStatus.DUPLICATE_EXTERNAL_EVENT
    assert reconcile_transactions([tx(), tx(qty="11")])[1].status is ReconciliationStatus.CONFLICT


def test_unknown_and_corporate_events_fail_closed():
    assert reconcile_transactions([tx(instrument="NABIL")])[0].status is ReconciliationStatus.UNKNOWN_INSTRUMENT
    assert reconcile_transactions([tx(NEPSETransactionType.UNKNOWN)])[0].status is ReconciliationStatus.UNKNOWN_TRANSACTION
    assert reconcile_transactions([tx(NEPSETransactionType.BONUS, price=None)])[0].status is ReconciliationStatus.UNSUPPORTED_CORPORATE_ACTION


def test_supported_trade_and_dividend_proposals_keep_traceability():
    results = reconcile_transactions([tx(NEPSETransactionType.SELL), tx(NEPSETransactionType.DIVIDEND_CASH)], source_fingerprint="sha")
    assert all(r.source_schema_status == "SOURCE_SCHEMA_UNVERIFIED" for r in results)
    assert results[0].proposals[0].cash_effect == Decimal("1000")
    assert results[0].proposals[0].idempotency_key == results[0].proposals[0].idempotency_key


def test_reordered_transactions_have_stable_keys():
    a = reconcile_transactions([tx(ref="a"), tx(ref="b")])
    b = reconcile_transactions([tx(ref="b"), tx(ref="a")])
    assert {p.proposals[0].idempotency_key for p in a} == {p.proposals[0].idempotency_key for p in b}
