"""Typed, proposal-only NEPSE external transaction records."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class NEPSETransactionSource(str, Enum):
    MEROSHARE = "MEROSHARE"
    TMS = "TMS"
    NEPAL_SHARE = "NEPAL_SHARE"


class NEPSETransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    BONUS = "BONUS"
    RIGHTS_ALLOTMENT = "RIGHTS_ALLOTMENT"
    IPO_ALLOTMENT = "IPO_ALLOTMENT"
    FPO_ALLOTMENT = "FPO_ALLOTMENT"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    DIVIDEND_CASH = "DIVIDEND_CASH"
    DIVIDEND_STOCK = "DIVIDEND_STOCK"
    MERGER_ADJUSTMENT = "MERGER_ADJUSTMENT"
    SPLIT_ADJUSTMENT = "SPLIT_ADJUSTMENT"
    CORPORATE_ACTION = "CORPORATE_ACTION"
    REVERSAL = "REVERSAL"
    UNKNOWN = "UNKNOWN"


class NEPSETransactionDescriptionMatch(str, Enum):
    EXACT_ALIAS = "EXACT_ALIAS"
    VERIFIED_ALIAS = "VERIFIED_ALIAS"
    UNKNOWN = "UNKNOWN"


class NEPSETransactionSchemaStatus(str, Enum):
    SOURCE_SCHEMA_UNVERIFIED = "SOURCE_SCHEMA_UNVERIFIED"
    UNKNOWN_SCHEMA = "UNKNOWN_SCHEMA"


class NEPSETransactionDuplicateStatus(str, Enum):
    UNIQUE = "UNIQUE"
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    CONFLICTING_DUPLICATE = "CONFLICTING_DUPLICATE"


class NEPSETransactionReasonCode(str, Enum):
    UNKNOWN_SCHEMA = "UNKNOWN_SCHEMA"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_SYMBOL = "INVALID_SYMBOL"
    UNKNOWN_INSTRUMENT = "UNKNOWN_INSTRUMENT"
    INVALID_DATE = "INVALID_DATE"
    AMBIGUOUS_DATE = "AMBIGUOUS_DATE"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    INVALID_PRICE = "INVALID_PRICE"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    INVALID_CURRENCY = "INVALID_CURRENCY"
    UNKNOWN_TRANSACTION_TYPE = "UNKNOWN_TRANSACTION_TYPE"
    DUPLICATE_TRANSACTION = "DUPLICATE_TRANSACTION"
    AMBIGUOUS_TRANSACTION = "AMBIGUOUS_TRANSACTION"
    UNSUPPORTED_DATE_FORMAT = "UNSUPPORTED_DATE_FORMAT"
    FILE_LIMIT_EXCEEDED = "FILE_LIMIT_EXCEEDED"
    MALFORMED_INPUT = "MALFORMED_INPUT"


@dataclass(frozen=True)
class NEPSETransactionFileLimits:
    """Hard parser bounds for retail-sized exports."""

    max_file_size_bytes: int = 5 * 1024 * 1024
    max_rows: int = 50_000
    max_columns: int = 64
    max_cell_length: int = 4_096

    def __post_init__(self) -> None:
        for name in (
            "max_file_size_bytes",
            "max_rows",
            "max_columns",
            "max_cell_length",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")


DEFAULT_TRANSACTION_FILE_LIMITS = NEPSETransactionFileLimits()


class NEPSETransactionFileError(ValueError):
    """A typed whole-file refusal; no partial result is returned."""

    def __init__(self, reason_code: NEPSETransactionReasonCode, detail: str) -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"{reason_code.value}: {detail}")


@dataclass(frozen=True)
class NEPSEExternalTransaction:
    """Faithful external fact set; never a posting, order, or position change."""

    transaction_id: str
    source: NEPSETransactionSource
    source_schema: str
    source_file_ref: str
    source_row_number: int
    instrument_id: str
    raw_symbol: str
    transaction_type: NEPSETransactionType
    raw_transaction_type: str
    raw_description: str
    description_match: NEPSETransactionDescriptionMatch
    trade_date: date
    settlement_date: date | None
    available_at: datetime | None
    received_at: datetime
    quantity: Decimal | None
    unit_price: Decimal | None
    gross_amount: Decimal | None
    fees: Decimal | None
    commission: Decimal | None
    sebon_fee: Decimal | None
    dp_charge: Decimal | None
    tax: Decimal | None
    capital_gains_tax: Decimal | None
    other_charges: Decimal | None
    net_amount: Decimal | None
    currency: str
    external_reference: str | None
    contract_number: str | None
    settlement_reference: str | None
    warnings: tuple[NEPSETransactionReasonCode, ...]
    raw_ref: str
    duplicate_status: NEPSETransactionDuplicateStatus = (
        NEPSETransactionDuplicateStatus.UNIQUE
    )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in (
            "quantity",
            "unit_price",
            "gross_amount",
            "fees",
            "commission",
            "sebon_fee",
            "dp_charge",
            "tax",
            "capital_gains_tax",
            "other_charges",
            "net_amount",
        ):
            value = result[key]
            result[key] = str(value) if value is not None else None
        result["source"] = self.source.value
        result["transaction_type"] = self.transaction_type.value
        result["description_match"] = self.description_match.value
        result["trade_date"] = self.trade_date.isoformat()
        result["settlement_date"] = (
            self.settlement_date.isoformat() if self.settlement_date else None
        )
        result["available_at"] = (
            self.available_at.isoformat() if self.available_at else None
        )
        result["received_at"] = self.received_at.isoformat()
        result["warnings"] = [warning.value for warning in self.warnings]
        result["duplicate_status"] = self.duplicate_status.value
        return result


@dataclass(frozen=True)
class NEPSERejectedTransactionRow:
    row_number: int
    reason_code: NEPSETransactionReasonCode
    field: str
    detail: str
    raw_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_number": self.row_number,
            "reason_code": self.reason_code.value,
            "field": self.field,
            "detail": self.detail,
            "raw_ref": self.raw_ref,
        }


@dataclass(frozen=True)
class NEPSETransactionDuplicate:
    row_number: int
    prior_row_number: int
    transaction_id: str
    status: NEPSETransactionDuplicateStatus

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_number": self.row_number,
            "prior_row_number": self.prior_row_number,
            "transaction_id": self.transaction_id,
            "status": self.status.value,
        }


@dataclass(frozen=True)
class NEPSETransactionImportResult:
    """Fully accounted import proposal.

    Duplicate rows remain in ``transactions`` and therefore in ``accepted``.
    ``duplicates`` counts accepted rows after the first row in a duplicate
    group.  Reconciliation can inspect every original event; nothing is merged.
    """

    source: NEPSETransactionSource
    source_schema: str
    schema_status: NEPSETransactionSchemaStatus
    source_file_ref: str
    source_file_fingerprint: str
    rows_seen: int
    accepted: int
    rejected: int
    duplicates: int
    transactions: tuple[NEPSEExternalTransaction, ...] = ()
    rejected_rows: tuple[NEPSERejectedTransactionRow, ...] = ()
    duplicate_rows: tuple[NEPSETransactionDuplicate, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.accepted != len(self.transactions):
            raise ValueError("accepted must equal len(transactions)")
        if self.rejected != len(self.rejected_rows):
            raise ValueError("rejected must equal len(rejected_rows)")
        if self.duplicates != len(self.duplicate_rows):
            raise ValueError("duplicates must equal len(duplicate_rows)")
        if self.accepted + self.rejected != self.rows_seen:
            raise ValueError("accepted + rejected must equal rows_seen")

    @property
    def accepted_count(self) -> int:
        return self.accepted

    @property
    def rejected_count(self) -> int:
        return self.rejected

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "source_schema": self.source_schema,
            "schema_status": self.schema_status.value,
            "source_file_ref": self.source_file_ref,
            "source_file_fingerprint": self.source_file_fingerprint,
            "rows_seen": self.rows_seen,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "duplicates": self.duplicates,
            "warnings": list(self.warnings),
            "transactions": [transaction.to_dict() for transaction in self.transactions],
            "rejected_rows": [row.to_dict() for row in self.rejected_rows],
            "duplicate_rows": [row.to_dict() for row in self.duplicate_rows],
        }
