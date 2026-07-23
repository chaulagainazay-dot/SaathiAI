"""M10 Agent Runtime API — /api/v1/agents/* (auth inherited from /api/v1).

Approvals are user actions: the global middleware requires an authenticated
user, so an agent process cannot resolve its own approval through this API.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from saathi.agent_runtime import registry
from saathi.agent_runtime.errors import AgentRunError
from saathi.agent_runtime.orchestrator import default_orchestrator
from saathi.agent_runtime.service import start_agent_run

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


class CreateRun(BaseModel):
    objective: str
    strategy: str = ""
    project_id: str = ""
    conversation_id: str = ""
    budget: dict = {}
    # M48.2 optional contract fields (fail-closed when elevated)
    authority_class: str = "READ_ONLY"
    requested_capability: str = ""
    approval_token: str | None = None
    idempotency_key: str = ""


class Approve(BaseModel):
    approval_id: str
    approved: bool


@router.get("/definitions")
def definitions():
    return {"agents": [a.to_dict() for a in registry.all_agents()]}


@router.get("/definitions/{agent_id}")
def definition(agent_id: str):
    a = registry.get(agent_id)
    return a.to_dict() if a else {"error": "not found"}


@router.post("/runs")
def create_run(req: CreateRun):
    """Canonical path: validate via start_agent_run before persistence."""
    orch = default_orchestrator()
    rec = start_agent_run(
        objective=req.objective,
        strategy=req.strategy,
        project_id=req.project_id,
        conversation_id=req.conversation_id,
        budget=req.budget or None,
        authority_class=req.authority_class or "READ_ONLY",
        requested_capability=req.requested_capability or "",
        approval_token=req.approval_token,
        idempotency_key=req.idempotency_key or "",
        execute=False,
        orchestrator=orch,
    )
    if not rec.ok:
        return {
            "error": rec.error_code,
            "message": rec.message,
            "violations": rec.violations,
            "ok": False,
        }
    return {"run_id": rec.run_id, "ok": True, "state": rec.state}


@router.post("/runs/{rid}/execute")
def execute(rid: str, max_wall_sec: float = 60.0):
    return default_orchestrator().run(rid, max_wall_sec=max_wall_sec)


@router.get("/runs")
def list_runs(limit: int = 50, conversation_id: str | None = None):
    return {"runs": default_orchestrator().store.list_runs(
        limit=limit, conversation_id=conversation_id)}


@router.get("/runs/{rid}")
def get_run(rid: str):
    st = default_orchestrator().store
    run = st.get_run(rid)
    if not run:
        return {"error": "not found"}
    return {"run": run, "tasks": st.list_tasks(rid),
            "delegations": st.delegations(rid),
            "pending_approvals": st.pending_approvals(rid),
            "metrics": st.metrics(rid), "outcome": run.get("final_outcome")}


@router.get("/runs/{rid}/tasks")
def tasks(rid: str):
    return {"tasks": default_orchestrator().store.list_tasks(rid)}


@router.get("/runs/{rid}/events")
def events(rid: str, limit: int = 200, offset: int = 0):
    return {"events": default_orchestrator().store.events(rid, limit=limit, offset=offset)}


@router.get("/runs/{rid}/tool-intents")
def tool_intents(rid: str):
    return {"tool_requests": default_orchestrator().store.tool_requests(rid)}


@router.get("/runs/{rid}/verifications")
def verifications(rid: str):
    return {"verifications": default_orchestrator().store.verifications(rid)}


@router.get("/runs/{rid}/messages")
def messages(rid: str):
    return {"messages": default_orchestrator().store.messages(rid)}


@router.get("/runs/{rid}/artifacts")
def artifacts(rid: str):
    return {"artifacts": [{k: v for k, v in a.items() if k != "content"}
                          for a in default_orchestrator().store.artifacts(rid)]}


@router.get("/artifacts/{aid}")
def artifact(aid: str):
    st = default_orchestrator().store
    with st._conn() as c:
        row = c.execute("SELECT * FROM artifact WHERE id=?", (aid,)).fetchone()
    return dict(row) if row else {"error": "not found"}


@router.post("/runs/{rid}/pause")
def pause(rid: str):
    default_orchestrator().pause(rid)
    return {"run_id": rid, "paused": True}


@router.post("/runs/{rid}/resume")
def resume(rid: str):
    return default_orchestrator().resume(rid)


@router.post("/runs/{rid}/cancel")
def cancel(rid: str):
    default_orchestrator().cancel(rid)
    return {"run_id": rid, "cancelled": True}


@router.post("/runs/{rid}/tasks/{task_id}/retry")
def retry_task(rid: str, task_id: str):
    return default_orchestrator().retry_task(rid, task_id)


@router.post("/runs/{rid}/approve")
def approve(rid: str, req: Approve):
    return default_orchestrator().approve(rid, req.approval_id,
                                          approved=req.approved, actor="user:ajay")


@router.get("/runs/{rid}/health")
def run_health(rid: str):
    st = default_orchestrator().store
    run = st.get_run(rid)
    if not run:
        return {"error": "not found"}
    return {"state": run["state"], "metrics": st.metrics(rid),
            "pending_approvals": len(st.pending_approvals(rid))}
