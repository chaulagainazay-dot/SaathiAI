"""Historical dataset import orchestration (M185–M187).

Local-first. Disk preflight. Fingerprint. Quality gate. Quarantine. Immutable accept.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from saathi.platform.nepse.calendar import (
    NEPSE_CALENDAR_V2_CANONICAL,
    CalendarCoverageStatus,
    NepseCalendar,
)
from saathi.platform.tg.historical.calendars import NEPSE_BACKTEST_POLICY
from saathi.platform.tg.historical.adapters.binance import BinancePublicHistoricalAdapter
from saathi.platform.tg.historical.adapters.local_file import LocalFileAdapter
from saathi.platform.tg.historical.adapters.nepse import NepseLocalAdapter
from saathi.platform.tg.historical.adapters.yahoo import YahooPublicHistoricalAdapter
from saathi.platform.tg.historical.models import (
    AdjustmentMethodology,
    CorporateAction,
    DataImportRun,
    DatasetClassification,
    DatasetFingerprint,
    DatasetManifest,
    DatasetSource,
    DatasetVersion,
    DataQualityVerdict,
    ImportStatus,
    fingerprint_payload,
)
from saathi.platform.tg.historical.normalize import apply_corporate_actions
from saathi.platform.tg.historical.quality import build_coverage, evaluate_dataset_quality
from saathi.platform.tg.historical.store import HistoricalDatasetStore, HistoricalStoreError


ADAPTERS = {
    "local": LocalFileAdapter,
    "local_csv": LocalFileAdapter,
    "local_parquet": LocalFileAdapter,
    "local_file": LocalFileAdapter,
    "binance": BinancePublicHistoricalAdapter,
    "binance_public": BinancePublicHistoricalAdapter,
    "nepse": NepseLocalAdapter,
    "nepse_local": NepseLocalAdapter,
    "yahoo": YahooPublicHistoricalAdapter,
    "yahoo_public": YahooPublicHistoricalAdapter,
}


class HistoricalImportService:
    def __init__(self, store: HistoricalDatasetStore | None = None):
        self.store = store or HistoricalDatasetStore()

    def import_file(
        self,
        path: str | Path,
        *,
        adapter: str = "local_file",
        dataset_name: str = "",
        version: str = "1.0.0",
        market: str = "",
        currency: str = "USD",
        timezone: str = "UTC",
        timeframe: str = "1d",
        calendar_name: str = "DEFAULT_24_5",
        classification: str = "HISTORICAL_LOCAL_DATASET",
        default_instrument: str = "UNKNOWN",
        corporate_actions: list[CorporateAction] | None = None,
        adjustment_methodology: str = "SPLIT_ONLY",
        org_id: str = "local",
        workspace_id: str = "local",
        schema_map: dict[str, str] | None = None,
        min_rows: int = 20,
        force_fixture_class: bool = False,
        nepse_calendar: NepseCalendar | None = None,
    ) -> dict[str, Any]:
        # An explicitly NEPSE dataset is a bounded identity contract.  Do not
        # let historical defaults (USD, UTC, DEFAULT_24_5) leak into it when a
        # caller uses the generic local-file adapter.
        if str(market or "").strip().upper() == "NEPSE":
            market = "NEPSE"
            currency = "NPR"
            timezone = "Asia/Kathmandu"
            calendar_name = "NEPSE"
        path = Path(path)
        pre = self.store.disk_preflight(path.parent if path.parent.exists() else ".")
        if not pre.get("ok"):
            return {
                "status": "REJECTED",
                "reason": "insufficient_disk",
                "preflight": pre,
                "paper_only": True,
            }

        run = DataImportRun(
            dataset_id="",
            version=version,
            adapter=adapter,
            status=ImportStatus.RUNNING,
            source_path=str(path),
            progress=0.05,
            message="starting",
            org_id=org_id,
            workspace_id=workspace_id,
        )
        self.store.record_import(run)

        # Load via adapter
        try:
            cls = ADAPTERS.get(adapter)
            if cls is None:
                run.status = ImportStatus.REJECTED
                run.error = f"unknown_adapter:{adapter}"
                run.finished_at = time.time()
                return {"status": "REJECTED", "error": run.error, "import_run": run.to_public()}

            adapter_inst = cls()
            if adapter in ("binance", "binance_public"):
                result = adapter_inst.load_from_file(  # type: ignore[attr-defined]
                    path,
                    symbol=default_instrument,
                    timeframe=timeframe,
                    currency=currency or "USDT",
                    schema_map=schema_map,
                )
                market = market or "BINANCE"
                calendar_name = calendar_name if calendar_name != "DEFAULT_24_5" else "BINANCE_24_7"
                currency = currency or "USDT"
            elif adapter in ("nepse", "nepse_local"):
                result = adapter_inst.load(  # type: ignore[call-arg]
                    path,
                    default_instrument=default_instrument,
                    schema_map=schema_map,
                    timeframe=timeframe,
                    currency="NPR",
                )
                market = market or "NEPSE"
                calendar_name = "NEPSE"
                currency = "NPR"
                timezone = "Asia/Kathmandu"
            elif adapter in ("yahoo", "yahoo_public"):
                result = adapter_inst.load_from_file(  # type: ignore[attr-defined]
                    path,
                    symbol=default_instrument,
                    schema_map=schema_map,
                    timeframe=timeframe,
                    currency=currency,
                )
                market = market or "US"
                calendar_name = calendar_name if calendar_name != "DEFAULT_24_5" else "US_RTH"
            else:
                result = adapter_inst.load(  # type: ignore[call-arg]
                    path,
                    default_instrument=default_instrument,
                    timeframe=timeframe,
                    currency=currency,
                    timezone_name=timezone,
                    schema_map=schema_map,
                )
        except Exception as e:
            run.status = ImportStatus.REJECTED
            run.error = f"{type(e).__name__}:{e}"[:240]
            run.finished_at = time.time()
            return {"status": "REJECTED", "error": run.error, "import_run": run.to_public()}

        run.progress = 0.4
        run.message = "loaded"
        if not result.ok or not result.bars:
            run.status = ImportStatus.REJECTED
            run.error = result.error or "empty_or_failed_load"
            run.finished_at = time.time()
            return {
                "status": "REJECTED",
                "error": run.error,
                "warnings": result.warnings,
                "import_run": run.to_public(),
            }

        # Corporate actions + normalize
        run.status = ImportStatus.NORMALIZING
        run.progress = 0.55
        actions = list(corporate_actions or [])
        try:
            method = AdjustmentMethodology(adjustment_methodology)
        except ValueError:
            method = AdjustmentMethodology.SPLIT_ONLY
        bars, audit = apply_corporate_actions(result.bars, actions, methodology=method)
        run.progress = 0.7

        # Quality
        canonical_nepse_calendar = nepse_calendar or NepseCalendar()
        quality = evaluate_dataset_quality(
            bars,
            calendar_name=calendar_name,
            currency=currency,
            timezone=timezone,
            timeframe=timeframe,
            min_rows=min_rows,
            corporate_action_status="APPLIED" if actions else "NONE",
            nepse_calendar=canonical_nepse_calendar if calendar_name == "NEPSE" else None,
        )
        coverage = build_coverage(
            bars,
            calendar_name=calendar_name,
            timeframe=timeframe,
            nepse_calendar=canonical_nepse_calendar if calendar_name == "NEPSE" else None,
        )

        if calendar_name == "NEPSE":
            calendar_version = NEPSE_CALENDAR_V2_CANONICAL
            calendar_source_version = canonical_nepse_calendar.calendar_source_version
            calendar_coverage_status = coverage.calendar_coverage_status
            calendar_policy = NEPSE_BACKTEST_POLICY
        else:
            calendar_version = "GENERIC_CALENDAR_UNVERSIONED"
            calendar_source_version = ""
            calendar_coverage_status = CalendarCoverageStatus.UNKNOWN.value
            calendar_policy = "GENERIC"

        # Classification
        if force_fixture_class:
            dcls = DatasetClassification.FIXTURE_TEST_ONLY
        else:
            try:
                dcls = DatasetClassification(classification)
            except ValueError:
                dcls = DatasetClassification.HISTORICAL_LOCAL_DATASET

        content_fp = fingerprint_payload([
            {
                "i": b.instrument,
                "ts": b.ts,
                "o": str(b.open),
                "h": str(b.high),
                "l": str(b.low),
                "c": str(b.close),
                "v": str(b.volume),
                "ac": str(b.adj_close),
            }
            for b in bars
        ])
        schema_fp = fingerprint_payload({
            "schema": "m184.ohlcv.v1",
            "timeframe": timeframe,
            "currency": currency,
            "calendar_version": calendar_version,
            "calendar_source_version": calendar_source_version,
            "calendar_coverage_status": calendar_coverage_status,
        })

        name = dataset_name or path.stem
        ds = self.store.ensure_dataset(
            name=name, market=market, org_id=org_id, workspace_id=workspace_id,
        )
        run.dataset_id = ds.id

        manifest = DatasetManifest(
            dataset_id=ds.id,
            version=version,
            market=market,
            currency=currency,
            timezone=timezone,
            timeframe=timeframe,
            instrument_universe=sorted({b.instrument for b in bars}),
            classification=dcls,
            adjustment_methodology=method,
            calendar_name=calendar_name,
            calendar_version=calendar_version,
            calendar_source_version=calendar_source_version,
            calendar_coverage_status=calendar_coverage_status,
            calendar_policy=calendar_policy,
            corporate_actions=actions,
            source=result.source or DatasetSource(adapter=adapter, uri=str(path)),
            notes=list(dict.fromkeys(list(result.warnings) + list(quality.warnings))),
        )

        dver = DatasetVersion(
            dataset_id=ds.id,
            version=version,
            status=ImportStatus.RUNNING,
            classification=dcls,
            fingerprint=DatasetFingerprint(
                content_fingerprint=content_fp,
                source_file_fingerprint=result.source_file_fingerprint,
                schema_fingerprint=schema_fp,
            ),
            coverage=coverage,
            quality=quality,
            manifest=manifest,
            row_count=len(bars),
            missing_bar_count=quality.missing_bar_count,
            duplicate_bar_count=quality.duplicate_bar_count,
            outlier_count=quality.outlier_count,
            corporate_action_status="APPLIED" if actions else "NONE",
            adjustment_methodology=method.value,
            import_timestamp=time.time(),
            normalization_timestamp=time.time(),
            org_id=org_id,
            workspace_id=workspace_id,
            market=market,
            currency=currency,
            timezone=timezone,
            timeframe=timeframe,
            instrument_universe=list(manifest.instrument_universe),
            source_path=str(path.resolve()) if path.exists() else str(path),
            adapter=adapter,
            bars=bars,
            transformations=list(audit.transformations),
            notes=list(dict.fromkeys(list(result.warnings) + list(quality.warnings))),
        )

        # Accept / quarantine / reject
        if quality.verdict == DataQualityVerdict.REJECTED:
            dver.reject("quality_rejected")
            try:
                self.store.put_version(dver, allow_duplicate_fp=True)
            except HistoricalStoreError:
                pass
            qrec = self.store.quarantine(dver, reason="quality_rejected", findings=quality.findings)
            run.status = ImportStatus.REJECTED
            run.progress = 1.0
            run.finished_at = time.time()
            run.message = "rejected"
            return {
                "status": "REJECTED",
                "dataset": ds.to_public(),
                "version": dver.to_public(),
                "quality": quality.to_public(),
                "quarantine": qrec.to_public(),
                "import_run": run.to_public(),
                "paper_only": True,
            }

        if quality.verdict in (DataQualityVerdict.QUARANTINED, DataQualityVerdict.INSUFFICIENT_COVERAGE):
            dver.quarantine(quality.verdict.value)
            try:
                self.store.put_version(dver, allow_duplicate_fp=True)
            except HistoricalStoreError as e:
                return {"status": "REJECTED", "error": f"{e.code}:{e.message}", "import_run": run.to_public()}
            qrec = self.store.quarantine(dver, reason=quality.verdict.value, findings=quality.findings)
            run.status = ImportStatus.QUARANTINED
            run.progress = 1.0
            run.finished_at = time.time()
            return {
                "status": "QUARANTINED",
                "dataset": ds.to_public(),
                "version": dver.to_public(),
                "quality": quality.to_public(),
                "quarantine": qrec.to_public(),
                "import_run": run.to_public(),
                "paper_only": True,
                "usable_for_promotion": False,
            }

        # Accept
        try:
            warnings = quality.verdict == DataQualityVerdict.ACCEPTED_WITH_WARNINGS
            dver.accept(warnings=warnings)
            self.store.put_version(dver)
        except HistoricalStoreError as e:
            run.status = ImportStatus.REJECTED
            run.error = f"{e.code}:{e.message}"
            run.finished_at = time.time()
            return {
                "status": "REJECTED",
                "error": run.error,
                "import_run": run.to_public(),
                "paper_only": True,
            }

        run.status = dver.status
        run.progress = 1.0
        run.finished_at = time.time()
        run.message = "accepted"
        return {
            "status": dver.status.value,
            "dataset": ds.to_public(),
            "version": dver.to_public(),
            "quality": quality.to_public(),
            "normalization": audit.to_public(),
            "import_run": run.to_public(),
            "promotable": dver.promotable,
            "paper_only": True,
            "live_authorized": False,
            "disclaimer": (
                "Imported historical dataset for research only. "
                "Not a live trading feed. Quality gates required before promotion."
            ),
        }
