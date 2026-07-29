"""Universal Application Runtime domain model (M121+).

Applications are first-class platform citizens. They never bypass ExecutionGateway,
Approval Center, RBAC, Skill Runtime, Conversation, Knowledge, or Workers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import re
import time
from typing import Any

from saathi.platform.apps import limits

APP_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,64}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([.-][a-zA-Z0-9]+)?$")


class AppLifecycleState(str, Enum):
    DISCOVERED = "DISCOVERED"
    VALIDATED = "VALIDATED"
    REGISTERED = "REGISTERED"
    INSTALLED = "INSTALLED"
    DISABLED = "DISABLED"
    ENABLED = "ENABLED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    UPGRADING = "UPGRADING"
    MIGRATING = "MIGRATING"
    BACKING_UP = "BACKING_UP"
    RESTORING = "RESTORING"
    QUARANTINED = "QUARANTINED"
    REVOKED = "REVOKED"
    UNINSTALLED = "UNINSTALLED"
    FAILED = "FAILED"


class AppHealthState(str, Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    BLOCKED = "BLOCKED"
    QUARANTINED = "QUARANTINED"
    DISABLED = "DISABLED"


class AppTrustState(str, Enum):
    BUILT_IN = "BUILT_IN"
    TRUSTED_LOCAL = "TRUSTED_LOCAL"
    DEVELOPMENT_LOCAL = "DEVELOPMENT_LOCAL"
    UNVERIFIED = "UNVERIFIED"
    QUARANTINED = "QUARANTINED"
    REVOKED = "REVOKED"


EXECUTABLE_STATES = frozenset(
    {
        AppLifecycleState.ENABLED.value,
        AppLifecycleState.RUNNING.value,
        AppLifecycleState.PAUSED.value,
    }
)
EXECUTABLE_TRUST = frozenset(
    {AppTrustState.BUILT_IN.value, AppTrustState.TRUSTED_LOCAL.value}
)

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    AppLifecycleState.DISCOVERED.value: frozenset(
        {AppLifecycleState.VALIDATED.value, AppLifecycleState.FAILED.value}
    ),
    AppLifecycleState.VALIDATED.value: frozenset(
        {AppLifecycleState.REGISTERED.value, AppLifecycleState.FAILED.value}
    ),
    AppLifecycleState.REGISTERED.value: frozenset(
        {AppLifecycleState.INSTALLED.value, AppLifecycleState.UNINSTALLED.value}
    ),
    AppLifecycleState.INSTALLED.value: frozenset(
        {
            AppLifecycleState.DISABLED.value,
            AppLifecycleState.ENABLED.value,
            AppLifecycleState.UNINSTALLED.value,
            AppLifecycleState.QUARANTINED.value,
        }
    ),
    AppLifecycleState.DISABLED.value: frozenset(
        {
            AppLifecycleState.ENABLED.value,
            AppLifecycleState.UPGRADING.value,
            AppLifecycleState.UNINSTALLED.value,
            AppLifecycleState.QUARANTINED.value,
            AppLifecycleState.BACKING_UP.value,
        }
    ),
    AppLifecycleState.ENABLED.value: frozenset(
        {
            AppLifecycleState.RUNNING.value,
            AppLifecycleState.DISABLED.value,
            AppLifecycleState.PAUSED.value,
            AppLifecycleState.UPGRADING.value,
            AppLifecycleState.BACKING_UP.value,
            AppLifecycleState.QUARANTINED.value,
            AppLifecycleState.MIGRATING.value,
        }
    ),
    AppLifecycleState.RUNNING.value: frozenset(
        {
            AppLifecycleState.ENABLED.value,
            AppLifecycleState.PAUSED.value,
            AppLifecycleState.DISABLED.value,
            AppLifecycleState.QUARANTINED.value,
        }
    ),
    AppLifecycleState.PAUSED.value: frozenset(
        {
            AppLifecycleState.ENABLED.value,
            AppLifecycleState.RUNNING.value,
            AppLifecycleState.DISABLED.value,
        }
    ),
    AppLifecycleState.UPGRADING.value: frozenset(
        {
            AppLifecycleState.ENABLED.value,
            AppLifecycleState.DISABLED.value,
            AppLifecycleState.FAILED.value,
            AppLifecycleState.MIGRATING.value,
        }
    ),
    AppLifecycleState.MIGRATING.value: frozenset(
        {
            AppLifecycleState.ENABLED.value,
            AppLifecycleState.DISABLED.value,
            AppLifecycleState.FAILED.value,
        }
    ),
    AppLifecycleState.BACKING_UP.value: frozenset(
        {AppLifecycleState.ENABLED.value, AppLifecycleState.DISABLED.value}
    ),
    AppLifecycleState.RESTORING.value: frozenset(
        {
            AppLifecycleState.ENABLED.value,
            AppLifecycleState.DISABLED.value,
            AppLifecycleState.FAILED.value,
        }
    ),
    AppLifecycleState.QUARANTINED.value: frozenset(
        {AppLifecycleState.REVOKED.value, AppLifecycleState.DISABLED.value}
    ),
    AppLifecycleState.REVOKED.value: frozenset({AppLifecycleState.UNINSTALLED.value}),
    AppLifecycleState.UNINSTALLED.value: frozenset(),
    AppLifecycleState.FAILED.value: frozenset(
        {AppLifecycleState.DISABLED.value, AppLifecycleState.UNINSTALLED.value}
    ),
}


def validate_transition(current: str, nxt: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    if nxt not in allowed and current != nxt:
        raise ValueError(f"invalid app lifecycle transition {current} → {nxt}")


@dataclass
class AppManifest:
    manifest_schema_version: str
    app_id: str
    name: str
    display_name: str
    description: str
    publisher: str
    version: str
    app_type: str = "business"
    category: str = "platform"
    icon: str = "▦"
    entrypoint_type: str = "declarative"
    minimum_saathios_version: str = limits.SAATHIOS_VERSION
    pages: list[dict[str, Any]] = field(default_factory=list)
    navigation: list[dict[str, Any]] = field(default_factory=list)
    dashboards: list[dict[str, Any]] = field(default_factory=list)
    forms: list[dict[str, Any]] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    optional_permissions: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    knowledge_sources: list[str] = field(default_factory=list)
    worker_requirements: list[str] = field(default_factory=list)
    approval_requirements: list[str] = field(default_factory=list)
    workflows: list[dict[str, Any]] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    storage: dict[str, Any] = field(default_factory=dict)
    notifications: dict[str, Any] = field(default_factory=dict)
    health_check_contract: str = "manifest_and_workspace"
    backup_strategy: str = "workspace_snapshot"
    restore_strategy: str = "replace_workspace_snapshot"
    upgrade_strategy: str = "install_side_by_side_then_switch"
    migration_strategy: str = "config_only_no_schema_break"
    production_posture: str = "not_authorized"
    trading_guardian_posture: str = "unengaged"
    network_requirements: str = "none"
    local_trust_status: str = AppTrustState.BUILT_IN.value
    module_registry_id: str = ""  # optional link to ModuleRegistry id
    package_hash: str = ""
    content_hash: str = ""
    feature_flags: dict[str, Any] = field(default_factory=dict)
    extension: dict[str, Any] = field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        return asdict(self)

    def compute_content_hash(self) -> str:
        data = self.to_public()
        for k in ("content_hash", "package_hash"):
            data.pop(k, None)
        raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AppManifest":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        unknown = set(raw.keys()) - known - {"extension"}
        filtered = {k: v for k, v in raw.items() if k in known}
        m = cls(**filtered)
        if unknown:
            m.extension = dict(m.extension or {})
            m.extension["_unknown_critical_fields"] = sorted(unknown)
        return m


@dataclass
class AppRecord:
    install_id: str
    app_id: str
    version: str
    lifecycle_state: str
    trust_state: str
    health_state: str = AppHealthState.UNKNOWN.value
    org_id: str = ""
    workspace_id: str = ""
    package_hash: str = ""
    manifest_hash: str = ""
    effective: bool = False
    favorite: bool = False
    last_launched_at: float = 0.0
    installed_at: float = 0.0
    updated_at: float = 0.0
    rollback_target: str = ""
    quarantine_reason: str = ""
    source_path: str = ""
    manifest: dict[str, Any] = field(default_factory=dict)
    workspace_config: dict[str, Any] = field(default_factory=dict)
    launch_count: int = 0

    def to_public(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AppRecord":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass
class AppBackupRecord:
    backup_id: str
    app_id: str
    version: str
    org_id: str
    workspace_id: str
    created_at: float
    snapshot: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    content_hash: str = ""

    def to_public(self, *, include_snapshot: bool = False) -> dict[str, Any]:
        d = {
            "backup_id": self.backup_id,
            "app_id": self.app_id,
            "version": self.version,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at,
            "reason": self.reason,
            "content_hash": self.content_hash,
        }
        if include_snapshot:
            d["snapshot"] = dict(self.snapshot)
        return d


def content_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def now_ts() -> float:
    return time.time()
