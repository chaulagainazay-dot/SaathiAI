"""M275 — Deterministic point-in-time regime classification."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.research_lab.models import AUTHORITY_VALUES, RegimeState
from saathi.platform.tg.research_lab.regimes import (
    DEFAULT_REGIME_DEFINITIONS,
    freeze_thresholds_from_train,
    regime_definition_checksum,
)
from saathi.platform.tg.research_lab.storage import ResearchLabStore, evidence_hash, _uid


def _realized_vol(rets: list[float], lookback: int = 20) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(rets)):
        if i + 1 < lookback:
            out.append(None)
            continue
        window = rets[i + 1 - lookback : i + 1]
        m = sum(window) / len(window)
        var = sum((x - m) ** 2 for x in window) / max(1, len(window) - 1)
        out.append(var ** 0.5)
    return out


def _sma_return(rets: list[float], lookback: int = 20) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(rets)):
        if i + 1 < lookback:
            out.append(None)
            continue
        # cumulative simple return over lookback
        r = 1.0
        for x in rets[i + 1 - lookback : i + 1]:
            r *= 1 + x
        out.append(r - 1.0)
    return out


class RegimeClassifier:
    def __init__(self, store: ResearchLabStore):
        self.store = store

    def build_definitions(
        self,
        train_returns: list[float],
        *,
        include_macro: bool = False,
    ) -> dict[str, Any]:
        if include_macro:
            # Explicitly refuse fabrication
            macro_note = "MACRO_REGIMES_NOT_FABRICATED_WITHOUT_DATA"
        else:
            macro_note = "macro_omitted_no_governed_pit_data"

        frozen = []
        for base in DEFAULT_REGIME_DEFINITIONS:
            dim = base["dimension"]
            if dim == "volatility":
                series = [v for v in _realized_vol(train_returns) if v is not None]
            elif dim == "trend":
                series = [v for v in _sma_return(train_returns) if v is not None]
            else:
                series = []
            d = freeze_thresholds_from_train(dim, series, base)
            rid = _uid("rdef")
            self.store.execute(
                "INSERT INTO rl_regimes(id, definition_json, version, checksum, created_at) VALUES(?,?,?,?,?)",
                (rid, json.dumps(d, sort_keys=True, default=str), d.get("regime_version", "v1"),
                 d.get("checksum") or regime_definition_checksum(d), time.time()),
            )
            d["storage_id"] = rid
            frozen.append(d)

        return {
            "ok": True,
            "schema": "M275_ADAPTIVE_REGIME_INTELLIGENCE",
            "section": "definitions",
            "definitions": frozen,
            "macro_regimes_fabricated": False,
            "macro_note": macro_note,
            "thresholds_fitted_on": "training_only",
            "test_set_used_for_thresholds": False,
            **AUTHORITY_VALUES,
        }

    def classify(
        self,
        returns: list[float],
        definitions: list[dict[str, Any]],
        *,
        train_end_index: int | None = None,
    ) -> dict[str, Any]:
        """Classify regimes bar-by-bar using only information available at t."""
        n = len(returns)
        if train_end_index is None:
            train_end_index = int(n * 0.6)

        trend_rets = _sma_return(returns, 20)
        vols = _realized_vol(returns, 20)

        trend_def = next((d for d in definitions if d.get("dimension") == "trend"), None)
        vol_def = next((d for d in definitions if d.get("dimension") == "volatility"), None)

        series = []
        transitions = []
        prev_label = None
        unknown_count = 0
        low_conf = 0
        classified = 0

        for i in range(n):
            labels: dict[str, Any] = {}
            conf = 1.0
            state = RegimeState.REGIME_CLASSIFIED.value

            # Point-in-time: features require lookback; before that → insufficient
            if trend_rets[i] is None or vols[i] is None:
                state = RegimeState.REGIME_INSUFFICIENT_DATA.value
                labels["trend"] = "UNKNOWN"
                labels["volatility"] = "UNKNOWN"
                conf = 0.0
                unknown_count += 1
            else:
                # Trend
                if trend_def:
                    thr = trend_def.get("thresholds") or {}
                    tr = trend_rets[i]
                    if tr is None:
                        labels["trend"] = "UNKNOWN"
                        state = RegimeState.REGIME_UNKNOWN.value
                        unknown_count += 1
                    elif tr > thr.get("up_ret", 0.05):
                        labels["trend"] = "upward_trend"
                    elif tr < thr.get("down_ret", -0.05):
                        labels["trend"] = "downward_trend"
                    elif abs(tr) < 0.01:
                        labels["trend"] = "sideways"
                    else:
                        labels["trend"] = "transitional"
                        conf *= 0.7
                else:
                    labels["trend"] = "UNKNOWN"

                # Volatility — use frozen train quantiles only
                if vol_def:
                    thr = vol_def.get("thresholds") or {}
                    v = vols[i]
                    low = thr.get("low", 0.005)
                    high = thr.get("high", 0.015)
                    extreme = thr.get("extreme", 0.03)
                    if v is None:
                        labels["volatility"] = "UNKNOWN"
                    elif v >= extreme:
                        labels["volatility"] = "extreme_volatility"
                    elif v >= high:
                        labels["volatility"] = "high_volatility"
                    elif v <= low:
                        labels["volatility"] = "low_volatility"
                    else:
                        labels["volatility"] = "normal_volatility"
                else:
                    labels["volatility"] = "UNKNOWN"

                # Liquidity / correlation without multi-asset volume → unknown (honest)
                labels["liquidity"] = "REGIME_UNKNOWN"
                labels["correlation"] = "REGIME_UNKNOWN"
                conf *= 0.8  # reduced due to unknown dimensions
                if conf < 0.5:
                    state = RegimeState.REGIME_LOW_CONFIDENCE.value
                    low_conf += 1
                else:
                    classified += 1

            label_key = f"{labels.get('trend')}|{labels.get('volatility')}"
            if prev_label is not None and label_key != prev_label and state == RegimeState.REGIME_CLASSIFIED.value:
                state = RegimeState.REGIME_TRANSITION.value
                transitions.append({"index": i, "from": prev_label, "to": label_key})
            prev_label = label_key

            series.append({
                "index": i,
                "labels": labels,
                "state": state,
                "confidence": round(conf, 4),
                "availability_timestamp_index": i,  # PIT: available at bar i only
                "uses_future_information": False,
            })

        # Drift: distribution shift train vs test
        train_labels = [s["labels"].get("trend") for s in series[:train_end_index] if s["labels"].get("trend") != "UNKNOWN"]
        test_labels = [s["labels"].get("trend") for s in series[train_end_index:] if s["labels"].get("trend") != "UNKNOWN"]
        drift = False
        if train_labels and test_labels:
            def freq(xs):
                d: dict[str, int] = {}
                for x in xs:
                    d[x] = d.get(x, 0) + 1
                tot = sum(d.values()) or 1
                return {k: v / tot for k, v in d.items()}
            ft, fte = freq(train_labels), freq(test_labels)
            keys = set(ft) | set(fte)
            tv = sum(abs(ft.get(k, 0) - fte.get(k, 0)) for k in keys) / 2
            drift = tv > 0.35

        result = {
            "ok": True,
            "n_bars": n,
            "series_sample": series[:20] + ([{"truncated": True}] if n > 20 else []),
            "series_full_bounded": series[-50:] if n > 50 else series,
            "transition_count": len(transitions),
            "transitions_sample": transitions[:20],
            "counts": {
                "unknown": unknown_count,
                "low_confidence": low_conf,
                "classified": classified,
            },
            "regime_drift_detected": drift,
            "drift_state": RegimeState.REGIME_DRIFT_DETECTED.value if drift else None,
            "point_in_time_controls": {
                "future_information_used": False,
                "thresholds_from_test": False,
                "ex_post_relabelling": False,
            },
            "unknown_regime_supported": True,
            "insufficient_data_supported": True,
            **AUTHORITY_VALUES,
        }
        eh = evidence_hash({k: result[k] for k in result if k != "series_full_bounded"})
        result["evidence_hash"] = eh
        cid = _uid("rcls")
        self.store.execute(
            "INSERT INTO rl_regime_classifications(id, regime_def_id, result_json, evidence_hash, created_at) "
            "VALUES(?,?,?,?,?)",
            (cid, (definitions[0].get("storage_id") if definitions else "none"),
             json.dumps(result, sort_keys=True, default=str), eh, time.time()),
        )
        result["classification_id"] = cid
        return result
