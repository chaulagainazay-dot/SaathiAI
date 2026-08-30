"""NEPSE venue package — reference data, calendar, and file-based import.

Read-only by construction. This package holds no execution, approval, risk, or
ledger-mutation authority: imported holdings are handed to the Canonical Fund
Ledger, which remains the sole books authority.

No network I/O. NEPSE market data enters SaathiOS through operator-supplied
files with provenance, never by scraping a protected system.
"""
from __future__ import annotations

from saathi.platform.nepse.instruments import (
    NEPSE_CURRENCY,
    NEPSE_TIMEZONE,
    NEPSE_VENUE,
    NepseInstrument,
    NepseSector,
    instrument_id_for,
    normalize_symbol,
    sector_from_code,
)

__all__ = [
    "NEPSE_VENUE",
    "NEPSE_CURRENCY",
    "NEPSE_TIMEZONE",
    "NepseInstrument",
    "NepseSector",
    "instrument_id_for",
    "normalize_symbol",
    "sector_from_code",
]
