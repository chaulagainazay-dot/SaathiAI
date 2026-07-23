"""M50 platform execution context — required identity chain for every run.

Anonymous execution is prohibited. Context feeds M49 ExecutionGateway via
requested_by + ToolApprovalReference; it does not replace the gateway.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from saathi.platform.models import PlatformPermission, PlatformRole, role_has_permission


class PlatformContextError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class PlatformExecutionContext:
    """Full identity chain required for platform-governed execution."""

    user_id: str
    role: str
    org_id: str
    workspace_id: str
    project_id: str = ""
    mission_id: str = ""
    run_id: str = ""
    session_id: str = ""
    approval_id: str = ""
    authority: str = ""

    def validate(self) -> None:
        if not self.user_id:
            raise PlatformContextError("ANONYMOUS_PROHIBITED", "user_id required")
        if not self.org_id:
            raise PlatformContextError("ORG_REQUIRED", "org_id required")
        if not self.workspace_id:
            raise PlatformContextError("WORKSPACE_REQUIRED", "workspace_id required")
        if not self.role:
            raise PlatformContextError("ROLE_REQUIRED", "role required")
        try:
            PlatformRole(self.role)
        except ValueError as exc:
            raise PlatformContextError("ROLE_INVALID", f"unknown role: {self.role}") from exc

    def require_permission(self, perm: PlatformPermission | str) -> None:
        self.validate()
        if not role_has_permission(self.role, perm):
            raise PlatformContextError(
                "PERMISSION_DENIED",
                f"role {self.role} lacks {perm}",
            )

    def requested_by(self) -> str:
        return f"user:{self.user_id}"

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "role": self.role,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "mission_id": self.mission_id,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "approval_id": self.approval_id,
            "authority": self.authority,
        }
