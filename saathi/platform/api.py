"""M50 Platform API — FastAPI router. Token via X-Platform-Token or Authorization Bearer.

Read-safe by default. Mutation routes require session + RBAC. No live connectors.
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

# Request used by login / invite accept for client key

from saathi.platform.context import PlatformContextError
from saathi.platform.mission_runtime import (
    MissionRuntimeOrchestrator,
    MissionRuntimeService,
)
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


def _mission_runtime_auth(
    mission_id: str,
    authorization: str | None,
    x_platform_token: str | None,
):
    token = _token(authorization, x_platform_token)
    # MissionRuntimeService performs the existence and tenant/project check so a
    # missing or cross-scope identifier has one non-enumerating NOT_FOUND path.
    return token, _svc().require_context(token)


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
    if exc.code in (
        "APPROVAL_REQUIRED",
        "INVALID_STATE",
        "MISSION_KEY_EXISTS",
        "RESOURCE_BUDGET_EXHAUSTED",
        "REVIEW_REQUIRED",
        "VERIFICATION_REQUIRED",
    ):
        status = 409
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


class MissionRuntimePlanBody(BaseModel):
    definition: dict[str, Any] = Field(default_factory=dict)


class MissionRuntimeRunBody(BaseModel):
    max_cycles: int = Field(default=1, ge=1, le=50)
    timeout_sec: float | None = Field(default=None, gt=0, le=3600)


class MissionRuntimeControlBody(BaseModel):
    reason: str = ""


class MissionRuntimeApprovalBody(BaseModel):
    approval_id: str


class MissionRuntimeEvidenceBody(BaseModel):
    task_id: str = ""
    evidence_type: str
    status: str
    summary: str
    reference: str = ""
    check_name: str = ""
    collected_by: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissionRuntimeReviewBody(BaseModel):
    task_id: str
    verdict: str
    findings: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    reviewer_agent: str = "ReviewerAgent"


class MissionRuntimeCheckpointBody(BaseModel):
    latest_commit: str | None = None
    rollback_sha: str | None = None
    test_status: str | None = None
    browser_status: str | None = None
    known_blockers: list[str] | None = None


class MissionRuntimeCertificationBody(BaseModel):
    verdict: str
    summary: str
    evidence_ids: list[str] = Field(min_length=1, max_length=100)
    limitations: list[str] = Field(default_factory=list, max_length=50)


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


# ── M66 IELTSAlert bounded workflow bodies ──────────────────────────────────
class IELTSProfileBody(BaseModel):
    display_name: str
    timezone: str = "Asia/Kathmandu"
    preferred_language: str = "en"
    idempotency_key: str = ""


class IELTSGoalBody(BaseModel):
    exam_type: str
    target_band: float
    planned_test_date: str
    daily_minutes: int = 30
    idempotency_key: str = ""


class IELTSPracticeBody(BaseModel):
    skill: str
    task_type: str
    prompt: str
    response: str
    duration_seconds: int = 0
    artifact_ref: str = ""
    transcript_ref: str = ""
    idempotency_key: str = ""


class IELTSAlertBody(BaseModel):
    exam_type: str
    test_format: str = "computer"
    preferred_locations: list[str] = Field(default_factory=list)
    date_from: str
    date_to: str
    expires_on: str
    notification_channel: str = "in_app"
    idempotency_key: str = ""


class IELTSStateBody(BaseModel):
    status: str


class IELTSPaymentBody(BaseModel):
    product: str
    amount: str
    currency: str = "NPR"
    payment_method_label: str
    transaction_reference: str
    evidence_ref: str
    submission_note: str = ""
    idempotency_key: str = ""


class IELTSPaymentReviewBody(BaseModel):
    approve: bool
    reason: str


# ── M74 provider-neutral local speech bodies ────────────────────────────────
class VoiceSpeechBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default="", max_length=160)
    source: str = Field(default="assistant", max_length=80)
    text: str = Field(min_length=1, max_length=4_000)
    language: str = Field(default="en-US", max_length=16)
    voice_id: str = Field(default="", max_length=120)
    voice_profile_id: str = Field(default="", max_length=160)
    speaking_rate: float = Field(default=1.0, ge=0.5, le=2.0)
    style: str = Field(default="", max_length=500)
    output_format: str = Field(default="aiff", max_length=8)
    streaming: bool = False
    priority: int = Field(default=50, ge=0, le=100)
    correlation_id: str = Field(default="", max_length=160)
    provider: str = Field(default="auto", max_length=32)
    idempotency_key: str = Field(default="", max_length=120)


class VoiceProfileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=100)
    provider: str = Field(default="auto", max_length=32)
    provider_voice_id: str = Field(default="", max_length=120)
    language: str = Field(default="en-US", max_length=16)
    style: str = Field(default="", max_length=500)
    rate: float = Field(default=1.0, ge=0.5, le=2.0)
    pitch: float = Field(default=0.0, ge=-12.0, le=12.0)
    reference_artifact_id: str = Field(default="", max_length=160)
    cloning_consent_state: str = Field(default="not_requested", max_length=32)
    module_preference: str = Field(default="", max_length=80)
    accessibility_rate: float = Field(default=1.0, ge=0.5, le=2.0)
    status: str = Field(default="active", max_length=20)


class VoiceProfilePatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    provider: str | None = Field(default=None, max_length=32)
    provider_voice_id: str | None = Field(default=None, max_length=120)
    language: str | None = Field(default=None, max_length=16)
    style: str | None = Field(default=None, max_length=500)
    rate: float | None = Field(default=None, ge=0.5, le=2.0)
    pitch: float | None = Field(default=None, ge=-12.0, le=12.0)
    reference_artifact_id: str | None = Field(default=None, max_length=160)
    cloning_consent_state: str | None = Field(default=None, max_length=32)
    module_preference: str | None = Field(default=None, max_length=80)
    accessibility_rate: float | None = Field(default=None, ge=0.5, le=2.0)
    status: str | None = Field(default=None, max_length=20)


class VoiceRuntimeSessionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_mode: str = Field(default="toggle", max_length=40)
    stt_provider: str = Field(default="auto", max_length=40)
    voice_profile_id: str = Field(default="yeti_teacher", max_length=160)
    sample_rate: int = Field(default=16000, ge=8000, le=48000)
    max_recording_seconds: float = Field(default=30.0, ge=1.0, le=60.0)
    silence_timeout_ms: float = Field(default=900.0, ge=200.0, le=5000.0)
    min_speech_ms: float = Field(default=150.0, ge=50.0, le=2000.0)
    conversation_id: str = Field(default="", max_length=160)
    project_id: str = Field(default="", max_length=160)
    locale: str = Field(default="en-US", max_length=16)
    yeti_mode: str = Field(default="general", max_length=40)


class VoiceRuntimeListenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = Field(default="toggle", max_length=40)
    permission_granted: bool = True


class VoiceRuntimeTranscriptBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="", max_length=8_000)
    is_final: bool = True
    partial: bool = False
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    language: str = Field(default="en", max_length=16)


class VoiceRuntimePermissionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    granted: bool = False


class VoiceRuntimePlaybackBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=20)


class VoiceRuntimePlaybackCompleteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    playback_id: str = Field(min_length=1, max_length=160)


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
    service = _svc()
    cancelled = _cancel_user_speech(service, tok)
    voice_cleared = _clear_user_voice_runtime(service, tok)
    return {
        "ok": service.logout(tok),
        "speech_cancelled": cancelled,
        "voice_sessions_cleared": voice_cleared,
    }


def _cancel_user_speech(service, token: str) -> int:
    cancelled = 0
    speech_service = getattr(service, "_speech_service", None)
    if token and speech_service is not None:
        try:
            ctx = service.require_context(token)
            for operation in speech_service.list_operations(ctx):
                if not operation["state"] in {
                    "completed",
                    "cancelled",
                    "failed",
                    "unavailable",
                    "expired",
                }:
                    speech_service.cancel(ctx, operation["operation_id"])
                    cancelled += 1
        except PlatformContextError:
            pass
    return cancelled


def _clear_user_voice_runtime(service, token: str) -> int:
    """Finish live voice sessions on logout/context switch."""
    if not token:
        return 0
    try:
        from saathi.platform.voice.runtime import default_voice_runtime

        runtime = default_voice_runtime(service)
        ctx = service.require_context(token)
        return int(runtime.clear_user_sessions(ctx) or 0)
    except Exception:
        return 0


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


# ── M71 Autonomous Mission Runtime ─────────────────────────────────────────
@router.get("/mission-runtimes/dashboard")
def mission_runtime_dashboard(
    limit: int = 100,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx = _svc().require_context(_token(authorization, x_platform_token))
        return {
            "mission_runtimes": MissionRuntimeService(_svc()).list_dashboard(
                ctx, limit=max(1, min(int(limit), 500))
            )
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/missions/{mission_id}/runtime")
def mission_runtime_detail(
    mission_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        _, ctx = _mission_runtime_auth(
            mission_id, authorization, x_platform_token
        )
        return MissionRuntimeService(_svc()).get(ctx, mission_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.put("/missions/{mission_id}/runtime/plan")
def mission_runtime_plan(
    mission_id: str,
    body: MissionRuntimePlanBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        _, ctx = _mission_runtime_auth(
            mission_id, authorization, x_platform_token
        )
        return MissionRuntimeService(_svc()).plan(
            ctx, mission_id, body.definition
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/missions/{mission_id}/runtime/run")
def mission_runtime_run(
    mission_id: str,
    body: MissionRuntimeRunBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        token, ctx = _mission_runtime_auth(
            mission_id, authorization, x_platform_token
        )
        return MissionRuntimeOrchestrator(_svc()).run_until_stop(
            ctx,
            mission_id,
            token=token,
            max_cycles=body.max_cycles,
            timeout_sec=body.timeout_sec,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/missions/{mission_id}/runtime/pause")
def mission_runtime_pause(
    mission_id: str,
    body: MissionRuntimeControlBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        _, ctx = _mission_runtime_auth(
            mission_id, authorization, x_platform_token
        )
        return {
            "runtime": MissionRuntimeOrchestrator(_svc()).pause(
                ctx, mission_id, reason=body.reason or "operator pause"
            )
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/missions/{mission_id}/runtime/resume")
def mission_runtime_resume(
    mission_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        _, ctx = _mission_runtime_auth(
            mission_id, authorization, x_platform_token
        )
        return {
            "runtime": MissionRuntimeOrchestrator(_svc()).resume(ctx, mission_id)
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/missions/{mission_id}/runtime/cancel")
def mission_runtime_cancel(
    mission_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        token, ctx = _mission_runtime_auth(
            mission_id, authorization, x_platform_token
        )
        return MissionRuntimeOrchestrator(_svc()).cancel(
            ctx, mission_id, token=token
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/missions/{mission_id}/runtime/recover")
def mission_runtime_recover(
    mission_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        token, ctx = _mission_runtime_auth(
            mission_id, authorization, x_platform_token
        )
        return MissionRuntimeOrchestrator(_svc()).recover(
            ctx, mission_id, token=token
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/missions/{mission_id}/runtime/tasks/{task_id}/approval")
def mission_runtime_attach_approval(
    mission_id: str,
    task_id: str,
    body: MissionRuntimeApprovalBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        _, ctx = _mission_runtime_auth(
            mission_id, authorization, x_platform_token
        )
        return {
            "task": MissionRuntimeOrchestrator(_svc()).attach_approval(
                ctx, mission_id, task_id, body.approval_id
            )
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/missions/{mission_id}/runtime/evidence")
def mission_runtime_evidence(
    mission_id: str,
    body: MissionRuntimeEvidenceBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        _, ctx = _mission_runtime_auth(
            mission_id, authorization, x_platform_token
        )
        return {
            "evidence": MissionRuntimeService(_svc()).record_evidence(
                ctx,
                mission_id,
                task_id=body.task_id,
                evidence_type=body.evidence_type,
                status=body.status,
                summary=body.summary,
                reference=body.reference,
                check_name=body.check_name,
                collected_by=body.collected_by,
                metadata=body.metadata,
            )
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/missions/{mission_id}/runtime/reviews")
def mission_runtime_review(
    mission_id: str,
    body: MissionRuntimeReviewBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        _, ctx = _mission_runtime_auth(
            mission_id, authorization, x_platform_token
        )
        return {
            "review": MissionRuntimeService(_svc()).record_review(
                ctx,
                mission_id,
                task_id=body.task_id,
                verdict=body.verdict,
                findings=body.findings,
                evidence_ids=body.evidence_ids,
                reviewer_agent=body.reviewer_agent,
            )
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/missions/{mission_id}/runtime/checkpoints")
def mission_runtime_checkpoint(
    mission_id: str,
    body: MissionRuntimeCheckpointBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        _, ctx = _mission_runtime_auth(
            mission_id, authorization, x_platform_token
        )
        return {
            "checkpoint": MissionRuntimeService(_svc()).create_checkpoint(
                ctx,
                mission_id,
                created_by=ctx.requested_by(),
                latest_commit=body.latest_commit,
                rollback_sha=body.rollback_sha,
                test_status=body.test_status,
                browser_status=body.browser_status,
                known_blockers=body.known_blockers,
            )
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/missions/{mission_id}/runtime/certifications")
def mission_runtime_certification(
    mission_id: str,
    body: MissionRuntimeCertificationBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        _, ctx = _mission_runtime_auth(
            mission_id, authorization, x_platform_token
        )
        return MissionRuntimeService(_svc()).certify(
            ctx,
            mission_id,
            verdict=body.verdict,
            summary=body.summary,
            evidence_ids=body.evidence_ids,
            limitations=body.limitations,
        )
    except PlatformContextError as e:
        raise _err(e) from e


# ── M95+ Agent Orchestration and Planning Runtime ───────────────────────────
class OrchestrationIntakeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1, max_length=4000)
    expected_outcome: str = Field(default="", max_length=2000)
    scope: str = Field(default="", max_length=2000)
    exclusions: str = Field(default="", max_length=2000)
    project_id: str = Field(default="", max_length=160)
    mission_id: str = Field(default="", max_length=160)
    risk_level: str = Field(default="medium", max_length=20)
    domain: str = Field(default="engineering", max_length=40)
    template_id: str = Field(default="", max_length=80)
    production_impact: bool = False
    success_criteria: str = Field(default="", max_length=2000)
    stop_conditions: str = Field(default="", max_length=1000)
    budget_constraints: str = Field(default="", max_length=500)
    time_constraints: str = Field(default="", max_length=500)
    external_dependencies: str = Field(default="", max_length=1000)


class OrchestrationCreateBody(OrchestrationIntakeBody):
    model_config = ConfigDict(extra="forbid")


class OrchestrationCommandBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    orchestration_id: str = Field(default="", max_length=160)


class OrchestrationCertifyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    with_limitations: bool = True
    summary: str = Field(default="", max_length=2000)
    limitations: list[str] = Field(default_factory=list)


class OrchestrationReplanBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="operator_replan", max_length=300)
    objective: str = Field(default="", max_length=4000)
    template_id: str = Field(default="", max_length=80)


def _orchestration_svc():
    from saathi.platform.orchestration import default_orchestration_service

    return default_orchestration_service(_svc())


def _orch_ctx(authorization: str | None, x_platform_token: str | None):
    token = _token(authorization, x_platform_token)
    return _svc().require_context(token), token


@router.get("/orchestration/health")
def orchestration_health(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _orch_ctx(authorization, x_platform_token)
        return {"health": _orchestration_svc().health(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/orchestration/roles")
def orchestration_roles(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _orch_ctx(authorization, x_platform_token)
        return {"roles": _orchestration_svc().list_roles(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/orchestration/templates")
def orchestration_templates(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _orch_ctx(authorization, x_platform_token)
        return {"templates": _orchestration_svc().list_templates(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/orchestration/intake")
def orchestration_intake(
    body: OrchestrationIntakeBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _orch_ctx(authorization, x_platform_token)
        return _orchestration_svc().intake(ctx, body.model_dump())
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/orchestration/compile")
def orchestration_compile(
    body: OrchestrationIntakeBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _orch_ctx(authorization, x_platform_token)
        return _orchestration_svc().compile_plan(ctx, body.model_dump())
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/orchestration")
def orchestration_create(
    body: OrchestrationCreateBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _orch_ctx(authorization, x_platform_token)
        return _orchestration_svc().create(ctx, body.model_dump())
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/orchestration")
def orchestration_list(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _orch_ctx(authorization, x_platform_token)
        return _orchestration_svc().list(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/orchestration/{orchestration_id}")
def orchestration_get(
    orchestration_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _orch_ctx(authorization, x_platform_token)
        return _orchestration_svc().get(ctx, orchestration_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/orchestration/{orchestration_id}/start")
def orchestration_start(
    orchestration_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, token = _orch_ctx(authorization, x_platform_token)
        return _orchestration_svc().start(ctx, orchestration_id, token=token)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/orchestration/{orchestration_id}/pause")
def orchestration_pause(
    orchestration_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _orch_ctx(authorization, x_platform_token)
        return _orchestration_svc().pause(ctx, orchestration_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/orchestration/{orchestration_id}/resume")
def orchestration_resume(
    orchestration_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, token = _orch_ctx(authorization, x_platform_token)
        return _orchestration_svc().resume(ctx, orchestration_id, token=token)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/orchestration/{orchestration_id}/cancel")
def orchestration_cancel(
    orchestration_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _orch_ctx(authorization, x_platform_token)
        return _orchestration_svc().cancel(ctx, orchestration_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/orchestration/{orchestration_id}/replan")
def orchestration_replan(
    orchestration_id: str,
    body: OrchestrationReplanBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _orch_ctx(authorization, x_platform_token)
        payload = body.model_dump() if body else {}
        return _orchestration_svc().replan(ctx, orchestration_id, payload)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/orchestration/{orchestration_id}/checkpoint")
def orchestration_checkpoint(
    orchestration_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _orch_ctx(authorization, x_platform_token)
        return _orchestration_svc().checkpoint(ctx, orchestration_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/orchestration/{orchestration_id}/recover")
def orchestration_recover(
    orchestration_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, token = _orch_ctx(authorization, x_platform_token)
        return _orchestration_svc().recover(ctx, orchestration_id, token=token)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/orchestration/{orchestration_id}/certify")
def orchestration_certify(
    orchestration_id: str,
    body: OrchestrationCertifyBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _orch_ctx(authorization, x_platform_token)
        b = body or OrchestrationCertifyBody()
        return _orchestration_svc().certify(
            ctx,
            orchestration_id,
            with_limitations=b.with_limitations,
            summary=b.summary,
            limitations=b.limitations,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/orchestration/command")
def orchestration_command(
    body: OrchestrationCommandBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _orch_ctx(authorization, x_platform_token)
        return _orchestration_svc().command_from_conversation(
            ctx, body.message, orchestration_id=body.orchestration_id
        )
    except PlatformContextError as e:
        raise _err(e) from e


# ══════════════════════════════════════════════════════════════════════════
# M103–M111 Distributed Worker Execution and Fleet Runtime
# Extends M56 ClusterCoordinator. Loopback Phase A only. No public listeners.
# ══════════════════════════════════════════════════════════════════════════
class FleetWorkerRegisterBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_id: str = Field(default="", max_length=120)
    node_id: str = Field(default="node-local", max_length=120)
    protocol_version: str = Field(default="fleet.v1", max_length=40)
    runtime_version: str = Field(default="m103.fleet.v1", max_length=40)
    process_instance_id: str = Field(default="", max_length=120)
    capability_set: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    bind_host: str = Field(default="127.0.0.1", max_length=64)
    resource_limits: dict[str, Any] = Field(default_factory=dict)
    platform: str = Field(default="darwin", max_length=40)
    architecture: str = Field(default="arm64", max_length=40)
    labels: dict[str, str] = Field(default_factory=dict)
    public_listener: bool = False
    listen_host: str = Field(default="127.0.0.1", max_length=64)


class FleetHeartbeatBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu_pressure: float = 0.0
    memory_pressure: float = 0.0
    disk_pressure: float = 0.0
    queue_depth: int = 0
    active_leases: int = 0
    model_status: str = Field(default="unavailable", max_length=40)
    browser_availability: bool = False
    error_state: str = Field(default="", max_length=200)
    last_successful_action: str = Field(default="", max_length=120)
    protocol_version: str = Field(default="fleet.v1", max_length=40)
    sequence: int = 0


class FleetWorkNodeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_node_id: str = Field(default="", max_length=160)
    id: str = Field(default="", max_length=160)
    required_capabilities: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    role: str = Field(default="", max_length=80)
    approval_state: str = Field(default="not_required", max_length=40)
    approval_required: bool = False
    approval_reference: str = Field(default="", max_length=160)
    dependencies_complete: bool = True
    depends_on: list[str] = Field(default_factory=list)
    incomplete_dependencies: list[str] = Field(default_factory=list)
    risk_classification: str = Field(default="low", max_length=40)
    anti_affinity_workers: list[str] = Field(default_factory=list)
    affinity_workers: list[str] = Field(default_factory=list)
    sod_exclude_workers: list[str] = Field(default_factory=list)
    prior_failure_workers: list[str] = Field(default_factory=list)
    attempt: int = 1
    mission_id: str = Field(default="", max_length=160)
    orchestration_id: str = Field(default="", max_length=160)
    plan_version: str = Field(default="1", max_length=40)
    idempotency_key: str = Field(default="", max_length=200)


class FleetLeaseAcquireBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_node: FleetWorkNodeBody
    worker_id: str = Field(default="", max_length=120)
    ttl_sec: float | None = None
    approval_reference: str = Field(default="", max_length=160)
    mission_id: str = Field(default="", max_length=160)
    orchestration_id: str = Field(default="", max_length=160)
    plan_version: str = Field(default="1", max_length=40)
    m56_execution_id: str = Field(default="", max_length=160)


class FleetLeaseRenewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lease_id: str = Field(min_length=1, max_length=160)
    worker_id: str = Field(min_length=1, max_length=120)
    fencing_token: int
    ttl_sec: float | None = None


class FleetExecuteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lease_id: str = Field(min_length=1, max_length=160)
    worker_id: str = Field(min_length=1, max_length=120)
    fencing_token: int
    arguments: dict[str, Any] = Field(default_factory=dict)
    tool_id: str = Field(default="m49.echo_readonly", max_length=120)


class FleetReconcileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lease_id: str = Field(min_length=1, max_length=160)
    worker_id: str = Field(min_length=1, max_length=120)
    fencing_token: int
    result: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(default="", max_length=200)


class FleetCancelBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str = Field(min_length=1, max_length=40)
    target_id: str = Field(min_length=1, max_length=160)
    reason: str = Field(default="operator_cancel", max_length=300)


class FleetDispatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[FleetWorkNodeBody] = Field(default_factory=list)
    mission_id: str = Field(default="", max_length=160)
    orchestration_id: str = Field(default="", max_length=160)
    plan_version: str = Field(default="1", max_length=40)


class FleetReassignBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_node: FleetWorkNodeBody
    previous_lease_id: str = Field(default="", max_length=160)
    approval_reference: str = Field(default="", max_length=160)


class FleetReasonBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="operator", max_length=300)


class FleetDispatchControlBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paused: bool = True
    reason: str = Field(default="", max_length=300)


class FleetCommandBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    worker_id: str = Field(default="", max_length=120)


class FleetEventBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lease_id: str = Field(min_length=1, max_length=160)
    worker_id: str = Field(min_length=1, max_length=120)
    fencing_token: int
    event_type: str = Field(default="progress", max_length=40)
    sequence: int = 0
    payload: dict[str, Any] = Field(default_factory=dict)


def _fleet_svc():
    from saathi.platform.fleet import default_fleet_runtime

    return default_fleet_runtime(_svc())


def _fleet_ctx(authorization: str | None, x_platform_token: str | None):
    token = _token(authorization, x_platform_token)
    return _svc().require_context(token), token


@router.get("/fleet/health")
def fleet_health(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return {"health": _fleet_svc().health(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/fleet/metrics")
def fleet_metrics(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return {"metrics": _fleet_svc().fleet_metrics(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/fleet/workers")
def fleet_workers_list(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().list_workers(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/workers/register")
def fleet_workers_register(
    body: FleetWorkerRegisterBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().register_worker(ctx, body.model_dump())
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/fleet/workers/{worker_id}")
def fleet_worker_get(
    worker_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().get_worker(ctx, worker_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/workers/{worker_id}/heartbeat")
def fleet_worker_heartbeat(
    worker_id: str,
    body: FleetHeartbeatBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        payload = body.model_dump() if body else {}
        return _fleet_svc().heartbeat(ctx, worker_id, payload)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/workers/{worker_id}/drain")
def fleet_worker_drain(
    worker_id: str,
    body: FleetReasonBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        reason = body.reason if body else "operator_drain"
        return _fleet_svc().drain_worker(ctx, worker_id, reason=reason)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/workers/{worker_id}/quarantine")
def fleet_worker_quarantine(
    worker_id: str,
    body: FleetReasonBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        reason = body.reason if body else "operator_quarantine"
        return _fleet_svc().quarantine_worker(ctx, worker_id, reason=reason)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/workers/{worker_id}/revoke")
def fleet_worker_revoke(
    worker_id: str,
    body: FleetReasonBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        reason = body.reason if body else "operator_revoke"
        return _fleet_svc().revoke_worker(ctx, worker_id, reason=reason)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/match")
def fleet_match(
    body: FleetWorkNodeBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        decision = _fleet_svc().match_worker(ctx, body.model_dump())
        return {"decision": decision.to_public()}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/fleet/schedule")
def fleet_schedule(
    work_node_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().explain_schedule(ctx, work_node_id=work_node_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/leases/acquire")
def fleet_lease_acquire(
    body: FleetLeaseAcquireBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().acquire_lease(
            ctx,
            work_node=body.work_node.model_dump(),
            worker_id=body.worker_id,
            ttl_sec=body.ttl_sec,
            approval_reference=body.approval_reference,
            mission_id=body.mission_id,
            orchestration_id=body.orchestration_id,
            plan_version=body.plan_version,
            m56_execution_id=body.m56_execution_id,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/leases/renew")
def fleet_lease_renew(
    body: FleetLeaseRenewBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().renew_lease(
            ctx,
            lease_id=body.lease_id,
            worker_id=body.worker_id,
            fencing_token=body.fencing_token,
            ttl_sec=body.ttl_sec,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/fleet/leases")
def fleet_leases_list(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().list_leases(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/fleet/leases/{lease_id}/verify")
def fleet_lease_verify(
    lease_id: str,
    worker_id: str = "",
    fencing_token: int | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().verify_lease(
            ctx, lease_id=lease_id, worker_id=worker_id, fencing_token=fencing_token
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/fleet/leases/{lease_id}/request")
def fleet_lease_request(
    lease_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return {"request": _fleet_svc().build_execution_request(ctx, lease_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/execute")
def fleet_execute(
    body: FleetExecuteBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, token = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().execute_leased_work(
            ctx,
            lease_id=body.lease_id,
            worker_id=body.worker_id,
            fencing_token=body.fencing_token,
            token=token,
            tool_id=body.tool_id,
            arguments=body.arguments,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/events")
def fleet_events_ingest(
    body: FleetEventBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().ingest_event(ctx, body.model_dump())
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/fleet/events")
def fleet_events_list(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().list_events(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/reconcile")
def fleet_reconcile(
    body: FleetReconcileBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().reconcile_result(
            ctx,
            lease_id=body.lease_id,
            worker_id=body.worker_id,
            fencing_token=body.fencing_token,
            result=body.result,
            idempotency_key=body.idempotency_key,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/fleet/reconciliations")
def fleet_reconciliations(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().list_reconciliations(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/cancel")
def fleet_cancel(
    body: FleetCancelBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().cancel(
            ctx, scope=body.scope, target_id=body.target_id, reason=body.reason
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/dispatch")
def fleet_dispatch(
    body: FleetDispatchBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().dispatch_ready_nodes(
            ctx,
            nodes=[n.model_dump() for n in body.nodes],
            mission_id=body.mission_id,
            orchestration_id=body.orchestration_id,
            plan_version=body.plan_version,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/dispatch/control")
def fleet_dispatch_control(
    body: FleetDispatchControlBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().set_dispatch_paused(ctx, paused=body.paused, reason=body.reason)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/recover")
def fleet_recover(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().recover_lost_workers(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/reassign")
def fleet_reassign(
    body: FleetReassignBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().reassign_work(
            ctx,
            work_node=body.work_node.model_dump(),
            previous_lease_id=body.previous_lease_id,
            approval_reference=body.approval_reference,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/fleet/recovery")
def fleet_recovery_history(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().recovery_history(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/command")
def fleet_command(
    body: FleetCommandBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().command_from_conversation(
            ctx, body.message, worker_id=body.worker_id
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/fleet/certify")
def fleet_certify(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _fleet_ctx(authorization, x_platform_token)
        return _fleet_svc().certify_fleet(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


# ══════════════════════════════════════════════════════════════════════════
# M112–M120 Skill Ecosystem Runtime — local packages only, no marketplace
# ══════════════════════════════════════════════════════════════════════════
class SkillPackageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_id: str = Field(min_length=1, max_length=120)
    approval_reference: str = Field(default="", max_length=160)


class SkillEnableBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(default="", max_length=40)
    approval_reference: str = Field(default="", max_length=160)


class SkillExecuteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(default="", max_length=40)
    capability: str = Field(default="", max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)
    approval_reference: str = Field(default="", max_length=160)
    idempotency_key: str = Field(default="", max_length=200)


class SkillUpgradeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to_version: str = Field(min_length=1, max_length=40)
    package_id: str = Field(min_length=1, max_length=120)
    approval_reference: str = Field(default="", max_length=160)


class SkillReasonBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="operator", max_length=300)
    version: str = Field(default="", max_length=40)


class SkillCommandBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    skill_id: str = Field(default="", max_length=120)


def _skill_svc():
    from saathi.platform.skills import default_skill_runtime

    return default_skill_runtime(_svc())


def _skill_ctx(authorization: str | None, x_platform_token: str | None):
    token = _token(authorization, x_platform_token)
    return _svc().require_context(token), token


@router.get("/skills/health")
def skills_health(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        return {"health": _skill_svc().health(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/skills")
def skills_list(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        return _skill_svc().list_skills(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/skills/discovered")
def skills_discovered(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        return _skill_svc().list_discovered(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/skills/discover")
def skills_discover(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        return _skill_svc().discover(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/skills/validate")
def skills_validate(
    body: SkillPackageBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        return _skill_svc().validate_package(ctx, package_id=body.package_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/skills/register")
def skills_register(
    body: SkillPackageBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        return _skill_svc().register(
            ctx, package_id=body.package_id, approval_reference=body.approval_reference
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/skills/{skill_id}")
def skills_get(
    skill_id: str,
    version: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        return _skill_svc().get_skill(ctx, skill_id, version=version)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/skills/{skill_id}/enable")
def skills_enable(
    skill_id: str,
    body: SkillEnableBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        b = body or SkillEnableBody()
        return _skill_svc().enable(
            ctx, skill_id, version=b.version, approval_reference=b.approval_reference
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/skills/{skill_id}/disable")
def skills_disable(
    skill_id: str,
    body: SkillEnableBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        b = body or SkillEnableBody()
        return _skill_svc().disable(ctx, skill_id, version=b.version)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/skills/{skill_id}/execute")
def skills_execute(
    skill_id: str,
    body: SkillExecuteBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, token = _skill_ctx(authorization, x_platform_token)
        b = body or SkillExecuteBody()
        return _skill_svc().execute(
            ctx,
            skill_id,
            version=b.version,
            capability=b.capability,
            arguments=b.arguments,
            approval_reference=b.approval_reference,
            idempotency_key=b.idempotency_key,
            token=token,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/skills/{skill_id}/upgrade")
def skills_upgrade(
    skill_id: str,
    body: SkillUpgradeBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        return _skill_svc().upgrade(
            ctx,
            skill_id,
            to_version=body.to_version,
            package_id=body.package_id,
            approval_reference=body.approval_reference,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/skills/{skill_id}/rollback")
def skills_rollback(
    skill_id: str,
    body: SkillReasonBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        reason = body.reason if body else "operator_rollback"
        return _skill_svc().rollback(ctx, skill_id, reason=reason)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/skills/{skill_id}/quarantine")
def skills_quarantine(
    skill_id: str,
    body: SkillReasonBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        b = body or SkillReasonBody()
        return _skill_svc().quarantine(
            ctx, skill_id, reason=b.reason, version=b.version
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/skills/{skill_id}/revoke")
def skills_revoke(
    skill_id: str,
    body: SkillReasonBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        b = body or SkillReasonBody()
        return _skill_svc().revoke(ctx, skill_id, reason=b.reason, version=b.version)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/skills/{skill_id}/executions")
def skills_executions(
    skill_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        return _skill_svc().list_executions(ctx, skill_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/skills/{skill_id}/health")
def skills_skill_health(
    skill_id: str,
    version: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        return _skill_svc().check_health(ctx, skill_id, version=version)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/skills/command")
def skills_command(
    body: SkillCommandBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        return _skill_svc().command_from_conversation(
            ctx, body.message, skill_id=body.skill_id
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/skills/certify")
def skills_certify(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _skill_ctx(authorization, x_platform_token)
        return _skill_svc().certify(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


# ══════════════════════════════════════════════════════════════════════════
# M121–M129 Universal Application Runtime — local apps only, no marketplace
# ══════════════════════════════════════════════════════════════════════════
class AppPackageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_id: str = Field(min_length=1, max_length=120)


class AppVersionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(default="", max_length=40)


class AppFavoriteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    favorite: bool = True


class AppWorkflowBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_id: str = Field(default="", max_length=80)
    approval_reference: str = Field(default="", max_length=160)
    arguments: dict[str, Any] = Field(default_factory=dict)


class AppUpgradeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to_version: str = Field(min_length=1, max_length=40)
    package_id: str = Field(min_length=1, max_length=120)


class AppRestoreBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backup_id: str = Field(min_length=1, max_length=160)


class AppReasonBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="operator", max_length=300)
    version: str = Field(default="", max_length=40)


def _app_svc():
    from saathi.platform.apps import default_app_runtime

    return default_app_runtime(_svc())


def _app_ctx(authorization: str | None, x_platform_token: str | None):
    token = _token(authorization, x_platform_token)
    return _svc().require_context(token), token


@router.get("/apps/health")
def apps_health(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        return {"health": _app_svc().health(ctx)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/apps/launcher")
def apps_launcher(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        return _app_svc().launcher(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/apps")
def apps_list(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        return _app_svc().list_apps(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/apps/discover")
def apps_discover(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        return _app_svc().discover(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/apps/validate")
def apps_validate(
    body: AppPackageBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        return _app_svc().validate_package(ctx, package_id=body.package_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/apps/register")
def apps_register(
    body: AppPackageBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        return _app_svc().register(ctx, package_id=body.package_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/apps/{app_id}")
def apps_get(
    app_id: str,
    version: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        return _app_svc().get_app(ctx, app_id, version=version)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/apps/{app_id}/enable")
def apps_enable(
    app_id: str,
    body: AppVersionBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        v = body.version if body else ""
        return _app_svc().enable(ctx, app_id, version=v)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/apps/{app_id}/disable")
def apps_disable(
    app_id: str,
    body: AppVersionBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        v = body.version if body else ""
        return _app_svc().disable(ctx, app_id, version=v)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/apps/{app_id}/launch")
def apps_launch(
    app_id: str,
    body: AppVersionBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        v = body.version if body else ""
        return _app_svc().launch(ctx, app_id, version=v)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/apps/{app_id}/favorite")
def apps_favorite(
    app_id: str,
    body: AppFavoriteBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        fav = body.favorite if body else True
        return _app_svc().set_favorite(ctx, app_id, favorite=fav)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/apps/{app_id}/workflow")
def apps_workflow(
    app_id: str,
    body: AppWorkflowBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        b = body or AppWorkflowBody()
        return _app_svc().run_workflow(
            ctx,
            app_id,
            workflow_id=b.workflow_id,
            approval_reference=b.approval_reference,
            arguments=b.arguments,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/apps/{app_id}/backup")
def apps_backup(
    app_id: str,
    body: AppReasonBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        reason = body.reason if body else "operator"
        return _app_svc().backup(ctx, app_id, reason=reason)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/apps/{app_id}/backups")
def apps_backups(
    app_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        return _app_svc().list_backups(ctx, app_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/apps/{app_id}/restore")
def apps_restore(
    app_id: str,
    body: AppRestoreBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        return _app_svc().restore(ctx, app_id, backup_id=body.backup_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/apps/{app_id}/upgrade")
def apps_upgrade(
    app_id: str,
    body: AppUpgradeBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        return _app_svc().upgrade(
            ctx, app_id, to_version=body.to_version, package_id=body.package_id
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/apps/{app_id}/rollback")
def apps_rollback(
    app_id: str,
    body: AppReasonBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        reason = body.reason if body else "operator"
        return _app_svc().rollback(ctx, app_id, reason=reason)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/apps/{app_id}/quarantine")
def apps_quarantine(
    app_id: str,
    body: AppReasonBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        b = body or AppReasonBody()
        return _app_svc().quarantine(ctx, app_id, reason=b.reason, version=b.version)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/apps/{app_id}/health")
def apps_app_health(
    app_id: str,
    version: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        return _app_svc().check_health(ctx, app_id, version=version)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/apps/recover")
def apps_recover(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        return _app_svc().recover(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/apps/certify")
def apps_certify(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        ctx, _ = _app_ctx(authorization, x_platform_token)
        return _app_svc().certify(ctx)
    except PlatformContextError as e:
        raise _err(e) from e


# ══════════════════════════════════════════════════════════════════════════
# M130+ HCG Native Operations Application (local-first, no production)
# ══════════════════════════════════════════════════════════════════════════
class HcgOrderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lines: list[dict[str, Any]] = Field(default_factory=list)
    channel: str = Field(default="dine_in", max_length=40)
    customer_id: str = Field(default="", max_length=120)
    table_ref: str = Field(default="", max_length=40)
    notes: str = Field(default="", max_length=500)
    discount_minor: int = Field(default=0, ge=0)
    idempotency_key: str = Field(default="", max_length=120)
    shift_id: str = Field(default="", max_length=120)
    app_instance_id: str = Field(default="", max_length=160)


class HcgPaymentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str = Field(min_length=1, max_length=120)
    amount_minor: int = Field(ge=0)
    method: str = Field(min_length=1, max_length=40)
    qr_reference: str = Field(default="", max_length=120)
    customer_id: str = Field(default="", max_length=120)
    shift_id: str = Field(default="", max_length=120)
    idempotency_key: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=200)
    app_instance_id: str = Field(default="", max_length=160)


class HcgShiftOpenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opening_cash_minor: int = Field(ge=0)
    register_id: str = Field(default="reg-1", max_length=80)
    idempotency_key: str = Field(default="", max_length=120)
    app_instance_id: str = Field(default="", max_length=160)


class HcgShiftCloseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actual_cash_minor: int = Field(ge=0)
    explanation: str = Field(default="", max_length=500)
    app_instance_id: str = Field(default="", max_length=160)


class HcgKitchenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to_state: str = Field(min_length=1, max_length=40)
    app_instance_id: str = Field(default="", max_length=160)


class HcgExpenseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str = Field(min_length=1, max_length=80)
    amount_minor: int = Field(ge=1)
    description: str = Field(default="", max_length=500)
    payment_source: str = Field(default="CASH", max_length=40)
    shift_id: str = Field(default="", max_length=120)
    idempotency_key: str = Field(default="", max_length=120)
    app_instance_id: str = Field(default="", max_length=160)


class HcgPurchaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_id: str = Field(min_length=1, max_length=120)
    lines: list[dict[str, Any]] = Field(default_factory=list)
    credit_minor: int = Field(default=0, ge=0)
    paid_minor: int = Field(default=0, ge=0)
    payment_method: str = Field(default="CASH", max_length=40)
    idempotency_key: str = Field(default="", max_length=120)
    app_instance_id: str = Field(default="", max_length=160)


class HcgRepaymentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: str = Field(min_length=1, max_length=120)
    amount_minor: int = Field(ge=1)
    method: str = Field(default="CASH", max_length=40)
    shift_id: str = Field(default="", max_length=120)
    idempotency_key: str = Field(default="", max_length=120)
    app_instance_id: str = Field(default="", max_length=160)


class HcgStockBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inventory_item_id: str = Field(min_length=1, max_length=120)
    qty_delta: int
    reason: str = Field(min_length=1, max_length=200)
    movement_type: str = Field(default="ADJUSTMENT_IN", max_length=40)
    approval_reference: str = Field(default="", max_length=160)
    app_instance_id: str = Field(default="", max_length=160)


class HcgMenuBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    category_id: str = Field(default="", max_length=120)
    price_minor: int = Field(ge=0)
    available: bool = True
    favorite: bool = False
    recipe_id: str = Field(default="", max_length=120)
    station: str = Field(default="main", max_length=40)
    item_id: str = Field(default="", max_length=120)
    app_instance_id: str = Field(default="", max_length=160)


class HcgQuestionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=500)
    app_instance_id: str = Field(default="", max_length=160)


class HcgReverseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_reference: str = Field(default="", max_length=160)
    reason: str = Field(default="", max_length=200)
    app_instance_id: str = Field(default="", max_length=160)


class HcgRestoreBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload: dict[str, Any] = Field(default_factory=dict)
    approval_reference: str = Field(default="", max_length=160)
    app_instance_id: str = Field(default="", max_length=160)


def _hcg_svc():
    from saathi.platform.hcg import default_hcg_service

    return default_hcg_service(_svc())


def _hcg_ctx(authorization: str | None, x_platform_token: str | None):
    token = _token(authorization, x_platform_token)
    return _svc().require_context(token)


def _hcg_err(exc: Exception) -> HTTPException:
    if isinstance(exc, PlatformContextError):
        return _err(exc)
    from saathi.platform.hcg.models import HcgValidationError
    from saathi.platform.hcg.money import MoneyError

    if isinstance(exc, (HcgValidationError, MoneyError)):
        code = getattr(exc, "code", "HCG_ERROR")
        return HTTPException(status_code=400, detail={"code": code, "message": str(exc)})
    return HTTPException(status_code=500, detail={"code": "HCG_INTERNAL", "message": "error"})


@router.get("/apps/hcg/dashboard")
def hcg_dashboard(
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {"dashboard": _hcg_svc().dashboard(_hcg_ctx(authorization, x_platform_token), app_instance_id=app_instance_id)}
    except Exception as e:
        raise _hcg_err(e) from e


@router.get("/apps/hcg/health")
def hcg_health(
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {"health": _hcg_svc().health(_hcg_ctx(authorization, x_platform_token), app_instance_id=app_instance_id)}
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/seed")
def hcg_seed(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().ensure_seeded(_hcg_ctx(authorization, x_platform_token))
    except Exception as e:
        raise _hcg_err(e) from e


@router.get("/apps/hcg/menu")
def hcg_menu(
    q: str = "",
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().list_menu(_hcg_ctx(authorization, x_platform_token), app_instance_id=app_instance_id, q=q)
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/menu")
def hcg_menu_upsert(
    body: HcgMenuBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().upsert_menu_item(
            _hcg_ctx(authorization, x_platform_token),
            name=body.name, category_id=body.category_id, price_minor=body.price_minor,
            available=body.available, favorite=body.favorite, recipe_id=body.recipe_id,
            station=body.station, item_id=body.item_id, app_instance_id=body.app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.get("/apps/hcg/orders")
def hcg_orders(
    status: str = "",
    q: str = "",
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().list_orders(
            _hcg_ctx(authorization, x_platform_token),
            app_instance_id=app_instance_id, status=status, q=q,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/orders")
def hcg_order_create(
    body: HcgOrderBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().create_order(
            _hcg_ctx(authorization, x_platform_token),
            lines=body.lines, channel=body.channel, customer_id=body.customer_id,
            table_ref=body.table_ref, notes=body.notes, discount_minor=body.discount_minor,
            idempotency_key=body.idempotency_key, shift_id=body.shift_id,
            app_instance_id=body.app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.get("/apps/hcg/orders/{order_id}")
def hcg_order_get(
    order_id: str,
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().get_order(
            _hcg_ctx(authorization, x_platform_token), order_id, app_instance_id=app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/orders/{order_id}/kitchen")
def hcg_order_kitchen(
    order_id: str,
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().submit_to_kitchen(
            _hcg_ctx(authorization, x_platform_token), order_id, app_instance_id=app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/payments")
def hcg_payment(
    body: HcgPaymentBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().record_payment(
            _hcg_ctx(authorization, x_platform_token),
            order_id=body.order_id, amount_minor=body.amount_minor, method=body.method,
            qr_reference=body.qr_reference, customer_id=body.customer_id,
            shift_id=body.shift_id, idempotency_key=body.idempotency_key,
            note=body.note, app_instance_id=body.app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/payments/{payment_id}/reverse")
def hcg_payment_reverse(
    payment_id: str,
    body: HcgReverseBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().reverse_payment(
            _hcg_ctx(authorization, x_platform_token), payment_id,
            approval_reference=body.approval_reference, reason=body.reason,
            app_instance_id=body.app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.get("/apps/hcg/kitchen")
def hcg_kitchen(
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().list_kitchen(_hcg_ctx(authorization, x_platform_token), app_instance_id=app_instance_id)
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/kitchen/{ticket_id}/transition")
def hcg_kitchen_transition(
    ticket_id: str,
    body: HcgKitchenBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().transition_kitchen(
            _hcg_ctx(authorization, x_platform_token), ticket_id,
            to_state=body.to_state, app_instance_id=body.app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.get("/apps/hcg/shifts")
def hcg_shifts(
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().list_shifts(_hcg_ctx(authorization, x_platform_token), app_instance_id=app_instance_id)
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/shifts/open")
def hcg_shift_open(
    body: HcgShiftOpenBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().open_shift(
            _hcg_ctx(authorization, x_platform_token),
            opening_cash_minor=body.opening_cash_minor, register_id=body.register_id,
            idempotency_key=body.idempotency_key, app_instance_id=body.app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/shifts/{shift_id}/close")
def hcg_shift_close(
    shift_id: str,
    body: HcgShiftCloseBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().close_shift(
            _hcg_ctx(authorization, x_platform_token), shift_id,
            actual_cash_minor=body.actual_cash_minor, explanation=body.explanation,
            app_instance_id=body.app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.get("/apps/hcg/inventory")
def hcg_inventory(
    q: str = "",
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().list_inventory(
            _hcg_ctx(authorization, x_platform_token), app_instance_id=app_instance_id, q=q,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/inventory/adjust")
def hcg_inventory_adjust(
    body: HcgStockBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().stock_adjust(
            _hcg_ctx(authorization, x_platform_token),
            inventory_item_id=body.inventory_item_id, qty_delta=body.qty_delta,
            reason=body.reason, movement_type=body.movement_type,
            approval_reference=body.approval_reference, app_instance_id=body.app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.get("/apps/hcg/customers")
def hcg_customers(
    q: str = "",
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().list_customers(
            _hcg_ctx(authorization, x_platform_token), app_instance_id=app_instance_id, q=q,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.get("/apps/hcg/customers/{customer_id}/statement")
def hcg_customer_statement(
    customer_id: str,
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().customer_statement(
            _hcg_ctx(authorization, x_platform_token), customer_id, app_instance_id=app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/credit/repay")
def hcg_credit_repay(
    body: HcgRepaymentBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().record_repayment(
            _hcg_ctx(authorization, x_platform_token),
            customer_id=body.customer_id, amount_minor=body.amount_minor,
            method=body.method, shift_id=body.shift_id,
            idempotency_key=body.idempotency_key, app_instance_id=body.app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.get("/apps/hcg/suppliers")
def hcg_suppliers(
    q: str = "",
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().list_suppliers(
            _hcg_ctx(authorization, x_platform_token), app_instance_id=app_instance_id, q=q,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.get("/apps/hcg/suppliers/{supplier_id}/statement")
def hcg_supplier_statement(
    supplier_id: str,
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().supplier_statement(
            _hcg_ctx(authorization, x_platform_token), supplier_id, app_instance_id=app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/purchases")
def hcg_purchase(
    body: HcgPurchaseBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().create_purchase(
            _hcg_ctx(authorization, x_platform_token),
            supplier_id=body.supplier_id, lines=body.lines,
            credit_minor=body.credit_minor, paid_minor=body.paid_minor,
            payment_method=body.payment_method, idempotency_key=body.idempotency_key,
            app_instance_id=body.app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/expenses")
def hcg_expense(
    body: HcgExpenseBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().create_expense(
            _hcg_ctx(authorization, x_platform_token),
            category=body.category, amount_minor=body.amount_minor,
            description=body.description, payment_source=body.payment_source,
            shift_id=body.shift_id, idempotency_key=body.idempotency_key,
            app_instance_id=body.app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.get("/apps/hcg/expenses")
def hcg_expenses_list(
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().list_expenses(_hcg_ctx(authorization, x_platform_token), app_instance_id=app_instance_id)
    except Exception as e:
        raise _hcg_err(e) from e


@router.get("/apps/hcg/reports")
def hcg_reports(
    kind: str = "daily_sales",
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().report(
            _hcg_ctx(authorization, x_platform_token), kind=kind, app_instance_id=app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.get("/apps/hcg/search")
def hcg_search(
    q: str = "",
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().search(
            _hcg_ctx(authorization, x_platform_token), q=q, app_instance_id=app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.get("/apps/hcg/notifications")
def hcg_notifications(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().list_notifications(_hcg_ctx(authorization, x_platform_token))
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/yeti")
def hcg_yeti(
    body: HcgQuestionBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().grounded_answer(
            _hcg_ctx(authorization, x_platform_token), body.question,
            app_instance_id=body.app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/backup")
def hcg_backup(
    app_instance_id: str = "",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {"backup": _hcg_svc().export_backup_payload(
            _hcg_ctx(authorization, x_platform_token), app_instance_id=app_instance_id,
        )}
    except Exception as e:
        raise _hcg_err(e) from e


@router.post("/apps/hcg/restore")
def hcg_restore(
    body: HcgRestoreBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _hcg_svc().restore_payload(
            _hcg_ctx(authorization, x_platform_token), body.payload,
            approval_reference=body.approval_reference, app_instance_id=body.app_instance_id,
        )
    except Exception as e:
        raise _hcg_err(e) from e


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
        service = _svc()
        token = _token(authorization, x_platform_token)
        _cancel_user_speech(service, token)
        _clear_user_voice_runtime(service, token)
        return service.select_workspace(
            token,
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


# ══════════════════════════════════════════════════════════════════════════
# M62.4 — strategy + deterministic backtesting endpoints. Authenticated,
# tenant-scoped, audited, bounded. SIMULATION ONLY — NO order/broker/execution
# actions, NO leverage, NO buy/sell. A passing backtest is NOT trade approval.
# ══════════════════════════════════════════════════════════════════════════
def _ssvc():
    from saathi.platform.strategy import StrategyService, StrategyStore
    from saathi.platform.research import ResearchStore
    return StrategyService(StrategyStore(), research_store=ResearchStore()).bind_audit(_svc().store)


def _sctx(a, x):
    return _svc().require_context(_token(a, x))


class StrategyBody(BaseModel):
    name: str
    strategy_type: str = "MOMENTUM"
    instrument: str = "TRENDING"
    instrument_universe: list[str] = Field(default_factory=list)
    timeframe: str = "1d"
    description: str = ""
    features: list[dict[str, Any]] = Field(default_factory=list)
    signals: list[dict[str, Any]] = Field(default_factory=list)
    sizing: dict[str, Any] = Field(default_factory=dict)
    benchmark: str = ""
    cost_tier: str = "realistic"
    warmup_bars: int = 0
    risk_max_position_fraction: str = "1"


class StrategyUpdateBody(StrategyBody):
    expected_version: int


class StrategyStatusBody(BaseModel):
    status: str
    expected_version: int


class ResearchLinkBody(BaseModel):
    project_id: str
    thesis_version: int | None = None
    expected_version: int


class VersionBody(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class BacktestBody(BaseModel):
    dataset: str = "TRENDING"
    cost_tier: str = "realistic"
    seed: int = 0
    n: int = 30


class CertifyBody(BaseModel):
    decision: str = "validate"        # validate | reject
    expected_version: int


@router.post("/strategies")
def strat_create(body: StrategyBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"strategy": _ssvc().create_strategy(_sctx(authorization, x_platform_token), body.model_dump())}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/strategies")
def strat_list(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"strategies": _ssvc().list_strategies(_sctx(authorization, x_platform_token))}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/strategies/{sid}")
def strat_get(sid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"strategy": _ssvc().get_strategy(_sctx(authorization, x_platform_token), sid)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.patch("/strategies/{sid}")
def strat_update(sid: str, body: StrategyUpdateBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        data = body.model_dump(); ev = data.pop("expected_version")
        return {"strategy": _ssvc().update_strategy(_sctx(authorization, x_platform_token), sid, data, expected_version=ev)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/strategies/{sid}/status")
def strat_status(sid: str, body: StrategyStatusBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"strategy": _ssvc().set_status(_sctx(authorization, x_platform_token), sid, body.status, expected_version=body.expected_version)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/strategies/{sid}/research-link")
def strat_research_link(sid: str, body: ResearchLinkBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"result": _ssvc().link_research(_sctx(authorization, x_platform_token), sid, project_id=body.project_id, thesis_version=body.thesis_version, expected_version=body.expected_version)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/strategies/{sid}/versions")
def strat_version_create(sid: str, body: VersionBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"version": _ssvc().create_version(_sctx(authorization, x_platform_token), sid, parameters=body.parameters, rationale=body.rationale)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/strategies/{sid}/versions")
def strat_versions(sid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"versions": _ssvc().list_versions(_sctx(authorization, x_platform_token), sid)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/strategies/{sid}/versions/{version}")
def strat_version_get(sid: str, version: int, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"version": _ssvc().get_version(_sctx(authorization, x_platform_token), sid, version)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/strategies/{sid}/certify")
def strat_certify(sid: str, body: CertifyBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"strategy": _ssvc().certify_strategy(_sctx(authorization, x_platform_token), sid, expected_version=body.expected_version, decision=body.decision)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/strategies/{sid}/backtests")
def strat_bt_create(sid: str, body: BacktestBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"backtest": _ssvc().create_backtest(_sctx(authorization, x_platform_token), sid, dataset=body.dataset, cost_tier=body.cost_tier, seed=body.seed, n=body.n)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/strategies/{sid}/backtests")
def strat_bt_list(sid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"backtests": _ssvc().list_backtests(_sctx(authorization, x_platform_token), sid)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/backtests/{rid}")
def bt_get(rid: str, sid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"backtest": _ssvc().get_backtest(_sctx(authorization, x_platform_token), sid, rid)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/strategies/{sid}/backtests/{rid}/run")
def bt_run(sid: str, rid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"backtest": _ssvc().run_backtest(_sctx(authorization, x_platform_token), sid, rid)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/strategies/{sid}/backtests/{rid}/cancel")
def bt_cancel(sid: str, rid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"backtest": _ssvc().cancel_backtest(_sctx(authorization, x_platform_token), sid, rid)}
    except PlatformContextError as e:
        raise _err(e) from e


def _bt_evidence(kind):
    def handler(sid: str, rid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
        try:
            svc = _ssvc(); ctx = _sctx(authorization, x_platform_token)
            return {kind: getattr(svc, kind)(ctx, sid, rid)}
        except PlatformContextError as e:
            raise _err(e) from e
    return handler


router.add_api_route("/strategies/{sid}/backtests/{rid}/metrics", _bt_evidence("metrics"), methods=["GET"])
router.add_api_route("/strategies/{sid}/backtests/{rid}/trades", _bt_evidence("trades"), methods=["GET"])
router.add_api_route("/strategies/{sid}/backtests/{rid}/equity", _bt_evidence("equity"), methods=["GET"])
router.add_api_route("/strategies/{sid}/backtests/{rid}/validation", _bt_evidence("validation"), methods=["GET"])
router.add_api_route("/strategies/{sid}/backtests/{rid}/stress", _bt_evidence("stress"), methods=["GET"])
router.add_api_route("/strategies/{sid}/backtests/{rid}/sensitivity", _bt_evidence("sensitivity"), methods=["GET"])
router.add_api_route("/strategies/{sid}/backtests/{rid}/manifest", _bt_evidence("manifest"), methods=["GET"])


# ══════════════════════════════════════════════════════════════════════════
# M62.5 — deterministic paper broker + durable order lifecycle. Authenticated,
# tenant-scoped, audited. PAPER environment ONLY, long-only. Broker MUTATIONS go
# through PlatformAgentRuntime → ExecutionGateway → registered paper-trading tool;
# NO API route invokes the broker directly. NO live execution, NO leverage/margin/
# short/derivatives. A paper fill is a simulation event, not a live trade.
# ══════════════════════════════════════════════════════════════════════════
def _ppsvc():
    from saathi.platform.paper_trading import default_paper_service
    return default_paper_service()


def _ppctx(a, x):
    return _svc().require_context(_token(a, x))


def _pp_gateway_result(r):
    """Translate a ToolExecutionResult from the paper-broker tool into an API result."""
    from saathi.tool_runtime.contracts import ToolOutcomeClass
    if r.outcome_class == ToolOutcomeClass.SUCCESS_CONFIRMED:
        return r.data
    status = 400
    if r.outcome_class in (ToolOutcomeClass.PROHIBITED,):
        status = 403
    raise HTTPException(status_code=status, detail={"code": r.error_code or "PAPER_SUBMIT_FAILED",
                                                    "message": r.safe_message or "paper broker action rejected"})


class PaperAccountBody(BaseModel):
    name: str = "paper account"
    starting_cash: str = "100000"
    base_currency: str = "USD"
    project_id: str = ""


class PaperHaltBody(BaseModel):
    expected_version: int
    reason: str = "manual halt"


class PaperMarket(BaseModel):
    symbol: str
    bid: str
    ask: str
    last: str | None = None
    liquidity: str = "1000000"
    quality: str = "VALID"
    market_state: str = "OPEN"
    ts: float = 0.0
    ref: str = ""


class PaperIntentBody(BaseModel):
    account_id: str
    symbol: str
    side: str
    order_type: str = "MARKET"
    quantity: str
    limit_price: str | None = None
    time_in_force: str = "DAY"
    idempotency_key: str = ""
    reason: str = ""
    strategy_ref: str = ""
    thesis_ref: str = ""
    market_data_ref: str = ""


class PaperSubmitBody(BaseModel):
    market: PaperMarket
    approval_id: str = ""
    idempotency_key: str = ""


class PaperCancelBody(BaseModel):
    idempotency_key: str = ""


class PaperProcessBody(BaseModel):
    market: PaperMarket


@router.post("/paper/accounts")
def paper_acct_create(body: PaperAccountBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"account": _ppsvc().create_account(_ppctx(authorization, x_platform_token), name=body.name, starting_cash=body.starting_cash, base_currency=body.base_currency, project_id=body.project_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/accounts")
def paper_acct_list(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"accounts": _ppsvc().list_accounts(_ppctx(authorization, x_platform_token))}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/accounts/{account_id}")
def paper_acct_get(account_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"account": _ppsvc().get_account(_ppctx(authorization, x_platform_token), account_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/paper/accounts/{account_id}/halt")
def paper_acct_halt(account_id: str, body: PaperHaltBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"account": _ppsvc().halt_account(_ppctx(authorization, x_platform_token), account_id, expected_version=body.expected_version, reason=body.reason)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/accounts/{account_id}/positions")
def paper_positions(account_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"positions": _ppsvc().list_positions(_ppctx(authorization, x_platform_token), account_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/accounts/{account_id}/ledger")
def paper_ledger(account_id: str, limit: int = 500, offset: int = 0, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"ledger": _ppsvc().ledger(_ppctx(authorization, x_platform_token), account_id, limit=limit, offset=offset)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/accounts/{account_id}/summary")
def paper_summary(account_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"summary": _ppsvc().summary(_ppctx(authorization, x_platform_token), account_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/accounts/{account_id}/command-snapshot")
def paper_command_snapshot(account_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    """Canonical ledger snapshot for production Hybrid Command (read-only)."""
    try:
        return _ppsvc().command_center_snapshot(_ppctx(authorization, x_platform_token), account_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/accounts/{account_id}/risk")
def paper_account_risk(account_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    """Independent PortfolioRiskEngine contract for production Command (read-only)."""
    try:
        return _ppsvc().paper_risk_snapshot(_ppctx(authorization, x_platform_token), account_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/accounts/{account_id}/proposals")
def paper_account_proposals(account_id: str, limit: int = 10, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    """Latest portfolio construction proposals for fund (read-only; no execution)."""
    try:
        return _ppsvc().list_portfolio_proposals(_ppctx(authorization, x_platform_token), account_id, limit=limit)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/paper/order-intents")
def paper_intent_create(body: PaperIntentBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"intent": _ppsvc().create_intent(_ppctx(authorization, x_platform_token), account_id=body.account_id, symbol=body.symbol, side=body.side, order_type=body.order_type, quantity=body.quantity, limit_price=body.limit_price, time_in_force=body.time_in_force, idempotency_key=body.idempotency_key, reason=body.reason, strategy_ref=body.strategy_ref, thesis_ref=body.thesis_ref, market_data_ref=body.market_data_ref)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/order-intents")
def paper_intent_list(account_id: str = "", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"intents": _ppsvc().list_intents(_ppctx(authorization, x_platform_token), account_id=account_id or None)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/order-intents/{intent_id}")
def paper_intent_get(intent_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"intent": _ppsvc().get_intent(_ppctx(authorization, x_platform_token), intent_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/paper/order-intents/{intent_id}/submit")
def paper_intent_submit(intent_id: str, body: PaperSubmitBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    from saathi.platform.paper_trading import orchestration
    from saathi.platform.models import PlatformPermission
    try:
        ctx = _ppctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ORDER_SUBMIT)
        r = orchestration.submit_via_gateway(ctx, intent_id=intent_id, market=body.market.model_dump(), approval_id=body.approval_id, idempotency_key=body.idempotency_key)
        return {"result": _pp_gateway_result(r)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/paper/orders/{order_id}/cancel")
def paper_order_cancel(order_id: str, body: PaperCancelBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    from saathi.platform.paper_trading import orchestration
    from saathi.platform.models import PlatformPermission
    try:
        ctx = _ppctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ORDER_CANCEL)
        r = orchestration.cancel_via_gateway(ctx, order_id=order_id, idempotency_key=body.idempotency_key)
        return {"result": _pp_gateway_result(r)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/paper/orders/{order_id}/process-event")
def paper_order_process(order_id: str, body: PaperProcessBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    from saathi.platform.paper_trading import orchestration
    from saathi.platform.models import PlatformPermission
    try:
        ctx = _ppctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ORDER_SUBMIT)
        r = orchestration.process_event_via_gateway(ctx, order_id=order_id, market=body.market.model_dump())
        return {"result": _pp_gateway_result(r)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/orders")
def paper_orders_list(account_id: str = "", limit: int = 200, offset: int = 0, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"orders": _ppsvc().list_orders(_ppctx(authorization, x_platform_token), account_id=account_id or None, limit=limit, offset=offset)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/orders/{order_id}")
def paper_order_get(order_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"order": _ppsvc().get_order(_ppctx(authorization, x_platform_token), order_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/orders/{order_id}/fills")
def paper_order_fills(order_id: str, limit: int = 1000, offset: int = 0, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"fills": _ppsvc().list_fills(_ppctx(authorization, x_platform_token), order_id, limit=limit, offset=offset)}
    except PlatformContextError as e:
        raise _err(e) from e


# ══════════════════════════════════════════════════════════════════════════
# M62.7 — automated paper-safety circuit breakers, sweeps, alerts, acknowledgement,
# and fail-closed reset controls. Authenticated, tenant-scoped, audited. Breaker
# MUTATIONS (trip/acknowledge/request-reset/reset/sweep) route through
# PlatformAgentRuntime → ExecutionGateway → registered paper_safety.* tool; NO API
# route mutates breaker state directly. PAPER only; no live/production/repair path.
# ══════════════════════════════════════════════════════════════════════════
def _safesvc():
    from saathi.platform.safety import default_safety_service
    return default_safety_service()


class SafetyBreakerBody(BaseModel):
    breaker_type: str
    scope: str
    scope_ref: str = ""
    threshold: str = "0"
    warning_threshold: str | None = None
    window_seconds: int = 0
    min_samples: int = 0
    severity: str = "ERROR"
    open_order_policy: str | None = None
    timezone: str = "UTC"
    requires_config: bool = False


class SafetyBreakerPatch(BaseModel):
    expected_version: int
    updates: dict = {}


class SafetyManualTripBody(BaseModel):
    scope: str
    scope_ref: str = ""
    reason: str = "manual kill switch"


class SafetyAckBody(BaseModel):
    note: str = ""
    evidence_reviewed: bool = False


class SafetyResetRequestBody(BaseModel):
    reason: str
    approval_id: str = ""
    idempotency_key: str = ""


class SafetyResetExecBody(BaseModel):
    approval_id: str = ""
    expires_at: float = 0.0


@router.get("/paper/safety/breakers")
def safety_breakers_list(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"breakers": _safesvc().list_breakers(_ppctx(authorization, x_platform_token))}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/paper/safety/breakers")
def safety_breaker_create(body: SafetyBreakerBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"breaker": _safesvc().create_breaker(_ppctx(authorization, x_platform_token), **body.model_dump())}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/safety/breakers/{definition_id}")
def safety_breaker_get(definition_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"breaker": _safesvc().get_breaker(_ppctx(authorization, x_platform_token), definition_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.patch("/paper/safety/breakers/{definition_id}")
def safety_breaker_patch(definition_id: str, body: SafetyBreakerPatch, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"breaker": _safesvc().update_breaker(_ppctx(authorization, x_platform_token), definition_id, expected_version=body.expected_version, updates=body.updates)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/safety/states")
def safety_states(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"states": _safesvc().list_states(_ppctx(authorization, x_platform_token))}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/safety/trips")
def safety_trips(definition_id: str = "", limit: int = 200, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"trips": _safesvc().list_trips(_ppctx(authorization, x_platform_token), definition_id=definition_id or None, limit=limit)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/safety/trips/{trip_id}")
def safety_trip_get(trip_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"trip": _safesvc().get_trip(_ppctx(authorization, x_platform_token), trip_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/safety/alerts")
def safety_alerts(limit: int = 200, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"alerts": _safesvc().list_alerts(_ppctx(authorization, x_platform_token), limit=limit)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/safety/sweeps")
def safety_sweeps(limit: int = 100, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"sweeps": _safesvc().list_sweeps(_ppctx(authorization, x_platform_token), limit=limit)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/safety/sweeps/{sweep_id}")
def safety_sweep_get(sweep_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"sweep": _safesvc().get_sweep(_ppctx(authorization, x_platform_token), sweep_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/paper/safety/sweeps")
def safety_sweep_run(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    from saathi.platform.safety import orchestration
    from saathi.platform.models import PlatformPermission
    try:
        ctx = _ppctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_SWEEP)
        r = orchestration.run_sweep_via_gateway(ctx)
        return {"result": _pp_gateway_result(r)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/paper/safety/trips/manual")
def safety_manual_trip(body: SafetyManualTripBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    from saathi.platform.safety import orchestration
    from saathi.platform.models import PlatformPermission
    try:
        ctx = _ppctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_TRIP)
        r = orchestration.trip_via_gateway(ctx, scope=body.scope, scope_ref=body.scope_ref, reason=body.reason)
        return {"result": _pp_gateway_result(r)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/paper/safety/trips/{trip_id}/acknowledge")
def safety_acknowledge(trip_id: str, body: SafetyAckBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    from saathi.platform.safety import orchestration
    from saathi.platform.models import PlatformPermission
    try:
        ctx = _ppctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_ACKNOWLEDGE)
        r = orchestration.acknowledge_via_gateway(ctx, trip_id=trip_id, note=body.note, evidence_reviewed=body.evidence_reviewed)
        return {"result": _pp_gateway_result(r)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/paper/safety/trips/{trip_id}/reset-requests")
def safety_reset_request(trip_id: str, body: SafetyResetRequestBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    from saathi.platform.safety import orchestration
    from saathi.platform.models import PlatformPermission
    try:
        ctx = _ppctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_RESET_REQUEST)
        r = orchestration.request_reset_via_gateway(ctx, trip_id=trip_id, reason=body.reason, approval_id=body.approval_id, idempotency_key=body.idempotency_key)
        return {"result": _pp_gateway_result(r)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/paper/safety/reset-requests/{request_id}/execute")
def safety_reset_execute(request_id: str, body: SafetyResetExecBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    from saathi.platform.safety import orchestration
    from saathi.platform.models import PlatformPermission
    try:
        ctx = _ppctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_RESET)
        r = orchestration.reset_via_gateway(ctx, request_id=request_id, approval_id=body.approval_id, expires_at=body.expires_at)
        return {"result": _pp_gateway_result(r)}
    except PlatformContextError as e:
        raise _err(e) from e


# ── M62.6 reconciliation read + integrated run (surfaced for the M62.8 workspace) ──
# Read-only run/finding/repair-plan views; the run action uses the M62.7 integrated
# reconcile_and_guard path (reconcile → auto-trip on CRITICAL). NEVER executes repairs.
def _reconsvc():
    from saathi.platform.paper_trading import ReconciliationEngine
    svc = _ppsvc()
    eng = ReconciliationEngine(svc.store, platform_store=getattr(svc, "_platform_store", None))
    return eng


class ReconRunBody(BaseModel):
    account_id: str


@router.get("/paper/reconciliation/runs")
def recon_runs_list(account_id: str = "", limit: int = 100, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"runs": _reconsvc().list_runs(_ppctx(authorization, x_platform_token), account_id=account_id or None, limit=limit)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/reconciliation/runs/{run_id}")
def recon_run_get(run_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"run": _reconsvc().get_run(_ppctx(authorization, x_platform_token), run_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/reconciliation/repair-plans")
def recon_plans_list(account_id: str = "", limit: int = 100, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"repair_plans": _reconsvc().list_repair_plans(_ppctx(authorization, x_platform_token), account_id=account_id or None, limit=limit)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/paper/reconciliation/repair-plans/{plan_id}")
def recon_plan_get(plan_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"repair_plan": _reconsvc().get_repair_plan(_ppctx(authorization, x_platform_token), plan_id)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/paper/reconciliation/runs")
def recon_run(body: ReconRunBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    # Integrated M62.7 path: reconcile the account and auto-trip a breaker on CRITICAL
    # drift. Never executes a repair. Requires PAPER_SAFETY_SWEEP (may trip a breaker).
    try:
        ctx = _ppctx(authorization, x_platform_token)
        return {"result": _safesvc().reconcile_and_guard(ctx, body.account_id)}
    except PlatformContextError as e:
        raise _err(e) from e


# ── M66 IELTSAlert authenticated workflows ──────────────────────────────────
def _ieltssvc():
    from saathi.platform.ielts.service import IELTSService
    return IELTSService(_svc().store)


def _ielts_failure(exc: Exception) -> HTTPException:
    if isinstance(exc, PlatformContextError):
        return _err(exc)
    return HTTPException(
        status_code=400,
        detail={"code": "VALIDATION_FAILED", "message": str(exc)[:500]},
    )


def _body(body: BaseModel, *, omit: set[str] | None = None) -> dict:
    data = body.model_dump()
    for key in omit or set():
        data.pop(key, None)
    return data


@router.get("/ielts/dashboard")
def ielts_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"dashboard": _ieltssvc().dashboard(_ppctx(authorization, x_platform_token))}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.get("/ielts/health")
def ielts_health(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"health": _ieltssvc().health(_ppctx(authorization, x_platform_token))}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.get("/ielts/records")
def ielts_records(record_type: str = "", all_owners: bool = False, limit: int = 200, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"records": _ieltssvc().list(
            _ppctx(authorization, x_platform_token), record_type=record_type,
            all_owners=all_owners, limit=limit,
        )}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.get("/ielts/records/{record_id}")
def ielts_record_get(record_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"record": _ieltssvc().get(_ppctx(authorization, x_platform_token), record_id)}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/profile")
def ielts_profile(body: IELTSProfileBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"profile": _ieltssvc().upsert_profile(
            _ppctx(authorization, x_platform_token), _body(body, omit={"idempotency_key"}),
            idempotency_key=body.idempotency_key,
        )}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/goals")
def ielts_goal_create(body: IELTSGoalBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"goal": _ieltssvc().create_goal(
            _ppctx(authorization, x_platform_token), _body(body, omit={"idempotency_key"}),
            idempotency_key=body.idempotency_key,
        )}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/practice")
def ielts_practice_create(body: IELTSPracticeBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"practice": _ieltssvc().create_practice(
            _ppctx(authorization, x_platform_token), _body(body, omit={"idempotency_key"}),
            idempotency_key=body.idempotency_key,
        )}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/alerts")
def ielts_alert_create(body: IELTSAlertBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"alert": _ieltssvc().create_alert(
            _ppctx(authorization, x_platform_token), _body(body, omit={"idempotency_key"}),
            idempotency_key=body.idempotency_key,
        )}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.patch("/ielts/alerts/{alert_id}")
def ielts_alert_transition(alert_id: str, body: IELTSStateBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"alert": _ieltssvc().transition_alert(
            _ppctx(authorization, x_platform_token), alert_id, body.status,
        )}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/alerts/evaluate")
def ielts_alert_evaluate(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return _ieltssvc().evaluate_alerts(_ppctx(authorization, x_platform_token))
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/payments")
def ielts_payment_submit(body: IELTSPaymentBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"payment": _ieltssvc().submit_payment(
            _ppctx(authorization, x_platform_token), _body(body, omit={"idempotency_key"}),
            idempotency_key=body.idempotency_key,
        )}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/payments/{payment_id}/review")
def ielts_payment_review(payment_id: str, body: IELTSPaymentReviewBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"payment": _ieltssvc().review_payment(
            _ppctx(authorization, x_platform_token), payment_id,
            approve=body.approve, reason=body.reason,
        )}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.get("/ielts/evidence")
def ielts_evidence(all_owners: bool = False, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"evidence": _ieltssvc().evidence_timeline(
            _ppctx(authorization, x_platform_token), all_owners=all_owners,
        )}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.get("/ielts/search")
def ielts_search(q: str = "", limit: int = 50, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        return {"results": _ieltssvc().search(
            _ppctx(authorization, x_platform_token), q, limit=limit,
        )}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


# ── M139+ IELTSAlert native productization endpoints ────────────────────────
class IELTSDiagnosticBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exam_type: str = Field(default="academic", max_length=32)
    idempotency_key: str = Field(default="", max_length=120)


class IELTSPlanBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weeks: int = Field(default=4, ge=1, le=12)
    idempotency_key: str = Field(default="", max_length=120)


class IELTSObjectiveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill: str = Field(default="reading", max_length=20)
    exam_type: str = Field(default="academic", max_length=32)
    answers: list[str] = Field(default_factory=list)
    idempotency_key: str = Field(default="", max_length=120)


class IELTSRevisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_submission_id: str = Field(min_length=1, max_length=120)
    response: str = Field(min_length=1, max_length=12000)
    idempotency_key: str = Field(default="", max_length=120)


class IELTSMockBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exam_type: str = Field(default="academic", max_length=32)
    idempotency_key: str = Field(default="", max_length=120)


class IELTSMockSectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill: str = Field(min_length=1, max_length=20)
    answers: list[str] = Field(default_factory=list)
    response: str = Field(default="", max_length=12000)


class IELTSYetiBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=500)


class IELTSRestoreBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload: dict[str, Any] = Field(default_factory=dict)
    approval_reference: str = Field(default="", max_length=160)


class IELTSReminderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    due_date: str = Field(default="", max_length=10)
    kind: str = Field(default="study", max_length=40)
    idempotency_key: str = Field(default="", max_length=120)


@router.get("/ielts/product-dashboard")
def ielts_product_dashboard(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {"dashboard": _ieltssvc().product_dashboard(_ppctx(authorization, x_platform_token))}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.get("/ielts/content")
def ielts_content(
    exam_type: str = "academic",
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _ieltssvc().content_catalog(_ppctx(authorization, x_platform_token), exam_type=exam_type)
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/diagnostic")
def ielts_diagnostic(
    body: IELTSDiagnosticBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {"diagnostic": _ieltssvc().run_diagnostic(
            _ppctx(authorization, x_platform_token),
            exam_type=body.exam_type, idempotency_key=body.idempotency_key,
        )}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/study-plan")
def ielts_study_plan(
    body: IELTSPlanBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {"plan": _ieltssvc().generate_study_plan(
            _ppctx(authorization, x_platform_token),
            weeks=body.weeks, idempotency_key=body.idempotency_key,
        )}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/objective-practice")
def ielts_objective_practice(
    body: IELTSObjectiveBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {"practice": _ieltssvc().submit_objective_practice(
            _ppctx(authorization, x_platform_token),
            skill=body.skill, exam_type=body.exam_type, answers=body.answers,
            idempotency_key=body.idempotency_key,
        )}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/writing/revision")
def ielts_writing_revision(
    body: IELTSRevisionBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _ieltssvc().submit_writing_revision(
            _ppctx(authorization, x_platform_token),
            parent_submission_id=body.parent_submission_id, response=body.response,
            idempotency_key=body.idempotency_key,
        )
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/mock-tests")
def ielts_mock_create(
    body: IELTSMockBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {"mock_test": _ieltssvc().create_mock_test(
            _ppctx(authorization, x_platform_token),
            exam_type=body.exam_type, idempotency_key=body.idempotency_key,
        )}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/mock-tests/{mock_id}/sections")
def ielts_mock_section(
    mock_id: str,
    body: IELTSMockSectionBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _ieltssvc().complete_mock_section(
            _ppctx(authorization, x_platform_token), mock_id,
            skill=body.skill, answers=body.answers, response=body.response,
        )
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.get("/ielts/readiness")
def ielts_readiness(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _ieltssvc().readiness_snapshot(_ppctx(authorization, x_platform_token))
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/yeti")
def ielts_yeti(
    body: IELTSYetiBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _ieltssvc().grounded_answer(_ppctx(authorization, x_platform_token), body.question)
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/backup")
def ielts_backup(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {"backup": _ieltssvc().export_backup_payload(_ppctx(authorization, x_platform_token))}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/restore")
def ielts_restore(
    body: IELTSRestoreBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _ieltssvc().restore_payload(
            _ppctx(authorization, x_platform_token), body.payload,
            approval_reference=body.approval_reference,
        )
    except Exception as exc:
        raise _ielts_failure(exc) from exc


@router.post("/ielts/reminders")
def ielts_reminder(
    body: IELTSReminderBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {"reminder": _ieltssvc().create_reminder(
            _ppctx(authorization, x_platform_token),
            title=body.title, due_date=body.due_date, kind=body.kind,
            idempotency_key=body.idempotency_key,
        )}
    except Exception as exc:
        raise _ielts_failure(exc) from exc


# ══════════════════════════════════════════════════════════════════════════
# M148–M156 SaathiOS Core unification (compose certified runtimes only)
# ══════════════════════════════════════════════════════════════════════════
class CoreYetiBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=800)


class CorePrefsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preferences: dict[str, Any] = Field(default_factory=dict)


class CorePinBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_type: str = Field(min_length=1, max_length=40)
    item_id: str = Field(min_length=1, max_length=120)
    label: str = Field(default="", max_length=200)


class CoreAutomationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    schedule: str = Field(default="daily_morning", max_length=40)
    action: str = Field(default="summarize", max_length=80)
    app_scope: str = Field(default="platform", max_length=40)
    requires_approval: bool = True


class CoreWorkflowGraphBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    graph_id: str = Field(default="", max_length=80)


def _core_svc():
    from saathi.platform.core_os import default_core_service

    return default_core_service(_svc())


def _core_ctx(authorization: str | None, x_platform_token: str | None):
    return _svc().require_context(_token(authorization, x_platform_token))


@router.get("/core/home")
def core_home(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {"home": _core_svc().operator_home(_core_ctx(authorization, x_platform_token))}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/core/health")
def core_health(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {"health": _core_svc().health(_core_ctx(authorization, x_platform_token))}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/core/search")
def core_search(
    q: str = "",
    limit: int = 40,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _core_svc().universal_search(
            _core_ctx(authorization, x_platform_token), q, limit=limit,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/core/yeti")
def core_yeti(
    body: CoreYetiBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _core_svc().yeti_ask(_core_ctx(authorization, x_platform_token), body.question)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/core/memory")
def core_memory(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _core_svc().get_memory(_core_ctx(authorization, x_platform_token))
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/core/memory/preferences")
def core_prefs(
    body: CorePrefsBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _core_svc().update_preferences(
            _core_ctx(authorization, x_platform_token), body.preferences,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/core/memory/pin")
def core_pin(
    body: CorePinBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _core_svc().pin_item(
            _core_ctx(authorization, x_platform_token),
            item_type=body.item_type, item_id=body.item_id, label=body.label,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/core/notifications")
def core_notifications(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _core_svc().notification_center(_core_ctx(authorization, x_platform_token))
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/core/activity")
def core_activity(
    limit: int = 50,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _core_svc().activity_feed(
            _core_ctx(authorization, x_platform_token), limit=limit,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/core/timeline")
def core_timeline(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _core_svc().timeline(_core_ctx(authorization, x_platform_token))
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/core/context")
def core_context(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _core_svc().cross_app_context(_core_ctx(authorization, x_platform_token))
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/core/commands")
def core_commands(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _core_svc().command_catalog(_core_ctx(authorization, x_platform_token))
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/core/automations")
def core_automations_list(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _core_svc().list_automations(_core_ctx(authorization, x_platform_token))
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/core/automations")
def core_automations_create(
    body: CoreAutomationBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _core_svc().create_automation(
            _core_ctx(authorization, x_platform_token),
            name=body.name, schedule=body.schedule, action=body.action,
            app_scope=body.app_scope, requires_approval=body.requires_approval,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/core/automations/{automation_id}/dry-run")
def core_automation_dry(
    automation_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _core_svc().run_automation_dry(
            _core_ctx(authorization, x_platform_token), automation_id,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/core/workflows")
def core_workflows_list(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _core_svc().list_workflow_graphs(_core_ctx(authorization, x_platform_token))
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/core/workflows")
def core_workflows_save(
    body: CoreWorkflowGraphBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _core_svc().save_workflow_graph(
            _core_ctx(authorization, x_platform_token),
            name=body.name, nodes=body.nodes, edges=body.edges, graph_id=body.graph_id,
        )
    except PlatformContextError as e:
        raise _err(e) from e


# ── M74 authenticated provider-neutral voice output ─────────────────────────
def _voicesvc():
    from saathi.platform.voice import default_speech_service

    return default_speech_service(_svc())


def _voice_context(
    authorization: str | None,
    x_platform_token: str | None,
):
    return _svc().require_context(_token(authorization, x_platform_token))


def _voice_failure(exc: Exception) -> HTTPException:
    if isinstance(exc, PlatformContextError):
        return _err(exc)
    return HTTPException(
        status_code=500,
        detail={
            "code": "VOICE_INTERNAL_FAILURE",
            "message": "Voice output could not complete safely.",
        },
    )


@router.get("/voice/health")
def voice_health(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "health": _voicesvc().health(
                _voice_context(authorization, x_platform_token)
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.get("/voice/providers")
def voice_providers(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "providers": _voicesvc().provider_states(
                _voice_context(authorization, x_platform_token)
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.get("/voice/profiles")
def voice_profiles(
    all_owners: bool = False,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "profiles": _voicesvc().list_profiles(
                _voice_context(authorization, x_platform_token),
                all_owners=all_owners,
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/voice/profiles")
def voice_profile_create(
    body: VoiceProfileBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "profile": _voicesvc().create_profile(
                _voice_context(authorization, x_platform_token),
                body.model_dump(),
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.patch("/voice/profiles/{profile_id}")
def voice_profile_update(
    profile_id: str,
    body: VoiceProfilePatchBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        updates = {
            key: value
            for key, value in body.model_dump().items()
            if value is not None
        }
        return {
            "profile": _voicesvc().update_profile(
                _voice_context(authorization, x_platform_token),
                profile_id,
                updates,
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.delete("/voice/profiles/{profile_id}")
def voice_profile_delete(
    profile_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "deleted": _voicesvc().delete_profile(
                _voice_context(authorization, x_platform_token), profile_id
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.get("/voice/speech")
def voice_speech_list(
    all_owners: bool = False,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "operations": _voicesvc().list_operations(
                _voice_context(authorization, x_platform_token),
                all_owners=all_owners,
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/voice/speech")
def voice_speech_create(
    body: VoiceSpeechBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "operation": _voicesvc().create_speech(
                _voice_context(authorization, x_platform_token),
                body.model_dump(),
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.get("/voice/speech/{operation_id}")
def voice_speech_get(
    operation_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        operation = _voicesvc().get_operation(
            _voice_context(authorization, x_platform_token), operation_id
        )
        return {"operation": operation.to_public()}
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/voice/speech/{operation_id}/cancel")
def voice_speech_cancel(
    operation_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "operation": _voicesvc().cancel(
                _voice_context(authorization, x_platform_token), operation_id
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


_BYTE_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


@router.get("/voice/speech/{operation_id}/audio")
def voice_speech_audio(
    operation_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        operation, path = _voicesvc().artifact(
            _voice_context(authorization, x_platform_token), operation_id
        )
        data = path.read_bytes()
        status = 200
        headers = {
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, no-store, max-age=0",
            "Content-Security-Policy": "default-src 'none'",
            "X-Content-Type-Options": "nosniff",
        }
        range_header = request.headers.get("range", "").strip()
        if range_header:
            match = _BYTE_RANGE.fullmatch(range_header)
            if not match:
                raise HTTPException(
                    status_code=416,
                    detail={"code": "INVALID_RANGE", "message": "Invalid audio range."},
                    headers={"Content-Range": f"bytes */{len(data)}"},
                )
            start_text, end_text = match.groups()
            if not start_text and not end_text:
                raise HTTPException(status_code=416)
            if start_text:
                start = int(start_text)
                end = int(end_text) if end_text else len(data) - 1
            else:
                suffix = int(end_text)
                start = max(0, len(data) - suffix)
                end = len(data) - 1
            if start >= len(data) or start > end:
                raise HTTPException(
                    status_code=416,
                    detail={"code": "INVALID_RANGE", "message": "Invalid audio range."},
                    headers={"Content-Range": f"bytes */{len(data)}"},
                )
            end = min(end, len(data) - 1)
            data = data[start : end + 1]
            status = 206
            headers["Content-Range"] = f"bytes {start}-{end}/{operation.artifact_bytes}"
        media_type = (
            "audio/aiff" if operation.output_format == "aiff" else "audio/wav"
        )
        return Response(
            content=data, status_code=status, media_type=media_type, headers=headers
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.get("/voice/evidence")
def voice_evidence(
    all_owners: bool = False,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "evidence": _voicesvc().evidence(
                _voice_context(authorization, x_platform_token),
                all_owners=all_owners,
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


# ── M79 real-time voice runtime (listen / STT / barge-in / conversation) ────
def _voice_runtime():
    from saathi.platform.voice.runtime import default_voice_runtime

    return default_voice_runtime(_svc())


@router.get("/voice/runtime/health")
def voice_runtime_health(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "health": _voice_runtime().health(
                _voice_context(authorization, x_platform_token)
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.get("/voice/runtime/stt-providers")
def voice_runtime_stt_providers(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "providers": _voice_runtime().stt_provider_states(
                _voice_context(authorization, x_platform_token)
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/voice/runtime/sessions")
def voice_runtime_create_session(
    body: VoiceRuntimeSessionBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "session": _voice_runtime().create_session(
                _voice_context(authorization, x_platform_token),
                body.model_dump(),
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.get("/voice/runtime/sessions")
def voice_runtime_list_sessions(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "sessions": _voice_runtime().list_sessions(
                _voice_context(authorization, x_platform_token)
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.get("/voice/runtime/sessions/{session_id}")
def voice_runtime_get_session(
    session_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "session": _voice_runtime().get_session(
                _voice_context(authorization, x_platform_token), session_id
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


def _runtime_session_payload(payload: dict) -> dict:
    """Normalize manager snapshots to a stable {session: ...} wire shape."""
    if isinstance(payload, dict) and "session" in payload and "session_id" not in payload:
        return payload
    return {"session": payload}


@router.post("/voice/runtime/sessions/{session_id}/listen")
def voice_runtime_listen(
    session_id: str,
    body: VoiceRuntimeListenBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        payload = body.model_dump() if body else {}
        return _runtime_session_payload(
            _voice_runtime().start_listening(
                _voice_context(authorization, x_platform_token),
                session_id,
                mode=payload.get("mode"),
                permission_granted=bool(payload.get("permission_granted", True)),
            )
        )
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/voice/runtime/sessions/{session_id}/stop")
def voice_runtime_stop(
    session_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _runtime_session_payload(
            _voice_runtime().stop_listening(
                _voice_context(authorization, x_platform_token), session_id
            )
        )
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/voice/runtime/sessions/{session_id}/cancel")
def voice_runtime_cancel(
    session_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _runtime_session_payload(
            _voice_runtime().cancel_input(
                _voice_context(authorization, x_platform_token), session_id
            )
        )
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/voice/runtime/sessions/{session_id}/permission")
def voice_runtime_permission(
    session_id: str,
    body: VoiceRuntimePermissionBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _runtime_session_payload(
            _voice_runtime().set_microphone_permission(
                _voice_context(authorization, x_platform_token),
                session_id,
                granted=body.granted,
            )
        )
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/voice/runtime/sessions/{session_id}/transcript")
def voice_runtime_transcript(
    session_id: str,
    body: VoiceRuntimeTranscriptBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _voice_runtime().submit_transcript(
            _voice_context(authorization, x_platform_token),
            session_id,
            body.model_dump(),
        )
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/voice/runtime/sessions/{session_id}/audio")
async def voice_runtime_audio(
    session_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        content_type = request.headers.get("content-type", "application/octet-stream")
        audio = await request.body()
        sample_rate_header = request.headers.get("x-sample-rate")
        sample_rate = int(sample_rate_header) if sample_rate_header else None
        return _voice_runtime().submit_audio(
            _voice_context(authorization, x_platform_token),
            session_id,
            audio,
            content_type=content_type,
            sample_rate=sample_rate,
        )
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/voice/runtime/sessions/{session_id}/interrupt")
def voice_runtime_interrupt(
    session_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _runtime_session_payload(
            _voice_runtime().interrupt(
                _voice_context(authorization, x_platform_token),
                session_id,
                reason="barge_in",
            )
        )
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/voice/runtime/sessions/{session_id}/playback")
def voice_runtime_playback(
    session_id: str,
    body: VoiceRuntimePlaybackBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _runtime_session_payload(
            _voice_runtime().playback_control(
                _voice_context(authorization, x_platform_token),
                session_id,
                body.action,
            )
        )
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/voice/runtime/sessions/{session_id}/playback/complete")
def voice_runtime_playback_complete(
    session_id: str,
    body: VoiceRuntimePlaybackCompleteBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _runtime_session_payload(
            _voice_runtime().mark_playback_complete(
                _voice_context(authorization, x_platform_token),
                session_id,
                body.playback_id,
            )
        )
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/voice/runtime/sessions/{session_id}/finish")
def voice_runtime_finish(
    session_id: str,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "session": _voice_runtime().finish_session(
                _voice_context(authorization, x_platform_token), session_id
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


# ── M80+ centralized conversational intelligence ────────────────────────────
class ConversationCompleteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4_000)
    session_id: str = Field(default="", max_length=160)
    conversation_id: str = Field(default="", max_length=160)
    yeti_mode: str = Field(default="general", max_length=40)
    locale: str = Field(default="en-US", max_length=16)
    project_id: str = Field(default="", max_length=160)
    mission_id: str = Field(default="", max_length=160)
    module_context: str = Field(default="", max_length=400)
    provider: str = Field(default="auto", max_length=40)
    max_tokens: int = Field(default=512, ge=16, le=1024)
    timeout_seconds: float = Field(default=60.0, ge=5.0, le=120.0)
    stream: bool = True


class ConversationCancelBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=160)


def _conversation_svc():
    from saathi.platform.conversation import default_conversation_service

    return default_conversation_service(_svc())


@router.get("/conversation/health")
def conversation_health(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "health": _conversation_svc().health(
                _voice_context(authorization, x_platform_token)
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.get("/conversation/providers")
def conversation_providers(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {
            "providers": _conversation_svc().provider_health(
                _voice_context(authorization, x_platform_token)
            )
        }
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/conversation/complete")
def conversation_complete(
    body: ConversationCompleteBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        result = _conversation_svc().complete(
            _voice_context(authorization, x_platform_token),
            body.model_dump(),
        )
        return {"result": result.to_public()}
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/conversation/cancel")
def conversation_cancel(
    body: ConversationCancelBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        from saathi.platform.models import PlatformPermission

        ctx = _voice_context(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.VOICE_LISTEN)
        _conversation_svc().cancel(body.request_id)
        return {"ok": True, "request_id": body.request_id}
    except Exception as exc:
        raise _voice_failure(exc) from exc


# ── M87+ Knowledge and Grounding Runtime ─────────────────────────────────────
class KnowledgeSearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=6, ge=1, le=12)


class KnowledgeReindexBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = False


def _knowledge_svc():
    from saathi.platform.knowledge import default_knowledge_service

    return default_knowledge_service(_svc())


@router.get("/knowledge/health")
def knowledge_health(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return {"health": _knowledge_svc().health(_voice_context(authorization, x_platform_token))}
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/knowledge/search")
def knowledge_search(
    body: KnowledgeSearchBody,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        return _knowledge_svc().search(
            _voice_context(authorization, x_platform_token),
            body.query,
            top_k=body.top_k,
        )
    except Exception as exc:
        raise _voice_failure(exc) from exc


@router.post("/knowledge/reindex")
def knowledge_reindex(
    body: KnowledgeReindexBody | None = None,
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    try:
        force = bool(body.force) if body is not None else False
        return _knowledge_svc().reindex(
            _voice_context(authorization, x_platform_token),
            force=force,
        )
    except Exception as exc:
        raise _voice_failure(exc) from exc


# ── M63/M64 module registry (read-only; authoritative source for browser discovery) ──
def _module_registry():
    from saathi.platform.module_registry import get_registry
    return get_registry()


def _module_caller(ctx):
    """Build the caller-scoped predicate + agent flag for permission-filtered
    module discovery. RBAC stays authoritative — this only shapes what the shell
    RENDERS; backend routes still enforce their own permissions."""
    from saathi.platform.models import role_has_permission
    from saathi.platform.safety.models import is_agent_actor
    def can_read(perm: str) -> bool:
        try:
            return role_has_permission(ctx.role, perm)
        except Exception:
            return False
    return can_read, is_agent_actor(ctx)


@router.get("/modules")
def modules_list(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    """Authoritative, permission-filtered module discovery for the browser shell:
    installed modules + composed navigation/dashboard/search surfaces, each carrying
    a truthful caller-scoped state."""
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _ppctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PLATFORM_READ)
        can_read, is_agent = _module_caller(ctx)
        return _module_registry().discovery(can_read=can_read, is_agent=is_agent)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/modules/{module_id}")
def module_get(module_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _ppctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PLATFORM_READ)
        m = _module_registry().get(module_id)
        if not m:
            raise PlatformContextError("NOT_FOUND", "module not found")
        can_read, is_agent = _module_caller(ctx)
        return {"module": m.to_public(can_read=can_read, is_agent=is_agent)}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/dashboard")
def platform_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    """Module-driven dashboard: one card per installed application, caller-scoped state."""
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _ppctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PLATFORM_READ)
        can_read, is_agent = _module_caller(ctx)
        disc = _module_registry().discovery(can_read=can_read, is_agent=is_agent)
        return {"contract_version": disc["contract_version"], "cards": disc["dashboard_cards"],
                "health": disc["health"]}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/navigation")
def platform_navigation(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    """Data-driven, permission-filtered Applications navigation group."""
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _ppctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PLATFORM_READ)
        can_read, is_agent = _module_caller(ctx)
        return _module_registry().discovery(can_read=can_read, is_agent=is_agent)["navigation"]
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/modules/{module_id}/health")
def module_health(module_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _ppctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PLATFORM_READ)
        m = _module_registry().get(module_id)
        if not m:
            raise PlatformContextError("NOT_FOUND", "module not found")
        can_read, is_agent = _module_caller(ctx)
        return {"module_id": module_id, "status": m.status.value, "health": m.health().value,
                "state": m.resolve_state(can_read=can_read, is_agent=is_agent).value}
    except PlatformContextError as e:
        raise _err(e) from e


# ══════════════════════════════════════════════════════════════════════════
# M166–M175 — Trading Guardian Research & Paper Foundation
# PAPER ONLY. No live orders. No broker credentials. Default ADVISORY.
# Composes M62 paper_trading + strategy + safety; does not replace them.
# ══════════════════════════════════════════════════════════════════════════
def _tg_svc():
    from saathi.platform.tg.service import default_tg_service
    return default_tg_service()


def _tg_ctx(a, x):
    return _svc().require_context(_token(a, x))


@router.get("/tg/posture")
def tg_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        return _tg_svc().posture()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/strategies")
def tg_strategies(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.strategies import list_catalog
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        svc = _tg_svc()
        svc.seed_catalog(org_id=ctx.org_id, workspace_id=ctx.workspace_id)
        return {
            "catalog": list_catalog(),
            "registered": [s.to_public() for s in svc.registry.list(org_id=ctx.org_id, workspace_id=ctx.workspace_id)],
            "paper_only": True,
            "live_authorized": False,
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/strategies/{slug}")
def tg_strategy_detail(slug: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        svc = _tg_svc()
        svc.seed_catalog(org_id=ctx.org_id, workspace_id=ctx.workspace_id)
        s = svc.registry.get_by_slug(slug, org_id=ctx.org_id, workspace_id=ctx.workspace_id)
        if not s:
            raise PlatformContextError("NOT_FOUND", "strategy not found")
        return {"strategy": s.to_public(), "paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/policies")
def tg_policies(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        return {"policies": [_tg_svc().policy.to_public()], "paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


class TgRegimeBody(BaseModel):
    snapshot: dict[str, Any] = Field(default_factory=dict)


@router.post("/tg/regime/evaluate")
def tg_regime_evaluate(body: TgRegimeBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.fixtures import trending_snapshot
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        snap = body.snapshot if body.snapshot else trending_snapshot().to_public()
        return {"regime": _tg_svc().evaluate_regime(snap), "paper_only": True, "llm_determined": False}
    except PlatformContextError as e:
        raise _err(e) from e


class TgProposalBody(BaseModel):
    strategy_slug: str = "trend_following"
    snapshot: dict[str, Any] = Field(default_factory=dict)
    fixture: str = "trending"


@router.post("/tg/proposals")
def tg_proposal_create(body: TgProposalBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.fixtures import trending_snapshot, mean_reverting_snapshot, momentum_snapshot
        from saathi.platform.tg.service import TGServiceError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ORDER_PROPOSE)
        if body.snapshot:
            snap = body.snapshot
        else:
            snap = {
                "trending": trending_snapshot,
                "mean_reverting": mean_reverting_snapshot,
                "momentum": momentum_snapshot,
            }.get(body.fixture, trending_snapshot)().to_public()
        try:
            return _tg_svc().generate_proposal(
                strategy_slug=body.strategy_slug,
                snapshot=snap,
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                project_id=ctx.project_id or "",
                actor=ctx.requested_by(),
            )
        except TGServiceError as te:
            raise PlatformContextError(te.code, te.message) from te
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/proposals")
def tg_proposals_list(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ORDER_READ)
        return {"proposals": _tg_svc().list_proposals(org_id=ctx.org_id, workspace_id=ctx.workspace_id), "paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/proposals/{pid}")
def tg_proposal_get(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.service import TGServiceError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ORDER_READ)
        try:
            return {"proposal": _tg_svc().get_proposal(pid, org_id=ctx.org_id, workspace_id=ctx.workspace_id), "paper_only": True}
        except TGServiceError as te:
            raise PlatformContextError(te.code, te.message) from te
    except PlatformContextError as e:
        raise _err(e) from e


class TgReviewBody(BaseModel):
    decision: str  # approve | reject
    approval_id: str = ""
    notes: str = ""


@router.post("/tg/proposals/{pid}/review")
def tg_proposal_review(pid: str, body: TgReviewBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.service import TGServiceError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.APPROVAL_DECIDE)
        try:
            return _tg_svc().review_proposal(
                pid,
                decision=body.decision,
                actor=ctx.requested_by(),
                approval_id=body.approval_id,
                notes=body.notes,
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
            )
        except TGServiceError as te:
            raise PlatformContextError(te.code, te.message) from te
    except PlatformContextError as e:
        raise _err(e) from e


class TgBacktestBody(BaseModel):
    strategy_slug: str = "trend_following"
    dataset: str = "TRENDING"
    n: int = 40
    seed: int = 0
    cost_tier: str = "realistic"
    split_kind: str = "IN_SAMPLE"


@router.post("/tg/backtests")
def tg_backtest_run(body: TgBacktestBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.BACKTEST_RUN)
        return _tg_svc().run_backtest(
            strategy_slug=body.strategy_slug,
            dataset=body.dataset,
            n=min(body.n, 200),
            seed=body.seed,
            cost_tier=body.cost_tier,
            split_kind=body.split_kind,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/backtests/compare")
def tg_backtest_compare(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.BACKTEST_REVIEW)
        return _tg_svc().compare_strategies(org_id=ctx.org_id, workspace_id=ctx.workspace_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/journal")
def tg_journal(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ORDER_READ)
        entries = _tg_svc().journal.list(org_id=ctx.org_id, workspace_id=ctx.workspace_id)
        return {
            "entries": [e.to_public() for e in entries],
            "paper_only": True,
            "funds_label": "SIMULATED",
            "immutable": True,
        }
    except PlatformContextError as e:
        raise _err(e) from e


class TgKillSwitchBody(BaseModel):
    scope: str = "GLOBAL"
    scope_ref: str = ""
    reason: str = "manual"


@router.post("/tg/kill-switch/activate")
def tg_kill_activate(body: TgKillSwitchBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.domain import KillSwitchScope
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_TRIP)
        return {
            "kill_switch": _tg_svc().activate_kill_switch(
                scope=KillSwitchScope(body.scope),
                scope_ref=body.scope_ref,
                reason=body.reason,
                activated_by=ctx.requested_by(),
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                source_identity="operator",
            ),
            "paper_only": True,
        }
    except PlatformContextError as e:
        raise _err(e) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.get("/tg/kill-switch")
def tg_kill_status(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return {
            "kill_switches": _tg_svc().kill_switch_status(org_id=ctx.org_id, workspace_id=ctx.workspace_id),
            "paper_only": True,
        }
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/strategies/{slug}/suspend")
def tg_strategy_suspend(slug: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        svc = _tg_svc()
        svc.seed_catalog(org_id=ctx.org_id, workspace_id=ctx.workspace_id)
        s = svc.registry.get_by_slug(slug, org_id=ctx.org_id, workspace_id=ctx.workspace_id)
        if not s:
            raise PlatformContextError("NOT_FOUND", "strategy not found")
        return {"strategy": svc.registry.suspend(s.id).to_public(), "paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


# ══════════════════════════════════════════════════════════════════════════
# M176–M183 — Paper validation, walk-forward, stress, portfolio, recovery
# ══════════════════════════════════════════════════════════════════════════
class TgWalkForwardBody(BaseModel):
    strategy_slug: str = "trend_following"
    dataset: str = "TRENDING"
    n: int = 60
    mode: str = "expanding"
    n_folds: int = 3
    is_test_context: bool = False


@router.post("/tg/walk-forward")
def tg_walk_forward(body: TgWalkForwardBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.BACKTEST_RUN)
        return _tg_svc().run_walk_forward(
            strategy_slug=body.strategy_slug,
            dataset=body.dataset,
            n=min(body.n, 200),
            mode=body.mode,
            n_folds=min(body.n_folds, 8),
            is_test_context=body.is_test_context,
        )
    except PlatformContextError as e:
        raise _err(e) from e


class TgStressBody(BaseModel):
    strategy_slug: str = "trend_following"
    dataset: str = "TRENDING"
    n: int = 40
    is_test_context: bool = False


@router.post("/tg/stress")
def tg_stress(body: TgStressBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.BACKTEST_RUN)
        return _tg_svc().run_stress(
            strategy_slug=body.strategy_slug,
            dataset=body.dataset,
            n=min(body.n, 100),
            is_test_context=body.is_test_context,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/scorecard/{slug}")
def tg_scorecard(slug: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.BACKTEST_REVIEW)
        return _tg_svc().research_scorecard(strategy_slug=slug, dataset="TRENDING", n=50)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/recovery/cert")
def tg_recovery_cert(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.recovery import run_recovery_suite
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return run_recovery_suite()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/portfolio/analysis")
def tg_portfolio_analysis(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.portfolio import PortfolioState, PortfolioRiskAnalyzer
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        state = PortfolioState()
        analysis = PortfolioRiskAnalyzer().analyze(state)
        return {
            "portfolio": state.to_public(),
            "analysis": analysis,
            "paper_only": True,
            "funds_label": "SIMULATED",
            "disclaimer": "SIMULATED FUNDS — NOT REAL MONEY",
        }
    except PlatformContextError as e:
        raise _err(e) from e


class TgPortfolioScenarioBody(BaseModel):
    scenario: str = "correlated_selloff"


@router.post("/tg/portfolio/scenario")
def tg_portfolio_scenario(body: TgPortfolioScenarioBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.portfolio import PortfolioState, PortfolioRiskAnalyzer
        from decimal import Decimal
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        state = PortfolioState(
            positions={"AAPL": {"quantity": Decimal("10"), "avg_cost": Decimal("100"), "sector": "TECH"}},
            sector_of={"AAPL": "TECH"},
            strategy_of={"AAPL": "trend_following"},
            open_orders=[{"id": "p1", "status": "PENDING"}],
        )
        return PortfolioRiskAnalyzer().scenario(body.scenario, state)
    except PlatformContextError as e:
        raise _err(e) from e


# ══════════════════════════════════════════════════════════════════════════
# M184–M191 — Historical market data, research, Monte Carlo, qualification
# PAPER RESEARCH ONLY. No live orders. No broker credentials.
# ══════════════════════════════════════════════════════════════════════════
class TgHistoricalImportBody(BaseModel):
    path: str
    adapter: str = "local_file"
    dataset_name: str = ""
    market: str = ""
    currency: str = "USD"
    timezone: str = "UTC"
    timeframe: str = "1d"
    calendar_name: str = "DEFAULT_24_5"
    classification: str = "HISTORICAL_LOCAL_DATASET"
    default_instrument: str = "UNKNOWN"
    version: str = "1.0.0"
    adjustment_methodology: str = "SPLIT_ONLY"


@router.post("/tg/historical/import")
def tg_historical_import(body: TgHistoricalImportBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.BACKTEST_RUN)
        return _tg_svc().import_historical_dataset(
            body.path,
            adapter=body.adapter,
            dataset_name=body.dataset_name,
            market=body.market,
            currency=body.currency,
            timezone=body.timezone,
            timeframe=body.timeframe,
            calendar_name=body.calendar_name,
            classification=body.classification,
            default_instrument=body.default_instrument,
            version=body.version,
            adjustment_methodology=body.adjustment_methodology,
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/historical/datasets")
def tg_historical_datasets(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        return _tg_svc().list_historical_datasets(org_id=ctx.org_id, workspace_id=ctx.workspace_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/historical/datasets/{dataset_id}")
def tg_historical_dataset_detail(dataset_id: str, version: str | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.service import TGServiceError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        try:
            return _tg_svc().inspect_historical_dataset(
                dataset_id, version=version, org_id=ctx.org_id, workspace_id=ctx.workspace_id,
            )
        except TGServiceError as te:
            raise PlatformContextError(te.code, te.message) from te
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/historical/datasets/{dataset_id}/quality")
def tg_historical_quality(dataset_id: str, version: str | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.service import TGServiceError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        try:
            detail = _tg_svc().inspect_historical_dataset(
                dataset_id, version=version, org_id=ctx.org_id, workspace_id=ctx.workspace_id,
            )
            return {
                "quality": detail["version"].get("quality"),
                "coverage": detail["version"].get("coverage"),
                "classification": detail["version"].get("classification"),
                "promotable": detail.get("promotable"),
                "paper_only": True,
            }
        except TGServiceError as te:
            raise PlatformContextError(te.code, te.message) from te
    except PlatformContextError as e:
        raise _err(e) from e


class TgQuarantineBody(BaseModel):
    version: str
    reason: str = "operator_quarantine"


@router.post("/tg/historical/datasets/{dataset_id}/quarantine")
def tg_historical_quarantine(dataset_id: str, body: TgQuarantineBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.service import TGServiceError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        try:
            return _tg_svc().quarantine_historical_dataset(dataset_id, body.version, reason=body.reason)
        except TGServiceError as te:
            raise PlatformContextError(te.code, te.message) from te
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/historical/quarantine")
def tg_historical_quarantine_list(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        return _tg_svc().list_historical_quarantine(org_id=ctx.org_id, workspace_id=ctx.workspace_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/historical/calendars")
def tg_historical_calendars(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        return _tg_svc().historical_calendars()
    except PlatformContextError as e:
        raise _err(e) from e


class TgHistoricalResearchBody(BaseModel):
    strategy_slug: str = "trend_following"
    dataset_id: str = ""
    version: str | None = None
    period: str = "FULL"
    seed: int = 42
    fee_bps: str = "10"
    slippage_bps: str = "5"
    spread_model: str = "realistic"
    n_folds: int = 3
    mc_simulations: int = 100


@router.post("/tg/historical/research")
def tg_historical_research(body: TgHistoricalResearchBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.service import TGServiceError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.BACKTEST_RUN)
        try:
            return _tg_svc().run_historical_research(
                strategy_slug=body.strategy_slug,
                dataset_id=body.dataset_id,
                version=body.version,
                period=body.period,
                seed=body.seed,
                fee_bps=body.fee_bps,
                slippage_bps=body.slippage_bps,
                spread_model=body.spread_model,
                n_folds=min(body.n_folds, 8),
                mc_simulations=min(body.mc_simulations, 500),
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
            )
        except TGServiceError as te:
            raise PlatformContextError(te.code, te.message) from te
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/historical/research")
def tg_historical_research_list(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.BACKTEST_REVIEW)
        return _tg_svc().historical_research_status()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/historical/research/{run_id}")
def tg_historical_research_get(run_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.service import TGServiceError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.BACKTEST_REVIEW)
        try:
            return _tg_svc().historical_research_status(run_id)
        except TGServiceError as te:
            raise PlatformContextError(te.code, te.message) from te
    except PlatformContextError as e:
        raise _err(e) from e


class TgMonteCarloBody(BaseModel):
    strategy_slug: str = "trend_following"
    dataset_id: str = ""
    dataset: str = "TRENDING"
    n: int = 40
    seed: int = 42
    n_simulations: int = 100


@router.post("/tg/historical/monte-carlo")
def tg_monte_carlo(body: TgMonteCarloBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.BACKTEST_RUN)
        return _tg_svc().run_monte_carlo_analysis(
            strategy_slug=body.strategy_slug,
            dataset=body.dataset,
            n=min(body.n, 200),
            seed=body.seed,
            n_simulations=min(body.n_simulations, 500),
            dataset_id=body.dataset_id,
        )
    except PlatformContextError as e:
        raise _err(e) from e


class TgQualifyBody(BaseModel):
    strategy_slug: str = "trend_following"
    dataset_id: str = ""
    period: str = "FULL"
    seed: int = 42
    mc_simulations: int = 100


@router.post("/tg/historical/qualify")
def tg_qualify(body: TgQualifyBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.BACKTEST_REVIEW)
        return _tg_svc().qualify_strategy_historical(
            body.strategy_slug,
            dataset_id=body.dataset_id,
            period=body.period,
            seed=body.seed,
            mc_simulations=min(body.mc_simulations, 500),
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/historical/scorecard/{slug}")
def tg_historical_scorecard(slug: str, dataset_id: str = "", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.BACKTEST_REVIEW)
        return _tg_svc().qualify_strategy_historical(
            slug, dataset_id=dataset_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id,
        )
    except PlatformContextError as e:
        raise _err(e) from e


# ══════════════════════════════════════════════════════════════════════════
# M192–M199 — Paper Activation Governance (PAPER ONLY, no live broker)
# ══════════════════════════════════════════════════════════════════════════
def _paper_gov():
    """Prefer durable multi-process store (M200+); falls back to process-local."""
    import os
    if os.environ.get("SAATHI_PAPER_GOV_DURABLE", "1") != "0":
        from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
        return default_durable_gov()
    from saathi.platform.tg.paper_activation.service import default_paper_gov
    return default_paper_gov()


@router.get("/tg/paper/posture")
def tg_paper_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        return _paper_gov().posture()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/status")
def tg_paper_status(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        return _paper_gov().status(org_id=ctx.org_id, workspace_id=ctx.workspace_id)
    except PlatformContextError as e:
        raise _err(e) from e


class TgPaperPortfolioBody(BaseModel):
    name: str = "Paper Fund"
    starting_cash: str = "100000"
    base_currency: str = "USD"


@router.post("/tg/paper/portfolios")
def tg_paper_portfolio_create(body: TgPaperPortfolioBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.service import PaperGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_CREATE)
        try:
            return _paper_gov().create_portfolio(
                name=body.name, starting_cash=body.starting_cash, base_currency=body.base_currency,
                org_id=ctx.org_id, workspace_id=ctx.workspace_id,
            )
        except PaperGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/portfolios")
def tg_paper_portfolios(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        return _paper_gov().list_portfolios(org_id=ctx.org_id, workspace_id=ctx.workspace_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/portfolios/{pid}")
def tg_paper_portfolio_get(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.service import PaperGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        try:
            return _paper_gov().get_portfolio(pid)
        except PaperGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


class TgPaperApprovalRequestBody(BaseModel):
    strategy_slug: str
    reason: str
    qualification: dict[str, Any] = Field(default_factory=dict)
    strategy_version: str = "1.0.0"
    dataset_id: str = ""
    dataset_fingerprint: str = ""


@router.post("/tg/paper/approvals/request")
def tg_paper_approval_request(body: TgPaperApprovalRequestBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.service import PaperGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.APPROVAL_REQUEST)
        try:
            return _paper_gov().request_approval(
                strategy_slug=body.strategy_slug,
                qualification=body.qualification,
                reason=body.reason,
                operator_id=ctx.user_id or ctx.requested_by(),
                operator_identity=f"operator:{ctx.requested_by()}",
                strategy_version=body.strategy_version,
                dataset_id=body.dataset_id,
                dataset_fingerprint=body.dataset_fingerprint,
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
            )
        except PaperGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


class TgPaperApprovalDecideBody(BaseModel):
    decision: str  # approve | reject
    notes: str = ""
    reason: str = ""


@router.post("/tg/paper/approvals/{aid}/decide")
def tg_paper_approval_decide(aid: str, body: TgPaperApprovalDecideBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.service import PaperGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.APPROVAL_DECIDE)
        try:
            return _paper_gov().decide_approval(
                approval_id=aid,
                decision=body.decision,
                operator_id=ctx.user_id or ctx.requested_by(),
                operator_identity=f"operator:{ctx.requested_by()}",
                notes=body.notes,
                reason=body.reason,
            )
        except PaperGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/approvals")
def tg_paper_approvals(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.APPROVAL_READ)
        return _paper_gov().list_approvals(org_id=ctx.org_id, workspace_id=ctx.workspace_id)
    except PlatformContextError as e:
        raise _err(e) from e


class TgPaperActivateBody(BaseModel):
    strategy_slug: str
    approval_id: str
    portfolio_id: str = ""
    portfolio_name: str = ""
    starting_cash: str = "100000"


@router.post("/tg/paper/activate")
def tg_paper_activate(body: TgPaperActivateBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.service import PaperGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        try:
            return _paper_gov().activate_strategy(
                strategy_slug=body.strategy_slug,
                approval_id=body.approval_id,
                portfolio_id=body.portfolio_id or None,
                operator_identity=f"operator:{ctx.requested_by()}",
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
                portfolio_name=body.portfolio_name,
                starting_cash=body.starting_cash,
            )
        except PaperGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/activations")
def tg_paper_activations(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        return _paper_gov().list_activations(org_id=ctx.org_id, workspace_id=ctx.workspace_id)
    except PlatformContextError as e:
        raise _err(e) from e


class TgPaperOrderBody(BaseModel):
    portfolio_id: str
    strategy_slug: str
    symbol: str
    side: str = "BUY"
    quantity: str
    order_type: str = "MARKET"
    tif: str = "DAY"
    limit_price: str | None = None
    stop_price: str | None = None
    reason: str = ""
    notes: str = ""
    market_regime: str = ""
    confidence: str = ""
    stop: str = ""
    target: str = ""


@router.post("/tg/paper/orders")
def tg_paper_order(body: TgPaperOrderBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.service import PaperGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ORDER_PROPOSE)
        try:
            return _paper_gov().place_order(
                portfolio_id=body.portfolio_id,
                strategy_slug=body.strategy_slug,
                symbol=body.symbol,
                side=body.side,
                quantity=body.quantity,
                order_type=body.order_type,
                tif=body.tif,
                limit_price=body.limit_price,
                stop_price=body.stop_price,
                reason=body.reason,
                notes=body.notes,
                market_regime=body.market_regime,
                confidence=body.confidence,
                stop=body.stop,
                target=body.target,
                org_id=ctx.org_id,
                workspace_id=ctx.workspace_id,
            )
        except PaperGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/portfolios/{pid}/orders")
def tg_paper_orders(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ORDER_READ)
        return _paper_gov().list_orders(pid)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/portfolios/{pid}/positions")
def tg_paper_positions(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        return _paper_gov().list_positions(pid)
    except PlatformContextError as e:
        raise _err(e) from e


class TgPaperTickBody(BaseModel):
    symbol: str
    bid: str
    ask: str
    last: str
    volume: str = "1000000"
    gap_open: bool = False


@router.post("/tg/paper/portfolios/{pid}/tick")
def tg_paper_tick(pid: str, body: TgPaperTickBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.service import PaperGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ORDER_PROPOSE)
        try:
            return _paper_gov().process_market(
                pid, symbol=body.symbol, bid=body.bid, ask=body.ask, last=body.last,
                volume=body.volume, gap_open=body.gap_open,
            )
        except PaperGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/portfolios/{pid}/analytics")
def tg_paper_analytics(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.service import PaperGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        try:
            return _paper_gov().analytics(pid)
        except PaperGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/portfolios/{pid}/journal")
def tg_paper_journal(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ORDER_READ)
        return _paper_gov().list_journal(portfolio_id=pid, org_id=ctx.org_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper/portfolios/{pid}/reconcile")
def tg_paper_reconcile(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.service import PaperGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        try:
            return _paper_gov().reconcile(pid)
        except PaperGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


class TgPaperKillBody(BaseModel):
    reason: str = "operator_halt"
    scope: str = "GLOBAL"


@router.post("/tg/paper/kill-switch")
def tg_paper_kill(body: TgPaperKillBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.domain import KillSwitchScope
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_TRIP)
        return _paper_gov().activate_kill_switch(
            scope=KillSwitchScope(body.scope),
            reason=body.reason,
            activated_by=ctx.requested_by(),
            source_identity="operator",
            org_id=ctx.org_id,
            workspace_id=ctx.workspace_id,
        )
    except PlatformContextError as e:
        raise _err(e) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


@router.get("/tg/paper/kill-switch")
def tg_paper_kill_status(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        gov = _paper_gov()
        if hasattr(gov, "kill_switch_status"):
            try:
                return gov.kill_switch_status(org_id=ctx.org_id, workspace_id=ctx.workspace_id)
            except TypeError:
                return gov.kill_switch_status()
        return {"kill_switches": [], "paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


# ── M200–M207 durable ops extensions ───────────────────────────────────────
@router.get("/tg/paper/storage-status")
def tg_paper_storage(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        gov = _paper_gov()
        if hasattr(gov, "storage_status"):
            return gov.storage_status()
        return {"status": "PROCESS_LOCAL", "durable": False, "paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper/migrate")
def tg_paper_migrate(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        gov = _paper_gov()
        if hasattr(gov, "migrate"):
            return gov.migrate()
        return {"status": "NOOP", "paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


class TgCampaignBody(BaseModel):
    strategy_slug: str
    initial_cash: str = "100000"
    operator_notes: str = ""
    min_trade_count: int = 0


@router.post("/tg/paper/campaigns")
def tg_paper_campaign_create(body: TgCampaignBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.durable.service import DurableGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        gov = _paper_gov()
        if not hasattr(gov, "campaign_create"):
            raise PlatformContextError("NOT_SUPPORTED", "durable campaigns require durable store")
        try:
            return gov.campaign_create(
                strategy_slug=body.strategy_slug, initial_cash=body.initial_cash,
                operator_notes=body.operator_notes, min_trade_count=body.min_trade_count,
                org_id=ctx.org_id, workspace_id=ctx.workspace_id,
            )
        except DurableGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/campaigns")
def tg_paper_campaigns(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        gov = _paper_gov()
        if hasattr(gov, "list_campaigns"):
            return gov.list_campaigns(org_id=ctx.org_id)
        return {"campaigns": [], "paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


class TgCampaignApproveBody(BaseModel):
    approval_id: str


@router.post("/tg/paper/campaigns/{cid}/approve")
def tg_paper_campaign_approve(cid: str, body: TgCampaignApproveBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.durable.service import DurableGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.APPROVAL_DECIDE)
        gov = _paper_gov()
        try:
            return gov.campaign_approve(cid, approval_id=body.approval_id, operator_identity=f"operator:{ctx.requested_by()}")
        except DurableGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper/campaigns/{cid}/start")
def tg_paper_campaign_start(cid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.durable.service import DurableGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        gov = _paper_gov()
        try:
            return gov.campaign_start(cid, operator_identity=f"operator:{ctx.requested_by()}", org_id=ctx.org_id, workspace_id=ctx.workspace_id)
        except DurableGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper/campaigns/{cid}/pause")
def tg_paper_campaign_pause(cid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.durable.service import DurableGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        try:
            return _paper_gov().campaign_pause(cid)
        except DurableGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper/campaigns/{cid}/complete")
def tg_paper_campaign_complete(cid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.durable.service import DurableGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        try:
            return _paper_gov().campaign_complete(cid, operator_identity=f"operator:{ctx.requested_by()}")
        except DurableGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/events")
def tg_paper_events(aggregate_id: str = "", limit: int = 100, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ORDER_READ)
        gov = _paper_gov()
        if hasattr(gov, "list_events"):
            return gov.list_events(aggregate_id=aggregate_id, limit=min(limit, 500))
        return {"events": [], "paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/workers")
def tg_paper_workers(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        gov = _paper_gov()
        return {
            "worker_id": getattr(gov, "worker_id", None),
            "queue_sample": gov.process_queue_once() if hasattr(gov, "process_queue_once") else {},
            "paper_only": True,
        }
    except PlatformContextError as e:
        raise _err(e) from e


class TgBackupBody(BaseModel):
    dest_dir: str = ""


@router.post("/tg/paper/backup")
def tg_paper_backup(body: TgBackupBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from pathlib import Path
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        gov = _paper_gov()
        dest = body.dest_dir or str(Path("data/platform/paper_backups"))
        if hasattr(gov, "backup_create"):
            return gov.backup_create(dest)
        return {"status": "NOOP", "paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


class TgRecoveryBody(BaseModel):
    source_backup: str
    recovery_db: str = "data/platform/paper_recovery.db"


@router.post("/tg/paper/recovery-test")
def tg_paper_recovery(body: TgRecoveryBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        gov = _paper_gov()
        if hasattr(gov, "recovery_test"):
            return gov.recovery_test(body.source_backup, body.recovery_db)
        return {"verdict": "RECOVERY_INCOMPLETE", "paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper/portfolios/{pid}/snapshot")
def tg_paper_snapshot(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        gov = _paper_gov()
        if hasattr(gov, "snapshot"):
            return gov.snapshot(pid)
        return {"paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper/portfolios/{pid}/replay")
def tg_paper_replay(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        gov = _paper_gov()
        if hasattr(gov, "replay"):
            return gov.replay(pid)
        return {"paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/reports/daily")
def tg_paper_report_daily(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        gov = _paper_gov()
        if hasattr(gov, "report_daily"):
            return gov.report_daily()
        return {"kind": "daily", "paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/reports/weekly")
def tg_paper_report_weekly(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        gov = _paper_gov()
        if hasattr(gov, "report_weekly"):
            return gov.report_weekly()
        return {"kind": "weekly", "paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/incidents")
def tg_paper_incidents(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        gov = _paper_gov()
        if hasattr(gov, "list_incidents"):
            return gov.list_incidents()
        return {"incidents": [], "paper_only": True}
    except PlatformContextError as e:
        raise _err(e) from e


# ── M208–M215 Operational Graduation ───────────────────────────────────────
def _ops_gov():
    from saathi.platform.tg.paper_activation.ops.service import default_ops_gov
    return default_ops_gov()


@router.get("/tg/paper/ops/posture")
def tg_ops_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _ops_gov().posture()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/ops/dashboard")
def tg_ops_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        return _ops_gov().ops_dashboard()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/ops/health")
def tg_ops_health(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _ops_gov().health()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/ops/verdict")
def tg_ops_verdict(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _ops_gov().terminal_verdict()
    except PlatformContextError as e:
        raise _err(e) from e


class TgOpsCampaignBody(BaseModel):
    strategy_slug: str
    initial_cash: str = "100000"
    operator_notes: str = ""
    group_id: str = ""
    template_id: str = ""
    owner: str = ""
    tags: list[str] = []
    objectives_text: str = ""
    min_trade_count: int = 0
    min_duration_sec: float = 0


@router.post("/tg/paper/ops/campaigns")
def tg_ops_campaign_create(body: TgOpsCampaignBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.durable.service import DurableGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        try:
            return _ops_gov().campaign_create(
                strategy_slug=body.strategy_slug, initial_cash=body.initial_cash,
                operator_notes=body.operator_notes, group_id=body.group_id,
                template_id=body.template_id, owner=body.owner or ctx.requested_by(),
                tags=body.tags, objectives_text=body.objectives_text,
                min_trade_count=body.min_trade_count, min_duration_sec=body.min_duration_sec,
                org_id=ctx.org_id, workspace_id=ctx.workspace_id,
            )
        except DurableGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/ops/campaigns")
def tg_ops_campaigns(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        return _ops_gov().list_campaigns(org_id=ctx.org_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/ops/campaigns/{cid}")
def tg_ops_campaign_get(cid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.durable.service import DurableGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        try:
            return _ops_gov().campaign_get(cid)
        except DurableGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper/ops/campaigns/{cid}/clone")
def tg_ops_campaign_clone(cid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.durable.service import DurableGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        try:
            return _ops_gov().campaign_clone(cid, owner=ctx.requested_by())
        except DurableGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper/ops/campaigns/{cid}/archive")
def tg_ops_campaign_archive(cid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.durable.service import DurableGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        try:
            return _ops_gov().campaign_archive(cid, operator_identity=f"operator:{ctx.requested_by()}")
        except DurableGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper/ops/campaigns/{cid}/resume")
def tg_ops_campaign_resume(cid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.durable.service import DurableGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        try:
            return _ops_gov().campaign_resume(cid, operator_identity=f"operator:{ctx.requested_by()}")
        except DurableGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


class TgOpsCompareBody(BaseModel):
    campaign_ids: list[str]


@router.post("/tg/paper/ops/campaigns/compare")
def tg_ops_campaign_compare(body: TgOpsCompareBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        return _ops_gov().campaign_compare(body.campaign_ids)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper/ops/campaigns/{cid}/graduate")
def tg_ops_graduate(cid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.durable.service import DurableGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        try:
            return _ops_gov().graduate(cid, actor=f"operator:{ctx.requested_by()}")
        except DurableGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper/ops/campaigns/{cid}/certify")
def tg_ops_certify(cid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.paper_activation.durable.service import DurableGovError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        try:
            return _ops_gov().certify_campaign(cid, actor=f"operator:{ctx.requested_by()}")
        except DurableGovError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/ops/graduation")
def tg_ops_graduation_rankings(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        return _ops_gov().strategy_rankings()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper/ops/intelligence/scan")
def tg_ops_intel_scan(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _ops_gov().scan_intelligence()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/ops/recommendations")
def tg_ops_recommendations(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _ops_gov().recommendations()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/ops/analytics/rolling/{pid}")
def tg_ops_rolling(pid: str, window: int = 20, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        return _ops_gov().rolling_analytics(pid, window=window)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/ops/reports/weekly")
def tg_ops_weekly(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        return _ops_gov().weekly_report()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/ops/reports/monthly")
def tg_ops_monthly(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        return _ops_gov().monthly_report()
    except PlatformContextError as e:
        raise _err(e) from e


class TgOpsSimBody(BaseModel):
    scenario: str
    portfolio_id: str = ""


@router.post("/tg/paper/ops/simulate")
def tg_ops_simulate(body: TgOpsSimBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _ops_gov().simulate(body.scenario, portfolio_id=body.portfolio_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper/ops/simulate/suite")
def tg_ops_simulate_suite(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _ops_gov().simulate_suite()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/ops/evidence")
def tg_ops_evidence(campaign_id: str = "", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _ops_gov().list_evidence(campaign_id=campaign_id)
    except PlatformContextError as e:
        raise _err(e) from e


class TgOpsGroupBody(BaseModel):
    name: str
    description: str = ""
    tags: list[str] = []


@router.post("/tg/paper/ops/groups")
def tg_ops_create_group(body: TgOpsGroupBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        return _ops_gov().create_group(
            name=body.name, description=body.description, tags=body.tags,
            owner=ctx.requested_by(), org_id=ctx.org_id, workspace_id=ctx.workspace_id,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper/ops/groups")
def tg_ops_groups(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_READ)
        return _ops_gov().list_groups(org_id=ctx.org_id)
    except PlatformContextError as e:
        raise _err(e) from e


# ── M216–M223 Broker Integration Sandbox Architecture ───────────────────────
# PAPER ONLY. No live brokers. No API credentials. No exchange authentication.
def _broker_sandbox():
    from saathi.platform.tg.broker_sandbox.service import default_broker_sandbox
    return default_broker_sandbox()


@router.get("/tg/broker-sandbox/posture")
def tg_bs_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_sandbox().posture()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-sandbox/verdict")
def tg_bs_verdict(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_sandbox().terminal_verdict()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-sandbox/dashboard")
def tg_bs_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        return _broker_sandbox().dashboard()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-sandbox/abstraction")
def tg_bs_abstraction(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_sandbox().abstraction()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-sandbox/brokers")
def tg_bs_brokers(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_sandbox().list_brokers()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-sandbox/brokers/{broker_id}")
def tg_bs_broker(broker_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.broker_sandbox.service import BrokerSandboxError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        try:
            return _broker_sandbox().get_broker(broker_id)
        except BrokerSandboxError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-sandbox/capabilities")
def tg_bs_capabilities(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_sandbox().list_capabilities()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/broker-sandbox/brokers/{broker_id}/connect")
def tg_bs_connect_refused(broker_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    """Always refuses real connections — architecture safety surface."""
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_sandbox().refuse_connect(broker_id)
    except PlatformContextError as e:
        raise _err(e) from e


class TgBsCredBody(BaseModel):
    broker_id: str
    label: str = ""
    provider_metadata: dict = {}
    permission_scopes: list[str] = []


@router.post("/tg/broker-sandbox/credentials")
def tg_bs_cred_create(body: TgBsCredBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.broker_sandbox.service import BrokerSandboxError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        try:
            return _broker_sandbox().create_credential_ref(
                broker_id=body.broker_id,
                label=body.label,
                provider_metadata=body.provider_metadata,
                permission_scopes=body.permission_scopes or None,
                actor=f"operator:{ctx.requested_by()}",
            )
        except BrokerSandboxError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-sandbox/credentials")
def tg_bs_creds(broker_id: str = "", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_sandbox().list_credential_refs(broker_id=broker_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/broker-sandbox/credentials/{ref_id}/use")
def tg_bs_cred_use(ref_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    """Always fails closed — credentials are unusable."""
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_sandbox().attempt_use_credential(ref_id)
    except PlatformContextError as e:
        raise _err(e) from e


class TgBsEmuSessionBody(BaseModel):
    seed: int = 42
    latency_ms: int = 0
    market_open: bool = True


@router.post("/tg/broker-sandbox/emulator/sessions")
def tg_bs_emu_session(body: TgBsEmuSessionBody = TgBsEmuSessionBody(), authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        return _broker_sandbox().emulator_session(
            seed=body.seed, latency_ms=body.latency_ms, market_open=body.market_open,
        )
    except PlatformContextError as e:
        raise _err(e) from e


class TgBsEmuOrderBody(BaseModel):
    session_id: str
    symbol: str = "AAA"
    side: str = "BUY"
    order_type: str = "MARKET"
    quantity: str = "1"
    limit_price: str | None = None
    client_order_id: str = ""
    partial_fill_ratio: str | None = None


@router.post("/tg/broker-sandbox/emulator/orders")
def tg_bs_emu_order(body: TgBsEmuOrderBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.broker_sandbox.service import BrokerSandboxError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        try:
            return _broker_sandbox().emulator_place_order(
                body.session_id,
                symbol=body.symbol, side=body.side, order_type=body.order_type,
                quantity=body.quantity, limit_price=body.limit_price,
                client_order_id=body.client_order_id,
                partial_fill_ratio=body.partial_fill_ratio,
            )
        except BrokerSandboxError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-sandbox/emulator/orders")
def tg_bs_emu_orders(session_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_ACCOUNT_READ)
        return _broker_sandbox().emulator_orders(session_id)
    except PlatformContextError as e:
        raise _err(e) from e


class TgBsTrustBody(BaseModel):
    broker_id: str
    notes: str = ""
    paper_graduation_ref: str = ""


@router.post("/tg/broker-sandbox/trust/pipelines")
def tg_bs_trust_create(body: TgBsTrustBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.broker_sandbox.service import BrokerSandboxError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        try:
            return _broker_sandbox().trust_create(
                broker_id=body.broker_id,
                created_by=f"operator:{ctx.requested_by()}",
                notes=body.notes,
                paper_graduation_ref=body.paper_graduation_ref,
            )
        except BrokerSandboxError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-sandbox/trust/pipelines")
def tg_bs_trust_list(broker_id: str = "", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_sandbox().trust_list(broker_id=broker_id)
    except PlatformContextError as e:
        raise _err(e) from e


class TgBsTrustDecideBody(BaseModel):
    stage: str
    decision: str
    reason: str = ""
    actor_role: str = "OPERATOR"


@router.post("/tg/broker-sandbox/trust/pipelines/{pid}/decide")
def tg_bs_trust_decide(pid: str, body: TgBsTrustDecideBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.broker_sandbox.service import BrokerSandboxError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.STRATEGY_EDIT)
        try:
            return _broker_sandbox().trust_decide(
                pid, stage=body.stage, decision=body.decision,
                actor=f"operator:{ctx.requested_by()}",
                actor_role=body.actor_role, reason=body.reason,
            )
        except BrokerSandboxError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-sandbox/trust/pipelines/{pid}/gate")
def tg_bs_trust_gate(pid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.broker_sandbox.service import BrokerSandboxError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        try:
            return _broker_sandbox().trust_gate(pid)
        except BrokerSandboxError as e:
            raise PlatformContextError(e.code, e.message) from e
    except PlatformContextError as e:
        raise _err(e) from e


class TgBsFailBody(BaseModel):
    scenario: str
    session_id: str = ""


@router.post("/tg/broker-sandbox/failure/run")
def tg_bs_fail_run(body: TgBsFailBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_sandbox().failure_run(body.scenario, session_id=body.session_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/broker-sandbox/failure/suite")
def tg_bs_fail_suite(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_sandbox().failure_suite()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/broker-sandbox/security/validate")
def tg_bs_security(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_sandbox().security_validate()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-sandbox/audit")
def tg_bs_audit(limit: int = 100, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_sandbox().audit_timeline(limit=limit)
    except PlatformContextError as e:
        raise _err(e) from e


# ── M224–M231 Read-Only Broker Connectivity Readiness ────────────────────────
# SIMULATION ONLY. No real brokers. No real credentials. No order submission.
def _broker_readiness():
    from saathi.platform.tg.broker_readiness.service import default_broker_readiness
    return default_broker_readiness()


@router.get("/tg/broker-readiness/posture")
def tg_br_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().posture()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-readiness/verdict")
def tg_br_verdict(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().terminal_verdict()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-readiness/dashboard")
def tg_br_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().dashboard()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-readiness/providers")
def tg_br_providers(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().list_providers()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-readiness/adapters")
def tg_br_adapters(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().adapter_contract()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-readiness/capabilities")
def tg_br_capabilities(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().list_adapter_ops()
    except PlatformContextError as e:
        raise _err(e) from e


class BrPolicyBody(BaseModel):
    operation: str
    scopes: list[str] = []
    permissions: list[str] = []
    environment: str = "SIMULATION"
    approval_state: str = "UNAPPROVED"
    owner_signoff: bool = False
    expired: bool = False
    revoked: bool = False
    withdrawal_permission: bool = False
    trading_permission: bool = False
    administrative_permission: bool = False
    production_authority: bool = False
    live_trading_authority: bool = False
    real_connection_requested: bool = False


@router.post("/tg/broker-readiness/policy/evaluate")
def tg_br_policy(body: BrPolicyBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().policy_check(**body.model_dump())
    except PlatformContextError as e:
        raise _err(e) from e


class BrCredentialProposeBody(BaseModel):
    provider_id: str = "sim.readonly.fixture"
    credential_type: str = "SIMULATED_METADATA"
    declared_scopes: list[str] = ["ACCOUNT_METADATA_READ", "BALANCE_READ", "POSITION_READ"]
    environment: str = "SIMULATION"
    metadata: dict = {}


@router.post("/tg/broker-readiness/credentials")
def tg_br_cred_propose(body: BrCredentialProposeBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.broker_readiness.service import BrokerReadinessError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_CONFIGURE)
        # Reject any secret-shaped fields in raw body extras — model only allows metadata dict
        return _broker_readiness().propose_credential(
            provider_id=body.provider_id,
            credential_type=body.credential_type,
            declared_scopes=body.declared_scopes,
            environment=body.environment,
            actor=ctx.user_id if hasattr(ctx, "user_id") else "api",
            metadata=body.metadata,
        )
    except BrokerReadinessError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message}) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-readiness/credentials")
def tg_br_cred_list(provider_id: str = "", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().list_credentials(provider_id=provider_id)
    except PlatformContextError as e:
        raise _err(e) from e


class BrLifecycleBody(BaseModel):
    to_state: str
    reason: str = ""


@router.post("/tg/broker-readiness/credentials/{cid}/lifecycle")
def tg_br_cred_life(cid: str, body: BrLifecycleBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.broker_readiness.service import BrokerReadinessError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_CONFIGURE)
        return _broker_readiness().credential_lifecycle(cid, to_state=body.to_state, reason=body.reason, actor=getattr(ctx, "user_id", "api"))
    except BrokerReadinessError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message}) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/broker-readiness/credentials/{cid}/advance")
def tg_br_cred_advance(cid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.broker_readiness.service import BrokerReadinessError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_CONFIGURE)
        return _broker_readiness().advance_credential(cid, actor=getattr(ctx, "user_id", "api"))
    except BrokerReadinessError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message}) from e
    except PlatformContextError as e:
        raise _err(e) from e


class BrScopeBody(BaseModel):
    requested: list[str] = []
    declared: list[str] = []
    provider_reported: list[str] = []
    approved: list[str] = []
    credential_id: str = ""


@router.post("/tg/broker-readiness/scope/validate")
def tg_br_scope(body: BrScopeBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().scope_check(**body.model_dump())
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/broker-readiness/sessions")
def tg_br_session_create(provider_id: str = "sim.readonly.fixture", credential_id: str = "", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_CONFIGURE)
        return _broker_readiness().session_create(provider_id=provider_id, credential_id=credential_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/broker-readiness/sessions/{sid}/simulate")
def tg_br_session_sim(sid: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.broker_readiness.service import BrokerReadinessError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_CONFIGURE)
        return _broker_readiness().session_simulate(sid)
    except BrokerReadinessError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message}) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-readiness/sessions")
def tg_br_sessions(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().list_sessions()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/broker-readiness/snapshots/load")
def tg_br_snap_load(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_CONFIGURE)
        return _broker_readiness().snapshot_load()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-readiness/snapshots")
def tg_br_snaps(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().list_snapshots()
    except PlatformContextError as e:
        raise _err(e) from e


class BrReconcileBody(BaseModel):
    provider_snapshot_id: str
    local_snapshot_id: str = ""


@router.post("/tg/broker-readiness/reconcile")
def tg_br_reconcile(body: BrReconcileBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.broker_readiness.service import BrokerReadinessError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().reconcile_run(body.provider_snapshot_id, body.local_snapshot_id)
    except BrokerReadinessError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message}) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/broker-readiness/drills/expiry")
def tg_br_expiry(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_CONFIGURE)
        return _broker_readiness().expiry_drill()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/broker-readiness/drills/revocation")
def tg_br_revocation(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_CONFIGURE)
        return _broker_readiness().revocation_drill()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/broker-readiness/drills/{scenario}")
def tg_br_drill(scenario: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_CONFIGURE)
        aliases = {
            "expiry": "credential_expiry_during_session",
            "revocation": "credential_revocation_during_session",
        }
        scenario = aliases.get(scenario, scenario)
        return _broker_readiness().drill_run(scenario)
    except PlatformContextError as e:
        raise _err(e) from e
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/tg/broker-readiness/incidents")
def tg_br_incidents(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().list_drills()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/broker-readiness/security/scan")
def tg_br_security(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().security_scan()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/broker-readiness/audit")
def tg_br_audit(limit: int = 100, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().audit_timeline(limit=limit)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/broker-readiness/certify")
def tg_br_certify(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().certify()
    except PlatformContextError as e:
        raise _err(e) from e


class BrTransportBody(BaseModel):
    url: str


@router.post("/tg/broker-readiness/transport/probe")
def tg_br_transport(body: BrTransportBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().transport_probe(body.url)
    except PlatformContextError as e:
        raise _err(e) from e


class BrLlmBody(BaseModel):
    action: str


@router.post("/tg/broker-readiness/llm/refuse")
def tg_br_llm(body: BrLlmBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _broker_readiness().llm_refuse(body.action)
    except PlatformContextError as e:
        raise _err(e) from e

# ── M232–M239 Integration Assurance (reproducibility / supply-chain / planning) ──
# REPRODUCIBILITY AND PLANNING ONLY. No real connectivity. No credentials.
def _integration_assurance():
    from saathi.platform.tg.integration_assurance.service import default_integration_assurance
    return default_integration_assurance()


@router.get("/tg/integration-assurance/posture")
def tg_ia_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().posture()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/integration-assurance/verdict")
def tg_ia_verdict(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().terminal_verdict()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/integration-assurance/dashboard")
def tg_ia_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().dashboard()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/integration-assurance/source-audit")
def tg_ia_source(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().source_audit()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/integration-assurance/reproduction/clean-worktree")
def tg_ia_wt(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().clean_worktree()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/integration-assurance/reproduction/clean-clone")
def tg_ia_cc(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().clean_clone()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/integration-assurance/environment")
def tg_ia_env(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().env_contract()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/integration-assurance/environment/preflight")
def tg_ia_preflight(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().env_preflight()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/integration-assurance/dependencies")
def tg_ia_deps(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().dependency_inventory()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/integration-assurance/lockfiles")
def tg_ia_locks(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().lockfile_checks()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/integration-assurance/sbom")
def tg_ia_sbom(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().generate_sbom()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/integration-assurance/provenance")
def tg_ia_prov(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().provenance()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/integration-assurance/supply-chain")
def tg_ia_sc(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().threat_model()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/integration-assurance/assurance-gates")
def tg_ia_gates(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().assurance_gates()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/integration-assurance/authorization/domains")
def tg_ia_domains(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().auth_domains()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/integration-assurance/authorization/plan")
def tg_ia_plan(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.integration_assurance.service import IntegrationAssuranceError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_CONFIGURE)
        return _integration_assurance().auth_create_plan()
    except IntegrationAssuranceError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message}) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/integration-assurance/authorization/eligibility")
def tg_ia_elig(plan_id: str = "", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().auth_eligibility(plan_id)
    except PlatformContextError as e:
        raise _err(e) from e


class IaApprovalBody(BaseModel):
    plan_id: str
    domain: str
    approver_identity: str = ""
    role: str = "human"
    scope: str = "read-only-planning"
    provider: str = ""
    environment: str = "PLANNING"
    automated: bool = False
    evidence_refs: list[str] = []
    acknowledgements: list[str] = []


@router.post("/tg/integration-assurance/authorization/approval")
def tg_ia_appr(body: IaApprovalBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        from saathi.platform.tg.integration_assurance.service import IntegrationAssuranceError
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_CONFIGURE)
        # Never accept credentials
        return _integration_assurance().auth_record_approval(
            body.plan_id, body.domain,
            approver_identity=body.approver_identity,
            role=body.role,
            scope=body.scope,
            provider=body.provider,
            environment=body.environment,
            automated=body.automated,
            evidence_refs=body.evidence_refs,
            acknowledgements=body.acknowledgements,
            actor=getattr(ctx, "user_id", "api"),
        )
    except IntegrationAssuranceError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message}) from e
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/integration-assurance/authorization/owner-signoff-attempt")
def tg_ia_owner_block(plan_id: str = "", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        if not plan_id:
            plan = _integration_assurance().auth_create_plan()
            plan_id = plan["plan"]["id"]
        return _integration_assurance().auth_owner_signoff_attempt(plan_id, actor="agent")
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/integration-assurance/authorization/activate")
def tg_ia_activate(plan_id: str = "", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().auth_activate_connectivity(plan_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/integration-assurance/network-policy")
def tg_ia_net(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().network_policy()
    except PlatformContextError as e:
        raise _err(e) from e


class IaTransportBody(BaseModel):
    url: str


@router.post("/tg/integration-assurance/transport/probe")
def tg_ia_transport(body: IaTransportBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().transport_probe(body.url)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/integration-assurance/security/scan")
def tg_ia_sec(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().security_scan()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/integration-assurance/audit")
def tg_ia_audit(limit: int = 100, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().audit_timeline(limit=limit)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/integration-assurance/certify")
def tg_ia_certify(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().certify()
    except PlatformContextError as e:
        raise _err(e) from e


class IaLlmBody(BaseModel):
    action: str


@router.post("/tg/integration-assurance/llm/refuse")
def tg_ia_llm(body: IaLlmBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _integration_assurance().llm_refuse(body.action)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/integration-assurance/evidence")
def tg_ia_evidence(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return {
            "path": "docs/trading/m232_m239_evidence/",
            "REAL_CONNECTIVITY_AUTHORIZED": False,
            "note": "Evidence generated offline; UI displays findings only",
        }
    except PlatformContextError as e:
        raise _err(e) from e



# ── M240–M247 Provider Canary Planning (PLANNING ONLY) ──────────────────────
def _provider_canary_planning():
    from saathi.platform.tg.provider_canary_planning.service import default_provider_canary_planning
    return default_provider_canary_planning()


@router.get("/tg/provider-canary-planning/posture")
def tg_pcp_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().posture()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/verdict")
def tg_pcp_verdict(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().terminal_verdict()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/dashboard")
def tg_pcp_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().dashboard()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/candidates")
def tg_pcp_candidates(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().candidates()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/rankings")
def tg_pcp_rankings(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().rankings()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/sources")
def tg_pcp_sources(provider: str | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().list_sources(provider)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/preferred")
def tg_pcp_preferred(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().preferred()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/fallback")
def tg_pcp_fallback(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().fallback()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/capabilities")
def tg_pcp_caps(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().capabilities_map()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/endpoints")
def tg_pcp_endpoints(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().endpoints()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/scopes")
def tg_pcp_scopes(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().scopes()
    except PlatformContextError as e:
        raise _err(e) from e


class PcpScopesBody(BaseModel):
    scopes: list[str] = []


@router.post("/tg/provider-canary-planning/scopes/validate")
def tg_pcp_scopes_validate(body: PcpScopesBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().validate_scopes(body.scopes)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/eligibility")
def tg_pcp_elig(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().eligibility_review()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/terms")
def tg_pcp_terms(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().terms_review()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/canary")
def tg_pcp_canary(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().canary_design()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/provider-canary-planning/canary/activate")
def tg_pcp_canary_activate(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().canary_activate_attempt()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/credential-ceremony")
def tg_pcp_cred(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().credential_ceremony()
    except PlatformContextError as e:
        raise _err(e) from e


class PcpCredBody(BaseModel):
    api_key: str | None = None
    secret: str | None = None
    token: str | None = None


@router.post("/tg/provider-canary-planning/credentials")
def tg_pcp_cred_reject(body: PcpCredBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        val = None
        if body:
            val = body.api_key or body.secret or body.token
        return _provider_canary_planning().refuse_credentials(val)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/provider-canary-planning/oauth")
def tg_pcp_oauth(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().refuse_oauth()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/monitoring")
def tg_pcp_mon(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().monitoring_plan()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/reconciliation")
def tg_pcp_recon(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().reconciliation_plan()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/acceptance")
def tg_pcp_accept(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().acceptance_gates()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/abort")
def tg_pcp_abort(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().abort_gates()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/owner-package")
def tg_pcp_owner(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().owner_package()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/provider-canary-planning/owner-signoff")
def tg_pcp_owner_signoff(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().owner_auto_signoff_attempt()
    except PlatformContextError as e:
        raise _err(e) from e


class PcpReviewBody(BaseModel):
    status: str
    notes: str = ""


@router.post("/tg/provider-canary-planning/planning-review-status")
def tg_pcp_review(body: PcpReviewBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_CONFIGURE)
        return _provider_canary_planning().planning_review_status(body.status, notes=body.notes, actor="api")
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/network-policy")
def tg_pcp_net(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().network_policy()
    except PlatformContextError as e:
        raise _err(e) from e


class PcpTransportBody(BaseModel):
    url: str


@router.post("/tg/provider-canary-planning/transport/probe")
def tg_pcp_transport(body: PcpTransportBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().transport_probe(body.url)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/provider-canary-planning/security/scan")
def tg_pcp_sec(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().security_scan()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/threat-model")
def tg_pcp_threats(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().threat_model()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/audit")
def tg_pcp_audit(limit: int = 100, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().audit_timeline(limit=limit)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/provider-canary-planning/certify")
def tg_pcp_certify(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().certify()
    except PlatformContextError as e:
        raise _err(e) from e


class PcpLlmBody(BaseModel):
    action: str


@router.post("/tg/provider-canary-planning/llm/refuse")
def tg_pcp_llm(body: PcpLlmBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _provider_canary_planning().llm_refuse(body.action)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/provider-canary-planning/evidence")
def tg_pcp_evidence(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return {
            "path": "docs/trading/m240_m247_evidence/",
            "REAL_CONNECTIVITY_AUTHORIZED": False,
            "note": "Evidence generated offline; UI displays findings only",
        }
    except PlatformContextError as e:
        raise _err(e) from e


# ── M248–M255 Institutional Investment Intelligence (PAPER ONLY) ─────────────
def _tg_intelligence():
    from saathi.platform.tg.intelligence.service import default_intelligence
    return default_intelligence()


@router.get("/tg/intelligence/posture")
def tg_ii_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().posture()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/verdict")
def tg_ii_verdict(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().terminal_verdict()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/dashboard")
def tg_ii_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().dashboard()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/strategies")
def tg_ii_strategies(category: str | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().list_strategies(category)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/strategies/categories")
def tg_ii_strategy_cats(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().strategy_categories()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/strategies/{strategy_id}")
def tg_ii_strategy_get(strategy_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().get_strategy(strategy_id)
    except PlatformContextError as e:
        raise _err(e) from e


class IiStrategyRunBody(BaseModel):
    bars: list[dict] | None = None
    params: dict | None = None


@router.post("/tg/intelligence/strategies/{strategy_id}/run")
def tg_ii_strategy_run(strategy_id: str, body: IiStrategyRunBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        body = body or IiStrategyRunBody()
        return _tg_intelligence().strategy_run(strategy_id, bars=body.bars, params=body.params)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/portfolio")
def tg_ii_portfolio(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().portfolio_overview()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/portfolio/risk")
def tg_ii_portfolio_risk(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().portfolio_risk()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/portfolio/report")
def tg_ii_portfolio_report(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().portfolio_report()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/analytics")
def tg_ii_analytics(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().analytics()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/risk")
def tg_ii_risk(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().portfolio_risk()
    except PlatformContextError as e:
        raise _err(e) from e


class IiBacktestBody(BaseModel):
    strategy_id: str = "tf_dual_ma"
    seed: int = 42
    capital: float = 100000.0
    commission_bps: float = 5.0
    slippage_bps: float = 8.0


@router.post("/tg/intelligence/backtests")
def tg_ii_backtest(body: IiBacktestBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        body = body or IiBacktestBody()
        return _tg_intelligence().backtest(
            body.strategy_id, seed=body.seed, capital=body.capital,
            commission_bps=body.commission_bps, slippage_bps=body.slippage_bps,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/backtests")
def tg_ii_backtests_list(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().list_backtests()
    except PlatformContextError as e:
        raise _err(e) from e


class IiCompareBody(BaseModel):
    strategy_ids: list[str] | None = None
    seed: int = 42


@router.post("/tg/intelligence/backtests/compare")
def tg_ii_backtest_compare(body: IiCompareBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        body = body or IiCompareBody()
        return _tg_intelligence().backtest_compare(body.strategy_ids, seed=body.seed)
    except PlatformContextError as e:
        raise _err(e) from e


class IiWalkForwardBody(BaseModel):
    strategy_id: str = "tf_dual_ma"
    seed: int = 42
    n_folds: int = 3


@router.post("/tg/intelligence/simulations/walk-forward")
def tg_ii_wf(body: IiWalkForwardBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        body = body or IiWalkForwardBody()
        return _tg_intelligence().run_walk_forward(body.strategy_id, seed=body.seed, n_folds=body.n_folds)
    except PlatformContextError as e:
        raise _err(e) from e


class IiMonteCarloBody(BaseModel):
    n_simulations: int = 200
    seed: int = 42
    horizon: int = 60
    target_return: float = 0.10


@router.post("/tg/intelligence/simulations/monte-carlo")
def tg_ii_mc(body: IiMonteCarloBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        body = body or IiMonteCarloBody()
        return _tg_intelligence().run_monte_carlo(
            n_simulations=body.n_simulations, seed=body.seed,
            horizon=body.horizon, target_return=body.target_return,
        )
    except PlatformContextError as e:
        raise _err(e) from e


class IiCommitteeBody(BaseModel):
    instrument: str = "SPY"
    context: dict | None = None


@router.post("/tg/intelligence/committee")
def tg_ii_committee(body: IiCommitteeBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        body = body or IiCommitteeBody()
        return _tg_intelligence().committee_review(body.instrument, context=body.context)
    except PlatformContextError as e:
        raise _err(e) from e


class IiExplainBody(BaseModel):
    instrument: str = "SPY"
    action: str | None = None
    strategy_id: str | None = None
    context: dict | None = None


@router.post("/tg/intelligence/explanations")
def tg_ii_explain(body: IiExplainBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        body = body or IiExplainBody()
        return _tg_intelligence().explain(
            instrument=body.instrument, action=body.action,
            strategy_id=body.strategy_id, context=body.context,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/decisions")
def tg_ii_decisions(limit: int = 50, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().decisions(limit=limit)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/watchlists")
def tg_ii_watchlists(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().watchlists()
    except PlatformContextError as e:
        raise _err(e) from e


class IiWatchlistBody(BaseModel):
    name: str
    symbols: list[str] = []


@router.post("/tg/intelligence/watchlists")
def tg_ii_watchlist_upsert(body: IiWatchlistBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().upsert_watchlist(body.name, body.symbols)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/alerts")
def tg_ii_alerts(limit: int = 50, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().alerts(limit=limit)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/timeline")
def tg_ii_timeline(limit: int = 100, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().timeline(limit=limit)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/intelligence/confidence-trends")
def tg_ii_conf(limit: int = 50, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().confidence_trends(limit=limit)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/intelligence/security/scan")
def tg_ii_sec(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().security_scan()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/intelligence/certify")
def tg_ii_certify(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().certify()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/intelligence/broker/connect")
def tg_ii_broker_refuse(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().refuse_broker()
    except PlatformContextError as e:
        raise _err(e) from e


class IiCredBody(BaseModel):
    api_key: str | None = None
    secret: str | None = None


@router.post("/tg/intelligence/credentials")
def tg_ii_cred_refuse(body: IiCredBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        val = None
        if body:
            val = body.api_key or body.secret
        return _tg_intelligence().refuse_credentials(val)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/intelligence/orders")
def tg_ii_order_refuse(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_intelligence().refuse_order()
    except PlatformContextError as e:
        raise _err(e) from e


# ── M256–M263 Market Data & Signal Validation (RESEARCH ONLY) ────────────────
def _tg_market_data():
    from saathi.platform.tg.market_data.service import default_market_data
    return default_market_data()


@router.get("/tg/research-data/posture")
def tg_md_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().posture()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-data/verdict")
def tg_md_verdict(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().terminal_verdict()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-data/dashboard")
def tg_md_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().dashboard()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-data/datasets")
def tg_md_datasets(state: str | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().list_datasets(state)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-data/datasets/{dataset_id}")
def tg_md_dataset_get(dataset_id: str, version: str | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().get_dataset(dataset_id, version)
    except PlatformContextError as e:
        raise _err(e) from e


class MdRegisterBody(BaseModel):
    name: str
    description: str = ""
    provider: str = "local"
    source_type: str = "REPOSITORY_FIXTURE"
    source_ref: str = ""
    market: str = "US"
    exchange: str = "XNAS"
    asset_class: str = "equity"
    frequency: str = "1d"
    licence_type: str = "CC0-1.0"
    checksum: str = ""
    is_synthetic: bool = False
    dataset_version: str = "v1"


@router.post("/tg/research-data/datasets/register")
def tg_md_register(body: MdRegisterBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().register_dataset(**body.model_dump())
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-data/datasets/{dataset_id}/quarantine")
def tg_md_quarantine(dataset_id: str, version: str = "v1", reason: str = "quarantined", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().quarantine_dataset(dataset_id, version, reason)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-data/datasets/{dataset_id}/provenance")
def tg_md_provenance(dataset_id: str, version: str = "v1", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().get_provenance(dataset_id, version)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-data/datasets/{dataset_id}/licence")
def tg_md_licence(dataset_id: str, version: str = "v1", use_case: str = "local_research", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().licence_check(dataset_id, version, use_case)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-data/datasets/{dataset_id}/ingest")
def tg_md_ingest(dataset_id: str, version: str = "v1", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().ingest(dataset_id, version)
    except PlatformContextError as e:
        raise _err(e) from e
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/tg/research-data/datasets/{dataset_id}/ingestion-report")
def tg_md_ingest_report(dataset_id: str, version: str | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().ingest_report(dataset_id, version)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-data/datasets/{dataset_id}/quality")
def tg_md_quality(dataset_id: str, version: str = "v1", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().quality_check(dataset_id, version)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-data/datasets/{dataset_id}/quality-report")
def tg_md_quality_report(dataset_id: str, version: str = "v1", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().quality_report(dataset_id, version)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-data/calendars/{exchange}")
def tg_md_calendar(exchange: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().calendar.get(exchange)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-data/datasets/{dataset_id}/corporate-actions")
def tg_md_ca(dataset_id: str, version: str = "v1", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().list_corporate_actions(dataset_id, version)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-data/datasets/{dataset_id}/bias-check")
def tg_md_bias(dataset_id: str, version: str = "v1", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().bias_check(dataset_id, version)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-data/datasets/{dataset_id}/split")
def tg_md_split(dataset_id: str, version: str = "v1", kind: str = "chronological_holdout", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().split_dataset(dataset_id, version, kind=kind)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-data/features")
def tg_md_features(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().feature_list()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-data/features/{feature_id}/lineage")
def tg_md_feature_lineage(feature_id: str, version: str | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().feature_lineage(feature_id, version)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-data/datasets/{dataset_id}/features/build")
def tg_md_feature_build(dataset_id: str, version: str = "v1", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().feature_build(dataset_id, version)
    except PlatformContextError as e:
        raise _err(e) from e


class MdValidateBody(BaseModel):
    strategy_id: str = "tf_dual_ma"
    version: str = "v1"
    commission_bps: float = 5.0
    slippage_bps: float = 8.0
    seed: int = 42
    trial_count: int = 1


@router.post("/tg/research-data/datasets/{dataset_id}/validate")
def tg_md_validate(dataset_id: str, body: MdValidateBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        body = body or MdValidateBody()
        split = _tg_market_data().split_dataset(dataset_id, body.version)
        return _tg_market_data().validate_signal(
            body.strategy_id, dataset_id, body.version,
            split=split, commission_bps=body.commission_bps,
            slippage_bps=body.slippage_bps, seed=body.seed, trial_count=body.trial_count,
        )
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-data/bootstrap")
def tg_md_bootstrap(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().bootstrap_fixture_pipeline()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-data/certify")
def tg_md_certify(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().certify()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-data/evidence")
def tg_md_evidence(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().evidence_bundle()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-data/security")
def tg_md_security(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().security_scan()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-data/broker/connect")
def tg_md_broker_refuse(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().refuse_broker()
    except PlatformContextError as e:
        raise _err(e) from e


class MdCredBody(BaseModel):
    api_key: str | None = None
    secret: str | None = None


@router.post("/tg/research-data/credentials")
def tg_md_cred_refuse(body: MdCredBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        val = None
        if body:
            val = body.api_key or body.secret
        return _tg_market_data().refuse_credentials(val)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-data/orders")
def tg_md_order_refuse(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().refuse_order()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-data/canary/activate")
def tg_md_canary_refuse(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_data().refuse_canary()
    except PlatformContextError as e:
        raise _err(e) from e


# ── M272–M279 Multi-Strategy Research Lab (RESEARCH ONLY) ────────────────────

def _tg_research_lab():
    from saathi.platform.tg.research_lab.service import default_research_lab
    return default_research_lab()


@router.get("/tg/research-lab/posture")
def tg_rl_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().posture()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-lab/verdict")
def tg_rl_verdict(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().terminal_verdict()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-lab/dashboard")
def tg_rl_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().dashboard()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-lab/experiments")
def tg_rl_experiments(status: str | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().list_experiments(status)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-lab/experiments/{experiment_id}")
def tg_rl_experiment_get(experiment_id: str, version: str = "v1", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().get_experiment(experiment_id, version)
    except PlatformContextError as e:
        raise _err(e) from e


class RlExperimentCreateBody(BaseModel):
    name: str = "api_experiment"
    description: str = ""
    research_question: str = ""
    hypothesis: str = ""
    strategy_ids: list[str] = ["tf_dual_ma"]
    random_seed: int = 42


@router.post("/tg/research-lab/experiments")
def tg_rl_experiment_create(body: RlExperimentCreateBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().create_experiment(
            body.name,
            description=body.description,
            research_question=body.research_question,
            hypothesis=body.hypothesis,
            strategy_ids=body.strategy_ids,
            random_seed=body.random_seed,
            actor=getattr(ctx, "actor_id", None) or "api",
        )
    except PlatformContextError as e:
        raise _err(e) from e
    except Exception as e:
        from saathi.platform.tg.research_lab.errors import ResearchLabError
        if isinstance(e, ResearchLabError):
            return e.to_dict()
        raise


@router.post("/tg/research-lab/experiments/{experiment_id}/pre-register")
def tg_rl_pre_register(experiment_id: str, version: str = "v1", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().pre_register(experiment_id, version)
    except PlatformContextError as e:
        raise _err(e) from e
    except Exception as e:
        from saathi.platform.tg.research_lab.errors import ResearchLabError
        if isinstance(e, ResearchLabError):
            return e.to_dict()
        raise


@router.post("/tg/research-lab/experiments/{experiment_id}/run")
def tg_rl_run(experiment_id: str, version: str = "v1", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().run_experiment(experiment_id, version)
    except PlatformContextError as e:
        raise _err(e) from e
    except Exception as e:
        from saathi.platform.tg.research_lab.errors import ResearchLabError
        if isinstance(e, ResearchLabError):
            return e.to_dict()
        raise


@router.post("/tg/research-lab/experiments/{experiment_id}/replay")
def tg_rl_replay(experiment_id: str, version: str = "v1", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().replay_experiment(experiment_id, version)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-lab/compare")
def tg_rl_compare(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().compare_strategies()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-lab/robustness")
def tg_rl_robustness(strategy_id: str = "tf_dual_ma", authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().analyse_robustness(strategy_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-lab/regimes/definitions")
def tg_rl_regime_defs(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().regime_definitions()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-lab/regimes/build")
def tg_rl_regime_build(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().build_regimes()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-lab/regimes/classify")
def tg_rl_regime_classify(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().classify_regimes()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-lab/portfolios/build")
def tg_rl_portfolio_build(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        from saathi.platform.tg.research_lab.comparison import _simulate_strategy_returns
        assets = ["tf_dual_ma", "mom_rs_equity", "mr_bollinger_reversion"]
        rets = {a: _simulate_strategy_returns(a, n=100, seed=i)["returns"] for i, a in enumerate(assets)}
        return _tg_research_lab().build_portfolio(assets, rets, method="equal_weight")
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-lab/ensembles/build")
def tg_rl_ensemble_build(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().build_ensemble(["tf_dual_ma", "mom_rs_equity", "mr_bollinger_reversion"])
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-lab/stress/run")
def tg_rl_stress(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        from saathi.platform.tg.research_lab.comparison import _simulate_strategy_returns
        assets = ["tf_dual_ma", "mom_rs_equity"]
        rets = {a: _simulate_strategy_returns(a, n=80, seed=i)["returns"] for i, a in enumerate(assets)}
        return _tg_research_lab().run_stress({a: 0.5 for a in assets}, rets)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-lab/candidates")
def tg_rl_candidates(state: str | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().list_candidates(state)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-lab/candidates/{candidate_id}")
def tg_rl_candidate_get(candidate_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().get_candidate(candidate_id)
    except PlatformContextError as e:
        raise _err(e) from e


class RlCandidateActionBody(BaseModel):
    reason: str = "operator_action"
    actor: str = "human_reviewer"


@router.post("/tg/research-lab/candidates/{candidate_id}/review")
def tg_rl_candidate_review(candidate_id: str, body: RlCandidateActionBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        actor = (body.actor if body else None) or "human_reviewer"
        return _tg_research_lab().request_candidate_review(candidate_id, actor=actor)
    except PlatformContextError as e:
        raise _err(e) from e
    except Exception as e:
        from saathi.platform.tg.research_lab.errors import ResearchLabError
        if isinstance(e, ResearchLabError):
            return e.to_dict()
        raise


@router.post("/tg/research-lab/candidates/{candidate_id}/reject")
def tg_rl_candidate_reject(candidate_id: str, body: RlCandidateActionBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        reason = (body.reason if body else None) or "rejected"
        return _tg_research_lab().reject_candidate(candidate_id, reason)
    except PlatformContextError as e:
        raise _err(e) from e
    except Exception as e:
        from saathi.platform.tg.research_lab.errors import ResearchLabError
        if isinstance(e, ResearchLabError):
            return e.to_dict()
        raise


@router.post("/tg/research-lab/candidates/{candidate_id}/revoke")
def tg_rl_candidate_revoke(candidate_id: str, body: RlCandidateActionBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        reason = (body.reason if body else None) or "revoked"
        return _tg_research_lab().revoke_candidate(candidate_id, reason)
    except PlatformContextError as e:
        raise _err(e) from e
    except Exception as e:
        from saathi.platform.tg.research_lab.errors import ResearchLabError
        if isinstance(e, ResearchLabError):
            return e.to_dict()
        raise


@router.post("/tg/research-lab/bootstrap")
def tg_rl_bootstrap(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().bootstrap_demo_pipeline()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-lab/certify")
def tg_rl_certify(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().certify()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-lab/certification")
def tg_rl_certification_get(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().terminal_verdict()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-lab/evidence")
def tg_rl_evidence(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().evidence_bundle()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-lab/security")
def tg_rl_security(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().security_scan()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-lab/broker/connect")
def tg_rl_broker_refuse(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().refuse_broker()
    except PlatformContextError as e:
        raise _err(e) from e


class RlCredBody(BaseModel):
    api_key: str | None = None
    secret: str | None = None


@router.post("/tg/research-lab/credentials")
def tg_rl_cred_refuse(body: RlCredBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        val = None
        if body:
            val = body.api_key or body.secret
        return _tg_research_lab().refuse_credentials(val)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-lab/orders")
def tg_rl_order_refuse(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().refuse_order()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-lab/canary/activate")
def tg_rl_canary_refuse(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().refuse_canary()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-lab/paper-execution/activate")
def tg_rl_paper_exec_refuse(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_lab().refuse_paper_execution()
    except PlatformContextError as e:
        raise _err(e) from e


# ── M280–M287 Autonomous Research Orchestrator (RESEARCH ONLY) ───────────────

def _tg_research_orchestrator():
    from saathi.platform.tg.research_orchestrator.service import default_research_orchestrator
    return default_research_orchestrator()


@router.get("/tg/research-orchestrator/posture")
def tg_ro_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().posture()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-orchestrator/verdict")
def tg_ro_verdict(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().terminal_verdict()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-orchestrator/dashboard")
def tg_ro_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().dashboard()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-orchestrator/jobs")
def tg_ro_jobs(state: str | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().list_jobs(state)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-orchestrator/jobs/{job_id}")
def tg_ro_job_get(job_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().get_job(job_id)
    except PlatformContextError as e:
        raise _err(e) from e


class RoEnqueueBody(BaseModel):
    name: str = "api_job"
    kind: str = "noop"
    seed: int = 42
    priority: str = "NORMAL"
    template_id: str | None = None
    strategy_ids: list[str] | None = None
    depends_on: list[str] | None = None


@router.post("/tg/research-orchestrator/jobs")
def tg_ro_enqueue(body: RoEnqueueBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        config: dict = {"kind": body.kind, "seed": body.seed}
        if body.strategy_ids:
            config["strategy_ids"] = body.strategy_ids
        return _tg_research_orchestrator().enqueue_job(
            body.name, config, priority=body.priority,
            template_id=body.template_id, depends_on=body.depends_on,
        )
    except PlatformContextError as e:
        raise _err(e) from e
    except Exception as e:
        from saathi.platform.tg.research_orchestrator.errors import OrchestratorError
        if isinstance(e, OrchestratorError):
            return e.to_dict()
        raise


@router.post("/tg/research-orchestrator/tick")
def tg_ro_tick(max_jobs: int = 1, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().tick(max_jobs=max_jobs)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-orchestrator/jobs/{job_id}/cancel")
def tg_ro_cancel(job_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().cancel_job(job_id)
    except PlatformContextError as e:
        raise _err(e) from e
    except Exception as e:
        from saathi.platform.tg.research_orchestrator.errors import OrchestratorError
        if isinstance(e, OrchestratorError):
            return e.to_dict()
        raise


@router.post("/tg/research-orchestrator/jobs/{job_id}/resume")
def tg_ro_resume(job_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().resume_job(job_id)
    except PlatformContextError as e:
        raise _err(e) from e
    except Exception as e:
        from saathi.platform.tg.research_orchestrator.errors import OrchestratorError
        if isinstance(e, OrchestratorError):
            return e.to_dict()
        raise


@router.post("/tg/research-orchestrator/jobs/{job_id}/replay")
def tg_ro_replay(job_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().replay_job(job_id)
    except PlatformContextError as e:
        raise _err(e) from e
    except Exception as e:
        from saathi.platform.tg.research_orchestrator.errors import OrchestratorError
        if isinstance(e, OrchestratorError):
            return e.to_dict()
        raise


@router.get("/tg/research-orchestrator/workers")
def tg_ro_workers(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().workers_status()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-orchestrator/budget")
def tg_ro_budget(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().budget_status()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-orchestrator/templates")
def tg_ro_templates(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().list_templates()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-orchestrator/strategies")
def tg_ro_strategies(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().list_strategies_v2()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-orchestrator/notebook")
def tg_ro_notebook(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().notebook()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-orchestrator/hypotheses")
def tg_ro_hypotheses(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().list_hypotheses()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-orchestrator/failures")
def tg_ro_failures(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().failure_analysis()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-orchestrator/calendar")
def tg_ro_calendar(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().research_calendar()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-orchestrator/dependencies")
def tg_ro_deps(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().dependency_graph()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-orchestrator/bootstrap")
def tg_ro_bootstrap(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().bootstrap_demo_pipeline()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-orchestrator/certify")
def tg_ro_certify(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().certify()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-orchestrator/evidence")
def tg_ro_evidence(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().evidence_bundle()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/research-orchestrator/security")
def tg_ro_security(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().security_scan()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-orchestrator/broker/connect")
def tg_ro_broker_refuse(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().refuse_broker()
    except PlatformContextError as e:
        raise _err(e) from e


class RoCredBody(BaseModel):
    api_key: str | None = None


@router.post("/tg/research-orchestrator/credentials")
def tg_ro_cred_refuse(body: RoCredBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().refuse_credentials(body.api_key if body else None)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-orchestrator/orders")
def tg_ro_order_refuse(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().refuse_order()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-orchestrator/canary/activate")
def tg_ro_canary_refuse(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().refuse_canary()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/research-orchestrator/paper-execution/activate")
def tg_ro_paper_exec_refuse(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_research_orchestrator().refuse_paper_execution()
    except PlatformContextError as e:
        raise _err(e) from e


# ── M288–M295 Institutional Paper Trading Simulation ─────────────────────────

def _tg_paper_sim():
    from saathi.platform.tg.paper_simulation.service import default_paper_simulation
    return default_paper_simulation()


@router.get("/tg/paper-simulation/posture")
def tg_ps_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().posture()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper-simulation/verdict")
def tg_ps_verdict(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().terminal_verdict()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper-simulation/dashboard")
def tg_ps_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().dashboard()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper-simulation/exchange")
def tg_ps_exchange(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().exchange_status()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper-simulation/order-book/{symbol}")
def tg_ps_book(symbol: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().order_book(symbol)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper-simulation/portfolios")
def tg_ps_portfolios(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().list_portfolios()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper-simulation/portfolios/{portfolio_id}")
def tg_ps_portfolio(portfolio_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().get_portfolio(portfolio_id)
    except PlatformContextError as e:
        raise _err(e) from e


class PsPortfolioBody(BaseModel):
    name: str = "Paper Portfolio"
    initial_cash: float = 100000.0


@router.post("/tg/paper-simulation/portfolios")
def tg_ps_create_pf(body: PsPortfolioBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().create_portfolio(body.name, initial_cash=body.initial_cash)
    except PlatformContextError as e:
        raise _err(e) from e


class PsOrderBody(BaseModel):
    portfolio_id: str
    symbol: str = "SPY"
    side: str = "BUY"
    order_type: str = "MARKET"
    quantity: float = 1.0
    limit_price: float | None = None
    stop_price: float | None = None
    tif: str = "DAY"


@router.post("/tg/paper-simulation/orders")
def tg_ps_order(body: PsOrderBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().submit_order(
            body.portfolio_id, body.symbol, body.side, body.order_type, body.quantity,
            limit_price=body.limit_price, stop_price=body.stop_price, tif=body.tif,
        )
    except PlatformContextError as e:
        raise _err(e) from e
    except Exception as e:
        from saathi.platform.tg.paper_simulation.errors import PaperSimError
        if isinstance(e, PaperSimError):
            return e.to_dict()
        raise


@router.get("/tg/paper-simulation/portfolios/{portfolio_id}/orders")
def tg_ps_orders(portfolio_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().list_orders(portfolio_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper-simulation/portfolios/{portfolio_id}/fills")
def tg_ps_fills(portfolio_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().list_fills(portfolio_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper-simulation/portfolios/{portfolio_id}/cash")
def tg_ps_cash(portfolio_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().cash_ledger(portfolio_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper-simulation/kill-switch")
def tg_ps_ks(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().kill_switch_status()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper-simulation/calendar")
def tg_ps_cal(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().trading_calendar()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper-simulation/bootstrap")
def tg_ps_bootstrap(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().bootstrap_demo_pipeline()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper-simulation/certify")
def tg_ps_certify(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().certify()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper-simulation/evidence")
def tg_ps_evidence(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().evidence_bundle()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/paper-simulation/security")
def tg_ps_security(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().security_scan()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper-simulation/broker/connect")
def tg_ps_broker(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().refuse_broker()
    except PlatformContextError as e:
        raise _err(e) from e


class PsCredBody(BaseModel):
    api_key: str | None = None


@router.post("/tg/paper-simulation/credentials")
def tg_ps_cred(body: PsCredBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().refuse_credentials(body.api_key if body else None)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper-simulation/real-orders")
def tg_ps_real_orders(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().refuse_real_order()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper-simulation/canary/activate")
def tg_ps_canary(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().refuse_canary()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/paper-simulation/live/activate")
def tg_ps_live(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_paper_sim().refuse_live()
    except PlatformContextError as e:
        raise _err(e) from e


# ── M296–M303 Institutional Portfolio & Risk Intelligence ────────────────────

def _tg_portfolio_risk():
    from saathi.platform.tg.portfolio_risk.service import default_portfolio_risk
    return default_portfolio_risk()


@router.get("/tg/portfolio-risk/posture")
def tg_pr_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().posture()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/portfolio-risk/verdict")
def tg_pr_verdict(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().terminal_verdict()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/portfolio-risk/dashboard")
def tg_pr_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().dashboard()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/portfolio-risk/analytics")
def tg_pr_analytics(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().analyze()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/portfolio-risk/limits")
def tg_pr_limits(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().evaluate_limits()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/portfolio-risk/attribution")
def tg_pr_attr(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().performance_attribution()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/portfolio-risk/optimise")
def tg_pr_opt(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().optimise()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/portfolio-risk/scenarios")
def tg_pr_scn(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().run_scenarios()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/portfolio-risk/sizing")
def tg_pr_size(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().size_positions()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/portfolio-risk/committee")
def tg_pr_cm(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().committee_review()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/portfolio-risk/bootstrap")
def tg_pr_boot(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().bootstrap_demo_pipeline()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/portfolio-risk/certify")
def tg_pr_cert(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().certify()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/portfolio-risk/evidence")
def tg_pr_ev(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().evidence_bundle()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/portfolio-risk/security")
def tg_pr_sec(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().security_scan()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/portfolio-risk/broker/connect")
def tg_pr_broker(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().refuse_broker()
    except PlatformContextError as e:
        raise _err(e) from e


class PrCredBody(BaseModel):
    api_key: str | None = None


@router.post("/tg/portfolio-risk/credentials")
def tg_pr_cred(body: PrCredBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().refuse_credentials(body.api_key if body else None)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/portfolio-risk/orders")
def tg_pr_orders(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().refuse_order()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/portfolio-risk/canary/activate")
def tg_pr_canary(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().refuse_canary()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/portfolio-risk/live/activate")
def tg_pr_live(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_portfolio_risk().refuse_live()
    except PlatformContextError as e:
        raise _err(e) from e


# ── M304–M311 Read-Only Market Observation ───────────────────────────────────

def _tg_market_observation():
    from saathi.platform.tg.market_observation.service import default_market_observation
    return default_market_observation()


@router.get("/tg/market-observation/posture")
def tg_mo_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().posture()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/market-observation/verdict")
def tg_mo_verdict(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().terminal_verdict()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/market-observation/dashboard")
def tg_mo_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().dashboard()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/market-observation/symbols")
def tg_mo_symbols(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().list_symbols()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/market-observation/symbols/{symbol}")
def tg_mo_symbol(symbol: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().get_symbol(symbol)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/market-observation/quotes")
def tg_mo_quotes(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().list_quotes()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/market-observation/quotes/{symbol}")
def tg_mo_quote(symbol: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().get_quote(symbol)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/market-observation/snapshots")
def tg_mo_snap(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().market_snapshot()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/market-observation/history/{symbol}/refresh")
def tg_mo_hist(symbol: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().historical_refresh(symbol)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/market-observation/history/{symbol}")
def tg_mo_hist_get(symbol: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().get_history(symbol)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/market-observation/exchanges")
def tg_mo_ex(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().list_exchange_status()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/market-observation/corporate-actions")
def tg_mo_ca(symbol: str | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().list_corporate_actions(symbol)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/market-observation/benchmarks/update")
def tg_mo_bm(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().update_benchmarks()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/market-observation/benchmarks")
def tg_mo_bm_list(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().list_benchmarks()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/market-observation/bootstrap")
def tg_mo_boot(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().bootstrap_demo_pipeline()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/market-observation/certify")
def tg_mo_cert(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().certify()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/market-observation/evidence")
def tg_mo_ev(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().evidence_bundle()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/market-observation/security")
def tg_mo_sec(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().security_scan()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/market-observation/broker/login")
def tg_mo_broker_login(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().refuse_broker_login()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/market-observation/oauth")
def tg_mo_oauth(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().refuse_oauth()
    except PlatformContextError as e:
        raise _err(e) from e


class MoCredBody(BaseModel):
    api_key: str | None = None


@router.post("/tg/market-observation/credentials")
def tg_mo_cred(body: MoCredBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().refuse_credentials(body.api_key if body else None)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/market-observation/orders")
def tg_mo_orders(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().refuse_order()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/market-observation/accounts")
def tg_mo_accounts(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().refuse_account_access()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/market-observation/portfolios")
def tg_mo_portfolios(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().refuse_portfolio_access()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/market-observation/balances")
def tg_mo_balances(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().refuse_balance_access()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/market-observation/canary/activate")
def tg_mo_canary(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().refuse_canary()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/market-observation/live/activate")
def tg_mo_live(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().refuse_live_trading()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/market-observation/live-feed")
def tg_mo_live_feed(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_market_observation().refuse_authenticated_live_feed()
    except PlatformContextError as e:
        raise _err(e) from e


# ---------------------------------------------------------------------------
# M312–M319 Connectivity Governance (governance only — no provider connection)
# ---------------------------------------------------------------------------

def _tg_connectivity_governance():
    from saathi.platform.tg.connectivity_governance.service import default_connectivity_governance
    return default_connectivity_governance()


@router.get("/tg/connectivity-governance/posture")
def tg_cg_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().posture()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/verdict")
def tg_cg_verdict(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().terminal_verdict()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/dashboard")
def tg_cg_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().dashboard()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/charter")
def tg_cg_charter(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().charter()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/authorities")
def tg_cg_authorities(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().authority_list()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/authorities/{capability}")
def tg_cg_authority_detail(capability: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().authority_evaluate(capability)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/providers")
def tg_cg_providers(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().list_providers()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/providers/{provider_id}")
def tg_cg_provider_detail(provider_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().get_provider(provider_id)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/capability-policy")
def tg_cg_capability_policy(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().capability_policy()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/approvals")
def tg_cg_approvals(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().list_approvals()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/approvals/{approval_id}")
def tg_cg_approval_detail(approval_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().get_approval(approval_id)
    except PlatformContextError as e:
        raise _err(e) from e


class CgApprovalBody(BaseModel):
    requestor: str = "api_requestor"
    approval_type: str = "provider_documentation_review"
    provider: str = "prov_mock_contract"
    environment: str = "governance"
    capability_scope: list[str] = ["offline_fixture_access"]
    operation_scope: list[str] = ["documentation_review"]
    jurisdiction: str = "N/A"
    expiry_seconds: float = 86400.0
    allowed_network_destinations: list[str] = ["localhost"]
    evidence_requirements: list[str] = ["docs"]
    revocation_conditions: list[str] = ["operator_request"]
    acknowledgements: list[str] = ["governance_only", "no_activation"]


@router.post("/tg/connectivity-governance/approvals")
def tg_cg_approval_create(body: CgApprovalBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        import time as _time
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        b = body or CgApprovalBody()
        return _tg_connectivity_governance().create_approval(
            requestor=b.requestor,
            approval_type=b.approval_type,
            provider=b.provider,
            environment=b.environment,
            capability_scope=b.capability_scope,
            operation_scope=b.operation_scope,
            jurisdiction=b.jurisdiction,
            expiry_time=_time.time() + b.expiry_seconds,
            allowed_network_destinations=b.allowed_network_destinations,
            evidence_requirements=b.evidence_requirements,
            revocation_conditions=b.revocation_conditions,
            acknowledgements=b.acknowledgements,
        )
    except Exception as e:
        from saathi.platform.tg.connectivity_governance.errors import ConnectivityGovernanceError
        if isinstance(e, ConnectivityGovernanceError):
            return e.to_dict()
        if isinstance(e, PlatformContextError):
            raise _err(e) from e
        raise


class CgReviewBody(BaseModel):
    approver: str = "api_approver"
    decision: str = "approve"
    notes: str = ""


@router.post("/tg/connectivity-governance/approvals/{approval_id}/submit")
def tg_cg_approval_submit(approval_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        appr = _tg_connectivity_governance().get_approval(approval_id)
        actor = (appr.get("approval") or {}).get("requestor") or "api_requestor"
        return _tg_connectivity_governance().submit_approval(approval_id, actor=actor)
    except Exception as e:
        from saathi.platform.tg.connectivity_governance.errors import ConnectivityGovernanceError
        if isinstance(e, ConnectivityGovernanceError):
            return e.to_dict()
        if isinstance(e, PlatformContextError):
            raise _err(e) from e
        raise


@router.post("/tg/connectivity-governance/approvals/{approval_id}/review")
def tg_cg_approval_review(approval_id: str, body: CgReviewBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        b = body or CgReviewBody()
        return _tg_connectivity_governance().review_approval(approval_id, approver=b.approver, decision=b.decision, notes=b.notes)
    except Exception as e:
        from saathi.platform.tg.connectivity_governance.errors import ConnectivityGovernanceError
        if isinstance(e, ConnectivityGovernanceError):
            return e.to_dict()
        if isinstance(e, PlatformContextError):
            raise _err(e) from e
        raise


@router.post("/tg/connectivity-governance/approvals/{approval_id}/revoke")
def tg_cg_approval_revoke(approval_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().revoke_approval(approval_id, actor="api_operator", reason="operator_request")
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/credential-policy")
def tg_cg_credential_policy(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().credential_policy()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/revocations")
def tg_cg_revocations(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().list_revocations()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/incidents")
def tg_cg_incidents(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().list_incidents()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/incidents/{incident_id}")
def tg_cg_incident_detail(incident_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().get_incident(incident_id)
    except PlatformContextError as e:
        raise _err(e) from e


class CgEmergencyBody(BaseModel):
    actor: str = "api_operator"
    reason: str = "governance_drill"


@router.get("/tg/connectivity-governance/emergency-shutdown")
def tg_cg_emergency_status(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().emergency_status()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/connectivity-governance/emergency-shutdown")
def tg_cg_emergency_activate(body: CgEmergencyBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        b = body or CgEmergencyBody()
        return _tg_connectivity_governance().emergency_shutdown(actor=b.actor, reason=b.reason)
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/threat-model")
def tg_cg_threats(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().list_threats()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/risk-summary")
def tg_cg_risk_summary(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().risk_summary()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/maturity")
def tg_cg_maturity(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().maturity()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/connectivity-governance/bootstrap")
def tg_cg_bootstrap(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().bootstrap_demo_pipeline()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/connectivity-governance/certify")
def tg_cg_certify(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().certify()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/evidence")
def tg_cg_evidence(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().evidence_bundle()
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/tg/connectivity-governance/security")
def tg_cg_security(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().security_scan()
    except PlatformContextError as e:
        raise _err(e) from e


# Hard refusal endpoints — no secrets accepted, no connectivity
@router.post("/tg/connectivity-governance/broker/login")
def tg_cg_broker_login(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().refuse_broker_login()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/connectivity-governance/oauth")
def tg_cg_oauth(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().refuse_oauth()
    except PlatformContextError as e:
        raise _err(e) from e


class CgCredBody(BaseModel):
    # Deliberately does not accept raw secret fields as validated credentials
    note: str = "credentials_refused"


@router.post("/tg/connectivity-governance/credentials")
def tg_cg_credentials(body: CgCredBody | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().refuse_credentials(None)
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/connectivity-governance/connect")
def tg_cg_connect(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().refuse_provider_connect()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/connectivity-governance/orders")
def tg_cg_orders(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().refuse_order()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/connectivity-governance/accounts")
def tg_cg_accounts(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().refuse_account_access()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/connectivity-governance/balances")
def tg_cg_balances(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().refuse_balance_access()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/connectivity-governance/positions")
def tg_cg_positions(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().refuse_position_access()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/connectivity-governance/canary/activate")
def tg_cg_canary(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().refuse_canary()
    except PlatformContextError as e:
        raise _err(e) from e


@router.post("/tg/connectivity-governance/live/activate")
def tg_cg_live(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_connectivity_governance().refuse_live_trading()
    except PlatformContextError as e:
        raise _err(e) from e


# ---------------------------------------------------------------------------
# M320–M327 Credentialless Provider Contracts (mock/replay only)
# ---------------------------------------------------------------------------

def _tg_provider_contracts():
    from saathi.platform.tg.provider_contracts.service import default_provider_contracts
    return default_provider_contracts()


def _tg_pc_authorized(
    authorization: str | None,
    x_platform_token: str | None,
):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_provider_contracts()
    except PlatformContextError as e:
        raise _err(e) from e


class ProviderCapabilityBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: str = "saathi.mock.market.v1"
    capabilities: list[str] = Field(default_factory=lambda: [
        "quotes",
        "candles",
        "trades",
        "orderbook",
        "symbols",
        "market_status",
    ])


class ProviderOfflineRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: str = "saathi.mock.market.v1"
    operation: str = "quotes.get"
    params: dict[str, Any] = Field(default_factory=lambda: {"symbol": "AAPL"})
    idempotency_key: str = "ui:mock:quote:AAPL:v1"
    schema_version: str = "m320.provider_contracts.v1"


@router.get("/tg/provider-contracts/posture")
def tg_pc_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_pc_authorized(authorization, x_platform_token).posture()


@router.get("/tg/provider-contracts/charter")
def tg_pc_charter(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_pc_authorized(authorization, x_platform_token).charter()


@router.get("/tg/provider-contracts/dashboard")
def tg_pc_dashboard(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_pc_authorized(authorization, x_platform_token).dashboard()


@router.get("/tg/provider-contracts/providers")
def tg_pc_providers(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_pc_authorized(authorization, x_platform_token).list_providers()


@router.get("/tg/provider-contracts/providers/{provider_id}")
def tg_pc_provider_detail(provider_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    service = _tg_pc_authorized(authorization, x_platform_token)
    try:
        return service.get_provider(provider_id)
    except Exception as exc:
        from saathi.platform.tg.provider_contracts.errors import normalize_error
        return {"ok": False, "error": normalize_error(exc).to_dict()}


@router.get("/tg/provider-contracts/capabilities")
def tg_pc_capabilities(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_pc_authorized(authorization, x_platform_token).capabilities()


@router.post("/tg/provider-contracts/capabilities/negotiate")
def tg_pc_capability_negotiate(body: ProviderCapabilityBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    service = _tg_pc_authorized(authorization, x_platform_token)
    try:
        return service.negotiate(body.provider_id, body.capabilities)
    except Exception as exc:
        from saathi.platform.tg.provider_contracts.errors import normalize_error
        return {"ok": False, "error": normalize_error(exc).to_dict()}


@router.get("/tg/provider-contracts/sessions")
def tg_pc_sessions(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_pc_authorized(authorization, x_platform_token).sessions()


@router.get("/tg/provider-contracts/replay/fixtures")
def tg_pc_replay_fixtures(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_pc_authorized(authorization, x_platform_token).replay_fixtures()


@router.post("/tg/provider-contracts/requests")
def tg_pc_request(body: ProviderOfflineRequestBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    service = _tg_pc_authorized(authorization, x_platform_token)
    return service.request(body.model_dump())


@router.get("/tg/provider-contracts/security")
def tg_pc_security(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_pc_authorized(authorization, x_platform_token).security_scan()


@router.get("/tg/provider-contracts/maturity")
def tg_pc_maturity(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_pc_authorized(authorization, x_platform_token).maturity()


@router.get("/tg/provider-contracts/evidence")
def tg_pc_evidence(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_pc_authorized(authorization, x_platform_token).evidence_bundle()


@router.post("/tg/provider-contracts/certify")
def tg_pc_certify(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_pc_authorized(authorization, x_platform_token).certify()


# ---------------------------------------------------------------------------
# M328–M335 Production Readiness, Observability & Operational Resilience
# Read-only offline operations surface. No execution or deployment control.
# ---------------------------------------------------------------------------

def _tg_operations():
    from saathi.platform.tg.production_readiness.service import default_operations
    return default_operations()


def _tg_ops_authorized(
    authorization: str | None,
    x_platform_token: str | None,
):
    try:
        from saathi.platform.models import PlatformPermission
        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return _tg_operations()
    except PlatformContextError as e:
        raise _err(e) from e


def _tg_ops_guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        from saathi.platform.tg.production_readiness.errors import error_envelope
        return error_envelope(exc)


class OperationsAlertActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = "operator"


class OperationsRecoveryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_id: str | None = None


@router.get("/tg/operations/posture")
def tg_ops_posture(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).posture()


@router.get("/tg/operations/charter")
def tg_ops_charter(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).charter()


@router.get("/tg/operations/control-center")
def tg_ops_control_center(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).control_center()


@router.get("/tg/operations/health")
def tg_ops_health(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).health.snapshot()


@router.get("/tg/operations/health/{component_id}")
def tg_ops_health_component(component_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    service = _tg_ops_authorized(authorization, x_platform_token)
    return _tg_ops_guard(service.health.component, component_id)


@router.get("/tg/operations/observability")
def tg_ops_observability(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).observability.posture()


@router.get("/tg/operations/observability/logs")
def tg_ops_logs(limit: int = 200, level: str | None = None, component: str | None = None, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    service = _tg_ops_authorized(authorization, x_platform_token)
    return _tg_ops_guard(service.observability.records, limit=limit, level=level, component=component)


@router.get("/tg/operations/observability/traces/{trace_id}")
def tg_ops_trace(trace_id: str, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    service = _tg_ops_authorized(authorization, x_platform_token)
    return _tg_ops_guard(service.observability.trace, trace_id)


@router.get("/tg/operations/observability/timelines")
def tg_ops_timelines(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).observability.timelines()


@router.get("/tg/operations/observability/execution-history")
def tg_ops_execution_history(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).observability.execution_history()


@router.get("/tg/operations/observability/audit-visualization")
def tg_ops_audit_visualization(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    service = _tg_ops_authorized(authorization, x_platform_token)
    return service.observability.audit_visualization(service.governance.store.list_audit(100))


@router.get("/tg/operations/metrics")
def tg_ops_metrics(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).metrics.summary()


@router.get("/tg/operations/alerts")
def tg_ops_alerts(severity: str | None = None, state: str | None = None, limit: int = 100, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    service = _tg_ops_authorized(authorization, x_platform_token)
    return _tg_ops_guard(service.alerts.list_alerts, severity=severity, state=state, limit=limit)


@router.get("/tg/operations/alerts/policy")
def tg_ops_alert_policy(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).alerts.destination_policy()


@router.post("/tg/operations/alerts/{alert_id}/acknowledge")
def tg_ops_alert_acknowledge(alert_id: str, body: OperationsAlertActionBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    service = _tg_ops_authorized(authorization, x_platform_token)
    return _tg_ops_guard(service.alerts.acknowledge, alert_id, body.actor)


@router.post("/tg/operations/alerts/{alert_id}/resolve")
def tg_ops_alert_resolve(alert_id: str, body: OperationsAlertActionBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    service = _tg_ops_authorized(authorization, x_platform_token)
    return _tg_ops_guard(service.alerts.resolve, alert_id, body.actor)


@router.get("/tg/operations/backups")
def tg_ops_backups(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).backups.list_snapshots()


@router.post("/tg/operations/backups/verify")
def tg_ops_backup_verify(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).verify_backups()


@router.post("/tg/operations/backups/simulate-recovery")
def tg_ops_simulate_recovery(body: OperationsRecoveryBody, authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    service = _tg_ops_authorized(authorization, x_platform_token)
    return _tg_ops_guard(service.simulate_recovery, body.snapshot_id)


@router.get("/tg/operations/backups/recovery-history")
def tg_ops_recovery_history(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).backups.recovery_history()


@router.post("/tg/operations/diagnostics")
def tg_ops_diagnostics(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).run_diagnostics()


@router.post("/tg/operations/load-validation")
def tg_ops_load_validation(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).run_load_validation()


@router.get("/tg/operations/authority")
def tg_ops_authority(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).authority_summary()


@router.get("/tg/operations/certification-history")
def tg_ops_certification_history(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).certification_history()


@router.get("/tg/operations/security")
def tg_ops_security(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).security_scan()


@router.get("/tg/operations/maturity")
def tg_ops_maturity(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).maturity()


@router.get("/tg/operations/evidence")
def tg_ops_evidence(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).evidence_bundle()


@router.post("/tg/operations/certify")
def tg_ops_certify(authorization: str | None = Header(default=None), x_platform_token: str | None = Header(default=None, alias="X-Platform-Token")):
    return _tg_ops_authorized(authorization, x_platform_token).certify()


# ---------------------------------------------------------------------------
# M336–M343 Private Alpha Launch Readiness
# Read-only. No route here launches, deploys, publishes, invites, connects a
# provider, executes an order, or records owner review. Owner review is a human
# act performed outside this tooling and is never satisfied by an API call.
# ---------------------------------------------------------------------------

def _private_alpha_readiness_authorized(
    authorization: str | None,
    x_platform_token: str | None,
):
    try:
        from saathi.platform.models import PlatformPermission

        ctx = _tg_ctx(authorization, x_platform_token)
        ctx.require_permission(PlatformPermission.PAPER_SAFETY_READ)
        return ctx
    except PlatformContextError as e:
        raise _err(e) from e


@router.get("/private-alpha/readiness")
def private_alpha_readiness(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    _private_alpha_readiness_authorized(authorization, x_platform_token)
    from saathi.platform.private_alpha.launch_readiness import launch_readiness_report

    return launch_readiness_report()


@router.get("/private-alpha/checklist")
def private_alpha_checklist(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    _private_alpha_readiness_authorized(authorization, x_platform_token)
    from saathi.platform.private_alpha.launch_readiness import build_checklist

    return {"checklist": build_checklist()}


@router.get("/private-alpha/contract")
def private_alpha_contract(
    authorization: str | None = Header(default=None),
    x_platform_token: str | None = Header(default=None, alias="X-Platform-Token"),
):
    _private_alpha_readiness_authorized(authorization, x_platform_token)
    from saathi.platform.private_alpha.launch_readiness import (
        AUTHORITY_LOCKS,
        KNOWN_LIMITATIONS,
        MAX_STATE,
        authority_posture,
    )

    return {
        "private_alpha": True,
        "invite_only": True,
        "public_registration_authorized": False,
        "max_state": MAX_STATE,
        "known_limitations": KNOWN_LIMITATIONS,
        "authority_locks": authority_posture()["locks"],
        "authority_lock_names": list(AUTHORITY_LOCKS),
    }
