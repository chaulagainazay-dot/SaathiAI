"""Saathi Chat API — /api/v1/chat/* (auth inherited from the global
/api/v1 middleware). Streaming replies via SSE; every inference and tool call
travels through the ExecutionGateway inside the engine.
"""
from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from saathi.chat.engine import default_engine, AGENT_ROLES
from saathi.chat.store import default_store

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


# ── models ──────────────────────────────────────────────────────────────────
class CreateConversation(BaseModel):
    title: str = ""
    model: str = ""
    project_id: str = ""
    folder: str = ""
    tags: list[str] = []
    tools: list[str] = []


class UpdateConversation(BaseModel):
    title: str | None = None
    folder: str | None = None
    tags: list[str] | None = None
    model: str | None = None
    project_id: str | None = None
    pinned: bool | None = None
    favorite: bool | None = None
    archived: bool | None = None


class SendMessage(BaseModel):
    text: str
    system: str = ""
    agent: str = ""
    stream: bool = False


class EditMessage(BaseModel):
    text: str


class ToolCall(BaseModel):
    tool: str
    args: dict = {}


class AgentTask(BaseModel):
    agent: str
    task: str
    delegated_by: str = ""


# ── conversations (Layer 1) ────────────────────────────────────────────────
@router.get("/conversations")
def list_conversations(folder: str | None = None, project_id: str | None = None,
                       archived: bool = False, pinned: bool = False,
                       limit: int = 50, offset: int = 0):
    return {"conversations": default_store().list_conversations(
        folder=folder, project_id=project_id, include_archived=archived,
        pinned_only=pinned, limit=limit, offset=offset)}


@router.post("/conversations")
def create_conversation(req: CreateConversation):
    return default_store().create_conversation(
        title=req.title, model=req.model, project_id=req.project_id,
        folder=req.folder, tags=req.tags, tools=req.tools)


@router.get("/conversations/{cid}")
def get_conversation(cid: str, limit: int = 100, offset: int = 0):
    st = default_store()
    conv = st.get_conversation(cid)
    if not conv:
        return {"error": "not found"}
    return {"conversation": conv,
            "messages": st.list_messages(cid, limit=limit, offset=offset),
            "attachments": st.list_attachments(cid),
            "memory_links": st.list_memory_links(cid),
            "executions": st.list_executions(cid),
            "agent_runs": st.list_agent_runs(cid),
            "checkpoints": st.list_checkpoints(cid)}


@router.patch("/conversations/{cid}")
def update_conversation(cid: str, req: UpdateConversation):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    return default_store().update_conversation(cid, **fields) or {"error": "not found"}


@router.delete("/conversations/{cid}")
def delete_conversation(cid: str):
    return default_store().delete(cid) or {"error": "not found"}


@router.post("/conversations/{cid}/restore")
def restore_conversation(cid: str):
    return default_store().restore(cid) or {"error": "not found"}


@router.get("/search")
def search(q: str, limit: int = 20):
    return {"results": default_store().search(q, limit=limit)}


# ── messages (Layers 2+3) ───────────────────────────────────────────────────
@router.post("/conversations/{cid}/messages")
def send_message(cid: str, req: SendMessage):
    eng = default_engine()
    if req.stream:
        def _gen():
            yield f"data: {json.dumps({'event': 'start'})}\n\n"
            try:
                r = eng.send(cid, req.text, system=req.system, agent=req.agent)
                text = r.message["content"]
                # incremental delivery in word groups (Layer 10 streaming)
                words = text.split(" ")
                for i in range(0, len(words), 8):
                    yield ("data: " + json.dumps(
                        {"event": "delta", "text": " ".join(words[i:i + 8]) + " "}) + "\n\n")
                yield ("data: " + json.dumps(
                    {"event": "done", "message": r.message,
                     "citations": r.citations,
                     "execution": r.execution}) + "\n\n")
            except Exception as exc:
                yield ("data: " + json.dumps(
                    {"event": "error", "detail": str(exc)[:300]}) + "\n\n")
        return StreamingResponse(_gen(), media_type="text/event-stream")
    try:
        r = eng.send(cid, req.text, system=req.system, agent=req.agent)
    except KeyError:
        return {"error": "conversation not found"}
    return {"message": r.message, "execution": r.execution,
            "memory_links": r.memory_links, "citations": r.citations}


@router.post("/messages/{mid}/edit")
def edit_message(mid: str, req: EditMessage):
    st = default_store()
    msg = st.get_message(mid)
    if not msg:
        return {"error": "not found"}
    r = default_engine().edit_and_resend(msg["conversation_id"], mid, req.text)
    return {"message": r.message}


@router.post("/messages/{mid}/regenerate")
def regenerate(mid: str):
    st = default_store()
    msg = st.get_message(mid)
    if not msg:
        return {"error": "not found"}
    r = default_engine().regenerate(msg["conversation_id"], mid)
    return {"message": r.message}


@router.get("/messages/{mid}/versions")
def message_versions(mid: str):
    return {"versions": default_store().message_versions(mid)}


@router.get("/messages/{mid}/citations")
def citations(mid: str):
    return {"citations": default_store().list_citations(mid)}


# ── attachments (Layer 6) ───────────────────────────────────────────────────
class AddAttachment(BaseModel):
    kind: str
    name: str
    path: str
    size: int = 0


@router.post("/conversations/{cid}/attachments")
def add_attachment(cid: str, req: AddAttachment):
    return default_store().add_attachment(cid, kind=req.kind, name=req.name,
                                          path=req.path, size=req.size)


# ── tools (Layer 7) ─────────────────────────────────────────────────────────
@router.post("/messages/{mid}/tools")
def call_tool(mid: str, req: ToolCall):
    st = default_store()
    msg = st.get_message(mid)
    if not msg:
        return {"error": "not found"}
    return default_engine().call_tool(msg["conversation_id"], mid,
                                      req.tool, req.args)


# ── checkpoints (Layer 4) ───────────────────────────────────────────────────
@router.post("/conversations/{cid}/checkpoints")
def create_checkpoint(cid: str, label: str = ""):
    return default_store().create_checkpoint(cid, label=label)


@router.post("/checkpoints/{kid}/restore")
def restore_checkpoint(kid: str):
    try:
        return default_store().restore_checkpoint(kid)
    except KeyError:
        return {"error": "not found"}


# ── agents (Layer 9) ────────────────────────────────────────────────────────
@router.get("/agents")
def agents():
    return {"agents": [{"name": k, "role": v} for k, v in AGENT_ROLES.items()]}


@router.post("/conversations/{cid}/agents")
def run_agent(cid: str, req: AgentTask):
    try:
        return default_engine().run_agent(cid, req.agent, req.task,
                                          delegated_by=req.delegated_by)
    except ValueError as exc:
        return {"error": str(exc)}


# ── M10: multi-agent team runs (real orchestration, not a mock) ────────────
class TeamRun(BaseModel):
    objective: str
    strategy: str = ""
    execute: bool = True


@router.post("/conversations/{cid}/team-run")
def team_run(cid: str, req: TeamRun):
    """Spawn a real M10 orchestration run linked to this conversation.

    Delegates to ChatEngine.start_orchestration (M10 Orchestrator underneath)
    — no parallel execution path. Task graph, approvals, tool intents, and
    events are all inspectable via /api/v1/agents/runs/{run_id}."""
    try:
        return default_engine().start_orchestration(
            cid, req.objective, strategy=req.strategy, execute=req.execute)
    except KeyError:
        return {"error": "conversation not found"}
