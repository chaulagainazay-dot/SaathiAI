"""Provisional source mappings kept separate from canonical transaction logic.

Every mapping in this module is UNVERIFIED.  It exists for deterministic
synthetic/redacted fixtures and must not be promoted until genuine header rows
are supplied by NEPSE-SCHEMA-1.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import (
    NEPSETransactionDescriptionMatch,
    NEPSETransactionSource,
    NEPSETransactionType,
)


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def normalize_description(value: str) -> str:
    return " ".join((value or "").strip().casefold().split())


@dataclass(frozen=True)
class ProvisionalTransactionSchema:
    source: NEPSETransactionSource
    schema_id: str
    signature: frozenset[str]
    column_aliases: tuple[tuple[str, tuple[str, ...]], ...]
    description_aliases: tuple[tuple[str, NEPSETransactionType], ...]

    def aliases_for(self, field_name: str) -> tuple[str, ...]:
        for name, aliases in self.column_aliases:
            if name == field_name:
                return aliases
        return ()

    def normalize_transaction_type(
        self, raw_transaction_type: str, raw_description: str
    ) -> tuple[NEPSETransactionType, NEPSETransactionDescriptionMatch, bool]:
        aliases = dict(self.description_aliases)
        matches: list[NEPSETransactionType] = []
        for candidate in (raw_transaction_type, raw_description):
            normalized = normalize_description(candidate)
            if normalized in aliases:
                matches.append(aliases[normalized])
        unique_matches = tuple(dict.fromkeys(matches))
        if len(unique_matches) > 1:
            return (
                NEPSETransactionType.UNKNOWN,
                NEPSETransactionDescriptionMatch.UNKNOWN,
                True,
            )
        if unique_matches:
            return (
                unique_matches[0],
                NEPSETransactionDescriptionMatch.EXACT_ALIAS,
                False,
            )
        return (
            NEPSETransactionType.UNKNOWN,
            NEPSETransactionDescriptionMatch.UNKNOWN,
            False,
        )


_COMMON_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("raw_description", ("description", "remarks", "narration")),
    ("settlement_date", ("settlementdate",)),
    ("available_at", ("availableat",)),
    ("gross_amount", ("grossamount",)),
    ("fees", ("fees", "fee")),
    ("commission", ("commission", "brokercommission")),
    ("sebon_fee", ("sebonfee",)),
    ("dp_charge", ("dpcharge",)),
    ("tax", ("tax",)),
    ("capital_gains_tax", ("capitalgainstax", "cgt")),
    ("other_charges", ("othercharges",)),
    ("currency", ("currency",)),
    ("external_reference", ("externalreference", "referenceno", "reference")),
    ("settlement_reference", ("settlementreference",)),
)


_PURCHASE_SALE_ALIASES: tuple[tuple[str, NEPSETransactionType], ...] = (
    ("purchase", NEPSETransactionType.BUY),
    ("sale", NEPSETransactionType.SELL),
    ("buy", NEPSETransactionType.BUY),
    ("sell", NEPSETransactionType.SELL),
    ("bonus", NEPSETransactionType.BONUS),
    ("rights", NEPSETransactionType.RIGHTS_ALLOTMENT),
    ("right share", NEPSETransactionType.RIGHTS_ALLOTMENT),
    ("rights allotment", NEPSETransactionType.RIGHTS_ALLOTMENT),
    ("ipo allotment", NEPSETransactionType.IPO_ALLOTMENT),
    ("fpo allotment", NEPSETransactionType.FPO_ALLOTMENT),
    ("transfer in", NEPSETransactionType.TRANSFER_IN),
    ("transfer out", NEPSETransactionType.TRANSFER_OUT),
    ("cash dividend", NEPSETransactionType.DIVIDEND_CASH),
    ("stock dividend", NEPSETransactionType.DIVIDEND_STOCK),
    ("merger adjustment", NEPSETransactionType.MERGER_ADJUSTMENT),
    ("split adjustment", NEPSETransactionType.SPLIT_ADJUSTMENT),
    ("corporate action", NEPSETransactionType.CORPORATE_ACTION),
    ("reversal", NEPSETransactionType.REVERSAL),
)


MEROSHARE_TRANSACTION_SCHEMA = ProvisionalTransactionSchema(
    source=NEPSETransactionSource.MEROSHARE,
    schema_id="MEROSHARE_TRANSACTION_PROVISIONAL_V1",
    signature=frozenset({"scrip", "transactiontype", "tradedate", "quantity"}),
    column_aliases=(
        ("symbol", ("scrip", "symbol")),
        ("raw_transaction_type", ("transactiontype", "type")),
        ("trade_date", ("tradedate", "transactiondate", "date")),
        ("quantity", ("quantity", "qty")),
        ("unit_price", ("unitprice", "rate", "price")),
        ("net_amount", ("netamount", "amount")),
        ("contract_number", ("contractnumber", "contractno")),
    )
    + _COMMON_COLUMNS,
    description_aliases=_PURCHASE_SALE_ALIASES,
)


TMS_TRANSACTION_SCHEMA = ProvisionalTransactionSchema(
    source=NEPSETransactionSource.TMS,
    schema_id="TMS_TRANSACTION_PROVISIONAL_V1",
    signature=frozenset(
        {"symbol", "tradetype", "tradedate", "quantity", "contractno"}
    ),
    column_aliases=(
        ("symbol", ("symbol", "scrip")),
        ("raw_transaction_type", ("tradetype", "transactiontype")),
        ("trade_date", ("tradedate", "date")),
        ("quantity", ("quantity", "qty")),
        ("unit_price", ("rate", "unitprice", "price")),
        ("net_amount", ("netamount", "amount")),
        ("contract_number", ("contractno", "contractnumber")),
    )
    + _COMMON_COLUMNS,
    description_aliases=_PURCHASE_SALE_ALIASES,
)


NEPAL_SHARE_TRANSACTION_SCHEMA = ProvisionalTransactionSchema(
    source=NEPSETransactionSource.NEPAL_SHARE,
    schema_id="NEPAL_SHARE_TRANSACTION_PROVISIONAL_V1",
    signature=frozenset({"stock", "description", "date", "qty", "referenceno"}),
    column_aliases=(
        ("symbol", ("stock", "symbol", "scrip")),
        ("raw_transaction_type", ("transactiontype", "type")),
        ("raw_description", ("description", "remarks", "narration")),
        ("trade_date", ("date", "tradedate")),
        ("quantity", ("qty", "quantity")),
        ("unit_price", ("price", "unitprice", "rate")),
        ("net_amount", ("amount", "netamount")),
        ("contract_number", ("contractno", "contractnumber")),
    )
    + tuple(item for item in _COMMON_COLUMNS if item[0] != "raw_description"),
    description_aliases=_PURCHASE_SALE_ALIASES,
)
