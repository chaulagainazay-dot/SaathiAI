"""M261 — Versioned research feature store (not live-trading infra)."""
from __future__ import annotations

import json
import math
import time
from typing import Any

from saathi.platform.tg.market_data.models import (
    AUTHORITY_VALUES,
    FEATURE_CREATOR_VERSION,
)
from saathi.platform.tg.market_data.storage import MarketDataStore, content_checksum, evidence_hash


def _sma(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
        else:
            out.append(sum(values[i + 1 - window: i + 1]) / window)
    return out


def _ema(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    if not values:
        return out
    k = 2 / (window + 1)
    ema = values[0]
    for i, v in enumerate(values):
        if i == 0:
            out.append(None if window > 1 else ema)
            continue
        ema = v * k + ema * (1 - k)
        out.append(ema if i + 1 >= window else None)
    return out


def _rsi(values: list[float], window: int = 14) -> list[float | None]:
    out: list[float | None] = [None]
    gains, losses = [], []
    for i in range(1, len(values)):
        ch = values[i] - values[i - 1]
        gains.append(max(ch, 0))
        losses.append(max(-ch, 0))
        if i < window:
            out.append(None)
        else:
            ag = sum(gains[i - window: i]) / window
            al = sum(losses[i - window: i]) / window
            if al == 0:
                out.append(100.0)
            else:
                rs = ag / al
                out.append(100 - (100 / (1 + rs)))
    return out


FEATURE_CATALOG = {
    "simple_return": {
        "category": "price_return",
        "formula": "(close_t / close_t-1) - 1",
        "lookback": 1,
        "version": "v1",
    },
    "log_return": {
        "category": "price_return",
        "formula": "ln(close_t / close_t-1)",
        "lookback": 1,
        "version": "v1",
    },
    "sma_10": {
        "category": "trend",
        "formula": "mean(close, 10)",
        "lookback": 10,
        "version": "v1",
    },
    "sma_20": {
        "category": "trend",
        "formula": "mean(close, 20)",
        "lookback": 20,
        "version": "v1",
    },
    "ema_12": {
        "category": "trend",
        "formula": "ema(close, 12)",
        "lookback": 12,
        "version": "v1",
    },
    "rolling_volatility_20": {
        "category": "volatility",
        "formula": "stdev(simple_return, 20)",
        "lookback": 20,
        "version": "v1",
    },
    "rsi_14": {
        "category": "technical",
        "formula": "rsi(close, 14)",
        "lookback": 14,
        "version": "v1",
    },
    "atr_14": {
        "category": "volatility",
        "formula": "mean(true_range, 14)",
        "lookback": 14,
        "version": "v1",
    },
    "relative_volume_20": {
        "category": "volume",
        "formula": "volume / mean(volume, 20)",
        "lookback": 20,
        "version": "v1",
    },
    "momentum_10": {
        "category": "price_return",
        "formula": "close_t / close_t-10 - 1",
        "lookback": 10,
        "version": "v1",
    },
}


class FeatureStore:
    def __init__(self, store: MarketDataStore):
        self.store = store
        self._ensure_catalog()

    def _ensure_catalog(self) -> None:
        for fid, meta in FEATURE_CATALOG.items():
            existing = self.store.query_one(
                "SELECT feature_id FROM md_features WHERE feature_id=? AND feature_version=?",
                (fid, meta["version"]),
            )
            if existing:
                continue
            self.store.execute(
                """INSERT INTO md_features(
                    feature_id, feature_version, name, category, formula, lookback,
                    timestamp_semantics, availability_rule, missing_data_policy,
                    normalization_policy, input_dataset_versions_json, output_checksum,
                    creator_version, lineage_json, limitations_json, certified, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    fid, meta["version"], fid, meta["category"], meta["formula"], meta["lookback"],
                    "bar_close", "same_bar_close_available", "propagate_null",
                    "none_global_fit_forbidden", "[]", "",
                    FEATURE_CREATOR_VERSION, json.dumps([{"step": "definition", "formula": meta["formula"]}]),
                    json.dumps(["research_only", "not_live_trading_infra"]),
                    0, time.time(),
                ),
            )

    def catalogue(self) -> dict[str, Any]:
        rows = self.store.query("SELECT * FROM md_features ORDER BY feature_id, feature_version")
        features = []
        for r in rows:
            features.append({
                "feature_id": r["feature_id"],
                "feature_version": r["feature_version"],
                "name": r["name"],
                "category": r["category"],
                "formula": r["formula"],
                "lookback": r["lookback"],
                "timestamp_semantics": r["timestamp_semantics"],
                "availability_rule": r["availability_rule"],
                "missing_data_policy": r["missing_data_policy"],
                "normalization_policy": r["normalization_policy"],
                "input_dataset_versions": json.loads(r["input_dataset_versions_json"] or "[]"),
                "output_checksum": r["output_checksum"] or "",
                "creator_version": r["creator_version"],
                "lineage": json.loads(r["lineage_json"] or "[]"),
                "limitations": json.loads(r["limitations_json"] or "[]"),
                "certified": bool(r["certified"]),
            })
        payload = {
            "schema": "M261_FEATURE_CATALOG",
            "count": len(features),
            "features": features,
            "immutable_versions": True,
            "creator_version": FEATURE_CREATOR_VERSION,
            **AUTHORITY_VALUES,
        }
        payload["evidence_hash"] = evidence_hash(payload)
        return payload

    def register_version(
        self,
        feature_id: str,
        formula: str,
        *,
        category: str = "custom",
        lookback: int = 1,
        version: str | None = None,
    ) -> dict[str, Any]:
        """Changed formula must create a new version — never mutate certified formula."""
        existing = self.store.query(
            "SELECT * FROM md_features WHERE feature_id=? ORDER BY created_at",
            (feature_id,),
        )
        for e in existing:
            if e["formula"] == formula:
                return {
                    "ok": True,
                    "feature_id": feature_id,
                    "feature_version": e["feature_version"],
                    "idempotent": True,
                    **AUTHORITY_VALUES,
                }
            if e.get("certified"):
                # cannot mutate
                pass
        # New version
        ver = version or f"v{len(existing) + 1}"
        collision = self.store.query_one(
            "SELECT feature_id FROM md_features WHERE feature_id=? AND feature_version=?",
            (feature_id, ver),
        )
        if collision:
            # force next
            ver = f"v{len(existing) + 1}_{int(time.time()) % 10000}"
        self.store.execute(
            """INSERT INTO md_features(
                feature_id, feature_version, name, category, formula, lookback,
                timestamp_semantics, availability_rule, missing_data_policy,
                normalization_policy, input_dataset_versions_json, output_checksum,
                creator_version, lineage_json, limitations_json, certified, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                feature_id, ver, feature_id, category, formula, lookback,
                "bar_close", "same_bar_close_available", "propagate_null",
                "none_global_fit_forbidden", "[]", "",
                FEATURE_CREATOR_VERSION,
                json.dumps([{"step": "new_version", "formula": formula, "prior_versions": len(existing)}]),
                json.dumps(["research_only"]),
                0, time.time(),
            ),
        )
        return {"ok": True, "feature_id": feature_id, "feature_version": ver, "formula": formula, **AUTHORITY_VALUES}

    def build(
        self,
        dataset_id: str,
        dataset_version: str,
        feature_ids: list[str] | None = None,
        *,
        symbol: str | None = None,
        fit_timestamps: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build features with point-in-time semantics. No global norm leakage."""
        feature_ids = feature_ids or list(FEATURE_CATALOG.keys())
        q = """SELECT * FROM md_bars WHERE dataset_id=? AND dataset_version=?"""
        params: list[Any] = [dataset_id, dataset_version]
        if symbol:
            q += " AND symbol=?"
            params.append(symbol.upper())
        q += " ORDER BY symbol, timestamp"
        bars = self.store.query(q, params)
        if not bars:
            return {"ok": False, "code": "NO_BARS", **AUTHORITY_VALUES}

        by_sym: dict[str, list] = {}
        for b in bars:
            by_sym.setdefault(b["symbol"], []).append(b)

        built = 0
        versions_used = []
        processing_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # Clear previous feature values for this dataset version rebuild of selected features
        for fid in feature_ids:
            meta = FEATURE_CATALOG.get(fid)
            ver = meta["version"] if meta else "v1"
            self.store.execute(
                """DELETE FROM md_feature_values WHERE feature_id=? AND feature_version=?
                   AND dataset_id=? AND dataset_version=?""",
                (fid, ver, dataset_id, dataset_version),
            )

        batch: list[tuple] = []
        for sym, rows in by_sym.items():
            closes = [float(r["close"]) for r in rows]
            highs = [float(r["high"] for r in rows)] if False else [float(r["high"]) for r in rows]
            lows = [float(r["low"]) for r in rows]
            vols = [float(r["volume"] or 0) for r in rows]
            ts_list = [r["timestamp"] for r in rows]

            computed: dict[str, list[float | None]] = {}
            if "simple_return" in feature_ids:
                computed["simple_return"] = [None] + [
                    (closes[i] / closes[i - 1] - 1.0) if closes[i - 1] else None
                    for i in range(1, len(closes))
                ]
            if "log_return" in feature_ids:
                computed["log_return"] = [None] + [
                    math.log(closes[i] / closes[i - 1]) if closes[i - 1] > 0 and closes[i] > 0 else None
                    for i in range(1, len(closes))
                ]
            if "sma_10" in feature_ids:
                computed["sma_10"] = _sma(closes, 10)
            if "sma_20" in feature_ids:
                computed["sma_20"] = _sma(closes, 20)
            if "ema_12" in feature_ids:
                computed["ema_12"] = _ema(closes, 12)
            if "rsi_14" in feature_ids:
                computed["rsi_14"] = _rsi(closes, 14)
            if "momentum_10" in feature_ids:
                computed["momentum_10"] = [
                    (closes[i] / closes[i - 10] - 1.0) if i >= 10 and closes[i - 10] else None
                    for i in range(len(closes))
                ]
            if "rolling_volatility_20" in feature_ids:
                rets = [None] + [
                    (closes[i] / closes[i - 1] - 1.0) if closes[i - 1] else None
                    for i in range(1, len(closes))
                ]
                vol_series: list[float | None] = []
                for i in range(len(rets)):
                    window = [x for x in rets[max(0, i - 19): i + 1] if x is not None]
                    if len(window) < 20:
                        vol_series.append(None)
                    else:
                        m = sum(window) / len(window)
                        var = sum((x - m) ** 2 for x in window) / len(window)
                        vol_series.append(math.sqrt(var))
                computed["rolling_volatility_20"] = vol_series
            if "atr_14" in feature_ids:
                trs = []
                for i in range(len(closes)):
                    if i == 0:
                        trs.append(highs[i] - lows[i])
                    else:
                        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
                        trs.append(tr)
                computed["atr_14"] = _sma(trs, 14)
            if "relative_volume_20" in feature_ids:
                vma = _sma(vols, 20)
                computed["relative_volume_20"] = [
                    (vols[i] / vma[i]) if vma[i] else None for i in range(len(vols))
                ]

            for fid, series in computed.items():
                meta = FEATURE_CATALOG[fid]
                ver = meta["version"]
                versions_used.append(f"{fid}@{ver}")
                # Train-only scaler fitting if fit_timestamps provided (isolation)
                scale_mean = 0.0
                scale_std = 1.0
                if fit_timestamps:
                    fit_vals = [
                        series[i] for i, t in enumerate(ts_list)
                        if t in fit_timestamps and series[i] is not None
                    ]
                    if fit_vals:
                        scale_mean = sum(fit_vals) / len(fit_vals)
                        var = sum((x - scale_mean) ** 2 for x in fit_vals) / len(fit_vals)
                        scale_std = math.sqrt(var) if var > 0 else 1.0

                for i, val in enumerate(series):
                    event_ts = ts_list[i]
                    # Availability = bar close (same bar) — research rule documented
                    availability_ts = event_ts
                    if fit_timestamps is not None and event_ts not in set(fit_timestamps) and fit_timestamps:
                        # still compute raw value; normalization only from train
                        pass
                    out_val = val
                    if val is not None and fit_timestamps:
                        out_val = (val - scale_mean) / scale_std if scale_std else val
                    batch.append((
                        fid, ver, dataset_id, dataset_version, sym,
                        event_ts, availability_ts, processing_ts,
                        out_val, json.dumps({"raw": val}),
                    ))
                    built += 1

        if batch:
            self.store.executemany(
                """INSERT INTO md_feature_values(
                    feature_id, feature_version, dataset_id, dataset_version, symbol,
                    event_ts, availability_ts, processing_ts, value, meta_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                batch,
            )

        # Update feature checksums
        payload = {"dataset_id": dataset_id, "dataset_version": dataset_version, "built": built}
        cs = content_checksum(json.dumps(payload, sort_keys=True))
        for fid in feature_ids:
            meta = FEATURE_CATALOG.get(fid)
            if not meta:
                continue
            self.store.execute(
                """UPDATE md_features SET output_checksum=?,
                    input_dataset_versions_json=?,
                    lineage_json=?
                    WHERE feature_id=? AND feature_version=?""",
                (
                    cs,
                    json.dumps([f"{dataset_id}@{dataset_version}"]),
                    json.dumps([
                        {"dataset": f"{dataset_id}@{dataset_version}"},
                        {"formula": meta["formula"]},
                        {"creator": FEATURE_CREATOR_VERSION},
                    ]),
                    fid, meta["version"],
                ),
            )

        return {
            "ok": True,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "features_built": sorted(set(versions_used)),
            "value_count": built,
            "missing_data_policy": "propagate_null",
            "normalization_policy": "train_fit_only" if fit_timestamps else "none",
            "no_future_data": True,
            "output_checksum": cs,
            **AUTHORITY_VALUES,
        }

    def lineage(self, feature_id: str, feature_version: str | None = None) -> dict[str, Any]:
        if feature_version:
            row = self.store.query_one(
                "SELECT * FROM md_features WHERE feature_id=? AND feature_version=?",
                (feature_id, feature_version),
            )
        else:
            row = self.store.query_one(
                "SELECT * FROM md_features WHERE feature_id=? ORDER BY created_at DESC LIMIT 1",
                (feature_id,),
            )
        if not row:
            return {"ok": False, "code": "FEATURE_NOT_FOUND", "feature_id": feature_id, **AUTHORITY_VALUES}
        return {
            "ok": True,
            "feature_id": row["feature_id"],
            "feature_version": row["feature_version"],
            "formula": row["formula"],
            "lineage": json.loads(row["lineage_json"] or "[]"),
            "input_dataset_versions": json.loads(row["input_dataset_versions_json"] or "[]"),
            "output_checksum": row["output_checksum"],
            "creator_version": row["creator_version"],
            "limitations": json.loads(row["limitations_json"] or "[]"),
            **AUTHORITY_VALUES,
        }
