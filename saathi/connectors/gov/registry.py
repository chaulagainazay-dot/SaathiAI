"""M27/M29 — Governed connector registry, lifecycle, and identity resolution.

M29: register / unregister / validate / list / resolve / inspect / deprecate.
Duplicate IDs fail closed. Unknown connectors fail closed. Identity is never
resolved by import path or filename.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
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


class DuplicateConnectorError(ValueError):
    pass


class UnknownConnectorError(KeyError):
    pass


class UnregisteredConnectorError(KeyError):
    pass


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_semver(v: str) -> tuple[int, int, int]:
    parts = str(v or "0").split("+")[0].split("-")[0].split(".")
    nums: list[int] = []
    for p in parts[:3]:
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    return nums[0], nums[1], nums[2]


class ConnectorRegistry:
    """Canonical in-process registry for governed connectors (M29 identity authority)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, ConnectorRecord] = {}
        self._adapters: dict[str, Any] = {}
        self._version_history: dict[str, list[dict[str, Any]]] = {}

    def register(
        self,
        manifest: ConnectorManifest,
        *,
        adapter: Any = None,
        allow_replace: bool = False,
        allow_upgrade: bool = False,
        skip_manifest_validation: bool = False,
    ) -> ConnectorRecord:
        """Register a connector. Duplicate IDs fail unless allow_replace or version upgrade."""
        with self._lock:
            if manifest.trading:
                raise ValueError("trading connectors are forbidden")

            if not skip_manifest_validation:
                from saathi.connectors.registry.validation import validate_manifest

                # Soft known-deps: only validate graph of already-registered + self
                known = set(self._records.keys()) | {manifest.connector_id}
                # Also allow logical deps not yet registered only as warnings via no known filter
                result = validate_manifest(manifest, strict=True, known_dependency_ids=None)
                if not result.ok:
                    raise ValueError("manifest_invalid:" + ",".join(result.errors))

            existing = self._records.get(manifest.connector_id)
            if existing is not None and not allow_replace:
                if allow_upgrade:
                    old_v = _parse_semver(existing.manifest.version)
                    new_v = _parse_semver(manifest.version)
                    if new_v <= old_v:
                        raise DuplicateConnectorError(
                            f"duplicate_connector_id:{manifest.connector_id}:"
                            f"version_not_greater:{existing.manifest.version}->{manifest.version}"
                        )
                    # Silent replacement forbidden — record history
                    self._version_history.setdefault(manifest.connector_id, []).append({
                        "from_version": existing.manifest.version,
                        "to_version": manifest.version,
                        "ts": _utc(),
                        "previous_deprecated": bool(getattr(existing.manifest, "deprecated", False)),
                    })
                    if not manifest.updated_at:
                        manifest.updated_at = _utc()
                else:
                    raise DuplicateConnectorError(
                        f"duplicate_connector_id:{manifest.connector_id}"
                    )

            if not manifest.created_at:
                if existing and existing.manifest.created_at:
                    manifest.created_at = existing.manifest.created_at
                else:
                    manifest.created_at = _utc()
            if not manifest.updated_at:
                manifest.updated_at = _utc()

            rec = ConnectorRecord(
                manifest=manifest,
                lifecycle=ConnectorLifecycle.REGISTERED,
            )
            self._records[manifest.connector_id] = rec
            if adapter is not None:
                self._adapters[manifest.connector_id] = adapter
            elif manifest.connector_id not in self._adapters and existing is not None:
                # preserve prior adapter on upgrade if none supplied
                pass
            return rec

    def unregister(self, connector_id: str, *, reason: str = "unregistered") -> None:
        with self._lock:
            if connector_id not in self._records:
                raise UnknownConnectorError(connector_id)
            del self._records[connector_id]
            self._adapters.pop(connector_id, None)

    def get(self, connector_id: str) -> Optional[ConnectorRecord]:
        with self._lock:
            return self._records.get(connector_id)

    def resolve(self, connector_id: str) -> ConnectorRecord:
        """Resolve connector identity by registry id only. Fail closed if unknown."""
        with self._lock:
            rec = self._records.get(connector_id)
            if rec is None:
                raise UnknownConnectorError(f"unknown_connector:{connector_id}")
            if getattr(rec.manifest, "deprecated", False):
                # Still resolvable for inspect / drain, but marked
                return rec
            return rec

    def inspect(self, connector_id: str) -> dict[str, Any]:
        rec = self.resolve(connector_id)
        m = rec.manifest
        trust = getattr(m, "trust_level", "INTERNAL")
        from saathi.connectors.registry.trust import (
            approval_floor_for_trust,
            rollout_eligible_for_trust,
        )
        return {
            "connector_id": m.connector_id,
            "version": m.version,
            "display_name": getattr(m, "display_name", "") or m.connector_id,
            "description": m.description,
            "owner": getattr(m, "owner", ""),
            "adapter_type": getattr(m, "adapter_type", "") or (
                m.kind.value if hasattr(m.kind, "value") else str(m.kind)
            ),
            "trust_level": trust,
            "approval_floor": approval_floor_for_trust(trust),
            "rollout_eligible": sorted(rollout_eligible_for_trust(trust)),
            "lifecycle": rec.lifecycle.value,
            "validated": rec.validated,
            "capability_classes": list(getattr(m, "capability_classes", ()) or ()),
            "supported_operations": list(m.supported_operations or m.capabilities or ()),
            "side_effect_classes": list(getattr(m, "side_effect_classes", ()) or ()),
            "required_approvals": list(getattr(m, "required_approvals", ()) or ()),
            "dependencies": list(getattr(m, "dependencies", ()) or ()),
            "health_policy": dict(getattr(m, "health_policy", None) or {}),
            "readiness_policy": dict(getattr(m, "readiness_policy", None) or {}),
            "incident_policy": getattr(m, "incident_policy", "m26"),
            "evidence_policy": m.evidence_policy,
            "rollout_compatible": list(m.rollout_compatible or ()),
            "supported_environments": list(getattr(m, "supported_environments", ()) or ()),
            "deprecated": bool(getattr(m, "deprecated", False)),
            "deprecated_at": getattr(m, "deprecated_at", "") or "",
            "replacement_connector": getattr(m, "replacement_connector", "") or "",
            "created_at": getattr(m, "created_at", "") or "",
            "updated_at": getattr(m, "updated_at", "") or "",
            "version_history": list(self._version_history.get(connector_id, [])),
            "has_adapter": connector_id in self._adapters,
            "request_count": rec.request_count,
            "failure_count": rec.failure_count,
            "identity_source": "registry",  # never import_path / filename
            "privacy_safe": True,
            "m29": True,
        }

    def deprecate(
        self,
        connector_id: str,
        *,
        replacement: str = "",
        reason: str = "",
    ) -> ConnectorRecord:
        with self._lock:
            rec = self._records.get(connector_id)
            if not rec:
                raise UnknownConnectorError(connector_id)
            if replacement and replacement == connector_id:
                raise ValueError("replacement_self_reference")
            if replacement and replacement not in self._records:
                # Replacement must be known — no silent swap to unknown
                raise UnknownConnectorError(f"unknown_replacement:{replacement}")
            m = rec.manifest
            m.deprecated = True
            m.deprecated_at = _utc()
            m.replacement_connector = replacement or m.replacement_connector
            m.updated_at = _utc()
            if reason:
                rec.last_error = f"deprecated:{reason}"[:200]
            # Move toward DRAINING when ready/degraded
            if rec.lifecycle in (ConnectorLifecycle.READY, ConnectorLifecycle.DEGRADED):
                try:
                    self.transition(connector_id, ConnectorLifecycle.DRAINING, reason="deprecated")
                except IllegalLifecycleTransition:
                    pass
            return self._records[connector_id]

    def get_adapter(self, connector_id: str) -> Any:
        with self._lock:
            return self._adapters.get(connector_id)

    def bind_adapter(self, connector_id: str, adapter: Any) -> None:
        with self._lock:
            if connector_id not in self._records:
                raise UnregisteredConnectorError(connector_id)
            self._adapters[connector_id] = adapter

    def list_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._records.keys())

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "connector_id": r.manifest.connector_id,
                    "version": r.manifest.version,
                    "trust_level": getattr(r.manifest, "trust_level", "INTERNAL"),
                    "lifecycle": r.lifecycle.value,
                    "deprecated": bool(getattr(r.manifest, "deprecated", False)),
                }
                for r in self._records.values()
            ]

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
        """Validate manifest schema + auth presence; move REGISTERED → VALIDATED on success."""
        rec = self.get(connector_id)
        if not rec:
            return {"ok": False, "error": "not_registered"}
        m = rec.manifest

        from saathi.connectors.registry.validation import validate_manifest

        schema = validate_manifest(m, strict=True)
        if not schema.ok:
            self.transition(connector_id, ConnectorLifecycle.FAILED, reason="manifest_invalid")
            return {
                "ok": False,
                "error": "manifest_invalid",
                "errors": schema.errors,
                "warnings": schema.warnings,
            }

        # Dependency graph among registered connectors
        try:
            dep_check = self.validate_dependencies(include_unregistered=False)
            if not dep_check.get("ok"):
                return {"ok": False, "error": "dependency_invalid", "detail": dep_check}
        except Exception as e:
            # Only fail this connector if *its* deps are bad
            deps = tuple(getattr(m, "dependencies", ()) or ())
            if deps:
                for d in deps:
                    if d not in self._records and d != connector_id:
                        self.transition(connector_id, ConnectorLifecycle.FAILED, reason=f"unknown_dependency:{d}")
                        return {"ok": False, "error": f"unknown_dependency:{d}"}
            # cycles involving this node
            msg = str(e)
            if "dependency_cycle" in msg and connector_id in msg:
                self.transition(connector_id, ConnectorLifecycle.FAILED, reason=msg[:200])
                return {"ok": False, "error": msg}

        if not m.connector_id or not m.version:
            self.transition(connector_id, ConnectorLifecycle.FAILED, reason="manifest_incomplete")
            return {"ok": False, "error": "manifest_incomplete"}
        if m.cloud and m.kind not in (ConnectorKind.HTTP, ConnectorKind.MCP, ConnectorKind.BROWSER):
            pass
        auth = resolve_auth(m, environ=environ)
        if m.auth_mode.value != "none" and not auth.ok:
            self.transition(connector_id, ConnectorLifecycle.FAILED, reason=auth.detail)
            return {"ok": False, "error": auth.detail, "auth": auth.to_public_dict()}

        # Trust floor vs PROHIBITED
        if str(getattr(m, "trust_level", "")).upper() == "PROHIBITED":
            self.transition(connector_id, ConnectorLifecycle.FAILED, reason="trust_prohibited")
            return {"ok": False, "error": "trust_prohibited"}

        if rec.lifecycle is ConnectorLifecycle.REGISTERED:
            self.transition(connector_id, ConnectorLifecycle.VALIDATED, reason="validated")
        elif rec.lifecycle is ConnectorLifecycle.FAILED:
            self.transition(connector_id, ConnectorLifecycle.VALIDATED, reason="revalidated")
        return {
            "ok": True,
            "lifecycle": self.get(connector_id).lifecycle.value,
            "auth": auth.to_public_dict(),
            "schema_warnings": schema.warnings,
            "m29": True,
        }

    def validate_dependencies(self, *, include_unregistered: bool = False) -> dict[str, Any]:
        from saathi.connectors.registry.deps import validate_dependency_graph

        with self._lock:
            edges = {
                r.manifest.connector_id: list(getattr(r.manifest, "dependencies", ()) or ())
                for r in self._records.values()
            }
            known = set(self._records.keys())
        if include_unregistered:
            return validate_dependency_graph(edges, known_ids=None)
        # Filter edges that only reference known ids for cycle check; unknown deps reported
        unknown: list[str] = []
        filtered: dict[str, list[str]] = {}
        for src, deps in edges.items():
            kept = []
            for d in deps:
                if d in known:
                    kept.append(d)
                else:
                    unknown.append(f"{src}->{d}")
            filtered[src] = kept
        result = validate_dependency_graph(filtered, known_ids=known)
        result["unknown_dependencies"] = unknown
        result["ok"] = result.get("ok", True) and not unknown
        if unknown:
            result["error"] = "unknown_dependencies"
        return result

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
