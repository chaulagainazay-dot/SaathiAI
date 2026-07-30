"""Dataset catalogue helpers and inventory views."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.market_data.models import AUTHORITY_VALUES, DatasetState
from saathi.platform.tg.market_data.registry import DatasetRegistry
from saathi.platform.tg.market_data.storage import MarketDataStore


class DatasetCatalog:
    def __init__(self, store: MarketDataStore, registry: DatasetRegistry):
        self.store = store
        self.registry = registry

    def overview(self) -> dict[str, Any]:
        rows = self.store.list_datasets()
        by_state: dict[str, int] = {}
        for r in rows:
            by_state[r["state"]] = by_state.get(r["state"], 0) + 1
        approved = [r for r in rows if r["state"] == DatasetState.RESEARCH_APPROVED.value]
        restricted = [r for r in rows if r["state"] == DatasetState.RESEARCH_RESTRICTED.value]
        quarantined = [r for r in rows if r["state"] == DatasetState.QUARANTINED.value]
        synthetic = [r for r in rows if r.get("is_synthetic")]
        return {
            "ok": True,
            "dataset_count": len(rows),
            "by_state": by_state,
            "approved_count": len(approved),
            "restricted_count": len(restricted),
            "quarantined_count": len(quarantined),
            "synthetic_count": len(synthetic),
            "states": [s.value for s in DatasetState],
            **AUTHORITY_VALUES,
        }

    def sources_inventory(self) -> dict[str, Any]:
        rows = self.store.list_datasets()
        sources = []
        for r in rows:
            sources.append({
                "dataset_id": r["dataset_id"],
                "dataset_version": r["dataset_version"],
                "provider": r.get("provider"),
                "source_type": r.get("source_type"),
                "source_ref": r.get("source_ref"),
                "checksum": r.get("checksum"),
                "is_synthetic": bool(r.get("is_synthetic")),
                "state": r.get("state"),
            })
        return {"ok": True, "count": len(sources), "sources": sources, **AUTHORITY_VALUES}
