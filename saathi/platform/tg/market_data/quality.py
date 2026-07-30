"""M259 — Research-grade data quality engine."""
from __future__ import annotations

import json
import math
import time
from typing import Any

from saathi.platform.tg.market_data.models import AUTHORITY_VALUES, DatasetState, QualityClass
from saathi.platform.tg.market_data.storage import MarketDataStore, evidence_hash, _uid


class QualityEngine:
    def __init__(self, store: MarketDataStore):
        self.store = store

    def evaluate(self, dataset_id: str, dataset_version: str, *, now_ts: str | None = None) -> dict[str, Any]:
        bars = self.store.query(
            """SELECT * FROM md_bars WHERE dataset_id=? AND dataset_version=?
               ORDER BY symbol, timestamp""",
            (dataset_id, dataset_version),
        )
        findings: list[dict[str, Any]] = []
        blocking: list[str] = []

        if not bars:
            blocking.append("no_bars")
            return self._finalize(dataset_id, dataset_version, findings, blocking, {
                "completeness": 0, "consistency": 0, "timeliness": 0,
                "uniqueness": 0, "validity": 0, "adjustment_confidence": 0, "source_confidence": 0.5,
            })

        # Price integrity
        for b in bars:
            o, h, l, c = b["open"], b["high"], b["low"], b["close"]
            if any(x is None or not math.isfinite(float(x)) for x in (o, h, l, c)):
                findings.append({"kind": "price", "code": "non_finite", "symbol": b["symbol"], "ts": b["timestamp"]})
                blocking.append("non_finite_price")
            if any(float(x) < 0 for x in (o, h, l, c)):
                findings.append({"kind": "price", "code": "negative_price", "symbol": b["symbol"], "ts": b["timestamp"]})
                blocking.append("negative_price")
            if float(h) < float(l):
                findings.append({"kind": "price", "code": "high_below_low", "symbol": b["symbol"], "ts": b["timestamp"]})
                blocking.append("high_below_low")
            if float(o) > float(h) or float(o) < float(l):
                findings.append({"kind": "price", "code": "open_outside_range", "symbol": b["symbol"], "ts": b["timestamp"]})
            if float(c) > float(h) or float(c) < float(l):
                findings.append({"kind": "price", "code": "close_outside_range", "symbol": b["symbol"], "ts": b["timestamp"]})
            if float(c) == 0:
                findings.append({"kind": "price", "code": "zero_price", "symbol": b["symbol"], "ts": b["timestamp"]})
                blocking.append("zero_price")

        # Timestamp integrity per symbol
        by_sym: dict[str, list] = {}
        for b in bars:
            by_sym.setdefault(b["symbol"], []).append(b)

        dup_ts = 0
        out_of_order = 0
        future_ts = 0
        weekend_bars = 0
        stale = 0
        extreme_jumps = 0
        zero_vol = 0
        neg_vol = 0

        ref_now = now_ts or "2099-01-01T00:00:00Z"  # default: don't flag future unless explicit
        for sym, rows in by_sym.items():
            seen_ts: set[str] = set()
            prev_ts = None
            prev_close = None
            for b in rows:
                ts = b["timestamp"]
                if ts in seen_ts:
                    dup_ts += 1
                    findings.append({"kind": "timestamp", "code": "duplicate_timestamp", "symbol": sym, "ts": ts})
                    blocking.append("duplicate_timestamp")
                seen_ts.add(ts)
                if prev_ts and ts < prev_ts:
                    out_of_order += 1
                    findings.append({"kind": "timestamp", "code": "out_of_order", "symbol": sym, "ts": ts})
                    blocking.append("timestamp_out_of_order")
                if now_ts and ts > now_ts:
                    future_ts += 1
                    findings.append({"kind": "timestamp", "code": "future_timestamp", "symbol": sym, "ts": ts})
                    blocking.append("future_timestamp")
                # Weekend check for equities only
                if (b.get("asset_class") or "equity") in ("equity", "etf", "index"):
                    try:
                        # ISO date portion
                        from datetime import datetime
                        d = datetime.strptime(ts[:10], "%Y-%m-%d")
                        if d.weekday() >= 5:
                            weekend_bars += 1
                            findings.append({"kind": "calendar", "code": "unexpected_weekend_bar", "symbol": sym, "ts": ts})
                    except ValueError:
                        findings.append({"kind": "timestamp", "code": "invalid_date", "symbol": sym, "ts": ts})
                        blocking.append("invalid_timestamp")
                vol = b.get("volume")
                if vol is not None and float(vol) < 0:
                    neg_vol += 1
                    findings.append({"kind": "volume", "code": "negative_volume", "symbol": sym, "ts": ts})
                    blocking.append("negative_volume")
                if vol is not None and float(vol) == 0:
                    zero_vol += 1
                    findings.append({"kind": "volume", "code": "zero_volume", "symbol": sym, "ts": ts, "severity": "warn"})
                if prev_close and float(prev_close) > 0:
                    jump = abs(float(b["close"]) / float(prev_close) - 1.0)
                    if jump > 0.5:
                        extreme_jumps += 1
                        findings.append({"kind": "price", "code": "extreme_jump", "symbol": sym, "ts": ts, "jump": jump})
                    if float(b["close"]) == float(prev_close) and float(b["open"]) == float(prev_close):
                        stale += 1
                prev_ts = ts
                prev_close = b["close"]

        n = len(bars)
        uniqueness = 1.0 - (dup_ts / max(n, 1))
        validity = 1.0 - (len([f for f in findings if f.get("severity") != "warn"]) / max(n, 1))
        validity = max(0.0, min(1.0, validity))
        consistency = 1.0 if out_of_order == 0 and not any(
            f["code"] in ("high_below_low", "open_outside_range", "close_outside_range") for f in findings
        ) else 0.6
        completeness = 1.0 if n >= 10 else n / 10.0
        timeliness = 0.0 if future_ts else 1.0
        adjustment_confidence = 0.8  # raw preserved; adjustments optional
        source_confidence = 0.5 if self.store.get_dataset(dataset_id, dataset_version).get("is_synthetic") else 0.85

        scores = {
            "completeness": round(completeness, 4),
            "consistency": round(consistency, 4),
            "timeliness": round(timeliness, 4),
            "uniqueness": round(uniqueness, 4),
            "validity": round(validity, 4),
            "adjustment_confidence": adjustment_confidence,
            "source_confidence": source_confidence,
        }

        # Deduplicate blocking
        blocking = sorted(set(blocking))
        return self._finalize(dataset_id, dataset_version, findings, blocking, scores, extra={
            "bar_count": n,
            "duplicate_timestamps": dup_ts,
            "out_of_order": out_of_order,
            "future_timestamps": future_ts,
            "weekend_bars": weekend_bars,
            "extreme_jumps": extreme_jumps,
            "stale_repeated_bars": stale,
            "zero_volume_bars": zero_vol,
            "negative_volume": neg_vol,
        })

    def _finalize(
        self,
        dataset_id: str,
        dataset_version: str,
        findings: list,
        blocking: list,
        scores: dict,
        extra: dict | None = None,
    ) -> dict[str, Any]:
        # Numerical score must not hide blocking defects
        if blocking:
            if any(b in blocking for b in (
                "negative_price", "high_below_low", "zero_price", "non_finite_price",
                "duplicate_timestamp", "timestamp_out_of_order", "future_timestamp", "negative_volume",
                "no_bars",
            )):
                classification = QualityClass.REJECTED.value if "no_bars" in blocking or "negative_price" in blocking or "high_below_low" in blocking else QualityClass.QUARANTINED.value
            else:
                classification = QualityClass.LIMITED_USE.value
        else:
            avg = sum(scores.values()) / max(len(scores), 1)
            if avg >= 0.9:
                classification = QualityClass.HIGH_CONFIDENCE.value
            elif avg >= 0.75:
                classification = QualityClass.RESEARCH_USABLE_WITH_WARNINGS.value
            else:
                classification = QualityClass.LIMITED_USE.value

        report = {
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "classification": classification,
            "scores": scores,
            "findings": findings[:200],
            "finding_count": len(findings),
            "blocking_defects": blocking,
            "blocking_defect_count": len(blocking),
            "price_integrity": "fail" if any(f["kind"] == "price" and f["code"] in (
                "negative_price", "high_below_low", "zero_price", "non_finite"
            ) for f in findings) else "pass_with_warnings" if any(f["kind"] == "price" for f in findings) else "pass",
            "timestamp_integrity": "fail" if any(f["kind"] == "timestamp" for f in findings if f["code"] in (
                "duplicate_timestamp", "out_of_order", "future_timestamp"
            )) else "pass_with_warnings" if any(f["kind"] == "timestamp" for f in findings) else "pass",
            "volume_integrity": "fail" if any(f.get("code") == "negative_volume" for f in findings) else "pass_with_warnings" if any(f["kind"] == "volume" for f in findings) else "pass",
            "note": "Numerical quality score does not override blocking defects",
            **(extra or {}),
        }
        eh = evidence_hash(report)
        report["evidence_hash"] = eh
        rid = _uid("qual")
        self.store.execute(
            """INSERT INTO md_quality_reports(
                id, dataset_id, dataset_version, classification, scores_json, findings_json,
                blocking_defects_json, report_json, evidence_hash, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                rid, dataset_id, dataset_version, classification,
                json.dumps(scores), json.dumps(findings[:200], default=str),
                json.dumps(blocking), json.dumps(report, default=str), eh, time.time(),
            ),
        )
        ds = self.store.get_dataset(dataset_id, dataset_version)
        if ds:
            ds["quality_status"] = classification
            if classification in (QualityClass.REJECTED.value, QualityClass.QUARANTINED.value):
                ds["state"] = DatasetState.QUARANTINED.value
            elif classification in (
                QualityClass.HIGH_CONFIDENCE.value,
                QualityClass.RESEARCH_USABLE_WITH_WARNINGS.value,
            ):
                ds["state"] = DatasetState.QUALITY_REVIEW_REQUIRED.value
            else:
                ds["state"] = DatasetState.QUALITY_REVIEW_REQUIRED.value
            self.store.upsert_dataset(ds)

        self.store.audit("quality.evaluate", subject=dataset_id, detail={
            "classification": classification, "blocking": blocking,
        })
        report["ok"] = True
        report["report_id"] = rid
        report.update(AUTHORITY_VALUES)
        return report

    def latest(self, dataset_id: str, dataset_version: str) -> dict[str, Any]:
        row = self.store.query_one(
            """SELECT * FROM md_quality_reports WHERE dataset_id=? AND dataset_version=?
               ORDER BY created_at DESC LIMIT 1""",
            (dataset_id, dataset_version),
        )
        if not row:
            return {"ok": False, "code": "NO_QUALITY_REPORT", **AUTHORITY_VALUES}
        report = json.loads(row["report_json"])
        report["ok"] = True
        report.update(AUTHORITY_VALUES)
        return report
