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
