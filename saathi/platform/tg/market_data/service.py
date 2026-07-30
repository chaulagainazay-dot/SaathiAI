"""M256–M263 Market Data & Signal Validation service facade.

RESEARCH ONLY. OFFLINE-FIRST. NO BROKER. NO API KEYS. NO LIVE TRADING.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from saathi.platform.tg.market_data.adjustments import AdjustmentEngine
from saathi.platform.tg.market_data.bias_controls import BiasControlEngine
from saathi.platform.tg.market_data.calendar import CalendarEngine
from saathi.platform.tg.market_data.catalog import DatasetCatalog
from saathi.platform.tg.market_data.corporate_actions import CorporateActionEngine
from saathi.platform.tg.market_data.dataset_split import DatasetSplitEngine
from saathi.platform.tg.market_data.errors import MarketDataError
from saathi.platform.tg.market_data.feature_store import FeatureStore
from saathi.platform.tg.market_data.ingestion import IngestionEngine
from saathi.platform.tg.market_data.licensing import LicenceEngine
from saathi.platform.tg.market_data.models import (
    AUTHORITY_VALUES,
    ENGINE_VERSION,
    LLM_BOUNDARY,
    MAX_STATE,
    MD_POSTURE,
    SCHEMA_VERSION,
    SYNTHETIC_TEST_DATA_LABEL,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
    DatasetState,
    SourceType,
)
from saathi.platform.tg.market_data.provenance import ProvenanceEngine
from saathi.platform.tg.market_data.quality import QualityEngine
from saathi.platform.tg.market_data.reconciliation import ReconciliationEngine
from saathi.platform.tg.market_data.registry import DatasetRegistry
from saathi.platform.tg.market_data.security import MarketDataSecurity
from saathi.platform.tg.market_data.signal_validation import SignalValidationEngine
from saathi.platform.tg.market_data.storage import MarketDataStore, evidence_hash, file_checksum, _uid


class MarketDataService:
    def __init__(self, db_path: str | Path | None = None, repo_root: Path | None = None):
        self.store = MarketDataStore(db_path)
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[4]
        self.registry = DatasetRegistry(self.store)
        self.catalog = DatasetCatalog(self.store, self.registry)
        self.licensing = LicenceEngine(self.store)
        self.provenance = ProvenanceEngine(self.store)
        self.ingestion = IngestionEngine(self.store, self.registry)
        self.quality = QualityEngine(self.store)
        self.calendar = CalendarEngine(self.store)
        self.corporate_actions = CorporateActionEngine(self.store)
        self.adjustments = AdjustmentEngine(self.store)
        self.bias = BiasControlEngine(self.store)
        self.splits = DatasetSplitEngine(self.store)
        self.features = FeatureStore(self.store)
        self.validation = SignalValidationEngine(self.store)
        self.reconciliation = ReconciliationEngine(self.store)
        self.security = MarketDataSecurity(self.repo_root)

    def posture(self) -> dict[str, Any]:
        return {
            **MD_POSTURE,
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "milestones": "M256-M263",
            "terminal_verdict_target": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "llm_boundary": dict(LLM_BOUNDARY),
            **AUTHORITY_VALUES,
        }

    def terminal_verdict(self) -> dict[str, Any]:
        return {
            "verdict": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "statements": list(TERMINAL_STATEMENTS),
            "capabilities": {
                "dataset_registry": True,
                "licence_governance": True,
                "provenance": True,
                "ingestion": True,
                "quality": True,
                "corporate_actions": True,
                "bias_controls": True,
                "feature_store": True,
                "signal_validation": True,
                "control_center": True,
            },
            "limitations": [
                "Not regulatory-grade market data",
                "Strategy results do not guarantee future performance",
                "Certification may use bounded synthetic fixtures labelled SYNTHETIC_TEST_DATA",
                "REAL_HISTORICAL_DATA_VALIDATION_INCOMPLETE when only fixtures used",
                "Holiday calendars are sample/incomplete",
                "No broker connectivity; research only",
                "Single-host SQLite market_data_research.db",
            ],
            **AUTHORITY_VALUES,
        }

    # ── M256 Registry ────────────────────────────────────────────────────
    def register_dataset(self, **kwargs: Any) -> dict[str, Any]:
        return self.registry.register(**kwargs)

    def register_dataset_file(self, path: str | Path, **kwargs: Any) -> dict[str, Any]:
        return self.registry.register_from_file(path, **kwargs)

    def list_datasets(self, state: str | None = None) -> dict[str, Any]:
        return self.registry.list_datasets(state)

    def get_dataset(self, dataset_id: str, version: str | None = None) -> dict[str, Any]:
        return self.registry.get(dataset_id, version)

    def quarantine_dataset(self, dataset_id: str, version: str, reason: str = "") -> dict[str, Any]:
        return self.registry.quarantine(dataset_id, version, reason)

    def revoke_dataset(self, dataset_id: str, version: str, reason: str = "") -> dict[str, Any]:
        return self.registry.revoke(dataset_id, version, reason)

    def verify_checksum(self, dataset_id: str, version: str) -> dict[str, Any]:
        return self.registry.verify_checksum(dataset_id, version)

    def dataset_registry_export(self) -> dict[str, Any]:
        return self.registry.catalogue_export()

    # ── M257 Governance ──────────────────────────────────────────────────
    def record_licence(self, dataset_id: str, version: str, **kwargs: Any) -> dict[str, Any]:
        return self.licensing.record_licence(dataset_id, version, **kwargs)

    def licence_check(self, dataset_id: str, version: str, use_case: str = "local_research") -> dict[str, Any]:
        return self.licensing.check_use(dataset_id, version, use_case)

    def record_provenance(self, dataset_id: str, version: str, **kwargs: Any) -> dict[str, Any]:
        return self.provenance.record(dataset_id, version, **kwargs)

    def get_provenance(self, dataset_id: str, version: str) -> dict[str, Any]:
        return self.provenance.get(dataset_id, version)

    def governance_export(self) -> dict[str, Any]:
        inv = self.licensing.inventory()
        inv["provenance_note"] = "Per-dataset provenance via md-provenance / API"
        return inv

    # ── M258 Ingestion ───────────────────────────────────────────────────
    def ingest(self, dataset_id: str, version: str, **kwargs: Any) -> dict[str, Any]:
        return self.ingestion.ingest(dataset_id, version, **kwargs)

    def ingest_report(self, dataset_id: str, version: str | None = None) -> dict[str, Any]:
        return self.ingestion.report(dataset_id, version)

    # ── M259 Quality / CA / Calendar ─────────────────────────────────────
    def quality_check(self, dataset_id: str, version: str, **kwargs: Any) -> dict[str, Any]:
        return self.quality.evaluate(dataset_id, version, **kwargs)

    def quality_report(self, dataset_id: str, version: str) -> dict[str, Any]:
        return self.quality.latest(dataset_id, version)

    def calendar_check(self, dataset_id: str, version: str) -> dict[str, Any]:
        return self.calendar.check_bars(dataset_id, version)

    def add_corporate_action(self, dataset_id: str, version: str, **kwargs: Any) -> dict[str, Any]:
        return self.corporate_actions.add(dataset_id, version, **kwargs)

    def list_corporate_actions(self, dataset_id: str, version: str) -> dict[str, Any]:
        return self.corporate_actions.list(dataset_id, version)

    def adjust(self, dataset_id: str, version: str, symbol: str) -> dict[str, Any]:
        return self.adjustments.apply_split_adjustments(dataset_id, version, symbol=symbol)

    # ── M260 Bias / Splits ───────────────────────────────────────────────
    def bias_check(self, dataset_id: str, version: str, **kwargs: Any) -> dict[str, Any]:
        return self.bias.evaluate(dataset_id, version, **kwargs)

    def split_dataset(self, dataset_id: str, version: str, kind: str = "chronological_holdout", **kwargs: Any) -> dict[str, Any]:
        if kind == "rolling_walk_forward":
            return self.splits.rolling_walk_forward(dataset_id, version, **kwargs)
        if kind == "expanding_window":
            return self.splits.expanding_window(dataset_id, version, **kwargs)
        return self.splits.chronological_holdout(dataset_id, version, **kwargs)

    # ── M261 Features ────────────────────────────────────────────────────
    def feature_list(self) -> dict[str, Any]:
        return self.features.catalogue()

    def feature_build(self, dataset_id: str, version: str, **kwargs: Any) -> dict[str, Any]:
        return self.features.build(dataset_id, version, **kwargs)

    def feature_lineage(self, feature_id: str, feature_version: str | None = None) -> dict[str, Any]:
        return self.features.lineage(feature_id, feature_version)

    # ── M262 Validation ──────────────────────────────────────────────────
    def validate_signal(
        self,
        strategy_id: str,
        dataset_id: str,
        version: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self.validation.validate(strategy_id, dataset_id, version, **kwargs)

    def compare_strategies(self, strategy_ids: list[str], dataset_id: str, version: str, **kwargs: Any) -> dict[str, Any]:
        return self.validation.compare_strategies(strategy_ids, dataset_id, version, **kwargs)

    def regime_analysis(self, dataset_id: str, version: str, strategy_id: str = "tf_dual_ma") -> dict[str, Any]:
        # Run validation and extract regime block
        split = self.splits.chronological_holdout(dataset_id, version, embargo_bars=2)
        val = self.validation.validate(strategy_id, dataset_id, version, split=split)
        return {
            "ok": True,
            "regime_analysis": val.get("regime_analysis"),
            "strategy_id": strategy_id,
            "dataset_id": dataset_id,
            "dataset_version": version,
            **AUTHORITY_VALUES,
        }

    # ── Approval path ────────────────────────────────────────────────────
    def approve_for_research(self, dataset_id: str, version: str, restricted: bool = False) -> dict[str, Any]:
        """Approve only when licence, provenance, checksum, quality gates pass."""
        ds = self.store.get_dataset(dataset_id, version)
        if not ds:
            return {"ok": False, "code": "UNREGISTERED_DATASET", **AUTHORITY_VALUES}
        try:
            self.licensing.gate_research_approval(dataset_id, version)
            self.provenance.require_complete(dataset_id, version)
        except MarketDataError as e:
            return {"ok": False, "code": e.code, "message": e.message, **AUTHORITY_VALUES}
        if not ds.get("checksum"):
            return {"ok": False, "code": "CHECKSUM_MISSING", **AUTHORITY_VALUES}
        q = self.quality.latest(dataset_id, version)
        if q.get("ok") and q.get("blocking_defects"):
            return {
                "ok": False,
                "code": "QUALITY_BLOCKING",
                "blocking_defects": q.get("blocking_defects"),
                **AUTHORITY_VALUES,
            }
        if q.get("classification") in ("REJECTED", "QUARANTINED"):
            return {"ok": False, "code": "QUALITY_BLOCKING", "classification": q.get("classification"), **AUTHORITY_VALUES}
        new_state = DatasetState.RESEARCH_RESTRICTED.value if restricted else DatasetState.RESEARCH_APPROVED.value
        return self.registry.transition(dataset_id, version, new_state, "research_approved_by_policy")

    # ── Bootstrap fixture pipeline ───────────────────────────────────────
    def bootstrap_fixture_pipeline(self) -> dict[str, Any]:
        """End-to-end governed pipeline on bundled synthetic fixture for certification."""
        fixture = Path(__file__).resolve().parent / "fixtures" / "synth_ohlcv_equity.csv"
        if not fixture.is_file():
            self._write_default_fixture(fixture)

        reg = self.registry.register_from_file(
            fixture,
            name="synth_ohlcv_equity_demo",
            provider="saathi_fixtures",
            source_type=SourceType.SYNTHETIC_TEST_DATA.value,
            is_synthetic=True,
            licence_type="CC0-1.0",
            market="US",
            exchange="XNAS",
            asset_class="equity",
            frequency="1d",
            description="Bounded synthetic OHLCV fixture for research certification",
            survivorship={"includes_delisted": False, "status": "unreported", "note": "synthetic"},
            limitations=[SYNTHETIC_TEST_DATA_LABEL, "REAL_HISTORICAL_DATA_VALIDATION_INCOMPLETE"],
            commercial_use_status="permitted",
            redistribution_status="permitted",
        )
        ds_id = reg["dataset_id"]
        ver = reg["dataset_version"]

        lic = self.licensing.record_licence(
            ds_id, ver,
            licence_name="CC0-1.0",
            official_source="https://creativecommons.org/publicdomain/zero/1.0/",
            commercial_use="permitted",
            redistribution="permitted",
            modification="permitted",
            attribution_required=False,
        )
        prov = self.provenance.record(
            ds_id, ver,
            original_publisher="SaathiAI Test Fixtures",
            source_location=str(fixture),
            retrieval_method="repository_fixture",
            transformation_history=[{"step": "none", "note": "raw synthetic generation"}],
            processing_config={"generator": "deterministic_fixture_v1"},
            operator="market_data_service",
        )
        ing = self.ingestion.ingest(ds_id, ver)
        # Add a sample split corporate action (does not destroy raw)
        ca = self.corporate_actions.add(
            ds_id, ver,
            symbol="DEMO",
            action_type="stock_split",
            effective_date="2024-06-15",
            availability_date="2024-06-15",
            factor=2.0,
            provenance="fixture",
        )
        adj = self.adjustments.apply_split_adjustments(ds_id, ver, symbol="DEMO")
        qual = self.quality.evaluate(ds_id, ver, now_ts="2026-07-30T00:00:00Z")
        cal = self.calendar.check_bars(ds_id, ver)
        split = self.splits.chronological_holdout(ds_id, ver, embargo_bars=2, purge_bars=0)
        bias = self.bias.evaluate(ds_id, ver, split_result=split)
        feats = self.features.build(ds_id, ver, fit_timestamps=split.get("train_timestamps"))
        # Approve if gates pass
        approval = self.approve_for_research(ds_id, ver, restricted=True)
        val = self.validation.validate(
            "tf_dual_ma", ds_id, ver,
            split=split,
            commission_bps=5.0,
            slippage_bps=8.0,
            seed=42,
            trial_count=1,
        )
        return {
            "ok": True,
            "dataset_id": ds_id,
            "dataset_version": ver,
            "registration": reg,
            "licence": lic,
            "provenance": prov,
            "ingestion": {k: ing.get(k) for k in (
                "job_id", "accepted_row_count", "rejected_row_count", "duplicate_count",
                "source_checksum", "output_checksum", "status", "idempotent",
            )},
            "corporate_action": ca,
            "adjustment": adj,
            "quality": {k: qual.get(k) for k in ("classification", "blocking_defects", "scores")},
            "calendar": {k: cal.get(k) for k in ("ok", "issue_count", "is_247")},
            "split": {k: split.get(k) for k in (
                "kind", "train", "validation", "test", "embargo_bars", "leakage_detected",
            )},
            "bias": {k: bias.get(k) for k in ("invariants", "invariants_satisfied", "limitations")},
            "features": {k: feats.get(k) for k in ("features_built", "value_count", "output_checksum")},
            "approval": approval,
            "validation": {
                "state": val.get("state"),
                "sharpe_ratio": val.get("sharpe_ratio"),
                "trade_count": val.get("trade_count"),
                "is_synthetic": val.get("is_synthetic"),
            },
            "SYNTHETIC_TEST_DATA": True,
            "REAL_HISTORICAL_DATA_VALIDATION_INCOMPLETE": True,
            **AUTHORITY_VALUES,
        }

    def _write_default_fixture(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Deterministic synthetic OHLCV weekdays only
        lines = ["date,symbol,open,high,low,close,volume"]
        px = 100.0
        # Generate ~120 weekdays from 2024-01-02
        from datetime import date, timedelta
        d = date(2024, 1, 2)
        n = 0
        seed = 42
        state = seed & 0x7FFFFFFF
        while n < 120:
            if d.weekday() < 5:
                state = (1103515245 * state + 12345) & 0x7FFFFFFF
                u = state / float(0x7FFFFFFF)
                ret = 0.0008 + (u - 0.5) * 0.015
                o = px
                c = px * (1 + ret)
                h = max(o, c) * (1 + abs(u - 0.5) * 0.01)
                l = min(o, c) * (1 - abs(u - 0.5) * 0.01)
                vol = int(1_000_000 * (0.8 + u * 0.4))
                lines.append(
                    f"{d.isoformat()},DEMO,{o:.4f},{h:.4f},{l:.4f},{c:.4f},{vol}"
                )
                px = c
                n += 1
            d += timedelta(days=1)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ── Dashboard / Control Center ───────────────────────────────────────
    def dashboard(self) -> dict[str, Any]:
        overview = self.catalog.overview()
        datasets = self.registry.list_datasets()
        features = self.features.catalogue()
        latest_val = self.validation.latest_report()
        sec = self.security.full_scan()
        return {
            "title": "Market Data & Research Validation Control Center",
            "verdict_target": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "statements": list(TERMINAL_STATEMENTS),
            "overview": overview,
            "datasets": datasets.get("datasets", [])[:50],
            "feature_count": features.get("count"),
            "latest_validation": {
                "state": latest_val.get("state"),
                "strategy_id": latest_val.get("strategy_id"),
                "dataset_id": latest_val.get("dataset_id"),
            } if latest_val.get("ok") else None,
            "security_ok": sec.get("ok"),
            "labels": {
                "RESEARCH_ONLY": True,
                "OFFLINE_FIRST": True,
                "NO_BROKER_CONNECTIVITY": True,
                "NO_ACCOUNT_ACCESS": True,
                "NO_ORDER_EXECUTION": True,
                "NO_LIVE_TRADING": True,
            },
            **AUTHORITY_VALUES,
        }

    def evidence_bundle(self) -> dict[str, Any]:
        return {
            "registry": self.registry.catalogue_export(),
            "governance": self.licensing.inventory(),
            "features": self.features.catalogue(),
            "sources": self.catalog.sources_inventory(),
            "security": self.security.full_scan(),
            **AUTHORITY_VALUES,
        }

    # ── Boundary refusals ────────────────────────────────────────────────
    def refuse_broker(self, target: str = "") -> dict[str, Any]:
        return self.security.refuse_broker_connect(target)

    def refuse_credentials(self, value: str | None = None) -> dict[str, Any]:
        return self.security.refuse_credentials(value)

    def refuse_order(self) -> dict[str, Any]:
        return self.security.refuse_order()

    def refuse_canary(self) -> dict[str, Any]:
        return self.security.refuse_canary()

    def security_scan(self) -> dict[str, Any]:
        return self.security.full_scan()

    # ── Certification ────────────────────────────────────────────────────
    def certify(self) -> dict[str, Any]:
        from saathi.platform.tg.market_data.certification import certify_market_data
        return certify_market_data(self)


_default: MarketDataService | None = None


def default_market_data() -> MarketDataService:
    global _default
    if _default is None:
        _default = MarketDataService()
    return _default


def reset_market_data_for_tests(db_path: str | Path | None = None) -> MarketDataService:
    global _default
    if _default is not None:
        try:
            _default.store.close()
        except Exception:
            pass
    _default = MarketDataService(db_path=db_path)
    return _default
