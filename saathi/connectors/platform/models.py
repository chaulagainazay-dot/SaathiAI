"""M15 Universal Connector Platform — canonical models.

One typed, versioned connector + tool model, a provider-neutral capability
catalog, the normalized result envelope, the risk model, and the connection
lifecycle state machine. Business logic consumes ONLY the normalized envelope,
never raw provider responses. Secrets are referenced, never stored here.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


# ── risk model (maps onto gateway RiskLevel L0–L4) ──────────────────────────
class RiskClass(int, Enum):
    LOCAL_READ = 0        # inspect metadata, registry lookup, health
    EXTERNAL_READ = 1     # search email, list events, inspect repo
    REVERSIBLE_MUTATION = 2   # draft email, create branch, create local file
    EXTERNAL_SIDE_EFFECT = 3  # send email, publish, push, create event, deploy staging
    HIGH_IMPACT = 4       # prod deploy/delete, credential rotation, transfer, trade


def to_gateway_risk(rc: RiskClass) -> str:
    return {0: "L0", 1: "L1", 2: "L2", 3: "L3", 4: "L4"}[int(rc)]


APPROVAL_THRESHOLD = RiskClass.EXTERNAL_SIDE_EFFECT   # risk >= 3 needs approval
MANUAL_ONLY = RiskClass.HIGH_IMPACT                    # risk 4 manual-only


class MutationClass(str, Enum):
    NONE = "none"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"


# ── connection lifecycle ────────────────────────────────────────────────────
class ConnState(str, Enum):
    UNCONFIGURED = "unconfigured"
    CONFIGURED = "configured"
    AUTHORIZATION_PENDING = "authorization_pending"
    CONNECTED = "connected"
    HEALTHY = "healthy"
    DISCONNECTED = "disconnected"
    EXPIRED = "expired"
    UNAUTHORIZED = "unauthorized"
    DEGRADED = "degraded"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    ERROR = "error"


_EXECUTABLE_STATES = {ConnState.CONNECTED, ConnState.HEALTHY, ConnState.DEGRADED}

_TRANSITIONS: dict[ConnState, set[ConnState]] = {
    ConnState.UNCONFIGURED: {ConnState.CONFIGURED, ConnState.DISABLED},
    ConnState.CONFIGURED: {ConnState.AUTHORIZATION_PENDING, ConnState.CONNECTED,
                           ConnState.UNAUTHORIZED, ConnState.DISABLED, ConnState.ERROR},
    ConnState.AUTHORIZATION_PENDING: {ConnState.CONNECTED, ConnState.UNAUTHORIZED,
                                      ConnState.ERROR, ConnState.DISCONNECTED},
    ConnState.CONNECTED: {ConnState.HEALTHY, ConnState.DEGRADED, ConnState.EXPIRED,
                          ConnState.RATE_LIMITED, ConnState.UNAVAILABLE,
                          ConnState.DISCONNECTED, ConnState.DISABLED, ConnState.ERROR},
    ConnState.HEALTHY: {ConnState.DEGRADED, ConnState.EXPIRED, ConnState.RATE_LIMITED,
                        ConnState.UNAVAILABLE, ConnState.DISCONNECTED, ConnState.DISABLED,
                        ConnState.CONNECTED, ConnState.ERROR},
    ConnState.DEGRADED: {ConnState.HEALTHY, ConnState.CONNECTED, ConnState.UNAVAILABLE,
                         ConnState.DISCONNECTED, ConnState.DISABLED, ConnState.ERROR},
    ConnState.RATE_LIMITED: {ConnState.HEALTHY, ConnState.CONNECTED, ConnState.DEGRADED},
    ConnState.EXPIRED: {ConnState.AUTHORIZATION_PENDING, ConnState.CONNECTED,
                        ConnState.DISCONNECTED, ConnState.DISABLED},
    ConnState.UNAUTHORIZED: {ConnState.AUTHORIZATION_PENDING, ConnState.DISCONNECTED,
                             ConnState.DISABLED},
    ConnState.UNAVAILABLE: {ConnState.HEALTHY, ConnState.CONNECTED, ConnState.DISCONNECTED,
                            ConnState.DISABLED, ConnState.ERROR},
    ConnState.DISCONNECTED: {ConnState.CONFIGURED, ConnState.AUTHORIZATION_PENDING,
                             ConnState.DISABLED},
    ConnState.DISABLED: {ConnState.UNCONFIGURED, ConnState.CONFIGURED},
    ConnState.ERROR: {ConnState.CONFIGURED, ConnState.DISCONNECTED, ConnState.DISABLED},
}


class IllegalConnTransition(Exception):
    pass


def validate_conn_transition(src: ConnState, dst: ConnState) -> None:
    if dst not in _TRANSITIONS.get(src, set()):
        raise IllegalConnTransition(f"illegal connection transition {src.value} → {dst.value}")


def is_executable(state: ConnState) -> bool:
    return state in _EXECUTABLE_STATES


# ── definitions ─────────────────────────────────────────────────────────────
@dataclass
class ToolDef:
    tool_id: str
    connector_id: str
    capability_id: str
    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    risk_class: RiskClass = RiskClass.LOCAL_READ
    mutation_class: MutationClass = MutationClass.NONE
    requires_approval: bool = False
    idempotent: bool = True
    timeout_sec: float = 30.0
    rate_limit_bucket: str = ""
    required_scopes: list[str] = field(default_factory=list)
    reversible: bool = True
    dry_run: bool = False
    deterministic_adapter: bool = True
    enabled: bool = True
    version: int = 1

    def __post_init__(self):
        # a connector/tool can NEVER downgrade below the approval threshold:
        # risk >= EXTERNAL_SIDE_EFFECT always requires approval
        if int(self.risk_class) >= int(APPROVAL_THRESHOLD):
            self.requires_approval = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["risk_class"] = int(self.risk_class)
        d["mutation_class"] = self.mutation_class.value
        return d


@dataclass
class ConnectorDef:
    connector_id: str
    provider: str
    display_name: str
    category: str
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    auth_type: str = "none"       # none | api_key | oauth | token | local
    required_credentials: list[str] = field(default_factory=list)
    optional_credentials: list[str] = field(default_factory=list)
    account_scopes: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    risk_ceiling: RiskClass = RiskClass.EXTERNAL_READ
    retry_policy: str = "transient-only"
    timeout_sec: float = 30.0
    rate_limit_policy: str = "default"
    health_strategy: str = "ping"
    webhook_support: bool = False
    polling_support: bool = False
    sync_support: bool = False
    local: bool = True
    config_schema: dict = field(default_factory=dict)
    version: int = 1
    adapter_version: int = 1
    status: str = "active"
    # honesty label: live-tested | deterministic-adapter-tested | contract-ready |
    # unavailable | environment-blocked
    integration_status: str = "deterministic-adapter-tested"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["risk_ceiling"] = int(self.risk_ceiling)
        return d


# ── normalized result envelope ──────────────────────────────────────────────
def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class ToolResult:
    status: str                    # success|partial|failed|blocked|approval_required|uncertain
    connector_id: str = ""
    tool_id: str = ""
    capability_id: str = ""
    execution_id: str = ""
    started_at: str = ""
    completed_at: str = ""
    data: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    retryable: bool = False
    external_reference: Optional[str] = None
    rate_limit: Optional[dict] = None
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def normalized_input_hash(tool_id: str, account_id: str, args: dict) -> str:
    """Stable hash binding an approval to the EXACT action (tool+account+input)."""
    basis = json.dumps({"tool": tool_id, "account": account_id, "args": args},
                       sort_keys=True, default=str)
    return hashlib.sha256(basis.encode()).hexdigest()[:24]
