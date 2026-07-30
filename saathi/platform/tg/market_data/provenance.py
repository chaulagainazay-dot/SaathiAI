"""M257 — Provenance capture for datasets."""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.market_data.errors import PROVENANCE_INCOMPLETE, MarketDataError
from saathi.platform.tg.market_data.models import AUTHORITY_VALUES, ENGINE_VERSION
from saathi.platform.tg.market_data.storage import MarketDataStore, evidence_hash, _uid


class ProvenanceEngine:
    def __init__(self, store: MarketDataStore):
        self.store = store

    def record(
        self,
        dataset_id: str,
        dataset_version: str,
        *,
        original_publisher: str = "",
        source_location: str = "",
        retrieval_date: str = "",
        retrieval_method: str = "local_file",
        transformation_history: list | None = None,
        parent_dataset: str = "",
        derived_lineage: list | None = None,
        software_version: str = ENGINE_VERSION,
        processing_config: dict | None = None,
        operator: str = "system",
    ) -> dict[str, Any]:
        if not original_publisher and not source_location:
            raise MarketDataError(
                PROVENANCE_INCOMPLETE,
                "Original publisher or source location required",
            )
        rec = {
            "id": _uid("prov"),
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "original_publisher": original_publisher,
            "source_location": source_location,
            "retrieval_date": retrieval_date or time.strftime("%Y-%m-%d"),
            "retrieval_method": retrieval_method,
            "transformation_history": transformation_history or [],
            "parent_dataset": parent_dataset,
            "derived_lineage": derived_lineage or [],
            "software_version": software_version,
            "processing_config": processing_config or {},
            "operator": operator,
        }
        eh = evidence_hash(rec)
        import json
        self.store.execute(
            """INSERT INTO md_provenance(
                id, dataset_id, dataset_version, original_publisher, source_location,
                retrieval_date, retrieval_method, transformation_history_json, parent_dataset,
                derived_lineage_json, software_version, processing_config_json, operator,
                evidence_hash, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rec["id"], dataset_id, dataset_version, original_publisher, source_location,
                rec["retrieval_date"], retrieval_method,
                json.dumps(rec["transformation_history"]), parent_dataset,
                json.dumps(rec["derived_lineage"]), software_version,
                json.dumps(rec["processing_config"]), operator, eh, time.time(),
            ),
        )
        self.store.audit("provenance.record", subject=dataset_id, detail={
            "version": dataset_version, "publisher": original_publisher, "evidence_hash": eh,
        })
        out = {**rec, "evidence_hash": eh, "ok": True, **AUTHORITY_VALUES}
        return out

    def get(self, dataset_id: str, dataset_version: str) -> dict[str, Any]:
        import json
        row = self.store.query_one(
            """SELECT * FROM md_provenance WHERE dataset_id=? AND dataset_version=?
               ORDER BY created_at DESC LIMIT 1""",
            (dataset_id, dataset_version),
        )
        if not row:
            return {"ok": False, "code": PROVENANCE_INCOMPLETE, "dataset_id": dataset_id, **AUTHORITY_VALUES}
        return {
            "ok": True,
            "dataset_id": row["dataset_id"],
            "dataset_version": row["dataset_version"],
            "original_publisher": row["original_publisher"],
            "source_location": row["source_location"],
            "retrieval_date": row["retrieval_date"],
            "retrieval_method": row["retrieval_method"],
            "transformation_history": json.loads(row["transformation_history_json"] or "[]"),
            "parent_dataset": row["parent_dataset"],
            "derived_lineage": json.loads(row["derived_lineage_json"] or "[]"),
            "software_version": row["software_version"],
            "processing_configuration": json.loads(row["processing_config_json"] or "{}"),
            "operator": row["operator"],
            "evidence_hash": row["evidence_hash"],
            **AUTHORITY_VALUES,
        }

    def require_complete(self, dataset_id: str, dataset_version: str) -> dict[str, Any]:
        p = self.get(dataset_id, dataset_version)
        if not p.get("ok"):
            raise MarketDataError(PROVENANCE_INCOMPLETE, f"Missing provenance for {dataset_id}")
        if not p.get("original_publisher") and not p.get("source_location"):
            raise MarketDataError(PROVENANCE_INCOMPLETE, "Publisher and source location empty")
        if not p.get("evidence_hash"):
            raise MarketDataError(PROVENANCE_INCOMPLETE, "Missing provenance evidence hash")
        return p
