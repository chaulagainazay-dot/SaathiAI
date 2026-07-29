"""Access policy for knowledge read/search/ingest operations."""
from __future__ import annotations

from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformPermission


class KnowledgeAccessPolicy:
    """RBAC + tenant/workspace gating for the knowledge runtime."""

    def require_read(self, ctx) -> None:
        ctx.require_permission(PlatformPermission.KNOWLEDGE_READ)

    def require_search(self, ctx) -> None:
        # search implies read
        if hasattr(ctx, "require_permission"):
            try:
                ctx.require_permission(PlatformPermission.KNOWLEDGE_SEARCH)
                return
            except PlatformContextError:
                # fall back to read for viewers granted only knowledge.read
                ctx.require_permission(PlatformPermission.KNOWLEDGE_READ)

    def require_ingest(self, ctx) -> None:
        ctx.require_permission(PlatformPermission.KNOWLEDGE_INGEST)

    def require_reindex(self, ctx) -> None:
        ctx.require_permission(PlatformPermission.KNOWLEDGE_REINDEX)

    def require_admin(self, ctx) -> None:
        ctx.require_permission(PlatformPermission.KNOWLEDGE_ADMIN)

    def tenant_id(self, ctx) -> str:
        return getattr(ctx, "org_id", None) or "platform"

    def workspace_id(self, ctx) -> str:
        return getattr(ctx, "workspace_id", None) or ""

    def allow_restricted(self, ctx) -> bool:
        try:
            return bool(
                ctx
                and (
                    getattr(ctx, "role", "") in {"owner", "admin", "system"}
                    or PlatformPermission.KNOWLEDGE_ADMIN.value
                    in getattr(ctx, "permissions", set())
                )
            )
        except Exception:
            return False

    def assert_session_active(self, ctx) -> None:
        """Revoked/missing identity chain fails closed."""
        if not getattr(ctx, "user_id", None):
            raise PlatformContextError("ANONYMOUS_PROHIBITED", "user_id required")
        if not getattr(ctx, "org_id", None):
            raise PlatformContextError("ORG_REQUIRED", "org_id required")
        if not getattr(ctx, "workspace_id", None):
            raise PlatformContextError("WORKSPACE_REQUIRED", "workspace_id required")
