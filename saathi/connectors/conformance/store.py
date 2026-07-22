"""M30 — Certification store with lease, revoke, and atomic persistence."""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from saathi.connectors.conformance.fingerprint import compute_certification_fingerprint
from saathi.connectors.conformance.models import (
    CertificationRecord,
    CertificationState,
    EXECUTABLE_CERT_STATES,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STORE_PATH = ROOT / "docs" / "evidence" / "m30" / "certification_registry.json"
LEASE_SECONDS = 120.0


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


class CertificationStore:
    """Process + optional file-backed certification records."""

    def __init__(
        self,
        path: Optional[Path] = None,
        *,
        auto_fixture: bool = False,
        clock: Optional[Any] = None,
        persist: bool = True,
    ):
        self.path = Path(path) if path else DEFAULT_STORE_PATH
        self.auto_fixture = auto_fixture  # TEST FIXTURE ONLY — never production default
        self.clock = clock or time.time
        self.persist = persist
        self._lock = threading.RLock()
        self._records: dict[str, CertificationRecord] = {}
        if persist and self.path.is_file():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for cid, raw in (data.get("connectors") or {}).items():
                self._records[cid] = CertificationRecord.from_dict(raw)
        except Exception:
            self._records = {}

    def _save(self) -> None:
        if not self.persist:
            return
        payload = {
            "schema": "m30.certification_registry.v1",
            "connectors": {k: v.to_dict() for k, v in sorted(self._records.items())},
            "privacy_safe": True,
            "trading_guardian": "UNCHANGED / UNENGAGED",
        }
        _atomic_write(self.path, payload)

    def get(self, connector_id: str) -> CertificationRecord:
        with self._lock:
            rec = self._records.get(connector_id)
            if rec is None:
                return CertificationRecord(connector_id=connector_id)
            return rec

    def list_records(self) -> list[CertificationRecord]:
        with self._lock:
            return [self._records[k] for k in sorted(self._records)]

    def begin_assessment(self, connector_id: str, *, lease_seconds: float = LEASE_SECONDS) -> str:
        """Acquire ASSESSING lease. Raises RuntimeError if lease held."""
        with self._lock:
            rec = self._records.get(connector_id) or CertificationRecord(connector_id=connector_id)
            now = float(self.clock())
            if (
                rec.state == CertificationState.ASSESSING.value
                and rec.lease_id
                and rec.lease_expires_at > now
            ):
                raise RuntimeError(f"assessment_lease_held:{connector_id}:{rec.lease_id}")
            # Recover interrupted assessment
            lease_id = uuid.uuid4().hex[:12]
            prev = rec.state
            rec.state = CertificationState.ASSESSING.value
            rec.lease_id = lease_id
            rec.lease_expires_at = now + lease_seconds
            rec.history.append({
                "event": "begin_assessment",
                "from": prev,
                "lease_id": lease_id,
                "ts": now,
            })
            self._records[connector_id] = rec
            self._save()
            return lease_id

    def complete_assessment(
        self,
        connector_id: str,
        *,
        lease_id: str,
        state: str,
        fingerprint: str,
        limitations: Optional[list[str]] = None,
        failure_codes: Optional[list[str]] = None,
        evidence_dir: str = "",
        assessed_at: str = "",
        fixture: bool = False,
    ) -> CertificationRecord:
        with self._lock:
            rec = self._records.get(connector_id) or CertificationRecord(connector_id=connector_id)
            if rec.lease_id and rec.lease_id != lease_id:
                raise RuntimeError(f"lease_mismatch:{connector_id}")
            rec.state = state
            rec.fingerprint = fingerprint
            rec.limitations = list(limitations or [])
            rec.failure_codes = list(failure_codes or [])
            rec.evidence_dir = evidence_dir
            rec.assessed_at = assessed_at
            rec.lease_id = ""
            rec.lease_expires_at = 0.0
            rec.fixture = fixture
            if state != CertificationState.REVOKED.value:
                rec.revoked_at = ""
                rec.revoke_reason = ""
            rec.history.append({
                "event": "complete_assessment",
                "state": state,
                "fingerprint": fingerprint[:16],
                "ts": float(self.clock()),
            })
            # Cap history
            rec.history = rec.history[-50:]
            self._records[connector_id] = rec
            self._save()
            return rec

    def mark_stale(self, connector_id: str, *, reason: str = "fingerprint_drift") -> CertificationRecord:
        with self._lock:
            rec = self._records.get(connector_id) or CertificationRecord(connector_id=connector_id)
            if rec.state in (
                CertificationState.CERTIFIED.value,
                CertificationState.CERTIFIED_WITH_LIMITATIONS.value,
            ):
                rec.history.append({
                    "event": "stale",
                    "from": rec.state,
                    "reason": reason,
                    "prior_fingerprint": rec.fingerprint[:16],
                    "ts": float(self.clock()),
                })
                rec.state = CertificationState.STALE.value
                self._records[connector_id] = rec
                self._save()
            return rec

    def revoke(
        self,
        connector_id: str,
        *,
        reason: str,
        preserve_evidence: bool = True,
    ) -> CertificationRecord:
        """Revoke certification. Prior evidence paths are retained on the record."""
        with self._lock:
            rec = self._records.get(connector_id) or CertificationRecord(connector_id=connector_id)
            prior = rec.to_dict()
            rec.history.append({
                "event": "revoke",
                "from": rec.state,
                "reason": reason[:200],
                "prior_fingerprint": rec.fingerprint[:16],
                "prior_evidence_dir": rec.evidence_dir if preserve_evidence else "",
                "ts": float(self.clock()),
            })
            rec.state = CertificationState.REVOKED.value
            rec.revoked_at = str(int(self.clock()))
            rec.revoke_reason = reason[:200]
            rec.lease_id = ""
            rec.lease_expires_at = 0.0
            # Keep fingerprint/evidence_dir for audit trail
            self._records[connector_id] = rec
            self._save()
            # Append revocation side-car if evidence dir exists
            if preserve_evidence and rec.evidence_dir:
                try:
                    p = Path(rec.evidence_dir) / "revocation.json"
                    _atomic_write(p, {
                        "schema": "m30.revocation.v1",
                        "connector_id": connector_id,
                        "reason": reason[:200],
                        "prior": {
                            "state": prior.get("state"),
                            "fingerprint": prior.get("fingerprint"),
                        },
                        "privacy_safe": True,
                    })
                except Exception:
                    pass
            return rec

    def install_fixture_certification(
        self,
        connector_id: str,
        *,
        registry: Any = None,
        state: str = CertificationState.CERTIFIED.value,
    ) -> CertificationRecord:
        """Isolated test helper — marks connector certified under fixture fingerprint.

        Never used by production assess paths except when auto_fixture=True on a
        test-scoped store.
        """
        manifest = None
        if registry is not None:
            try:
                rec = registry.get(connector_id) or registry.resolve(connector_id)
                manifest = getattr(rec, "manifest", None)
            except Exception:
                manifest = None
        fp = compute_certification_fingerprint(connector_id=connector_id, manifest=manifest)
        lease = self.begin_assessment(connector_id)
        return self.complete_assessment(
            connector_id,
            lease_id=lease,
            state=state,
            fingerprint=fp,
            limitations=["test_fixture_certification"] if state == CertificationState.CERTIFIED_WITH_LIMITATIONS.value else [],
            assessed_at="fixture",
            fixture=True,
        )

    def refresh_stale_from_fingerprint(
        self,
        connector_id: str,
        *,
        current_fingerprint: str,
    ) -> CertificationRecord:
        rec = self.get(connector_id)
        if rec.state in (
            CertificationState.CERTIFIED.value,
            CertificationState.CERTIFIED_WITH_LIMITATIONS.value,
        ):
            if rec.fingerprint and rec.fingerprint != current_fingerprint:
                return self.mark_stale(connector_id, reason="fingerprint_mismatch")
        return rec


# Process-global default store (production evidence path)
_GLOBAL: Optional[CertificationStore] = None
_GLOBAL_LOCK = threading.Lock()


def get_certification_store() -> CertificationStore:
    global _GLOBAL
    with _GLOBAL_LOCK:
        if _GLOBAL is None:
            _GLOBAL = CertificationStore()
        return _GLOBAL


def reset_certification_store() -> None:
    global _GLOBAL
    with _GLOBAL_LOCK:
        _GLOBAL = None


def install_test_certification(
    store: CertificationStore,
    connector_id: str,
    *,
    registry: Any = None,
    state: str = CertificationState.CERTIFIED.value,
) -> CertificationRecord:
    return store.install_fixture_certification(connector_id, registry=registry, state=state)
