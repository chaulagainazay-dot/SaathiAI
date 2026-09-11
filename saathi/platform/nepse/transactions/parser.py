"""Bounded parser for normalized NEPSE external transaction proposals."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable

from saathi.platform.nepse.calendar import NEPAL_TZ
from saathi.platform.nepse.instruments import (
    NepseInstrument,
    instrument_id_for,
    normalize_symbol,
)

from .models import (
    DEFAULT_TRANSACTION_FILE_LIMITS,
    NEPSEExternalTransaction,
    NEPSERejectedTransactionRow,
    NEPSETransactionDuplicate,
    NEPSETransactionDuplicateStatus,
    NEPSETransactionFileError,
    NEPSETransactionFileLimits,
    NEPSETransactionImportResult,
    NEPSETransactionReasonCode,
    NEPSETransactionSchemaStatus,
    NEPSETransactionType,
)
from .source_schemas import ProvisionalTransactionSchema, normalize_header


_FORMULA_PREFIXES = ("=", "+", "-", "@")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_YMD_SLASH_DATE = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$")
_MAX_ABSOLUTE_DECIMAL = Decimal("1E18")
_MAX_DECIMAL_PLACES = 8
_REFERENCE_FIELDS = (
    "external_reference",
    "contract_number",
    "settlement_reference",
)
_MONEY_FIELDS = (
    "gross_amount",
    "fees",
    "commission",
    "sebon_fee",
    "dp_charge",
    "tax",
    "capital_gains_tax",
    "other_charges",
    "net_amount",
)
_NON_NEGATIVE_CHARGES = frozenset(
    {
        "fees",
        "commission",
        "sebon_fee",
        "dp_charge",
        "tax",
        "capital_gains_tax",
        "other_charges",
    }
)
_PRICE_REQUIRED = frozenset({NEPSETransactionType.BUY, NEPSETransactionType.SELL})
_QUANTITY_OPTIONAL = frozenset(
    {
        NEPSETransactionType.DIVIDEND_CASH,
        NEPSETransactionType.CORPORATE_ACTION,
        NEPSETransactionType.REVERSAL,
        NEPSETransactionType.UNKNOWN,
    }
)


class _RowError(ValueError):
    def __init__(
        self, reason_code: NEPSETransactionReasonCode, field: str, detail: str
    ) -> None:
        self.reason_code = reason_code
        self.field = field
        self.detail = detail
        super().__init__(detail)


def _file_error(reason_code: NEPSETransactionReasonCode, detail: str) -> None:
    raise NEPSETransactionFileError(reason_code, detail)


def _prepare_text(
    data: str | bytes, limits: NEPSETransactionFileLimits
) -> tuple[str, str]:
    if isinstance(data, bytes):
        if len(data) > limits.max_file_size_bytes:
            _file_error(
                NEPSETransactionReasonCode.FILE_LIMIT_EXCEEDED,
                f"file exceeds {limits.max_file_size_bytes} bytes",
            )
        raw = data
        try:
            text = data.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError as exc:
            _file_error(
                NEPSETransactionReasonCode.MALFORMED_INPUT,
                f"input is not valid UTF-8 at byte {exc.start}",
            )
    elif isinstance(data, str):
        if len(data) > limits.max_file_size_bytes:
            _file_error(
                NEPSETransactionReasonCode.FILE_LIMIT_EXCEEDED,
                f"file exceeds {limits.max_file_size_bytes} characters",
            )
        raw = data.encode("utf-8")
        if len(raw) > limits.max_file_size_bytes:
            _file_error(
                NEPSETransactionReasonCode.FILE_LIMIT_EXCEEDED,
                f"UTF-8 file exceeds {limits.max_file_size_bytes} bytes",
            )
        text = data
    else:
        _file_error(
            NEPSETransactionReasonCode.MALFORMED_INPUT,
            "transaction input must be str or bytes",
        )

    if "\x00" in text:
        _file_error(
            NEPSETransactionReasonCode.MALFORMED_INPUT,
            "embedded null byte is forbidden",
        )
    return text, hashlib.sha256(raw).hexdigest()


def _validate_source_file_ref(source_file_ref: str) -> str:
    ref = (source_file_ref or "").strip()
    if len(ref) > 255:
        _file_error(
            NEPSETransactionReasonCode.FILE_LIMIT_EXCEEDED,
            "source_file_ref exceeds 255 characters",
        )
    if "\x00" in ref or "/" in ref or "\\" in ref or ref in {".", ".."}:
        _file_error(
            NEPSETransactionReasonCode.MALFORMED_INPUT,
            "source_file_ref must be a non-path provenance label",
        )
    return ref


def _validate_received_at(received_at: datetime | None) -> datetime:
    value = received_at or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        _file_error(
            NEPSETransactionReasonCode.MALFORMED_INPUT,
            "received_at must be timezone-aware",
        )
    return value


def _delimiter(text: str) -> str:
    first = next((line for line in text.splitlines() if line.strip()), "")
    comma_count = first.count(",")
    tab_count = first.count("\t")
    if comma_count == 0 and tab_count == 0 and first:
        _file_error(
            NEPSETransactionReasonCode.MALFORMED_INPUT,
            "expected a comma- or tab-delimited export",
        )
    return "\t" if tab_count > comma_count else ","


def _validate_row_limits(
    row: list[str], row_number: int, limits: NEPSETransactionFileLimits
) -> None:
    if len(row) > limits.max_columns:
        _file_error(
            NEPSETransactionReasonCode.FILE_LIMIT_EXCEEDED,
            f"row {row_number} exceeds {limits.max_columns} columns",
        )
    for column, cell in enumerate(row, start=1):
        if len(cell) > limits.max_cell_length:
            _file_error(
                NEPSETransactionReasonCode.FILE_LIMIT_EXCEEDED,
                f"row {row_number} column {column} exceeds "
                f"{limits.max_cell_length} characters",
            )


def _raw_ref(row: list[str]) -> str:
    serialized = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _instrument_index(
    instruments: Iterable[NepseInstrument],
) -> tuple[dict[str, NepseInstrument], frozenset[str]]:
    index: dict[str, NepseInstrument] = {}
    ambiguous: set[str] = set()
    for instrument in instruments:
        if not isinstance(instrument, NepseInstrument):
            _file_error(
                NEPSETransactionReasonCode.MALFORMED_INPUT,
                "instrument master entries must be NepseInstrument records",
            )
        canonical = normalize_symbol(instrument.symbol)
        if instrument.instrument_id != instrument_id_for(canonical):
            _file_error(
                NEPSETransactionReasonCode.MALFORMED_INPUT,
                f"instrument master contains inconsistent identity for {canonical}",
            )
        candidates = (canonical,) + tuple(instrument.aliases)
        for candidate in candidates:
            try:
                alias = normalize_symbol(candidate)
            except (TypeError, ValueError):
                continue
            prior = index.get(alias)
            if prior is not None and prior.instrument_id != instrument.instrument_id:
                ambiguous.add(alias)
            else:
                index[alias] = instrument
    return index, frozenset(ambiguous)


def _resolve_columns(
    headers: list[str], schema: ProvisionalTransactionSchema
) -> tuple[dict[str, int], str | None]:
    resolved: dict[str, int] = {}
    for field_name, aliases in schema.column_aliases:
        matches = [index for index, header in enumerate(headers) if header in aliases]
        if len(matches) > 1:
            return {}, f"multiple columns map to {field_name}"
        if matches:
            resolved[field_name] = matches[0]

    required = {"symbol", "trade_date", "quantity"}
    missing = sorted(required - resolved.keys())
    if missing:
        return {}, "missing required columns: " + ", ".join(missing)
    if not ({"raw_transaction_type", "raw_description"} & resolved.keys()):
        return {}, "missing transaction type or description column"
    return resolved, None


def _parse_date(raw: str, field: str, *, required: bool) -> date | None:
    value = raw.strip()
    if not value:
        if required:
            raise _RowError(
                NEPSETransactionReasonCode.MISSING_REQUIRED_FIELD,
                field,
                f"{field} is required",
            )
        return None
    try:
        if _ISO_DATE.fullmatch(value):
            return date.fromisoformat(value)
        dmy = _DMY_DATE.fullmatch(value)
        if dmy:
            day, month, year = (int(part) for part in dmy.groups())
            if day <= 12 and month <= 12:
                raise _RowError(
                    NEPSETransactionReasonCode.AMBIGUOUS_DATE,
                    field,
                    "date can be interpreted as either DD/MM or MM/DD",
                )
            if month > 12:
                raise _RowError(
                    NEPSETransactionReasonCode.INVALID_DATE,
                    field,
                    "date is not valid DD/MM/YYYY",
                )
            return date(year, month, day)
    except ValueError as exc:
        if isinstance(exc, _RowError):
            raise
        raise _RowError(
            NEPSETransactionReasonCode.INVALID_DATE,
            field,
            "invalid date value",
        ) from exc
    if _YMD_SLASH_DATE.fullmatch(value):
        raise _RowError(
            NEPSETransactionReasonCode.UNSUPPORTED_DATE_FORMAT,
            field,
            "slash-separated year-first date is unsupported; BS conversion is not inferred",
        )
    raise _RowError(
        NEPSETransactionReasonCode.UNSUPPORTED_DATE_FORMAT,
        field,
        "unsupported date format",
    )


def _parse_available_at(raw: str) -> datetime | None:
    value = raw.strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _RowError(
            NEPSETransactionReasonCode.INVALID_DATE,
            "available_at",
            "invalid ISO-8601 timestamp",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _RowError(
            NEPSETransactionReasonCode.INVALID_DATE,
            "available_at",
            "available_at must include an explicit UTC offset",
        )
    return parsed


def _parse_decimal(
    raw: str,
    field: str,
    *,
    required: bool = False,
    reason_code: NEPSETransactionReasonCode = NEPSETransactionReasonCode.INVALID_AMOUNT,
) -> Decimal | None:
    value = raw.strip().replace(",", "").replace(" ", "")
    if not value:
        if required:
            raise _RowError(
                NEPSETransactionReasonCode.MISSING_REQUIRED_FIELD,
                field,
                f"{field} is required",
            )
        return None
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise _RowError(reason_code, field, "invalid numeric value") from exc
    if not parsed.is_finite():
        raise _RowError(reason_code, field, "non-finite numeric value")
    if parsed.copy_abs() > _MAX_ABSOLUTE_DECIMAL:
        raise _RowError(
            reason_code,
            field,
            f"{field} exceeds the normalized transaction magnitude limit",
        )
    exponent = parsed.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -_MAX_DECIMAL_PLACES:
        raise _RowError(
            reason_code,
            field,
            f"{field} exceeds {_MAX_DECIMAL_PLACES} decimal places",
        )
    return parsed


def _reject_formula_like(field: str, value: str) -> None:
    if value.lstrip().startswith(_FORMULA_PREFIXES):
        raise _RowError(
            NEPSETransactionReasonCode.MALFORMED_INPUT,
            field,
            f"formula-like {field} value is forbidden",
        )


def _decimal_key(value: Decimal | None) -> str | None:
    return format(value.normalize(), "f") if value is not None else None


def _identity_payload(
    *,
    source: str,
    instrument_id: str,
    transaction_type: str,
    trade_date: date,
    quantity: Decimal | None,
    unit_price: Decimal | None,
    gross_amount: Decimal | None,
    net_amount: Decimal | None,
    raw_transaction_type: str,
    raw_description: str,
    external_reference: str | None,
    contract_number: str | None,
    settlement_reference: str | None,
) -> dict[str, object]:
    references = [
        (name, value)
        for name, value in (
            ("external_reference", external_reference),
            ("contract_number", contract_number),
            ("settlement_reference", settlement_reference),
        )
        if value
    ]
    if references:
        return {"source": source, "references": references}
    return {
        "source": source,
        "instrument_id": instrument_id,
        "trade_date": trade_date.isoformat(),
        "transaction_type": transaction_type,
        "quantity": _decimal_key(quantity),
        "unit_price": _decimal_key(unit_price),
        "gross_amount": _decimal_key(gross_amount),
        "net_amount": _decimal_key(net_amount),
        "raw_transaction_type": normalize_header(raw_transaction_type),
        "raw_description": " ".join(raw_description.casefold().split()),
    }


def _transaction_id(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "NEPSE-TXN-" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:32]


def _cell(row: list[str], columns: dict[str, int], field: str) -> str:
    index = columns.get(field)
    if index is None or index >= len(row):
        return ""
    return (row[index] or "").strip()


def _parse_row(
    row: list[str],
    row_number: int,
    *,
    columns: dict[str, int],
    schema: ProvisionalTransactionSchema,
    source_file_ref: str,
    received_at: datetime,
    instruments: dict[str, NepseInstrument],
    ambiguous_symbols: frozenset[str],
) -> NEPSEExternalTransaction:
    raw_symbol = _cell(row, columns, "symbol")
    _reject_formula_like("symbol", raw_symbol)
    try:
        symbol = normalize_symbol(raw_symbol)
    except (TypeError, ValueError) as exc:
        raise _RowError(
            NEPSETransactionReasonCode.INVALID_SYMBOL,
            "symbol",
            "symbol cannot be normalized",
        ) from exc
    if symbol in ambiguous_symbols:
        raise _RowError(
            NEPSETransactionReasonCode.AMBIGUOUS_TRANSACTION,
            "symbol",
            f"symbol {symbol} resolves to multiple instrument-master entries",
        )
    instrument = instruments.get(symbol)
    if instrument is None:
        raise _RowError(
            NEPSETransactionReasonCode.UNKNOWN_INSTRUMENT,
            "symbol",
            f"symbol {symbol} is absent from the supplied canonical instrument master",
        )

    raw_transaction_type = _cell(row, columns, "raw_transaction_type")
    raw_description = _cell(row, columns, "raw_description")
    _reject_formula_like("transaction_type", raw_transaction_type)
    _reject_formula_like("description", raw_description)
    transaction_type, description_match, conflicting_aliases = (
        schema.normalize_transaction_type(raw_transaction_type, raw_description)
    )
    if conflicting_aliases:
        raise _RowError(
            NEPSETransactionReasonCode.AMBIGUOUS_TRANSACTION,
            "transaction_type",
            "transaction type and description map to conflicting known semantics",
        )
    warnings: list[NEPSETransactionReasonCode] = []
    if transaction_type is NEPSETransactionType.UNKNOWN:
        warnings.append(NEPSETransactionReasonCode.UNKNOWN_TRANSACTION_TYPE)

    trade_date = _parse_date(
        _cell(row, columns, "trade_date"), "trade_date", required=True
    )
    assert trade_date is not None
    settlement_date = _parse_date(
        _cell(row, columns, "settlement_date"),
        "settlement_date",
        required=False,
    )
    if settlement_date is not None and settlement_date < trade_date:
        raise _RowError(
            NEPSETransactionReasonCode.INVALID_DATE,
            "settlement_date",
            "settlement_date precedes trade_date",
        )

    available_at = _parse_available_at(_cell(row, columns, "available_at"))
    if available_at is not None:
        if available_at.astimezone(NEPAL_TZ).date() < trade_date:
            raise _RowError(
                NEPSETransactionReasonCode.INVALID_DATE,
                "available_at",
                "available_at precedes trade_date",
            )
        if available_at > received_at:
            raise _RowError(
                NEPSETransactionReasonCode.INVALID_DATE,
                "available_at",
                "available_at is later than received_at",
            )

    quantity = _parse_decimal(
        _cell(row, columns, "quantity"),
        "quantity",
        required=transaction_type not in _QUANTITY_OPTIONAL,
        reason_code=NEPSETransactionReasonCode.INVALID_QUANTITY,
    )
    if quantity is not None:
        if quantity <= 0 or quantity != quantity.to_integral_value():
            raise _RowError(
                NEPSETransactionReasonCode.INVALID_QUANTITY,
                "quantity",
                "NEPSE transaction quantity must be a positive whole share count",
            )

    unit_price = _parse_decimal(
        _cell(row, columns, "unit_price"),
        "unit_price",
        required=transaction_type in _PRICE_REQUIRED,
        reason_code=NEPSETransactionReasonCode.INVALID_PRICE,
    )
    if unit_price is not None and unit_price <= 0:
        raise _RowError(
            NEPSETransactionReasonCode.INVALID_PRICE,
            "unit_price",
            "unit_price must be positive when present",
        )

    money: dict[str, Decimal | None] = {}
    for field_name in _MONEY_FIELDS:
        money[field_name] = _parse_decimal(
            _cell(row, columns, field_name), field_name
        )
        if field_name in _NON_NEGATIVE_CHARGES:
            value = money[field_name]
            if value is not None and value < 0:
                raise _RowError(
                    NEPSETransactionReasonCode.INVALID_AMOUNT,
                    field_name,
                    f"{field_name} cannot be negative",
                )

    currency = _cell(row, columns, "currency").upper() or "NPR"
    if currency != "NPR":
        raise _RowError(
            NEPSETransactionReasonCode.INVALID_CURRENCY,
            "currency",
            "provisional NEPSE source schemas do not prove a non-NPR currency",
        )

    references: dict[str, str | None] = {}
    for field_name in _REFERENCE_FIELDS:
        value = _cell(row, columns, field_name)
        _reject_formula_like(field_name, value)
        references[field_name] = value or None

    identity = _identity_payload(
        source=schema.source.value,
        instrument_id=instrument.instrument_id,
        transaction_type=transaction_type.value,
        trade_date=trade_date,
        quantity=quantity,
        unit_price=unit_price,
        gross_amount=money["gross_amount"],
        net_amount=money["net_amount"],
        raw_transaction_type=raw_transaction_type,
        raw_description=raw_description,
        external_reference=references["external_reference"],
        contract_number=references["contract_number"],
        settlement_reference=references["settlement_reference"],
    )

    return NEPSEExternalTransaction(
        transaction_id=_transaction_id(identity),
        source=schema.source,
        source_schema=schema.schema_id,
        source_file_ref=source_file_ref,
        source_row_number=row_number,
        instrument_id=instrument.instrument_id,
        raw_symbol=raw_symbol,
        transaction_type=transaction_type,
        raw_transaction_type=raw_transaction_type,
        raw_description=raw_description,
        description_match=description_match,
        trade_date=trade_date,
        settlement_date=settlement_date,
        available_at=available_at,
        received_at=received_at,
        quantity=quantity,
        unit_price=unit_price,
        gross_amount=money["gross_amount"],
        fees=money["fees"],
        commission=money["commission"],
        sebon_fee=money["sebon_fee"],
        dp_charge=money["dp_charge"],
        tax=money["tax"],
        capital_gains_tax=money["capital_gains_tax"],
        other_charges=money["other_charges"],
        net_amount=money["net_amount"],
        currency=currency,
        external_reference=references["external_reference"],
        contract_number=references["contract_number"],
        settlement_reference=references["settlement_reference"],
        warnings=tuple(warnings),
        raw_ref=_raw_ref(row),
    )


def _facts(transaction: NEPSEExternalTransaction) -> dict[str, object]:
    return {
        "source": transaction.source.value,
        "instrument_id": transaction.instrument_id,
        "transaction_type": transaction.transaction_type.value,
        "raw_transaction_type": transaction.raw_transaction_type,
        "raw_description": transaction.raw_description,
        "trade_date": transaction.trade_date.isoformat(),
        "settlement_date": (
            transaction.settlement_date.isoformat()
            if transaction.settlement_date
            else None
        ),
        "available_at": (
            transaction.available_at.isoformat() if transaction.available_at else None
        ),
        "quantity": _decimal_key(transaction.quantity),
        "unit_price": _decimal_key(transaction.unit_price),
        "gross_amount": _decimal_key(transaction.gross_amount),
        "fees": _decimal_key(transaction.fees),
        "commission": _decimal_key(transaction.commission),
        "sebon_fee": _decimal_key(transaction.sebon_fee),
        "dp_charge": _decimal_key(transaction.dp_charge),
        "tax": _decimal_key(transaction.tax),
        "capital_gains_tax": _decimal_key(transaction.capital_gains_tax),
        "other_charges": _decimal_key(transaction.other_charges),
        "net_amount": _decimal_key(transaction.net_amount),
        "currency": transaction.currency,
        "external_reference": transaction.external_reference,
        "contract_number": transaction.contract_number,
        "settlement_reference": transaction.settlement_reference,
    }


def _possible_duplicate_key(transaction: NEPSEExternalTransaction) -> tuple[object, ...]:
    return (
        transaction.source.value,
        transaction.instrument_id,
        transaction.transaction_type.value,
        transaction.trade_date.isoformat(),
        _decimal_key(transaction.quantity),
        _decimal_key(transaction.unit_price),
    )


def _classify_duplicates(
    transactions: list[NEPSEExternalTransaction],
) -> tuple[list[NEPSEExternalTransaction], list[NEPSETransactionDuplicate]]:
    classified: list[NEPSEExternalTransaction] = []
    duplicates: list[NEPSETransactionDuplicate] = []
    by_id: dict[str, tuple[int, int, dict[str, object]]] = {}
    possible: dict[tuple[object, ...], tuple[int, int]] = {}

    for transaction in transactions:
        row_number = transaction.source_row_number
        facts = _facts(transaction)
        prior = by_id.get(transaction.transaction_id)
        status = NEPSETransactionDuplicateStatus.UNIQUE
        prior_row_number: int | None = None
        if prior is not None:
            _, prior_row_number, prior_facts = prior
            status = (
                NEPSETransactionDuplicateStatus.EXACT_DUPLICATE
                if facts == prior_facts
                else NEPSETransactionDuplicateStatus.CONFLICTING_DUPLICATE
            )
        else:
            has_reference = any(
                getattr(transaction, field_name) for field_name in _REFERENCE_FIELDS
            )
            possible_key = _possible_duplicate_key(transaction)
            if not has_reference and possible_key in possible:
                _, prior_row_number = possible[possible_key]
                status = NEPSETransactionDuplicateStatus.POSSIBLE_DUPLICATE

        if status is not NEPSETransactionDuplicateStatus.UNIQUE:
            assert prior_row_number is not None
            transaction = replace(transaction, duplicate_status=status)
            duplicates.append(
                NEPSETransactionDuplicate(
                    row_number=row_number,
                    prior_row_number=prior_row_number,
                    transaction_id=transaction.transaction_id,
                    status=status,
                )
            )
        else:
            by_id[transaction.transaction_id] = (
                len(classified),
                row_number,
                facts,
            )
            if not any(
                getattr(transaction, field_name) for field_name in _REFERENCE_FIELDS
            ):
                possible.setdefault(
                    _possible_duplicate_key(transaction),
                    (len(classified), row_number),
                )
        classified.append(transaction)
    return classified, duplicates


def _unknown_schema_result(
    reader: csv.reader,
    *,
    schema: ProvisionalTransactionSchema,
    source_file_ref: str,
    fingerprint: str,
    limits: NEPSETransactionFileLimits,
    reason_code: NEPSETransactionReasonCode,
    detail: str,
) -> NEPSETransactionImportResult:
    rejected: list[NEPSERejectedTransactionRow] = []
    try:
        for row in reader:
            row_number = reader.line_num
            _validate_row_limits(row, row_number, limits)
            if not any(cell.strip() for cell in row):
                continue
            if len(rejected) >= limits.max_rows:
                _file_error(
                    NEPSETransactionReasonCode.FILE_LIMIT_EXCEEDED,
                    f"file exceeds {limits.max_rows} data rows",
                )
            rejected.append(
                NEPSERejectedTransactionRow(
                    row_number=row_number,
                    reason_code=reason_code,
                    field="header",
                    detail=detail,
                    raw_ref=_raw_ref(row),
                )
            )
    except csv.Error as exc:
        _file_error(
            NEPSETransactionReasonCode.MALFORMED_INPUT,
            f"malformed delimited input near line {reader.line_num}: {exc}",
        )
    return NEPSETransactionImportResult(
        source=schema.source,
        source_schema=schema.schema_id,
        schema_status=NEPSETransactionSchemaStatus.UNKNOWN_SCHEMA,
        source_file_ref=source_file_ref,
        source_file_fingerprint=fingerprint,
        rows_seen=len(rejected),
        accepted=0,
        rejected=len(rejected),
        duplicates=0,
        rejected_rows=tuple(rejected),
        warnings=(
            "SOURCE_SCHEMA_UNVERIFIED",
            reason_code.value,
        ),
    )


def parse_transactions(
    data: str | bytes,
    *,
    schema: ProvisionalTransactionSchema,
    instruments: Iterable[NepseInstrument],
    source_file_ref: str = "",
    received_at: datetime | None = None,
    limits: NEPSETransactionFileLimits = DEFAULT_TRANSACTION_FILE_LIMITS,
) -> NEPSETransactionImportResult:
    """Parse one bounded provisional export into a proposal-only result.

    Whole-file security failures raise ``NEPSETransactionFileError`` and never
    return a partial proposal.  Every non-blank data record in a returned
    result is accepted or rejected exactly once.
    """

    text, fingerprint = _prepare_text(data, limits)
    source_file_ref = _validate_source_file_ref(source_file_ref)
    received_at = _validate_received_at(received_at)
    instrument_index, ambiguous_symbols = _instrument_index(instruments)

    reader = csv.reader(
        io.StringIO(text, newline=""),
        delimiter=_delimiter(text),
        strict=True,
    )
    header: list[str] | None = None
    try:
        for row in reader:
            _validate_row_limits(row, reader.line_num, limits)
            if any(cell.strip() for cell in row):
                header = row
                break
    except csv.Error as exc:
        _file_error(
            NEPSETransactionReasonCode.MALFORMED_INPUT,
            f"malformed header near line {reader.line_num}: {exc}",
        )

    if header is None:
        return NEPSETransactionImportResult(
            source=schema.source,
            source_schema=schema.schema_id,
            schema_status=NEPSETransactionSchemaStatus.UNKNOWN_SCHEMA,
            source_file_ref=source_file_ref,
            source_file_fingerprint=fingerprint,
            rows_seen=0,
            accepted=0,
            rejected=0,
            duplicates=0,
            warnings=("SOURCE_SCHEMA_UNVERIFIED", "EMPTY_FILE"),
        )

    headers = [normalize_header(value) for value in header]
    if any(value.lstrip().startswith(_FORMULA_PREFIXES) for value in header):
        _file_error(
            NEPSETransactionReasonCode.MALFORMED_INPUT,
            "formula-like header value is forbidden",
        )
    if any(not value for value in headers) or len(headers) != len(set(headers)):
        return _unknown_schema_result(
            reader,
            schema=schema,
            source_file_ref=source_file_ref,
            fingerprint=fingerprint,
            limits=limits,
            reason_code=NEPSETransactionReasonCode.AMBIGUOUS_TRANSACTION,
            detail="header contains blank or duplicate normalized columns",
        )
    if not schema.signature <= set(headers):
        return _unknown_schema_result(
            reader,
            schema=schema,
            source_file_ref=source_file_ref,
            fingerprint=fingerprint,
            limits=limits,
            reason_code=NEPSETransactionReasonCode.UNKNOWN_SCHEMA,
            detail=f"header does not match provisional schema {schema.schema_id}",
        )

    columns, column_error = _resolve_columns(headers, schema)
    if column_error:
        return _unknown_schema_result(
            reader,
            schema=schema,
            source_file_ref=source_file_ref,
            fingerprint=fingerprint,
            limits=limits,
            reason_code=NEPSETransactionReasonCode.AMBIGUOUS_TRANSACTION,
            detail=column_error,
        )

    transactions: list[NEPSEExternalTransaction] = []
    rejected: list[NEPSERejectedTransactionRow] = []
    rows_seen = 0
    try:
        for row in reader:
            row_number = reader.line_num
            _validate_row_limits(row, row_number, limits)
            if not any(cell.strip() for cell in row):
                continue
            rows_seen += 1
            if rows_seen > limits.max_rows:
                _file_error(
                    NEPSETransactionReasonCode.FILE_LIMIT_EXCEEDED,
                    f"file exceeds {limits.max_rows} data rows",
                )
            try:
                transactions.append(
                    _parse_row(
                        row,
                        row_number,
                        columns=columns,
                        schema=schema,
                        source_file_ref=source_file_ref,
                        received_at=received_at,
                        instruments=instrument_index,
                        ambiguous_symbols=ambiguous_symbols,
                    )
                )
            except _RowError as exc:
                rejected.append(
                    NEPSERejectedTransactionRow(
                        row_number=row_number,
                        reason_code=exc.reason_code,
                        field=exc.field,
                        detail=exc.detail,
                        raw_ref=_raw_ref(row),
                    )
                )
    except csv.Error as exc:
        _file_error(
            NEPSETransactionReasonCode.MALFORMED_INPUT,
            f"malformed delimited input near line {reader.line_num}: {exc}",
        )

    transactions, duplicate_rows = _classify_duplicates(transactions)
    warnings = ["SOURCE_SCHEMA_UNVERIFIED"]
    if duplicate_rows:
        warnings.append("DUPLICATE_TRANSACTIONS_RETAINED_FOR_RECONCILIATION")
    if any(
        NEPSETransactionReasonCode.UNKNOWN_TRANSACTION_TYPE
        in transaction.warnings
        for transaction in transactions
    ):
        warnings.append("UNKNOWN_TRANSACTION_TYPES_REQUIRE_RECONCILIATION")

    return NEPSETransactionImportResult(
        source=schema.source,
        source_schema=schema.schema_id,
        schema_status=NEPSETransactionSchemaStatus.SOURCE_SCHEMA_UNVERIFIED,
        source_file_ref=source_file_ref,
        source_file_fingerprint=fingerprint,
        rows_seen=rows_seen,
        accepted=len(transactions),
        rejected=len(rejected),
        duplicates=len(duplicate_rows),
        transactions=tuple(transactions),
        rejected_rows=tuple(rejected),
        duplicate_rows=tuple(duplicate_rows),
        warnings=tuple(warnings),
    )
