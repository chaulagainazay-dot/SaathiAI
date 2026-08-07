"""Skill Ecosystem domain model (M112+).

A skill is a policy-bound, versioned capability package — not a permission grant,
approval, tool authority, or unrestricted script.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import re
from typing import Any

from saathi.platform.skills import limits

SKILL_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,80}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([.-][a-zA-Z0-9]+)?$")


class SkillLifecycleState(str, Enum):
    DISCOVERED = "DISCOVERED"
    VALIDATING = "VALIDATING"
    VALID = "VALID"
    INVALID = "INVALID"
    REGISTERED = "REGISTERED"
    DISABLED = "DISABLED"
    ENABLING = "ENABLING"
    ENABLED = "ENABLED"
    DEGRADED = "DEGRADED"
    UPGRADING = "UPGRADING"
    ROLLING_BACK = "ROLLING_BACK"
    QUARANTINED = "QUARANTINED"
    REVOKED = "REVOKED"
    UNINSTALLING = "UNINSTALLING"
    UNINSTALLED = "UNINSTALLED"
    FAILED = "FAILED"
    BLOCKED_INCOMPATIBLE = "BLOCKED_INCOMPATIBLE"
    BLOCKED_DEPENDENCY = "BLOCKED_DEPENDENCY"
    BLOCKED_PERMISSION = "BLOCKED_PERMISSION"
    BLOCKED_APPROVAL = "BLOCKED_APPROVAL"
    BLOCKED_POLICY = "BLOCKED_POLICY"


class SkillTrustState(str, Enum):
    BUILT_IN = "BUILT_IN"
    TRUSTED_LOCAL = "TRUSTED_LOCAL"
    DEVELOPMENT_LOCAL = "DEVELOPMENT_LOCAL"
    UNVERIFIED = "UNVERIFIED"
    QUARANTINED = "QUARANTINED"
    REVOKED = "REVOKED"


class SkillHealthState(str, Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    BLOCKED = "BLOCKED"
    QUARANTINED = "QUARANTINED"
    REVOKED = "REVOKED"
    DISABLED = "DISABLED"
    INCOMPATIBLE = "INCOMPATIBLE"


class SkillApprovalClass(str, Enum):
    NO_APPROVAL_REQUIRED = "NO_APPROVAL_REQUIRED"
    APPROVAL_REQUIRED_TO_REGISTER = "APPROVAL_REQUIRED_TO_REGISTER"
    APPROVAL_REQUIRED_TO_ENABLE = "APPROVAL_REQUIRED_TO_ENABLE"
    APPROVAL_REQUIRED_TO_EXECUTE = "APPROVAL_REQUIRED_TO_EXECUTE"
    APPROVAL_REQUIRED_FOR_MUTATION = "APPROVAL_REQUIRED_FOR_MUTATION"
    APPROVAL_REQUIRED_FOR_EXTERNAL_CALL = "APPROVAL_REQUIRED_FOR_EXTERNAL_CALL"
    APPROVAL_REQUIRED_FOR_CREDENTIAL_REFERENCE = "APPROVAL_REQUIRED_FOR_CREDENTIAL_REFERENCE"
    APPROVAL_REQUIRED_FOR_PRODUCTION = "APPROVAL_REQUIRED_FOR_PRODUCTION"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"


class SkillRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# States that may execute
EXECUTABLE_STATES = frozenset(
    {
        SkillLifecycleState.ENABLED.value,
        SkillLifecycleState.DEGRADED.value,
    }
)
EXECUTABLE_TRUST = frozenset(
    {
        SkillTrustState.BUILT_IN.value,
        SkillTrustState.TRUSTED_LOCAL.value,
    }
)

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    SkillLifecycleState.DISCOVERED.value: frozenset(
        {
            SkillLifecycleState.VALIDATING.value,
            SkillLifecycleState.INVALID.value,
            SkillLifecycleState.UNINSTALLED.value,
        }
    ),
    SkillLifecycleState.VALIDATING.value: frozenset(
        {
            SkillLifecycleState.VALID.value,
            SkillLifecycleState.INVALID.value,
            SkillLifecycleState.BLOCKED_POLICY.value,
        }
    ),
    SkillLifecycleState.VALID.value: frozenset(
        {
            SkillLifecycleState.REGISTERED.value,
            SkillLifecycleState.INVALID.value,
            SkillLifecycleState.BLOCKED_APPROVAL.value,
        }
    ),
    SkillLifecycleState.INVALID.value: frozenset(
        {SkillLifecycleState.VALIDATING.value, SkillLifecycleState.UNINSTALLED.value}
    ),
    SkillLifecycleState.REGISTERED.value: frozenset(
        {
            SkillLifecycleState.DISABLED.value,
            SkillLifecycleState.ENABLING.value,
            SkillLifecycleState.QUARANTINED.value,
            SkillLifecycleState.REVOKED.value,
            SkillLifecycleState.UNINSTALLING.value,
            SkillLifecycleState.BLOCKED_DEPENDENCY.value,
            SkillLifecycleState.BLOCKED_PERMISSION.value,
            SkillLifecycleState.BLOCKED_INCOMPATIBLE.value,
        }
    ),
    SkillLifecycleState.DISABLED.value: frozenset(
        {
            SkillLifecycleState.ENABLING.value,
            SkillLifecycleState.UPGRADING.value,
            SkillLifecycleState.QUARANTINED.value,
            SkillLifecycleState.REVOKED.value,
            SkillLifecycleState.UNINSTALLING.value,
        }
    ),
    SkillLifecycleState.ENABLING.value: frozenset(
        {
            SkillLifecycleState.ENABLED.value,
            SkillLifecycleState.DISABLED.value,
            SkillLifecycleState.BLOCKED_APPROVAL.value,
            SkillLifecycleState.BLOCKED_DEPENDENCY.value,
            SkillLifecycleState.BLOCKED_PERMISSION.value,
            SkillLifecycleState.FAILED.value,
        }
    ),
    SkillLifecycleState.ENABLED.value: frozenset(
        {
            SkillLifecycleState.DISABLED.value,
            SkillLifecycleState.DEGRADED.value,
            SkillLifecycleState.UPGRADING.value,
            SkillLifecycleState.QUARANTINED.value,
            SkillLifecycleState.REVOKED.value,
            SkillLifecycleState.UNINSTALLING.value,
        }
    ),
    SkillLifecycleState.DEGRADED.value: frozenset(
        {
            SkillLifecycleState.ENABLED.value,
            SkillLifecycleState.DISABLED.value,
            SkillLifecycleState.QUARANTINED.value,
            SkillLifecycleState.UPGRADING.value,
            SkillLifecycleState.ROLLING_BACK.value,
        }
    ),
    SkillLifecycleState.UPGRADING.value: frozenset(
        {
            SkillLifecycleState.ENABLED.value,
            SkillLifecycleState.DISABLED.value,
            SkillLifecycleState.ROLLING_BACK.value,
            SkillLifecycleState.FAILED.value,
            SkillLifecycleState.QUARANTINED.value,
        }
    ),
    SkillLifecycleState.ROLLING_BACK.value: frozenset(
        {
            SkillLifecycleState.ENABLED.value,
            SkillLifecycleState.DISABLED.value,
            SkillLifecycleState.FAILED.value,
        }
    ),
    SkillLifecycleState.QUARANTINED.value: frozenset(
        {
            SkillLifecycleState.REVOKED.value,
            SkillLifecycleState.DISABLED.value,
            SkillLifecycleState.UNINSTALLING.value,
        }
    ),
    SkillLifecycleState.REVOKED.value: frozenset(
        {SkillLifecycleState.UNINSTALLING.value, SkillLifecycleState.UNINSTALLED.value}
    ),
    SkillLifecycleState.UNINSTALLING.value: frozenset(
        {SkillLifecycleState.UNINSTALLED.value, SkillLifecycleState.FAILED.value}
    ),
    SkillLifecycleState.UNINSTALLED.value: frozenset(),
    SkillLifecycleState.FAILED.value: frozenset(
        {
            SkillLifecycleState.DISABLED.value,
            SkillLifecycleState.QUARANTINED.value,
            SkillLifecycleState.ROLLING_BACK.value,
            SkillLifecycleState.UNINSTALLING.value,
        }
    ),
    SkillLifecycleState.BLOCKED_INCOMPATIBLE.value: frozenset(
        {SkillLifecycleState.DISABLED.value, SkillLifecycleState.UNINSTALLING.value}
    ),
    SkillLifecycleState.BLOCKED_DEPENDENCY.value: frozenset(
        {SkillLifecycleState.DISABLED.value, SkillLifecycleState.ENABLING.value}
    ),
    SkillLifecycleState.BLOCKED_PERMISSION.value: frozenset(
        {SkillLifecycleState.DISABLED.value}
    ),
    SkillLifecycleState.BLOCKED_APPROVAL.value: frozenset(
        {SkillLifecycleState.DISABLED.value, SkillLifecycleState.ENABLING.value}
    ),
    SkillLifecycleState.BLOCKED_POLICY.value: frozenset(
        {SkillLifecycleState.INVALID.value, SkillLifecycleState.UNINSTALLED.value}
    ),
}


def validate_transition(current: str, nxt: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    if nxt not in allowed and current != nxt:
        raise ValueError(f"invalid skill lifecycle transition {current} → {nxt}")


@dataclass
class SkillDependency:
    skill_id: str
    version_range: str = ">=0.0.0"
    required: bool = True

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SkillManifest:
    """Strict skill package manifest. Declarations never grant authority."""

    manifest_schema_version: str
    skill_id: str
    name: str
    display_name: str
    description: str
    publisher: str
    version: str
    minimum_saathios_version: str = limits.SAATHIOS_VERSION
    maximum_saathios_version: str = ""
    entrypoint_type: str = "declarative"
    lifecycle_state: str = SkillLifecycleState.DISCOVERED.value
    domain: str = "platform"
    tags: list[str] = field(default_factory=list)
    declared_capabilities: list[str] = field(default_factory=list)
    declared_tools: list[str] = field(default_factory=list)
    declared_agent_roles: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    optional_permissions: list[str] = field(default_factory=list)
    prohibited_permissions: list[str] = field(default_factory=list)
    approval_requirements: list[str] = field(default_factory=list)
    worker_requirements: list[str] = field(default_factory=list)
    platform_requirements: list[str] = field(default_factory=list)
    os_requirements: list[str] = field(default_factory=lambda: ["darwin", "linux"])
    local_model_requirements: list[str] = field(default_factory=list)
    browser_requirements: bool = False
    storage_requirements_mb: int = 16
    network_requirements: str = "none"  # none | loopback | forbidden_external
    credential_reference_requirements: list[str] = field(default_factory=list)
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    resource_budgets: dict[str, Any] = field(default_factory=dict)
    timeouts: dict[str, float] = field(default_factory=dict)
    retry_policy: dict[str, Any] = field(default_factory=dict)
    cancellation_contract: str = "cooperative"
    health_check_contract: str = "manifest_hash_and_tools"
    evidence_contract: str = "content_hash"
    audit_contract: str = "platform_audit"
    upgrade_policy: str = "keep_previous_until_rollback_window"
    rollback_policy: str = "restore_previous_certified"
    data_handling_classification: str = "operational"
    privacy_classification: str = "no_personal_data"
    risk_classification: str = SkillRisk.LOW.value
    production_posture: str = "not_authorized"
    trading_guardian_posture: str = "unengaged_readonly_only"
    content_hash: str = ""
    package_hash: str = ""
    signature_status: str = "local_unsigned"
    local_trust_status: str = SkillTrustState.UNVERIFIED.value
    documentation_references: list[str] = field(default_factory=list)
    orchestration_template_id: str = ""
    knowledge_sources: list[str] = field(default_factory=list)
    extension: dict[str, Any] = field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_bytes(self) -> bytes:
        data = self.to_public()
        # Exclude mutable runtime fields from content hash base
        for k in ("lifecycle_state", "content_hash", "package_hash"):
            data.pop(k, None)
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def compute_content_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SkillManifest":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        # Reject unknown critical fields (not under extension)
        unknown = set(raw.keys()) - known - {"extension"}
        # Allow only nested extension bag for non-critical extensions
        filtered = {k: v for k, v in raw.items() if k in known}
        if "extension" in raw and isinstance(raw["extension"], dict):
            filtered["extension"] = raw["extension"]
        m = cls(**{k: v for k, v in filtered.items() if k in known})
        # Store unknown for validator to reject if critical
        if unknown:
            m.extension = dict(m.extension or {})
            m.extension["_unknown_critical_fields"] = sorted(unknown)
        return m


@dataclass
class SkillRecord:
    """Installed / registered skill version in a tenant/workspace scope."""

    install_id: str
    skill_id: str
    version: str
    package_hash: str
    manifest_hash: str
    lifecycle_state: str
    trust_state: str
    health_state: str = SkillHealthState.UNKNOWN.value
    org_id: str = ""
    workspace_id: str = ""
    enabled_scope: str = "workspace"  # workspace | tenant
    effective: bool = False
    registered_at: float = 0.0
    updated_at: float = 0.0
    last_validation: dict[str, Any] = field(default_factory=dict)
    last_execution_at: float = 0.0
    last_failure: str = ""
    rollback_target: str = ""
    superseded_by: str = ""
    quarantine_reason: str = ""
    approval_reference: str = ""
    execution_count: int = 0
    failure_count: int = 0
    manifest: dict[str, Any] = field(default_factory=dict)
    source_path: str = ""  # relative package id only, never absolute private path

    def to_public(self) -> dict[str, Any]:
        return {
            "install_id": self.install_id,
            "skill_id": self.skill_id,
            "version": self.version,
            "package_hash": self.package_hash,
            "manifest_hash": self.manifest_hash,
            "lifecycle_state": self.lifecycle_state,
            "trust_state": self.trust_state,
            "health_state": self.health_state,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "enabled_scope": self.enabled_scope,
            "effective": self.effective,
            "registered_at": self.registered_at,
            "updated_at": self.updated_at,
            "last_validation": dict(self.last_validation),
            "last_execution_at": self.last_execution_at,
            "last_failure": self.last_failure,
            "rollback_target": self.rollback_target,
            "superseded_by": self.superseded_by,
            "quarantine_reason": self.quarantine_reason,
            "approval_reference": self.approval_reference,
            "execution_count": self.execution_count,
            "failure_count": self.failure_count,
            "manifest": dict(self.manifest),
            "source_path": self.source_path,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SkillRecord":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass
class SkillExecutionRecord:
    execution_id: str
    skill_id: str
    version: str
    install_id: str
    org_id: str
    workspace_id: str
    state: str = "STARTED"  # STARTED | WAITING_APPROVAL | COMPLETED | FAILED | CANCELLED | REJECTED
    capability: str = ""
    tool_id: str = ""
    approval_reference: str = ""
    worker_id: str = ""
    lease_id: str = ""
    fencing_token: int = 0
    idempotency_key: str = ""
    result_hash: str = ""
    advances_graph: bool = False
    started_at: float = 0.0
    finished_at: float = 0.0
    error: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    execution_path: str = "PlatformAgentRuntime→ExecutionGateway"
    direct_tool_execution: bool = False

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


def content_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
