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
    ):
        status = 404
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
