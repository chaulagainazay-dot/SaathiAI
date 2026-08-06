"""M17.13 autonomous mission engine — ONE business objective, delegated down.

A Mission is ABOVE the pipeline. The hierarchy is:

    Mission → Pipeline → Harness Step → Adapter → Verification → Ledger

A Mission NEVER executes a tool directly. It NEVER knows how to drive FFmpeg,
SQLite, jq, zip, a shell, a browser, or anything else. It carries one business
objective (create today's IELTS lesson, produce the daily CEO brief, run the
kitchen inventory audit …), strongly-typed validated parameters, an approval
requirement, and a reference to a reusable TEMPLATE. To execute, it delegates to
the existing M17.12 `PipelineRunner`, which composes the existing governed
`run_harness_action` per step (ownership → trust → risk/approval → the sole
adapter → INDEPENDENT verification → durable ledger). The engine only sequences
the mission lifecycle and records it durably; it adds NO second execution engine,
trust model, DB, scheduler, or approval path.

Fail-closed guarantees:
- a mission `completed` ONLY if its delegated pipeline succeeded end to end; any
  pipeline failure, approval denial, owner mismatch, unknown template, or thrown
  exception drives the mission to `failed`/`blocked`. No partial success.
- owner isolation: run/inspect/cancel are owner-checked; a mismatch is rejected
  and never executes.
- approval gates are honoured: an approval-required mission cannot be queued
  until it is explicitly approved (no silent elevation). The per-step risk gate
  inside `run_harness_action` still applies independently underneath.
- terminal mission states are immutable; a failed mission is not resurrected —
  `retry` produces a NEW mission instance (auditable, correlated to its parent).

Templates are declared in TRUSTED Python (like the pilots and pipeline steps) and
produce Mission instances. Parsing untrusted mission spec JSON, event-driven
triggers, and auto-scheduling of recurring occurrences are deliberately out of
scope for this milestone (the engine supports instance-per-occurrence; wiring a
live scheduler is deferred, mirroring M17.11's opt-in stance).
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from saathi.application_harness.pipeline import (
    PipelineRunner, PipelineSpec, PipelineStep,
)
from saathi.application_harness import run_ledger as L
from saathi.application_harness.run_ledger import (
    RunLedger, default_ledger,
    MISSION_DRAFT, MISSION_APPROVAL_REQUIRED, MISSION_APPROVED, MISSION_QUEUED,
    MISSION_RUNNING, MISSION_COMPLETED, MISSION_FAILED, MISSION_BLOCKED,
    MISSION_TERMINAL,
)

# recognised mission triggers / types — additive; new kinds append, never rewrite
MISSION_TYPES = ("manual", "scheduled", "triggered", "recurring", "one_time")
_PARAM_TYPES = ("str", "int", "float", "bool", "enum")


@dataclass(frozen=True)
class MissionParameter:
    """One strongly-typed mission input, validated BEFORE any execution."""
    name: str
    type: str = "str"
    required: bool = True
    choices: tuple = ()
    default: Any = None


@dataclass(frozen=True)
class MissionTemplate:
    """A reusable mission blueprint. `build_steps(params)` returns the trusted
    pipeline steps for a validated parameter set — the ONLY place a mission is
    connected to concrete harness operations."""
    template_id: str
    title: str
    objective: str = ""
    mission_type: str = "manual"
    trigger: str = "manual"
    priority: str = "normal"
    risk: int = 0
    approval_required: bool = False
    schedule: str = ""
    parameters: tuple = ()
    build_steps: Callable = None          # (dict) -> list[PipelineStep]  (sequential)
    build_graph: Callable = None          # (dict) -> list[GraphStep]  (M17.16 graph)
    concurrency_limit: int = 4            # bounded local concurrency for a graph


def validate_params(parameters, values: dict) -> dict:
    """Strongly-typed validation of mission inputs. Returns
    {"ok": bool, "values": {...}} or {"ok": False, "errors": [...]}. Unknown keys
    are rejected (fail closed); required keys must be present; types are coerced
    strictly; enum values must be within `choices`."""
    values = values or {}
    errors: list[str] = []
    cleaned: dict[str, Any] = {}
    declared = {p.name for p in parameters}
    for k in values:
        if k not in declared:
            errors.append(f"unknown_parameter:{k}")
    for p in parameters:
        present = p.name in values
        if not present:
            if p.required and p.default is None:
                errors.append(f"missing_required:{p.name}")
            elif p.default is not None:
                cleaned[p.name] = p.default
            continue
        raw = values[p.name]
        coerced, err = _coerce(p, raw)
        if err:
            errors.append(err)
        else:
            cleaned[p.name] = coerced
    if errors:
        return {"ok": False, "errors": errors}
    return {"ok": True, "values": cleaned}


def _coerce(p: MissionParameter, raw):
    try:
        if p.type == "int":
            if isinstance(raw, bool):
                return None, f"bad_type:{p.name}:expected_int"
            return int(raw), None
        if p.type == "float":
            if isinstance(raw, bool):
                return None, f"bad_type:{p.name}:expected_float"
            return float(raw), None
        if p.type == "bool":
            if isinstance(raw, bool):
                return raw, None
            return None, f"bad_type:{p.name}:expected_bool"
        if p.type == "enum":
            s = str(raw)
            if p.choices and s not in p.choices:
                return None, f"bad_enum:{p.name}:{s}"
            return s, None
        # default: str
        return str(raw), None
    except (ValueError, TypeError):
        return None, f"bad_type:{p.name}:expected_{p.type}"


class MissionEngine:
    """Creates, gates, and executes missions by delegating to the pipeline.

    Deterministic: no LLM in any lifecycle decision. Injectable ledger + pipeline
    runner + template registry make it fully testable without a server."""

    def __init__(self, *, ledger: RunLedger | None = None, templates=None,
                 pipeline_runner: PipelineRunner | None = None,
                 graph_runner=None, runs_root: str | None = None):
        self.ledger = ledger or default_ledger()
        self.templates: dict[str, MissionTemplate] = dict(templates
                                                          or _default_templates())
        self.runner = pipeline_runner or PipelineRunner(ledger=self.ledger,
                                                        runs_root=runs_root)
        # M17.16: a graph mission is launched through the SAME PipelineRunner,
        # wrapped by the bounded dependency-aware executor (one engine, no 2nd path).
        if graph_runner is None:
            from saathi.application_harness.pipeline_graph import GraphPipelineRunner
            graph_runner = GraphPipelineRunner(ledger=self.ledger, runner=self.runner)
        self.graph_runner = graph_runner

    # ── creation (templates produce instances) ─────────────────────────────
    def create(self, template_id: str, *, owner: str, params: dict | None = None,
               mission_id: str = "", correlation_id: str = "") -> dict:
        tmpl = self.templates.get(template_id)
        if tmpl is None:
            return {"ok": False, "reason": "unknown_template"}
        if not owner:
            return {"ok": False, "reason": "empty_owner"}
        v = validate_params(tmpl.parameters, params or {})
        if not v["ok"]:
            return {"ok": False, "reason": "invalid_parameters", "errors": v["errors"]}
        mid = mission_id or ("ms_" + uuid.uuid4().hex[:16])
        created = self.ledger.create_mission(
            mid, owner=owner, title=tmpl.title, objective=tmpl.objective,
            mission_type=tmpl.mission_type, trigger=tmpl.trigger,
            priority=tmpl.priority, risk=tmpl.risk,
            approval_required=tmpl.approval_required, template=template_id,
            params=v["values"], schedule=tmpl.schedule,
            correlation_id=correlation_id)
        if not created.get("created"):
            return {"ok": False, "mission_id": mid, "reason": created.get("reason")}
        return {"ok": True, "mission_id": mid, "state": MISSION_DRAFT}

    # ── lifecycle gates ────────────────────────────────────────────────────
    def approve(self, mission_id: str, *, owner: str, approver: str) -> dict:
        m = self._owned(mission_id, owner)
        if not m["ok"]:
            return m
        res = self.ledger.approve_mission(mission_id, approver=approver)
        return {"ok": bool(res.get("ok")), **res}

    def enqueue(self, mission_id: str, *, owner: str) -> dict:
        """draft/approved → queued. An approval-required mission that is not yet
        approved is moved to `approval_required` and NOT queued (no elevation)."""
        m = self._owned(mission_id, owner)
        if not m["ok"]:
            return m
        mission = m["mission"]
        state = mission["state"]
        if state == MISSION_QUEUED:
            return {"ok": True, "noop": True, "state": MISSION_QUEUED}
        if mission["approval_required"] and state != MISSION_APPROVED:
            self.ledger.mark_mission_approval_required(mission_id)
            return {"ok": False, "reason": "approval_required",
                    "state": MISSION_APPROVAL_REQUIRED}
        if state == MISSION_DRAFT:                       # no-approval mission: auto
            self.ledger.approve_mission(mission_id, approver="auto")
        res = self.ledger.enqueue_mission(mission_id)
        return {"ok": bool(res.get("ok")), **res}

    def cancel(self, mission_id: str, *, owner: str, requester: str = "") -> dict:
        m = self._owned(mission_id, owner)
        if not m["ok"]:
            return m
        return self.ledger.cancel_mission(mission_id, requester=requester or owner)

    def block(self, mission_id: str, *, owner: str, reason: str = "") -> dict:
        m = self._owned(mission_id, owner)
        if not m["ok"]:
            return m
        return self.ledger.block_mission(mission_id, reason=reason)

    # ── execution: delegate ONE governed pipeline (fail-closed) ────────────
    def run(self, mission_id: str, *, owner: str, session_id: str = "mission") -> dict:
        m = self._owned(mission_id, owner)
        if not m["ok"]:
            return m
        mission = m["mission"]
        if mission["state"] != MISSION_QUEUED:
            return {"ok": False, "reason": f"not_queued:{mission['state']}"}
        tmpl = self.templates.get(mission["template"])
        if tmpl is None or (tmpl.build_steps is None and tmpl.build_graph is None):
            self.ledger.begin_mission_run(mission_id)
            self.ledger.finish_mission_run(mission_id, attempt=mission["run_count"] + 1,
                                           state=MISSION_FAILED,
                                           failure_code="MISSION_TEMPLATE_MISSING")
            return {"ok": False, "state": MISSION_FAILED,
                    "failure_code": "MISSION_TEMPLATE_MISSING"}
        begun = self.ledger.begin_mission_run(mission_id)
        if not begun.get("ok"):
            return {"ok": False, "reason": begun.get("reason")}
        attempt = begun["attempt"]
        try:
            if tmpl.build_graph is not None:            # M17.16 bounded graph mission
                from saathi.application_harness.pipeline_graph import GraphSpec, GraphStep
                gsteps = tmpl.build_graph(dict(mission["params"]))
                if not gsteps or not all(isinstance(s, GraphStep) for s in gsteps):
                    raise ValueError("template produced no valid graph steps")
                gspec = GraphSpec(name=mission["title"], owner=owner, steps=gsteps,
                                  concurrency_limit=tmpl.concurrency_limit,
                                  correlation_id=mission_id)
                pres = self.graph_runner.run(gspec, session_id=session_id)
            else:
                steps = tmpl.build_steps(dict(mission["params"]))
                if not steps or not all(isinstance(s, PipelineStep) for s in steps):
                    raise ValueError("template produced no valid pipeline steps")
                spec = PipelineSpec(name=mission["title"], owner=owner, steps=steps,
                                    correlation_id=mission_id)
                pres = self.runner.run(spec, session_id=session_id)
        except Exception as e:                          # any exception → fail closed
            self.ledger.finish_mission_run(
                mission_id, attempt=attempt, state=MISSION_FAILED,
                failure_code=f"MISSION_EXCEPTION:{type(e).__name__}")
            return {"ok": False, "state": MISSION_FAILED,
                    "failure_code": f"MISSION_EXCEPTION:{type(e).__name__}"}
        if pres.get("ok"):
            self.ledger.finish_mission_run(
                mission_id, attempt=attempt, state=MISSION_COMPLETED,
                pipeline_id=pres["pipeline_id"], steps_run=pres.get("steps_run", 0))
            return {"ok": True, "state": MISSION_COMPLETED,
                    "mission_id": mission_id, "pipeline_id": pres["pipeline_id"]}
        code = pres.get("failure_code") or pres.get("reason") or "PIPELINE_FAILED"
        pid = pres.get("pipeline_id", "")
        state = MISSION_FAILED
        if tmpl.build_graph is not None:            # M17.17 honest graph→mission map
            disp = self._classify_graph_failure(pid, owner, code)
            state, code = disp["state"], disp["failure_code"]
        self.ledger.finish_mission_run(
            mission_id, attempt=attempt, state=state,
            pipeline_id=pid, failure_code=code, steps_run=pres.get("steps_run", 0))
        return {"ok": False, "state": state, "mission_id": mission_id,
                "pipeline_id": pid, "failure_code": code}

    def launch(self, mission_id: str, *, owner: str, session_id: str = "mission") -> dict:
        """Convenience: enqueue (auto-approving a no-approval mission) then run.
        An approval-required mission stops at `approval_required` (never elevated)."""
        eq = self.enqueue(mission_id, owner=owner)
        if not eq.get("ok"):
            return eq
        return self.run(mission_id, owner=owner, session_id=session_id)

    def retry(self, mission_id: str, *, owner: str) -> dict:
        """Only a FAILED mission may be retried, and retry produces a NEW mission
        instance (terminal states are immutable). The clone is correlated to its
        parent for audit. Retrying any non-failed mission is rejected."""
        m = self._owned(mission_id, owner)
        if not m["ok"]:
            return m
        mission = m["mission"]
        if mission["state"] != MISSION_FAILED:
            return {"ok": False, "reason": f"retry_rejected:{mission['state']}"}
        res = self.create(mission["template"], owner=owner, params=mission["params"],
                          correlation_id=mission_id)
        if res.get("ok"):
            res["retried_from"] = mission_id
        return res

    # ── M17.17 graph mission recovery integration (still mission authority) ──
    def _classify_graph_failure(self, pipeline_id: str, owner: str, code: str) -> dict:
        """Map a FAILED graph pipeline into an honest mission disposition. Approval
        and stop-uncertain graphs are fail-closed BLOCKED (never silently `failed`),
        so the scheduler occurrence can propagate `approval_required` / attention.
        A plain transient/other failure stays `failed` (auto-recoverable upstream)."""
        up = (code or "").upper()
        bstates: set = set()
        try:
            g = self.ledger.inspect_graph(pipeline_id, owner=owner) if pipeline_id else None
            bstates = {b["state"] for b in (g or {}).get("branches", [])}
        except Exception:
            g = None
        if L.BRANCH_APPROVAL_REQUIRED in bstates or "APPROVAL" in up:
            return {"state": MISSION_BLOCKED, "failure_code": "GRAPH_APPROVAL_REQUIRED"}
        if (L.BRANCH_STOP_UNCERTAIN in bstates or "UNCERTAIN" in up
                or "VERIFICATION" in up):
            return {"state": MISSION_BLOCKED, "failure_code": "GRAPH_STOP_UNCERTAIN"}
        if L.BRANCH_BLOCKED in bstates:
            return {"state": MISSION_BLOCKED, "failure_code": code or "GRAPH_BLOCKED"}
        return {"state": MISSION_FAILED, "failure_code": code or "GRAPH_FAILED"}

    def _recovered_mission_id(self, mission_id: str) -> str:
        # DETERMINISTIC linked-retry id: repeated recovery of the same failed graph
        # mission maps to the SAME recovered mission (idempotent; no duplicate run).
        return "ms_rec_" + hashlib.sha256(mission_id.encode()).hexdigest()[:20]

    def settle_recovered(self, mission_id: str, *, owner: str, pipeline_id: str,
                         ok: bool, failure_code: str = "", steps_run: int = 0,
                         session_id: str = "graph_recovery") -> dict:
        """Bind an ALREADY-resumed graph pipeline result to a fresh mission instance
        and finalize it through the normal mission lifecycle WITHOUT launching a
        second graph (the graph was resumed in place by the recovery layer). Mission
        stays the authority for its own state; idempotent on a terminal mission.

        Concurrent settlers: only one begins the mission run. Losers reload the
        authoritative terminal state (or report in_progress) instead of inventing
        a second failure."""
        m = self._owned(mission_id, owner)
        if not m["ok"]:
            return m
        mission = m["mission"]
        if mission["state"] in MISSION_TERMINAL:        # already settled — idempotent
            return {"ok": mission["state"] == MISSION_COMPLETED,
                    "state": mission["state"], "mission_id": mission_id,
                    "idempotent": True}
        eq = self.enqueue(mission_id, owner=owner)      # draft/approved → queued
        if not eq.get("ok"):
            # Peer may have already advanced the lifecycle — reload.
            cur = self.ledger.inspect_mission(mission_id, owner=owner)
            if cur and cur["state"] in MISSION_TERMINAL:
                return {"ok": cur["state"] == MISSION_COMPLETED, "state": cur["state"],
                        "mission_id": mission_id, "idempotent": True}
            if cur and cur["state"] == MISSION_RUNNING:
                return {"ok": False, "reason": "settle_in_progress",
                        "mission_id": mission_id, "in_progress": True}
            return eq
        begun = self.ledger.begin_mission_run(mission_id)
        if not begun.get("ok"):
            cur = self.ledger.inspect_mission(mission_id, owner=owner)
            if cur and cur["state"] in MISSION_TERMINAL:
                return {"ok": cur["state"] == MISSION_COMPLETED, "state": cur["state"],
                        "mission_id": mission_id, "idempotent": True}
            if cur and cur["state"] == MISSION_RUNNING:
                return {"ok": False, "reason": "settle_in_progress",
                        "mission_id": mission_id, "in_progress": True}
            return {"ok": False, "reason": begun.get("reason")}
        attempt = begun["attempt"]
        if ok:
            self.ledger.finish_mission_run(mission_id, attempt=attempt,
                                           state=MISSION_COMPLETED,
                                           pipeline_id=pipeline_id, steps_run=steps_run)
            return {"ok": True, "state": MISSION_COMPLETED, "mission_id": mission_id,
                    "pipeline_id": pipeline_id}
        disp = self._classify_graph_failure(pipeline_id, owner, failure_code)
        self.ledger.finish_mission_run(mission_id, attempt=attempt, state=disp["state"],
                                       pipeline_id=pipeline_id,
                                       failure_code=disp["failure_code"],
                                       steps_run=steps_run)
        return {"ok": False, "state": disp["state"], "mission_id": mission_id,
                "pipeline_id": pipeline_id, "failure_code": disp["failure_code"]}

    def _resume_in_progress_result(self, mission_id: str, rec_id: str, pid: str) -> dict:
        """Concurrent recovery lost the claim or observed a mid-flight graph.

        Never settles the linked recovered mission as failed from a stale read —
        that races the winner into a permanent false terminal failure. Reload the
        recovered mission if the winner already finished; otherwise report
        in_progress so the caller leaves the occurrence recoverable.
        """
        existing = self.ledger.inspect_mission(rec_id, owner=None)
        if existing and existing["state"] in MISSION_TERMINAL:
            return {"ok": existing["state"] == MISSION_COMPLETED, "mission_id": rec_id,
                    "state": existing["state"], "pipeline_id": pid,
                    "retried_from": mission_id, "idempotent": True,
                    "converged": True}
        return {"ok": False, "reason": "resume_in_progress", "mission_id": rec_id,
                "retried_from": mission_id, "pipeline_id": pid, "in_progress": True}

    def _settle_linked_recovery(self, *, mission_id: str, rec_id: str, owner: str,
                                pid: str, graph_ok: bool, failure_code: str = "",
                                rres: dict | None = None,
                                session_id: str = "graph_recovery",
                                converged: bool = False) -> dict:
        """Create/settle the deterministic recovered mission from an authoritative
        terminal graph reading. Idempotent when another worker already settled it."""
        rres = rres or {}
        mission = self.ledger.inspect_mission(mission_id, owner=owner) or {}
        tmpl_id = mission.get("template") or ""
        params = dict(mission.get("params") or {})
        self.create(tmpl_id, owner=owner, params=params,
                    mission_id=rec_id, correlation_id=mission_id)
        settle = self.settle_recovered(rec_id, owner=owner, pipeline_id=pid,
                                       ok=graph_ok, failure_code=failure_code,
                                       steps_run=rres.get("rerun_steps", 0),
                                       session_id=session_id)
        if settle.get("in_progress"):
            return self._resume_in_progress_result(mission_id, rec_id, pid)
        # If we raced another settler, reload authoritative recovered state.
        existing = self.ledger.inspect_mission(rec_id, owner=owner)
        if existing and existing["state"] in MISSION_TERMINAL:
            return {"ok": existing["state"] == MISSION_COMPLETED,
                    "mission_id": rec_id, "retried_from": mission_id,
                    "pipeline_id": pid, "state": existing["state"],
                    "reused_steps": rres.get("reused_steps", 0),
                    "rerun_steps": rres.get("rerun_steps", 0),
                    "resume_reason": rres.get("reason", ""),
                    "failure_code": existing.get("failure_code", ""),
                    "idempotent": bool(settle.get("idempotent")),
                    "converged": converged or bool(settle.get("idempotent"))}
        return {"ok": bool(settle.get("ok")) and graph_ok,
                "mission_id": rec_id, "retried_from": mission_id,
                "pipeline_id": pid, "state": settle.get("state"),
                "reused_steps": rres.get("reused_steps", 0),
                "rerun_steps": rres.get("rerun_steps", 0),
                "resume_reason": rres.get("reason", ""),
                "failure_code": settle.get("failure_code", ""),
                "converged": converged, "idempotent": bool(settle.get("idempotent"))}

    def resume_graph_mission(self, mission_id: str, *, owner: str,
                             session_id: str = "graph_recovery", now=None) -> dict:
        """Recover a FAILED graph mission by resuming its EXISTING graph pipeline
        through the existing graph recovery interface (reusing valid checkpoints,
        rerunning only the interrupted branch, running the join once), then recording
        the outcome on a DETERMINISTIC linked-retry mission. The original failed
        mission stays immutable. Fully idempotent — repeated calls settle to the same
        recovered mission and never duplicate a branch, join, or mission run.

        Concurrent callers: at most one wins the recovery claim and runs the resume.
        Losers either converge on the winner's terminal recovered mission or return
        `in_progress` — they never invent a terminal failure from a mid-flight graph
        (`not_resumable:running`) or an active recovery claim."""
        m = self._owned(mission_id, owner)
        if not m["ok"]:
            return m
        mission = m["mission"]
        tmpl = self.templates.get(mission["template"])
        if tmpl is None or tmpl.build_graph is None:
            return {"ok": False, "reason": "not_graph_mission"}
        if mission["state"] != MISSION_FAILED:
            return {"ok": False, "reason": f"not_recoverable:{mission['state']}"}
        pid = mission.get("last_pipeline_id") or ""
        if not pid:
            return {"ok": False, "reason": "no_graph_pipeline"}
        rec_id = self._recovered_mission_id(mission_id)
        existing = self.ledger.inspect_mission(rec_id, owner=owner)
        if existing and existing["state"] in MISSION_TERMINAL:   # already recovered
            return {"ok": existing["state"] == MISSION_COMPLETED, "mission_id": rec_id,
                    "state": existing["state"], "pipeline_id": pid,
                    "retried_from": mission_id, "idempotent": True}
        from saathi.application_harness.pipeline_graph import GraphSpec
        gspec = GraphSpec(name=mission["title"], owner=owner,
                          steps=tmpl.build_graph(dict(mission["params"])),
                          concurrency_limit=tmpl.concurrency_limit,
                          correlation_id=mission_id, pipeline_id=pid)
        rres = self.graph_runner.resume(gspec, owner=owner, session_id=session_id,
                                        now=now)
        # Authoritative graph read AFTER resume attempt (winner or loser).
        g = self.ledger.inspect_graph(pid, owner=owner)
        gstate = (g or {}).get("state", "")
        gcode = (g or {}).get("failure_code", "") or rres.get("failure_code", "")

        if not rres.get("ok"):
            reason = rres.get("reason", "")
            # Contention / mid-flight: claim held, or pipeline not FAILED because
            # the winner reopened it (running) or already finished (succeeded).
            contending = (
                reason == "recovery_claimed"
                or reason.startswith("not_resumable:")
            )
            if contending:
                if gstate == L.PIPELINE_SUCCEEDED:
                    # Winner finished the graph — converge on the same recovered mission.
                    return self._settle_linked_recovery(
                        mission_id=mission_id, rec_id=rec_id, owner=owner, pid=pid,
                        graph_ok=True, failure_code="", rres=rres,
                        session_id=session_id, converged=True)
                # Still mid-flight or graph still failed while another worker holds
                # the claim — do NOT settle a failed recovered mission from this.
                return self._resume_in_progress_result(mission_id, rec_id, pid)
            # Definitive non-contention failure (graph invalid, owner mismatch, …)
            if gstate == L.PIPELINE_SUCCEEDED:
                return self._settle_linked_recovery(
                    mission_id=mission_id, rec_id=rec_id, owner=owner, pid=pid,
                    graph_ok=True, failure_code="", rres=rres, session_id=session_id,
                    converged=True)
            if gstate == L.PIPELINE_RUNNING:
                return self._resume_in_progress_result(mission_id, rec_id, pid)
            # Own resume attempt failed with a terminal-failed graph.
            return self._settle_linked_recovery(
                mission_id=mission_id, rec_id=rec_id, owner=owner, pid=pid,
                graph_ok=False, failure_code=gcode, rres=rres, session_id=session_id)

        # We won the resume claim and the runner returned. Graph terminal is authority.
        graph_ok = gstate == L.PIPELINE_SUCCEEDED
        return self._settle_linked_recovery(
            mission_id=mission_id, rec_id=rec_id, owner=owner, pid=pid,
            graph_ok=graph_ok, failure_code=gcode, rres=rres, session_id=session_id)

    def reconcile_running_mission(self, mission_id: str, *, owner: str) -> dict:
        """Crash window F: a mission left RUNNING while its graph pipeline already
        reached a terminal state (the process died between graph completion and
        `finish_mission_run`). Settle the mission from the authoritative graph state.
        No tool executes; idempotent on an already-terminal mission."""
        m = self._owned(mission_id, owner)
        if not m["ok"]:
            return m
        mission = m["mission"]
        if mission["state"] in MISSION_TERMINAL:
            return {"ok": mission["state"] == MISSION_COMPLETED,
                    "state": mission["state"], "idempotent": True}
        if mission["state"] != MISSION_RUNNING:
            return {"ok": False, "reason": f"not_running:{mission['state']}"}
        pid = mission.get("last_pipeline_id") or ""
        if not pid:                                     # never written pre-crash
            runs = self.ledger.pipelines_for_correlation(mission_id, owner=owner)
            pid = runs[0]["pipeline_id"] if runs else ""
        if not pid:
            return {"ok": False, "reason": "no_pipeline"}
        g = self.ledger.inspect_graph(pid, owner=owner)
        if g is None or g["state"] not in L.PIPELINE_TERMINAL:
            return {"ok": False, "reason": "graph_not_terminal"}
        attempt = int(mission["run_count"]) or 1
        if g["state"] == L.PIPELINE_SUCCEEDED:
            self.ledger.finish_mission_run(mission_id, attempt=attempt,
                                           state=MISSION_COMPLETED, pipeline_id=pid)
            return {"ok": True, "state": MISSION_COMPLETED, "mission_id": mission_id,
                    "pipeline_id": pid}
        disp = self._classify_graph_failure(pid, owner, g.get("failure_code", ""))
        self.ledger.finish_mission_run(mission_id, attempt=attempt, state=disp["state"],
                                       pipeline_id=pid, failure_code=disp["failure_code"])
        return {"ok": False, "state": disp["state"], "mission_id": mission_id,
                "pipeline_id": pid, "failure_code": disp["failure_code"]}

    # ── owner-safe reads ───────────────────────────────────────────────────
    def inspect(self, mission_id: str, *, owner: str | None = None) -> Optional[dict]:
        return self.ledger.inspect_mission(mission_id, owner=owner)

    def list(self, owner: str | None = None, *, limit: int = 100) -> list[dict]:
        return self.ledger.list_missions(owner, limit=limit)

    def history(self, mission_id: str, *, owner: str | None = None) -> list[dict]:
        return self.ledger.mission_history(mission_id, owner=owner)

    def health(self, owner: str | None = None) -> dict:
        return self.ledger.mission_health(owner)

    # ── internal ───────────────────────────────────────────────────────────
    def _owned(self, mission_id: str, owner: str) -> dict:
        """Fail-closed owner check. Returns {"ok": True, "mission": <safe dict>} or
        an owner-safe rejection."""
        if not owner:
            return {"ok": False, "reason": "empty_owner"}
        mission = self.ledger.inspect_mission(mission_id)      # raw (no owner arg)
        if mission is None:
            return {"ok": False, "reason": "unknown_mission"}
        if mission["owner"] != owner:
            return {"ok": False, "reason": "owner_mismatch"}
        return {"ok": True, "mission": mission}


# ── default trusted templates (like the pilots — trusted Python) ───────────
def _sqlite_then_zip_template() -> MissionTemplate:
    """A real, live-validated mission: build a small SQLite DB, then package it
    into a zip — the exact governed sqlite → zip chain proven in M17.12, now
    reachable as one business objective."""
    from saathi.application_harness.pilots import sqlite_harness as SQ, zip_archive as Z
    from saathi.application_harness.pipeline import StepContext, StepPlan
    import os

    def _mk(ctx: StepContext) -> StepPlan:
        dbp = os.path.join(ctx.workspace, "data.db")
        return StepPlan(argv=SQ.build_mutation_argv(db_path=dbp, table="t"),
                        produces="data.db", verify_kind="sqlite_db", verify_target=dbp)

    def _pack(ctx: StepContext) -> StepPlan:
        src = ctx.artifacts["build_db"]
        out = os.path.join(ctx.workspace, "bundle.zip")
        return StepPlan(argv=Z.build_pack_argv(output_path=out, input_paths=[src]),
                        produces="bundle.zip", verify_kind="zip", verify_target=out)

    def build_steps(params: dict) -> list:
        return [PipelineStep("build_db", "sqlite", "safe_mutation", _mk),
                PipelineStep("package", "zip", "pack", _pack)]

    return MissionTemplate(
        template_id="data_bundle",
        title="Build & package a data bundle",
        objective="Produce a verified SQLite database and package it into a zip archive.",
        mission_type="one_time", trigger="manual", priority="normal", risk=0,
        approval_required=False,
        parameters=(MissionParameter("label", "str", required=False, default="daily"),),
        build_steps=build_steps)


_TEMPLATES_CACHE: Optional[dict] = None


def _default_templates() -> dict:
    global _TEMPLATES_CACHE
    if _TEMPLATES_CACHE is None:
        _TEMPLATES_CACHE = {}
        try:
            t = _sqlite_then_zip_template()
            _TEMPLATES_CACHE[t.template_id] = t
        except Exception:
            pass
    return dict(_TEMPLATES_CACHE)


_default_engine: Optional[MissionEngine] = None


def default_engine() -> MissionEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = MissionEngine()
    return _default_engine
