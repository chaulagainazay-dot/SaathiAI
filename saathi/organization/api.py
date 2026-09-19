"""AI Company API — /api/v1/organization/* (authenticated by the global /api/v1
middleware, same model as /api/v1/agents and /api/v1/control).

Read-only except ``POST /missions``, which starts a bounded organization
mission of deterministic read-only probes. Nothing here can place an order,
approve, change a risk limit, or reach the ExecutionGateway.
"""
from __future__ import annotations

import json
import re
import sqlite3

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from saathi.organization.charter import load_charter
from saathi.organization.missions import (
    MissionError, MissionRunner, TEMPLATES, delegation_tree,
)
from saathi.organization.state import company_snapshot, role_states
from saathi.organization.store import default_store
from saathi.organization.system_status import system_status

router = APIRouter(prefix="/api/v1/organization", tags=["organization"])

_SECRET_KEY = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|cookie|credential|authorization|"
    r"session[_-]?(id|key)|^auth$|^bearer$)", re.I)


def _user(request: Request) -> str:
    return getattr(request.state, "user_id", None) or "ajay"


def _err(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": code, "message": message}, status_code=status)


def redact(value):
    """Drop any mapping key that looks like a credential, recursively."""
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if _SECRET_KEY.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


@router.get("/company")
def company(request: Request):
    return company_snapshot(_user(request))


@router.get("/system-status")
def get_system_status():
    return system_status()


@router.get("/templates")
def templates():
    return {"templates": [{"template_id": t.template_id, "title": t.title,
                           "objective": t.objective} for t in TEMPLATES.values()]}


@router.get("/roles/{role_id}")
def role_detail(role_id: str):
    ch = load_charter()
    role = ch.roles.get(role_id)
    if role is None:
        return _err("NOT_FOUND", "Unknown role", 404)
    states, sources = role_states()
    pub = role.to_public()
    pub.update(states[role_id])
    office = ch.offices[role.office_id]
    runtime = None
    if role.binding.kind == "agent_runtime":
        from saathi.agent_runtime import registry
        d = registry.get(role.binding.ref)
        if d:
            runtime = {"agent_id": d.agent_id, "model_policy": d.model_policy,
                       "allowed_tools": d.allowed_tools, "denied_tools": d.denied_tools,
                       "risk_ceiling": int(d.risk_ceiling), "can_self_approve": d.can_self_approve,
                       "max_token_budget": d.max_token_budget}
    elif role.binding.kind == "mission_agent":
        from saathi.platform.orchestration.roles import AgentRoleRegistry
        try:
            p = AgentRoleRegistry().get_by_agent_type(role.binding.ref)
            runtime = {"agent_type": role.binding.ref, "execution_authority": "PlatformAgentRuntime",
                       "allowed_capabilities": list(p.allowed_capabilities),
                       "approval_requirement": p.approval_requirement}
        except ValueError:
            runtime = None
    with default_store()._conn() as c:
        rows = c.execute(
            "SELECT s.id,s.mission_id,s.objective,s.status,s.reason,s.started_at,s.finished_at,"
            "s.parent_id,m.title FROM org_step s JOIN org_mission m ON m.id=s.mission_id "
            "WHERE s.role_id=? ORDER BY s.started_at DESC LIMIT 10", (role_id,)).fetchall()
        recent = [dict(r) for r in rows]
        for r in recent:
            parent = c.execute("SELECT role_id FROM org_step WHERE id=?", (r["parent_id"],)).fetchone()
            r["delegated_by"] = parent[0] if parent else "owner"
    current = states[role_id].get("activity")
    current_step = None
    if current and current.get("step_id"):
        s = default_store().get_step(current["step_id"])
        if s:
            parent = default_store().get_step(s["parent_id"]) if s["parent_id"] else None
            steps = default_store().steps(s["mission_id"])
            siblings = [x["role_id"] for x in steps if x["parent_id"] == s["parent_id"] and x["id"] != s["id"]]
            reviewers = [x["role_id"] for x in steps
                         if x["role_id"].startswith(("ic.", "gov.", "risk.challenger"))
                         and x["id"] != s["id"]]
            current_step = {**s, "delegated_by": parent["role_id"] if parent else "owner",
                            "collaborating_with": siblings, "reviewed_by": reviewers,
                            "output": redact(s["output"])}
    return {"role": pub, "office": vars(office), "runtime": runtime,
            "current_step": current_step, "recent_steps": recent, "sources": sources,
            "resource_usage": {"llm_tokens": None, "note": "Organization missions use no model "
                               "inference; token cost is not applicable"}}


@router.get("/offices/{office_id}")
def office_detail(office_id: str):
    ch = load_charter()
    office = ch.offices.get(office_id)
    if office is None:
        return _err("NOT_FOUND", "Unknown office", 404)
    states, _ = role_states()
    members = []
    for r in ch.members(office_id):
        p = r.to_public()
        p.update(states[r.role_id])
        members.append(p)
    ids = [m["role_id"] for m in members]
    work = []
    if ids:
        ph = ",".join("?" * len(ids))
        with default_store()._conn() as c:
            work = [dict(r) for r in c.execute(
                f"SELECT s.id,s.mission_id,s.role_id,s.objective,s.status,s.reason,s.started_at,"
                f"s.finished_at,m.title,m.status AS mission_status FROM org_step s "
                f"JOIN org_mission m ON m.id=s.mission_id WHERE s.role_id IN ({ph}) "
                f"ORDER BY s.started_at DESC LIMIT 30", ids).fetchall()]
    active = [w for w in work if not w["finished_at"] and w["mission_status"] == "RUNNING"]
    queued = [w for w in work if w["status"] == "ASSIGNED" and w["mission_status"] == "RUNNING"]
    blocked = [w for w in work if w["status"] in ("BLOCKED", "AWAITING_EVIDENCE", "ERROR")]
    return {"office": vars(office), "floor": vars(ch.floors[office.floor_id]),
            "department": vars(ch.departments[office.department_id]),
            "lead": office.lead_role_id or None, "members": members,
            "active_work": active, "queued_work": queued, "blocked_work": blocked[:10],
            "recent_outputs": [w for w in work if w["finished_at"]][:10],
            "resource_usage": {"llm_inference": "none (deterministic probes)"}}


class OperationsToggle(BaseModel):
    running: bool


@router.get("/operations")
def operations_status():
    from saathi.organization.operations import OperationsLoop
    return OperationsLoop.instance().status()


@router.post("/operations")
def operations_toggle(req: OperationsToggle):
    """Owner control: run or pause the company's standing duties."""
    from saathi.organization.operations import OperationsLoop
    return OperationsLoop.instance().set_running(req.running)


@router.on_event("startup")
def _start_operations() -> None:
    try:
        from saathi.organization.operations import OperationsLoop
        OperationsLoop.instance().start_if_enabled()
    except Exception as exc:  # never block server startup
        print(f"[saathi] organization operations not started: {exc}")


class StartMission(BaseModel):
    objective: str = Field(default="", max_length=500)
    template_id: str = Field(default="", max_length=64)


@router.post("/missions")
def start_mission(req: StartMission, request: Request):
    runner = MissionRunner()
    try:
        m = runner.create(objective=req.objective, template_id=req.template_id,
                          created_by=f"user:{_user(request)}")
        runner.start_async(m["id"])
    except MissionError as e:
        return _err(e.code, e.message, e.status)
    return {"ok": True, "mission": default_store().get_mission(m["id"])}


@router.get("/missions")
def missions(limit: int = 20):
    return {"missions": default_store().list_missions(limit=max(1, min(limit, 100)))}


@router.get("/missions/{mission_id}")
def mission(mission_id: str):
    tree = delegation_tree(default_store(), mission_id)
    if tree is None:
        return _err("NOT_FOUND", "Unknown mission", 404)
    tree = redact(tree)
    tree["events"] = default_store().events(mission_id=mission_id, limit=200)
    return tree


@router.get("/events")
def events(limit: int = 50):
    return {"events": default_store().events(limit=max(1, min(limit, 200)))}


@router.get("/evidence/{evidence_id}")
def evidence(evidence_id: str):
    """Open one Evidence Service record by id (read-only). The Evidence Service
    exposes query/stats only; this is the by-id view the Company View links to."""
    if not re.fullmatch(r"[0-9a-f]{8,32}", evidence_id):
        return _err("INVALID_ID", "Evidence id must be hex", 400)
    from saathi.evidence.store import default_store as ev_store
    path = ev_store().db_path
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
    c.row_factory = sqlite3.Row
    try:
        row = c.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()
    finally:
        c.close()
    if row is None:
        return _err("NOT_FOUND", "Unknown evidence id", 404)
    d = dict(row)
    for k in ("metrics", "feedback", "artifacts"):
        try:
            d[k] = json.loads(d.get(k) or "null")
        except Exception:
            pass
    return {"evidence": redact(d)}
