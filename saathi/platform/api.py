"""M50 Platform API — FastAPI router. Token via X-Platform-Token or Authorization Bearer.

Read-safe by default. Mutation routes require session + RBAC. No live connectors.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

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
    if exc.code in ("APPROVAL_NOT_FOUND", "TOOL_NOT_FOUND"):
        status = 404
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


class BootstrapBody(BaseModel):
    email: str = "owner@local"
    name: str = "Owner"
    org_name: str = "Default Org"
    workspace_name: str = "Default Workspace"


class LoginBody(BaseModel):
    email: str
    org_id: str = ""
    workspace_id: str = ""


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


class ConfigBody(BaseModel):
    updates: dict[str, Any] = Field(default_factory=dict)


@router.get("/health")
def platform_health():
    return _svc().health()


@router.post("/bootstrap")
def platform_bootstrap(body: BootstrapBody):
    return _svc().bootstrap_owner(
        email=body.email,
        name=body.name,
        org_name=body.org_name,
        workspace_name=body.workspace_name,
    )


@router.post("/auth/login")
def platform_login(body: LoginBody):
    try:
        return _svc().login(email=body.email, org_id=body.org_id, workspace_id=body.workspace_id)
    except PlatformContextError as e:
        raise _err(e) from e


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
        ctx = _svc().require_context(
            _token(authorization, x_platform_token),
            project_id=body.project_id,
            mission_id=body.mission_id,
            run_id=body.run_id,
        )
        result = _svc().execute_tool(
            ctx,
            tool_id=body.tool_id,
            arguments=body.arguments,
            approval_id=body.approval_id,
            idempotency_key=body.idempotency_key,
            capability=body.capability,
        )
        return {
            "ok": result.ok,
            "outcome_class": result.outcome_class.value,
            "error_code": result.error_code or "",
            "safe_message": result.safe_message,
            "data": result.data,
            "run_id": ctx.run_id,
            "tool_id": body.tool_id,
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
