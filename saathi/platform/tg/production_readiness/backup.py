"""M332 offline backup, integrity verification and recovery simulation.

Snapshots are content-addressed manifests held locally. Recovery is *simulated*: the
engine proves a snapshot would restore byte-identically, but never mutates live state
and never writes to a cloud target.
"""
from __future__ import annotations

from threading import RLock
from typing import Any, Mapping

from saathi.platform.tg.production_readiness.errors import (
    OperationsError,
    OperationsErrorCode,
)
from saathi.platform.tg.production_readiness.models import (
    BOUNDARY_VALUES,
    FORBIDDEN_OBSERVABILITY_FIELDS,
    SCHEMA_VERSION,
    BackupKind,
    BackupSnapshot,
    DeterministicClock,
    RecoveryOutcome,
    canonical_json,
    digest,
    redact,
    short_digest,
)

FORBIDDEN_BACKUP_TARGETS = frozenset({
    "s3",
    "gcs",
    "azure_blob",
    "backblaze",
    "dropbox",
    "google_drive",
    "icloud",
    "onedrive",
    "rsync_remote",
    "ftp",
    "sftp",
})


class BackupEngine:
    def __init__(self, clock: DeterministicClock | None = None):
        self.clock = clock or DeterministicClock()
        self._lock = RLock()
        self._snapshots: dict[str, BackupSnapshot] = {}
        self._payloads: dict[str, str] = {}
        self._order: list[str] = []
        self._recoveries: list[dict[str, Any]] = []
        self._sequence = 0

    # ── capture ─────────────────────────────────────────────────────────────
    def capture(
        self,
        kind: BackupKind | str,
        label: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        kind = kind if isinstance(kind, BackupKind) else BackupKind(kind)
        if not label:
            raise OperationsError(
                OperationsErrorCode.INVALID_REQUEST,
                "Snapshot requires a label",
            )
        cleaned = redact(payload)
        leaked = _forbidden_fields(payload)
        if leaked:
            raise OperationsError(
                OperationsErrorCode.FORBIDDEN_FIELD,
                "Snapshot payload contains a forbidden field",
                details={"fields": sorted(leaked)},
            )
        serialized = canonical_json(cleaned)
        with self._lock:
            self._sequence += 1
            snapshot = BackupSnapshot(
                snapshot_id="snap_" + short_digest({
                    "kind": kind.value,
                    "label": label,
                    "sequence": self._sequence,
                }, 14),
                kind=kind,
                label=label,
                payload_digest=digest(cleaned),
                item_count=_count_items(cleaned),
                size_bytes=len(serialized.encode("utf-8")),
                created_at=self.clock.advance(),
                manifest={
                    "keys": sorted(cleaned)[:40],
                    "schema_version": SCHEMA_VERSION,
                    "target": "local_offline_store",
                },
            )
            self._snapshots[snapshot.snapshot_id] = snapshot
            self._payloads[snapshot.snapshot_id] = serialized
            self._order.append(snapshot.snapshot_id)
        return {"ok": True, "snapshot": snapshot.to_dict(), **BOUNDARY_VALUES}

    def get(self, snapshot_id: str) -> BackupSnapshot:
        with self._lock:
            snapshot = self._snapshots.get(snapshot_id)
        if snapshot is None:
            raise OperationsError(
                OperationsErrorCode.SNAPSHOT_UNKNOWN,
                "Unknown snapshot",
                details={"snapshot_id": snapshot_id},
            )
        return snapshot

    def list_snapshots(self, *, kind: BackupKind | str | None = None) -> dict[str, Any]:
        with self._lock:
            snapshots = [self._snapshots[sid] for sid in self._order]
        if kind is not None:
            wanted = kind if isinstance(kind, BackupKind) else BackupKind(kind)
            snapshots = [item for item in snapshots if item.kind is wanted]
        by_kind = {item.value: 0 for item in BackupKind}
        for snapshot in snapshots:
            by_kind[snapshot.kind.value] += 1
        missing = [key for key, count in by_kind.items() if count == 0]
        return {
            "ok": True,
            "count": len(snapshots),
            "snapshots": [snapshot.to_dict() for snapshot in snapshots],
            "by_kind": by_kind,
            "kinds": [item.value for item in BackupKind],
            "missing_kinds": missing,
            "coverage_complete": not missing,
            "storage_target": "local_offline_store",
            "cloud_targets": [],
            "forbidden_targets": sorted(FORBIDDEN_BACKUP_TARGETS),
            **BOUNDARY_VALUES,
        }

    # ── integrity ───────────────────────────────────────────────────────────
    def verify(self, snapshot_id: str) -> dict[str, Any]:
        snapshot = self.get(snapshot_id)
        with self._lock:
            serialized = self._payloads[snapshot_id]
        recomputed = digest(_loads(serialized))
        intact = recomputed == snapshot.payload_digest
        size_match = len(serialized.encode("utf-8")) == snapshot.size_bytes
        return {
            "ok": intact and size_match,
            "snapshot_id": snapshot_id,
            "kind": snapshot.kind.value,
            "expected_digest": snapshot.payload_digest,
            "recomputed_digest": recomputed,
            "digest_match": intact,
            "size_match": size_match,
            "verified_at": self.clock.advance(),
            "mutated_live_state": False,
            **BOUNDARY_VALUES,
        }

    def verify_all(self) -> dict[str, Any]:
        with self._lock:
            snapshot_ids = list(self._order)
        results = [self.verify(sid) for sid in snapshot_ids]
        failures = [item["snapshot_id"] for item in results if not item["ok"]]
        return {
            "ok": not failures,
            "verified_count": len(results),
            "failures": failures,
            "results": results,
            **BOUNDARY_VALUES,
        }

    def corrupt_for_drill(self, snapshot_id: str) -> dict[str, Any]:
        """Drill hook: damage a stored payload so the integrity path is provable."""
        self.get(snapshot_id)
        with self._lock:
            self._payloads[snapshot_id] = canonical_json({"corrupted": True})
        return {"ok": True, "snapshot_id": snapshot_id, "corrupted": True}

    # ── recovery simulation ─────────────────────────────────────────────────
    def simulate_recovery(self, snapshot_id: str) -> dict[str, Any]:
        snapshot = self.get(snapshot_id)
        verification = self.verify(snapshot_id)
        if not verification["ok"]:
            outcome = RecoveryOutcome.INTEGRITY_MISMATCH
        else:
            with self._lock:
                restored = _loads(self._payloads[snapshot_id])
            outcome = (
                RecoveryOutcome.SIMULATED_SUCCESS
                if digest(restored) == snapshot.payload_digest
                else RecoveryOutcome.SIMULATED_FAILURE
            )
        record = {
            "recovery_id": "rec_" + short_digest({
                "snapshot_id": snapshot_id,
                "outcome": outcome.value,
                "sequence": len(self._recoveries),
            }, 14),
            "snapshot_id": snapshot_id,
            "kind": snapshot.kind.value,
            "outcome": outcome.value,
            "ok": outcome is RecoveryOutcome.SIMULATED_SUCCESS,
            "integrity": verification,
            "simulated_at": self.clock.advance(),
            "live_state_mutated": False,
            "applied_to_production": False,
            "restored_credentials": 0,
            "restored_accounts": 0,
            "restored_orders": 0,
        }
        with self._lock:
            self._recoveries.append(record)
        return {"ok": record["ok"], "recovery": record, **BOUNDARY_VALUES}

    def recovery_history(self) -> dict[str, Any]:
        with self._lock:
            rows = list(self._recoveries)
        return {
            "ok": True,
            "count": len(rows),
            "recoveries": rows,
            "successful": sum(1 for row in rows if row["ok"]),
            "failed": sum(1 for row in rows if not row["ok"]),
            **BOUNDARY_VALUES,
        }

    def posture(self) -> dict[str, Any]:
        snapshots = self.list_snapshots()
        history = self.recovery_history()
        return {
            "ok": True,
            "milestone": "M332",
            "name": "Offline Backup, Integrity and Recovery Simulation",
            "schema_version": SCHEMA_VERSION,
            "snapshot_count": snapshots["count"],
            "by_kind": snapshots["by_kind"],
            "coverage_complete": snapshots["coverage_complete"],
            "recovery_count": history["count"],
            "storage_target": "local_offline_store",
            "cloud_backup_enabled": False,
            "forbidden_targets": sorted(FORBIDDEN_BACKUP_TARGETS),
            "recovery_is_simulation_only": True,
            "clock": self.clock.snapshot(),
            **BOUNDARY_VALUES,
        }

    def isolation_scan(self) -> dict[str, Any]:
        with self._lock:
            snapshots = list(self._snapshots.values())
            payloads = dict(self._payloads)
        findings: list[dict[str, Any]] = []
        for snapshot in snapshots:
            if snapshot.manifest.get("target") != "local_offline_store":
                findings.append({"snapshot_id": snapshot.snapshot_id, "issue": "non_local_target"})
        for snapshot_id, serialized in payloads.items():
            lowered = serialized.lower()
            for field in FORBIDDEN_OBSERVABILITY_FIELDS:
                marker = f'"{field}":'
                if marker in lowered and '"[redacted]"' not in lowered.split(marker, 1)[1][:16]:
                    findings.append({"snapshot_id": snapshot_id, "field": field})
        return {
            "ok": not findings,
            "findings": findings,
            "snapshots_scanned": len(snapshots),
            "cloud_targets_configured": 0,
            "remote_transports_present": False,
        }


def _forbidden_fields(payload: Mapping[str, Any]) -> set[str]:
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if str(key).lower() in FORBIDDEN_OBSERVABILITY_FIELDS:
                    found.add(str(key).lower())
                walk(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                walk(child)

    walk(payload)
    return found


def _count_items(payload: Any) -> int:
    if isinstance(payload, Mapping):
        return sum(_count_items(value) for value in payload.values()) or len(payload)
    if isinstance(payload, (list, tuple)):
        return len(payload)
    return 1


def _loads(serialized: str) -> Any:
    import json

    return json.loads(serialized)
