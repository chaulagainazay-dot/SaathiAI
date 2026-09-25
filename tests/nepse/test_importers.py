"""NEPSE-1 — portfolio file import invariants.

The teardown that motivated this work is explicit that import is file-based,
not an API integration: the user exports from Meroshare / TMS / Nepal Share and
uploads the file. That makes the parser the trust boundary, so these tests are
mostly about what happens to input that is *wrong*.

Governing rule: a row that cannot be understood is REJECTED WITH A REASON. It is
never silently dropped and never guessed at. A holdings import that quietly
loses three rows produces a portfolio that is wrong in a way nobody can see.
"""
from __future__ import annotations

import pytest

from saathi.platform.nepse.importers import (
    ImportFormat,
    ImportResult,
    detect_format,
    parse_holdings,
)


# ── Meroshare ──────────────────────────────────────────────────────────────

MEROSHARE_CSV = """S.N,Scrip,Current Balance,Previous Balance,Value of Prev Closing Price
1,NABIL,120,120,64200.00
2,NICA,50,50,42500.00
3,UPPER,1000,1000,215000.00
"""


def test_meroshare_is_detected_from_its_header():
    assert detect_format(MEROSHARE_CSV) is ImportFormat.MEROSHARE


def test_meroshare_holdings_parse():
    r = parse_holdings(MEROSHARE_CSV, source_ref="meroshare-2026-08-30.csv")
    assert r.format is ImportFormat.MEROSHARE
    assert len(r.positions) == 3
    assert r.rejected == ()
    by_symbol = {p.symbol: p for p in r.positions}
    assert by_symbol["NABIL"].quantity == "120"
    assert by_symbol["NABIL"].instrument_id == "NEPSE:NABIL"
    assert by_symbol["UPPER"].quantity == "1000"


def test_every_imported_position_carries_provenance():
    r = parse_holdings(MEROSHARE_CSV, source_ref="meroshare-2026-08-30.csv")
    for p in r.positions:
        assert p.source_format == ImportFormat.MEROSHARE.value
        assert p.source_ref == "meroshare-2026-08-30.csv"
        assert p.row_number > 0


# ── Nepal Share (TSV variant) ──────────────────────────────────────────────

NEPAL_SHARE_TSV = "Symbol\tQuantity\tWACC\tLTP\nNABIL\t120\t512.00\t535.00\nNICA\t50\t800.00\t850.00\n"


def test_nepal_share_tsv_is_detected_and_parsed():
    r = parse_holdings(NEPAL_SHARE_TSV, source_ref="nepalshare.tsv")
    assert r.format is ImportFormat.NEPAL_SHARE
    assert len(r.positions) == 2
    assert r.positions[0].average_cost == "512.00"


def test_nepal_share_csv_variant_also_parses():
    csv_variant = NEPAL_SHARE_TSV.replace("\t", ",")
    r = parse_holdings(csv_variant, source_ref="nepalshare.csv")
    assert r.format is ImportFormat.NEPAL_SHARE
    assert len(r.positions) == 2


# ── TMS ────────────────────────────────────────────────────────────────────

TMS_CSV = """Symbol,Total Quantity,Weighted Average Rate,Last Transaction Price
NABIL,120,512.00,535.00
HIDCL,300,210.50,225.00
"""


def test_tms_is_detected_and_parsed():
    r = parse_holdings(TMS_CSV, source_ref="tms-export.csv")
    assert r.format is ImportFormat.TMS
    assert {p.symbol for p in r.positions} == {"NABIL", "HIDCL"}


# ── rejection, never silent loss ───────────────────────────────────────────

def test_a_row_with_an_unparseable_symbol_is_rejected_with_a_reason():
    bad = MEROSHARE_CSV + "4,,10,10,0.00\n"
    r = parse_holdings(bad, source_ref="x.csv")
    assert len(r.positions) == 3
    assert len(r.rejected) == 1
    assert r.rejected[0].row_number == 5
    assert r.rejected[0].reason
    assert "symbol" in r.rejected[0].reason.lower()


def test_a_row_with_a_non_numeric_quantity_is_rejected():
    bad = MEROSHARE_CSV + "4,NABIL,not-a-number,10,0.00\n"
    r = parse_holdings(bad, source_ref="x.csv")
    assert len(r.rejected) == 1
    assert "quantit" in r.rejected[0].reason.lower()


def test_a_negative_quantity_is_rejected_long_only():
    bad = MEROSHARE_CSV + "4,NABIL,-5,10,0.00\n"
    r = parse_holdings(bad, source_ref="x.csv")
    assert len(r.rejected) == 1
    assert "negative" in r.rejected[0].reason.lower()


def test_accepted_plus_rejected_equals_every_data_row():
    """Nothing may vanish between the file and the result."""
    raw = MEROSHARE_CSV + "4,,10,10,0.00\n5,NABIL,bad,10,0.00\n"
    r = parse_holdings(raw, source_ref="x.csv")
    data_rows = len([ln for ln in raw.strip().splitlines()[1:] if ln.strip()])
    assert len(r.positions) + len(r.rejected) == data_rows
    assert r.rows_seen == data_rows


def test_rejected_rows_keep_the_original_line_for_the_operator():
    r = parse_holdings(MEROSHARE_CSV + "4,,10,10,0.00\n", source_ref="x.csv")
    assert "4,,10,10,0.00" in r.rejected[0].raw


# ── duplicates are surfaced, not merged silently ───────────────────────────

def test_duplicate_symbols_are_reported():
    dup = MEROSHARE_CSV + "4,NABIL,80,80,42800.00\n"
    r = parse_holdings(dup, source_ref="x.csv")
    assert "NABIL" in r.duplicate_symbols


def test_a_clean_file_reports_no_duplicates():
    assert parse_holdings(MEROSHARE_CSV, source_ref="x.csv").duplicate_symbols == ()


# ── unknown and hostile input ──────────────────────────────────────────────

def test_an_unrecognised_header_is_not_forced_into_a_known_format():
    r = parse_holdings("alpha,beta,gamma\n1,2,3\n", source_ref="mystery.csv")
    assert r.format is ImportFormat.UNKNOWN
    assert r.positions == ()
    assert r.rejected


def test_an_empty_file_is_handled_without_raising():
    r = parse_holdings("", source_ref="empty.csv")
    assert r.positions == ()
    assert r.rows_seen == 0


def test_a_header_only_file_yields_nothing_and_no_error():
    r = parse_holdings("S.N,Scrip,Current Balance\n", source_ref="h.csv")
    assert r.positions == ()
    assert r.rejected == ()


def test_formula_injection_in_a_cell_cannot_reach_a_symbol():
    """A spreadsheet export is untrusted input, not a trusted schema."""
    hostile = MEROSHARE_CSV + '4,"=cmd|\'/c calc\'!A1",10,10,0\n'
    r = parse_holdings(hostile, source_ref="x.csv")
    symbols = {p.symbol for p in r.positions}
    assert not any("=" in s or "|" in s for s in symbols)


# ── the authority boundary ─────────────────────────────────────────────────

def test_import_result_is_not_a_ledger_write():
    """Parsing produces a proposal for the ledger. It must not mutate anything."""
    r = parse_holdings(MEROSHARE_CSV, source_ref="x.csv")
    assert isinstance(r, ImportResult)
    for forbidden in ("commit", "apply", "post", "record_fill", "write", "save"):
        assert not hasattr(r, forbidden)


def test_importers_have_no_network_dependency():
    import pathlib

    import saathi.platform.nepse.importers as m

    src = pathlib.Path(m.__file__).read_text(encoding="utf-8")
    for forbidden in ("requests", "httpx", "urllib", "socket", "aiohttp"):
        assert forbidden not in src


def test_importers_cannot_reach_the_ledger():
    """No import of, or call into, the ledger. Prose in the docstring is fine —
    a documented boundary is not a dependency, so the module docstring is
    excluded and only real code is checked."""
    import ast
    import pathlib

    import saathi.platform.nepse.importers as m

    tree = ast.parse(pathlib.Path(m.__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
            imported += [a.name for a in node.names]
    assert not any("fund_ledger" in name for name in imported), imported
    assert not any("PortfolioLedgerService" in name for name in imported)

    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    } | {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not (called & {"record_fill", "post_accepted_fill", "record_deposit"})
