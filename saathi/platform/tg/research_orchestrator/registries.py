"""Model / strategy V2 / feature / dataset registry integration (compose existing)."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.research_orchestrator.models import AUTHORITY_VALUES
from saathi.platform.tg.research_orchestrator.storage import OrchestratorStore, config_checksum, _uid


class ModelRegistry:
    def __init__(self, store: OrchestratorStore):
        self.store = store

    def register(self, name: str, version: str = "v1", **meta: Any) -> dict[str, Any]:
        payload = {"name": name, "version": version, **meta}
        cs = config_checksum(payload)
        mid = f"model_{cs[:12]}"
        existing = self.store.fetchone("SELECT model_id FROM orch_models WHERE model_id=?", (mid,))
        if existing:
            return {"ok": True, "idempotent": True, "model_id": mid, "checksum": cs, **AUTHORITY_VALUES}
        self.store.execute(
            "INSERT INTO orch_models(model_id, name, version, meta_json, checksum, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (mid, name, version, json.dumps(payload, sort_keys=True, default=str), cs, time.time()),
        )
        return {"ok": True, "model_id": mid, "checksum": cs, **AUTHORITY_VALUES}

    def list(self) -> dict[str, Any]:
        rows = self.store.fetchall("SELECT model_id, name, version, checksum, created_at FROM orch_models")
        return {"ok": True, "count": len(rows), "models": rows, **AUTHORITY_VALUES}


class StrategyRegistryV2:
    """Compose M248 strategy registry — additive metadata only, no parallel catalog."""

    def list(self, category: str | None = None) -> dict[str, Any]:
        from saathi.platform.tg.intelligence.strategy_registry import StrategyRegistryEngine
        base = StrategyRegistryEngine().list_strategies(category)
        strategies = []
        for s in base.get("strategies") or []:
            strategies.append({
                **s,
                "registry_version": "v2",
                "orchestrator_compatible": True,
                "research_only": True,
            })
        return {
            "ok": True,
            "registry": "strategy_registry_v2",
            "composes": "M248_StrategyRegistryEngine",
            "count": len(strategies),
            "strategies": strategies,
            **AUTHORITY_VALUES,
        }

    def get(self, strategy_id: str) -> dict[str, Any]:
        from saathi.platform.tg.intelligence.strategy_registry import StrategyRegistryEngine
        s = StrategyRegistryEngine().get(strategy_id)
        if not s:
            return {"ok": False, "code": "STRATEGY_NOT_FOUND", **AUTHORITY_VALUES}
        return {
            "ok": True,
            "strategy": {**s, "registry_version": "v2", "orchestrator_compatible": True},
            **AUTHORITY_VALUES,
        }


class FeatureRegistryView:
    """Compose M261 feature store catalogue when available."""

    def list(self) -> dict[str, Any]:
        try:
            from saathi.platform.tg.market_data.service import default_market_data
            md = default_market_data()
            cat = md.feature_list()
            return {
                "ok": True,
                "registry": "feature_registry",
                "composes": "M261_FeatureStore",
                "features": cat.get("features") or cat.get("catalogue") or cat,
                "count": cat.get("count"),
                **AUTHORITY_VALUES,
            }
        except Exception as e:
            return {
                "ok": True,
                "registry": "feature_registry",
                "composes": "M261_FeatureStore",
                "features": [
                    {"feature_id": "sma_10", "version": "v1"},
                    {"feature_id": "sma_20", "version": "v1"},
                    {"feature_id": "simple_return", "version": "v1"},
                    {"feature_id": "rsi_14", "version": "v1"},
                ],
                "count": 4,
                "fallback": True,
                "note": str(e),
                **AUTHORITY_VALUES,
            }


class DatasetRegistryView:
    """Compose M256 dataset registry when available."""

    def list(self, state: str | None = None) -> dict[str, Any]:
        try:
            from saathi.platform.tg.market_data.service import default_market_data
            md = default_market_data()
            return {
                "ok": True,
                "registry": "dataset_registry",
                "composes": "M256_DatasetRegistry",
                **md.list_datasets(state),
            }
        except Exception as e:
            return {
                "ok": True,
                "registry": "dataset_registry",
                "composes": "M256_DatasetRegistry",
                "datasets": [],
                "count": 0,
                "fallback": True,
                "note": str(e),
                **AUTHORITY_VALUES,
            }
