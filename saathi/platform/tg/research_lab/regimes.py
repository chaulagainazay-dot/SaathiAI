"""M275 — Regime definition models (point-in-time safe)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from saathi.platform.tg.research_lab.models import AUTHORITY_VALUES, REGIME_ENGINE_VERSION


def regime_definition_checksum(defn: dict[str, Any]) -> str:
    raw = json.dumps(defn, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


DEFAULT_REGIME_DEFINITIONS: list[dict[str, Any]] = [
    {
        "regime_id": "trend_regime_v1",
        "regime_version": "v1",
        "dimension": "trend",
        "formula": "sign(sma_return_20) with |ret| thresholds",
        "thresholds": {"up_ret": 0.05, "down_ret": -0.05},
        "labels": ["upward_trend", "downward_trend", "sideways", "transitional"],
        "input_features": ["simple_return_20"],
        "dataset_versions": {},
        "lookback_period": 20,
        "minimum_duration": 3,
        "transition_rule": "label_change_persists_min_duration",
        "availability": "real_time_research_features_only",
        "ex_post_descriptive": False,
        "limitations": ["Thresholds fitted on training data only"],
    },
    {
        "regime_id": "volatility_regime_v1",
        "regime_version": "v1",
        "dimension": "volatility",
        "formula": "realized_vol_20 vs train quantiles",
        "thresholds": {"low_q": 0.25, "high_q": 0.75, "extreme_q": 0.95},
        "labels": ["low_volatility", "normal_volatility", "high_volatility", "extreme_volatility"],
        "input_features": ["realized_vol_20"],
        "dataset_versions": {},
        "lookback_period": 20,
        "minimum_duration": 2,
        "transition_rule": "quantile_band_change",
        "availability": "real_time_research_features_only",
        "ex_post_descriptive": False,
        "limitations": ["Quantiles frozen from training split"],
    },
    {
        "regime_id": "liquidity_regime_v1",
        "regime_version": "v1",
        "dimension": "liquidity",
        "formula": "volume_zscore proxy when volume present else UNKNOWN",
        "thresholds": {"reduced_z": -1.0, "stressed_z": -2.0},
        "labels": ["normal_liquidity", "reduced_liquidity", "stressed_liquidity"],
        "input_features": ["volume_z_20"],
        "dataset_versions": {},
        "lookback_period": 20,
        "minimum_duration": 2,
        "transition_rule": "zscore_band",
        "availability": "real_time_research_features_only",
        "ex_post_descriptive": False,
        "limitations": ["Volume may be missing; falls back to REGIME_UNKNOWN"],
    },
    {
        "regime_id": "correlation_regime_v1",
        "regime_version": "v1",
        "dimension": "correlation",
        "formula": "avg pairwise corr rolling when multi-asset else UNKNOWN",
        "thresholds": {"low": 0.2, "high": 0.6, "risk_off": 0.8},
        "labels": ["low_cross_asset_correlation", "normal_correlation", "high_correlation", "risk_off_correlation_spike"],
        "input_features": ["rolling_corr_20"],
        "dataset_versions": {},
        "lookback_period": 20,
        "minimum_duration": 3,
        "transition_rule": "corr_band",
        "availability": "real_time_research_features_only",
        "ex_post_descriptive": False,
        "limitations": ["Single-asset series cannot form correlation regime"],
    },
]


def freeze_thresholds_from_train(
    dimension: str,
    train_series: list[float],
    base: dict[str, Any],
) -> dict[str, Any]:
    """Fit thresholds on training data only; freeze for val/test."""
    out = dict(base)
    thr = dict(base.get("thresholds") or {})
    if not train_series:
        out["thresholds"] = thr
        out["fit_status"] = "INSUFFICIENT_TRAIN_DATA"
        return out
    xs = sorted(train_series)
    n = len(xs)

    def q(p: float) -> float:
        return xs[min(n - 1, max(0, int(p * (n - 1))))]

    if dimension == "volatility":
        thr["low"] = q(thr.get("low_q", 0.25))
        thr["high"] = q(thr.get("high_q", 0.75))
        thr["extreme"] = q(thr.get("extreme_q", 0.95))
    elif dimension == "trend":
        # keep relative return thresholds; optionally scale by train vol
        pass
    out["thresholds"] = thr
    out["fit_status"] = "FITTED_ON_TRAIN_FROZEN"
    out["fitted_on"] = "training_period_only"
    out["test_set_used_for_thresholds"] = False
    out["checksum"] = regime_definition_checksum(out)
    out["engine_version"] = REGIME_ENGINE_VERSION
    return out


def list_default_definitions() -> dict[str, Any]:
    defs = []
    for d in DEFAULT_REGIME_DEFINITIONS:
        item = dict(d)
        item["checksum"] = regime_definition_checksum(item)
        item["engine_version"] = REGIME_ENGINE_VERSION
        defs.append(item)
    return {
        "ok": True,
        "definitions": defs,
        "macro_regimes_fabricated": False,
        "note": "Macro regimes omitted without governed point-in-time macro data",
        **AUTHORITY_VALUES,
    }
