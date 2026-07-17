"""M27 — Governed connector registry and lifecycle."""
from __future__ import annotations

import threading
from typing import Any, Optional

from saathi.connectors.gov.auth import resolve_auth
from saathi.connectors.gov.models import (
    VALID_LIFECYCLE_TRANSITIONS,
    ConnectorKind,
    ConnectorLifecycle,
    ConnectorManifest,
    ConnectorRecord,
)


class IllegalLifecycleTransition(Exception):
    pass


class ConnectorRegistry:
    """In-process registry for governed connectors."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, ConnectorRecord] = {}
        self._adapters: dict[str, Any] = {}

    def register(
        self,
        manifest: ConnectorManifest,
        *,
        adapter: Any = None,
    ) -> ConnectorRecord:
        with self._lock:
            if manifest.trading:
                raise ValueError("trading connectors are forbidden")
            rec = ConnectorRecord(
                manifest=manifest,
                lifecycle=ConnectorLifecycle.REGISTERED,
            )
            self._records[manifest.connector_id] = rec
            if adapter is not None:
                self._adapters[manifest.connector_id] = adapter
            return rec

    def get(self, connector_id: str) -> Optional[ConnectorRecord]:
        with self._lock:
            return self._records.get(connector_id)

    def get_adapter(self, connector_id: str) -> Any:
        with self._lock:
            return self._adapters.get(connector_id)

    def list_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._records.keys())

    def all_records(self) -> list[ConnectorRecord]:
        with self._lock:
            return list(self._records.values())

    def transition(self, connector_id: str, target: ConnectorLifecycle, *, reason: str = "") -> ConnectorRecord:
        with self._lock:
            rec = self._records.get(connector_id)
            if not rec:
                raise KeyError(connector_id)
            cur = rec.lifecycle
            if target is cur:
                return rec
            allowed = VALID_LIFECYCLE_TRANSITIONS.get(cur, frozenset())
            if target not in allowed:
                raise IllegalLifecycleTransition(f"{cur.value} -> {target.value}")
            rec.lifecycle = target
            if reason:
                rec.last_error = reason[:200]
            if target is ConnectorLifecycle.VALIDATED:
                rec.validated = True
            if target is ConnectorLifecycle.READY:
                rec.validated = True
            return rec

    def validate(self, connector_id: str, *, environ: Optional[dict[str, str]] = None) -> dict[str, Any]:
        """Validate manifest + auth presence; move REGISTERED → VALIDATED on success."""
        rec = self.get(connector_id)
        if not rec:
            return {"ok": False, "error": "not_registered"}
        m = rec.manifest
        if not m.connector_id or not m.version:
            self.transition(connector_id, ConnectorLifecycle.FAILED, reason="manifest_incomplete")
            return {"ok": False, "error": "manifest_incomplete"}
        if m.cloud and m.kind not in (ConnectorKind.HTTP, ConnectorKind.MCP, ConnectorKind.BROWSER):
            # cloud flag without enablement path
            pass
        auth = resolve_auth(m, environ=environ)
        if m.auth_mode.value != "none" and not auth.ok:
            self.transition(connector_id, ConnectorLifecycle.FAILED, reason=auth.detail)
            return {"ok": False, "error": auth.detail, "auth": auth.to_public_dict()}
        # Adapter must be bound for READY later; validation only needs registration
        if rec.lifecycle is ConnectorLifecycle.REGISTERED:
            self.transition(connector_id, ConnectorLifecycle.VALIDATED, reason="validated")
        elif rec.lifecycle is ConnectorLifecycle.FAILED:
            self.transition(connector_id, ConnectorLifecycle.VALIDATED, reason="revalidated")
        return {"ok": True, "lifecycle": self.get(connector_id).lifecycle.value, "auth": auth.to_public_dict()}

    def mark_ready(self, connector_id: str) -> ConnectorRecord:
        rec = self.get(connector_id)
        if not rec:
            raise KeyError(connector_id)
        if rec.lifecycle is ConnectorLifecycle.REGISTERED:
            self.validate(connector_id)
            rec = self.get(connector_id)
        if rec.lifecycle not in (ConnectorLifecycle.VALIDATED, ConnectorLifecycle.DEGRADED, ConnectorLifecycle.READY):
            if rec.lifecycle is ConnectorLifecycle.DISABLED:
                raise IllegalLifecycleTransition("DISABLED -> READY requires re-register path")
        return self.transition(connector_id, ConnectorLifecycle.READY, reason="ready")

    def disable(self, connector_id: str, *, reason: str = "disabled") -> ConnectorRecord:
        return self.transition(connector_id, ConnectorLifecycle.DISABLED, reason=reason)

    def drain(self, connector_id: str) -> ConnectorRecord:
        rec = self.get(connector_id)
        if not rec:
            raise KeyError(connector_id)
        if rec.lifecycle in (ConnectorLifecycle.READY, ConnectorLifecycle.DEGRADED):
            return self.transition(connector_id, ConnectorLifecycle.DRAINING, reason="drain")
        return rec

    def recover(self, connector_id: str) -> ConnectorRecord:
        rec = self.get(connector_id)
        if not rec:
            raise KeyError(connector_id)
        if rec.lifecycle is ConnectorLifecycle.FAILED:
            self.transition(connector_id, ConnectorLifecycle.REGISTERED, reason="recover")
            self.validate(connector_id)
            return self.mark_ready(connector_id)
        if rec.lifecycle is ConnectorLifecycle.DRAINING:
            return self.transition(connector_id, ConnectorLifecycle.READY, reason="recover_from_drain")
        if rec.lifecycle is ConnectorLifecycle.DEGRADED:
            return self.transition(connector_id, ConnectorLifecycle.READY, reason="recover_from_degraded")
        if rec.lifecycle is ConnectorLifecycle.DISABLED:
            self.transition(connector_id, ConnectorLifecycle.REGISTERED, reason="reenable")
            self.validate(connector_id)
            return self.mark_ready(connector_id)
        return rec

    def bump_request(self, connector_id: str, *, ok: bool) -> None:
        with self._lock:
            rec = self._records.get(connector_id)
            if not rec:
                return
            rec.request_count += 1
            if not ok:
                rec.failure_count += 1


_default_registry: Optional[ConnectorRegistry] = None
_reg_lock = threading.Lock()


def get_registry() -> ConnectorRegistry:
    global _default_registry
    with _reg_lock:
        if _default_registry is None:
            _default_registry = ConnectorRegistry()
        return _default_registry


def reset_registry() -> None:
    global _default_registry
    with _reg_lock:
        _default_registry = None
