"""Binance public historical market-data adapter (read-only).

Allowed: historical candles / exchange metadata labels.
Forbidden: account access, orders, balances, positions, credentials, private endpoints.

Default path is local-file import of exported public klines (tests never require network).
Optional network fetch is credential-free public klines only and is disabled by default.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from saathi.platform.tg.historical.adapters.base import AdapterResult, HistoricalAdapter
from saathi.platform.tg.historical.adapters.local_file import LocalFileAdapter
from saathi.platform.tg.historical.models import DatasetSource


# Public klines only — no private API base
PUBLIC_KLINES = "https://api.binance.com/api/v3/klines"
FORBIDDEN_PATH_MARKERS = (
    "/api/v3/order",
    "/api/v3/account",
    "/sapi/",
    "withdraw",
    "balance",
    "position",
    "listenKey",
)


class BinancePublicHistoricalAdapter(HistoricalAdapter):
    name = "binance_public"
    read_only = True
    credentials_required = False
    allows_live_orders = False

    def load_from_file(self, path: str | Path, **kwargs: Any) -> AdapterResult:
        """Preferred: operator-exported public kline CSV/JSONL/Parquet."""
        res = LocalFileAdapter().load(path, default_instrument=kwargs.get("symbol", "BTCUSDT"), **{
            k: v for k, v in kwargs.items() if k in (
                "timeframe", "currency", "timezone_name", "schema_map", "date_range", "max_rows",
            )
        })
        if res.ok and res.source:
            res.source = DatasetSource(
                adapter="binance_public_file",
                uri=str(path),
                read_only=True,
                credentials_required=False,
                network_required=False,
                provenance_notes=[
                    "Binance public historical export (local file)",
                    "No account endpoints",
                    "No order capability",
                ],
            )
            for b in res.bars:
                b.source = "binance_public_file"
                b.currency = kwargs.get("currency", "USDT")
        res.metadata["market"] = "BINANCE"
        res.metadata["calendar"] = "BINANCE_24_7"
        return res

    def load_public_klines(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        limit: int = 100,
        allow_network: bool = False,
        timeout_sec: float = 10.0,
    ) -> AdapterResult:
        """Optional public klines fetch — OFF by default; tests use files."""
        if not allow_network:
            return AdapterResult(
                ok=False,
                error="network_disabled — pass allow_network=True or use load_from_file",
                source=DatasetSource(
                    adapter="binance_public",
                    uri=PUBLIC_KLINES,
                    network_required=True,
                    provenance_notes=["network fetch disabled by default"],
                ),
            )
        # Hard reject any attempt to hit private paths
        url = f"{PUBLIC_KLINES}?symbol={symbol.upper()}&interval={interval}&limit={min(int(limit), 1000)}"
        for marker in FORBIDDEN_PATH_MARKERS:
            if marker in url:
                return AdapterResult(ok=False, error=f"forbidden_path:{marker}")
        try:
            req = Request(url, headers={"User-Agent": "SaathiOS-TradingGuardian-Research/1.0 (read-only)"})
            with urlopen(req, timeout=timeout_sec) as resp:  # nosec B310 — public read-only
                raw = resp.read()
            data = json.loads(raw.decode("utf-8"))
        except (URLError, HTTPError, TimeoutError, json.JSONDecodeError, OSError) as e:
            return AdapterResult(ok=False, error=f"fetch_failed:{type(e).__name__}:{e}"[:240])

        from decimal import Decimal
        from saathi.platform.tg.historical.models import AdjustedPriceBar

        bars: list[AdjustedPriceBar] = []
        if not isinstance(data, list):
            return AdapterResult(ok=False, error="unexpected_klines_payload")
        for row in data:
            # [open_time, o, h, l, c, volume, close_time, ...]
            try:
                ts = float(row[0]) / 1000.0
                o, h, l, c, v = (Decimal(str(row[i])) for i in (1, 2, 3, 4, 5))
                bars.append(AdjustedPriceBar(
                    instrument=symbol.upper(),
                    ts=ts,
                    open=o, high=h, low=l, close=c, volume=v,
                    adj_open=o, adj_high=h, adj_low=l, adj_close=c,
                    timeframe=interval if interval != "1d" else "1d",
                    currency="USDT",
                    source="binance_public_klines",
                ))
            except Exception:
                continue
        return AdapterResult(
            ok=bool(bars),
            bars=bars,
            source=DatasetSource(
                adapter="binance_public",
                uri=PUBLIC_KLINES,
                read_only=True,
                credentials_required=False,
                network_required=True,
                provenance_notes=[
                    "Public /api/v3/klines only",
                    "No credentials",
                    "No account or order endpoints",
                ],
            ),
            error="" if bars else "empty_klines",
            metadata={"symbol": symbol.upper(), "interval": interval, "market": "BINANCE"},
        )

    def load(self, **kwargs: Any) -> AdapterResult:
        if "path" in kwargs:
            return self.load_from_file(kwargs.pop("path"), **kwargs)
        return self.load_public_klines(
            kwargs.get("symbol", "BTCUSDT"),
            interval=kwargs.get("interval", "1d"),
            limit=kwargs.get("limit", 100),
            allow_network=bool(kwargs.get("allow_network", False)),
        )
