"""Yahoo Finance-style public historical adapter (narrow, fail-closed).

Prefer local cached files. Network is optional and off by default.
Documents adjustment methodology limitations. No credentials.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from saathi.platform.tg.historical.adapters.base import AdapterResult, HistoricalAdapter
from saathi.platform.tg.historical.adapters.local_file import LocalFileAdapter
from saathi.platform.tg.historical.models import DatasetSource


YAHOO_SCHEMA = {
    "timestamp": "Date",
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "volume": "Volume",
}


class YahooPublicHistoricalAdapter(HistoricalAdapter):
    name = "yahoo_public"
    read_only = True
    credentials_required = False
    allows_live_orders = False

    def load_from_file(
        self,
        path: str | Path,
        *,
        symbol: str = "SPY",
        schema_map: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> AdapterResult:
        p = Path(path)
        res = LocalFileAdapter().load(
            p,
            default_instrument=symbol,
            timeframe=kwargs.get("timeframe", "1d"),
            currency=kwargs.get("currency", "USD"),
            timezone_name=kwargs.get("timezone_name", "America/New_York"),
            schema_map=schema_map or YAHOO_SCHEMA,
            date_range=kwargs.get("date_range"),
            max_rows=kwargs.get("max_rows", 500_000),
        )
        if not res.ok:
            return res
        for b in res.bars:
            b.source = "yahoo_public_file"
            b.instrument = (b.instrument or symbol).upper()
        res.source = DatasetSource(
            adapter="yahoo_public_file",
            uri=str(p.resolve()),
            read_only=True,
            credentials_required=False,
            network_required=False,
            provenance_notes=[
                "Yahoo-style CSV export (local)",
                "Adjusted Close column may be mapped to close depending on schema",
                "Corporate-action methodology: operator-documented; prefer explicit CA table",
                "Rate limits: N/A for local files",
            ],
        )
        res.metadata["market"] = kwargs.get("market", "US")
        res.metadata["calendar"] = "US_RTH"
        res.metadata["adjustment_caveat"] = (
            "Yahoo adjusted series can differ from split-only adjustments; "
            "results may not match other vendors."
        )
        res.warnings.append(res.metadata["adjustment_caveat"])
        return res

    def load(self, **kwargs: Any) -> AdapterResult:
        if "path" not in kwargs:
            return AdapterResult(
                ok=False,
                error=(
                    "yahoo_network_fetch_not_enabled — supply path= to local CSV cache; "
                    "network fetch intentionally not implemented to avoid rate-limit and "
                    "license ambiguity in CI"
                ),
                source=DatasetSource(
                    adapter="yahoo_public",
                    uri="",
                    network_required=True,
                    provenance_notes=["network disabled by design"],
                ),
            )
        return self.load_from_file(kwargs.pop("path"), **kwargs)
