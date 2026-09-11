"""NEPSE portfolio file importers — Meroshare, TMS, Nepal Share.

There is no live brokerage connection into SaathiOS and this module does not
create one. Holdings enter the way a Nepali retail investor actually has them:
by exporting a file from Meroshare (the CDS depository portal), from TMS (the
broker's own trading portal), or from Nepal Share, and importing that file.

Trust model
-----------
An uploaded spreadsheet is **untrusted input**, not a trusted schema. Three
consequences are enforced here:

1. **Nothing is silently lost.** Every data row ends up either in ``positions``
   or in ``rejected`` with a reason and its original text.
   ``len(positions) + len(rejected) == rows_seen`` is a tested invariant. A
   holdings file that quietly drops three rows produces a portfolio that is
   wrong in a way nobody can see.
2. **Nothing is guessed.** An unparseable symbol is rejected rather than
   coerced into some other real security. An unrecognised header is reported as
   ``UNKNOWN`` rather than forced into the closest known format.
3. **Cell content cannot become structure.** Symbols are normalised through
   the instrument master, which strips everything outside ``[A-Z0-9]``, so a
   formula-injection payload cannot survive into an instrument identity.

Authority
---------
Parsing produces a *proposal*. This module holds no ledger, execution, or
approval authority, performs no network I/O, and cannot reach
``PortfolioLedgerService``. Applying an ``ImportResult`` to the Canonical Fund
Ledger is a separate, deliberate step outside this module.

Schema status
-------------
**The column mappings below are UNVERIFIED.** They are derived from the public
description of each export, not from a real file. Each source's aliases must be
pinned against one genuine export before this importer is certified for
operator use. Until then a mismatched header degrades to ``UNKNOWN`` with every
row rejected — loudly wrong rather than quietly wrong.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Iterable

from saathi.platform.nepse.instruments import instrument_id_for, normalize_symbol

__all__ = [
    "ImportFormat",
    "ImportedPosition",
    "RejectedRow",
    "ImportResult",
    "detect_format",
    "parse_holdings",
]


class ImportFormat(str, Enum):
    MEROSHARE = "MEROSHARE"
    TMS = "TMS"
    NEPAL_SHARE = "NEPAL_SHARE"
    UNKNOWN = "UNKNOWN"


def _norm_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


# Column aliases per source. UNVERIFIED — see module docstring.
_SYMBOL_ALIASES = {
    ImportFormat.MEROSHARE: ("scrip", "scripname", "symbol", "stocksymbol"),
    ImportFormat.TMS: ("symbol", "scrip", "securityname"),
    ImportFormat.NEPAL_SHARE: ("symbol", "scrip", "stock"),
}
_QUANTITY_ALIASES = {
    ImportFormat.MEROSHARE: ("currentbalance", "balance", "quantity", "totalquantity"),
    ImportFormat.TMS: ("totalquantity", "quantity", "qty", "currentbalance"),
    ImportFormat.NEPAL_SHARE: ("quantity", "qty", "units", "totalquantity"),
}
_COST_ALIASES = {
    ImportFormat.MEROSHARE: ("valueofprevclosingprice",),
    ImportFormat.TMS: ("weightedaveragerate", "wacc", "averagerate", "avgrate"),
    ImportFormat.NEPAL_SHARE: ("wacc", "weightedaveragerate", "averagecost", "avgcost"),
}
_LTP_ALIASES = ("lasttransactionprice", "ltp", "lastprice", "closingprice")

# A header fingerprint that identifies a source unambiguously.
_FORMAT_SIGNATURES: tuple[tuple[ImportFormat, frozenset[str]], ...] = (
    (ImportFormat.MEROSHARE, frozenset({"scrip", "currentbalance"})),
    (ImportFormat.TMS, frozenset({"totalquantity", "weightedaveragerate"})),
    (ImportFormat.NEPAL_SHARE, frozenset({"symbol", "quantity", "wacc"})),
)


@dataclass(frozen=True)
class ImportedPosition:
    """One holding read from a file. Reference only — not a ledger entry."""

    instrument_id: str
    symbol: str
    quantity: str
    average_cost: str = ""
    last_price: str = ""
    source_format: str = ""
    source_ref: str = ""
    row_number: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument_id": self.instrument_id,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "average_cost": self.average_cost,
            "last_price": self.last_price,
            "source_format": self.source_format,
            "source_ref": self.source_ref,
            "row_number": self.row_number,
        }


@dataclass(frozen=True)
class RejectedRow:
    """A row that could not be understood. Kept verbatim for the operator."""

    row_number: int
    reason: str
    raw: str

    def to_dict(self) -> dict[str, Any]:
        return {"row_number": self.row_number, "reason": self.reason, "raw": self.raw}


@dataclass(frozen=True)
class ImportResult:
    """Outcome of parsing one file. A proposal, never an applied change."""

    format: ImportFormat
    positions: tuple[ImportedPosition, ...] = ()
    rejected: tuple[RejectedRow, ...] = ()
    rows_seen: int = 0
    duplicate_symbols: tuple[str, ...] = ()
    source_ref: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def accepted_count(self) -> int:
        return len(self.positions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format.value,
            "positions": [p.to_dict() for p in self.positions],
            "rejected": [r.to_dict() for r in self.rejected],
            "rows_seen": self.rows_seen,
            "duplicate_symbols": list(self.duplicate_symbols),
            "source_ref": self.source_ref,
            "warnings": list(self.warnings),
        }


def _sniff_delimiter(text: str) -> str:
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    return "\t" if first.count("\t") > first.count(",") else ","


def _headers(text: str) -> list[str]:
    delim = _sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    for row in reader:
        if any(c.strip() for c in row):
            return [_norm_header(c) for c in row]
    return []


def detect_format(text: str) -> ImportFormat:
    """Identify the source from its header fingerprint. Never guesses."""
    present = set(_headers(text))
    if not present:
        return ImportFormat.UNKNOWN
    for fmt, signature in _FORMAT_SIGNATURES:
        if signature <= present:
            return fmt
    return ImportFormat.UNKNOWN


def _pick(headers: list[str], aliases: Iterable[str]) -> int | None:
    for alias in aliases:
        if alias in headers:
            return headers.index(alias)
    return None


def _decimal_or_none(raw: str) -> Decimal | None:
    cleaned = (raw or "").strip().replace(",", "").replace(" ", "")
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def parse_holdings(text: str, *, source_ref: str = "") -> ImportResult:
    """Parse a holdings export into a typed, fully-accounted result.

    Never raises on bad content: a malformed row becomes a ``RejectedRow``.
    """
    if not (text or "").strip():
        return ImportResult(format=ImportFormat.UNKNOWN, rows_seen=0, source_ref=source_ref)

    fmt = detect_format(text)
    delim = _sniff_delimiter(text)
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim)]
    rows = [r for r in rows if any((c or "").strip() for c in r)]
    if not rows:
        return ImportResult(format=fmt, rows_seen=0, source_ref=source_ref)

    headers = [_norm_header(c) for c in rows[0]]
    data_rows = rows[1:]

    if fmt is ImportFormat.UNKNOWN:
        rejected = tuple(
            RejectedRow(
                row_number=i + 2,
                reason=(
                    "unrecognised file format: header does not match Meroshare, "
                    "TMS, or Nepal Share"
                ),
                raw=delim.join(row),
            )
            for i, row in enumerate(data_rows)
        )
        return ImportResult(
            format=fmt,
            rejected=rejected,
            rows_seen=len(data_rows),
            source_ref=source_ref,
            warnings=("format not recognised; no row was imported",),
        )

    sym_idx = _pick(headers, _SYMBOL_ALIASES[fmt])
    qty_idx = _pick(headers, _QUANTITY_ALIASES[fmt])
    cost_idx = _pick(headers, _COST_ALIASES[fmt])
    ltp_idx = _pick(headers, _LTP_ALIASES)

    positions: list[ImportedPosition] = []
    rejected: list[RejectedRow] = []
    seen: dict[str, int] = {}
    duplicates: list[str] = []

    for offset, row in enumerate(data_rows):
        row_number = offset + 2
        raw_line = delim.join(row)

        def cell(idx: int | None) -> str:
            if idx is None or idx >= len(row):
                return ""
            return (row[idx] or "").strip()

        if sym_idx is None or qty_idx is None:
            rejected.append(RejectedRow(row_number, "missing symbol or quantity column", raw_line))
            continue

        try:
            symbol = normalize_symbol(cell(sym_idx))
        except (ValueError, TypeError):
            rejected.append(
                RejectedRow(row_number, f"unusable symbol {cell(sym_idx)!r}", raw_line)
            )
            continue

        qty = _decimal_or_none(cell(qty_idx))
        if qty is None:
            rejected.append(
                RejectedRow(row_number, f"non-numeric quantity {cell(qty_idx)!r}", raw_line)
            )
            continue
        if qty < 0:
            rejected.append(
                RejectedRow(row_number, f"negative quantity {qty} — NEPSE is long-only", raw_line)
            )
            continue

        if symbol in seen:
            duplicates.append(symbol)
        seen[symbol] = row_number

        positions.append(
            ImportedPosition(
                instrument_id=instrument_id_for(symbol),
                symbol=symbol,
                quantity=str(qty),
                average_cost=cell(cost_idx),
                last_price=cell(ltp_idx),
                source_format=fmt.value,
                source_ref=source_ref,
                row_number=row_number,
            )
        )

    warnings: list[str] = []
    if duplicates:
        warnings.append(
            f"{len(duplicates)} duplicate symbol(s) present; rows are kept separate, "
            "not merged — resolve before applying to the ledger"
        )

    return ImportResult(
        format=fmt,
        positions=tuple(positions),
        rejected=tuple(rejected),
        rows_seen=len(data_rows),
        duplicate_symbols=tuple(dict.fromkeys(duplicates)),
        source_ref=source_ref,
        warnings=tuple(warnings),
    )
