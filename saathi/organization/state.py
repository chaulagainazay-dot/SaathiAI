"""Real-state adapter: derives every role's visible status from existing runtimes.

Precedence per role (first match wins):
  1. ``requires`` unmet            → UNAVAILABLE / NOT CONNECTED (reason)
     requires uncheckable          → UNKNOWN (reason)
  2. active organization mission step for the role → that step's status
  3. M10 agent-runtime turn running for the bound/mapped runtime identity
     → busy status for the role's activity (stale records → WAITING + reason)
  4. M10 task pending in a fresh non-terminal run → ASSIGNED
  5. organization step finished within ``RECENT_SEC`` → COMPLETE /
     AWAITING_EVIDENCE / ERROR (with reason)
  6. otherwise IDLE (defined, not instantiated)
If a source cannot be read, roles depending on it are UNKNOWN — never IDLE.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from saathi.organization import dependencies as deps
from saathi.organization.charter import AGENT_RUNTIME_ROLE, load_charter
from saathi.organization.models import (
    ACTIVE_STATUSES, AgentStatus, BUSY_STATUS_BY_ACTIVITY, REVIEW_STATUSES,
)
from saathi.organization.store import default_store

RECENT_SEC = 15 * 60
STALE_SEC = 6 * 3600
_M10_TERMINAL = ("completed", "cancelled", "failed", "timed_out", "rolled_back",
                 "partially_completed")


def _m10_activity() -> dict:
    """Running agent turns + pending tasks from the M10 store (read-only)."""
    from saathi.agent_runtime.store import DB_PATH
    p = Path(DB_PATH)
    if not p.exists():
        return {"ok": True, "running": [], "pending": [], "note": "store not initialised"}
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=3)
    c.row_factory = sqlite3.Row
    try:
        running = [dict(r) for r in c.execute(
            "SELECT a.agent, a.run_id, a.created_at, r.objective, r.state AS run_state, r.updated_at "
            "FROM agent_run a JOIN orchestration_run r ON r.id=a.run_id WHERE a.state='running'")]
        ph = ",".join("?" * len(_M10_TERMINAL))
        pending = [dict(r) for r in c.execute(
            "SELECT t.agent, t.run_id, t.objective, r.updated_at FROM task t "
            f"JOIN orchestration_run r ON r.id=t.run_id WHERE t.status IN ('pending','ready') "
            f"AND r.state NOT IN ({ph})", _M10_TERMINAL)]
    finally:
        c.close()
    return {"ok": True, "running": running, "pending": pending}


def _runtime_role(agent_id: str) -> str | None:
    return AGENT_RUNTIME_ROLE.get(agent_id)


def role_states(now: float | None = None) -> tuple[dict, dict]:
    """Returns (states by role_id, source health)."""
    now = now or time.time()
    ch = load_charter()
    sources: dict[str, dict] = {}
    states: dict[str, dict] = {}

    # organization store
    try:
        steps = default_store().latest_step_per_role(since=now - RECENT_SEC)
        sources["organization"] = {"ok": True}
    except Exception as exc:
        steps, sources["organization"] = None, {"ok": False, "error": type(exc).__name__}

    # M10 runtime
    try:
        m10 = _m10_activity()
        sources["agent_runtime"] = {"ok": True, "running": len(m10["running"]),
                                    "pending_tasks": len(m10["pending"])}
    except Exception as exc:
        m10, sources["agent_runtime"] = None, {"ok": False, "error": type(exc).__name__}

    m10_running: dict[str, dict] = {}
    m10_pending: dict[str, dict] = {}
    stale_ignored = 0
    if m10:
        for r in m10["running"]:
            rid = _runtime_role(r["agent"])
            if rid:
                m10_running[rid] = r
        for t in m10["pending"]:
            rid = _runtime_role(t["agent"])
            if not rid:
                continue
            if now - float(t["updated_at"] or 0) > STALE_SEC:
                stale_ignored += 1
                continue
            m10_pending.setdefault(rid, t)
        sources["agent_runtime"]["stale_pending_ignored"] = stale_ignored

    req_keys = {k for r in ch.roles.values() for k in r.requires}
    req = deps.check_all(req_keys)

    for rid in ch.role_order:
        role = ch.roles[rid]
        st = {"status": AgentStatus.IDLE.value, "reason": "", "activity": None,
              "availability": "AVAILABLE"}
        # 1. requirements
        unmet = [(k, req[k]) for k in role.requires if req[k][0] != deps.AVAILABLE]
        if unmet:
            k, (state, reason) = unmet[0]
            st["availability"] = state
            st["status"] = (AgentStatus.UNKNOWN if state == deps.UNKNOWN
                            else AgentStatus.UNAVAILABLE).value
            st["reason"] = reason
            states[rid] = st
            continue
        # 2. organization mission
        step = (steps or {}).get(rid)
        if steps is None and role.binding.kind == "organization":
            st.update(status=AgentStatus.UNKNOWN.value, reason="Organization store unreadable")
            states[rid] = st
            continue
        if step and not step["finished_at"] and step["mission_status"] == "RUNNING":
            st.update(status=step["status"], reason=step["reason"],
                      activity=_activity(step, "organization"))
            states[rid] = st
            continue
        # 3/4. M10 runtime
        if role.binding.kind == "agent_runtime" or rid in AGENT_RUNTIME_ROLE.values():
            if m10 is None:
                st.update(status=AgentStatus.UNKNOWN.value, reason="Agent runtime store unreadable")
                states[rid] = st
                continue
            run = m10_running.get(rid)
            if run:
                age = now - float(run["updated_at"] or run["created_at"] or 0)
                if age > STALE_SEC:
                    st.update(status=AgentStatus.WAITING.value,
                              reason=f"Runtime record not updated for {age / 3600:.0f} h (possibly stale)")
                else:
                    st["status"] = BUSY_STATUS_BY_ACTIVITY[role.activity].value
                st["activity"] = {"source": "agent_runtime", "run_id": run["run_id"],
                                  "objective": run["objective"], "started_at": run["created_at"]}
                states[rid] = st
                continue
            task = m10_pending.get(rid)
            if task:
                st.update(status=AgentStatus.ASSIGNED.value,
                          activity={"source": "agent_runtime", "run_id": task["run_id"],
                                    "objective": task["objective"], "started_at": None})
                states[rid] = st
                continue
        # 5. recent organization outcome
        if step and step["finished_at"]:
            st.update(status=step["status"], reason=step["reason"],
                      activity=_activity(step, "organization"))
        states[rid] = st
    return states, sources


def _activity(step: dict, source: str) -> dict:
    return {"source": source, "mission_id": step["mission_id"], "mission_title": step.get("mission_title"),
            "step_id": step["id"], "objective": step["objective"], "started_at": step["started_at"],
            "finished_at": step["finished_at"] or None, "probe": step["probe"]}


def metrics(states: dict) -> dict:
    vals = [AgentStatus(s["status"]) for s in states.values()]
    return {
        "total": len(vals),
        "active": sum(v in ACTIVE_STATUSES for v in vals),
        "idle": sum(v == AgentStatus.IDLE for v in vals),
        "in_review": sum(v in REVIEW_STATUSES for v in vals),
        "waiting": sum(v in (AgentStatus.WAITING, AgentStatus.AWAITING_EVIDENCE) for v in vals),
        "blocked": sum(v == AgentStatus.BLOCKED for v in vals),
        "errors": sum(v == AgentStatus.ERROR for v in vals),
        "unavailable": sum(v in (AgentStatus.UNAVAILABLE, AgentStatus.OFFLINE) for v in vals),
        "unknown": sum(v == AgentStatus.UNKNOWN for v in vals),
        "complete_recent": sum(v == AgentStatus.COMPLETE for v in vals),
    }


def authority_chain_status() -> list[dict]:
    """Live posture of each deterministic authority system (read-only)."""
    ch = load_charter()
    out = []
    probes = {
        "portfolio_construction": _pc_status,
        "portfolio_risk": _risk_status,
        "trading_guardian": _tg_status,
        "approval": _approval_status,
        "execution_gateway": _gateway_status,
    }
    for s in ch.chain:
        try:
            status, detail = probes[s.system_id]()
        except Exception as exc:
            status, detail = "UNKNOWN", f"posture read failed: {type(exc).__name__}"
        out.append({"system_id": s.system_id, "name": s.name, "order": s.order,
                    "description": s.description, "deterministic": s.deterministic,
                    "status": status, "detail": detail})
    return out


def _pc_status():
    from saathi.platform.portfolio_construction.engine import PortfolioConstructionEngine  # noqa: F401
    return "ACTIVE", "Proposals only — never orders"


def _risk_status():
    from saathi.platform.portfolio_risk_engine.engine import PortfolioRiskEngine
    b = PortfolioRiskEngine().get_risk_budget()
    return "ACTIVE", f"{b['version']} · {b['environment']} · leverage {'on' if b['leverage_enabled'] else 'off'}"


def _tg_status():
    from saathi.platform.trading_guardian import safety_posture
    sp = safety_posture()
    return "ACTIVE", f"Live execution {sp['LIVE_EXECUTION']} · max target {sp['HIGHEST_PERMITTED_TARGET']}"


def _approval_status():
    from saathi.platform.models import PlatformPermission, ROLE_PERMISSIONS, PlatformRole
    deciders = [r.value for r in PlatformRole
                if PlatformPermission.APPROVAL_DECIDE in ROLE_PERMISSIONS.get(r, set())]
    return "ACTIVE", f"Decided by human roles only: {', '.join(deciders)}"


def _gateway_status():
    from saathi.tool_runtime.contracts import ToolAuthorityClass
    assert ToolAuthorityClass.FINANCIAL_EXECUTION  # prohibited class exists
    return "PAPER-ONLY", "Registered paper tools only · FINANCIAL_EXECUTION prohibited"


def today_focus(owner: str) -> dict:
    try:
        from saathi.ceo.store import default_store as ceo_store
        goals = ceo_store().list_goals(owner)
    except Exception as exc:
        return {"state": "UNKNOWN", "items": [], "reason": f"CEO store unreadable: {type(exc).__name__}"}
    items = [{"id": g["id"], "text": g.get("description") or "", "status": g.get("status"),
              "done": g.get("status") in ("done", "completed", "achieved")} for g in goals[:8]]
    return {"state": "OK" if items else "EMPTY", "items": items, "source": "ceo_os.goal"}


def recent_outputs(limit: int = 8) -> list[dict]:
    out = []
    try:
        for m in default_store().list_missions(limit=limit):
            if m["finished_at"]:
                out.append({"kind": "org_mission", "id": m["id"], "title": m["title"],
                            "status": m["status"], "at": m["finished_at"],
                            "summary": (m["report"] or {}).get("summary")})
    except Exception:
        pass
    try:
        from saathi.agent_runtime.store import DB_PATH
        p = Path(DB_PATH)
        if p.exists():
            c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=3)
            try:
                for r in c.execute("SELECT id,run_id,kind,name,created_at FROM artifact "
                                   "ORDER BY created_at DESC LIMIT ?", (limit,)):
                    out.append({"kind": "agent_artifact", "id": r[0], "run_id": r[1],
                                "title": r[3] or r[2], "status": r[2], "at": r[4], "summary": None})
            finally:
                c.close()
    except Exception:
        pass
    out.sort(key=lambda x: x["at"] or 0, reverse=True)
    return out[:limit]


def live_activity(limit: int = 12) -> list[dict]:
    ch = load_charter()
    try:
        evs = default_store().events(limit=limit * 3)
    except Exception:
        return []
    out = []
    for e in evs:
        if e["name"] not in ("agent.started", "agent.output_created", "mission.created",
                             "mission.completed", "decision.proposed", "agent.error"):
            continue
        r = ch.roles.get(e["role_id"])
        out.append({"id": e["id"], "name": e["name"], "role_id": e["role_id"] or None,
                    "role_name": r.name if r else "Saathi", "mission_id": e["mission_id"],
                    "at": e["created_at"]})
        if len(out) >= limit:
            break
    return out


def company_snapshot(owner: str = "ajay") -> dict:
    ch = load_charter()
    states, sources = role_states()
    roles = []
    for rid in ch.role_order:
        pub = ch.roles[rid].to_public()
        pub.update(states[rid])
        roles.append(pub)
    active_missions = []
    try:
        active_missions = default_store().active_missions()
    except Exception:
        pass
    return {
        "generated_at": time.time(),
        "owner": ch.owner,
        "departments": [vars(d) for d in ch.departments.values()],
        "floors": [{**vars(ch.floors[f]), "offices": [o.office_id for o in ch.offices_on(f)]}
                   for f in ch.floor_order],
        "offices": [{**vars(o), "members": [r.role_id for r in ch.members(o.office_id)]}
                    for o in (ch.offices[i] for i in ch.office_order)],
        "roles": roles,
        "metrics": metrics(states),
        "authority_chain": authority_chain_status(),
        "reasoning_chain": ["Specialists", "Desk synthesis", "Fund Manager",
                            "Investment Committee", "Decision synthesis"],
        "active_missions": active_missions,
        "today_focus": today_focus(owner),
        "recent_outputs": recent_outputs(),
        "live_activity": live_activity(),
        "sources": sources,
        "concurrency": {"max_org_missions": 1, "llm_inference_in_org_missions": False},
    }
