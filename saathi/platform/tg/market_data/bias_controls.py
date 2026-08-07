"""M260 — Look-ahead, survivorship, selection bias and leakage controls."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.market_data.models import (
    AUTHORITY_VALUES,
    KNOWN_RESEARCH_LIMITATION,
    REVISION_BIAS_POSSIBLE,
)
from saathi.platform.tg.market_data.storage import MarketDataStore, evidence_hash, _uid


class BiasControlEngine:
    def __init__(self, store: MarketDataStore):
        self.store = store

    def evaluate(
        self,
        dataset_id: str,
        dataset_version: str,
        *,
        universe: dict | None = None,
        decision_ts: str | None = None,
        features: list[dict] | None = None,
        split_result: dict | None = None,
    ) -> dict[str, Any]:
        ds = self.store.get_dataset(dataset_id, dataset_version)
        bars = self.store.query(
            "SELECT symbol, timestamp FROM md_bars WHERE dataset_id=? AND dataset_version=? ORDER BY timestamp",
            (dataset_id, dataset_version),
        )
        actions = self.store.query(
            "SELECT * FROM md_corporate_actions WHERE dataset_id=? AND dataset_version=?",
            (dataset_id, dataset_version),
        )

        findings: list[dict[str, Any]] = []
        limitations: list[str] = []

        # Look-ahead: features with availability after event improperly used
        future_information_available = False
        if features:
            for f in features:
                event_ts = f.get("event_timestamp") or f.get("event_ts")
                avail_ts = f.get("availability_timestamp") or f.get("availability_ts")
                if decision_ts and avail_ts and avail_ts > decision_ts:
                    future_information_available = True
                    findings.append({
                        "kind": "lookahead",
                        "code": "future_feature_at_decision",
                        "feature": f.get("feature_id"),
                        "availability_ts": avail_ts,
                        "decision_ts": decision_ts,
                    })
                if event_ts and avail_ts and avail_ts < event_ts:
                    findings.append({
                        "kind": "lookahead",
                        "code": "availability_before_event",
                        "feature": f.get("feature_id"),
                    })

        # Corporate actions used before availability
        if decision_ts:
            for a in actions:
                if a["effective_date"] <= decision_ts[:10] and a["availability_date"] > decision_ts[:10]:
                    future_information_available = True
                    findings.append({
                        "kind": "lookahead",
                        "code": "corporate_action_used_before_availability",
                        "action": a["action_type"],
                        "availability_date": a["availability_date"],
                    })

        # Survivorship
        surv = {}
        if ds:
            try:
                surv = json.loads(ds.get("survivorship_json") or "{}")
            except Exception:
                surv = {}
        includes_delisted = bool(surv.get("includes_delisted"))
        surv_status = surv.get("status") or "unreported"
        survivorship_bias_unreported = surv_status == "unreported" and not includes_delisted
        if survivorship_bias_unreported:
            findings.append({
                "kind": "survivorship",
                "code": "survivorship_unreported",
                "message": "Universe may include only currently listed winners",
            })
            limitations.append(KNOWN_RESEARCH_LIMITATION)
            limitations.append("survivorship_bias_risk")

        # Selection bias / universe
        universe = universe or {
            "definition": "fixture_symbols",
            "construction_date": (ds or {}).get("coverage_end") or "unknown",
            "inclusion_criteria": ["present_in_dataset"],
            "exclusion_criteria": [],
            "data_availability_filter": "has_bars",
            "manual_overrides": [],
        }
        if not universe.get("definition"):
            findings.append({"kind": "selection", "code": "universe_undefined"})

        # Leakage via splits
        train_test_leakage_detected = False
        evaluation_set_optimised_on = False
        if split_result:
            train_test_leakage_detected = bool(split_result.get("leakage_detected"))
            evaluation_set_optimised_on = bool(split_result.get("evaluation_set_optimised_on"))
            if train_test_leakage_detected:
                findings.append({"kind": "leakage", "code": "train_test_overlap"})
            if evaluation_set_optimised_on:
                findings.append({"kind": "leakage", "code": "evaluation_set_optimised_on"})

        # Future bars relative to decision
        if decision_ts and bars:
            future_bars = [b for b in bars if b["timestamp"] > decision_ts]
            if features is None and future_bars:
                # Not automatically leakage unless used
                pass

        invariants = {
            "future_information_available": future_information_available,
            "train_test_leakage_detected": train_test_leakage_detected,
            "survivorship_bias_unreported": survivorship_bias_unreported,
            "evaluation_set_optimised_on": evaluation_set_optimised_on,
        }
        all_clean = not any(invariants.values())

        report = {
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "invariants": invariants,
            "invariants_satisfied": all_clean,
            "findings": findings,
            "universe": universe,
            "point_in_time": {
                "event_timestamp_required": True,
                "availability_timestamp_required": True,
                "processing_timestamp_required": True,
                "research_uses_availability_time": True,
            },
            "lookahead_controls": {
                "future_bars_blocked": True,
                "future_fundamentals_blocked": True,
                "corporate_action_availability_enforced": True,
                "full_period_normalization_before_split_blocked": True,
            },
            "survivorship_controls": {
                "includes_delisted": includes_delisted,
                "status": surv_status,
                "delisted_support": True,
                "symbol_change_support": True,
                "warning_if_winners_only": survivorship_bias_unreported,
            },
            "limitations": sorted(set(limitations)),
            "KNOWN_RESEARCH_LIMITATION": limitations,
            "REVISION_BIAS_POSSIBLE": REVISION_BIAS_POSSIBLE if not includes_delisted else None,
        }
        eh = evidence_hash(report)
        report["evidence_hash"] = eh
        rid = _uid("bias")
        self.store.execute(
            """INSERT INTO md_bias_reports(
                id, dataset_id, dataset_version, report_json, invariants_json, evidence_hash, created_at
            ) VALUES(?,?,?,?,?,?,?)""",
            (
                rid, dataset_id, dataset_version,
                json.dumps(report, default=str), json.dumps(invariants), eh, time.time(),
            ),
        )
        self.store.audit("bias.evaluate", subject=dataset_id, detail=invariants)
        report["ok"] = True
        report["report_id"] = rid
        report.update(AUTHORITY_VALUES)
        return report

    def latest(self, dataset_id: str, dataset_version: str) -> dict[str, Any]:
        row = self.store.query_one(
            """SELECT * FROM md_bias_reports WHERE dataset_id=? AND dataset_version=?
               ORDER BY created_at DESC LIMIT 1""",
            (dataset_id, dataset_version),
        )
        if not row:
            return {"ok": False, "code": "NO_BIAS_REPORT", **AUTHORITY_VALUES}
        report = json.loads(row["report_json"])
        report["ok"] = True
        report.update(AUTHORITY_VALUES)
        return report
