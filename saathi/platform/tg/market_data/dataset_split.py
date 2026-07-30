"""M260 — Deterministic dataset splits with embargo/purge."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.market_data.models import AUTHORITY_VALUES, SplitKind
from saathi.platform.tg.market_data.storage import MarketDataStore, evidence_hash, _uid


class DatasetSplitEngine:
    def __init__(self, store: MarketDataStore):
        self.store = store

    def chronological_holdout(
        self,
        dataset_id: str,
        dataset_version: str,
        *,
        train_ratio: float = 0.6,
        val_ratio: float = 0.2,
        embargo_bars: int = 2,
        purge_bars: int = 0,
    ) -> dict[str, Any]:
        bars = self.store.query(
            """SELECT DISTINCT timestamp FROM md_bars
               WHERE dataset_id=? AND dataset_version=? ORDER BY timestamp""",
            (dataset_id, dataset_version),
        )
        ts = [b["timestamp"] for b in bars]
        n = len(ts)
        if n < 10:
            return {
                "ok": False,
                "code": "INSUFFICIENT_BARS",
                "n": n,
                "leakage_detected": False,
                "evaluation_set_optimised_on": False,
                **AUTHORITY_VALUES,
            }

        n_train = max(1, int(n * train_ratio))
        n_val = max(1, int(n * val_ratio))
        # Embargo after train before val, and after val before test
        train_end = n_train
        val_start = min(n, train_end + embargo_bars)
        val_end = min(n, val_start + n_val)
        test_start = min(n, val_end + embargo_bars)
        # Purge overlapping label windows from train end
        if purge_bars > 0:
            train_end = max(1, train_end - purge_bars)

        train_ts = ts[:train_end]
        val_ts = ts[val_start:val_end]
        test_ts = ts[test_start:]

        train_set, val_set, test_set = set(train_ts), set(val_ts), set(test_ts)
        leakage = bool(train_set & val_set or train_set & test_set or val_set & test_set)

        result = {
            "kind": SplitKind.CHRONOLOGICAL_HOLDOUT.value,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "n_timestamps": n,
            "train": {"start": train_ts[0] if train_ts else None, "end": train_ts[-1] if train_ts else None, "count": len(train_ts)},
            "validation": {"start": val_ts[0] if val_ts else None, "end": val_ts[-1] if val_ts else None, "count": len(val_ts)},
            "test": {"start": test_ts[0] if test_ts else None, "end": test_ts[-1] if test_ts else None, "count": len(test_ts)},
            "embargo_bars": embargo_bars,
            "purge_bars": purge_bars,
            "leakage_detected": leakage,
            "evaluation_set_optimised_on": False,
            "final_evaluation_untouched": True,
            "train_timestamps": train_ts,
            "validation_timestamps": val_ts,
            "test_timestamps": test_ts,
        }
        return self._persist(dataset_id, dataset_version, SplitKind.CHRONOLOGICAL_HOLDOUT.value, {
            "train_ratio": train_ratio, "val_ratio": val_ratio,
            "embargo_bars": embargo_bars, "purge_bars": purge_bars,
        }, result)

    def rolling_walk_forward(
        self,
        dataset_id: str,
        dataset_version: str,
        *,
        n_folds: int = 3,
        train_size: int = 40,
        test_size: int = 10,
        embargo_bars: int = 1,
    ) -> dict[str, Any]:
        bars = self.store.query(
            """SELECT DISTINCT timestamp FROM md_bars
               WHERE dataset_id=? AND dataset_version=? ORDER BY timestamp""",
            (dataset_id, dataset_version),
        )
        ts = [b["timestamp"] for b in bars]
        folds = []
        leakage = False
        i = 0
        for fold in range(n_folds):
            tr_start = i
            tr_end = tr_start + train_size
            te_start = tr_end + embargo_bars
            te_end = te_start + test_size
            if te_end > len(ts):
                break
            train_ts = ts[tr_start:tr_end]
            test_ts = ts[te_start:te_end]
            if set(train_ts) & set(test_ts):
                leakage = True
            folds.append({
                "fold": fold,
                "train": {"start": train_ts[0], "end": train_ts[-1], "count": len(train_ts)},
                "test": {"start": test_ts[0], "end": test_ts[-1], "count": len(test_ts)},
            })
            i = tr_start + test_size  # roll forward

        result = {
            "kind": SplitKind.ROLLING_WALK_FORWARD.value,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "n_folds": len(folds),
            "folds": folds,
            "embargo_bars": embargo_bars,
            "leakage_detected": leakage,
            "evaluation_set_optimised_on": False,
            "parameter_selection_train_only": True,
        }
        return self._persist(dataset_id, dataset_version, SplitKind.ROLLING_WALK_FORWARD.value, {
            "n_folds": n_folds, "train_size": train_size, "test_size": test_size, "embargo_bars": embargo_bars,
        }, result)

    def expanding_window(
        self,
        dataset_id: str,
        dataset_version: str,
        *,
        min_train: int = 30,
        test_size: int = 10,
        n_folds: int = 3,
        embargo_bars: int = 1,
    ) -> dict[str, Any]:
        bars = self.store.query(
            """SELECT DISTINCT timestamp FROM md_bars
               WHERE dataset_id=? AND dataset_version=? ORDER BY timestamp""",
            (dataset_id, dataset_version),
        )
        ts = [b["timestamp"] for b in bars]
        folds = []
        leakage = False
        for fold in range(n_folds):
            tr_end = min_train + fold * test_size
            te_start = tr_end + embargo_bars
            te_end = te_start + test_size
            if te_end > len(ts) or tr_end < 1:
                break
            train_ts = ts[:tr_end]
            test_ts = ts[te_start:te_end]
            if set(train_ts) & set(test_ts):
                leakage = True
            folds.append({
                "fold": fold,
                "train_count": len(train_ts),
                "test": {"start": test_ts[0], "end": test_ts[-1], "count": len(test_ts)},
            })
        result = {
            "kind": SplitKind.EXPANDING_WINDOW.value,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "folds": folds,
            "leakage_detected": leakage,
            "evaluation_set_optimised_on": False,
        }
        return self._persist(dataset_id, dataset_version, SplitKind.EXPANDING_WINDOW.value, {
            "min_train": min_train, "test_size": test_size, "n_folds": n_folds,
        }, result)

    def _persist(self, dataset_id: str, dataset_version: str, kind: str, config: dict, result: dict) -> dict[str, Any]:
        eh = evidence_hash(result)
        result["evidence_hash"] = eh
        sid = _uid("split")
        self.store.execute(
            """INSERT INTO md_splits(
                id, dataset_id, dataset_version, kind, config_json, result_json, evidence_hash, created_at
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                sid, dataset_id, dataset_version, kind,
                json.dumps(config), json.dumps(result, default=str), eh, time.time(),
            ),
        )
        result["ok"] = True
        result["split_id"] = sid
        result.update(AUTHORITY_VALUES)
        return result
