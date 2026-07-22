"""M13 AI Studio API — /api/v1/studio-os/* (auth inherited from /api/v1).

Distinct prefix from the legacy /api/v1/studio dashboard routes. All mutations
are ownership-checked; publishing enforces approval.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from saathi.studio_os.store import default_store
from saathi.studio_os.service import StudioService, WORKFLOWS
from saathi.studio_os.models import ProjectState, ProjectSpec
from saathi.studio_os import storage as S
from saathi.studio_os import providers as P
from saathi.studio_os import publishing as PUB

router = APIRouter(prefix="/api/v1/studio-os", tags=["studio"])


def _user(request: Request) -> str:
    return getattr(request.state, "user_id", None) or "ajay"


class CreateProject(BaseModel):
    title: str = ""
    objective: str = ""
    content_type: str = "short_video"
    platforms: list[str] = ["youtube"]
    duration_target_sec: int = 60
    budget_usd: float = 5.0
    workflow: str = ""
    conversation_id: str = ""


class PublishReq(BaseModel):
    platform: str
    approved: bool = False
    live: bool = False


@router.get("/workflows")
def workflows():
    return {"workflows": {k: v for k, v in WORKFLOWS.items()}}


@router.get("/providers")
def providers_matrix():
    return P.capability_matrix()


@router.get("/storage/health")
def storage_health():
    return S.storage_health()


@router.post("/projects")
def create_project(req: CreateProject, request: Request):
    spec = ProjectSpec(title=req.title, objective=req.objective,
                       content_type=req.content_type, platforms=req.platforms,
                       duration_target_sec=req.duration_target_sec,
                       budget_usd=req.budget_usd, workflow=req.workflow)
    pid = StudioService(default_store()).create_project(
        _user(request), spec, conversation_id=req.conversation_id)
    return {"project_id": pid}


@router.get("/projects")
def list_projects(request: Request, limit: int = 50):
    return {"projects": default_store().list_projects(owner=_user(request), limit=limit)}


@router.get("/projects/{pid}")
def get_project(pid: str, request: Request):
    st = default_store()
    p = st.get_project(pid)
    if not p or p["owner"] != _user(request):
        return {"error": "not found"}
    return {"project": p, "stages": st.list_stages(pid),
            "artifacts": st.list_artifacts(pid), "cost": st.cost_summary(pid),
            "receipts": st.receipts(pid)}


@router.post("/projects/{pid}/run")
def run_project(pid: str, request: Request):
    st = default_store()
    if not st.owns(pid, _user(request)):
        return {"error": "not found"}
    try:
        out = StudioService(st).run(pid, owner=_user(request))
        return {"project_id": pid, "state": out.state, "stages_done": out.stages_done,
                "stages_failed": out.stages_failed, "artifacts": out.artifacts,
                "note": out.note}
    except (PermissionError, RuntimeError) as exc:
        return {"error": str(exc)}


@router.get("/projects/{pid}/artifacts")
def artifacts(pid: str, request: Request):
    st = default_store()
    if not st.owns(pid, _user(request)):
        return {"error": "not found"}
    return {"artifacts": st.list_artifacts(pid, latest_only=False)}


@router.post("/artifacts/{aid}/approve")
def approve_artifact(aid: str, request: Request, approved: bool = True):
    st = default_store()
    art = st.get_artifact(aid)
    if not art or not st.owns(art["project_id"], _user(request)):
        return {"error": "not found"}
    st.set_artifact_approval(aid, "approved" if approved else "rejected")
    return {"artifact_id": aid, "approval": "approved" if approved else "rejected"}


@router.post("/projects/{pid}/publish")
def publish(pid: str, req: PublishReq, request: Request):
    st = default_store()
    if not st.owns(pid, _user(request)):
        return {"error": "not found"}
    try:
        r = PUB.publish(st, pid, platform=req.platform, owner=_user(request),
                        approved=req.approved, live=req.live)
        return {"ok": r.ok, "status": r.status, "platform": r.platform,
                "receipt_id": r.receipt_id, "url": r.url, "detail": r.detail}
    except (PUB.NotApproved, PUB.NoPublishableArtifact, PermissionError) as exc:
        return {"error": str(exc)}


@router.get("/projects/{pid}/cost")
def cost(pid: str, request: Request):
    st = default_store()
    if not st.owns(pid, _user(request)):
        return {"error": "not found"}
    return st.cost_summary(pid)


@router.post("/projects/{pid}/cancel")
def cancel(pid: str, request: Request):
    st = default_store()
    if not st.owns(pid, _user(request)):
        return {"error": "not found"}
    try:
        st.transition(pid, ProjectState.CANCELLED, actor=f"user:{_user(request)}")
        return {"project_id": pid, "cancelled": True}
    except Exception as exc:
        return {"error": str(exc)}
