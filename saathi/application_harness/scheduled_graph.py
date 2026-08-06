"""M17.17 governed scheduled graph mission recovery integration.

This is the SEAM — not a new engine — that completes the chain:

    Scheduler / trusted event
      → Mission occurrence
        → MissionEngine            (mission authority: create / launch / settle)
          → existing PipelineRunner
            → existing bounded graph executor (M17.16)
              → run_harness_action → adapter → INDEPENDENT verification
                → existing ledger, checkpoints, claims, recovery records (M17.15)

A scheduled occurrence can launch a graph-backed mission, survive interruption,
resume safely THROUGH THE EXISTING graph + recovery layers, and settle the mission
and the scheduler occurrence EXACTLY ONCE. No new execution path is introduced:

- fresh launch always goes through `MissionEngine.launch` (never the graph executor
  directly); the engine dispatches to the bounded graph runner because the bound
  TEMPLATE declares `build_graph` (M17.16);
- recovery always goes through `MissionEngine.resume_graph_mission`, which requests
  the EXISTING public graph recovery interface (`GraphPipelineRunner.resume`) — the
  coordinator never computes checkpoint validity, graph-readiness, branch retry, or
  claim handling itself;
- occurrence settlement reuses the scheduler's own honest mission→occurrence mapping.

Idempotency is layered and durable, NOT memory-only: one occurrence per due time
(scheduler dedup_key), one mission per occurrence (deterministic id), one graph
pipeline per mission run, one recovery claim per graph, one step claim per step, one
join, one final settlement. Repeated sweeps / dispatches / reconciliations therefore
create no duplicate work.

Registered graph-backed TEMPLATES (trusted Python, like the pilots) are the only
place a schedule/event is connected to a concrete bounded graph. A schedule or event
payload can NEVER supply a graph definition, dependencies, harness names, commands,
risk, approval, owner, or concurrency beyond the registered template's limits.

This module performs NO financial-market execution of any kind — it only schedules
and recovers governed local-harness graph work (asserted by a regression test).
"""
from __future__ import annotations

import os
from typing import Optional

from saathi.application_harness import run_ledger as L
from saathi.application_harness.mission import (
    MissionEngine, MissionTemplate, MissionParameter,
)
from saathi.application_harness.scheduler import MissionScheduler

_RECONCILE_BATCH = 25            # bounded per-pass work (no storms; deterministic order)


# ── registered trusted graph-backed mission templates ───────────────────────
def _graph_data_bundle_template() -> MissionTemplate:
    """A real, credential-free graph-backed mission: one SQLite root, two INDEPENDENT
    verified SQLite branches, one zip join that packages both verified branch
    artifacts. Same governed sqlite → zip chain proven in M17.12/M17.16, now reachable
    as ONE scheduled business objective with bounded parallelism."""
    from saathi.application_harness.pilots import sqlite_harness as SQ, zip_archive as Z
    from saathi.application_harness.pipeline import StepContext, StepPlan
    from saathi.application_harness.pipeline_graph import GraphStep

    def _mk(table, produces):
        def plan(ctx: StepContext) -> StepPlan:
            dbp = os.path.join(ctx.workspace, produces)
            return StepPlan(argv=SQ.build_mutation_argv(db_path=dbp, table=table),
                            produces=produces, verify_kind="sqlite_db",
                            verify_target=dbp)
        return plan

    def _pack(srcs, produces="bundle.zip"):
        def plan(ctx: StepContext) -> StepPlan:
            paths = [ctx.artifacts[s] for s in srcs]
            out = os.path.join(ctx.workspace, produces)
            return StepPlan(argv=Z.build_pack_argv(output_path=out, input_paths=paths),
                            produces=produces, verify_kind="zip", verify_target=out)
        return plan

    def build_graph(params: dict) -> list:
        return [
            GraphStep("root", "sqlite", "safe_mutation", _mk("tbase", "base.db")),
            GraphStep("branch_a", "sqlite", "safe_mutation", _mk("ta", "a.db"),
                      dependencies=("root",)),
            GraphStep("branch_b", "sqlite", "safe_mutation", _mk("tb", "b.db"),
                      dependencies=("root",)),
            GraphStep("join", "zip", "pack", _pack(["branch_a", "branch_b"], "bundle.zip"),
                      dependencies=("branch_a", "branch_b")),
        ]

    return MissionTemplate(
        template_id="graph_data_bundle",
        title="Scheduled graph data bundle",
        objective="Build a verified SQLite root, two verified branches, and package "
                  "both into one verified zip via a bounded parallel graph.",
        mission_type="scheduled", trigger="scheduled", priority="normal", risk=0,
        approval_required=False,
        parameters=(MissionParameter("label", "str", required=False, default="daily"),),
        build_graph=build_graph, concurrency_limit=2)


_GRAPH_TEMPLATES_CACHE: Optional[dict] = None


def graph_mission_templates() -> dict:
    """The registered graph-backed mission templates (trusted Python)."""
    global _GRAPH_TEMPLATES_CACHE
    if _GRAPH_TEMPLATES_CACHE is None:
        _GRAPH_TEMPLATES_CACHE = {}
        try:
            t = _graph_data_bundle_template()
            _GRAPH_TEMPLATES_CACHE[t.template_id] = t
        except Exception:
            pass
    return dict(_GRAPH_TEMPLATES_CACHE)


def register_graph_templates(engine: MissionEngine) -> MissionEngine:
    """Additively register the graph-backed templates on an engine (idempotent)."""
    for tid, tmpl in graph_mission_templates().items():
        engine.templates.setdefault(tid, tmpl)
    return engine


class ScheduledGraphCoordinator:
    """Bounded, restart-safe coordinator that links the scheduler, MissionEngine, and
    the existing graph + recovery layers for graph-backed scheduled missions. It
    executes NOTHING itself and computes NO recovery internals — it dispatches through
    the MissionEngine and observes/settles through existing durable records."""

    def __init__(self, *, ledger: L.RunLedger | None = None,
                 engine: MissionEngine | None = None,
                 scheduler: MissionScheduler | None = None):
        self.ledger = ledger or L.default_ledger()
        self.engine = engine or MissionEngine(ledger=self.ledger)
        register_graph_templates(self.engine)
        self.scheduler = scheduler or MissionScheduler(ledger=self.ledger,
                                                       engine=self.engine)

    # ── graph-backed template guard ─────────────────────────────────────────
    def is_graph_mission(self, mission: dict | None) -> bool:
        if not mission:
            return False
        tmpl = self.engine.templates.get(mission.get("template", ""))
        return bool(tmpl is not None and tmpl.build_graph is not None)

    # ── scheduled graph dispatch (fresh launch through the MissionEngine) ────
    def dispatch(self, occurrence_id, *, now=None, worker="scheduled_graph") -> dict:
        """Dispatch a due occurrence, deferring terminal failure when the graph left
        a retryable recovery record (so `recover` can resume it). Fresh execution goes
        through the MissionEngine ONLY (never the graph executor directly)."""
        return self.scheduler.dispatch_occurrence(occurrence_id, now=now, worker=worker,
                                                  graph_recovery=True)

    def sweep(self, *, now=None, worker="scheduled_graph", limit=100) -> dict:
        """One deterministic sweep: reconcile → generate due occurrences → dispatch
        each with graph-recovery deferral enabled."""
        now = now if now is not None else L._now()
        recon = self.reconcile(now=now)
        gen = self.scheduler.create_due_occurrences(now=now)
        dispatched = []
        for occ in self.ledger.pending_due_occurrences(now=now, limit=limit):
            r = self.dispatch(occ["occurrence_id"], now=now, worker=worker)
            dispatched.append({"occurrence_id": occ["occurrence_id"],
                               "state": r.get("state"), "ok": r.get("ok")})
        return {"reconciled": recon, "generated": gen["created"],
                "dispatched": dispatched, "swept_at": now}

    # ── scheduled graph recovery (resume through the existing interface) ─────
    def recover(self, occurrence_id, *, now=None) -> dict:
        """Idempotently reconcile ONE scheduled graph occurrence end to end. Confirms
        owner consistency, settles a crash-stuck running mission from its graph, and
        resumes a failed graph mission through the existing recovery interface, then
        settles the occurrence exactly once. Repeated calls never duplicate work."""
        now = now if now is not None else L._now()
        occ = self.ledger.inspect_occurrence(occurrence_id)
        if occ is None:
            return {"ok": False, "reason": "unknown_occurrence"}
        if occ["state"] in L.OCC_TERMINAL:                # already settled — idempotent
            return {"ok": occ["state"] == L.OCC_SUCCEEDED, "state": occ["state"],
                    "idempotent": True}
        owner = occ["owner"]
        mid = occ.get("mission_id") or ""
        if not mid:                                       # case A — no mission yet
            return {"ok": False, "reason": "no_mission",
                    "hint": "scheduler.reconcile requeues occurrences with no mission"}
        m = self.engine.inspect(mid)
        if m is None:
            return {"ok": False, "reason": "unknown_mission"}
        if m["owner"] != owner:                           # owner mismatch → fail closed
            self.ledger.finish_occurrence(occurrence_id, state=L.OCC_FAILED,
                                          failure_category="owner_mismatch", now=now)
            return {"ok": False, "reason": "owner_mismatch", "state": L.OCC_FAILED}
        st = m["state"]
        # case F: mission stuck RUNNING while its graph already reached terminal
        if st == L.MISSION_RUNNING:
            self.engine.reconcile_running_mission(mid, owner=owner)
            m = self.engine.inspect(mid) or m
            st = m["state"]
        # Prefer an already-settled deterministic recovered mission when present —
        # concurrent recoveries converge on the same linked id.
        rec_id = self.engine._recovered_mission_id(mid)
        rec_m = self.engine.inspect(rec_id)
        if rec_m and rec_m["state"] in L.MISSION_TERMINAL:
            out = self.scheduler.settle_occurrence_from_mission(
                occurrence_id, rec_m, now=now, graph_recovery=True)
            out["recovered_mission_id"] = rec_id
            out["idempotent"] = True
            out["converged"] = True
            return out
        # a FAILED graph mission → resume through the existing recovery interface
        recovered = None
        if st == L.MISSION_FAILED:
            recovered = self.engine.resume_graph_mission(mid, owner=owner, now=now)
            # Contention: another worker holds the recovery claim or is mid-resume.
            # Do NOT settle the occurrence from the original failed mission — that
            # races the winner into a permanent OCC_FAILED after recovery is no
            # longer "retryable". Leave the occurrence recoverable instead.
            if recovered.get("in_progress"):
                rec_m = self.engine.inspect(rec_id)
                if rec_m and rec_m["state"] in L.MISSION_TERMINAL:
                    m = rec_m
                else:
                    return {"ok": False, "state": L.OCC_RETRY_WAIT,
                            "reason": "resume_in_progress", "in_progress": True,
                            "recoverable": True, "mission_id": mid,
                            "recovered_mission_id": rec_id,
                            "pipeline_id": recovered.get("pipeline_id", "")}
            else:
                rid = recovered.get("mission_id", mid)
                m = self.engine.inspect(rid) or m
        # settle the occurrence from the authoritative (recovered) mission, keeping
        # retryable-still-failing missions recoverable for a bounded next pass
        out = self.scheduler.settle_occurrence_from_mission(occurrence_id, m, now=now,
                                                            graph_recovery=True)
        if recovered is not None:
            out["recovered_mission_id"] = recovered.get("mission_id")
            out["reused_steps"] = recovered.get("reused_steps", 0)
            out["rerun_steps"] = recovered.get("rerun_steps", 0)
            if recovered.get("converged") or recovered.get("idempotent"):
                out["converged"] = True
                out["idempotent"] = True
        return out

    # ── bounded automatic reconciliation (opt-in; deterministic; restart-safe) ─
    def reconcile(self, *, now=None, batch=_RECONCILE_BATCH) -> dict:
        """Bounded reconciliation pass. Deterministic order, bounded batch size,
        restart-safe, idempotent. Overlap protection is inherited from the per-record
        leases every mutating sub-operation holds (occurrence claim, graph-step claim,
        graph recovery claim) — two concurrent passes cannot double-execute any step,
        branch, join, mission, or settlement. Reuses the existing graph + scheduler
        reconcilers; adds only the graph-mission cases they do not cover."""
        now = now if now is not None else L._now()
        # 1. reclaim stale graph-step claims (EXISTING graph recovery interface)
        self.engine.graph_runner.reconcile(now=now)
        recovered, settled = [], []
        # 2. stale RUNNING/CLAIMED occurrences with a graph mission (cases F, G)
        seen: set = set()
        for occ in self.ledger.reclaim_stale_occurrences(now=now,
                                                         lease_sec=self.scheduler.lease_sec):
            oid = occ["occurrence_id"]
            m = self.engine.inspect(occ.get("mission_id") or "") if occ.get("mission_id") else None
            if not self.is_graph_mission(m):
                continue                                  # leave non-graph to scheduler
            seen.add(oid)
            r = self.recover(oid, now=now)
            settled.append({"occurrence_id": oid, "state": r.get("state")})
        # 3. recoverable retry_wait graph occurrences (deterministic order, bounded)
        for occ in self.ledger.pending_due_occurrences(now=now, limit=batch):
            oid = occ["occurrence_id"]
            if oid in seen or occ["state"] != L.OCC_RETRY_WAIT or not occ.get("mission_id"):
                continue
            m = self.engine.inspect(occ["mission_id"])
            if not self.is_graph_mission(m):
                continue
            r = self.recover(oid, now=now)
            recovered.append({"occurrence_id": oid, "state": r.get("state")})
        # 4. hand the rest (non-graph, stale occurrence leases) to the scheduler
        sched = self.scheduler.reconcile(now=now)
        return {"recovered": recovered, "settled": settled, "scheduler": sched,
                "reconciled_at": now}

    # ── owner-safe Control Center health ────────────────────────────────────
    def health(self, owner: str | None = None, *, now=None) -> dict:
        """Owner-safe aggregate for the scheduled-graph recovery Control Center view.
        Never exposes raw commands, payloads, artifacts, secrets, or cross-owner
        records — only counts + states from owner-scoped ledger reads."""
        now = now if now is not None else L._now()
        graphs = self.ledger.graph_health(owner)
        recovery = self.ledger.recovery_health(owner)
        occ = self.ledger.occurrence_health(owner, now=now)
        missions = self.ledger.mission_health(owner)
        # attention items derived purely from owner-scoped aggregates
        attention = []
        if graphs.get("failed_branches", 0):
            attention.append("failed_graph_branch")
        if occ.get("by_state", {}).get(L.OCC_APPROVAL_REQUIRED, 0):
            attention.append("approval_required_scheduled_graph")
        if recovery.get("by_state", {}).get(L.RECOVERY_STOP_UNCERTAIN, 0):
            attention.append("stop_uncertain_graph")
        if recovery.get("by_state", {}).get(L.RECOVERY_EXHAUSTED, 0):
            attention.append("retry_exhausted")
        return {"graphs": graphs, "recovery": recovery, "occurrences": occ,
                "missions": missions, "attention": sorted(set(attention)),
                "generated_at": now}


_default: Optional[ScheduledGraphCoordinator] = None


def default_coordinator() -> ScheduledGraphCoordinator:
    global _default
    if _default is None:
        _default = ScheduledGraphCoordinator()
    return _default
