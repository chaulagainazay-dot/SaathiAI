"""M10 Agent Runtime API — /api/v1/agents/* (auth inherited from /api/v1).

Approvals are user actions: the global middleware requires an authenticated
user, so an agent process cannot resolve its own approval through this API.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from saathi.agent_runtime.test_fail import TEST_FAIL_STRATEGY
from saathi.agent_runtime.test_hold import TEST_HOLD_STRATEGY
from pydantic import BaseModel

from saathi.agent_runtime import registry
from saathi.agent_runtime.errors import AgentRunError
from saathi.agent_runtime.orchestrator import default_orchestrator
from saathi.agent_runtime.service import start_agent_run

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


def _origin_allowed(origin: str) -> bool:
    """Same allowlist the app's CORS policy uses; resolved lazily so importing
    this module never depends on server start-up order."""
    from saathi.cors_policy import origin_allowed, resolve_cors_origins
    return origin_allowed(origin, resolve_cors_origins())


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


# ── authority truth (Phase 10) ──────────────────────────────────────────────

#: Authority types this contract can assert. DEGRADED and FAILED are deliberately
#: absent: a capability problem and a runtime failure are not authority refusals,
#: and attention already owns them.
AUTHORITY_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
AUTHORITY_BLOCKED = "BLOCKED"

#: Which system asserted the decision. Never inferred from display text.
PROVENANCE_APPROVAL_STORE = "AUTHORITATIVE_APPROVAL_STORE"
PROVENANCE_RUN_STATE = "AUTHORITATIVE_RUN_STATE"

_AUTHORITY_BY_STATE = {
    "awaiting_approval": AUTHORITY_APPROVAL_REQUIRED,
    "blocked": AUTHORITY_BLOCKED,
}

#: Deterministic wording. The system speaks for itself here; no model text.
_AUTHORITY_REASON = {
    AUTHORITY_APPROVAL_REQUIRED: "This action is waiting for your approval.",
    AUTHORITY_BLOCKED: "This action cannot proceed under the current authority state.",
}


@router.get("/authority")
def authority(limit: int = 20, conversation_id: str | None = None):
    """Runs currently held by an authority decision, with their approvals.

    Read-only, and deliberately narrow: only a run waiting for the owner and a
    run the system has stopped. Approvals for every returned run are fetched in
    one grouped query, so a page costs two reads however many rows it holds.

    Nothing here grants, clears or resolves authority. `can_user_act` reports
    whether a decision is *available* to the owner, which is not the same as the
    caller being permitted to make it -- that remains the approval route's own
    check.
    """
    st = default_orchestrator().store
    limit = max(1, min(int(limit or 20), 100))

    runs = st.authority_runs(limit=limit, conversation_id=conversation_id or None)
    approvals = st.pending_approvals_for_runs([r["id"] for r in runs])

    items = []
    for r in runs:
        state = (r.get("state") or "").lower()
        kind = _AUTHORITY_BY_STATE.get(state)
        if not kind:
            continue
        pending = approvals.get(r["id"], [])

        if kind == AUTHORITY_APPROVAL_REQUIRED:
            # An approval-held run without an approval record is a contradiction;
            # fail closed by reporting the run state rather than inventing one.
            provenance = (PROVENANCE_APPROVAL_STORE if pending
                          else PROVENANCE_RUN_STATE)
        else:
            provenance = PROVENANCE_RUN_STATE

        items.append({
            "id": f"{kind}:{r['id']}",
            "type": kind,
            "run_id": r["id"],
            "conversation_id": r.get("conversation_id") or "",
            "objective": r.get("objective") or "",
            "strategy": r.get("strategy") or "",
            "state": state,
            "reason": _AUTHORITY_REASON[kind],
            # The backend's own code for why a run was stopped, when it wrote one.
            "detail_code": r.get("last_error_code") or r.get("terminal_reason") or "",
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
            "resolution_state": "UNRESOLVED",
            "provenance": provenance,
            # Identifiers only. No approval token, no credential, no agent text.
            "approvals": [{"approval_id": a["id"], "agent": a.get("agent") or "",
                           "action": a.get("action") or "", "risk": a.get("risk"),
                           "expires_at": a.get("expires_at")}
                          for a in pending],
            "can_user_act": kind == AUTHORITY_APPROVAL_REQUIRED and bool(pending),
            "read_only": True,
        })

    return {"items": items, "count": len(items)}


# ── historical truth (Phase 9) ──────────────────────────────────────────────

#: Certification-only strategies. Their runs are real runtime records, but they
#: exist to exercise the system rather than to do the owner's work, so history
#: excludes them by default. Identified by strategy, never by matching text in an
#: objective, and taken from the fixtures' own constants so the two cannot drift.
TEST_STRATEGIES: tuple[str, ...] = (TEST_HOLD_STRATEGY, TEST_FAIL_STRATEGY)

#: Verification is its own truth. A run ending says nothing about whether
#: anything was verified, so these are derived only from verification records.
VERIFICATION_PASSED = "PASSED"
VERIFICATION_FAILED = "FAILED"
VERIFICATION_UNAVAILABLE = "UNAVAILABLE"


def _verification_state(summary: dict | None) -> str:
    """A failure dominates any number of passes; absence stays absence."""
    if not summary:
        return VERIFICATION_UNAVAILABLE
    if summary.get("failed", 0) > 0:
        return VERIFICATION_FAILED
    if summary.get("passed", 0) > 0:
        return VERIFICATION_PASSED
    return VERIFICATION_UNAVAILABLE


@router.get("/history")
def history(limit: int = 20, before: float | None = None,
            conversation_id: str | None = None,
            include_test_strategies: bool = False):
    """Terminal runs, newest-ended first, each with a verification summary.

    Read-only. This exists because `/runs` answers a different question: it
    returns the newest runs of any kind, so filtering it down to terminal rows
    afterwards lets short-lived runs push real history out of the window. Here
    the terminal filter and the fixture exclusion are part of the query.

    Verification is aggregated for every returned run in a single grouped read,
    so a page of history costs two queries regardless of how many rows it holds
    -- never one lookup per row.
    """
    st = default_orchestrator().store
    limit = max(1, min(int(limit or 20), 100))

    rows, has_more = st.terminal_history(
        limit=limit,
        before=before,
        conversation_id=conversation_id or None,
        exclude_strategies=() if include_test_strategies else TEST_STRATEGIES,
    )
    summaries = st.verification_summary([r["id"] for r in rows])

    items = []
    for r in rows:
        summary = summaries.get(r["id"])
        items.append({
            "run_id": r["id"],
            "conversation_id": r.get("conversation_id") or "",
            "strategy": r.get("strategy") or "",
            "objective": r.get("objective") or "",
            "terminal_state": r.get("state") or "",
            "terminal_reason": r.get("terminal_reason") or "",
            "created_at": r.get("created_at"),
            "terminal_at": r.get("updated_at"),
            "verification_state": _verification_state(summary),
            "verification_passed_count": (summary or {}).get("passed", 0),
            "verification_failed_count": (summary or {}).get("failed", 0),
            "is_test_strategy": (r.get("strategy") or "") in TEST_STRATEGIES,
        })

    # A cursor the caller can hand back as `before` to read older history.
    next_before = items[-1]["terminal_at"] if items and has_more else None
    return {"items": items, "has_more": has_more, "next_before": next_before}


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
def approve(rid: str, req: Approve, request: Request):
    """Resolve one approval, bound to the run that owns it.

    Three properties this route has to hold, each of which it did not before:

    * The approval must belong to `rid`. Resolving by approval id alone let a
      caller pass one run's id with another run's approval: the wrong approval
      was resolved, and the run named in the URL was transitioned out of
      AWAITING_APPROVAL without its own approval ever being decided -- a run
      advancing past its approval gate. The pairing is now checked first.
    * An unknown approval is a 404, not the 500 the unhandled KeyError produced.
    * A cross-site browser request is refused. The session cookie is SameSite=None,
      so a page on another origin could previously drive this mutation with the
      user's cookie. An Origin outside the allowlist is now rejected; a request
      with no Origin at all is not a browser CSRF vector and is left alone, so
      server-to-server callers are unaffected.

    Resolution itself is unchanged and remains the store's: an already-resolved
    approval is returned as-is rather than re-decided.
    """
    from fastapi.responses import JSONResponse

    origin = request.headers.get("origin", "")
    if origin and not _origin_allowed(origin):
        return JSONResponse({"ok": False, "error": "ORIGIN_REJECTED"}, status_code=403)

    st = default_orchestrator().store
    appr = st.get_approval(req.approval_id)
    if not appr:
        return JSONResponse({"ok": False, "error": "APPROVAL_NOT_FOUND"}, status_code=404)
    if appr.get("run_id") != rid:
        # Deliberately the same answer as a missing approval: this approval does
        # not exist *on this run*, and saying more would confirm it exists on
        # another one.
        return JSONResponse({"ok": False, "error": "APPROVAL_NOT_FOUND"}, status_code=404)

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
