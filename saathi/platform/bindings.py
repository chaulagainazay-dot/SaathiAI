"""M53 durable platform-agent binding administration.

This module extends the M51/M52 binding adapter. It reuses platform RBAC,
tenancy, audit, and the existing SQLite store; it is not an agent identity or
execution system of its own.
"""
from __future__ import annotations

import json
import re
from typing import Any

from saathi.platform.context import PlatformContextError, PlatformExecutionContext
from saathi.platform.models import (
    PlatformAgentBindingRecord,
    PlatformAgentBindingState,
    PlatformPermission,
    PlatformRole,
    new_id,
)
from saathi.tool_runtime.contracts import ToolAuthorityClass

SAFE_AUTHORITY_ORDER = {
    ToolAuthorityClass.READ_ONLY.value: 0,
    ToolAuthorityClass.LOCAL_MUTATION.value: 1,
    ToolAuthorityClass.EXTERNAL_MUTATION.value: 2,
    ToolAuthorityClass.SECURITY_SENSITIVE.value: 3,
}

ROLE_AUTHORITY_CEILING = {
    PlatformRole.VIEWER.value: ToolAuthorityClass.READ_ONLY.value,
    PlatformRole.OPERATOR.value: ToolAuthorityClass.LOCAL_MUTATION.value,
    PlatformRole.OWNER.value: ToolAuthorityClass.EXTERNAL_MUTATION.value,
    PlatformRole.ADMIN.value: ToolAuthorityClass.SECURITY_SENSITIVE.value,
    PlatformRole.SYSTEM.value: ToolAuthorityClass.SECURITY_SENSITIVE.value,
}

_AGENT_ID = re.compile(r"^[a-z][a-z0-9._-]{2,63}$")


def authority_allows(ceiling: str, requested: str) -> bool:
    if ceiling not in SAFE_AUTHORITY_ORDER or requested not in SAFE_AUTHORITY_ORDER:
        return False
    return SAFE_AUTHORITY_ORDER[requested] <= SAFE_AUTHORITY_ORDER[ceiling]


def ensure_default_binding(platform, org_id: str, workspace_id: str, creator_id: str):
    """Seed the M52 compatibility identity without granting financial authority."""
    existing = platform.store.find_agent_binding(
        org_id=org_id,
        workspace_id=workspace_id,
        agent_id="platform-agent",
    )
    if existing:
        return existing
    now = platform.store._now()
    record = PlatformAgentBindingRecord(
        binding_id=new_id("bind_"),
        agent_id="platform-agent",
        name="Default platform agent",
        description="M52 compatibility binding; gateway authority remains authoritative.",
        org_id=org_id,
        workspace_id=workspace_id,
        allowed_tools_json="[]",
        allowed_capabilities_json="[]",
        authority_ceiling=ToolAuthorityClass.SECURITY_SENSITIVE.value,
        state=PlatformAgentBindingState.ACTIVE.value,
        version=1,
        created_by=creator_id or "system:bootstrap",
        updated_by=creator_id or "system:bootstrap",
        created_at=now,
        updated_at=now,
    )
    try:
        return platform.store.create_agent_binding(record)
    except ValueError:
        found = platform.store.find_agent_binding(
            org_id=org_id,
            workspace_id=workspace_id,
            agent_id="platform-agent",
        )
        if not found:
            raise
        return found


class BindingAdministrationService:
    """Tenant-scoped binding lifecycle and policy administration."""

    def __init__(self, platform=None):
        if platform is None:
            from saathi.platform.service import default_platform

            platform = default_platform()
        self.platform = platform
        self.store = platform.store

    def create(
        self,
        ctx: PlatformExecutionContext,
        *,
        agent_id: str,
        name: str,
        description: str = "",
        workspace_id: str = "",
        project_id: str = "",
        mission_id: str = "",
        allowed_tools: list[str] | None = None,
        allowed_capabilities: list[str] | None = None,
        authority_ceiling: str = ToolAuthorityClass.READ_ONLY.value,
    ) -> PlatformAgentBindingRecord:
        ctx.require_permission(PlatformPermission.AGENT_BINDING_MANAGE)
        target_workspace = workspace_id or ctx.workspace_id
        self._validate_scope(
            ctx,
            workspace_id=target_workspace,
            project_id=project_id,
            mission_id=mission_id,
        )
        if not _AGENT_ID.fullmatch(agent_id or ""):
            self._reject(ctx, "BINDING_IDENTITY_INVALID")
            raise PlatformContextError(
                "BINDING_IDENTITY_INVALID", "agent_id must be a stable slug"
            )
        if not name.strip():
            raise PlatformContextError("BINDING_NAME_REQUIRED", "binding name required")
        tools = self._validate_tools(allowed_tools or [])
        capabilities = self._normalize_values(allowed_capabilities or [])
        self._validate_authority_ceiling(ctx, authority_ceiling)
        now = self.store._now()
        record = PlatformAgentBindingRecord(
            binding_id=new_id("bind_"),
            agent_id=agent_id,
            name=name.strip()[:120],
            description=description.strip()[:500],
            org_id=ctx.org_id,
            workspace_id=target_workspace,
            project_id=project_id,
            mission_id=mission_id,
            allowed_tools_json=json.dumps(tools, separators=(",", ":")),
            allowed_capabilities_json=json.dumps(
                capabilities, separators=(",", ":")
            ),
            authority_ceiling=authority_ceiling,
            state=PlatformAgentBindingState.ACTIVE.value,
            version=1,
            created_by=ctx.user_id,
            updated_by=ctx.user_id,
            created_at=now,
            updated_at=now,
        )
        try:
            created = self.store.create_agent_binding(record)
        except ValueError as exc:
            self._reject(ctx, "BINDING_IDENTITY_EXISTS")
            raise PlatformContextError(
                "BINDING_IDENTITY_EXISTS",
                "agent identity already exists in workspace",
            ) from exc
        self._audit("binding.created", ctx, created)
        return created

    def list(
        self,
        ctx: PlatformExecutionContext,
        *,
        state: str = "",
        limit: int = 200,
    ) -> list[PlatformAgentBindingRecord]:
        ctx.require_permission(PlatformPermission.AGENT_BINDING_READ)
        if state:
            try:
                state = PlatformAgentBindingState(state).value
            except ValueError as exc:
                raise PlatformContextError(
                    "BINDING_STATE_INVALID", "unknown binding state"
                ) from exc
        return self.store.list_agent_bindings(
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
            state=state,
            limit=limit,
        )

    def inspect(
        self, ctx: PlatformExecutionContext, binding_id: str
    ) -> PlatformAgentBindingRecord:
        ctx.require_permission(PlatformPermission.AGENT_BINDING_READ)
        return self._scoped(ctx, binding_id)

    def update(
        self,
        ctx: PlatformExecutionContext,
        binding_id: str,
        updates: dict[str, Any],
    ) -> PlatformAgentBindingRecord:
        ctx.require_permission(PlatformPermission.AGENT_BINDING_MANAGE)
        current = self._scoped(ctx, binding_id)
        if current.state == PlatformAgentBindingState.REVOKED.value:
            raise PlatformContextError("BINDING_REVOKED", "revoked binding is immutable")
        allowed = {
            "name",
            "description",
            "project_id",
            "mission_id",
            "allowed_tools",
            "allowed_capabilities",
            "authority_ceiling",
        }
        unknown = set(updates) - allowed
        if unknown:
            raise PlatformContextError(
                "BINDING_UPDATE_UNSUPPORTED", "unsupported binding update"
            )
        store_updates: dict[str, Any] = {}
        security_change = False
        if "name" in updates:
            value = str(updates["name"]).strip()
            if not value:
                raise PlatformContextError(
                    "BINDING_NAME_REQUIRED", "binding name required"
                )
            store_updates["name"] = value[:120]
        if "description" in updates:
            store_updates["description"] = str(updates["description"]).strip()[:500]
        project_id = str(updates.get("project_id", current.project_id) or "")
        mission_id = str(updates.get("mission_id", current.mission_id) or "")
        if "project_id" in updates or "mission_id" in updates:
            self._validate_scope(
                ctx,
                workspace_id=current.workspace_id,
                project_id=project_id,
                mission_id=mission_id,
            )
            store_updates.update(project_id=project_id, mission_id=mission_id)
            security_change = True
        if "allowed_tools" in updates:
            store_updates["allowed_tools_json"] = json.dumps(
                self._validate_tools(list(updates["allowed_tools"] or [])),
                separators=(",", ":"),
            )
            security_change = True
        if "allowed_capabilities" in updates:
            store_updates["allowed_capabilities_json"] = json.dumps(
                self._normalize_values(
                    list(updates["allowed_capabilities"] or [])
                ),
                separators=(",", ":"),
            )
            security_change = True
        if "authority_ceiling" in updates:
            ceiling = str(updates["authority_ceiling"])
            self._validate_authority_ceiling(ctx, ceiling)
            store_updates["authority_ceiling"] = ceiling
            security_change = True
        updated = self.store.update_agent_binding(
            binding_id,
            updates=store_updates,
            updated_by=ctx.user_id,
            bump_version=security_change,
        )
        self._audit("binding.updated", ctx, updated)
        return updated

    def suspend(
        self, ctx: PlatformExecutionContext, binding_id: str
    ) -> PlatformAgentBindingRecord:
        return self._transition(
            ctx,
            binding_id,
            target=PlatformAgentBindingState.SUSPENDED,
            event="binding.suspended",
        )

    def activate(
        self, ctx: PlatformExecutionContext, binding_id: str
    ) -> PlatformAgentBindingRecord:
        return self._transition(
            ctx,
            binding_id,
            target=PlatformAgentBindingState.ACTIVE,
            event="binding.activated",
        )

    def revoke(
        self, ctx: PlatformExecutionContext, binding_id: str
    ) -> PlatformAgentBindingRecord:
        return self._transition(
            ctx,
            binding_id,
            target=PlatformAgentBindingState.REVOKED,
            event="binding.revoked",
        )

    def rotate(
        self, ctx: PlatformExecutionContext, binding_id: str
    ) -> PlatformAgentBindingRecord:
        ctx.require_permission(PlatformPermission.AGENT_BINDING_MANAGE)
        current = self._scoped(ctx, binding_id)
        if current.state == PlatformAgentBindingState.REVOKED.value:
            raise PlatformContextError("BINDING_REVOKED", "revoked binding is immutable")
        updated = self.store.update_agent_binding(
            binding_id,
            updates={},
            updated_by=ctx.user_id,
            bump_version=True,
        )
        self._audit("binding.rotated", ctx, updated)
        return updated

    def resolve_for_execution(
        self,
        ctx: PlatformExecutionContext,
        *,
        binding_id: str = "",
        agent_id: str = "platform-agent",
        binding_version: int | None = None,
    ) -> PlatformAgentBindingRecord:
        ctx.require_permission(PlatformPermission.AGENT_BINDING_USE)
        record = (
            self.store.get_agent_binding(binding_id)
            if binding_id
            else self.store.find_agent_binding(
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                agent_id=agent_id,
            )
        )
        if (
            not record
            and agent_id == "platform-agent"
            and ctx.role in {PlatformRole.OWNER.value, PlatformRole.ADMIN.value}
        ):
            record = ensure_default_binding(
                self.platform, ctx.org_id, ctx.workspace_id, ctx.user_id
            )
        if not record or record.org_id != ctx.org_id or record.workspace_id != ctx.workspace_id:
            raise PlatformContextError(
                "AGENT_BINDING_MISMATCH", "binding unavailable in workspace"
            )
        if record.agent_id != agent_id:
            raise PlatformContextError(
                "AGENT_BINDING_MISMATCH", "binding identity mismatch"
            )
        if record.state == PlatformAgentBindingState.SUSPENDED.value:
            raise PlatformContextError(
                "BINDING_SUSPENDED", "platform-agent binding is suspended"
            )
        if record.state == PlatformAgentBindingState.REVOKED.value:
            raise PlatformContextError(
                "BINDING_REVOKED", "platform-agent binding is revoked"
            )
        if binding_version is not None and int(binding_version) != record.version:
            raise PlatformContextError(
                "BINDING_VERSION_STALE", "platform-agent binding version is stale"
            )
        self._validate_record_scope(ctx, record)
        return record

    def validate_execution_policy(
        self,
        ctx: PlatformExecutionContext,
        record: PlatformAgentBindingRecord,
        *,
        tool_id: str,
        capability: str,
        authority: str,
    ) -> None:
        if record.allowed_tools and tool_id not in record.allowed_tools:
            raise PlatformContextError(
                "BINDING_TOOL_SCOPE", "tool is outside binding scope"
            )
        if record.allowed_capabilities and capability not in record.allowed_capabilities:
            raise PlatformContextError(
                "BINDING_CAPABILITY_SCOPE", "capability is outside binding scope"
            )
        if not authority_allows(record.authority_ceiling, authority):
            raise PlatformContextError(
                "BINDING_AUTHORITY_EXCEEDED",
                "tool authority exceeds binding ceiling",
            )
        role_ceiling = ROLE_AUTHORITY_CEILING.get(ctx.role, "")
        if not authority_allows(role_ceiling, authority):
            raise PlatformContextError(
                "BINDING_AUTHORITY_EXCEEDED",
                "tool authority exceeds caller role ceiling",
            )

    def _transition(
        self,
        ctx: PlatformExecutionContext,
        binding_id: str,
        *,
        target: PlatformAgentBindingState,
        event: str,
    ) -> PlatformAgentBindingRecord:
        ctx.require_permission(PlatformPermission.AGENT_BINDING_MANAGE)
        current = self._scoped(ctx, binding_id)
        source = PlatformAgentBindingState(current.state)
        if source == PlatformAgentBindingState.REVOKED:
            raise PlatformContextError("BINDING_REVOKED", "revoked binding is immutable")
        if target == source:
            raise PlatformContextError(
                "BINDING_TRANSITION_DUPLICATE", "binding already in requested state"
            )
        if target == PlatformAgentBindingState.ACTIVE and source != PlatformAgentBindingState.SUSPENDED:
            raise PlatformContextError(
                "BINDING_TRANSITION_ILLEGAL", "only suspended bindings may activate"
            )
        updated = self.store.update_agent_binding(
            binding_id,
            updates={"state": target.value},
            updated_by=ctx.user_id,
            bump_version=True,
        )
        self._audit(event, ctx, updated)
        return updated

    def _scoped(
        self, ctx: PlatformExecutionContext, binding_id: str
    ) -> PlatformAgentBindingRecord:
        record = self.store.get_agent_binding(binding_id)
        if (
            not record
            or record.org_id != ctx.org_id
            or record.workspace_id != ctx.workspace_id
        ):
            self._reject(ctx, "BINDING_ACCESS_REJECTED")
            raise PlatformContextError(
                "BINDING_NOT_FOUND", "binding not found in workspace"
            )
        return record

    def _validate_scope(
        self,
        ctx: PlatformExecutionContext,
        *,
        workspace_id: str,
        project_id: str,
        mission_id: str,
    ) -> None:
        if workspace_id != ctx.workspace_id:
            self._reject(ctx, "BINDING_ACCESS_REJECTED")
            raise PlatformContextError(
                "BINDING_SCOPE_INVALID", "binding workspace is unavailable"
            )
        if project_id:
            project = self.store.get_project(project_id)
            if (
                not project
                or project.org_id != ctx.org_id
                or project.workspace_id != ctx.workspace_id
                or project.status != "active"
            ):
                raise PlatformContextError(
                    "BINDING_SCOPE_INVALID", "project is unavailable"
                )
        if mission_id:
            if not project_id:
                raise PlatformContextError(
                    "PROJECT_REQUIRED", "mission binding requires project"
                )
            mission = self.store.get_mission(mission_id)
            if (
                not mission
                or mission.org_id != ctx.org_id
                or mission.workspace_id != ctx.workspace_id
                or mission.project_id != project_id
                or mission.status != "active"
            ):
                raise PlatformContextError(
                    "BINDING_SCOPE_INVALID", "mission is unavailable"
                )

    @staticmethod
    def _validate_record_scope(
        ctx: PlatformExecutionContext, record: PlatformAgentBindingRecord
    ) -> None:
        if record.project_id and record.project_id != ctx.project_id:
            raise PlatformContextError(
                "BINDING_PROJECT_SCOPE", "execution project is outside binding scope"
            )
        if record.mission_id and record.mission_id != ctx.mission_id:
            raise PlatformContextError(
                "BINDING_MISSION_SCOPE", "execution mission is outside binding scope"
            )

    def _validate_authority_ceiling(
        self, ctx: PlatformExecutionContext, ceiling: str
    ) -> None:
        if ceiling not in SAFE_AUTHORITY_ORDER:
            self._reject(ctx, "AUTHORITY_ESCALATION_REJECTED")
            raise PlatformContextError(
                "BINDING_AUTHORITY_INVALID",
                "financial, unknown, or unsupported binding authority is prohibited",
            )
        role_ceiling = ROLE_AUTHORITY_CEILING.get(ctx.role, "")
        security = self.store.get_config("security", {}) or {}
        owner_ceiling = str(
            security.get(
                "authority_ceiling", ToolAuthorityClass.SECURITY_SENSITIVE.value
            )
        )
        effective = role_ceiling
        if owner_ceiling in SAFE_AUTHORITY_ORDER and authority_allows(
            effective, owner_ceiling
        ):
            effective = owner_ceiling
        if not authority_allows(effective, ceiling):
            self._reject(ctx, "AUTHORITY_ESCALATION_REJECTED")
            raise PlatformContextError(
                "BINDING_AUTHORITY_ESCALATION",
                "binding authority exceeds administrator policy ceiling",
            )

    @staticmethod
    def _normalize_values(values: list[str]) -> list[str]:
        return sorted({str(value).strip()[:120] for value in values if str(value).strip()})

    def _validate_tools(self, tools: list[str]) -> list[str]:
        normalized = self._normalize_values(tools)
        if not normalized:
            return []
        from saathi.tool_runtime.registry import default_registry

        registry = default_registry()
        missing = [tool for tool in normalized if not registry.get_manifest(tool)]
        if missing:
            raise PlatformContextError(
                "BINDING_TOOL_UNKNOWN", "binding contains an unknown tool"
            )
        return normalized

    def _audit(
        self,
        event: str,
        ctx: PlatformExecutionContext,
        record: PlatformAgentBindingRecord,
    ) -> None:
        self.platform._audit(
            event,
            ctx,
            authority=record.authority_ceiling,
            outcome=record.state,
            detail={
                "binding_id": record.binding_id,
                "agent_id": record.agent_id,
                "binding_version": record.version,
            },
        )

    def _reject(self, ctx: PlatformExecutionContext, code: str) -> None:
        self.platform._audit(
            "binding.administration_rejected",
            ctx,
            outcome="BLOCKED",
            detail={"reason": code},
        )
