"""Source-labelled adapters over the canonical transaction parser.

These adapters select provisional mappings only.  They do not read paths,
connect to providers, or upgrade a source to verified compatibility.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from saathi.platform.nepse.instruments import NepseInstrument

from .models import (
    DEFAULT_TRANSACTION_FILE_LIMITS,
    NEPSETransactionFileLimits,
    NEPSETransactionImportResult,
)
from .parser import parse_transactions
from .source_schemas import (
    MEROSHARE_TRANSACTION_SCHEMA,
    NEPAL_SHARE_TRANSACTION_SCHEMA,
    TMS_TRANSACTION_SCHEMA,
)


def parse_meroshare_transactions(
    data: str | bytes,
    *,
    instruments: Iterable[NepseInstrument],
    source_file_ref: str = "",
    received_at: datetime | None = None,
    limits: NEPSETransactionFileLimits = DEFAULT_TRANSACTION_FILE_LIMITS,
) -> NEPSETransactionImportResult:
    return parse_transactions(
        data,
        schema=MEROSHARE_TRANSACTION_SCHEMA,
        instruments=instruments,
        source_file_ref=source_file_ref,
        received_at=received_at,
        limits=limits,
    )


def parse_tms_transactions(
    data: str | bytes,
    *,
    instruments: Iterable[NepseInstrument],
    source_file_ref: str = "",
    received_at: datetime | None = None,
    limits: NEPSETransactionFileLimits = DEFAULT_TRANSACTION_FILE_LIMITS,
) -> NEPSETransactionImportResult:
    return parse_transactions(
        data,
        schema=TMS_TRANSACTION_SCHEMA,
        instruments=instruments,
        source_file_ref=source_file_ref,
        received_at=received_at,
        limits=limits,
    )


def parse_nepal_share_transactions(
    data: str | bytes,
    *,
    instruments: Iterable[NepseInstrument],
    source_file_ref: str = "",
    received_at: datetime | None = None,
    limits: NEPSETransactionFileLimits = DEFAULT_TRANSACTION_FILE_LIMITS,
) -> NEPSETransactionImportResult:
    return parse_transactions(
        data,
        schema=NEPAL_SHARE_TRANSACTION_SCHEMA,
        instruments=instruments,
        source_file_ref=source_file_ref,
        received_at=received_at,
        limits=limits,
    )
