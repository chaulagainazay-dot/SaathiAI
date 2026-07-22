"""M31 — Canonical credential broker.

Permissions are distinct:
  metadata access | existence check | retrieval | injection | rotation | revocation | deletion
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.credentials.backends import (
    InMemoryTestSecretBackend,
    SecretBackend,
    SecretBackendError,
    create_backend,
)
from saathi.credentials.lease import (
    DEFAULT_LEASE_TTL_SEC,
    LeaseError,
    LeaseStore,
    request_fingerprint,
)
from saathi.credentials.models import (
    SCHEMA_VERSION,
    CredentialReference,
    CredentialStatus,
    CredentialType,
    RevocationState,
    RotationState,
    StorageBackendKind,
    is_prohibited_provider,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_META_PATH = ROOT / "docs" / "evidence" / "m31" / "credential_registry.json"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


class BrokerError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


class CredentialBroker:
    """Governed credential control plane — secrets only via lease + backend."""

    def __init__(
        self,
        *,
        backend: Optional[SecretBackend] = None,
        metadata_path: Optional[Path] = None,
        clock: Optional[Callable[[], float]] = None,
        persist: bool = True,
        event_sink: Optional[Callable[[str, dict], None]] = None,
    ):
        self.backend = backend or InMemoryTestSecretBackend()
        self.metadata_path = Path(metadata_path) if metadata_path else DEFAULT_META_PATH
        self.clock = clock or time.time
        self.persist = persist
        self.event_sink = event_sink
        self.leases = LeaseStore(clock=self.clock)
        self._refs: dict[str, CredentialReference] = {}
        self._lock = threading.RLock()
        self._events: list[dict[str, Any]] = []
        self._incidents: list[dict[str, Any]] = []
        if persist and self.metadata_path.is_file():
            self._load()

    def _emit(self, event_type: str, payload: Optional[dict] = None) -> None:
        ev = {
            "schema": "m31.credential_event.v1",
            "event_type": event_type,
            "ts": _utc(),
            "payload": payload or {},
            "privacy_safe": True,
            "contains_secret_values": False,
        }
        self._events.append(ev)
        if self.event_sink:
            try:
                self.event_sink(event_type, payload or {})
            except Exception:
                pass

    def _incident(self, incident_type: str, summary: str) -> str:
        # Dedup open by type+summary
        for inc in self._incidents:
            if inc.get("state") == "open" and inc.get("type") == incident_type and inc.get("summary") == summary[:200]:
                return inc["id"]
        iid = "inc_" + uuid.uuid4().hex[:10]
        self._incidents.append({
            "id": iid,
            "type": incident_type,
            "summary": summary[:200],
            "state": "open",
            "ts": _utc(),
            "privacy_safe": True,
        })
        return iid

    def _load(self) -> None:
        try:
            data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            for rid, raw in (data.get("credentials") or {}).items():
                self._refs[rid] = CredentialReference(**{
                    k: raw[k] for k in CredentialReference.__dataclass_fields__ if k in raw
                })
        except Exception:
            self._refs = {}

    def _save(self) -> None:
        if not self.persist:
            return
        payload = {
            "schema": SCHEMA_VERSION,
            "credentials": {k: v.to_safe_dict() for k, v in sorted(self._refs.items())},
            "privacy_safe": True,
            "contains_secret_values": False,
            "real_credentials_stored": 0,
            "trading_guardian": "UNCHANGED / UNENGAGED",
        }
        _atomic_write(self.metadata_path, payload)

    # ── Metadata access ─────────────────────────────────────────────────────

    def inspect(self, credential_ref_id: str, *, owner_scope: str = "") -> dict[str, Any]:
        ref = self._refs.get(credential_ref_id)
        if ref is None:
            raise BrokerError("unknown_credential_ref")
        if owner_scope and ref.owner_scope != owner_scope:
            self._incident("cross_owner_account_access", "cross-owner credential inspect denied")
            raise BrokerError("cross_owner_denied")
        return ref.to_safe_dict()

    def list_metadata(self, *, owner_scope: str = "") -> list[dict[str, Any]]:
        out = []
        for ref in self._refs.values():
            if owner_scope and ref.owner_scope != owner_scope:
                continue
            out.append(ref.to_safe_dict())
        return out

    def get_ref(self, credential_ref_id: str) -> Optional[CredentialReference]:
        return self._refs.get(credential_ref_id)

    # ── Existence check (no values) ─────────────────────────────────────────

    def exists(self, credential_ref_id: str) -> bool:
        ref = self._refs.get(credential_ref_id)
        if ref is None:
            return False
        if ref.status in (
            CredentialStatus.REVOKED.value,
            CredentialStatus.DELETED.value,
            CredentialStatus.QUARANTINED.value,
        ):
            return False
        try:
            return self.backend.exists(ref.backend_locator or credential_ref_id)
        except Exception:
            return False

    # ── Create reference + store secrets ────────────────────────────────────

    def create_reference(
        self,
        *,
        owner_scope: str,
        provider_id: str,
        credential_type: str = CredentialType.GENERIC.value,
        secret_fields: Optional[dict[str, str]] = None,
        secret_field_names: Optional[tuple[str, ...]] = None,
        scopes: tuple[str, ...] = (),
        account_link_id: str = "",
        connector_ids: tuple[str, ...] = (),
        environment: str = "test",
        storage_backend: str = "",
        expires_at: str = "",
        allow_caller_backend: bool = False,
    ) -> CredentialReference:
        """Create a credential reference.

        Callers cannot choose storage backend unless allow_caller_backend is
        explicitly set for test fixtures (never for production callers).
        """
        if is_prohibited_provider(provider_id):
            raise BrokerError("PROHIBITED_PROVIDER", f"provider blocked: {provider_id}")
        for s in scopes:
            from saathi.credentials.models import is_prohibited_scope
            if is_prohibited_scope(s):
                raise BrokerError("PROHIBITED_SCOPE", s)

        # Backend selection is broker-owned
        if storage_backend and not allow_caller_backend:
            raise BrokerError("caller_cannot_select_backend")
        backend_kind = storage_backend or getattr(self.backend, "kind", StorageBackendKind.IN_MEMORY_TEST.value)

        rid = "cred_" + uuid.uuid4().hex[:16]
        locator = rid
        fields = secret_fields or {}
        # Only field NAMES are recorded in metadata; values stay in the backend.
        names = tuple(secret_field_names or tuple(fields.keys()))

        # Store secrets first if provided
        if fields:
            try:
                self.backend.put(locator, {k: str(v) for k, v in fields.items()})
            except SecretBackendError as e:
                self._incident("credential_backend_unavailable", e.code)
                raise BrokerError(e.code) from e

        ref = CredentialReference(
            credential_ref_id=rid,
            credential_type=credential_type,
            provider_id=provider_id,
            account_link_id=account_link_id,
            owner_scope=owner_scope,
            environment=environment,
            storage_backend=backend_kind,
            secret_fields_present=names,
            scopes=tuple(scopes),
            created_at=_utc(),
            updated_at=_utc(),
            expires_at=expires_at,
            status=CredentialStatus.ACTIVE.value,
            backend_locator=locator,
            connector_ids=tuple(connector_ids),
            metadata_safe={"fields_count": len(names)},
        )
        ref.fingerprint = ref.compute_fingerprint()
        with self._lock:
            self._refs[rid] = ref
            self._save()
        self._emit("credential.reference_created", {
            "credential_ref_id": rid,
            "provider_id": provider_id,
            "owner_scope": owner_scope,
        })
        return ref

    # ── Lease + injection path ──────────────────────────────────────────────

    def issue_lease(
        self,
        *,
        credential_ref_id: str,
        request_id: str,
        connector_id: str,
        operation: str,
        actor: str,
        owner_scope: str = "",
        purpose: str = "execution_injection",
        ttl_seconds: float = DEFAULT_LEASE_TTL_SEC,
        payload: Optional[dict] = None,
        resource_target: str = "",
        allowed_fields: Optional[tuple[str, ...]] = None,
    ) -> dict[str, Any]:
        ref = self._refs.get(credential_ref_id)
        if ref is None:
            raise BrokerError("unknown_credential_ref")
        if owner_scope and ref.owner_scope != owner_scope:
            self._incident("cross_owner_account_access", "cross-owner lease denied")
            raise BrokerError("cross_owner_denied")
        if ref.status == CredentialStatus.REVOKED.value:
            raise BrokerError("credential_revoked")
        if ref.status == CredentialStatus.QUARANTINED.value:
            raise BrokerError("credential_quarantined")
        if ref.status == CredentialStatus.EXPIRED.value:
            raise BrokerError("credential_expired")
        if ref.status == CredentialStatus.DELETED.value:
            raise BrokerError("credential_deleted")
        if ref.connector_ids and connector_id not in ref.connector_ids:
            raise BrokerError("connector_not_bound")

        fields = allowed_fields or ref.secret_fields_present
        # Caller cannot request undeclared fields
        for f in fields:
            if f not in ref.secret_fields_present:
                raise BrokerError("undeclared_secret_field")

        fp = request_fingerprint(
            connector_id=connector_id,
            operation=operation,
            request_id=request_id,
            payload=payload,
            resource_target=resource_target,
        )
        lease = self.leases.issue(
            credential_ref_id=credential_ref_id,
            request_id=request_id,
            connector_id=connector_id,
            operation=operation,
            actor=actor,
            purpose=purpose,
            ttl_seconds=ttl_seconds,
            request_fingerprint=fp,
            allowed_fields=tuple(fields),
        )
        self._emit("credential.lease_issued", lease.to_safe_dict())
        return lease.to_safe_dict()

    def inject_secrets(
        self,
        *,
        lease_id: str,
        credential_ref_id: str,
        request_id: str,
        connector_id: str,
        operation: str,
        payload: Optional[dict] = None,
        resource_target: str = "",
    ) -> dict[str, str]:
        """Retrieve secret fields only for a valid lease. Caller must discard.

        Unleased retrieval is not supported (use this path only).
        """
        fp = request_fingerprint(
            connector_id=connector_id,
            operation=operation,
            request_id=request_id,
            payload=payload,
            resource_target=resource_target,
        )
        try:
            lease = self.leases.validate_and_consume(
                lease_id,
                credential_ref_id=credential_ref_id,
                request_id=request_id,
                connector_id=connector_id,
                operation=operation,
                request_fingerprint=fp,
            )
        except LeaseError as e:
            if e.code == "lease_expired":
                self._emit("credential.lease_expired", {"lease_id": lease_id})
            raise BrokerError(e.code) from e

        ref = self._refs.get(credential_ref_id)
        if ref is None:
            raise BrokerError("unknown_credential_ref")
        if ref.status in (
            CredentialStatus.REVOKED.value,
            CredentialStatus.QUARANTINED.value,
            CredentialStatus.EXPIRED.value,
            CredentialStatus.DELETED.value,
        ):
            raise BrokerError(f"credential_{ref.status.lower()}")

        try:
            secrets = self.backend.get(
                ref.backend_locator or credential_ref_id,
                fields=list(lease.allowed_fields) if lease.allowed_fields else None,
            )
        except SecretBackendError as e:
            self._incident("credential_backend_unavailable", e.code)
            raise BrokerError(e.code) from e
        # Return only allowed fields
        if lease.allowed_fields:
            secrets = {k: v for k, v in secrets.items() if k in lease.allowed_fields}
        return secrets

    def retrieve_unleased(self, credential_ref_id: str) -> None:
        """Explicitly blocked — unleased retrieval fails closed."""
        self._incident("credential_access_denied", "unleased_retrieval_blocked")
        raise BrokerError("unleased_retrieval_forbidden")

    # ── Rotation / expiry / quarantine / revoke / delete ────────────────────

    def mark_expired(self, credential_ref_id: str) -> CredentialReference:
        ref = self._require(credential_ref_id)
        ref.status = CredentialStatus.EXPIRED.value
        ref.updated_at = _utc()
        ref.fingerprint = ref.compute_fingerprint()
        self.leases.revoke_for_credential(credential_ref_id)
        self._save()
        return ref

    def require_rotation(self, credential_ref_id: str) -> CredentialReference:
        ref = self._require(credential_ref_id)
        ref.rotation_state = RotationState.REQUIRED.value
        ref.status = CredentialStatus.ROTATION_REQUIRED.value
        ref.updated_at = _utc()
        self._emit("credential.rotation_required", {"credential_ref_id": credential_ref_id})
        self._save()
        return ref

    def rotate(
        self,
        credential_ref_id: str,
        *,
        new_secret_fields: dict[str, str],
        invalidate_old: bool = True,
    ) -> CredentialReference:
        ref = self._require(credential_ref_id)
        if ref.status == CredentialStatus.REVOKED.value:
            raise BrokerError("credential_revoked")
        locator = ref.backend_locator or credential_ref_id
        if invalidate_old:
            try:
                self.backend.delete(locator)
            except SecretBackendError:
                pass
        self.backend.put(locator, {k: str(v) for k, v in new_secret_fields.items()})
        ref.secret_fields_present = tuple(new_secret_fields.keys())
        ref.rotation_state = RotationState.COMPLETE.value
        ref.status = CredentialStatus.ACTIVE.value
        ref.updated_at = _utc()
        ref.fingerprint = ref.compute_fingerprint()
        self.leases.revoke_for_credential(credential_ref_id)
        self._save()
        return ref

    def quarantine(self, credential_ref_id: str, *, reason: str) -> CredentialReference:
        ref = self._require(credential_ref_id)
        ref.status = CredentialStatus.QUARANTINED.value
        ref.quarantine_reason = reason[:200]
        ref.updated_at = _utc()
        ref.fingerprint = ref.compute_fingerprint()
        self.leases.revoke_for_credential(credential_ref_id)
        self._emit("credential.quarantined", {
            "credential_ref_id": credential_ref_id,
            "reason": reason[:200],
        })
        self._incident("credential_quarantined", reason[:200])
        self._save()
        return ref

    def revoke(self, credential_ref_id: str, *, reason: str) -> CredentialReference:
        ref = self._require(credential_ref_id)
        ref.status = CredentialStatus.REVOKED.value
        ref.revocation_state = RevocationState.REVOKED.value
        ref.updated_at = _utc()
        ref.metadata_safe = {**(ref.metadata_safe or {}), "revoke_reason": reason[:200]}
        ref.fingerprint = ref.compute_fingerprint()
        self.leases.revoke_for_credential(credential_ref_id)
        self._emit("credential.revoked", {
            "credential_ref_id": credential_ref_id,
            "reason": reason[:200],
        })
        self._save()
        return ref

    def delete_secret_material(self, credential_ref_id: str, *, reason: str) -> CredentialReference:
        """Explicit governed deletion of secret material — separate from revoke."""
        ref = self._require(credential_ref_id)
        try:
            self.backend.delete(ref.backend_locator or credential_ref_id)
        except SecretBackendError as e:
            if e.code != "secret_not_found":
                raise BrokerError(e.code) from e
        ref.status = CredentialStatus.DELETED.value
        ref.revocation_state = RevocationState.DELETED.value
        ref.updated_at = _utc()
        ref.metadata_safe = {**(ref.metadata_safe or {}), "delete_reason": reason[:200]}
        self.leases.revoke_for_credential(credential_ref_id)
        self._emit("credential.deleted", {"credential_ref_id": credential_ref_id})
        self._save()
        return ref

    def _require(self, credential_ref_id: str) -> CredentialReference:
        ref = self._refs.get(credential_ref_id)
        if ref is None:
            raise BrokerError("unknown_credential_ref")
        return ref

    def readiness(self) -> dict[str, Any]:
        be = self.backend.readiness()
        return {
            "schema": "m31.broker_readiness.v1",
            "backend": be,
            "credential_count": len(self._refs),
            "active_leases": sum(
                1 for l in self.leases.list_safe() if l.get("status") == "ISSUED"
            ),
            "real_credentials_stored": 0,
            "live_oauth_flows": 0,
            "ready": bool(be.get("ready")),
            "privacy_safe": True,
        }

    def status_report(self) -> dict[str, Any]:
        return {
            "schema": "m31.broker_status.v1",
            "credentials": self.list_metadata(),
            "leases": self.leases.list_safe(),
            "backend": self.backend.readiness(),
            "events_count": len(self._events),
            "incidents": list(self._incidents),
            "real_credentials_stored": 0,
            "real_oauth_flows_completed": 0,
            "live_accounts_linked": 0,
            "trading_guardian": "UNCHANGED / UNENGAGED",
            "privacy_safe": True,
            "contains_secret_values": False,
        }


_GLOBAL: Optional[CredentialBroker] = None
_GLOCK = threading.Lock()


def get_broker() -> CredentialBroker:
    global _GLOBAL
    with _GLOCK:
        if _GLOBAL is None:
            _GLOBAL = CredentialBroker()
        return _GLOBAL


def reset_broker() -> None:
    global _GLOBAL
    with _GLOCK:
        _GLOBAL = None
