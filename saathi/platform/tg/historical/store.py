"""Immutable historical dataset store (process-local + optional path root).

Accepted versions cannot be mutated. Duplicate content fingerprints are detected.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from saathi.platform.tg.historical.models import (
    DataImportRun,
    DatasetQuarantineRecord,
    DatasetVersion,
    HistoricalDataset,
    ImportStatus,
    fingerprint_payload,
)


class HistoricalStoreError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class HistoricalDatasetStore:
    def __init__(self, root: str | Path | None = None, *, min_free_mb: int = 256):
        self.root = Path(root) if root else None
        self.min_free_mb = min_free_mb
        self._datasets: dict[str, HistoricalDataset] = {}
        self._versions: dict[str, DatasetVersion] = {}  # key = dataset_id:version
        self._by_fingerprint: dict[str, str] = {}  # content_fp -> version key
        self._imports: dict[str, DataImportRun] = {}
        self._quarantine: list[DatasetQuarantineRecord] = []

    def _vkey(self, dataset_id: str, version: str) -> str:
        return f"{dataset_id}:{version}"

    def disk_preflight(self, path: str | Path | None = None) -> dict[str, Any]:
        target = Path(path or self.root or ".")
        try:
            usage = shutil.disk_usage(str(target if target.exists() else target.parent if target.parent.exists() else "."))
            free_mb = usage.free // (1024 * 1024)
            ok = free_mb >= self.min_free_mb
            return {
                "free_mb": free_mb,
                "min_free_mb": self.min_free_mb,
                "ok": ok,
                "path": str(target),
            }
        except OSError as e:
            return {"free_mb": 0, "min_free_mb": self.min_free_mb, "ok": False, "error": str(e)}

    def ensure_dataset(
        self,
        *,
        name: str,
        market: str = "",
        org_id: str = "local",
        workspace_id: str = "local",
        dataset_id: str | None = None,
    ) -> HistoricalDataset:
        if dataset_id and dataset_id in self._datasets:
            return self._datasets[dataset_id]
        # match by name+scope
        for d in self._datasets.values():
            if d.name == name and d.org_id == org_id and d.workspace_id == workspace_id:
                return d
        ds = HistoricalDataset(
            id=dataset_id or "",
            name=name,
            market=market,
            org_id=org_id,
            workspace_id=workspace_id,
        )
        if not ds.id:
            from saathi.platform.tg.historical.models import _id
            ds.id = _id("hds")
        self._datasets[ds.id] = ds
        return ds

    def put_version(self, version: DatasetVersion, *, allow_duplicate_fp: bool = False) -> DatasetVersion:
        key = self._vkey(version.dataset_id, version.version)
        existing = self._versions.get(key)
        if existing and existing.immutable:
            raise HistoricalStoreError("IMMUTABLE", f"version {key} is immutable")
        fp = version.fingerprint.content_fingerprint
        if fp and fp in self._by_fingerprint and not allow_duplicate_fp:
            prior = self._by_fingerprint[fp]
            if prior != key:
                raise HistoricalStoreError(
                    "DUPLICATE_DATASET",
                    f"content fingerprint already registered as {prior}",
                )
        self._versions[key] = version
        if fp:
            self._by_fingerprint[fp] = key
        ds = self._datasets.get(version.dataset_id)
        if ds is not None:
            if version.version not in ds.versions:
                ds.versions.append(version.version)
            ds.latest_version = version.version
        return version

    def get_version(self, dataset_id: str, version: str) -> DatasetVersion | None:
        return self._versions.get(self._vkey(dataset_id, version))

    def get_latest(self, dataset_id: str) -> DatasetVersion | None:
        ds = self._datasets.get(dataset_id)
        if not ds or not ds.latest_version:
            return None
        return self.get_version(dataset_id, ds.latest_version)

    def list_datasets(self, *, org_id: str = "", workspace_id: str = "") -> list[HistoricalDataset]:
        out = []
        for d in self._datasets.values():
            if org_id and d.org_id != org_id:
                continue
            if workspace_id and d.workspace_id != workspace_id:
                continue
            out.append(d)
        return out

    def list_versions(self, dataset_id: str) -> list[DatasetVersion]:
        return [v for k, v in self._versions.items() if v.dataset_id == dataset_id]

    def record_import(self, run: DataImportRun) -> DataImportRun:
        self._imports[run.id] = run
        return run

    def get_import(self, run_id: str) -> DataImportRun | None:
        return self._imports.get(run_id)

    def quarantine(
        self,
        version: DatasetVersion,
        *,
        reason: str,
        findings: list[dict[str, Any]] | None = None,
    ) -> DatasetQuarantineRecord:
        version.quarantine(reason)
        rec = DatasetQuarantineRecord(
            dataset_id=version.dataset_id,
            version=version.version,
            reason=reason,
            findings=list(findings or version.quality.findings),
            org_id=version.org_id,
            workspace_id=version.workspace_id,
        )
        self._quarantine.append(rec)
        # re-put
        self._versions[self._vkey(version.dataset_id, version.version)] = version
        return rec

    def list_quarantine(self, *, org_id: str = "", workspace_id: str = "") -> list[DatasetQuarantineRecord]:
        out = []
        for q in self._quarantine:
            if org_id and q.org_id != org_id:
                continue
            if workspace_id and q.workspace_id != workspace_id:
                continue
            out.append(q)
        return out

    def to_public_summary(self) -> dict[str, Any]:
        return {
            "datasets": len(self._datasets),
            "versions": len(self._versions),
            "quarantine": len(self._quarantine),
            "imports": len(self._imports),
            "paper_only": True,
            "min_free_mb": self.min_free_mb,
        }
