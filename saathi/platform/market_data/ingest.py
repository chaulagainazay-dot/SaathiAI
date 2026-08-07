"""M62.2 — ingestion service: provider fetch → normalize → validate → classify →
persist → ingestion report.

Rejection policy: rejected records NEVER enter the valid dataset. Their metadata +
content hash are retained separately (md_rejects) for evidence, but they are not
queryable as market data.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from saathi.platform.market_data.models import MDBar, MDQuote, Timeframe, MarketDataQuality
from saathi.platform.market_data.provider import MarketDataProvider, ProviderStatus
from saathi.platform.market_data.quality import classify_series, classify_quote
from saathi.platform.market_data.store import MarketDataStore
from saathi.platform.market_data.fixtures import FIXTURE_VERSION


def _bar_hash(b: MDBar) -> str:
    return hashlib.sha256(
        f"{b.instrument}|{b.timeframe.value}|{b.start_time.isoformat()}|{b.open}|{b.high}|{b.low}|{b.close}|{b.volume}".encode()
    ).hexdigest()


@dataclass
class IngestionReport:
    instrument: str
    timeframe: str
    correlation_id: str
    dataset_version: str = FIXTURE_VERSION
    requested: int = 0
    received: int = 0
    accepted: int = 0
    rejected: int = 0
    duplicates: int = 0
    gaps: int = 0
    outliers: int = 0
    stale: int = 0
    provider_errors: int = 0
    provider_status: str = ""
    time_range: list = field(default_factory=list)

    def to_public(self) -> dict[str, Any]:
        return {
            "instrument": self.instrument, "timeframe": self.timeframe,
            "correlation_id": self.correlation_id, "dataset_version": self.dataset_version,
            "requested": self.requested, "received": self.received, "accepted": self.accepted,
            "rejected": self.rejected, "duplicates": self.duplicates, "gaps": self.gaps,
            "outliers": self.outliers, "stale": self.stale, "provider_errors": self.provider_errors,
            "provider_status": self.provider_status, "time_range": self.time_range,
        }


class IngestionService:
    def __init__(self, provider: MarketDataProvider, store: MarketDataStore):
        self.provider = provider
        self.store = store

    def ingest_instrument(self, org_id: str, symbol: str) -> dict | None:
        res = self.provider.get_instrument(symbol)
        if not res.ok or res.data is None:
            return None
        self.store.upsert_instrument(org_id, res.data)
        return res.data.to_public()

    def ingest_bars(self, org_id: str, symbol: str, timeframe: Timeframe,
                    start: datetime, end: datetime, *, now: datetime, correlation_id: str) -> IngestionReport:
        rep = IngestionReport(instrument=symbol, timeframe=timeframe.value, correlation_id=correlation_id)
        res = self.provider.get_bars(symbol, timeframe, start, end, now=now)
        rep.provider_status = res.status.value
        if not res.ok or res.data is None:
            rep.provider_errors = 1
            return rep
        bars: list[MDBar] = res.data
        rep.requested = rep.received = len(bars)
        summary = classify_series(bars, now=now)
        rep.duplicates = summary["duplicates"]
        rep.gaps = summary["gaps"]
        if bars:
            rep.time_range = [bars[0].start_time.isoformat(), bars[-1].end_time.isoformat()]
        for b in bars:
            h = _bar_hash(b)
            if b.quality == MarketDataQuality.VALID:
                outcome = self.store.insert_bar(org_id, b, raw_hash=h)
                if outcome == "inserted":
                    rep.accepted += 1
                else:
                    rep.duplicates += 1 if summary["duplicates"] == 0 else 0
            else:
                rep.rejected += 1
                if b.quality == MarketDataQuality.OUTLIER:
                    rep.outliers += 1
                if b.quality == MarketDataQuality.STALE:
                    rep.stale += 1
                self.store.record_reject(
                    org_id, provider=b.provider, instrument=symbol, kind="bar",
                    quality=b.quality.value, start_epoch=b.start_time.timestamp(),
                    raw_hash=h, findings=[f.to_public() for f in b.findings],
                )
        return rep

    def ingest_quote(self, org_id: str, symbol: str, *, now: datetime, market_open: bool | None = None) -> dict:
        res = self.provider.get_quote(symbol, now=now)
        if not res.ok or res.data is None:
            return {"provider_status": res.status.value, "accepted": False}
        q: MDQuote = res.data
        classify_quote(q, now=now, market_open=market_open)
        if q.quality == MarketDataQuality.VALID:
            self.store.insert_quote(org_id, q)
            return {"provider_status": res.status.value, "accepted": True, "quality": q.quality.value, "quote": q.to_public()}
        self.store.record_reject(org_id, provider=q.provider, instrument=symbol, kind="quote",
                                 quality=q.quality.value, findings=[f.to_public() for f in q.findings])
        return {"provider_status": res.status.value, "accepted": False, "quality": q.quality.value,
                "findings": [f.to_public() for f in q.findings]}
