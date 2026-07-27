"""M50 Platform API — FastAPI router. Token via X-Platform-Token or Authorization Bearer.

Read-safe by default. Mutation routes require session + RBAC. No live connectors.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

# Request used by login / invite accept for client key

from saathi.platform.context import PlatformContextError
from saathi.platform.service import default_platform

router = APIRouter(prefix="/api/v1/platform", tags=["platform-m50"])


def _token(
    authorization: str | None = None,
    x_platform_token: str | None = None,
) -> str:
    if x_platform_token:
        return x_platform_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _svc():
    return default_platform()


def _err(exc: PlatformContextError) -> HTTPException:
    status = 403
    if exc.code in ("ANONYMOUS_PROHIBITED", "SESSION_INVALID", "AUTH_FAILED"):
        status = 401
    if exc.code in (
        "APPROVAL_NOT_FOUND",
        "TOOL_NOT_FOUND",
        "BINDING_NOT_FOUND",
        "EXECUTION_NOT_FOUND",
        "NOT_FOUND",
    ):
        status = 404
    if exc.code == "STALE_STATE":
        status = 409  # optimistic-concurrency conflict
    if exc.code in ("VALIDATION_FAILED", "UNSAFE_CONFIG"):
        status = 400
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


class BootstrapBody(BaseModel):
    email: str = "owner@local"
    name: str = "Owner"
    org_name: str = "Default Org"
    workspace_name: str = "Default Workspace"
    password: str = ""


class LoginBody(BaseModel):
    email: str
    password: str = ""
    method: str = "LOCAL_PASSWORD"
    magic_code: str = ""
    org_id: str = ""
    workspace_id: str = ""
    # legacy M50: passwordless email login still allowed when no password set


class PasswordChangeBody(BaseModel):
    current: str
    new_password: str


class InviteBody(BaseModel):
    email: str
    role: str = "viewer"
    workspace_id: str = ""
    ttl_sec: float = 604800


class AcceptInviteBody(BaseModel):
    invite_code: str
    name: str = ""
    password: str = ""


class WorkspaceSelectBody(BaseModel):
    org_id: str
    workspace_id: str


class MemberRoleBody(BaseModel):
    user_id: str
    role: str


class MemberUserBody(BaseModel):
    user_id: str


class LegacyMissionLinkBody(BaseModel):
    mission_id: str
    legacy_key: str


class SafetyBody(BaseModel):
    updates: dict[str, Any] = Field(default_factory=dict)


class AgentExecuteBody(BaseModel):
    tool_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    approval_id: str = ""
    project_id: str = ""
    mission_id: str = ""
    run_id: str = ""
    idempotency_key: str = ""
    capability: str = ""
    agent_id: str = "platform-agent"
    binding_id: str = ""
    binding_version: int | None = None
    timeout_sec: float | None = None
    # spoof fields intentionally ignored
    user_id: str = ""
    org_id: str = ""
    workspace_id: str = ""
    role: str = ""
    authority: str = ""


class ProjectBody(BaseModel):
    name: str
    mission_key: str = ""


class MissionBody(BaseModel):
    project_id: str
    key: str
    name: str


class MemberBody(BaseModel):
    user_id: str
    role: str = "viewer"


class ApprovalRequestBody(BaseModel):
    tool_id: str
    action: str = ""
    target_resource: str = ""
    authority: str = ""
    side_effect_class: str = ""
    capability: str = ""
    project_id: str = ""
    mission_id: str = ""
    connector: str = ""
    ttl_sec: float | None = None


class ApprovalDecideBody(BaseModel):
    approve: bool
    reason: str = ""


class ExecuteBody(BaseModel):
    tool_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    approval_id: str = ""
    project_id: str = ""
    mission_id: str = ""
    run_id: str = ""
    idempotency_key: str = ""
    capability: str = ""
    timeout_sec: float | None = None
    # compatibility fields are accepted but never trusted
    user_id: str = ""
    org_id: str = ""
    workspace_id: str = ""
    role: str = ""
    authority: str = ""


class RuntimeResumeBody(BaseModel):
    approval_id: str = ""
    timeout_sec: float | None = None


class AgentBindingCreateBody(BaseModel):
    agent_id: str
    name: str
    description: str = ""
    workspace_id: str = ""
    project_id: str = ""
    mission_id: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_capabilities: list[str] = Field(default_factory=list)
    authority_ceiling: str = "READ_ONLY"


class AgentBindingUpdateBody(BaseModel):
    updates: dict[str, Any] = Field(default_factory=dict)


class RuntimeReconcileBody(BaseModel):
    action: str
    idempotency_key: str
    note: str = ""
    evidence_reference: str = ""
    approval_id: str = ""


class ConfigBody(BaseModel):
    updates: dict[str, Any] = Field(default_factory=dict)


class RetentionPreviewBody(BaseModel):
    retention_days: int | None = None


class RetentionHoldBody(BaseModel):
    execution_id: str
    held: bool = True


@router.get("/health")
def platform_health():
    return _svc().health()


@router.post("/bootstrap")
def platform_bootstrap(body: BootstrapBody):
    try:
        if body.password:
            return _svc().bootstrap_owner_secure(
                email=body.email,
                name=body.name,
                password=body.password,
                org_name=body.org_name,
                workspace_name=body.workspace_name,
            )
        # M50 compatibility: passwordless bootstrap
        return _svc().bootstrap_owner(
            email=body.email,
            name=body.name,
            org_name=body.org_name,
            workspace_name=body.workspace_name,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/auth/login")
def platform_login(body: LoginBody, request: Request):
    try:
        client = request.client.host if request.client else ""
        if body.password or body.magic_code or body.method != "LOCAL_PASSWORD":
            return _svc().authenticate_login(
                email=body.email,
                password=body.password,
                method=body.method,
                magic_code=body.magic_code,
                org_id=body.org_id,
                workspace_id=body.workspace_id,
                client_key=f"{client}:{body.email}",
            )
        # M50 passwordless path (existing users without credentials)
        return _svc().login(
            email=body.email, org_id=body.org_id, workspace_id=body.workspace_id
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/private-alpha")
def private_alpha_banner():
    return _svc().private_alpha_banner()


@router.post("/auth/logout")
def platform_logout(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    tok = _token(authorization, x_platform_token)
    return {"ok": _svc().logout(tok)}


@router.get("/me")
def platform_me(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        user = _svc().store.get_user(ctx.user_id)
        return {
            "user": user.to_public() if user else {"user_id": ctx.user_id},
            "context": ctx.to_audit_dict(),
            "permissions": sorted(
                p.value for p in __import__(
                    "saathi.platform.models", fromlist=["permissions_for_role"]
                ).permissions_for_role(ctx.role)
            ),
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/organizations")
def list_orgs(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        orgs = _svc().store.list_orgs_for_user(ctx.user_id)
        return {"organizations": [o.to_public() for o in orgs]}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/workspaces")
def list_workspaces(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        wss = _svc().store.list_workspaces(ctx.org_id)
        return {"workspaces": [w.to_public() for w in wss]}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/projects")
def list_projects(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        projs = _svc().store.list_projects(org_id=ctx.org_id, workspace_id=ctx.workspace_id)
        return {"projects": [p.to_public() for p in projs]}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/projects")
def create_project(
    body: ProjectBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return {"project": _svc().create_project(ctx, body.name, mission_key=body.mission_key)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/missions")
def list_missions(
    project_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(
            _token(authorization, x_platform_token), project_id=project_id
        )
        miss = _svc().store.list_missions(
            project_id=project_id, org_id=ctx.org_id if not project_id else ""
        )
        if not project_id:
            miss = [m for m in miss if m.org_id == ctx.org_id]
        return {"missions": [m.to_public() for m in miss]}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/missions")
def create_mission(
    body: MissionBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(
            _token(authorization, x_platform_token), project_id=body.project_id
        )
        return {
            "mission": _svc().create_mission(ctx, body.project_id, body.key, body.name)
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/members")
def add_member(
    body: MemberBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        _svc().add_member(ctx, body.user_id, body.role)
        return {"ok": True}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/approvals")
def approvals_inbox(
    status: str = "pending",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return {"approvals": _svc().inbox(ctx, status=status)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/approvals")
def request_approval(
    body: ApprovalRequestBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(
            _token(authorization, x_platform_token),
            project_id=body.project_id,
            mission_id=body.mission_id,
        )
        rec = _svc().request_approval(
            ctx,
            tool_id=body.tool_id,
            action=body.action,
            target_resource=body.target_resource,
            authority=body.authority,
            side_effect_class=body.side_effect_class,
            capability=body.capability,
            ttl_sec=body.ttl_sec,
            connector=body.connector,
        )
        return {"approval": rec.to_public()}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/approvals/{approval_id}/decide")
def decide_approval(
    approval_id: str,
    body: ApprovalDecideBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        rec = _svc().decide_approval(
            ctx, approval_id, approve=body.approve, reason=body.reason
        )
        return {"approval": rec.to_public()}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/approvals/{approval_id}/revoke")
def revoke_approval(
    approval_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        rec = _svc().revoke_approval(ctx, approval_id)
        return {"approval": rec.to_public()}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/execute")
def platform_execute(
    body: ExecuteBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        from saathi.platform.runtime import PlatformAgentRuntime

        result = PlatformAgentRuntime(_svc()).execute_token(
            token=_token(authorization, x_platform_token),
            tool_id=body.tool_id,
            arguments=body.arguments,
            project_id=body.project_id,
            mission_id=body.mission_id,
            run_id=body.run_id,
            approval_id=body.approval_id,
            idempotency_key=body.idempotency_key,
            capability=body.capability,
            timeout_sec=body.timeout_sec,
        )
        return {
            "ok": result.ok,
            "outcome_class": result.outcome_class.value,
            "error_code": result.error_code or "",
            "safe_message": result.safe_message,
            "data": result.data,
            "run_id": getattr(result, "platform_run_id", body.run_id),
            "tool_id": body.tool_id,
            "execution_id": getattr(result, "platform_execution_id", ""),
            "execution_state": getattr(result, "platform_execution_state", ""),
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/config")
def get_config(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return {"config": _svc().configuration(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.patch("/config")
def patch_config(
    body: ConfigBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return {"config": _svc().update_configuration(ctx, body.updates)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/audit")
def list_audit(
    limit: int = 50,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        from saathi.platform.models import PlatformPermission

        ctx = _svc().require_context(_token(authorization, x_platform_token))
        ctx.require_permission(PlatformPermission.AUDIT_READ)
        return {
            "events": _svc().store.list_audit(org_id=ctx.org_id, limit=min(limit, 200))
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/sessions")
def list_sessions(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        sessions = _svc().store.list_sessions(ctx.user_id)
        return {
            "sessions": [
                {
                    "session_id": s.session_id,
                    "org_id": s.org_id,
                    "workspace_id": s.workspace_id,
                    "role": s.role,
                    "expires_at": s.expires_at,
                    "last_seen": s.last_seen,
                    "label": s.label,
                }
                for s in sessions
            ]
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/sessions/{session_id}/revoke")
def revoke_session(
    session_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        ok = _svc().revoke_session(actor_user_id=ctx.user_id, session_id=session_id)
        return {"ok": ok}
    except PlatformContextError as e:
        raise _err(e) from e


# ── M51 private-alpha surfaces ────────────────────────────────────────────

@router.post("/auth/password/change")
def change_password(
    body: PasswordChangeBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return _svc().change_password(ctx, current=body.current, new_password=body.new_password)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/auth/session/rotate")
def rotate_session(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _svc().rotate_session(_token(authorization, x_platform_token))
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/context/workspace")
def select_workspace(
    body: WorkspaceSelectBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _svc().select_workspace(
            _token(authorization, x_platform_token),
            org_id=body.org_id,
            workspace_id=body.workspace_id,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/invitations")
def create_invitation(
    body: InviteBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return {
            "invitation": _svc().create_invitation(
                ctx,
                email=body.email,
                role=body.role,
                workspace_id=body.workspace_id,
                ttl_sec=body.ttl_sec,
            )
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/invitations")
def list_invitations(
    status: str = "pending",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        from saathi.platform.models import PlatformPermission

        ctx.require_permission(PlatformPermission.USER_MANAGE)
        return {"invitations": _svc().store.list_invitations(ctx.org_id, status=status)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/invitations/accept")
def accept_invitation(body: AcceptInviteBody, request: Request):
    try:
        client = request.client.host if request.client else ""
        return _svc().accept_invitation(
            invite_code=body.invite_code,
            name=body.name,
            password=body.password,
            client_key=client,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/invitations/{invite_id}/revoke")
def revoke_invitation(
    invite_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return _svc().revoke_invitation(ctx, invite_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/members")
def list_members(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return {"members": _svc().list_members(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/members/role")
def change_member_role(
    body: MemberRoleBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return _svc().change_member_role(ctx, body.user_id, body.role)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/members/remove")
def remove_member(
    body: MemberUserBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return _svc().remove_member(ctx, body.user_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/members/suspend")
def suspend_member(
    body: MemberUserBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return _svc().suspend_member(ctx, body.user_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/missions/legacy-link")
def legacy_mission_link(
    body: LegacyMissionLinkBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return _svc().link_legacy_mission(ctx, body.mission_id, body.legacy_key)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/owner/safety")
def owner_safety(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return _svc().owner_safety_flags(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


@router.patch("/owner/safety")
def owner_safety_patch(
    body: SafetyBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return _svc().owner_set_safety(ctx, body.updates)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/agent/execute")
def agent_execute(
    body: AgentExecuteBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    """Trusted platform-context agent execution — ignores spoofed user/org/role."""
    try:
        from saathi.platform.agent_binding import PlatformAgentBinding

        result = PlatformAgentBinding(_svc()).execute(
            token=_token(authorization, x_platform_token),
            tool_id=body.tool_id,
            arguments=body.arguments,
            project_id=body.project_id,
            mission_id=body.mission_id,
            approval_id=body.approval_id,
            run_id=body.run_id,
            idempotency_key=body.idempotency_key,
            capability=body.capability,
            agent_id=body.agent_id,
            binding_id=body.binding_id,
            binding_version=body.binding_version,
            timeout_sec=body.timeout_sec,
        )
        return {
            "ok": result.ok,
            "outcome_class": result.outcome_class.value,
            "error_code": result.error_code or "",
            "safe_message": result.safe_message,
            "data": result.data,
            "execution_id": getattr(result, "platform_execution_id", ""),
            "execution_state": getattr(result, "platform_execution_state", ""),
            "spoof_fields_ignored": [
                "user_id",
                "org_id",
                "workspace_id",
                "role",
                "authority",
            ],
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/agent/callers")
def agent_callers():
    from saathi.platform.agent_binding import inventory_agent_callers

    return {"callers": inventory_agent_callers()}


@router.post("/agent-bindings")
def agent_binding_create(
    body: AgentBindingCreateBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        from saathi.platform.bindings import BindingAdministrationService

        svc = _svc()
        ctx = svc.require_context(_token(authorization, x_platform_token))
        record = BindingAdministrationService(svc).create(
            ctx, **body.model_dump()
        )
        return {"binding": record.to_public()}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/agent-bindings")
def agent_binding_list(
    state: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        from saathi.platform.bindings import BindingAdministrationService

        svc = _svc()
        ctx = svc.require_context(_token(authorization, x_platform_token))
        records = BindingAdministrationService(svc).list(ctx, state=state)
        return {"bindings": [record.to_public() for record in records]}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/agent-bindings/{binding_id}")
def agent_binding_inspect(
    binding_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        from saathi.platform.bindings import BindingAdministrationService

        svc = _svc()
        ctx = svc.require_context(_token(authorization, x_platform_token))
        return {
            "binding": BindingAdministrationService(svc)
            .inspect(ctx, binding_id)
            .to_public()
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.patch("/agent-bindings/{binding_id}")
def agent_binding_update(
    binding_id: str,
    body: AgentBindingUpdateBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        from saathi.platform.bindings import BindingAdministrationService

        svc = _svc()
        ctx = svc.require_context(_token(authorization, x_platform_token))
        return {
            "binding": BindingAdministrationService(svc)
            .update(ctx, binding_id, body.updates)
            .to_public()
        }
    except PlatformContextError as e:
        raise _err(e) from e


def _binding_transition(
    action: str,
    binding_id: str,
    authorization: str | None,
    x_platform_token: str | None,
):
    from saathi.platform.bindings import BindingAdministrationService

    svc = _svc()
    ctx = svc.require_context(_token(authorization, x_platform_token))
    method = getattr(BindingAdministrationService(svc), action)
    return {"binding": method(ctx, binding_id).to_public()}


@router.post("/agent-bindings/{binding_id}/suspend")
def agent_binding_suspend(
    binding_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _binding_transition(
            "suspend", binding_id, authorization, x_platform_token
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/agent-bindings/{binding_id}/activate")
def agent_binding_activate(
    binding_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _binding_transition(
            "activate", binding_id, authorization, x_platform_token
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/agent-bindings/{binding_id}/revoke")
def agent_binding_revoke(
    binding_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _binding_transition("revoke", binding_id, authorization, x_platform_token)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/agent-bindings/{binding_id}/rotate")
def agent_binding_rotate(
    binding_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _binding_transition("rotate", binding_id, authorization, x_platform_token)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/runtime/executions")
def runtime_executions(
    state: str = "",
    project_id: str = "",
    mission_id: str = "",
    binding_id: str = "",
    user_id: str = "",
    tool_id: str = "",
    created_after: float = 0,
    created_before: float = 0,
    limit: int = 100,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        from saathi.platform.operations import RuntimeOperationsService

        ops = RuntimeOperationsService(_svc())
        ctx = ops.context(_token(authorization, x_platform_token))
        return {
            "executions": ops.list_executions(
                ctx,
                state=state,
                project_id=project_id,
                mission_id=mission_id,
                binding_id=binding_id,
                user_id=user_id,
                tool_id=tool_id,
                created_after=created_after,
                created_before=created_before,
                limit=limit,
            )
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/runtime/executions/{execution_id}")
def runtime_execution(
    execution_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        from saathi.platform.operations import RuntimeOperationsService

        ops = RuntimeOperationsService(_svc())
        ctx = ops.context(_token(authorization, x_platform_token))
        return {"execution": ops.inspect(ctx, execution_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/runtime/executions/{execution_id}/cancel")
def runtime_cancel(
    execution_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        from saathi.platform.operations import RuntimeOperationsService

        token = _token(authorization, x_platform_token)
        ops = RuntimeOperationsService(_svc())
        ctx = ops.context(token)
        return {
            "execution": ops.cancel(
                ctx, token=token, execution_id=execution_id
            )
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/runtime/executions/{execution_id}/timeline")
def runtime_timeline(
    execution_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        from saathi.platform.operations import RuntimeOperationsService

        ops = RuntimeOperationsService(_svc())
        ctx = ops.context(_token(authorization, x_platform_token))
        return {"timeline": ops.timeline(ctx, execution_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/runtime/attention")
def runtime_attention(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        from saathi.platform.operations import RuntimeOperationsService

        ops = RuntimeOperationsService(_svc())
        ctx = ops.context(_token(authorization, x_platform_token))
        return {"attention": ops.attention(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/runtime/metrics")
def runtime_metrics(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        from saathi.platform.operations import RuntimeOperationsService

        ops = RuntimeOperationsService(_svc())
        ctx = ops.context(_token(authorization, x_platform_token))
        return {"metrics": ops.metrics(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/runtime/executions/{execution_id}/reconcile")
def runtime_reconcile(
    execution_id: str,
    body: RuntimeReconcileBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        from saathi.platform.operations import RuntimeOperationsService

        token = _token(authorization, x_platform_token)
        ops = RuntimeOperationsService(_svc())
        ctx = ops.context(token)
        return ops.reconcile(
            ctx,
            token=token,
            execution_id=execution_id,
            **body.model_dump(),
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/runtime/executions/{execution_id}/resume")
def runtime_resume(
    execution_id: str,
    body: RuntimeResumeBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        from saathi.platform.runtime import PlatformAgentRuntime

        result = PlatformAgentRuntime(_svc()).resume(
            token=_token(authorization, x_platform_token),
            execution_id=execution_id,
            approval_id=body.approval_id,
            timeout_sec=body.timeout_sec,
        )
        return {
            "ok": result.ok,
            "outcome_class": result.outcome_class.value,
            "error_code": result.error_code or "",
            "safe_message": result.safe_message,
            "data": result.data,
            "execution_id": getattr(result, "platform_execution_id", ""),
            "execution_state": getattr(result, "platform_execution_state", ""),
        }
    except PlatformContextError as e:
        raise _err(e) from e


# ── M54 private-alpha operational readiness ─────────────────────────────────
def _readiness():
    from saathi.platform.readiness import OperationalReadinessService

    return OperationalReadinessService(_svc())


@router.get("/runtime/diagnostics")
def runtime_diagnostics(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        svc = _readiness()
        ctx = svc.context(_token(authorization, x_platform_token))
        return {"diagnostics": svc.diagnostics(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/runtime/export")
def runtime_export(
    kind: str = "execution_summary",
    format: str = "json",
    limit: int = 200,
    execution_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        svc = _readiness()
        ctx = svc.context(_token(authorization, x_platform_token))
        return svc.export(
            ctx, kind=kind, fmt=format, limit=limit, execution_id=execution_id
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/runtime/retention/preview")
def runtime_retention_preview(
    body: RetentionPreviewBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        svc = _readiness()
        ctx = svc.context(_token(authorization, x_platform_token))
        return {"retention": svc.retention_preview(ctx, retention_days=body.retention_days)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/runtime/retention/hold")
def runtime_retention_hold(
    body: RetentionHoldBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        svc = _readiness()
        ctx = svc.context(_token(authorization, x_platform_token))
        return {
            "hold": svc.set_hold(
                ctx, execution_id=body.execution_id, held=body.held
            )
        }
    except PlatformContextError as e:
        raise _err(e) from e


# ── M55 release-candidate operational excellence ────────────────────────────
def _release():
    from saathi.platform.release import ReleaseOperationsService

    return ReleaseOperationsService(_svc())


@router.get("/release/health")
def release_health(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        svc = _release()
        ctx = svc.context(_token(authorization, x_platform_token))
        return {"health": svc.health(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/release/metrics")
def release_metrics(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        svc = _release()
        ctx = svc.context(_token(authorization, x_platform_token))
        return {"metrics": svc.metrics(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/release/validate")
def release_validate(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        svc = _release()
        ctx = svc.context(_token(authorization, x_platform_token))
        return {"release": svc.release_validate(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/release/backup")
def release_backup(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        svc = _release()
        ctx = svc.context(_token(authorization, x_platform_token))
        return {"backup": svc.backup_validate(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/release/recovery")
def release_recovery(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        svc = _release()
        ctx = svc.context(_token(authorization, x_platform_token))
        return {"recovery": svc.recovery_certify(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


# ── M56 distributed runtime foundation ──────────────────────────────────────
class WorkerRegisterBody(BaseModel):
    worker_id: str = ""
    node_id: str = "node-local"
    capabilities: list[str] = Field(default_factory=list)


class WorkerActionBody(BaseModel):
    worker_id: str
    action: str = ""  # heartbeat | drain | pause | resume | retire


class LeaseBody(BaseModel):
    execution_id: str
    worker_id: str = "worker-local"
    ttl_sec: float = 300.0


class LeaseTransferBody(BaseModel):
    execution_id: str
    to_worker_id: str


class SchedulerControlBody(BaseModel):
    action: str  # pause | resume


def _cluster():
    from saathi.platform.cluster import ClusterCoordinator

    return ClusterCoordinator(_svc())


@router.get("/cluster/topology")
def cluster_topology(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        c = _cluster()
        ctx = c.read_context(_token(authorization, x_platform_token))
        return {"topology": c.topology(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/cluster/node-health")
def cluster_node_health(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        c = _cluster()
        ctx = c.read_context(_token(authorization, x_platform_token))
        return {"node_health": c.node_health(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/cluster/metrics")
def cluster_metrics(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        c = _cluster()
        ctx = c.read_context(_token(authorization, x_platform_token))
        return {"metrics": c.distributed_metrics(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/cluster/scheduler")
def cluster_scheduler(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        c = _cluster()
        ctx = c.read_context(_token(authorization, x_platform_token))
        return {"scheduler": c.scheduler_plan(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/cluster/scheduler/control")
def cluster_scheduler_control(
    body: SchedulerControlBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        c = _cluster()
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return {"scheduler": c.scheduler_control(ctx, action=body.action)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/cluster/workers/register")
def cluster_worker_register(
    body: WorkerRegisterBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        c = _cluster()
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return {"worker": c.register_worker(
            ctx, worker_id=body.worker_id, node_id=body.node_id, capabilities=body.capabilities
        )}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/cluster/workers/action")
def cluster_worker_action(
    body: WorkerActionBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        c = _cluster()
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        if body.action == "heartbeat":
            return {"heartbeat": c.heartbeat(ctx, worker_id=body.worker_id)}
        return {"worker": c.set_worker_state(ctx, worker_id=body.worker_id, action=body.action)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/cluster/leases/acquire")
def cluster_lease_acquire(
    body: LeaseBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        c = _cluster()
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return {"lease": c.acquire_lease(
            ctx, execution_id=body.execution_id, worker_id=body.worker_id, ttl_sec=body.ttl_sec
        )}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/cluster/leases/renew")
def cluster_lease_renew(
    body: LeaseBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        c = _cluster()
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return {"lease": c.renew_lease(
            ctx, execution_id=body.execution_id, worker_id=body.worker_id, ttl_sec=body.ttl_sec
        )}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/cluster/leases/transfer")
def cluster_lease_transfer(
    body: LeaseTransferBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        c = _cluster()
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return {"lease": c.transfer_lease(
            ctx, execution_id=body.execution_id, to_worker_id=body.to_worker_id
        )}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/cluster/leases/verify")
def cluster_lease_verify(
    execution_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        c = _cluster()
        ctx = c.read_context(_token(authorization, x_platform_token))
        return {"lease": c.verify_lease(ctx, execution_id=execution_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/cluster/leases/recover")
def cluster_lease_recover(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        c = _cluster()
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return {"recovery": c.recover_leases(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/cluster/recovery")
def cluster_recovery(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        c = _cluster()
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return {"recovery": c.recovery_certify(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


# ══════════════════════════════════════════════════════════════════════════
# M61 — workflow persistence endpoints (plans, notifications, saved views,
# templates, drafts, attention mutations, server search). Server-authoritative,
# permission-gated, audited, optimistic-concurrency checked. No execution path.
# ══════════════════════════════════════════════════════════════════════════
def _wf():
    from saathi.platform.workflow_service import WorkflowService
    return WorkflowService(_svc().store)


class PlanBody(BaseModel):
    mission_id: str
    body: dict[str, Any] = Field(default_factory=dict)
    state: str | None = None
    expected_version: int | None = None


class PublishPlanBody(BaseModel):
    mission_id: str
    expected_version: int


class NotificationBody(BaseModel):
    type: str
    title: str
    summary: str = ""
    severity: str = "info"
    related_object: str = ""
    related_type: str = ""
    evidence: str = ""
    dedupe_key: str = ""


class NotificationFlagBody(BaseModel):
    read: bool | None = None
    archived: bool | None = None


class SavedViewBody(BaseModel):
    name: str
    route: str
    config: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False


class SavedViewUpdateBody(BaseModel):
    expected_version: int
    name: str | None = None
    route: str | None = None
    config: dict[str, Any] | None = None
    is_default: bool | None = None


class TemplateBody(BaseModel):
    name: str
    body: dict[str, Any] = Field(default_factory=dict)


class TemplateUpdateBody(BaseModel):
    expected_version: int
    name: str | None = None
    body: dict[str, Any] | None = None
    state: str | None = None


class DraftBody(BaseModel):
    kind: str
    body: dict[str, Any] = Field(default_factory=dict)


class AttentionActionBody(BaseModel):
    action: str
    note: str = ""
    expected_version: int | None = None


def _ctx(authorization, x_platform_token):
    return _svc().require_context(_token(authorization, x_platform_token))


# ── mission plans ──────────────────────────────────────────────────────────
@router.get("/workflow/plans/{mission_id}")
def wf_get_plan(mission_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"plan": _wf().get_plan(_ctx(authorization, x_platform_token), mission_id=mission_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.put("/workflow/plans")
def wf_upsert_plan(body: PlanBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"plan": _wf().upsert_plan(_ctx(authorization, x_platform_token), mission_id=body.mission_id, body=body.body, state=body.state, expected_version=body.expected_version)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/workflow/plans/publish")
def wf_publish_plan(body: PublishPlanBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"plan": _wf().publish_plan(_ctx(authorization, x_platform_token), mission_id=body.mission_id, expected_version=body.expected_version)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/workflow/plans/{mission_id}/revisions")
def wf_plan_revisions(mission_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        wf = _wf()
        ctx = _ctx(authorization, x_platform_token)
        plan = wf.get_plan(ctx, mission_id=mission_id)
        if not plan:
            return {"revisions": []}
        return {"revisions": wf.plan_revisions(ctx, plan_id=plan["plan_id"])}
    except PlatformContextError as e:
        raise _err(e) from e


# ── notifications ──────────────────────────────────────────────────────────
@router.get("/workflow/notifications")
def wf_list_notifications(include_archived: bool = False, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"notifications": _wf().list_notifications(_ctx(authorization, x_platform_token), include_archived=include_archived)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/workflow/notifications")
def wf_create_notification(body: NotificationBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"notification": _wf().create_notification(_ctx(authorization, x_platform_token), type=body.type, title=body.title, summary=body.summary, severity=body.severity, related_object=body.related_object, related_type=body.related_type, evidence=body.evidence, dedupe_key=body.dedupe_key)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.patch("/workflow/notifications/{notification_id}")
def wf_flag_notification(notification_id: str, body: NotificationFlagBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"notification": _wf().set_notification(_ctx(authorization, x_platform_token), notification_id, read=body.read, archived=body.archived)}
    except PlatformContextError as e:
        raise _err(e) from e


# ── saved views ────────────────────────────────────────────────────────────
@router.get("/workflow/saved-views")
def wf_list_views(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"views": _wf().list_views(_ctx(authorization, x_platform_token))}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/workflow/saved-views")
def wf_create_view(body: SavedViewBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"view": _wf().create_view(_ctx(authorization, x_platform_token), name=body.name, route=body.route, config=body.config, is_default=body.is_default)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.patch("/workflow/saved-views/{view_id}")
def wf_update_view(view_id: str, body: SavedViewUpdateBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"view": _wf().update_view(_ctx(authorization, x_platform_token), view_id, expected_version=body.expected_version, name=body.name, route=body.route, config=body.config, is_default=body.is_default)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.delete("/workflow/saved-views/{view_id}")
def wf_delete_view(view_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        _wf().delete_view(_ctx(authorization, x_platform_token), view_id)
        return {"ok": True}
    except PlatformContextError as e:
        raise _err(e) from e


# ── templates ──────────────────────────────────────────────────────────────
@router.get("/workflow/templates")
def wf_list_templates(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"templates": _wf().list_templates(_ctx(authorization, x_platform_token))}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/workflow/templates")
def wf_create_template(body: TemplateBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"template": _wf().create_template(_ctx(authorization, x_platform_token), name=body.name, body=body.body)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.patch("/workflow/templates/{template_id}")
def wf_update_template(template_id: str, body: TemplateUpdateBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"template": _wf().update_template(_ctx(authorization, x_platform_token), template_id, expected_version=body.expected_version, name=body.name, body=body.body, state=body.state)}
    except PlatformContextError as e:
        raise _err(e) from e


# ── drafts ─────────────────────────────────────────────────────────────────
@router.get("/workflow/drafts/{kind}")
def wf_get_draft(kind: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"draft": _wf().get_draft(_ctx(authorization, x_platform_token), kind=kind)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.put("/workflow/drafts")
def wf_save_draft(body: DraftBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"draft": _wf().save_draft(_ctx(authorization, x_platform_token), kind=body.kind, body=body.body)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.delete("/workflow/drafts/{kind}")
def wf_discard_draft(kind: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        _wf().discard_draft(_ctx(authorization, x_platform_token), kind=kind)
        return {"ok": True}
    except PlatformContextError as e:
        raise _err(e) from e


# ── attention mutations ────────────────────────────────────────────────────
@router.get("/workflow/attention/{execution_id}/state")
def wf_attention_state(execution_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"attention": _wf().attention_state(_ctx(authorization, x_platform_token), execution_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/workflow/attention/{execution_id}/action")
def wf_attention_action(execution_id: str, body: AttentionActionBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"attention": _wf().attention_transition(_ctx(authorization, x_platform_token), execution_id, action=body.action, note=body.note, expected_version=body.expected_version)}
    except PlatformContextError as e:
        raise _err(e) from e


# ── server search ──────────────────────────────────────────────────────────
@router.get("/workflow/search")
def wf_search(q: str = "", type: str = "all", limit: int = 50, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return _wf().search(_ctx(authorization, x_platform_token), q, type_filter=type, limit=max(1, min(int(limit), 200)))
    except PlatformContextError as e:
        raise _err(e) from e


# ══════════════════════════════════════════════════════════════════════════
# M62.2 — market-data foundation endpoints (READ-ONLY + ingestion management).
# Authenticated, tenant-scoped, bounded. NO order/broker/execution actions.
# ══════════════════════════════════════════════════════════════════════════
_MD_REPLAYS: dict[str, Any] = {}   # in-memory replay registry: id -> (org_id, engine)


def _md():
    from saathi.platform.market_data import FixtureProvider, MarketDataStore, IngestionService
    prov = FixtureProvider()
    store = MarketDataStore()
    return prov, store, IngestionService(prov, store)


def _md_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


class MDIngestBody(BaseModel):
    symbol: str
    timeframe: str = "1d"


class MDReplayBody(BaseModel):
    symbol: str
    timeframe: str = "1d"


class MDReplayStepBody(BaseModel):
    count: int = 1


def _tf(value: str):
    from saathi.platform.market_data import Timeframe
    try:
        return Timeframe(value)
    except ValueError as exc:
        raise PlatformContextError("VALIDATION_FAILED", f"unsupported timeframe {value}") from exc


@router.get("/market-data/instruments")
def md_instruments(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        ctx.require_permission(PlatformPermission.WORKFLOW_READ)
        _, store, _ = _md()
        return {"instruments": store.list_instruments(ctx.org_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/market-data/instruments/{symbol}")
def md_instrument(symbol: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        ctx.require_permission(PlatformPermission.WORKFLOW_READ)
        _, store, _ = _md()
        rec = store.get_instrument(ctx.org_id, symbol)
        if not rec:
            raise PlatformContextError("NOT_FOUND", "instrument not ingested for this tenant")
        return {"instrument": rec}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/market-data/quotes/{symbol}")
def md_quote(symbol: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.market_data import classify_quote
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        ctx.require_permission(PlatformPermission.WORKFLOW_READ)
        prov, _, _ = _md()
        now = _md_now()
        res = prov.get_quote(symbol, now=now)
        if not res.ok or res.data is None:
            raise PlatformContextError("NOT_FOUND", f"quote unavailable ({res.status.value})")
        q = res.data
        classify_quote(q, now=now)
        return {"quote": q.to_public()}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/market-data/bars/{symbol}")
def md_bars(symbol: str, timeframe: str = "1d", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        ctx.require_permission(PlatformPermission.WORKFLOW_READ)
        tf = _tf(timeframe)
        _, store, _ = _md()
        rows = store.query_bars(ctx.org_id, symbol, tf, 0, _md_now().timestamp(), limit=1000)
        return {"bars": rows, "count": len(rows)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/market-data/fixtures/manifest")
def md_fixture_manifest(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.market_data import fixture_manifest
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        ctx.require_permission(PlatformPermission.WORKFLOW_READ)
        return {"manifest": fixture_manifest()}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/market-data/fixtures/ingest")
def md_ingest(body: MDIngestBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from datetime import timedelta
        from saathi.platform.models import PlatformPermission
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        ctx.require_permission(PlatformPermission.WORKFLOW_WRITE)
        tf = _tf(body.timeframe)
        prov, store, ing = _md()
        now = _md_now()
        ing.ingest_instrument(ctx.org_id, body.symbol)
        rep = ing.ingest_bars(ctx.org_id, body.symbol, tf, now - timedelta(days=3650), now + timedelta(days=1),
                              now=now, correlation_id=f"ingest:{ctx.org_id}:{body.symbol}")
        _svc().store.append_audit("market_data.ingested", org_id=ctx.org_id, workspace_id=ctx.workspace_id,
                                  user_id=ctx.user_id, role=ctx.role, outcome="ok",
                                  detail={"symbol": body.symbol, "timeframe": tf.value, "accepted": rep.accepted, "rejected": rep.rejected})
        return {"report": rep.to_public()}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/market-data/replays")
def md_replay_create(body: MDReplayBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission, new_id
        from saathi.platform.market_data import build_bars, fixture_manifest, ReplayEngine
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        ctx.require_permission(PlatformPermission.WORKFLOW_WRITE)
        tf = _tf(body.timeframe)
        bars = build_bars(body.symbol, tf)
        rid = new_id("mdrep_")
        eng = ReplayEngine(bars, correlation_id=rid, dataset_version=fixture_manifest()["version"])
        _MD_REPLAYS[rid] = (ctx.org_id, eng)
        return {"replay": eng.checkpoint(), "replay_id": rid}
    except PlatformContextError as e:
        raise _err(e) from e


def _replay_for(ctx, rid):
    entry = _MD_REPLAYS.get(rid)
    if not entry or entry[0] != ctx.org_id:
        raise PlatformContextError("NOT_FOUND", "replay not found for tenant")
    return entry[1]


@router.get("/market-data/replays/{rid}")
def md_replay_get(rid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        ctx.require_permission(PlatformPermission.WORKFLOW_READ)
        return {"replay": _replay_for(ctx, rid).checkpoint()}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/market-data/replays/{rid}/step")
def md_replay_step(rid: str, body: MDReplayStepBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        ctx.require_permission(PlatformPermission.WORKFLOW_WRITE)
        eng = _replay_for(ctx, rid)
        events = eng.step(max(1, min(int(body.count), 500)))
        return {"replay": eng.checkpoint(), "events": [{"index": e.index, "bar": e.bar.to_public()} for e in events]}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/market-data/replays/{rid}/stop")
def md_replay_stop(rid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        ctx.require_permission(PlatformPermission.WORKFLOW_WRITE)
        eng = _replay_for(ctx, rid)
        eng.stop()
        return {"replay": eng.checkpoint()}
    except PlatformContextError as e:
        raise _err(e) from e


# ══════════════════════════════════════════════════════════════════════════
# M62.3 — research pipeline endpoints. Authenticated, tenant-scoped, audited.
# NO trading/order/broker/execution actions. Source text is untrusted data.
# ══════════════════════════════════════════════════════════════════════════
def _rsvc():
    from saathi.platform.research import ResearchService
    return ResearchService().bind_audit(_svc().store)


class ResearchProjectBody(BaseModel):
    title: str
    question: str = ""
    scope: str = ""
    mission_id: str = ""


class ResearchPlanBody(BaseModel):
    plan: dict[str, Any] = Field(default_factory=dict)
    expected_version: int


class ResearchSourceBody(BaseModel):
    source_type: str
    title: str
    content: str = ""
    locator: str = ""
    author: str = ""
    publisher: str = ""
    published_at: float = 0.0
    trust: str = "UNVERIFIED"


class ResearchStageBody(BaseModel):
    expected_version: int
    rationale: str = ""


def _rctx(a, x):
    return _svc().require_context(_token(a, x))


@router.post("/research/projects")
def r_create(body: ResearchProjectBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"project": _rsvc().create_project(_rctx(authorization, x_platform_token), title=body.title, question=body.question, scope=body.scope, mission_id=body.mission_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/research/projects")
def r_list(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"projects": _rsvc().list_projects(_rctx(authorization, x_platform_token))}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/research/projects/{pid}")
def r_get(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"project": _rsvc().get_project(_rctx(authorization, x_platform_token), pid)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/research/projects/{pid}/plan")
def r_plan(pid: str, body: ResearchPlanBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"project": _rsvc().set_plan(_rctx(authorization, x_platform_token), pid, plan=body.plan, expected_version=body.expected_version)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/research/projects/{pid}/sources")
def r_add_source(pid: str, body: ResearchSourceBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"source": _rsvc().add_source(_rctx(authorization, x_platform_token), pid, source_type=body.source_type, title=body.title, content=body.content, locator=body.locator, author=body.author, publisher=body.publisher, published_at=body.published_at, trust=body.trust)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/research/projects/{pid}/sources")
def r_sources(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"sources": _rsvc().list_sources(_rctx(authorization, x_platform_token), pid)}
    except PlatformContextError as e:
        raise _err(e) from e


def _stage(fn_name):
    def handler(pid: str, body: ResearchStageBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
        try:
            svc = _rsvc()
            ctx = _rctx(authorization, x_platform_token)
            fn = getattr(svc, fn_name)
            if fn_name == "revise":
                return fn(ctx, pid, expected_version=body.expected_version, rationale=body.rationale)
            return fn(ctx, pid, expected_version=body.expected_version)
        except PlatformContextError as e:
            raise _err(e) from e
    return handler


router.add_api_route("/research/projects/{pid}/validate", _stage("validate_sources"), methods=["POST"])
router.add_api_route("/research/projects/{pid}/claims/extract", _stage("extract_claims"), methods=["POST"])
router.add_api_route("/research/projects/{pid}/citations/verify", _stage("verify_citations"), methods=["POST"])
router.add_api_route("/research/projects/{pid}/contradictions/search", _stage("search_contradictions"), methods=["POST"])
router.add_api_route("/research/projects/{pid}/synthesize", _stage("synthesize"), methods=["POST"])
router.add_api_route("/research/projects/{pid}/challenge", _stage("challenge"), methods=["POST"])
router.add_api_route("/research/projects/{pid}/revise", _stage("revise"), methods=["POST"])
router.add_api_route("/research/projects/{pid}/publish", _stage("publish"), methods=["POST"])


@router.get("/research/projects/{pid}/claims")
def r_claims(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"claims": _rsvc().list_claims(_rctx(authorization, x_platform_token), pid)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/research/projects/{pid}/contradictions")
def r_contradictions(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"contradictions": _rsvc().list_contradictions(_rctx(authorization, x_platform_token), pid)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/research/projects/{pid}/thesis")
def r_thesis(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"thesis": _rsvc().get_thesis(_rctx(authorization, x_platform_token), pid)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/research/projects/{pid}/thesis/versions")
def r_thesis_versions(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"versions": _rsvc().thesis_versions(_rctx(authorization, x_platform_token), pid)}
    except PlatformContextError as e:
        raise _err(e) from e
