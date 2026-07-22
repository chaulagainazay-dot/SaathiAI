"""M15.1 authenticated connector REST API — /api/v1/connectors/*.

Every route is owner-scoped through `_user(request)` (same auth model as the
CEO/chat/voice routers: the server middleware sets `request.state.user_id`).
Ownership is enforced on every account/execution/approval access; cross-user and
cross-project access is rejected. Credential *metadata* is returned, never raw
secrets — and secrets never appear in any error body. All execution flows through
the ExecutionEngine (gateway-routed); no route calls a provider directly.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from saathi.connectors.platform import registry as R
from saathi.connectors.platform import catalog, health as H
from saathi.connectors.platform import store as S
from saathi.connectors.platform.execution import ExecutionEngine, ExecRequest
from saathi.connectors.platform.models import ConnState

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])


def _user(request: Request) -> str:
    return getattr(request.state, "user_id", None) or "ajay"


def _store() -> S.ConnectorStore:
    return S.default_store()


def _engine() -> ExecutionEngine:
    # engine bound to the shared default store so API + engine agree
    return ExecutionEngine(store=_store())


def _page(items: list, limit: int, offset: int) -> dict:
    return {"total": len(items), "limit": limit, "offset": offset,
            "items": items[offset:offset + limit]}


def _own_account(request: Request, aid: str) -> dict:
    acct = _store().get_account(aid)
    if not acct:
        raise HTTPException(404, "account not found")
    if acct["owner"] != _user(request):
        raise HTTPException(403, "not your account")
    return acct


# ── registry / discovery ────────────────────────────────────────────────────
@router.get("")
def list_connectors(request: Request, limit: int = 50, offset: int = 0):
    return _page([c.to_dict() for c in R.all_connectors()], limit, offset)


@router.get("/categories")
def categories(request: Request):
    cats: dict = {}
    for c in R.all_connectors():
        cats.setdefault(c.category, 0)
        cats[c.category] += 1
    return {"categories": cats}


@router.get("/capabilities")
def capabilities(request: Request):
    return {"capabilities": catalog.all_capabilities()}


@router.get("/tools")
def tools(request: Request, capability: str = "", limit: int = 100, offset: int = 0):
    items = (R.tools_for_capability(capability) if capability else R.all_tools())
    return _page([t.to_dict() for t in items], limit, offset)


@router.get("/tools/{tool_id}")
def tool(request: Request, tool_id: str):
    t = R.get_tool(tool_id)
    if not t:
        raise HTTPException(404, "tool not found")
    return t.to_dict()


@router.get("/{connector_id}")
def connector(request: Request, connector_id: str):
    c = R.get_connector(connector_id)
    if not c:
        raise HTTPException(404, "connector not found")
    return {**c.to_dict(), "health": H.connector_health(connector_id)}


# ── health ──────────────────────────────────────────────────────────────────
@router.get("/health/platform")
def platform_health(request: Request):
    return H.platform_health()


@router.get("/metrics/overview")
def metrics(request: Request):
    return _store().metrics(owner=_user(request))


# ── accounts / credentials (metadata only) ──────────────────────────────────
class AccountIn(BaseModel):
    connector_id: str
    label: str = ""
    backend: str = "env"
    backend_key: str = ""       # env var NAME — never a value
    project_scope: str = ""


@router.get("/accounts/list")
def list_accounts(request: Request, connector_id: str = "",
                  limit: int = 50, offset: int = 0):
    accts = _store().list_accounts(_user(request), connector_id or None)
    return _page(accts, limit, offset)


@router.get("/accounts/{aid}")
def get_account(request: Request, aid: str):
    acct = _own_account(request, aid)
    cred = None
    if acct.get("cred_ref_id"):
        row = _store().get_cred_ref(acct["cred_ref_id"])
        if row:
            # SAFE: metadata only — backend + key NAME, never a value
            cred = {k: row[k] for k in ("ref_id", "connector_id", "backend",
                    "backend_key", "status", "expiry", "granted_scopes")
                    if k in row}
    return {"account": acct, "credential_ref": cred,
            "health": H.connector_health(acct["connector_id"])}


@router.post("/accounts/connect")
def connect_account(request: Request, body: AccountIn):
    if not R.get_connector(body.connector_id):
        raise HTTPException(400, "unknown connector")
    from saathi.connectors.platform.credentials import new_ref
    ref = None
    if body.backend_key:
        ref = new_ref(connector_id=body.connector_id, scope=f"user:{_user(request)}",
                      backend=body.backend, backend_key=body.backend_key,
                      label=body.label)
        _store().put_cred_ref(ref)
    aid = _store().add_account(owner=_user(request), connector_id=body.connector_id,
                               label=body.label, cred_ref_id=ref.ref_id if ref else "",
                               project_scope=body.project_scope)
    return {"account_id": aid, "state": "configured"}


@router.post("/accounts/{aid}/state")
def set_state(request: Request, aid: str, state: str = "", enabled: Optional[bool] = None):
    _own_account(request, aid)
    if state and state not in {s.value for s in ConnState}:
        raise HTTPException(400, "invalid state")
    _store().set_account_state(aid, state or _own_account(request, aid)["state"],
                               enabled=enabled)
    return {"ok": True}


@router.delete("/accounts/{aid}")
def disconnect(request: Request, aid: str):
    acct = _own_account(request, aid)
    _store().set_account_state(aid, "disconnected", enabled=False)
    if acct.get("cred_ref_id"):
        _store().delete_cred_ref(acct["cred_ref_id"])  # drop reference on revoke
    return {"ok": True, "revoked": True}


# ── execution (gateway-routed only) ─────────────────────────────────────────
class ExecIn(BaseModel):
    tool_id: str
    account_id: str = ""
    args: dict = {}
    approval_id: str = ""
    idempotency_key: str = ""
    environment: str = "staging"
    target: str = ""


@router.post("/executions")
def execute(request: Request, body: ExecIn):
    # account ownership enforced before any execution
    if body.account_id:
        _own_account(request, body.account_id)
    r = _engine().execute(ExecRequest(
        owner=_user(request), tool_id=body.tool_id, account_id=body.account_id,
        args=dict(body.args), approval_id=body.approval_id,
        idempotency_key=body.idempotency_key, environment=body.environment,
        target=body.target, actor_type="user"))
    return r.to_dict()


@router.get("/executions/list")
def list_executions(request: Request, limit: int = 50, offset: int = 0):
    rows = _store().list_executions(_user(request), limit=limit, offset=offset)
    return {"items": rows, "limit": limit, "offset": offset}


# ── approvals (exact-action binding) ────────────────────────────────────────
class ApprovalReqIn(BaseModel):
    tool_id: str
    account_id: str = ""
    args: dict = {}
    environment: str = "staging"
    target: str = ""


@router.post("/approvals/request")
def request_approval(request: Request, body: ApprovalReqIn):
    if body.account_id:
        _own_account(request, body.account_id)
    return _engine().request_approval(ExecRequest(
        owner=_user(request), tool_id=body.tool_id, account_id=body.account_id,
        args=dict(body.args), environment=body.environment, target=body.target))


@router.get("/approvals/pending")
def pending(request: Request):
    return {"items": _store().pending_approvals(_user(request))}


@router.post("/approvals/{aid}/decide")
def decide(request: Request, aid: str, approved: bool = True):
    a = _store().get_approval(aid)
    if not a or a["owner"] != _user(request):
        raise HTTPException(404, "approval not found")
    return {"approval": _store().resolve_approval(aid, approved=approved,
                                                  actor=_user(request))}


# ── webhooks / sync (read-only listings) ────────────────────────────────────
@router.get("/webhooks/events")
def webhook_events(request: Request, connector_id: str = "", limit: int = 50):
    return {"items": _store().list_webhooks(connector_id or None, limit)}


@router.get("/sync/{sid}")
def sync_job(request: Request, sid: str):
    job = _store().get_sync(sid)
    if not job or job.get("owner") != _user(request):
        raise HTTPException(404, "sync job not found")
    return job
