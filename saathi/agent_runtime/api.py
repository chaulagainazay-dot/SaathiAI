"""M10 Agent Runtime API — /api/v1/agents/* (auth inherited from /api/v1).

Approvals are user actions: the global middleware requires an authenticated
user, so an agent process cannot resolve its own approval through this API.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from saathi.agent_runtime.models import RunState

from saathi.agent_runtime.test_fail import TEST_FAIL_STRATEGY
from saathi.agent_runtime.test_hold import TEST_HOLD_STRATEGY
from pydantic import BaseModel

from saathi.agent_runtime import registry
from saathi.agent_runtime.errors import AgentRunError
from saathi.agent_runtime.orchestrator import default_orchestrator
from saathi.agent_runtime.service import start_agent_run

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


#: The permission an authority mutation requires. Uses the vocabulary the roles
#: already ship with -- owner holds "*", admin and member hold "write", viewer
#: does not -- so no role migration is needed to make the check meaningful. A
#: dedicated "approve" permission can replace this later by editing one constant
#: and seeding it onto the roles that should hold it.
APPROVAL_PERMISSION = "write"


#: Future granular authority vocabulary. Every run-control mutation currently
#: maps to APPROVAL_PERMISSION ("write") because that is the vocabulary the
#: seeded roles actually ship with; these names are the intended replacement and
#: exist so the coarse mapping stays visible rather than becoming silent debt.
#: Migrating to them means seeding the permissions onto roles and swapping the
#: constant each route passes -- no route logic changes.
FUTURE_PERMISSIONS = {
    "approval.resolve": "approve or deny one approval",
    "run.create": "create an agent run",
    "run.pause": "pause a running run",
    "run.resume": "resume a paused run",
    "run.cancel": "cancel a run",
    "run.execute": "start execution of a run",
    "task.retry": "retry one task of a run",
}


def _authorize(request, action: str, *, detail: str = ""):
    """The single authority gate for a run-control mutation.

    Returns ``(actor_id, refusal)``; ``refusal`` is a response when the caller
    may not proceed and ``None`` when they may. Refusals are audited, because a
    refused authority attempt is exactly what an audit log is for.

    Deliberately checked before any resource lookup, so an unauthorised caller
    cannot learn whether a run or task exists by varying identifiers.
    """
    from fastapi.responses import JSONResponse

    actor_id, allowed = _resolve_actor(request)
    if allowed:
        return actor_id, None

    _audit_authority(request, f"{action}.denied_unauthorized", ok=False,
                     user_id=actor_id, detail=detail[:120])
    return actor_id, JSONResponse({"ok": False, "error": "NOT_AUTHORIZED"},
                                  status_code=403)


def _resolve_actor(request) -> tuple[str, bool]:
    """Who is calling, and may they decide an approval.

    Returns ``(user_id, allowed)``. Fails closed on every uncertainty: an
    unidentifiable caller is authorised for nothing. Note this is *authorisation*
    -- authentication has already happened in the app's auth layer, and the two
    were previously the same check, which is why any authenticated caller could
    resolve any approval.
    """
    from saathi import sessions
    from saathi.security.store import get_store

    token = (request.cookies.get("baadar_session")
             or request.headers.get("x-baadar-session", ""))
    user_id = sessions.identify(token) if token else None
    if not user_id:
        return "", False
    try:
        return user_id, get_store().has_permission(user_id, APPROVAL_PERMISSION)
    except Exception:
        return user_id, False


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
def create_run(req: CreateRun, request: Request):
    """Create a run. The last unauthorised mutation in this family.

    `start_agent_run` already validated the *request* -- objective present,
    strategy known, authority class fail-closed when elevated -- but validating
    what is being asked is not the same as deciding who may ask. Without this
    gate any authenticated caller could start agent work, and the run recorded a
    hardcoded actor rather than the person who created it.

    Authorisation is independent of the fixture gating in
    `agent_runtime.test_authority`: permission to create a run never unlocks a
    certification strategy, and arming a fixture never grants permission.
    """
    actor, refusal = _authorize(request, "run.create", detail=req.strategy or "")
    if refusal:
        return refusal

    orch = default_orchestrator()
    rec = start_agent_run(
        objective=req.objective,
        strategy=req.strategy,
        # The real creator, not the module default.
        actor=f"user:{actor}",
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
        _audit_authority(request, "run.create", ok=False, user_id=actor,
                         detail=f"rejected {rec.error_code}")
        return {
            "error": rec.error_code,
            "message": rec.message,
            "violations": rec.violations,
            "ok": False,
        }

    _audit_authority(request, "run.create", ok=True, user_id=actor,
                     detail=f"{rec.run_id[:32]} {req.strategy or 'auto'}")
    return {"run_id": rec.run_id, "ok": True, "state": rec.state}


@router.post("/runs/{rid}/execute")
def execute(rid: str, request: Request, max_wall_sec: float = 60.0):
    """Start a run's execution.

    Not in the four routes this milestone was scoped around, but the same
    authority family and strictly more powerful than any of them: it is what
    causes agents to run and tools to be requested. Leaving it unauthorised
    while hardening pause would have secured the brakes and not the accelerator.
    """
    from fastapi.responses import JSONResponse

    actor, refusal = _authorize(request, "run.execute", detail=rid)
    if refusal:
        return refusal

    st = default_orchestrator().store
    if not st.get_run(rid):
        return JSONResponse({"ok": False, "error": "RUN_NOT_FOUND"}, status_code=404)

    _audit_authority(request, "run.execute", ok=True, user_id=actor, detail=rid[:32])
    return default_orchestrator().run(rid, max_wall_sec=max_wall_sec)


# ── execution authority snapshot (Phase 14) ─────────────────────────────────


def _kill_switch_blocked() -> bool | None:
    """Global kill-switch state, or None when it cannot be established.

    Only the GLOBAL and TRADING_GUARDIAN scopes are meaningful for an
    agent-runtime action; the others key on strategy/instrument/portfolio, which
    an agent run does not have. Any failure returns None, which denies the
    positive state rather than defaulting to permissive.
    """
    try:
        from saathi.platform.tg.service import TradingGuardianService  # noqa: F401
        from saathi.platform.tg.kill_switch import KillSwitchStore

        res = KillSwitchStore().is_blocked()
        return bool(res.get("blocked"))
    except Exception:
        return None


def _platform_runtime_bound() -> bool | None:
    """Whether agent tool execution has a platform runtime bound.

    This is the real precondition: `gateway_exec` rejects every tool request
    with PLATFORM_RUNTIME_REQUIRED when it is absent.
    """
    try:
        from saathi.agent_runtime.gateway_exec import AgentExecutor

        ex = AgentExecutor()
        return bool(getattr(ex, "platform_runtime", None)
                    and getattr(ex, "platform_token", None))
    except Exception:
        return None


def _gateway_decision(intent_id: str) -> dict | None:
    """The ExecutionGateway's recorded decision for one intent, or None.

    Read-only, and read *from* the gateway rather than recomputed: the gateway
    owns the decision, this surface only reports it. None means no decision was
    recorded, which the composer reports as not-evaluated rather than as a pass.
    """
    if not intent_id:
        return None
    try:
        from saathi.execution.gateway import ExecutionGateway

        return ExecutionGateway().inspect_decision(intent_id=intent_id)
    except Exception:
        return None


@router.get("/runs/{rid}/execution-authority")
def execution_authority(rid: str, request: Request, task_id: str = "",
                        intent_id: str = ""):
    """Read-only: what this system can truthfully say about one action.

    Pure inspection. It executes nothing, approves nothing, invokes no gateway
    mutation and changes no state -- and its answer is not a capability token:
    `gateway_exec` still enforces independently when execution happens, so a
    positive snapshot may never be replayed as permission.

    Requires authentication like every other authority surface. Unlike the
    mutation routes it does not 403 a caller who merely lacks `write`: a
    read-only explanation of why they cannot act is the point, and it is
    returned as NOT_AUTHORIZED rather than withheld.
    """
    from saathi.agent_runtime.execution_authority import AuthorityInputs, compose

    actor_id, allowed = _resolve_actor(request)
    st = default_orchestrator().store
    run = st.get_run(rid)

    inputs = AuthorityInputs(
        actor_user_id=actor_id or None,
        has_permission=allowed if actor_id else None,
        run=run,
        pending_approvals=st.pending_approvals(rid) if run else [],
        resolved_approvals=_resolved_approvals(st, rid) if run else [],
        kill_switch_blocked=_kill_switch_blocked(),
        platform_runtime_bound=_platform_runtime_bound(),
        gateway_decision=_gateway_decision(intent_id),
    )
    return compose(inputs, run_id=rid, task_id=task_id)


def _resolved_approvals(store, rid: str) -> list[dict]:
    """Approvals on this run that are no longer pending."""
    try:
        with store._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM approval_request WHERE run_id=? AND status!='pending'",
                (rid,)).fetchall()]
    except Exception:
        return []


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
def pause(rid: str, request: Request):
    """Pause a run. Authorisation first, then existence, then lifecycle."""
    from fastapi.responses import JSONResponse

    actor, refusal = _authorize(request, "run.pause", detail=rid)
    if refusal:
        return refusal

    st = default_orchestrator().store
    run = st.get_run(rid)
    if not run:
        # Previously this claimed {"paused": True} for a run that did not exist.
        return JSONResponse({"ok": False, "error": "RUN_NOT_FOUND"}, status_code=404)

    before = run["state"]
    default_orchestrator().pause(rid, actor=f"user:{actor}")
    after = st.get_run(rid)["state"]
    _audit_authority(request, "run.pause", ok=(after != before), user_id=actor,
                     detail=f"{rid[:32]} {before}->{after}")
    # Reports what the lifecycle actually did, not what was asked for: an
    # illegal transition leaves the state alone and must not read as success.
    return {"run_id": rid, "paused": after == RunState.PAUSED.value, "state": after}


@router.post("/runs/{rid}/resume")
def resume(rid: str, request: Request):
    """Resume a paused run. Resuming is not approving: a run held at the
    approval gate has an illegal transition to RUNNING and stays held."""
    from fastapi.responses import JSONResponse

    actor, refusal = _authorize(request, "run.resume", detail=rid)
    if refusal:
        return refusal

    st = default_orchestrator().store
    run = st.get_run(rid)
    if not run:
        return JSONResponse({"ok": False, "error": "RUN_NOT_FOUND"}, status_code=404)

    before = run["state"]
    try:
        res = default_orchestrator().resume(rid, actor=f"user:{actor}")
    except Exception as exc:
        # An illegal transition is a state conflict, not a server fault.
        _audit_authority(request, "run.resume", ok=False, user_id=actor,
                         detail=f"{rid[:32]} {before} illegal")
        return JSONResponse({"ok": False, "error": "INVALID_STATE",
                             "state": before, "detail": type(exc).__name__},
                            status_code=409)

    _audit_authority(request, "run.resume", ok=True, user_id=actor,
                     detail=f"{rid[:32]} {before}->{st.get_run(rid)['state']}")
    return res


@router.post("/runs/{rid}/cancel")
def cancel(rid: str, request: Request):
    """Cancel a run. Bound to the run in the URL and to nothing else."""
    from fastapi.responses import JSONResponse

    actor, refusal = _authorize(request, "run.cancel", detail=rid)
    if refusal:
        return refusal

    st = default_orchestrator().store
    run = st.get_run(rid)
    if not run:
        return JSONResponse({"ok": False, "error": "RUN_NOT_FOUND"}, status_code=404)

    before = run["state"]
    default_orchestrator().cancel(rid, actor=f"user:{actor}")
    after = st.get_run(rid)["state"]
    _audit_authority(request, "run.cancel", ok=True, user_id=actor,
                     detail=f"{rid[:32]} {before}->{after}")
    # Cancellation is durable and idempotent in the lifecycle controller; the
    # response reports the resulting state rather than asserting success.
    return {"run_id": rid, "cancelled": after == RunState.CANCELLED.value,
            "state": after}


@router.post("/runs/{rid}/tasks/{task_id}/retry")
def retry_task(rid: str, task_id: str, request: Request):
    """Retry one task of one run.

    The binding matters more here than anywhere else: `retry_task` resets a task
    by id, so without this check a request addressed to run A could reset a task
    belonging to run B -- proven against the real store before this was added --
    and then run A. The task must belong to the run named in the URL.
    """
    from fastapi.responses import JSONResponse

    actor, refusal = _authorize(request, "task.retry", detail=f"{rid}/{task_id}")
    if refusal:
        return refusal

    st = default_orchestrator().store
    run = st.get_run(rid)
    if not run:
        return JSONResponse({"ok": False, "error": "RUN_NOT_FOUND"}, status_code=404)

    task = next((t for t in st.list_tasks(rid) if t["id"] == task_id), None)
    if not task:
        # Same answer whether the task is unknown or belongs to another run:
        # it does not exist *on this run*, and saying more would confirm it
        # exists elsewhere.
        _audit_authority(request, "task.retry", ok=False, user_id=actor,
                         detail=f"{rid[:32]} unbound {task_id[:24]}")
        return JSONResponse({"ok": False, "error": "TASK_NOT_FOUND"}, status_code=404)

    res = default_orchestrator().retry_task(rid, task_id)
    _audit_authority(request, "task.retry", ok=True, user_id=actor,
                     detail=f"{rid[:32]} {task_id[:24]}")
    return res


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

    actor_id, allowed = _resolve_actor(request)
    if not allowed:
        # Authenticated is not authorised. Recorded either way: a refused
        # authority attempt is exactly the kind of thing an audit log is for.
        _audit_authority(request, "approval.denied_unauthorized", ok=False,
                         user_id=actor_id, detail=req.approval_id[:64])
        return JSONResponse({"ok": False, "error": "NOT_AUTHORIZED"}, status_code=403)

    st = default_orchestrator().store
    appr = st.get_approval(req.approval_id)
    if not appr:
        return JSONResponse({"ok": False, "error": "APPROVAL_NOT_FOUND"}, status_code=404)
    if appr.get("run_id") != rid:
        # Deliberately the same answer as a missing approval: this approval does
        # not exist *on this run*, and saying more would confirm it exists on
        # another one.
        return JSONResponse({"ok": False, "error": "APPROVAL_NOT_FOUND"}, status_code=404)

    # The real caller, not a hardcoded name: every approval used to audit as
    # "user:ajay" regardless of who resolved it.
    res = default_orchestrator().approve(rid, req.approval_id,
                                         approved=req.approved,
                                         actor=f"user:{actor_id}")
    _audit_authority(request, "approval.resolved", ok=True, user_id=actor_id,
                     detail=f"{res.get('status')} {req.approval_id[:32]}")
    return res


def _audit_authority(request, event: str, *, ok: bool, user_id: str, detail: str) -> None:
    """Durable audit for an authority decision, in the security store's own log.

    Identifiers and outcome only -- never the session token that authenticated
    the call, and never the approval's payload.
    """
    from saathi.security.store import get_store
    try:
        get_store().audit(
            event, ok=ok, user_id=user_id,
            ip=(request.client.host if request.client else ""),
            ua=request.headers.get("user-agent", "")[:160],
            detail=detail[:200],
        )
    except Exception:
        pass  # audit must never break the decision path


@router.get("/runs/{rid}/health")
def run_health(rid: str):
    st = default_orchestrator().store
    run = st.get_run(rid)
    if not run:
        return {"error": "not found"}
    return {"state": run["state"], "metrics": st.metrics(rid),
            "pending_approvals": len(st.pending_approvals(rid))}
