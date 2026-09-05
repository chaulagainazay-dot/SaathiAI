"""Proposal-only boundary between NEPSE evidence and the canonical ledger."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
import hashlib
from typing import Any, Iterable

from saathi.platform.nepse.transactions.models import NEPSEExternalTransaction, NEPSETransactionType


class ReconciliationStatus(str, Enum):
    MATCH = "MATCH"; EXTERNAL_ONLY = "EXTERNAL_ONLY"; LEDGER_ONLY = "LEDGER_ONLY"
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"; COST_BASIS_MISMATCH = "COST_BASIS_MISMATCH"
    CASH_MISMATCH = "CASH_MISMATCH"; DUPLICATE_EXTERNAL_EVENT = "DUPLICATE_EXTERNAL_EVENT"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"; UNKNOWN_INSTRUMENT = "UNKNOWN_INSTRUMENT"
    UNKNOWN_TRANSACTION = "UNKNOWN_TRANSACTION"; UNSUPPORTED_CORPORATE_ACTION = "UNSUPPORTED_CORPORATE_ACTION"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"; CONFLICT = "CONFLICT"
    POSITION_SNAPSHOT_RECONCILIATION = "POSITION_SNAPSHOT_RECONCILIATION"


@dataclass(frozen=True)
class NEPSEImportProposal:
    proposal_id: str
    source_transaction_id: str
    instrument_id: str
    event_type: str
    quantity: Decimal | None
    price: Decimal | None
    cash_effect: Decimal | None
    source_ref: str
    reason_code: str
    idempotency_key: str
    confidence: str = "UNVERIFIED"
    status: str = "PROPOSAL_ONLY"
    warnings: tuple[str, ...] = ()
    source: str = ""
    source_schema: str = "SOURCE_SCHEMA_UNVERIFIED"


@dataclass(frozen=True)
class NEPSELedgerReconciliation:
    status: ReconciliationStatus
    proposals: tuple[NEPSEImportProposal, ...] = ()
    reason_codes: tuple[str, ...] = ()
    source: str = ""
    source_fingerprint: str = ""
    source_schema_status: str = "SOURCE_SCHEMA_UNVERIFIED"
    transaction_ids: tuple[str, ...] = ()
    ledger_reference: str | None = None
    warnings: tuple[str, ...] = ()


_SUPPORTED = {NEPSETransactionType.BUY, NEPSETransactionType.SELL, NEPSETransactionType.DIVIDEND_CASH}


def _key(tx: NEPSEExternalTransaction) -> str:
    return tx.external_reference or tx.transaction_id


def _proposal(tx: NEPSEExternalTransaction) -> NEPSEImportProposal:
    t = tx.transaction_type
    reason = "PROPOSAL_ONLY"
    warnings = tuple(w.value for w in tx.warnings)
    if t not in _SUPPORTED:
        reason = "UNSUPPORTED_LEDGER_EVENT"
        warnings = warnings + ("POLICY_REQUIRED",)
    cash = None
    if tx.net_amount is not None:
        cash = -tx.net_amount if t == NEPSETransactionType.BUY else tx.net_amount if t in (NEPSETransactionType.SELL, NEPSETransactionType.DIVIDEND_CASH) else None
    idem = hashlib.sha256(f"nepse-ledger:{tx.transaction_id}:{tx.instrument_id}:{t.value}".encode()).hexdigest()
    return NEPSEImportProposal(tx.transaction_id, tx.transaction_id, tx.instrument_id, t.value, tx.quantity, tx.unit_price, cash, tx.raw_ref, reason, idem, source=tx.source.value, source_schema=tx.source_schema, warnings=warnings)


def reconcile_transactions(transactions: Iterable[NEPSEExternalTransaction], ledger_events: Iterable[Any] = (), *, source_fingerprint: str = "", known_instruments: set[str] | None = None) -> tuple[NEPSELedgerReconciliation, ...]:
    """Deterministically compare evidence with ledger events; never writes or applies."""
    txs = list(transactions)
    events = list(ledger_events)
    by_ref = {str(getattr(e, "fill_ref", "") or getattr(e, "event_id", "")): e for e in events}
    matched: set[str] = set()
    seen: dict[str, NEPSEExternalTransaction] = {}
    out: list[NEPSELedgerReconciliation] = []
    for tx in txs:
        key = _key(tx)
        if key in seen:
            prior = seen[key]
            same = (prior.instrument_id, prior.transaction_type, prior.quantity, prior.unit_price) == (tx.instrument_id, tx.transaction_type, tx.quantity, tx.unit_price)
            status = ReconciliationStatus.DUPLICATE_EXTERNAL_EVENT if same else ReconciliationStatus.CONFLICT
            out.append(NEPSELedgerReconciliation(status, (_proposal(tx),), (status.value,), tx.source.value, source_fingerprint, tx.source_schema, (tx.transaction_id,)))
            continue
        seen[key] = tx
        if not tx.instrument_id or not tx.instrument_id.startswith("NEPSE:") or (known_instruments is not None and tx.instrument_id not in known_instruments):
            status = ReconciliationStatus.UNKNOWN_INSTRUMENT
        elif tx.transaction_type == NEPSETransactionType.UNKNOWN:
            status = ReconciliationStatus.UNKNOWN_TRANSACTION
        elif tx.transaction_type not in _SUPPORTED:
            status = ReconciliationStatus.UNSUPPORTED_CORPORATE_ACTION
        else:
            existing = by_ref.get(key) or by_ref.get(tx.transaction_id)
            if existing is None:
                status = ReconciliationStatus.EXTERNAL_ONLY
            elif getattr(existing, "quantity", None) != tx.quantity:
                status = ReconciliationStatus.QUANTITY_MISMATCH
            elif getattr(existing, "price", None) != tx.unit_price:
                status = ReconciliationStatus.COST_BASIS_MISMATCH
            else:
                status = ReconciliationStatus.MATCH
            if existing is not None:
                matched.add(key if key in by_ref else tx.transaction_id)
        out.append(NEPSELedgerReconciliation(status, (_proposal(tx),), (status.value,), tx.source.value, source_fingerprint, tx.source_schema, (tx.transaction_id,)))
    for key, event in by_ref.items():
        if key and key not in matched and not any(key == t.transaction_id or key == _key(t) for t in txs):
            out.append(NEPSELedgerReconciliation(ReconciliationStatus.LEDGER_ONLY, (), ("LEDGER_ONLY",), ledger_reference=key))
    return tuple(out)


def reconcile_holdings_snapshot(*, instrument_id: str, quantity: Decimal, ledger_quantity: Decimal | None = None) -> NEPSELedgerReconciliation:
    """Reconcile a holdings evidence snapshot without inventing transaction history."""
    status = ReconciliationStatus.POSITION_SNAPSHOT_RECONCILIATION if ledger_quantity is None or quantity == ledger_quantity else ReconciliationStatus.QUANTITY_MISMATCH
    return NEPSELedgerReconciliation(status, reason_codes=(status.value,), transaction_ids=())
