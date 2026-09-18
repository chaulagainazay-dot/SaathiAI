"""Organization missions — owner goal → Saathi → departments → specialists.

A mission is a declarative delegation tree. Each step is performed by a logical
role through a deterministic READ-ONLY probe (``saathi.organization.probes``).
The runner is bounded: at most ``MAX_CONCURRENT_MISSIONS`` (1) missions run at a
time, steps run sequentially in one background thread, and no model inference
is used. Every transition is persisted (``OrgStore``) and mirrored as a
minimal event on the canonical in-memory bus (``saathi.events.bus``) as
``org.<name>`` with ids/status only — the SSE stream is unauthenticated, so no
mission content is ever put on the bus.

Pacing: each step stays visibly busy for at least ``pacing_sec`` so the owner
can watch delegation. Pacing is recorded on the mission and disclosed in the UI;
it is presentation timing, not work.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field

from saathi.organization.charter import load_charter
from saathi.organization.models import (
    AgentStatus, BUSY_STATUS_BY_ACTIVITY, validate_status_transition,
)
from saathi.organization.probes import run_probe
from saathi.organization.store import OrgStore, default_store

MAX_CONCURRENT_MISSIONS = 1
_slots = threading.BoundedSemaphore(MAX_CONCURRENT_MISSIONS)


class MissionError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


@dataclass(frozen=True)
class Node:
    role_id: str
    objective: str
    probe: str
    children: tuple["Node", ...] = field(default_factory=tuple)


def N(role_id, objective, probe, *children) -> Node:
    return Node(role_id, objective, probe, tuple(children))


@dataclass(frozen=True)
class Template:
    template_id: str
    title: str
    objective: str
    keywords: tuple[str, ...]
    root: Node


TEMPLATES = {t.template_id: t for t in (
    Template(
        "portfolio_review", "Portfolio risk & opportunity review",
        "Analyze my portfolio and identify important risks and opportunities.",
        ("portfolio", "risk", "exposure", "allocation", "rebalance", "opportunit"),
        N("exec.saathi", "Decompose owner goal, delegate, report back", "saathi_report",
          N("inv.fund_manager", "Portfolio-level review across desks", "fund_manager_synthesis",
            N("pm.manager", "Read paper portfolio state", "paper_portfolio",
              N("pm.exposure", "Measure gross exposure vs budget", "exposure"),
              N("risk.concentration", "Measure concentration vs budget", "concentration")),
            N("crypto.lead", "Crypto desk view", "desk_digest",
              N("crypto.technical", "Check recorded crypto market data", "crypto_market_data")),
            N("nepse.lead", "NEPSE desk view", "desk_digest",
              N("nepse.technical", "NEPSE market snapshot", "nepse_market_snapshot"),
              N("nepse.company", "Governed research evidence", "governed_research")),
            N("risk.chief", "Risk review", "desk_digest",
              N("risk.portfolio", "Compare positions with PortfolioRisk budget", "risk_budget_check"),
              N("risk.stress", "Engine stress test", "stress_engine"),
              N("risk.challenger", "Challenge assumptions", "challenge_gaps"))),
          N("ic.chair", "Committee synthesis (proposal only)", "committee_synthesis",
            N("ic.skeptic", "Devil's advocate on data quality", "skeptic")),
          N("gov.compliance", "Verify paper-only posture", "compliance_posture")),
    ),
    Template(
        "nepse_swing_research", "NEPSE banking swing research",
        "Research NEPSE banking stocks for swing opportunities.",
        ("nepse", "bank", "swing", "stock", "share"),
        N("exec.saathi", "Decompose owner goal, delegate, report back", "saathi_report",
          N("nepse.lead", "Coordinate NEPSE specialists", "desk_digest",
            N("nepse.company", "Governed research evidence", "governed_research"),
            N("nepse.technical", "NEPSE market snapshot", "nepse_market_snapshot"),
            N("nepse.sector", "Isolate banking sector", "nepse_sector"),
            N("nepse.swing", "Swing setup screening", "nepse_swing")),
          N("research.source_verifier", "Verify source freshness", "source_freshness"),
          N("risk.chief", "Risk posture for any proposal", "guardian_posture"),
          N("ic.skeptic", "Devil's advocate on data quality", "skeptic")),
    ),
    Template(
        "company_health", "Company systems check",
        "Check the health of SaathiOS systems and evidence.",
        ("health", "system", "status", "check"),
        N("exec.saathi", "Delegate a systems check", "saathi_report",
          N("eng.monitoring", "Probe runtime systems", "system_health"),
          N("gov.audit", "Audit evidence service", "evidence_audit"),
          N("gov.compliance", "Verify paper-only posture", "compliance_posture")),
    ),
)}


def route_objective(text: str) -> Template:
    t = (text or "").lower()
    best, score = None, 0
    for tpl in TEMPLATES.values():
        s = sum(1 for k in tpl.keywords if k in t)
        if s > score:
            best, score = tpl, s
    if best is None:
        raise MissionError(
            "NO_TEMPLATE",
            "No organization mission template matches this goal. Available: "
            + "; ".join(f"{t.template_id} ({t.objective})" for t in TEMPLATES.values()))
    return best


def validate_templates() -> list[str]:
    """Every node's role exists, probe exists; the executor is never used."""
    from saathi.organization.probes import PROBES
    ch = load_charter()
    errs = []

    def walk(n: Node):
        if n.role_id not in ch.roles:
            errs.append(f"unknown role {n.role_id}")
        if n.probe not in PROBES:
            errs.append(f"unknown probe {n.probe}")
        for c in n.children:
            walk(c)
    for t in TEMPLATES.values():
        if t.root.role_id != "exec.saathi":
            errs.append(f"template {t.template_id} must be rooted at Saathi")
        walk(t.root)
    return errs


def _pacing() -> float:
    try:
        return max(0.0, min(float(os.environ.get("SAATHI_ORG_STEP_PACING_SEC", "1.2")), 5.0))
    except ValueError:
        return 1.2


def _publish(name: str, payload: dict) -> None:
    try:
        from saathi.events import bus
        bus.publish_sync(f"org.{name}", payload)
    except Exception:
        pass


class MissionRunner:
    def __init__(self, store: OrgStore | None = None, pacing_sec: float | None = None):
        self.store = store or default_store()
        self.pacing = _pacing() if pacing_sec is None else pacing_sec
        self.charter = load_charter()

    # ── lifecycle ─────────────────────────────────────────────────────────
    def create(self, *, objective: str, template_id: str = "", created_by: str,
               source: str = "company_view") -> dict:
        tpl = TEMPLATES.get(template_id) if template_id else route_objective(objective)
        if tpl is None:
            raise MissionError("UNKNOWN_TEMPLATE", f"Unknown template {template_id!r}")
        objective = (objective or tpl.objective).strip()[:500]
        mid = self.store.create_mission(template=tpl.template_id, title=tpl.title,
                                        objective=objective, created_by=created_by,
                                        source=source, pacing_sec=self.pacing)
        seq = [0]

        def add(node: Node, parent: str) -> None:
            sid = self.store.add_step(mid, parent_id=parent, seq=seq[0], role_id=node.role_id,
                                      objective=node.objective, probe=node.probe)
            seq[0] += 1
            for c in node.children:
                add(c, sid)
        add(tpl.root, "")
        self._event("mission.created", mid, detail={"template": tpl.template_id, "by": created_by})
        return self.store.get_mission(mid)

    def start_async(self, mid: str) -> None:
        if not _slots.acquire(blocking=False):
            self.store.set_mission(mid, status="BLOCKED",
                                   reason="Another organization mission is running (bounded to 1)")
            self._event("mission.blocked", mid, detail={"reason": "concurrency_limit"})
            raise MissionError("BUSY", "Another organization mission is running", 409)
        t = threading.Thread(target=self._run_guarded, args=(mid,), daemon=True,
                             name=f"org-mission-{mid}")
        t.start()

    def run_sync(self, mid: str) -> dict:
        """Test/CLI path: runs in the caller thread under the same slot."""
        if not _slots.acquire(blocking=False):
            raise MissionError("BUSY", "Another organization mission is running", 409)
        self._run_guarded(mid)
        return self.store.get_mission(mid)

    def _run_guarded(self, mid: str) -> None:
        try:
            self._run(mid)
        except Exception as exc:  # never leave a mission RUNNING
            self.store.set_mission(mid, status="FAILED", reason=f"{type(exc).__name__}: {exc}"[:300])
            self._event("mission.failed", mid, detail={"error": type(exc).__name__})
        finally:
            _slots.release()

    # ── execution ─────────────────────────────────────────────────────────
    def _run(self, mid: str) -> None:
        self.store.set_mission(mid, status="RUNNING")
        steps = self.store.steps(mid)
        by_parent: dict[str, list[dict]] = {}
        for s in steps:
            by_parent.setdefault(s["parent_id"], []).append(s)
        self._state: dict[str, AgentStatus] = {s["id"]: AgentStatus.ASSIGNED for s in steps}
        prior: list[dict] = []
        for s in steps:
            self._event("agent.assigned", mid, s)
        root = by_parent[""][0]
        self._exec(mid, root, by_parent, prior)
        outcomes = [p["output"].get("status") for p in prior]
        final = "COMPLETE" if all(o == "complete" for o in outcomes) else "COMPLETE_WITH_GAPS"
        root_out = next((p["output"] for p in prior if p["step_id"] == root["id"]), {})
        chair = next((p["output"] for p in prior if p["role_id"] == "ic.chair"), None)
        report = {"summary": root_out.get("summary"), "gaps": root_out.get("gaps", []),
                  "decision_proposal": (chair or {}).get("data"),
                  "steps": len(prior), "llm_used": False, "pacing_sec": self.pacing,
                  "authorizes_execution": False}
        self.store.set_mission(mid, status=final, report=report)
        self._event("mission.completed", mid, detail={"status": final})

    def _transition(self, mid: str, step: dict, dst: AgentStatus, reason: str = "",
                    **kw) -> None:
        src = self._state[step["id"]]
        validate_status_transition(src, dst)
        self._state[step["id"]] = dst
        self.store.set_step(step["id"], status=dst.value, reason=reason, **kw)
        self._event("agent.status_changed", mid, step, detail={"status": dst.value})

    def _exec(self, mid: str, step: dict, by_parent: dict, prior: list[dict]) -> dict:
        role = self.charter.roles[step["role_id"]]
        busy = BUSY_STATUS_BY_ACTIVITY[role.activity]
        kids = by_parent.get(step["id"], [])
        self._transition(mid, step, busy, started=True)
        self._event("agent.started", mid, step)
        child_outputs = []
        if kids:
            for k in kids:
                self._event("mission.delegated", mid, step,
                            detail={"to_role": k["role_id"], "to_step": k["id"]})
            time.sleep(self.pacing / 2)
            self._transition(mid, step, AgentStatus.WAITING, reason="Waiting on delegated work")
            for k in kids:
                child_outputs.append(self._exec(mid, k, by_parent, prior))
            self._transition(mid, step, busy)
        if role.activity.value == "challenge":
            self._event("challenge.created", mid, step)
        elif role.activity.value == "review":
            self._event("review.started", mid, step)
        t0 = time.time()
        out = run_probe(step["probe"], {"children": child_outputs, "prior": list(prior),
                                        "mission_id": mid})
        left = self.pacing - (time.time() - t0)
        if left > 0:
            time.sleep(left)
        status = {"complete": AgentStatus.COMPLETE,
                  "awaiting_evidence": AgentStatus.AWAITING_EVIDENCE}.get(out["status"], AgentStatus.ERROR)
        reason = "; ".join(out.get("gaps", [])[:2]) if status != AgentStatus.COMPLETE else ""
        for ev in out.get("evidence", []):
            self._event("evidence.added", mid, step, detail={"source": ev.get("source")})
        self._transition(mid, step, status, reason=reason[:300], output=out,
                         evidence=out.get("evidence", []), finished=True)
        self._event("agent.output_created", mid, step)
        if step["role_id"] == "ic.chair":
            self._event("decision.proposed", mid, step)
        if status == AgentStatus.ERROR:
            self._event("agent.error", mid, step)
        rec = {"step_id": step["id"], "role_id": role.role_id, "role_name": role.name, "output": out}
        prior.append(rec)
        return rec

    def _event(self, name: str, mid: str, step: dict | None = None, detail: dict | None = None):
        sid = step["id"] if step else ""
        rid = step["role_id"] if step else ""
        self.store.event(name, mission_id=mid, step_id=sid, role_id=rid, detail=detail or {})
        payload = {"mission_id": mid, "step_id": sid or None, "role_id": rid or None}
        if detail and "status" in detail:
            payload["status"] = detail["status"]
        _publish(name, payload)


def delegation_tree(store: OrgStore, mid: str) -> dict | None:
    m = store.get_mission(mid)
    if not m:
        return None
    ch = load_charter()
    steps = store.steps(mid)
    nodes = {s["id"]: {**_public_step(s, ch), "children": []} for s in steps}
    root = None
    for s in steps:
        if s["parent_id"] and s["parent_id"] in nodes:
            nodes[s["parent_id"]]["children"].append(nodes[s["id"]])
        elif not s["parent_id"]:
            root = nodes[s["id"]]
    owner = {"step_id": None, "role_id": "owner", "name": ch.owner["name"],
             "office_id": "owner", "status": "COMPLETE" if m["status"] != "RUNNING" else "WAITING",
             "objective": m["objective"], "children": [root] if root else []}
    return {"mission": m, "tree": owner}


def _public_step(s: dict, ch) -> dict:
    r = ch.roles.get(s["role_id"])
    return {"step_id": s["id"], "role_id": s["role_id"], "name": r.name if r else s["role_id"],
            "office_id": r.office_id if r else "", "objective": s["objective"],
            "status": s["status"], "reason": s["reason"], "probe": s["probe"],
            "started_at": s["started_at"], "finished_at": s["finished_at"],
            "output": s["output"], "evidence": s["evidence"]}
