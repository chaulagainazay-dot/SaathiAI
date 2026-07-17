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
    """Declarative connector contract — no hidden behavior."""

    connector_id: str
    version: str = "1"
    kind: ConnectorKind = ConnectorKind.HTTP
    capabilities: tuple[str, ...] = ()
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

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["auth_mode"] = self.auth_mode.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConnectorManifest":
        kind = data.get("kind") or "http"
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
        )


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
})

FORBIDDEN_PAYLOAD_KEYS = frozenset({
    "api_key", "authorization", "password", "secret", "token", "cookie",
    "access_token", "refresh_token", "private_key", "credential", "bearer",
})
