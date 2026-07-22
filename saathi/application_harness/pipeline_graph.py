"""M17.16 governed bounded parallel / branching pipeline graphs.

This is NOT a second pipeline engine. It is a dependency-aware, bounded executor
that sits IMMEDIATELY AROUND the existing M17.12 `PipelineRunner`: every executable
step still runs through the SAME `PipelineRunner._run_step` (→ governed
`run_harness_action` → the sole adapter → INDEPENDENT verification → durable
ledger + M17.15 checkpoints). The graph layer only decides WHICH steps are ready,
runs independent ready steps under BOUNDED local concurrency, and enforces a single
explicit join barrier. It reuses the M17.15 checkpoint validation for
dependency-closed resume. No second execution engine, scheduler, retry framework,
verification path, approval system, or ledger is introduced.

Supported topology (bounded, acyclic, first slice):

           ┌→ B ─┐
    A ──────┤     ├──→ D            one fork (A), N independent branches (B, C),
           └→ C ─┘                  one explicit join barrier (D).

Guarantees (all deterministic; durable behavior never depends on thread timing):
- the whole graph is validated BEFORE any step executes (cycle / unknown dep /
  duplicate id / self-dep / owner mismatch / size / concurrency / unsupported
  nested fork or second join / artifact collision / secret-shaped name / path
  escape / unknown or non-executable harness) — no partial execution on failure;
- a step becomes ready ONLY when every declared dependency has SUCCEEDED and is
  independently verified; the join runs ONLY when all its upstream branches did;
- a branch step sees ONLY its DECLARED dependency artifacts (confinement);
- first terminal branch failure is fail-closed: no new downstream work starts, the
  join never runs, already-running siblings settle honestly, result is `failed`;
- resume reuses a dependency-CLOSED set of still-valid verified checkpoints and
  reruns only invalidated steps and their descendants (not a linear prefix);
- per-step durable claims dedupe execution and make crash reconciliation safe;
- owner / approval / risk stay per-step exactly as in the sequential pipeline.
"""
from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass, field
from typing import Callable, Optional

from saathi.application_harness import run_ledger as L
from saathi.application_harness.pipeline import (
    PipelineRunner, PipelineSpec, StepContext, StepPlan, default_resolver,
    step_fingerprint, file_fingerprint, _within, _sha,
)
from saathi.application_harness.pipeline_recovery import _validate_checkpoint

# ── bounded first-slice limits (limits MUST exist and be tested) ─────────────
MAX_STEPS = 16
MAX_CONCURRENCY = 4
MAX_BRANCH_WIDTH = 4          # fork out-degree ceiling
_SUCCESS = "success"


@dataclass(frozen=True)
class GraphStep:
    """One graph step. Same trusted `plan` builder contract as a sequential
    PipelineStep, plus explicit `dependencies` (names of upstream steps). Duck-types
    as a PipelineStep for `PipelineRunner._run_step` (name/harness_id/operation_id/
    plan)."""
    name: str
    harness_id: str
    operation_id: str
    plan: Callable                     # (StepContext) -> StepPlan
    dependencies: tuple = ()
    owner_id: str = ""                 # optional per-step owner (must match spec owner)


@dataclass(frozen=True)
class GraphSpec:
    name: str
    owner: str
    steps: list                        # list[GraphStep]
    concurrency_limit: int = MAX_CONCURRENCY
    correlation_id: str = ""
    pipeline_id: str = field(default="")


# ── deterministic graph-aware dependency fingerprint ────────────────────────
def graph_dependency_fingerprint(step: GraphStep, artifact_fps: dict) -> str:
    """Fingerprint of the state a graph step depends on: its SORTED declared
    dependency names and their produced-artifact fingerprints. Deterministic and
    independent of completion order — a changed/missing upstream artifact changes
    this, so a downstream checkpoint fails closed."""
    basis = sorted([[d, artifact_fps.get(d, "")] for d in step.dependencies])
    import json
    return _sha(json.dumps(basis, sort_keys=True))


# ── graph validation (reject BEFORE any step executes) ──────────────────────
@dataclass(frozen=True)
class GraphValidation:
    ok: bool
    errors: tuple = ()
    order: tuple = ()                  # deterministic topological order (names)
    roots: tuple = ()
    fork_step: str = ""
    join_step: str = ""
    branches: tuple = ()               # tuple of (branch_key, (step_names...))


def _topo_order(steps) -> Optional[list]:
    """Kahn's algorithm, ties broken by declaration index → deterministic.
    Returns None if a cycle is present."""
    idx = {s.name: i for i, s in enumerate(steps)}
    indeg = {s.name: len(set(s.dependencies)) for s in steps}
    succ = {s.name: [] for s in steps}
    for s in steps:
        for d in set(s.dependencies):
            if d in succ:
                succ[d].append(s.name)
    ready = sorted([n for n, d in indeg.items() if d == 0], key=lambda n: idx[n])
    order = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in sorted(succ[n], key=lambda x: idx[x]):
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
        ready = sorted(ready, key=lambda n: idx[n])
    return order if len(order) == len(steps) else None


def _branches(steps, roots: set, join: str) -> list:
    """Weakly-connected components of the subgraph EXCLUDING roots and the join —
    each component is one independent branch. Deterministic key = min step name."""
    mids = [s.name for s in steps if s.name not in roots and s.name != join]
    if not mids:
        return []
    by = {s.name: s for s in steps}
    parent = {n: n for n in mids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    midset = set(mids)
    for n in mids:
        for d in by[n].dependencies:
            if d in midset:
                union(n, d)
    comps: dict = {}
    for n in mids:
        comps.setdefault(find(n), []).append(n)
    out = []
    for root_name, names in comps.items():
        names = sorted(names)
        out.append((names[0], tuple(names)))
    return sorted(out, key=lambda t: t[0])


def validate_graph(spec: GraphSpec, *, resolver=default_resolver,
                   workspace: str = "") -> GraphValidation:
    errors: list = []
    steps = spec.steps or []
    names = [s.name for s in steps]

    if not steps:
        return GraphValidation(False, ("empty_graph",))
    if len(steps) > MAX_STEPS:
        errors.append(f"graph_too_large:{len(steps)}>{MAX_STEPS}")
    cl = spec.concurrency_limit
    if cl < 1 or cl > MAX_CONCURRENCY:
        errors.append(f"concurrency_out_of_bounds:{cl}")

    # unique step ids
    seen = set()
    for n in names:
        if n in seen:
            errors.append(f"duplicate_step_id:{n}")
        seen.add(n)
    nameset = set(names)

    # owner consistency + secret-shaped names
    for s in steps:
        if s.owner_id and s.owner_id != spec.owner:
            errors.append(f"owner_mismatch:{s.name}")
        if L._SECRET_KEY.search(s.name or ""):
            errors.append(f"secret_shaped_name:{s.name}")

    # dependency edges: exist, no self, no dup
    for s in steps:
        seen_dep = set()
        for d in s.dependencies:
            if d == s.name:
                errors.append(f"self_dependency:{s.name}")
            if d not in nameset:
                errors.append(f"unknown_dependency:{s.name}->{d}")
            if d in seen_dep:
                errors.append(f"duplicate_dependency_edge:{s.name}->{d}")
            seen_dep.add(d)

    # cycle detection / topo order
    order = _topo_order(steps)
    if order is None:
        errors.append("cycle_detected")

    # in/out degree topology: at most ONE fork, at most ONE join
    outdeg = {n: 0 for n in names}
    indeg = {n: 0 for n in names}
    for s in steps:
        for d in set(s.dependencies):
            if d in outdeg:
                outdeg[d] += 1
            indeg[s.name] += 1
    forks = [n for n in names if outdeg[n] >= 2]
    joins = [n for n, s in zip(names, steps) if len(set(s.dependencies)) >= 2]
    if len(forks) > 1:
        errors.append(f"unsupported_nested_fork:{sorted(forks)}")
    if len(joins) > 1:
        errors.append(f"unsupported_second_join:{sorted(joins)}")
    fork_step = forks[0] if forks else ""
    join_step = joins[0] if joins else ""
    if fork_step and outdeg[fork_step] > MAX_BRANCH_WIDTH:
        errors.append(f"branch_width_exceeded:{outdeg[fork_step]}>{MAX_BRANCH_WIDTH}")

    roots = {n for n in names if indeg[n] == 0}
    if not roots:
        errors.append("no_root")

    # harness resolvable + executable; produced-artifact collision + escape
    produced: dict = {}
    ws = workspace or "/tmp/_graph_validate"
    for i, s in enumerate(steps):
        defn, op = resolver(s.harness_id, s.operation_id)
        if defn is None or op is None:
            errors.append(f"unknown_harness:{s.name}"); continue
        if not defn.executable():
            errors.append(f"non_executable_harness:{s.name}")
        # best-effort static plan to detect produced-artifact collisions/escapes
        try:
            ph = {d: os.path.join(ws, f"__dep_{d}") for d in s.dependencies}
            plan = s.plan(StepContext(workspace=ws, artifacts=ph))
        except Exception:
            continue                    # dep-dependent builders validated at exec
        prod = plan.produces or ""
        if prod:
            if os.path.isabs(prod) or ".." in os.path.normpath(prod).split(os.sep):
                errors.append(f"path_escape:{s.name}:{prod}")
            if L._SECRET_KEY.search(prod):
                errors.append(f"secret_shaped_artifact:{s.name}:{prod}")
            if prod in produced and produced[prod] != s.name:
                errors.append(f"artifact_collision:{prod}")
            produced[prod] = s.name

    if errors:
        return GraphValidation(False, tuple(sorted(set(errors))))
    branches = tuple(_branches(steps, roots, join_step))
    return GraphValidation(True, (), tuple(order), tuple(sorted(roots)),
                           fork_step, join_step, branches)


class GraphPipelineRunner:
    """Dependency-aware bounded executor around the sequential PipelineRunner.
    Reuses `PipelineRunner._run_step` for EVERY executable step — the graph layer
    only schedules ready steps under bounded concurrency and enforces the join."""

    def __init__(self, *, ledger: L.RunLedger | None = None,
                 runner: PipelineRunner | None = None, resolver=default_resolver,
                 lease_sec: float = 120.0):
        self.ledger = ledger or L.default_ledger()
        self.runner = runner or PipelineRunner(ledger=self.ledger, resolver=resolver)
        self.resolver = resolver
        self.lease_sec = lease_sec

    @property
    def runs_root(self):
        return self.runner.runs_root

    # ── validation-only entry (for CLI / callers) ───────────────────────────
    def validate(self, spec: GraphSpec) -> GraphValidation:
        return validate_graph(spec, resolver=self.resolver,
                              workspace=str(self.runs_root / (spec.pipeline_id or "x")))

    # ── fresh graph run ─────────────────────────────────────────────────────
    def run(self, spec: GraphSpec, *, session_id: str = "graph", now=None,
            worker: str = "graph") -> dict:
        owner = spec.owner
        if not owner:
            return {"ok": False, "reason": "empty_owner"}
        pid = spec.pipeline_id or ("pg_" + uuid.uuid4().hex[:16])
        if not spec.pipeline_id:                    # bind the resolved id (frozen spec)
            from dataclasses import replace
            spec = replace(spec, pipeline_id=pid)
        workspace = str(self.runs_root / pid)
        v = validate_graph(spec, resolver=self.resolver, workspace=workspace)
        if not v.ok:
            return {"ok": False, "reason": "graph_invalid", "errors": list(v.errors)}
        os.makedirs(workspace, exist_ok=True)
        created = self.ledger.create_pipeline(pid, owner=owner, name=spec.name,
                                              step_count=len(spec.steps),
                                              correlation_id=spec.correlation_id)
        if not created.get("created"):
            return {"ok": False, "pipeline_id": pid, "reason": created.get("reason")}
        deps = [(s.name, d) for s in spec.steps for d in s.dependencies]
        self.ledger.create_graph(pid, owner=owner, name=spec.name,
                                 step_count=len(spec.steps),
                                 concurrency_limit=spec.concurrency_limit,
                                 fork_step=v.fork_step, join_step=v.join_step,
                                 branch_count=len(v.branches), dependencies=deps,
                                 correlation_id=spec.correlation_id)
        for bk, snames in v.branches:
            self.ledger.upsert_branch(pid, branch_key=bk, owner=owner,
                                      step_names=",".join(snames),
                                      state=L.BRANCH_PENDING, now=now)
        self.ledger.start_pipeline(pid)
        return self._execute(spec, v, owner, workspace, session_id, now=now,
                             worker=worker, seed_succeeded=set(), seed_artifacts={},
                             seed_fps={}, resumed_from="")

    # ── the bounded dependency-driven scheduler (join barrier is implicit) ──
    def _execute(self, spec, v, owner, workspace, session_id, *, now, worker,
                 seed_succeeded, seed_artifacts, seed_fps, resumed_from) -> dict:
        pid = spec.pipeline_id
        idx_of = {s.name: i for i, s in enumerate(spec.steps)}
        by_name = {s.name: s for s in spec.steps}
        branch_of = {}
        for bk, snames in v.branches:
            for sn in snames:
                branch_of[sn] = bk

        succeeded = set(seed_succeeded)
        artifacts = dict(seed_artifacts)
        artifact_fps = dict(seed_fps)
        scheduled = set(succeeded)
        rerun = 0
        fail_closed = False
        first_fail = None
        concurrency = max(1, min(spec.concurrency_limit, MAX_CONCURRENCY))
        ex = ThreadPoolExecutor(max_workers=concurrency)
        futures: dict = {}
        try:
            while True:
                if not fail_closed:
                    for s in spec.steps:                    # deterministic order
                        if s.name in scheduled:
                            continue
                        if all(d in succeeded for d in s.dependencies):
                            scheduled.add(s.name)
                            dep_art = {d: artifacts[d] for d in s.dependencies
                                       if d in artifacts}
                            dep_fp = {d: artifact_fps.get(d, "") for d in s.dependencies}
                            if branch_of.get(s.name):
                                self.ledger.set_branch_state(
                                    pid, branch_key=branch_of[s.name],
                                    state=L.BRANCH_RUNNING, now=now)
                            fut = ex.submit(self._run_one, pid, s, idx_of[s.name],
                                            owner, workspace, dep_art, dep_fp,
                                            session_id, now, worker)
                            futures[fut] = s
                if not futures:
                    break
                done, _ = wait(list(futures), return_when=FIRST_COMPLETED)
                for fut in done:
                    s = futures.pop(fut)
                    res = fut.result()
                    st = res["status"]
                    if st == _SUCCESS:
                        succeeded.add(s.name)
                        rerun += 1
                        if res.get("artifact"):
                            artifacts[s.name] = os.path.join(workspace, res["artifact"])
                            artifact_fps[s.name] = res.get("artifact_fp", "")
                    else:
                        fail_closed = True
                        if first_fail is None:
                            first_fail = (idx_of[s.name], s.name,
                                          res.get("error_code") or st)
                    self._settle_branch(pid, s.name, branch_of, by_name, v,
                                        succeeded, res, now)
        finally:
            ex.shutdown(wait=True)

        # unstarted work after a failure: honest cancellation (join stays blocked)
        for s in spec.steps:
            if s.name not in scheduled:
                bk = branch_of.get(s.name)
                if bk:
                    self.ledger.set_branch_state(pid, branch_key=bk,
                                                 state=L.BRANCH_CANCELLED, now=now)

        all_ok = all(s.name in succeeded for s in spec.steps)
        if all_ok and not fail_closed:
            self.ledger.complete_pipeline(pid, state=L.PIPELINE_SUCCEEDED)
            return {"ok": True, "pipeline_id": pid, "state": L.PIPELINE_SUCCEEDED,
                    "steps_run": len(spec.steps), "reused_steps": len(seed_succeeded),
                    "rerun_steps": rerun, "resumed_from": resumed_from,
                    "branches": [b[0] for b in v.branches], "join": v.join_step}
        fidx, fname, fcode = first_fail or (-1, "", "GRAPH_INCOMPLETE")
        self.ledger.complete_pipeline(pid, state=L.PIPELINE_FAILED, failed_step=fidx,
                                      failure_code=fcode)
        self._record_failure(pid, owner, fcode, now)
        return {"ok": False, "pipeline_id": pid, "state": L.PIPELINE_FAILED,
                "failed_step": fidx, "failed_step_name": fname, "failure_code": fcode,
                "reused_steps": len(seed_succeeded), "rerun_steps": rerun,
                "resumed_from": resumed_from, "join": v.join_step,
                "join_ran": v.join_step in succeeded if v.join_step else None}

    def _run_one(self, pid, step, idx, owner, workspace, dep_art, dep_fp,
                 session_id, now, worker) -> dict:
        """Claim → governed `_run_step` (through run_harness_action) → release.
        The per-step claim guarantees exactly-once execution and blocks duplicates."""
        if not self.ledger.claim_graph_step(pid, step_index=idx, step_name=step.name,
                                             worker=f"{worker}:{step.name}", now=now,
                                             lease_sec=self.lease_sec):
            return {"status": "blocked", "error_code": "STEP_ALREADY_CLAIMED",
                    "artifact": ""}
        gdep_fp = graph_dependency_fingerprint(step, dep_fp)
        out = self.runner._run_step(pid, idx, step, owner, workspace, dep_art,
                                    session_id, gdep_fp)
        self.ledger.release_graph_step(
            pid, step_index=idx,
            state=L.CLAIM_SUCCEEDED if out["status"] == _SUCCESS else L.CLAIM_FAILED,
            now=now)
        return out

    def _settle_branch(self, pid, sname, branch_of, by_name, v, succeeded, res, now):
        bk = branch_of.get(sname)
        if not bk:
            return
        snames = next((c[1] for c in v.branches if c[0] == bk), ())
        if res["status"] != _SUCCESS:
            code = res.get("error_code") or res["status"]
            state = (L.BRANCH_APPROVAL_REQUIRED if "APPROVAL" in code.upper()
                     else L.BRANCH_STOP_UNCERTAIN if ("UNCERTAIN" in code.upper()
                                                      or "VERIFICATION" in code.upper())
                     else L.BRANCH_BLOCKED if res["status"] == "blocked"
                     else L.BRANCH_FAILED)
            self.ledger.set_branch_state(pid, branch_key=bk, state=state,
                                         failure_code=code, now=now)
        elif all(n in succeeded for n in snames):
            self.ledger.set_branch_state(pid, branch_key=bk,
                                         state=L.BRANCH_SUCCEEDED, now=now)

    def _record_failure(self, pid, owner, code, now) -> None:
        try:
            rec = self.ledger.get_recovery(pid)
            up = (code or "").upper()
            state = (L.RECOVERY_STOP_UNCERTAIN
                     if ("UNCERTAIN" in up or "VERIFICATION" in up)
                     else L.RECOVERY_RETRY_WAIT)
            self.ledger.upsert_recovery(pid, owner=owner, failure_category=code,
                                        attempt=(rec["attempt"] if rec else 1),
                                        next_retry_at=0.0, state=state, now=now)
        except Exception:
            pass

    # ── dependency-closed reusable subgraph (graph resume) ──────────────────
    def reusable_subgraph(self, spec: GraphSpec, owner: str) -> dict:
        pid = spec.pipeline_id
        workspace = str(self.runs_root / pid)
        v = validate_graph(spec, resolver=self.resolver, workspace=workspace)
        order = v.order or [s.name for s in spec.steps]
        by_name = {s.name: s for s in spec.steps}
        idx_of = {s.name: i for i, s in enumerate(spec.steps)}
        reusable: set = set()
        artifacts: dict = {}
        artifact_fps: dict = {}
        for name in order:
            step = by_name[name]
            idx = idx_of[name]
            if any(d not in reusable for d in step.dependencies):
                continue                                # not dependency-closed
            cp = self.ledger.get_checkpoint(pid, step_index=idx)
            dep_art = {d: artifacts[d] for d in step.dependencies if d in artifacts}
            try:
                plan = step.plan(StepContext(workspace=workspace, artifacts=dep_art))
            except Exception:
                continue
            defn, op = self.resolver(step.harness_id, step.operation_id)
            dep_fp = graph_dependency_fingerprint(step, artifact_fps)
            ok, reason, bad = _validate_checkpoint(cp, step, plan, op, workspace,
                                                   owner, dep_fp)
            if not ok:
                if cp is not None and cp["status"] == L.CHECKPOINT_VALID:
                    self.ledger.invalidate_checkpoint(pid, step_index=idx,
                                                      reason=reason, status=bad)
                continue
            reusable.add(name)
            if cp["artifact"]:
                artifacts[name] = os.path.join(workspace, cp["artifact"])
                artifact_fps[name] = cp["artifact_fingerprint"]
        return {"reusable": reusable, "artifacts": artifacts,
                "artifact_fps": artifact_fps, "validation": v}

    # ── operator-explicit graph resume (dedup via recovery claim) ───────────
    def resume(self, spec: GraphSpec, *, owner: str, session_id: str = "graph_resume",
               now=None, worker="graph_recovery") -> dict:
        now = now if now is not None else L._now()
        pid = spec.pipeline_id
        if not pid:
            return {"ok": False, "reason": "no_pipeline_id"}
        run = self.ledger.inspect_pipeline(pid)
        if run is None:
            return {"ok": False, "reason": "unknown_pipeline"}
        if run["owner"] != owner:
            return {"ok": False, "reason": "owner_mismatch"}
        if run["state"] != L.PIPELINE_FAILED:
            return {"ok": False, "reason": f"not_resumable:{run['state']}"}
        if self.ledger.get_recovery(pid) is None:
            self.ledger.upsert_recovery(pid, owner=owner,
                                        failure_category=run.get("failure_code", ""),
                                        attempt=1, now=now)
        if not self.ledger.claim_recovery(pid, worker=worker, now=now,
                                          lease_sec=self.lease_sec):
            return {"ok": False, "reason": "recovery_claimed"}
        workspace = str(self.runs_root / pid)
        sub = self.reusable_subgraph(spec, owner)
        v = sub["validation"]
        if not v.ok:
            self.ledger.release_recovery(pid, state=L.RECOVERY_RETRY_WAIT, now=now)
            return {"ok": False, "reason": "graph_invalid", "errors": list(v.errors)}
        reopened = self.ledger.reopen_pipeline(pid, now=now)
        if not reopened.get("ok"):
            self.ledger.release_recovery(pid, state=L.RECOVERY_RETRY_WAIT, now=now)
            return {"ok": False, "reason": reopened.get("reason")}
        res = self._execute(spec, v, owner, workspace, session_id, now=now,
                            worker=worker, seed_succeeded=set(sub["reusable"]),
                            seed_artifacts=sub["artifacts"], seed_fps=sub["artifact_fps"],
                            resumed_from=pid)
        if res.get("ok"):
            self.ledger.release_recovery(pid, state=L.RECOVERY_RECOVERED,
                                         reused_steps=len(sub["reusable"]),
                                         rerun_steps=res.get("rerun_steps", 0), now=now)
        else:
            up = (res.get("failure_code") or "").upper()
            state = (L.RECOVERY_STOP_UNCERTAIN
                     if ("UNCERTAIN" in up or "VERIFICATION" in up)
                     else L.RECOVERY_RETRY_WAIT)
            self.ledger.release_recovery(pid, state=state,
                                         retry_reason=res.get("failure_code", ""),
                                         reused_steps=len(sub["reusable"]),
                                         rerun_steps=res.get("rerun_steps", 0), now=now)
        return res

    # ── crash reconciliation (prefer reconcile over duplicate execution) ────
    def reconcile(self, pid=None, *, now=None) -> dict:
        now = now if now is not None else L._now()
        released = []
        for claim in self.ledger.reclaim_stale_step_claims(pid, now=now,
                                                           lease_sec=self.lease_sec):
            self.ledger.release_graph_step(claim["pipeline_id"],
                                           step_index=claim["step_index"],
                                           state=L.CLAIM_RELEASED, now=now)
            released.append((claim["pipeline_id"], claim["step_index"]))
        return {"reclaimed_claims": released}

    # ── owner-safe reads ────────────────────────────────────────────────────
    def inspect(self, pid, *, owner: str | None = None) -> Optional[dict]:
        return self.ledger.inspect_graph(pid, owner=owner)

    def health(self, owner: str | None = None) -> dict:
        return self.ledger.graph_health(owner)


_default: Optional[GraphPipelineRunner] = None


def default_graph_runner() -> GraphPipelineRunner:
    global _default
    if _default is None:
        _default = GraphPipelineRunner()
    return _default
