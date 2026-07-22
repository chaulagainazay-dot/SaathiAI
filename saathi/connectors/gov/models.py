"""M27 — Governed connector models (lifecycle, manifest, results)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class ConnectorLifecycle(str, Enum):
    REGISTERED = "REGISTERED"
    VALIDATED = "VALIDATED"
    READY = "READY"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"
    DRAINING = "DRAINING"
    FAILED = "FAILED"


VALID_LIFECYCLE_TRANSITIONS: dict[ConnectorLifecycle, frozenset[ConnectorLifecycle]] = {
    ConnectorLifecycle.REGISTERED: frozenset({
        ConnectorLifecycle.VALIDATED, ConnectorLifecycle.DISABLED, ConnectorLifecycle.FAILED,
    }),
    ConnectorLifecycle.VALIDATED: frozenset({
        ConnectorLifecycle.READY, ConnectorLifecycle.DEGRADED, ConnectorLifecycle.DISABLED,
        ConnectorLifecycle.FAILED,
    }),
    ConnectorLifecycle.READY: frozenset({
        ConnectorLifecycle.DEGRADED, ConnectorLifecycle.DISABLED, ConnectorLifecycle.DRAINING,
        ConnectorLifecycle.FAILED, ConnectorLifecycle.READY,
    }),
    ConnectorLifecycle.DEGRADED: frozenset({
        ConnectorLifecycle.READY, ConnectorLifecycle.DISABLED, ConnectorLifecycle.DRAINING,
        ConnectorLifecycle.FAILED, ConnectorLifecycle.DEGRADED,
    }),
    ConnectorLifecycle.DISABLED: frozenset({
        ConnectorLifecycle.REGISTERED, ConnectorLifecycle.VALIDATED, ConnectorLifecycle.DISABLED,
    }),
    ConnectorLifecycle.DRAINING: frozenset({
        ConnectorLifecycle.DISABLED, ConnectorLifecycle.READY, ConnectorLifecycle.FAILED,
        ConnectorLifecycle.DRAINING,
    }),
    ConnectorLifecycle.FAILED: frozenset({
        ConnectorLifecycle.REGISTERED, ConnectorLifecycle.DISABLED, ConnectorLifecycle.VALIDATED,
        ConnectorLifecycle.FAILED,
    }),
}


class ConnectorKind(str, Enum):
    HTTP = "http"
    MCP = "mcp"
    BROWSER = "browser"
    LOCAL_TOOL = "local_tool"
    FILESYSTEM = "filesystem"
    CLI = "cli"
    SAAS = "saas"  # future; no live enablement in M27


class AuthMode(str, Enum):
    NONE = "none"
    ENV_VAR = "env_var"
    LOCAL_SECURE = "local_secure"
    FUTURE_SECRET_MANAGER = "future_secret_manager"


@dataclass
class ConnectorManifest:
    """Declarative connector contract — no hidden behavior (M27 + M29 identity).

    M29 adds trust, capability classes, health/readiness, dependencies,
    versioning/deprecation, and explicit side-effect/incident/auth metadata.
    """

    connector_id: str
    version: str = "1"
    kind: ConnectorKind = ConnectorKind.HTTP
    capabilities: tuple[str, ...] = ()  # often operation aliases (M27 compat)
    permissions: tuple[str, ...] = ()
    auth_mode: AuthMode = AuthMode.NONE
    auth_env_names: tuple[str, ...] = ()  # names only — never values
    timeout_seconds: float = 30.0
    max_retries: int = 1
    rate_limit_per_minute: int = 60
    evidence_policy: str = "redacted"  # redacted | metadata_only
    supported_operations: tuple[str, ...] = ()
    allowed_domains: tuple[str, ...] = ()
    denied_domains: tuple[str, ...] = ()
    allowed_operations: tuple[str, ...] = ()
    denied_operations: tuple[str, ...] = ()
    rollout_compatible: tuple[str, ...] = ("OFF", "SHADOW", "CANARY", "ACTIVE", "DRAINING")
    cloud: bool = False
    trading: bool = False
    description: str = ""
    # ── M29 identity / trust ─────────────────────────────────────────────
    display_name: str = ""
    owner: str = "saathi"
    adapter_type: str = ""  # defaults from kind
    trust_level: str = "INTERNAL"
    capability_classes: tuple[str, ...] = ()  # READ, WRITE, HTTP, …
    side_effect_classes: tuple[str, ...] = ()
    required_approvals: tuple[str, ...] = ()
    secret_references: tuple[str, ...] = ()  # names/refs only — never values
    retry_policy: dict[str, Any] = field(default_factory=dict)
    incident_policy: str = "m26"  # m26 | default
    health_policy: dict[str, Any] = field(default_factory=dict)
    readiness_policy: dict[str, Any] = field(default_factory=dict)
    dependencies: tuple[str, ...] = ()
    supported_environments: tuple[str, ...] = ("local", "dev", "test")
    created_at: str = ""
    updated_at: str = ""
    deprecated: bool = False
    deprecated_at: str = ""
    replacement_connector: str = ""
    lifecycle_state: str = ""  # optional declared target; runtime owns actual lifecycle

    def __post_init__(self) -> None:
        if not self.adapter_type:
            self.adapter_type = self.kind.value if isinstance(self.kind, ConnectorKind) else str(self.kind or "http")
        if not self.display_name:
            self.display_name = self.connector_id
        if not self.retry_policy:
            self.retry_policy = {"max_retries": int(self.max_retries)}
        if not self.health_policy:
            self.health_policy = {
                "startup_check": "validate",
                "health_check": "health",
            }
        if not self.readiness_policy:
            self.readiness_policy = {
                "readiness_check": "health",
                "requires_lifecycle": ["READY", "DEGRADED"],
            }
        if not self.supported_operations and self.capabilities:
            self.supported_operations = tuple(self.capabilities)
        if isinstance(self.capability_classes, list):
            self.capability_classes = tuple(self.capability_classes)
        if isinstance(self.dependencies, list):
            self.dependencies = tuple(self.dependencies)
        if isinstance(self.side_effect_classes, list):
            self.side_effect_classes = tuple(self.side_effect_classes)
        if isinstance(self.required_approvals, list):
            self.required_approvals = tuple(self.required_approvals)
        if isinstance(self.secret_references, list):
            self.secret_references = tuple(self.secret_references)
        if isinstance(self.supported_environments, list):
            self.supported_environments = tuple(self.supported_environments)
        if isinstance(self.trust_level, Enum):
            self.trust_level = self.trust_level.value

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["auth_mode"] = self.auth_mode.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConnectorManifest":
        kind = data.get("kind") or data.get("adapter_type") or "http"
        auth = data.get("auth_mode") or "none"
        return cls(
            connector_id=str(data["connector_id"]),
            version=str(data.get("version") or "1"),
            kind=ConnectorKind(kind) if not isinstance(kind, ConnectorKind) else kind,
            capabilities=tuple(data.get("capabilities") or ()),
            permissions=tuple(data.get("permissions") or ()),
            auth_mode=AuthMode(auth) if not isinstance(auth, AuthMode) else auth,
            auth_env_names=tuple(data.get("auth_env_names") or ()),
            timeout_seconds=float(data.get("timeout_seconds") or 30.0),
            max_retries=int(data.get("max_retries") if data.get("max_retries") is not None else 1),
            rate_limit_per_minute=int(data.get("rate_limit_per_minute") or 60),
            evidence_policy=str(data.get("evidence_policy") or "redacted"),
            supported_operations=tuple(data.get("supported_operations") or data.get("capabilities") or ()),
            allowed_domains=tuple(data.get("allowed_domains") or ()),
            denied_domains=tuple(data.get("denied_domains") or ()),
            allowed_operations=tuple(data.get("allowed_operations") or ()),
            denied_operations=tuple(data.get("denied_operations") or ()),
            rollout_compatible=tuple(data.get("rollout_compatible") or ("OFF", "SHADOW", "CANARY", "ACTIVE", "DRAINING")),
            cloud=bool(data.get("cloud")),
            trading=bool(data.get("trading")),
            description=str(data.get("description") or ""),
            display_name=str(data.get("display_name") or ""),
            owner=str(data.get("owner") or "saathi"),
            adapter_type=str(data.get("adapter_type") or ""),
            trust_level=str(data.get("trust_level") or "INTERNAL"),
            capability_classes=tuple(data.get("capability_classes") or ()),
            side_effect_classes=tuple(data.get("side_effect_classes") or ()),
            required_approvals=tuple(data.get("required_approvals") or ()),
            secret_references=tuple(data.get("secret_references") or ()),
            retry_policy=dict(data.get("retry_policy") or {}),
            incident_policy=str(data.get("incident_policy") or "m26"),
            health_policy=dict(data.get("health_policy") or {}),
            readiness_policy=dict(data.get("readiness_policy") or {}),
            dependencies=tuple(data.get("dependencies") or ()),
            supported_environments=tuple(data.get("supported_environments") or ("local", "dev", "test")),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            deprecated=bool(data.get("deprecated")),
            deprecated_at=str(data.get("deprecated_at") or ""),
            replacement_connector=str(data.get("replacement_connector") or ""),
            lifecycle_state=str(data.get("lifecycle_state") or ""),
        )


# M28 caller classes (identity only — never authority)
CALLER_CLASSES = frozenset({
    "mission", "automation", "scheduler", "agent", "api", "cli",
    "control_center", "system_recovery", "test", "connector_framework",
    "compat", "unknown",
})


@dataclass
class ConnectorRequest:
    connector_id: str
    operation: str
    payload: dict[str, Any] = field(default_factory=dict)
    method: str = "GET"  # HTTP
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    caller_id: str = "connector_framework"
    request_id: str = ""
    approval_token: str = ""  # optional explicit approval
    dry_run: bool = False
    # M28 governance fields (secrets never belong here)
    actor_id: str = ""
    caller_class: str = "connector_framework"
    capability: str = ""
    resource_target: str = ""
    idempotency_key: str = ""
    correlation_id: str = ""
    timeout_seconds: float = 0.0
    evidence_classification: str = "redacted"
    # Caller-supplied side_effect_class is IGNORED for policy (recorded only)
    claimed_side_effect_class: str = ""
    # Internal: set only by framework after registry resolve
    _resolved_side_effect_class: str = ""


@dataclass
class ConnectorResult:
    ok: bool
    connector_id: str
    operation: str
    status: str  # success|denied|error|timeout|shadow|draining
    lifecycle: str = ""
    mode: str = "OFF"
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    evidence_id: str = ""
    incident_id: str = ""
    attempts: int = 0
    latency_ms: float = 0.0
    privacy_safe: bool = True
    bypass: bool = False  # always False when framework used
    # M28 stable result contract
    request_id: str = ""
    executed: bool = False
    side_effect_class: str = ""
    approval_state: str = ""  # not_required|required|granted|denied|missing
    policy_state: str = ""  # pass|deny|…
    rollout_state: str = ""
    idempotency_state: str = ""  # new|replay|conflict|none
    safe_output: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    error_code: str = ""
    safe_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConnectorRecord:
    manifest: ConnectorManifest
    lifecycle: ConnectorLifecycle = ConnectorLifecycle.REGISTERED
    validated: bool = False
    last_error: str = ""
    request_count: int = 0
    failure_count: int = 0
    last_request_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "lifecycle": self.lifecycle.value,
            "validated": self.validated,
            "last_error": self.last_error,
            "request_count": self.request_count,
            "failure_count": self.failure_count,
            "last_request_at": self.last_request_at,
        }


CONNECTOR_INCIDENT_TYPES = frozenset({
    "auth_failure",
    "timeout",
    "invalid_response",
    "schema_violation",
    "rate_limit",
    "unavailable",
    "policy_violation",
    "permission_denied",
    # M28
    "connector_bypass_attempt",
    "approval_mismatch",
    "legacy_path_blocked",
    "intent_validation_failed",
    "adapter_direct_access",
    "idempotency_conflict",
    "unauthorized_caller",
})

FORBIDDEN_PAYLOAD_KEYS = frozenset({
    "api_key", "authorization", "password", "secret", "token", "cookie",
    "access_token", "refresh_token", "private_key", "credential", "bearer",
})
