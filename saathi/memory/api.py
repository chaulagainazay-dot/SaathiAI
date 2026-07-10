"""M9 Memory API — /api/v1/memory/* (auth inherited from /api/v1 middleware).

All writes are auditable (versions + access log). Reads are namespace-scoped.
Deleted memories never appear in search.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from saathi.memory.engine import default_engine, plan_query

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


class CreateMemory(BaseModel):
    namespace: str
    content: str
    memory_type: str = "semantic"
    project_id: str = ""
    user_scope: str = ""
    confidence: float = 0.5
    importance: float = 0.5
    privacy: str = "internal"
    retention: str = "standard"
    pinned: bool = False
    citation: str = ""


class UpdateMemory(BaseModel):
    content: str | None = None
    confidence: float | None = None
    importance: float | None = None
    pinned: bool | None = None


class SearchQuery(BaseModel):
    query: str
    user: str = "ajay"
    project_id: str = ""
    conversation_id: str = ""
    agent: str = ""
    top_k: int = 8


class Feedback(BaseModel):
    useful: bool
    note: str = ""


@router.get("/health")
def health():
    eng = default_engine()
    return {"stats": eng.store.stats(), "embedder": eng.embedder.provider,
            "embedding_version": eng.embedder.version}


@router.get("/list")
def list_memories(namespace: str | None = None, memory_type: str | None = None,
                  project_id: str | None = None, limit: int = 50):
    ns = [namespace] if namespace else None
    return {"memories": default_engine().store.list_items(
        namespaces=ns, memory_type=memory_type, project_id=project_id, limit=limit)}


@router.post("/search")
def search(req: SearchQuery):
    eng = default_engine()
    plan = plan_query(user=req.user, project_id=req.project_id,
                      conversation_id=req.conversation_id, agent=req.agent,
                      top_k=req.top_k)
    results, mode, run_id = eng.retrieve(req.query, plan=plan,
                                         actor=f"api:{req.user}")
    return {"mode": mode, "run_id": run_id,
            "results": [r.to_dict() for r in results]}


@router.post("/create")
def create(req: CreateMemory):
    eng = default_engine()
    mid = eng.remember(namespace=req.namespace, content=req.content,
                       memory_type=req.memory_type, project_id=req.project_id,
                       user_scope=req.user_scope, confidence=req.confidence,
                       importance=req.importance, privacy=req.privacy,
                       retention=req.retention, pinned=req.pinned,
                       source_type="api", citation=req.citation)
    return {"id": mid}


@router.get("/item/{mid}")
def item(mid: str):
    eng = default_engine()
    it = eng.store.get_item(mid)
    if not it:
        return {"error": "not found"}
    return {"item": it, "sources": eng.store.sources(mid),
            "versions": eng.store.versions(mid),
            "relations": eng.store.relations(mid)}


@router.patch("/item/{mid}")
def update(mid: str, req: UpdateMemory):
    eng = default_engine()
    if req.content is not None:
        return {"id": eng.supersede(mid, req.content, reason="api update")}
    fields = {k: v for k, v in req.model_dump().items()
              if v is not None and k != "content"}
    eng.store.update_item(mid, **fields)
    return {"id": mid, "updated": list(fields)}


@router.post("/item/{mid}/pin")
def pin(mid: str, pinned: bool = True):
    default_engine().store.update_item(mid, pinned=pinned)
    return {"id": mid, "pinned": pinned}


@router.post("/item/{mid}/feedback")
def feedback(mid: str, req: Feedback):
    default_engine().reinforce(mid, useful=req.useful)
    return {"id": mid, "recorded": True}


@router.delete("/item/{mid}")
def delete(mid: str):
    default_engine().forget(mid, reason="api delete")
    return {"id": mid, "deleted": True}


@router.post("/item/{mid}/restore")
def restore(mid: str):
    return {"id": mid, "restored": default_engine().restore(mid)}


@router.get("/conflicts")
def conflicts():
    return {"conflicts": default_engine().store.conflicts()}


@router.post("/conflicts/{cid}/resolve")
def resolve(cid: str):
    default_engine().store.resolve_conflict(cid)
    return {"id": cid, "resolved": True}


@router.post("/reindex")
def reindex(batch: int = 200):
    return default_engine().reindex(batch=batch)


@router.get("/runs")
def runs(limit: int = 20):
    return {"runs": default_engine().store.recent_runs(limit=limit)}
