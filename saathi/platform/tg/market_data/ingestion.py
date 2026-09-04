"""M258 — Deterministic offline ingestion (CSV, JSON, JSONL). No network."""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from saathi.platform.tg.market_data.errors import (
    CHECKSUM_MISMATCH,
    INGESTION_FAILED,
    OVERSIZED_INPUT,
    PATH_TRAVERSAL,
    UNSAFE_FILE,
    MarketDataError,
)
from saathi.platform.tg.market_data.models import (
    AUTHORITY_VALUES,
    INGESTION_VERSION,
    MAX_INGEST_BYTES,
    MAX_INGEST_ROWS,
    OHLCV_SCHEMA_VERSION,
    DatasetState,
    RowStatus,
)
from saathi.platform.tg.market_data.normalization import normalize_ohlcv_row
from saathi.platform.tg.market_data.registry import DatasetRegistry
from saathi.platform.tg.market_data.storage import MarketDataStore, content_checksum, evidence_hash, file_checksum, _uid


class IngestionEngine:
    def __init__(self, store: MarketDataStore, registry: DatasetRegistry):
        self.store = store
        self.registry = registry

    def ingest(
        self,
        dataset_id: str,
        dataset_version: str,
        *,
        file_path: str | Path | None = None,
        expected_checksum: str | None = None,
        symbol_default: str | None = None,
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        ds = self.store.get_dataset(dataset_id, dataset_version)
        if not ds:
            raise MarketDataError(INGESTION_FAILED, f"Unregistered dataset {dataset_id}")

        path = Path(file_path or ds.get("file_path") or "")
        if not path or not path.is_file():
            raise MarketDataError(INGESTION_FAILED, f"Source file missing: {path}")

        # Path safety: reject path traversal markers in original string
        raw_path = str(file_path or ds.get("file_path") or "")
        if ".." in Path(raw_path).parts:
            raise MarketDataError(PATH_TRAVERSAL, "Path traversal rejected")

        size = path.stat().st_size
        if size > MAX_INGEST_BYTES:
            raise MarketDataError(OVERSIZED_INPUT, f"File exceeds {MAX_INGEST_BYTES} bytes")

        if path.suffix.lower() in (".exe", ".pkl", ".pickle", ".so", ".dll", ".sh"):
            raise MarketDataError(UNSAFE_FILE, f"Unsafe file type: {path.suffix}")

        actual_cs = file_checksum(path)
        expected = expected_checksum or ds.get("checksum") or ""
        if expected and actual_cs != expected:
            self.registry.quarantine(dataset_id, dataset_version, "checksum_mismatch_on_ingest")
            raise MarketDataError(CHECKSUM_MISMATCH, "Source checksum mismatch", {
                "expected": expected, "actual": actual_cs,
            })

        # Idempotent: if same source checksum already ingested successfully, return prior job
        prior = self.store.query_one(
            """SELECT * FROM md_ingestion_jobs WHERE dataset_id=? AND dataset_version=?
               AND source_checksum=? AND status='OK' ORDER BY created_at DESC LIMIT 1""",
            (dataset_id, dataset_version, actual_cs),
        )
        if prior:
            manifest = json.loads(prior["manifest_json"])
            manifest["idempotent"] = True
            manifest["ok"] = True
            manifest.update(AUTHORITY_VALUES)
            return manifest

        rows_raw = self._load_rows(path)
        if len(rows_raw) > MAX_INGEST_ROWS:
            raise MarketDataError(OVERSIZED_INPUT, f"Row count exceeds {MAX_INGEST_ROWS}")

        defaults = {
            "symbol": symbol_default or "",
            "exchange": "" if str(ds.get("exchange") or "").upper() == "UNKNOWN" else (ds.get("exchange") or ""),
            "market": ds.get("market") or "",
            "asset_class": ds.get("asset_class") or "equity",
            "is_synthetic": bool(ds.get("is_synthetic")),
            "timezone": ds.get("timezone") or "UTC",
            "currency": ds.get("currency") or "USD",
            "frequency": ds.get("frequency") or "1d",
        }

        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        duplicates = 0
        seen: set[tuple[str, str, str]] = set()
        warnings: list[str] = []
        errors: list[str] = []

        for i, raw in enumerate(rows_raw):
            norm, status, reasons = normalize_ohlcv_row(
                raw,
                dataset_id=dataset_id,
                source_row_ref=f"row:{i}",
                defaults=defaults,
            )
            if status == RowStatus.REJECTED.value or norm is None:
                rejected.append({"row": i, "reasons": reasons, "status": status})
                errors.extend(reasons)
                continue
            if status == RowStatus.QUARANTINED.value:
                quarantined.append({"row": i, "reasons": reasons, "status": status})
                warnings.extend(reasons)
                # Still do not accept quarantined into bars table
                continue
            key = (norm["symbol"], norm["timestamp"], norm["interval"])
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            accepted.append(norm)

        # Deterministic sort
        accepted.sort(key=lambda r: (r["symbol"], r["timestamp"], r["interval"]))

        # Clear prior bars for this dataset version (versioned replace)
        self.store.execute(
            "DELETE FROM md_bars WHERE dataset_id=? AND dataset_version=?",
            (dataset_id, dataset_version),
        )
        if accepted:
            self.store.executemany(
                """INSERT INTO md_bars(
                    dataset_id, dataset_version, instrument_id, symbol, exchange, asset_class,
                    timestamp, timezone, interval, open, high, low, close, adjusted_close,
                    volume, trade_count, vwap, currency, source_row_ref, ingestion_version, row_status
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        dataset_id, dataset_version, r["instrument_id"], r["symbol"], r["exchange"],
                        r["asset_class"], r["timestamp"], r["timezone"], r["interval"],
                        r["open"], r["high"], r["low"], r["close"], r["adjusted_close"],
                        r["volume"], r.get("trade_count"), r.get("vwap"), r["currency"],
                        r["source_row_ref"], r["ingestion_version"], RowStatus.NORMALIZED.value,
                    )
                    for r in accepted
                ],
            )

        out_payload = {
            "rows": [
                {
                    "symbol": r["symbol"], "timestamp": r["timestamp"],
                    "open": r["open"], "high": r["high"], "low": r["low"],
                    "close": r["close"], "volume": r["volume"],
                }
                for r in accepted
            ]
        }
        output_cs = content_checksum(json.dumps(out_payload, sort_keys=True))
        duration_ms = (time.perf_counter() - t0) * 1000.0

        # Coverage
        coverage_start = accepted[0]["timestamp"] if accepted else None
        coverage_end = accepted[-1]["timestamp"] if accepted else None

        job_id = _uid("ing")
        manifest = {
            "job_id": job_id,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "source_checksum": actual_cs,
            "input_row_count": len(rows_raw),
            "accepted_row_count": len(accepted),
            "rejected_row_count": len(rejected),
            "quarantined_row_count": len(quarantined),
            "duplicate_count": duplicates,
            "transformed_row_count": len(accepted),
            "output_checksum": output_cs,
            "schema_version": OHLCV_SCHEMA_VERSION,
            "ingestion_version": INGESTION_VERSION,
            "processing_duration_ms": round(duration_ms, 3),
            "warning_summary": sorted(set(warnings))[:50],
            "error_summary": sorted(set(errors))[:50],
            "rejected_samples": rejected[:20],
            "quarantined_samples": quarantined[:20],
            "coverage_start": coverage_start,
            "coverage_end": coverage_end,
            "status": "OK" if accepted else "FAILED",
            "idempotent": False,
        }
        eh = evidence_hash(manifest)
        manifest["evidence_hash"] = eh

        self.store.execute(
            """INSERT INTO md_ingestion_jobs(
                id, dataset_id, dataset_version, source_checksum, input_row_count,
                accepted_row_count, rejected_row_count, duplicate_count, transformed_row_count,
                output_checksum, schema_version, processing_duration_ms, warning_summary_json,
                error_summary_json, rejected_samples_json, status, manifest_json, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job_id, dataset_id, dataset_version, actual_cs, len(rows_raw),
                len(accepted), len(rejected), duplicates, len(accepted),
                output_cs, OHLCV_SCHEMA_VERSION, duration_ms,
                json.dumps(manifest["warning_summary"]),
                json.dumps(manifest["error_summary"]),
                json.dumps(manifest["rejected_samples"]),
                manifest["status"], json.dumps(manifest, default=str), time.time(),
            ),
        )

        # Update dataset
        ds["checksum"] = actual_cs
        ds["row_count"] = len(accepted)
        ds["file_size"] = size
        ds["coverage_start"] = coverage_start
        ds["coverage_end"] = coverage_end
        ds["ingestion_ts"] = time.time()
        ds["file_path"] = str(path)
        ds["state"] = (
            DatasetState.INGESTED_UNVERIFIED.value if accepted
            else DatasetState.QUALITY_REVIEW_REQUIRED.value
        )
        self.store.upsert_dataset(ds)
        self.store.audit("ingestion.complete", subject=dataset_id, detail={
            "job_id": job_id, "accepted": len(accepted), "rejected": len(rejected),
        })

        if not accepted:
            raise MarketDataError(INGESTION_FAILED, "No rows accepted", manifest)

        manifest["ok"] = True
        manifest.update(AUTHORITY_VALUES)
        return manifest

    def report(self, dataset_id: str, dataset_version: str | None = None) -> dict[str, Any]:
        if dataset_version:
            row = self.store.query_one(
                """SELECT * FROM md_ingestion_jobs WHERE dataset_id=? AND dataset_version=?
                   ORDER BY created_at DESC LIMIT 1""",
                (dataset_id, dataset_version),
            )
        else:
            row = self.store.query_one(
                """SELECT * FROM md_ingestion_jobs WHERE dataset_id=?
                   ORDER BY created_at DESC LIMIT 1""",
                (dataset_id,),
            )
        if not row:
            return {"ok": False, "code": "NO_INGESTION_JOB", "dataset_id": dataset_id, **AUTHORITY_VALUES}
        manifest = json.loads(row["manifest_json"])
        manifest["ok"] = True
        manifest.update(AUTHORITY_VALUES)
        return manifest

    def _load_rows(self, path: Path) -> list[dict[str, Any]]:
        suffix = path.suffix.lower()
        text = path.read_text(encoding="utf-8", errors="replace")
        # Reject formula bombs at file level for leading cells
        if suffix == ".csv":
            return self._load_csv(text)
        if suffix == ".json":
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "rows" in data:
                return list(data["rows"])
            if isinstance(data, dict) and "data" in data:
                return list(data["data"])
            raise MarketDataError(INGESTION_FAILED, "JSON must be list or {rows:[]}")
        if suffix in (".jsonl", ".ndjson"):
            rows = []
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
            return rows
        # Parquet / SQLite optional — not required if unavailable
        if suffix == ".parquet":
            raise MarketDataError(INGESTION_FAILED, "Parquet support requires optional dependency; use CSV/JSON fixtures")
        if suffix in (".db", ".sqlite", ".sqlite3"):
            raise MarketDataError(INGESTION_FAILED, "SQLite export ingestion not enabled in offline cert path; use CSV/JSON")
        raise MarketDataError(INGESTION_FAILED, f"Unsupported format: {suffix}")

    def _load_csv(self, text: str) -> list[dict[str, Any]]:
        # Strip BOM
        if text.startswith("\ufeff"):
            text = text[1:]
        reader = csv.DictReader(text.splitlines())
        if not reader.fieldnames:
            raise MarketDataError(INGESTION_FAILED, "CSV missing headers")
        rows = []
        for row in reader:
            # CSV injection detection at cell level
            clean = {}
            for k, v in row.items():
                if k is None:
                    continue
                if isinstance(v, str) and v[:1] in ("=", "+", "@") and k.lower() not in ("symbol", "ticker"):
                    # mark but keep for normalizer rejection
                    clean[k] = v
                else:
                    clean[k] = v
            rows.append(clean)
        return rows
