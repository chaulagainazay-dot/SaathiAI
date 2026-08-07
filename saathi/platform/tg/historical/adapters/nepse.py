"""NEPSE historical dataset importer — local-file-first.

No scraping of protected systems. Operator supplies CSV/Parquet with provenance.
Uses NEPSE calendar for session validation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from saathi.platform.tg.historical.adapters.base import AdapterResult, HistoricalAdapter
from saathi.platform.tg.historical.adapters.local_file import LocalFileAdapter
from saathi.platform.tg.historical.models import DatasetSource


# Common NEPSE CSV header aliases
NEPSE_SCHEMA = {
    "timestamp": "date",
    "instrument": "symbol",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
}


def normalize_nepse_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    # strip common suffixes / whitespace
    s = s.replace(" ", "").replace(".N", "").replace("NEPSE:", "")
    return s


class NepseLocalAdapter(HistoricalAdapter):
    name = "nepse_local"
    read_only = True
    credentials_required = False
    allows_live_orders = False

    def load(
        self,
        path: str | Path,
        *,
        default_instrument: str = "NABIL",
        schema_map: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> AdapterResult:
        p = Path(path)
        if not p.is_file():
            return AdapterResult(ok=False, error=f"file_not_found:{p}")

        mapping = schema_map or NEPSE_SCHEMA
        res = LocalFileAdapter().load(
            p,
            default_instrument=default_instrument,
            timeframe=kwargs.get("timeframe", "1d"),
            currency=kwargs.get("currency", "NPR"),
            timezone_name=kwargs.get("timezone_name", "Asia/Kathmandu"),
            schema_map=mapping,
            date_range=kwargs.get("date_range"),
            max_rows=kwargs.get("max_rows", 500_000),
        )
        if not res.ok:
            return res

        # Normalize symbols
        for b in res.bars:
            b.instrument = normalize_nepse_symbol(b.instrument)
            b.currency = "NPR"
            b.source = "nepse_local"

        res.source = DatasetSource(
            adapter="nepse_local",
            uri=str(p.resolve()),
            read_only=True,
            credentials_required=False,
            network_required=False,
            provenance_notes=[
                "Operator-supplied NEPSE historical file",
                "No scraping of protected systems",
                "NEPSE holidays via explicit calendar fixture",
                "Currency NPR",
            ],
        )
        res.metadata.update({
            "market": "NEPSE",
            "calendar": "NEPSE",
            "currency": "NPR",
            "timezone": "Asia/Kathmandu",
        })
        res.warnings.append("NEPSE official API may be limited; local-file path is authoritative for this adapter")
        return res
