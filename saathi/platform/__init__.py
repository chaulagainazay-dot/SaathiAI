"""M50 Platform Foundation — identity, RBAC, workspace, project, mission, approvals.

Built on top of the M49 tool runtime. Does not redesign ExecutionGateway,
ToolExecutionService, ToolRegistry, or durable idempotency.

Public entry:
    from saathi.platform import PlatformService, default_platform
    svc = default_platform()
    ctx = svc.require_context(session_token=...)
    result = svc.execute_tool(ctx, tool_id=..., arguments=..., approval_id=...)
"""
from __future__ import annotations

from saathi.platform.models import (
    ApprovalStatus,
    MembershipRole,
    PlatformRole,
    PlatformPermission,
)
from saathi.platform.service import PlatformService, default_platform, reset_platform_for_tests
from saathi.platform.context import PlatformExecutionContext
# M51 private-alpha methods
import saathi.platform.alpha  # noqa: F401

__all__ = [
    "PlatformService",
    "default_platform",
    "reset_platform_for_tests",
    "PlatformExecutionContext",
    "PlatformRole",
    "PlatformPermission",
    "MembershipRole",
    "ApprovalStatus",
]
