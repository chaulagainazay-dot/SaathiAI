"""NEPSE-TXN-1 normalized external transaction contract.

These tests intentionally use synthetic provisional exports.  They do not
claim that Meroshare, TMS, or Nepal Share's real headers have been verified.
"""
from __future__ import annotations

import ast
import csv
import io
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from saathi.platform.nepse import NepseInstrument, NepseSector
from saathi.platform.nepse.transactions import (
    DEFAULT_TRANSACTION_FILE_LIMITS,
    NEPSEExternalTransaction,
    NEPSETransactionDuplicateStatus,
    NEPSETransactionFileError,
    NEPSETransactionFileLimits,
    NEPSETransactionReasonCode,
    NEPSETransactionSchemaStatus,
    NEPSETransactionType,
    parse_meroshare_transactions,
    parse_nepal_share_transactions,
    parse_tms_transactions,
)


RECEIVED_AT = datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc)
MEROSHARE_HEADERS = (
    "Scrip",
    "Transaction Type",
    "Description",
    "Trade Date",
    "Settlement Date",
    "Available At",
    "Quantity",
    "Unit Price",
    "Gross Amount",
    "Fees",
    "Commission",
    "SEBON Fee",
    "DP Charge",
    "Tax",
    "Capital Gains Tax",
    "Other Charges",
    "Net Amount",
    "Currency",
    "External Reference",
    "Contract Number",
    "Settlement Reference",
)


def _instrument(symbol: str) -> NepseInstrument:
    return NepseInstrument.create(
        symbol=symbol,
        name=f"Synthetic {symbol}",
        sector=NepseSector.OTHERS,
        source="SYNTHETIC_TEST_FIXTURE",
    )


INSTRUMENTS = tuple(_instrument(symbol) for symbol in ("NABIL", "HIDCL", "UPPER"))


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "Scrip": "NABIL",
        "Transaction Type": "Purchase",
        "Description": "Synthetic purchase fixture",
        "Trade Date": "2026-08-30",
        "Settlement Date": "2026-09-01",
        "Available At": "",
        "Quantity": "10",
        "Unit Price": "512.10",
        "Gross Amount": "5121.00",
        "Fees": "1.25",
        "Commission": "20.50",
        "SEBON Fee": "0.77",
        "DP Charge": "25.00",
        "Tax": "",
        "Capital Gains Tax": "",
        "Other Charges": "",
        "Net Amount": "5168.52",
        "Currency": "NPR",
        "External Reference": "EXT-1",
        "Contract Number": "CON-1",
        "Settlement Reference": "SET-1",
    }
    row.update(overrides)
    return row


def _csv(rows: list[dict[str, str]], headers: tuple[str, ...] = MEROSHARE_HEADERS) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _parse(rows: list[dict[str, str]], **kwargs):
    return parse_meroshare_transactions(
        _csv(rows),
        instruments=INSTRUMENTS,
        source_file_ref="synthetic-meroshare.csv",
        received_at=RECEIVED_AT,
        **kwargs,
    )


def test_buy_normalization_uses_canonical_identity_and_decimal_money():
    result = _parse([_row()])

    assert result.schema_status is NEPSETransactionSchemaStatus.SOURCE_SCHEMA_UNVERIFIED
    assert result.accepted == 1
    assert result.rejected == 0
    transaction = result.transactions[0]
    assert isinstance(transaction, NEPSEExternalTransaction)
    assert transaction.instrument_id == "NEPSE:NABIL"
    assert transaction.transaction_type is NEPSETransactionType.BUY
    assert transaction.raw_transaction_type == "Purchase"
    assert transaction.quantity == Decimal("10")
    assert transaction.unit_price == Decimal("512.10")
    assert transaction.gross_amount == Decimal("5121.00")
    assert transaction.fees == Decimal("1.25")
    assert transaction.net_amount == Decimal("5168.52")
    assert transaction.currency == "NPR"


def test_sell_uses_positive_unsigned_quantity():
    transaction = _parse(
        [_row(**{"Transaction Type": "Sale", "Quantity": "7"})]
    ).transactions[0]

    assert transaction.transaction_type is NEPSETransactionType.SELL
    assert transaction.quantity == Decimal("7")
    assert transaction.quantity > 0


@pytest.mark.parametrize(
    ("raw_type", "expected"),
    [
        ("Bonus", NEPSETransactionType.BONUS),
        ("Rights Allotment", NEPSETransactionType.RIGHTS_ALLOTMENT),
        ("IPO Allotment", NEPSETransactionType.IPO_ALLOTMENT),
        ("Transfer In", NEPSETransactionType.TRANSFER_IN),
        ("Transfer Out", NEPSETransactionType.TRANSFER_OUT),
    ],
)
def test_supported_non_trade_types_are_normalized_without_accounting_treatment(
    raw_type, expected
):
    transaction = _parse(
        [
            _row(
                **{
                    "Transaction Type": raw_type,
                    "Unit Price": "" if expected is not NEPSETransactionType.RIGHTS_ALLOTMENT else "100",
                    "Gross Amount": "",
                    "Net Amount": "",
                }
            )
        ]
    ).transactions[0]

    assert transaction.transaction_type is expected
    assert transaction.quantity == Decimal("10")


def test_unknown_description_is_preserved_and_not_forced_to_a_known_type():
    transaction = _parse(
        [
            _row(
                **{
                    "Transaction Type": "Mystery Activity",
                    "Description": "Original opaque source description",
                    "Unit Price": "",
                }
            )
        ]
    ).transactions[0]

    assert transaction.transaction_type is NEPSETransactionType.UNKNOWN
    assert transaction.raw_transaction_type == "Mystery Activity"
    assert transaction.raw_description == "Original opaque source description"
    assert NEPSETransactionReasonCode.UNKNOWN_TRANSACTION_TYPE in transaction.warnings


def test_conflicting_known_type_and_description_aliases_are_rejected_as_ambiguous():
    result = _parse(
        [
            _row(
                **{
                    "Transaction Type": "Purchase",
                    "Description": "Sale",
                }
            )
        ]
    )

    assert result.rejected == 1
    assert (
        result.rejected_rows[0].reason_code
        is NEPSETransactionReasonCode.AMBIGUOUS_TRANSACTION
    )


def test_duplicate_rows_are_retained_and_surfaced():
    result = _parse([_row(), _row()])

    assert result.accepted == 2
    assert result.rejected == 0
    assert result.duplicates == 1
    assert result.transactions[0].duplicate_status is NEPSETransactionDuplicateStatus.UNIQUE
    assert (
        result.transactions[1].duplicate_status
        is NEPSETransactionDuplicateStatus.EXACT_DUPLICATE
    )
    assert result.transactions[0].transaction_id == result.transactions[1].transaction_id


def test_same_looking_transactions_with_distinct_external_refs_are_distinct():
    result = _parse(
        [
            _row(**{"External Reference": "EXT-A", "Contract Number": "CON-A"}),
            _row(**{"External Reference": "EXT-B", "Contract Number": "CON-B"}),
        ]
    )

    assert result.duplicates == 0
    assert len({transaction.transaction_id for transaction in result.transactions}) == 2


def test_same_external_reference_with_conflicting_facts_is_surfaced():
    result = _parse([_row(), _row(**{"Quantity": "11"})])

    assert result.duplicates == 1
    assert (
        result.transactions[1].duplicate_status
        is NEPSETransactionDuplicateStatus.CONFLICTING_DUPLICATE
    )


def test_same_reference_with_conflicting_available_at_is_not_an_exact_duplicate():
    result = _parse(
        [
            _row(**{"Available At": "2026-08-30T12:00:00+05:45"}),
            _row(**{"Available At": "2026-08-30T13:00:00+05:45"}),
        ]
    )

    assert result.duplicates == 1
    assert (
        result.transactions[1].duplicate_status
        is NEPSETransactionDuplicateStatus.CONFLICTING_DUPLICATE
    )


@pytest.mark.parametrize(
    ("symbol", "reason"),
    [
        ("...", NEPSETransactionReasonCode.INVALID_SYMBOL),
        ("NOTLISTED", NEPSETransactionReasonCode.UNKNOWN_INSTRUMENT),
    ],
)
def test_invalid_and_unknown_instruments_are_distinguished(symbol, reason):
    result = _parse([_row(Scrip=symbol)])

    assert result.accepted == 0
    assert result.rejected == 1
    assert result.rejected_rows[0].reason_code is reason


@pytest.mark.parametrize("quantity", ["0", "-1", "0.5"])
def test_zero_negative_and_fractional_quantities_are_rejected(quantity):
    result = _parse([_row(Quantity=quantity)])

    assert result.rejected == 1
    assert result.rejected_rows[0].reason_code is NEPSETransactionReasonCode.INVALID_QUANTITY


def test_missing_price_is_rejected_when_required_for_buy_or_sell():
    for transaction_type in ("Purchase", "Sale"):
        result = _parse([_row(**{"Transaction Type": transaction_type, "Unit Price": ""})])
        assert result.rejected == 1
        assert (
            result.rejected_rows[0].reason_code
            is NEPSETransactionReasonCode.MISSING_REQUIRED_FIELD
        )


def test_missing_price_is_legitimate_for_a_bonus():
    result = _parse(
        [
            _row(
                **{
                    "Transaction Type": "Bonus",
                    "Unit Price": "",
                    "Gross Amount": "",
                    "Net Amount": "",
                }
            )
        ]
    )

    assert result.accepted == 1
    assert result.transactions[0].unit_price is None
    assert result.transactions[0].gross_amount is None


def test_decimal_values_are_exact_and_absent_money_is_not_fabricated_as_zero():
    result = _parse(
        [
            _row(
                **{
                    "Unit Price": "0.10",
                    "Gross Amount": "1.00",
                    "Fees": "0.20",
                    "Tax": "",
                }
            )
        ]
    )
    transaction = result.transactions[0]

    assert transaction.unit_price == Decimal("0.10")
    assert transaction.fees + transaction.unit_price == Decimal("0.30")
    assert transaction.tax is None


@pytest.mark.parametrize("bad_amount", ["not-money", "NaN", "Infinity", "-Infinity"])
def test_non_finite_or_non_numeric_money_is_rejected(bad_amount):
    result = _parse([_row(**{"Gross Amount": bad_amount})])

    assert result.rejected == 1
    assert result.rejected_rows[0].reason_code is NEPSETransactionReasonCode.INVALID_AMOUNT


def test_rejection_detail_does_not_echo_untrusted_numeric_cell_content():
    secret_like = "TOP_SECRET_VALUE_SHOULD_NOT_TRAVEL"
    result = _parse([_row(**{"Gross Amount": secret_like})])

    assert result.rejected == 1
    assert secret_like not in result.rejected_rows[0].detail


@pytest.mark.parametrize("bad_amount", ["1E19", "0.000000001"])
def test_numeric_magnitude_and_scale_are_bounded(bad_amount):
    result = _parse([_row(**{"Gross Amount": bad_amount})])

    assert result.rejected == 1
    assert result.rejected_rows[0].reason_code is NEPSETransactionReasonCode.INVALID_AMOUNT


@pytest.mark.parametrize(
    ("trade_date", "reason"),
    [
        ("01/02/2026", NEPSETransactionReasonCode.AMBIGUOUS_DATE),
        ("2026-02-30", NEPSETransactionReasonCode.INVALID_DATE),
        ("2083/05/14", NEPSETransactionReasonCode.UNSUPPORTED_DATE_FORMAT),
    ],
)
def test_ambiguous_invalid_and_unsupported_dates_fail_closed(trade_date, reason):
    result = _parse([_row(**{"Trade Date": trade_date})])

    assert result.rejected == 1
    assert result.rejected_rows[0].reason_code is reason


@pytest.mark.parametrize("hostile", ["=NABIL", "+NABIL", "-NABIL", "@NABIL"])
def test_formula_injection_strings_are_rejected_before_symbol_normalization(hostile):
    result = _parse([_row(Scrip=hostile)])

    assert result.accepted == 0
    assert result.rejected_rows[0].reason_code is NEPSETransactionReasonCode.MALFORMED_INPUT


def test_huge_cells_fail_explicitly_before_a_partial_result_can_escape():
    huge = "x" * (DEFAULT_TRANSACTION_FILE_LIMITS.max_cell_length + 1)

    with pytest.raises(NEPSETransactionFileError) as exc:
        _parse([_row(Description=huge)])

    assert exc.value.reason_code is NEPSETransactionReasonCode.FILE_LIMIT_EXCEEDED


def test_file_row_and_column_limits_each_fail_explicitly():
    cases = (
        NEPSETransactionFileLimits(
            max_file_size_bytes=64,
            max_rows=50_000,
            max_columns=64,
            max_cell_length=4_096,
        ),
        NEPSETransactionFileLimits(
            max_file_size_bytes=5 * 1024 * 1024,
            max_rows=1,
            max_columns=64,
            max_cell_length=4_096,
        ),
        NEPSETransactionFileLimits(
            max_file_size_bytes=5 * 1024 * 1024,
            max_rows=50_000,
            max_columns=2,
            max_cell_length=4_096,
        ),
    )
    payloads = (_csv([_row()]), _csv([_row(), _row()]), _csv([_row()]))

    for limits, payload in zip(cases, payloads, strict=True):
        with pytest.raises(NEPSETransactionFileError) as exc:
            parse_meroshare_transactions(
                payload,
                instruments=INSTRUMENTS,
                source_file_ref="synthetic.csv",
                received_at=RECEIVED_AT,
                limits=limits,
            )
        assert exc.value.reason_code is NEPSETransactionReasonCode.FILE_LIMIT_EXCEEDED


def test_every_returned_result_accounts_for_every_data_row():
    result = _parse(
        [
            _row(),
            _row(Scrip="...", **{"External Reference": "EXT-2"}),
            _row(Quantity="0", **{"External Reference": "EXT-3"}),
        ]
    )

    assert result.accepted + result.rejected == result.rows_seen == 3
    assert len(result.transactions) == result.accepted
    assert len(result.rejected_rows) == result.rejected


def test_schema_mismatch_rejects_every_row_and_keeps_source_unverified():
    raw = "alpha,beta,gamma\n1,2,3\n4,5,6\n"
    result = parse_meroshare_transactions(
        raw,
        instruments=INSTRUMENTS,
        source_file_ref="synthetic-meroshare.csv",
        received_at=RECEIVED_AT,
    )

    assert result.schema_status is NEPSETransactionSchemaStatus.UNKNOWN_SCHEMA
    assert result.rows_seen == result.rejected == 2
    assert result.accepted == 0
    assert {row.reason_code for row in result.rejected_rows} == {
        NEPSETransactionReasonCode.UNKNOWN_SCHEMA
    }


def test_duplicate_headers_fail_closed_as_an_ambiguous_schema():
    headers = MEROSHARE_HEADERS + ("Scrip",)
    result = parse_meroshare_transactions(
        _csv([_row()], headers=headers),
        instruments=INSTRUMENTS,
        source_file_ref="synthetic-meroshare.csv",
        received_at=RECEIVED_AT,
    )

    assert result.schema_status is NEPSETransactionSchemaStatus.UNKNOWN_SCHEMA
    assert result.rejected_rows[0].reason_code is NEPSETransactionReasonCode.AMBIGUOUS_TRANSACTION


def test_formula_prefixed_header_is_a_whole_file_malformed_input_refusal():
    headers = ("=Scrip",) + MEROSHARE_HEADERS[1:]
    row = _row()
    row["=Scrip"] = row["Scrip"]

    with pytest.raises(NEPSETransactionFileError) as exc:
        parse_meroshare_transactions(
            _csv([row], headers=headers),
            instruments=INSTRUMENTS,
            source_file_ref="synthetic-meroshare.csv",
            received_at=RECEIVED_AT,
        )

    assert exc.value.reason_code is NEPSETransactionReasonCode.MALFORMED_INPUT


def test_transaction_id_is_stable_when_an_export_reorders_rows():
    nabil = _row(**{"External Reference": "", "Contract Number": "", "Settlement Reference": ""})
    hidcl = _row(
        Scrip="HIDCL",
        **{
            "External Reference": "",
            "Contract Number": "",
            "Settlement Reference": "",
        },
    )
    first = _parse([nabil, hidcl])
    second = _parse([hidcl, nabil])

    ids_first = {transaction.raw_symbol: transaction.transaction_id for transaction in first.transactions}
    ids_second = {transaction.raw_symbol: transaction.transaction_id for transaction in second.transactions}
    assert ids_first == ids_second


def test_uploaded_file_time_semantics_do_not_invent_available_at():
    transaction = _parse([_row()]).transactions[0]

    assert transaction.trade_date.isoformat() == "2026-08-30"
    assert transaction.settlement_date.isoformat() == "2026-09-01"
    assert transaction.available_at is None
    assert transaction.received_at == RECEIVED_AT


def test_explicit_available_at_is_preserved_when_temporally_valid():
    available_at = "2026-08-30T15:00:00+05:45"
    transaction = _parse([_row(**{"Available At": available_at})]).transactions[0]

    assert transaction.available_at.isoformat() == available_at
    assert transaction.available_at <= transaction.received_at


def test_available_at_after_received_at_is_rejected_not_rewritten():
    result = _parse([_row(**{"Available At": "2026-09-02T12:00:00+05:45"})])

    assert result.rejected_rows[0].reason_code is NEPSETransactionReasonCode.INVALID_DATE


def test_received_at_must_be_timezone_aware():
    with pytest.raises(NEPSETransactionFileError) as exc:
        parse_meroshare_transactions(
            _csv([_row()]),
            instruments=INSTRUMENTS,
            source_file_ref="synthetic-meroshare.csv",
            received_at=datetime(2026, 8, 31, 8, 0),
        )

    assert exc.value.reason_code is NEPSETransactionReasonCode.MALFORMED_INPUT


def test_all_three_source_adapters_are_provisional_and_unverified():
    tms = parse_tms_transactions(
        "Symbol,Trade Type,Trade Date,Quantity,Rate,Net Amount,Contract No\n"
        "NABIL,BUY,2026-08-30,10,512.10,5168.52,TMS-CON-1\n",
        instruments=INSTRUMENTS,
        source_file_ref="synthetic-tms.csv",
        received_at=RECEIVED_AT,
    )
    nepal_share = parse_nepal_share_transactions(
        "Stock,Description,Date,Qty,Price,Amount,Reference No\n"
        "NABIL,Purchase,2026-08-30,10,512.10,5168.52,NS-REF-1\n",
        instruments=INSTRUMENTS,
        source_file_ref="synthetic-nepal-share.csv",
        received_at=RECEIVED_AT,
    )

    for result in (tms, nepal_share):
        assert result.schema_status is NEPSETransactionSchemaStatus.SOURCE_SCHEMA_UNVERIFIED
        assert result.accepted == 1
        assert result.transactions[0].transaction_type is NEPSETransactionType.BUY


def test_source_file_reference_cannot_be_a_traversal_path():
    with pytest.raises(NEPSETransactionFileError) as exc:
        parse_meroshare_transactions(
            _csv([_row()]),
            instruments=INSTRUMENTS,
            source_file_ref="../../operator-secrets.csv",
            received_at=RECEIVED_AT,
        )

    assert exc.value.reason_code is NEPSETransactionReasonCode.MALFORMED_INPUT


@pytest.mark.parametrize("raw", [b"\xff\xfeinvalid", "Scrip\x00,Transaction Type\n"])
def test_malformed_encoding_and_embedded_nulls_fail_explicitly(raw):
    with pytest.raises(NEPSETransactionFileError) as exc:
        parse_meroshare_transactions(
            raw,
            instruments=INSTRUMENTS,
            source_file_ref="synthetic.csv",
            received_at=RECEIVED_AT,
        )

    assert exc.value.reason_code is NEPSETransactionReasonCode.MALFORMED_INPUT


def test_transaction_import_package_has_zero_ledger_or_execution_authority():
    import saathi.platform.nepse.transactions as transactions

    package_root = Path(transactions.__file__).parent
    forbidden_modules = {
        "fund_ledger",
        "execution",
        "execution_gateway",
        "oms",
        "trading_guardian",
        "portfolio_construction",
        "portfolio_risk_engine",
    }
    forbidden_names = {
        "ExecutionGateway",
        "PortfolioLedgerService",
        "PortfolioConstructionEngine",
        "PortfolioRiskEngine",
        "TradingGuardian",
        "record_fill",
        "append_event",
        "submit_order",
        "place_order",
    }

    for path in package_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports: list[str] = []
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
        assert not any(part in module for module in imports for part in forbidden_modules), imports
        assert not (names & forbidden_names), (path, names & forbidden_names)


def test_transaction_import_package_has_no_network_dependency():
    import saathi.platform.nepse.transactions as transactions

    source = "\n".join(
        path.read_text(encoding="utf-8") for path in Path(transactions.__file__).parent.glob("*.py")
    )
    for forbidden in ("requests", "httpx", "urllib", "socket", "aiohttp"):
        assert forbidden not in source
