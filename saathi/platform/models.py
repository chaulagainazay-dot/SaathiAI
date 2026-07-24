"""M50 platform domain models — identity, RBAC, tenancy, approvals.

Fail-closed enums. Callers cannot invent roles or permissions outside these sets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import time
import uuid


class PlatformRole(str, Enum):
    """Canonical platform roles (M50)."""

    VIEWER = "viewer"
    OPERATOR = "operator"
    OWNER = "owner"
    ADMIN = "admin"
    SYSTEM = "system"


class MembershipRole(str, Enum):
    """Role within an organization/workspace membership."""

    VIEWER = "viewer"
    OPERATOR = "operator"
    OWNER = "owner"
    ADMIN = "admin"


class PlatformPermission(str, Enum):
    PLATFORM_READ = "platform.read"
    PLATFORM_WRITE = "platform.write"
    ORG_MANAGE = "org.manage"
    USER_MANAGE = "user.manage"
    WORKSPACE_READ = "workspace.read"
    WORKSPACE_WRITE = "workspace.write"
    PROJECT_READ = "project.read"
    PROJECT_WRITE = "project.write"
    PROJECT_CREATE = "project.create"
    MISSION_READ = "mission.read"
    MISSION_WRITE = "mission.write"
    MISSION_RUN = "mission.run"
    APPROVAL_REQUEST = "approval.request"
    APPROVAL_DECIDE = "approval.decide"
    APPROVAL_READ = "approval.read"
    SETTINGS_READ = "settings.read"
    SETTINGS_WRITE = "settings.write"
    CONNECTOR_READ = "connector.read"
    CONNECTOR_LINK = "connector.link"
    AUDIT_READ = "audit.read"
    RUNTIME_EXECUTE = "runtime.execute"
    SESSION_MANAGE = "session.manage"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"
    CONSUMED = "consumed"


class PlatformExecutionState(str, Enum):
    """Externally meaningful M52 platform-agent lifecycle states."""

    CREATED = "CREATED"
    QUEUED = "QUEUED"
    READY = "READY"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


PLATFORM_EXECUTION_TERMINAL_STATES = frozenset(
    {
        PlatformExecutionState.COMPLETED,
        PlatformExecutionState.FAILED,
        PlatformExecutionState.CANCELLED,
        PlatformExecutionState.TIMED_OUT,
    }
)


PLATFORM_EXECUTION_TRANSITIONS: dict[
    PlatformExecutionState, frozenset[PlatformExecutionState]
] = {
    PlatformExecutionState.CREATED: frozenset(
        {
            PlatformExecutionState.QUEUED,
            PlatformExecutionState.CANCELLED,
            PlatformExecutionState.TIMED_OUT,
            PlatformExecutionState.FAILED,
            PlatformExecutionState.RECOVERING,
        }
    ),
    PlatformExecutionState.QUEUED: frozenset(
        {
            PlatformExecutionState.READY,
            PlatformExecutionState.WAITING_APPROVAL,
            PlatformExecutionState.CANCELLED,
            PlatformExecutionState.TIMED_OUT,
            PlatformExecutionState.FAILED,
            PlatformExecutionState.RECOVERING,
        }
    ),
    PlatformExecutionState.READY: frozenset(
        {
            PlatformExecutionState.RUNNING,
            PlatformExecutionState.CANCELLED,
            PlatformExecutionState.TIMED_OUT,
            PlatformExecutionState.RECOVERING,
            PlatformExecutionState.FAILED,
        }
    ),
    PlatformExecutionState.WAITING_APPROVAL: frozenset(
        {
            PlatformExecutionState.READY,
            PlatformExecutionState.CANCELLED,
            PlatformExecutionState.TIMED_OUT,
            PlatformExecutionState.FAILED,
        }
    ),
    PlatformExecutionState.RUNNING: frozenset(
        {
            PlatformExecutionState.COMPLETED,
            PlatformExecutionState.FAILED,
            PlatformExecutionState.CANCELLED,
            PlatformExecutionState.TIMED_OUT,
            PlatformExecutionState.PAUSED,
            PlatformExecutionState.RECOVERING,
        }
    ),
    PlatformExecutionState.PAUSED: frozenset(
        {
            PlatformExecutionState.READY,
            PlatformExecutionState.CANCELLED,
            PlatformExecutionState.TIMED_OUT,
            PlatformExecutionState.RECOVERING,
        }
    ),
    PlatformExecutionState.RECOVERING: frozenset(
        {
            PlatformExecutionState.READY,
            PlatformExecutionState.PAUSED,
            PlatformExecutionState.FAILED,
            PlatformExecutionState.CANCELLED,
            PlatformExecutionState.TIMED_OUT,
        }
    ),
    PlatformExecutionState.COMPLETED: frozenset(),
    PlatformExecutionState.FAILED: frozenset(),
    PlatformExecutionState.CANCELLED: frozenset(),
    PlatformExecutionState.TIMED_OUT: frozenset(),
}


# Role → permission sets (inheritance: higher roles include lower)
ROLE_PERMISSIONS: dict[PlatformRole, frozenset[PlatformPermission]] = {
    PlatformRole.VIEWER: frozenset(
        {
            PlatformPermission.PLATFORM_READ,
            PlatformPermission.WORKSPACE_READ,
            PlatformPermission.PROJECT_READ,
            PlatformPermission.MISSION_READ,
            PlatformPermission.APPROVAL_READ,
            PlatformPermission.SETTINGS_READ,
            PlatformPermission.CONNECTOR_READ,
            PlatformPermission.AUDIT_READ,
        }
    ),
    PlatformRole.OPERATOR: frozenset(),  # filled below
    PlatformRole.OWNER: frozenset(),
    PlatformRole.ADMIN: frozenset(),
    PlatformRole.SYSTEM: frozenset(PlatformPermission),
}

ROLE_PERMISSIONS[PlatformRole.OPERATOR] = ROLE_PERMISSIONS[PlatformRole.VIEWER] | frozenset(
    {
        PlatformPermission.PLATFORM_WRITE,
        PlatformPermission.WORKSPACE_WRITE,
        PlatformPermission.PROJECT_WRITE,
        PlatformPermission.PROJECT_CREATE,
        PlatformPermission.MISSION_WRITE,
        PlatformPermission.MISSION_RUN,
        PlatformPermission.APPROVAL_REQUEST,
        PlatformPermission.CONNECTOR_LINK,
        PlatformPermission.RUNTIME_EXECUTE,
        PlatformPermission.SESSION_MANAGE,
    }
)
ROLE_PERMISSIONS[PlatformRole.OWNER] = ROLE_PERMISSIONS[PlatformRole.OPERATOR] | frozenset(
    {
        PlatformPermission.APPROVAL_DECIDE,
        PlatformPermission.SETTINGS_WRITE,
        PlatformPermission.ORG_MANAGE,
        PlatformPermission.USER_MANAGE,
    }
)
ROLE_PERMISSIONS[PlatformRole.ADMIN] = ROLE_PERMISSIONS[PlatformRole.OWNER] | frozenset(
    {
        PlatformPermission.PLATFORM_WRITE,
    }
)


def permissions_for_role(role: PlatformRole | str) -> frozenset[PlatformPermission]:
    r = PlatformRole(role) if not isinstance(role, PlatformRole) else role
    return ROLE_PERMISSIONS.get(r, frozenset())


def role_has_permission(role: PlatformRole | str, perm: PlatformPermission | str) -> bool:
    p = PlatformPermission(perm) if not isinstance(perm, PlatformPermission) else perm
    return p in permissions_for_role(role)


@dataclass
class UserRecord:
    user_id: str
    email: str = ""
    name: str = ""
    status: str = "active"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_public(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "name": self.name,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass
class SessionRecord:
    session_id: str
    user_id: str
    token_hash: str
    org_id: str = ""
    workspace_id: str = ""
    role: str = PlatformRole.VIEWER.value
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    expires_at: float = 0.0
    revoked: bool = False
    label: str = ""
    # M51 session hardening
    auth_method: str = ""
    idle_expires_at: float = 0.0
    revoked_at: float = 0.0
    revocation_reason: str = ""
    session_version: int = 1
    ua_hash: str = ""
    absolute_expires_at: float = 0.0

    def is_active(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        if self.revoked:
            return False
        abs_exp = self.absolute_expires_at or self.expires_at
        if abs_exp and abs_exp < now:
            return False
        if self.idle_expires_at and self.idle_expires_at < now:
            return False
        if self.expires_at and self.expires_at < now:
            return False
        return True


@dataclass
class OrganizationRecord:
    org_id: str
    name: str
    owner_id: str
    created_at: float = field(default_factory=time.time)
    status: str = "active"

    def to_public(self) -> dict[str, Any]:
        return {
            "org_id": self.org_id,
            "name": self.name,
            "owner_id": self.owner_id,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass
class WorkspaceRecord:
    workspace_id: str
    org_id: str
    name: str
    created_by: str
    created_at: float = field(default_factory=time.time)
    status: str = "active"

    def to_public(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "org_id": self.org_id,
            "name": self.name,
            "created_by": self.created_by,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass
class ProjectRecord:
    project_id: str
    workspace_id: str
    org_id: str
    name: str
    owner_id: str
    mission_key: str = ""
    status: str = "active"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_public(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "workspace_id": self.workspace_id,
            "org_id": self.org_id,
            "name": self.name,
            "owner_id": self.owner_id,
            "mission_key": self.mission_key,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class MissionLinkRecord:
    """Platform-scoped mission link (does not replace MissionStore)."""

    mission_id: str
    project_id: str
    org_id: str
    workspace_id: str
    key: str
    name: str
    owner_id: str
    status: str = "active"
    created_at: float = field(default_factory=time.time)

    def to_public(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "project_id": self.project_id,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "key": self.key,
            "name": self.name,
            "owner_id": self.owner_id,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass
class ApprovalRecord:
    approval_id: str
    user_id: str
    org_id: str
    workspace_id: str
    project_id: str
    mission_id: str
    tool_id: str
    action: str
    target_resource: str
    authority: str
    side_effect_class: str
    capability: str = ""
    status: str = ApprovalStatus.PENDING.value
    requested_by: str = ""
    decided_by: str = ""
    reason: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    decided_at: float = 0.0
    consumed_at: float = 0.0
    run_id: str = ""
    tool_version: str = ""
    connector: str = ""

    def to_public(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "user_id": self.user_id,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "mission_id": self.mission_id,
            "tool_id": self.tool_id,
            "action": self.action,
            "target_resource": self.target_resource,
            "authority": self.authority,
            "side_effect_class": self.side_effect_class,
            "capability": self.capability,
            "status": self.status,
            "requested_by": self.requested_by,
            "decided_by": self.decided_by,
            "reason": self.reason,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "decided_at": self.decided_at,
            "consumed_at": self.consumed_at,
            "run_id": self.run_id,
            "connector": self.connector,
        }


@dataclass
class PlatformExecutionRecord:
    """Durable orchestration metadata; tool idempotency remains M49 authority."""

    execution_id: str
    state: str
    user_id: str
    session_id: str
    org_id: str
    workspace_id: str
    project_id: str
    mission_id: str
    agent_id: str
    run_id: str
    tool_id: str
    request_fingerprint: str
    arguments_json: str = "{}"
    capability: str = ""
    idempotency_key: str = ""
    approval_id: str = ""
    authority: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    deadline_at: float = 0.0
    cancel_requested: bool = False
    dispatch_started: bool = False
    adapter_invoked: bool = False
    result_json: str = ""
    error_code: str = ""
    recovery_count: int = 0
    version: int = 1

    def is_terminal(self) -> bool:
        return PlatformExecutionState(self.state) in PLATFORM_EXECUTION_TERMINAL_STATES

    def to_public(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "state": self.state,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "mission_id": self.mission_id,
            "agent_id": self.agent_id,
            "run_id": self.run_id,
            "tool_id": self.tool_id,
            "capability": self.capability,
            "approval_id": self.approval_id,
            "authority": self.authority,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deadline_at": self.deadline_at,
            "cancel_requested": self.cancel_requested,
            "dispatch_started": self.dispatch_started,
            "adapter_invoked": self.adapter_invoked,
            "error_code": self.error_code,
            "recovery_count": self.recovery_count,
        }


def new_id(prefix: str = "") -> str:
    body = uuid.uuid4().hex[:16]
    return f"{prefix}{body}" if prefix else body
