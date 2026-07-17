"""M29 — Registry persistence (manifest snapshots; adapters re-bound at boot)."""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from saathi.connectors.gov.models import ConnectorManifest


@dataclass
class RegistryPersistence:
    path: Path

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self._lock = threading.RLock()

    def save(self, manifests: list[dict[str, Any]], *, meta: Optional[dict[str, Any]] = None) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema": "m29.connector_registry.v1",
                "manifests": manifests,
                "meta": meta or {},
                "privacy_safe": True,
            }
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
            tmp.replace(self.path)

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.is_file():
                return {"schema": "m29.connector_registry.v1", "manifests": [], "meta": {}}
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("registry_snapshot_invalid")
            return data


def save_registry_snapshot(
    registry: Any,
    path: Path | str,
    *,
    meta: Optional[dict[str, Any]] = None,
) -> Path:
    path = Path(path)
    manifests = []
    for rec in registry.all_records():
        d = rec.manifest.to_dict()
        d["_lifecycle"] = rec.lifecycle.value if hasattr(rec.lifecycle, "value") else str(rec.lifecycle)
        d["_validated"] = bool(rec.validated)
        manifests.append(d)
    RegistryPersistence(path).save(manifests, meta=meta)
    return path


def load_registry_snapshot(
    path: Path | str,
    registry: Any,
    *,
    adapters: Optional[dict[str, Any]] = None,
    validate: bool = True,
) -> list[str]:
    """Load manifests into registry. Adapters optional (identity only without them)."""
    data = RegistryPersistence(Path(path)).load()
    ids: list[str] = []
    adapters = adapters or {}
    for raw in data.get("manifests") or []:
        m = ConnectorManifest.from_dict(raw)
        registry.register(m, adapter=adapters.get(m.connector_id), allow_replace=True)
        if validate:
            registry.validate(m.connector_id)
        ids.append(m.connector_id)
    return ids
