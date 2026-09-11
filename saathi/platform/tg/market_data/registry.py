"""M256 — Dataset registry, catalogue identity, versioning."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from saathi.platform.tg.market_data.errors import (
    CHECKSUM_MISMATCH,
    CHECKSUM_MISSING,
    DATASET_QUARANTINED,
    DATASET_REVOKED,
    UNREGISTERED_DATASET,
    VERSION_COLLISION,
    MarketDataError,
)
from saathi.platform.tg.market_data.models import (
    AUTHORITY_VALUES,
    OHLCV_SCHEMA_VERSION,
    DatasetState,
    SourceType,
)
from saathi.platform.tg.market_data.storage import MarketDataStore, content_checksum, evidence_hash, file_checksum, _uid
from saathi.platform.market_data.identity import IdentityValidationError, resolve_market_identity


def deterministic_dataset_id(
    provider: str,
    name: str,
    market: str,
    asset_class: str,
    frequency: str,
    source_ref: str = "",
) -> str:
    """Stable identity independent of local filename."""
    key = "|".join([
        (provider or "").strip().lower(),
        (name or "").strip().lower(),
        (market or "").strip().lower(),
        (asset_class or "").strip().lower(),
        (frequency or "").strip().lower(),
        (source_ref or "").strip().lower(),
    ])
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    slug = "".join(c if c.isalnum() else "_" for c in (name or "dataset").lower())[:32]
    return f"ds_{slug}_{digest}"


class DatasetRegistry:
    def __init__(self, store: MarketDataStore):
        self.store = store

    def register(
        self,
        *,
        name: str,
        description: str = "",
        provider: str = "local",
        source_type: str = SourceType.REPOSITORY_FIXTURE.value,
        source_ref: str = "",
        market: str = "",
        exchange: str = "",
        asset_class: str = "equity",
        instrument_type: str = "stock",
        symbol_namespace: str = "TICKER",
        coverage_start: str | None = None,
        coverage_end: str | None = None,
        frequency: str = "1d",
        timezone: str = "UTC",
        currency: str = "USD",
        price_fields: list[str] | None = None,
        volume_fields: list[str] | None = None,
        corporate_action_coverage: bool = False,
        benchmark_coverage: bool = False,
        survivorship: dict | None = None,
        revision_policy: str = "immutable_version",
        licence_type: str = "",
        redistribution_status: str = "unknown",
        commercial_use_status: str = "unknown",
        retention_restrictions: str = "",
        citation_requirements: str = "",
        checksum: str = "",
        file_path: str = "",
        file_size: int = 0,
        row_count: int = 0,
        is_synthetic: bool = False,
        limitations: list[str] | None = None,
        dataset_version: str = "v1",
        parent_dataset_id: str | None = None,
        meta: dict | None = None,
        force_id: str | None = None,
        instrument_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            identity = resolve_market_identity(
                instrument_id=instrument_id,
                venue=exchange,
                market=market,
                asset_class=asset_class,
            )
        except IdentityValidationError as exc:
            raise MarketDataError(exc.code, str(exc)) from exc
        market = "" if identity.market == "UNKNOWN" else identity.market
        exchange = identity.venue
        # Keep the legacy storage spelling (lowercase) while validating against
        # the canonical identity vocabulary above.
        asset_class = str(asset_class or "").strip().lower() or "unknown"
        ds_id = force_id or deterministic_dataset_id(
            provider, name, market, asset_class, frequency, source_ref,
        )
        existing = self.store.get_dataset(ds_id, dataset_version)
        if existing and existing.get("checksum") and checksum and existing["checksum"] != checksum:
            raise MarketDataError(
                VERSION_COLLISION,
                f"Version {dataset_version} already registered with different checksum",
                {"dataset_id": ds_id, "dataset_version": dataset_version},
            )
        if existing and existing.get("checksum") == checksum and checksum:
            # Idempotent re-register of identical content
            out = self._public(existing)
            out["ok"] = True
            out["idempotent"] = True
            return out

        # Duplicate detection by checksum across IDs
        if checksum:
            dups = self.store.query(
                "SELECT dataset_id, dataset_version FROM md_datasets WHERE checksum=? AND NOT (dataset_id=? AND dataset_version=?)",
                (checksum, ds_id, dataset_version),
            )
        else:
            dups = []

        state = DatasetState.REGISTERED.value
        if not licence_type or licence_type.lower() in ("unknown", "", "unclear"):
            state = DatasetState.LICENCE_REVIEW_REQUIRED.value
        if is_synthetic:
            limitations = list(limitations or []) + ["SYNTHETIC_TEST_DATA"]

        rec = {
            "dataset_id": ds_id,
            "dataset_version": dataset_version,
            "name": name,
            "description": description,
            "provider": provider,
            "source_type": source_type,
            "source_ref": source_ref,
            "retrieval_ts": time.time(),
            "ingestion_ts": None,
            "market": market,
            "exchange": exchange,
            "asset_class": asset_class,
            "instrument_type": instrument_type,
            "symbol_namespace": symbol_namespace,
            "coverage_start": coverage_start,
            "coverage_end": coverage_end,
            "frequency": frequency,
            "timezone": timezone,
            "currency": currency,
            "price_fields_json": price_fields or ["open", "high", "low", "close"],
            "volume_fields_json": volume_fields or ["volume"],
            "corporate_action_coverage": 1 if corporate_action_coverage else 0,
            "benchmark_coverage": 1 if benchmark_coverage else 0,
            "survivorship_json": survivorship or {"includes_delisted": False, "status": "unreported"},
            "revision_policy": revision_policy,
            "licence_type": licence_type,
            "redistribution_status": redistribution_status,
            "commercial_use_status": commercial_use_status,
            "retention_restrictions": retention_restrictions,
            "citation_requirements": citation_requirements,
            "checksum": checksum,
            "row_count": row_count,
            "file_size": file_size,
            "schema_version": OHLCV_SCHEMA_VERSION,
            "quality_status": "",
            "approval_status": "pending",
            "state": state,
            "limitations_json": limitations or [],
            "evidence_refs_json": [],
            "parent_dataset_id": parent_dataset_id,
            "superseded_by": None,
            "file_path": file_path,
            "is_synthetic": 1 if is_synthetic else 0,
            "meta_json": meta or {},
        }
        self.store.upsert_dataset(rec)
        self.store.audit("dataset.register", subject=ds_id, detail={
            "dataset_id": ds_id, "version": dataset_version, "state": state,
            "duplicates": dups, "checksum": checksum,
        })
        out = self._public(self.store.get_dataset(ds_id, dataset_version))
        out["ok"] = True
        out["duplicate_checksum_hits"] = dups
        out.update(AUTHORITY_VALUES)
        return out

    def register_from_file(
        self,
        path: str | Path,
        *,
        name: str | None = None,
        provider: str = "local",
        source_type: str = SourceType.LOCAL_FILE.value,
        is_synthetic: bool = False,
        licence_type: str = "CC0-1.0",
        **kwargs: Any,
    ) -> dict[str, Any]:
        p = Path(path).resolve()
        # Path traversal protection: must exist and be a file
        if not p.is_file():
            raise MarketDataError("UNSAFE_FILE", f"Not a readable file: {path}")
        # Reject suspicious extensions
        if p.suffix.lower() in (".exe", ".dll", ".so", ".dylib", ".py", ".sh", ".bat", ".pkl", ".pickle"):
            raise MarketDataError("UNSAFE_FILE", f"Executable/unsafe extension rejected: {p.suffix}")
        cs = file_checksum(p)
        return self.register(
            name=name or p.stem,
            source_ref=str(p),
            source_type=source_type,
            provider=provider,
            checksum=cs,
            file_path=str(p),
            file_size=p.stat().st_size,
            is_synthetic=is_synthetic,
            licence_type=licence_type,
            **kwargs,
        )

    def transition(self, dataset_id: str, version: str, new_state: str, reason: str = "") -> dict[str, Any]:
        ds = self.store.get_dataset(dataset_id, version)
        if not ds:
            raise MarketDataError(UNREGISTERED_DATASET, f"Unknown dataset {dataset_id}@{version}")
        allowed = {s.value for s in DatasetState}
        if new_state not in allowed:
            raise MarketDataError("INVALID_STATE", f"Invalid state {new_state}")
        ds["state"] = new_state
        if new_state == DatasetState.RESEARCH_APPROVED.value:
            ds["approval_status"] = "approved"
        if new_state == DatasetState.REVOKED.value:
            ds["approval_status"] = "revoked"
        if new_state == DatasetState.QUARANTINED.value:
            ds["approval_status"] = "quarantined"
        lim = json.loads(ds.get("limitations_json") or "[]")
        if reason:
            lim.append(reason)
        ds["limitations_json"] = lim
        self.store.upsert_dataset(ds)
        self.store.audit("dataset.transition", subject=dataset_id, detail={
            "version": version, "new_state": new_state, "reason": reason,
        })
        out = self._public(self.store.get_dataset(dataset_id, version))
        out["ok"] = True
        out.update(AUTHORITY_VALUES)
        return out

    def supersede(self, dataset_id: str, old_version: str, new_version: str, **kwargs: Any) -> dict[str, Any]:
        old = self.store.get_dataset(dataset_id, old_version)
        if not old:
            raise MarketDataError(UNREGISTERED_DATASET, f"Unknown {dataset_id}@{old_version}")
        # Register new version
        reg = self.register(
            name=old["name"],
            description=old.get("description") or "",
            provider=old.get("provider") or "local",
            source_type=old.get("source_type") or SourceType.DERIVED.value,
            source_ref=old.get("source_ref") or "",
            market=old.get("market") or "",
            exchange=old.get("exchange") or "",
            asset_class=old.get("asset_class") or "",
            frequency=old.get("frequency") or "1d",
            timezone=old.get("timezone") or "UTC",
            currency=old.get("currency") or "USD",
            licence_type=old.get("licence_type") or "",
            checksum=kwargs.get("checksum", ""),
            file_path=kwargs.get("file_path", old.get("file_path") or ""),
            is_synthetic=bool(old.get("is_synthetic")),
            dataset_version=new_version,
            parent_dataset_id=dataset_id,
            force_id=dataset_id,
            **{k: v for k, v in kwargs.items() if k not in ("checksum", "file_path")},
        )
        old["state"] = DatasetState.SUPERSEDED.value
        old["superseded_by"] = new_version
        self.store.upsert_dataset(old)
        self.store.audit("dataset.supersede", subject=dataset_id, detail={
            "old_version": old_version, "new_version": new_version,
        })
        return reg

    def revoke(self, dataset_id: str, version: str, reason: str = "revoked") -> dict[str, Any]:
        return self.transition(dataset_id, version, DatasetState.REVOKED.value, reason)

    def quarantine(self, dataset_id: str, version: str, reason: str = "quarantined") -> dict[str, Any]:
        return self.transition(dataset_id, version, DatasetState.QUARANTINED.value, reason)

    def require_research_usable(self, dataset_id: str, version: str | None = None) -> dict[str, Any]:
        ds = self.store.get_dataset(dataset_id, version)
        if not ds:
            raise MarketDataError(UNREGISTERED_DATASET, f"Unregistered dataset {dataset_id}")
        state = ds["state"]
        if state == DatasetState.REVOKED.value:
            raise MarketDataError(DATASET_REVOKED, f"Dataset revoked: {dataset_id}")
        if state == DatasetState.QUARANTINED.value:
            raise MarketDataError(DATASET_QUARANTINED, f"Dataset quarantined: {dataset_id}")
        if state not in (
            DatasetState.RESEARCH_APPROVED.value,
            DatasetState.RESEARCH_RESTRICTED.value,
            DatasetState.INGESTED_UNVERIFIED.value,  # allowed for pre-approval quality runs
            DatasetState.QUALITY_REVIEW_REQUIRED.value,
            DatasetState.REGISTERED.value,
            DatasetState.INGESTION_PENDING.value,
        ):
            if state in (DatasetState.LICENCE_REVIEW_REQUIRED.value,):
                raise MarketDataError("LICENCE_GATE_FAILED", "Licence review required before research use")
        if not ds.get("checksum"):
            raise MarketDataError(CHECKSUM_MISSING, "Dataset missing checksum")
        return ds

    def verify_checksum(self, dataset_id: str, version: str) -> dict[str, Any]:
        ds = self.store.get_dataset(dataset_id, version)
        if not ds:
            raise MarketDataError(UNREGISTERED_DATASET, f"Unknown {dataset_id}")
        expected = ds.get("checksum") or ""
        path = ds.get("file_path") or ""
        if not expected:
            return {"ok": False, "code": CHECKSUM_MISSING, "dataset_id": dataset_id, **AUTHORITY_VALUES}
        if path and Path(path).is_file():
            actual = file_checksum(Path(path))
            match = actual == expected
            if not match:
                self.transition(dataset_id, version, DatasetState.QUARANTINED.value, "checksum_mismatch")
            return {
                "ok": match,
                "code": None if match else CHECKSUM_MISMATCH,
                "expected": expected,
                "actual": actual,
                "dataset_id": dataset_id,
                "dataset_version": version,
                **AUTHORITY_VALUES,
            }
        return {
            "ok": True,
            "code": None,
            "expected": expected,
            "actual": expected,
            "file_verified": False,
            "note": "No local file path; registry checksum retained",
            "dataset_id": dataset_id,
            **AUTHORITY_VALUES,
        }

    def list_datasets(self, state: str | None = None) -> dict[str, Any]:
        rows = self.store.list_datasets(state)
        return {
            "ok": True,
            "count": len(rows),
            "datasets": [self._public(r) for r in rows],
            **AUTHORITY_VALUES,
        }

    def get(self, dataset_id: str, version: str | None = None) -> dict[str, Any]:
        ds = self.store.get_dataset(dataset_id, version)
        if not ds:
            return {"ok": False, "code": UNREGISTERED_DATASET, "dataset_id": dataset_id, **AUTHORITY_VALUES}
        out = self._public(ds)
        out["ok"] = True
        out["versions"] = [
            {"dataset_version": v["dataset_version"], "state": v["state"], "checksum": v.get("checksum")}
            for v in self.store.list_versions(dataset_id)
        ]
        out.update(AUTHORITY_VALUES)
        return out

    def catalogue_export(self) -> dict[str, Any]:
        rows = self.store.list_datasets()
        payload = {
            "schema_version": "M256_DATASET_REGISTRY",
            "certified_research_requires_registered_dataset": True,
            "count": len(rows),
            "datasets": [self._public(r) for r in rows],
            "states": sorted({r["state"] for r in rows}),
            **AUTHORITY_VALUES,
        }
        payload["evidence_hash"] = evidence_hash(payload)
        return payload

    @staticmethod
    def _public(ds: dict[str, Any] | None) -> dict[str, Any]:
        if not ds:
            return {}
        def _j(key: str, default: Any):
            raw = ds.get(key)
            if raw is None or raw == "":
                return default
            if isinstance(raw, (list, dict)):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return default
        return {
            "dataset_id": ds["dataset_id"],
            "dataset_version": ds["dataset_version"],
            "name": ds["name"],
            "description": ds.get("description") or "",
            "provider": ds.get("provider") or "",
            "source_type": ds.get("source_type") or "",
            "source_ref": ds.get("source_ref") or "",
            "retrieval_timestamp": ds.get("retrieval_ts"),
            "ingestion_timestamp": ds.get("ingestion_ts"),
            "market": ds.get("market") or "",
            "exchange": ds.get("exchange") or "",
            "asset_class": ds.get("asset_class") or "",
            "instrument_type": ds.get("instrument_type") or "",
            "symbol_namespace": ds.get("symbol_namespace") or "",
            "coverage_start": ds.get("coverage_start"),
            "coverage_end": ds.get("coverage_end"),
            "frequency": ds.get("frequency") or "",
            "timezone": ds.get("timezone") or "UTC",
            "currency": ds.get("currency") or "USD",
            "price_fields": _j("price_fields_json", []),
            "volume_fields": _j("volume_fields_json", []),
            "corporate_action_coverage": bool(ds.get("corporate_action_coverage")),
            "benchmark_coverage": bool(ds.get("benchmark_coverage")),
            "survivorship": _j("survivorship_json", {}),
            "revision_policy": ds.get("revision_policy") or "",
            "licence_type": ds.get("licence_type") or "",
            "redistribution_status": ds.get("redistribution_status") or "",
            "commercial_use_status": ds.get("commercial_use_status") or "",
            "retention_restrictions": ds.get("retention_restrictions") or "",
            "citation_requirements": ds.get("citation_requirements") or "",
            "checksum": ds.get("checksum") or "",
            "row_count": ds.get("row_count") or 0,
            "file_size": ds.get("file_size") or 0,
            "schema_version": ds.get("schema_version") or "",
            "quality_status": ds.get("quality_status") or "",
            "approval_status": ds.get("approval_status") or "",
            "state": ds.get("state") or "",
            "limitations": _j("limitations_json", []),
            "evidence_references": _j("evidence_refs_json", []),
            "parent_dataset_id": ds.get("parent_dataset_id"),
            "superseded_by": ds.get("superseded_by"),
            "file_path": ds.get("file_path") or "",
            "is_synthetic": bool(ds.get("is_synthetic")),
            "meta": _j("meta_json", {}),
        }
