"""Lightweight dataset reconciliation helpers."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.market_data.models import AUTHORITY_VALUES
from saathi.platform.tg.market_data.storage import MarketDataStore


class ReconciliationEngine:
    def __init__(self, store: MarketDataStore):
        self.store = store

    def row_count_check(self, dataset_id: str, dataset_version: str) -> dict[str, Any]:
        ds = self.store.get_dataset(dataset_id, dataset_version)
        bars = self.store.query(
            "SELECT COUNT(*) AS n FROM md_bars WHERE dataset_id=? AND dataset_version=?",
            (dataset_id, dataset_version),
        )
        n = bars[0]["n"] if bars else 0
        expected = (ds or {}).get("row_count") or 0
        return {
            "ok": n == expected or expected == 0,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "registered_row_count": expected,
            "stored_bar_count": n,
            "match": n == expected,
            **AUTHORITY_VALUES,
        }
