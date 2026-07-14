"""M17.16 governed bounded parallel / branching pipeline graphs.

Deterministic (injected clock, deterministic adapters/injected runners, bounded
ThreadPoolExecutor — no real sleeps, no timing assertions). Proves: a bounded
acyclic graph is fully validated before any step runs; independent branches run
under bounded concurrency; every step still goes through run_harness_action and is
independently verified; the join runs ONLY after all upstream branches succeed; a
branch failure/approval/blocked is fail-closed and the join never runs; resume
reuses a dependency-CLOSED set of valid checkpoints and reruns only invalidated
steps + descendants; per-step claims dedupe execution and make crash reconcile
safe; owner/approval stay per-step; and the layer opens NO trading/broker surface.
"""
import os
import tempfile
import threading
from dataclasses import replace

import pytest

from saathi.application_harness import service as SVC
from saathi.application_harness import run_ledger as L
from saathi.application_harness.run_ledger import (
    RunLedger, PIPELINE_FAILED, PIPELINE_SUCCEEDED, CHECKPOINT_VALID,
    BRANCH_SUCCEEDED, BRANCH_FAILED, BRANCH_CANCELLED, BRANCH_APPROVAL_REQUIRED,
    CLAIM_SUCCEEDED, CLAIM_RUNNING,
)
from saathi.application_harness.pipeline import (
    PipelineRunner, StepPlan, StepContext, default_resolver,
)
from saathi.application_harness.pipeline_graph import (
    GraphStep, GraphSpec, GraphPipelineRunner, validate_graph,
    graph_dependency_fingerprint, MAX_STEPS, MAX_CONCURRENCY, MAX_BRANCH_WIDTH,
)
from saathi.application_harness.pilots import sqlite_harness as SQ, zip_archive as Z

HAS_LIVE = SQ.available()["available"] and Z.available()["available"]
live = pytest.mark.skipif(not HAS_LIVE, reason="sqlite3/zip required")


# ── helpers ─────────────────────────────────────────────────────────────────
def _ledger():
    return RunLedger(os.path.join(tempfile.mkdtemp(), "l.db"))


def _mk(table, produces):
    def plan(ctx):
        dbp = os.path.join(ctx.workspace, produces)
        return StepPlan(argv=SQ.build_mutation_argv(db_path=dbp, table=table),
                        produces=produces, verify_kind="sqlite_db", verify_target=dbp)
    return plan


def _pack(srcs, produces="bundle.zip"):
    def plan(ctx):
        paths = [ctx.artifacts[s] for s in srcs]
        out = os.path.join(ctx.workspace, produces)
        return StepPlan(argv=Z.build_pack_argv(output_path=out, input_paths=paths),
                        produces=produces, verify_kind="zip", verify_target=out)
    return plan


def _diamond(pid="pg", concurrency=2, owner="ajay"):
    """A ─→(B,C)─→D — one fork, two independent branches, one join."""
    steps = [
        GraphStep("A", "sqlite", "safe_mutation", _mk("tbase", "base.db")),
        GraphStep("B", "sqlite", "safe_mutation", _mk("tbee", "bee.db"), dependencies=("A",)),
        GraphStep("C", "sqlite", "safe_mutation", _mk("tsea", "sea.db"), dependencies=("A",)),
        GraphStep("D", "zip", "pack", _pack(["B", "C"], "bundle.zip"), dependencies=("B", "C")),
    ]
    return GraphSpec(name="diamond", owner=owner, steps=steps,
                     concurrency_limit=concurrency, pipeline_id=pid)


def _runner(led, runner=None, runs=None):
    rr = runs or tempfile.mkdtemp()
    return GraphPipelineRunner(ledger=led,
                               runner=PipelineRunner(ledger=led, runner=runner, runs_root=rr))


def _fail_on(produces, times, category="transient_lock"):
    """Injected runner: fail a specific produced-artifact step `times` times, then
    delegate to the real governed service."""
    st = {"n": 0}
    lk = threading.Lock()

    def r(**kw):
        if any(a.endswith("/" + produces) for a in kw["argv"]):
            with lk:
                if st["n"] < times:
                    st["n"] += 1
                    return {"status": "failed", "error_code": category}
        return SVC.run_harness_action(**kw)
    return r


# ══ GRAPH VALIDATION ══════════════════════════════════════════════════════════
def test_valid_diamond_graph():
    v = validate_graph(_diamond())
    assert v.ok and v.fork_step == "A" and v.join_step == "D"
    assert len(v.branches) == 2


def test_valid_three_branch_graph():
    steps = [GraphStep("A", "sqlite", "safe_mutation", _mk("t0", "a.db"))]
    for n, t, f in (("B", "tb", "b.db"), ("C", "tc", "c.db"), ("E", "te", "e.db")):
        steps.append(GraphStep(n, "sqlite", "safe_mutation", _mk(t, f), dependencies=("A",)))
    steps.append(GraphStep("D", "zip", "pack", _pack(["B", "C", "E"]), dependencies=("B", "C", "E")))
    v = validate_graph(GraphSpec("g3", "ajay", steps, pipeline_id="g3"))
    assert v.ok and len(v.branches) == 3


def test_duplicate_step_id_rejected():
    s = _diamond().steps
    s[2] = GraphStep("B", "sqlite", "safe_mutation", _mk("tc", "sea.db"), dependencies=("A",))
    assert any("duplicate_step_id" in e for e in validate_graph(GraphSpec("g", "ajay", s)).errors)


def test_missing_dependency_rejected():
    s = _diamond().steps
    s[1] = GraphStep("B", "sqlite", "safe_mutation", _mk("tbee", "bee.db"), dependencies=("Z",))
    assert any("unknown_dependency" in e for e in validate_graph(GraphSpec("g", "ajay", s)).errors)


def test_self_dependency_rejected():
    s = _diamond().steps
    s[1] = GraphStep("B", "sqlite", "safe_mutation", _mk("tbee", "bee.db"), dependencies=("B",))
    assert any("self_dependency" in e for e in validate_graph(GraphSpec("g", "ajay", s)).errors)


def test_cycle_rejected():
    s = _diamond().steps
    s[0] = GraphStep("A", "sqlite", "safe_mutation", _mk("tbase", "base.db"), dependencies=("D",))
    assert "cycle_detected" in validate_graph(GraphSpec("g", "ajay", s)).errors


def test_owner_mismatch_rejected():
    s = _diamond().steps
    s[1] = GraphStep("B", "sqlite", "safe_mutation", _mk("tbee", "bee.db"),
                     dependencies=("A",), owner_id="mallory")
    assert any("owner_mismatch" in e for e in validate_graph(GraphSpec("g", "ajay", s)).errors)


def test_graph_size_limit_enforced():
    steps = [GraphStep("A", "sqlite", "safe_mutation", _mk("t0", "a.db"))]
    for i in range(MAX_STEPS + 2):
        steps.append(GraphStep(f"S{i}", "sqlite", "safe_mutation",
                               _mk(f"t{i}", f"s{i}.db"), dependencies=("A",)))
    assert any("graph_too_large" in e for e in validate_graph(GraphSpec("g", "ajay", steps)).errors)


def test_concurrency_limit_enforced():
    assert any("concurrency_out_of_bounds" in e
               for e in validate_graph(_diamond(concurrency=MAX_CONCURRENCY + 1)).errors)


def test_nested_fork_rejected():
    # two distinct fork points (A and B both fan out) → unsupported nested fork
    steps = [
        GraphStep("A", "sqlite", "safe_mutation", _mk("ta", "a.db")),
        GraphStep("B", "sqlite", "safe_mutation", _mk("tb", "b.db"), dependencies=("A",)),
        GraphStep("C", "sqlite", "safe_mutation", _mk("tc", "c.db"), dependencies=("A",)),
        GraphStep("E", "sqlite", "safe_mutation", _mk("te", "e.db"), dependencies=("B",)),
        GraphStep("F", "sqlite", "safe_mutation", _mk("tf", "f.db"), dependencies=("B",)),
        GraphStep("D", "zip", "pack", _pack(["C", "E", "F"]), dependencies=("C", "E", "F")),
    ]
    assert any("unsupported_nested_fork" in e
               for e in validate_graph(GraphSpec("g", "ajay", steps)).errors)


def test_second_join_rejected():
    steps = [
        GraphStep("A", "sqlite", "safe_mutation", _mk("ta", "a.db")),
        GraphStep("B", "sqlite", "safe_mutation", _mk("tb", "b.db"), dependencies=("A",)),
        GraphStep("C", "sqlite", "safe_mutation", _mk("tc", "c.db"), dependencies=("A",)),
        GraphStep("D", "zip", "pack", _pack(["B", "C"], "d.zip"), dependencies=("B", "C")),
        GraphStep("E", "zip", "pack", _pack(["B", "C"], "e.zip"), dependencies=("B", "C")),
    ]
    assert any("unsupported_second_join" in e
               for e in validate_graph(GraphSpec("g", "ajay", steps)).errors)


def test_branch_width_exceeded_rejected():
    steps = [GraphStep("A", "sqlite", "safe_mutation", _mk("t0", "a.db"))]
    mids = []
    for i in range(MAX_BRANCH_WIDTH + 1):
        n = f"B{i}"
        mids.append(n)
        steps.append(GraphStep(n, "sqlite", "safe_mutation", _mk(f"t{i}", f"b{i}.db"),
                               dependencies=("A",)))
    steps.append(GraphStep("D", "zip", "pack", _pack(mids), dependencies=tuple(mids)))
    assert any("branch_width_exceeded" in e
               for e in validate_graph(GraphSpec("g", "ajay", steps)).errors)


def test_artifact_collision_rejected():
    s = _diamond().steps
    s[2] = GraphStep("C", "sqlite", "safe_mutation", _mk("tsea", "bee.db"), dependencies=("A",))
    assert any("artifact_collision" in e for e in validate_graph(GraphSpec("g", "ajay", s)).errors)


def test_secret_shaped_name_rejected():
    s = _diamond().steps
    s[1] = GraphStep("api_key", "sqlite", "safe_mutation", _mk("tbee", "bee.db"),
                     dependencies=("A",))
    assert any("secret_shaped_name" in e for e in validate_graph(GraphSpec("g", "ajay", s)).errors)


def test_path_escape_rejected():
    def esc(ctx):
        return StepPlan(argv=["x"], produces="../escape.db")
    s = _diamond().steps
    s[1] = GraphStep("B", "sqlite", "safe_mutation", esc, dependencies=("A",))
    assert any("path_escape" in e for e in validate_graph(GraphSpec("g", "ajay", s)).errors)


def test_unknown_harness_rejected():
    s = _diamond().steps
    s[1] = GraphStep("B", "nope", "op", _mk("tbee", "bee.db"), dependencies=("A",))
    assert any("unknown_harness" in e for e in validate_graph(GraphSpec("g", "ajay", s)).errors)


@live
def test_invalid_graph_executes_nothing():
    led = _ledger()
    s = _diamond("pgbad").steps
    s[0] = GraphStep("A", "sqlite", "safe_mutation", _mk("tbase", "base.db"), dependencies=("D",))
    res = _runner(led).run(GraphSpec("g", "ajay", s, pipeline_id="pgbad"))
    assert res["ok"] is False and res["reason"] == "graph_invalid"
    assert led.inspect_pipeline("pgbad") is None          # no run created


# ══ READY QUEUE + PARALLEL EXECUTION + JOIN BARRIER ══════════════════════════
@live
def test_diamond_runs_and_join_receives_both_branches():
    led = _ledger()
    res = _runner(led).run(_diamond("pgok"), now=100.0)
    assert res["ok"] and res["state"] == PIPELINE_SUCCEEDED
    g = led.inspect_graph("pgok", owner="ajay")
    assert {s["step_name"]: s["status"] for s in g["steps"]} == {
        "A": "success", "B": "success", "C": "success", "D": "success"}
    # the join's produced bundle exists and was independently verified (success)
    assert g["join_step"] == "D"
    assert {b["branch_key"]: b["state"] for b in g["branches"]} == {
        "B": BRANCH_SUCCEEDED, "C": BRANCH_SUCCEEDED}


@live
def test_two_branches_execute_concurrently_under_bound():
    """Both branch steps are inside the executor at the same instant, and the pool
    never exceeds the configured worker bound. Deterministic via a barrier."""
    led = _ledger()
    barrier = threading.Barrier(2, timeout=10)
    peak = {"cur": 0, "max": 0}
    lk = threading.Lock()

    def _is_branch(kw):
        return (kw["op"].operation_id == "safe_mutation"
                and any(a.endswith(("/bee.db", "/sea.db")) for a in kw["argv"]))

    def r(**kw):
        if _is_branch(kw):
            with lk:
                peak["cur"] += 1
                peak["max"] = max(peak["max"], peak["cur"])
            barrier.wait()                     # both branches must be live together
            out = SVC.run_harness_action(**kw)
            with lk:
                peak["cur"] -= 1
            return out
        return SVC.run_harness_action(**kw)
    res = _runner(led, runner=r).run(_diamond("pgpar", concurrency=2), now=100.0)
    assert res["ok"]
    assert peak["max"] == 2                     # ran concurrently
    assert peak["max"] <= MAX_CONCURRENCY       # bounded


@live
def test_worker_bound_serializes_when_limit_one():
    led = _ledger()
    seen = {"max": 0, "cur": 0}
    lk = threading.Lock()

    def r(**kw):
        with lk:
            seen["cur"] += 1
            seen["max"] = max(seen["max"], seen["cur"])
        out = SVC.run_harness_action(**kw)
        with lk:
            seen["cur"] -= 1
        return out
    res = _runner(led, runner=r).run(_diamond("pg1w", concurrency=1), now=100.0)
    assert res["ok"] and seen["max"] == 1


@live
def test_each_step_passes_through_run_harness_action():
    led = _ledger()
    calls = []
    lk = threading.Lock()

    def r(**kw):
        with lk:
            calls.append(kw["op"].operation_id)
        return SVC.run_harness_action(**kw)
    res = _runner(led, runner=r).run(_diamond("pgrh"), now=100.0)
    assert res["ok"]
    assert sorted(calls) == ["pack", "safe_mutation", "safe_mutation", "safe_mutation"]


@live
def test_branch_sees_only_declared_dependency_artifacts():
    led = _ledger()
    captured = {}

    def _capturing_plan(name, table, produces, deps):
        def plan(ctx):
            captured[name] = sorted(ctx.artifacts.keys())
            dbp = os.path.join(ctx.workspace, produces)
            return StepPlan(argv=SQ.build_mutation_argv(db_path=dbp, table=table),
                            produces=produces, verify_kind="sqlite_db", verify_target=dbp)
        return GraphStep(name, "sqlite", "safe_mutation", plan, dependencies=deps)
    steps = [
        GraphStep("A", "sqlite", "safe_mutation", _mk("tbase", "base.db")),
        _capturing_plan("B", "tbee", "bee.db", ("A",)),
        _capturing_plan("C", "tsea", "sea.db", ("A",)),
        GraphStep("D", "zip", "pack", _pack(["B", "C"]), dependencies=("B", "C")),
    ]
    res = _runner(led).run(GraphSpec("g", "ajay", steps, pipeline_id="pgconf"), now=100.0)
    assert res["ok"]
    assert captured["B"] == ["A"] and captured["C"] == ["A"]   # only declared dep


# ══ FAIL-CLOSED ══════════════════════════════════════════════════════════════
@live
def test_branch_failure_prevents_join():
    led = _ledger()
    res = _runner(led, runner=_fail_on("bee.db", 99)).run(_diamond("pgf"), now=100.0)
    assert res["ok"] is False and res["state"] == PIPELINE_FAILED
    assert res["failed_step_name"] == "B" and res["join_ran"] is False
    g = led.inspect_graph("pgf")
    assert led.get_checkpoint("pgf", step_index=3) is None     # D never checkpointed
    st = {b["branch_key"]: b["state"] for b in g["branches"]}
    assert st["B"] == BRANCH_FAILED and st["C"] == BRANCH_SUCCEEDED  # sibling honest


@live
def test_approval_required_branch_blocks_join():
    led = _ledger()
    ops = {o.operation_id: o for o in SQ.operations()}
    gated = replace(ops["safe_mutation"], risk=3)            # forces approval

    def res_fn(h, o):
        defn, op = default_resolver(h, o)
        # gate ONLY branch B's op (it produces bee.db) — resolver is per (h,op) so
        # we gate all sqlite safe_mutation; A also gated. Instead gate via a
        # dedicated harness id is overkill — approve A/C by using a runner shim.
        return defn, gated if o == "safe_mutation" else op

    # approve A and C (pre-approved plans); leave B unapproved → approval_required
    def _mkapp(table, produces, approved):
        def plan(ctx):
            dbp = os.path.join(ctx.workspace, produces)
            return StepPlan(argv=SQ.build_mutation_argv(db_path=dbp, table=table),
                            produces=produces, verify_kind="sqlite_db",
                            verify_target=dbp, approved=approved)
        return plan
    steps = [
        GraphStep("A", "sqlite", "safe_mutation", _mkapp("tbase", "base.db", True)),
        GraphStep("B", "sqlite", "safe_mutation", _mkapp("tbee", "bee.db", False), dependencies=("A",)),
        GraphStep("C", "sqlite", "safe_mutation", _mkapp("tsea", "sea.db", True), dependencies=("A",)),
        GraphStep("D", "zip", "pack", _pack(["B", "C"]), dependencies=("B", "C")),
    ]
    gr = GraphPipelineRunner(ledger=led, resolver=res_fn,
                             runner=PipelineRunner(ledger=led, resolver=res_fn,
                                                   runs_root=tempfile.mkdtemp()))
    res = gr.run(GraphSpec("g", "ajay", steps, pipeline_id="pgap"), now=100.0)
    assert res["ok"] is False and res["join_ran"] is False
    st = {b["branch_key"]: b["state"] for b in led.inspect_graph("pgap")["branches"]}
    assert st["B"] == BRANCH_APPROVAL_REQUIRED


@live
def test_risk4_branch_needs_approval_and_blocks_join():
    """Risk-4 stays gated: the graph never silently elevates it. An unapproved
    risk-4 branch stops at approval_required and the join never runs."""
    led = _ledger()
    ops = {o.operation_id: o for o in SQ.operations()}
    r4 = replace(ops["safe_mutation"], risk=4)

    def res_fn(h, o):
        defn, op = default_resolver(h, o)
        return defn, r4 if o == "safe_mutation" else op

    def _mkapp(table, produces, approved):
        def plan(ctx):
            dbp = os.path.join(ctx.workspace, produces)
            return StepPlan(argv=SQ.build_mutation_argv(db_path=dbp, table=table),
                            produces=produces, verify_kind="sqlite_db",
                            verify_target=dbp, approved=approved)
        return plan
    steps = [
        GraphStep("A", "sqlite", "safe_mutation", _mkapp("tbase", "base.db", True)),
        GraphStep("B", "sqlite", "safe_mutation", _mkapp("tbee", "bee.db", False), dependencies=("A",)),
        GraphStep("C", "sqlite", "safe_mutation", _mkapp("tsea", "sea.db", True), dependencies=("A",)),
        GraphStep("D", "zip", "pack", _pack(["B", "C"]), dependencies=("B", "C")),
    ]
    gr = GraphPipelineRunner(ledger=led, resolver=res_fn,
                             runner=PipelineRunner(ledger=led, resolver=res_fn,
                                                   runs_root=tempfile.mkdtemp()))
    res = gr.run(GraphSpec("g", "ajay", steps, pipeline_id="pgr4"), now=100.0)
    assert res["ok"] is False and res["join_ran"] is False     # risk-4 not elevated
    st = {b["branch_key"]: b["state"] for b in led.inspect_graph("pgr4")["branches"]}
    assert st["B"] == BRANCH_APPROVAL_REQUIRED


# ══ CHECKPOINTS + GRAPH RESUME ═══════════════════════════════════════════════
@live
def test_partial_reuse_reruns_only_failed_branch_and_descendants():
    led = _ledger()
    runs = tempfile.mkdtemp()
    _runner(led, runner=_fail_on("bee.db", 99), runs=runs).run(_diamond("pgr"), now=100.0)
    # A + C verified; B failed; D never ran
    assert led.get_checkpoint("pgr", step_index=0)["status"] == CHECKPOINT_VALID
    assert led.get_checkpoint("pgr", step_index=2)["status"] == CHECKPOINT_VALID
    res = _runner(led, runs=runs).resume(_diamond("pgr"), owner="ajay", now=200.0)
    assert res["ok"] and res["reused_steps"] == 2 and res["rerun_steps"] == 2


@live
def test_invalid_root_invalidates_all_downstream():
    led = _ledger()
    runs = tempfile.mkdtemp()
    _runner(led, runner=_fail_on("sea.db", 99), runs=runs).run(_diamond("pgir"), now=100.0)
    # C failed → D never ran; A + B verified. Tamper the ROOT artifact.
    ws = str(_runner(led, runs=runs).runs_root / "pgir")
    with open(os.path.join(ws, "base.db"), "ab") as f:
        f.write(b"tampered")
    sub = _runner(led, runs=runs).reusable_subgraph(_diamond("pgir"), "ajay")
    assert sub["reusable"] == set()               # root invalid → nothing reusable


@live
def test_artifact_tamper_invalidates_branch_and_join_only():
    led = _ledger()
    runs = tempfile.mkdtemp()
    _runner(led, runs=runs).run(_diamond("pgt"), now=100.0)    # full success
    ws = str(_runner(led, runs=runs).runs_root / "pgt")
    with open(os.path.join(ws, "bee.db"), "ab") as f:          # tamper branch B
        f.write(b"x")
    sub = _runner(led, runs=runs).reusable_subgraph(_diamond("pgt"), "ajay")
    # A + C still reusable; B tampered → not reusable; D depends on B → not reusable
    assert "A" in sub["reusable"] and "C" in sub["reusable"]
    assert "B" not in sub["reusable"] and "D" not in sub["reusable"]


@live
def test_reusable_subgraph_is_dependency_closed():
    led = _ledger()
    runs = tempfile.mkdtemp()
    _runner(led, runs=runs).run(_diamond("pgdc"), now=100.0)
    ws = str(_runner(led, runs=runs).runs_root / "pgdc")
    with open(os.path.join(ws, "base.db"), "ab") as f:
        f.write(b"x")                                          # invalidate root only
    sub = _runner(led, runs=runs).reusable_subgraph(_diamond("pgdc"), "ajay")
    # no downstream step may be reused when its upstream is invalid
    assert sub["reusable"] == set()


@live
def test_duplicate_resume_deduplicated():
    led = _ledger()
    runs = tempfile.mkdtemp()
    _runner(led, runner=_fail_on("bee.db", 1), runs=runs).run(_diamond("pgdr"), now=100.0)
    led.upsert_recovery("pgdr", owner="ajay", failure_category="transient_lock", now=150.0)
    assert led.claim_recovery("pgdr", worker="first", now=150.0)   # first holds lease
    second = _runner(led, runs=runs).resume(_diamond("pgdr"), owner="ajay", now=150.0)
    assert second["ok"] is False and second["reason"] == "recovery_claimed"


# ══ RETRY ISOLATION ══════════════════════════════════════════════════════════
@live
def test_retryable_failure_reruns_only_that_branch():
    led = _ledger()
    runs = tempfile.mkdtemp()
    _runner(led, runner=_fail_on("bee.db", 1), runs=runs).run(_diamond("pgri"), now=100.0)
    # C succeeded already; resume must reuse A + C and rerun only B (+ join D)
    res = _runner(led, runs=runs).resume(_diamond("pgri"), owner="ajay", now=200.0)
    assert res["ok"] and res["reused_steps"] == 2 and res["rerun_steps"] == 2


def test_non_retryable_categories_are_not_retried():
    from saathi.application_harness.pipeline_recovery import is_retryable
    for bad in ("approval_required", "owner_mismatch", "verification_failed",
                "artifact_integrity", "unknown", "PIPELINE_PATH_ESCAPE:produces"):
        assert not is_retryable(bad)


# ══ CONCURRENCY + CLAIM DEDUP ════════════════════════════════════════════════
@live
def test_duplicate_graph_launch_deduplicated():
    led = _ledger()
    runs = tempfile.mkdtemp()
    r1 = _runner(led, runs=runs).run(_diamond("pgdup"), now=100.0)
    assert r1["ok"] is True
    r2 = _runner(led, runs=runs).run(_diamond("pgdup"), now=100.0)
    assert r2["ok"] is False and r2["reason"] == "duplicate_pipeline_id"


def test_exactly_one_claim_per_step_and_not_stealable():
    led = _ledger()
    led.create_pipeline("pgc", owner="ajay", name="c", step_count=1)
    assert led.claim_graph_step("pgc", step_index=0, step_name="A", worker="w1", now=100.0)
    # active lease not stealable
    assert not led.claim_graph_step("pgc", step_index=0, step_name="A", worker="w2", now=150.0)
    # expired lease reclaimable
    assert led.claim_graph_step("pgc", step_index=0, step_name="A", worker="w2", now=100 + 1000)
    led.release_graph_step("pgc", step_index=0, state=CLAIM_SUCCEEDED)
    # succeeded claim never re-runnable
    assert not led.claim_graph_step("pgc", step_index=0, step_name="A", worker="w3", now=100 + 5000)


@live
def test_each_step_claimed_exactly_once_during_run():
    led = _ledger()
    res = _runner(led).run(_diamond("pgcl"), now=100.0)
    assert res["ok"]
    claims = led.list_step_claims("pgcl", owner="ajay")
    assert len(claims) == 4 and all(c["state"] == CLAIM_SUCCEEDED for c in claims)


# ══ CRASH RECONCILIATION ═════════════════════════════════════════════════════
def test_stale_step_claim_reclaimed():
    led = _ledger()
    led.create_pipeline("pgrec", owner="ajay", name="r", step_count=1)
    led.claim_graph_step("pgrec", step_index=0, step_name="B", worker="w1",
                         now=100.0, lease_sec=120.0)
    gr = GraphPipelineRunner(ledger=led)
    out = gr.reconcile("pgrec", now=100 + 5000)           # lease expired
    assert ("pgrec", 0) in out["reclaimed_claims"]
    # after reclaim, a fresh worker may claim
    assert led.claim_graph_step("pgrec", step_index=0, step_name="B", worker="w2",
                                now=100 + 6000)


@live
def test_crash_before_join_no_duplicate_branch_work():
    led = _ledger()
    runs = tempfile.mkdtemp()
    # simulate: both branches verified, pipeline marked failed before join
    _runner(led, runner=_fail_on("bundle.zip", 1), runs=runs).run(_diamond("pgcb"), now=100.0)
    a0 = led.get_checkpoint("pgcb", step_index=0)["artifact_fingerprint"]
    b1 = led.get_checkpoint("pgcb", step_index=1)["artifact_fingerprint"]
    res = _runner(led, runs=runs).resume(_diamond("pgcb"), owner="ajay", now=200.0)
    assert res["ok"] and res["reused_steps"] == 3 and res["rerun_steps"] == 1  # only join reran
    # verified branch artifacts unchanged (no duplicate branch execution)
    assert led.get_checkpoint("pgcb", step_index=0)["artifact_fingerprint"] == a0
    assert led.get_checkpoint("pgcb", step_index=1)["artifact_fingerprint"] == b1


# ══ APPROVAL + OWNER SAFETY ══════════════════════════════════════════════════
def test_owner_mismatch_executes_nothing():
    led = _ledger()
    led.create_pipeline("pgown", owner="ajay", name="o", step_count=4)
    led.complete_pipeline("pgown", state=PIPELINE_FAILED, failed_step=1,
                          failure_code="transient_lock")
    res = _runner(led).resume(_diamond("pgown"), owner="mallory", now=100.0)
    assert res["ok"] is False and res["reason"] == "owner_mismatch"


@live
def test_cross_owner_graph_inspection_hidden():
    led = _ledger()
    _runner(led).run(_diamond("pgx", owner="ajay"), now=100.0)
    assert led.inspect_graph("pgx", owner="ajay") is not None
    assert led.inspect_graph("pgx", owner="mallory") is None
    assert led.list_branches("pgx", owner="mallory") == []
    assert led.list_step_claims("pgx", owner="mallory") == []


def test_risk_increase_changes_step_fingerprint():
    # a risk bump is execution-affecting → the step fingerprint changes → a prior
    # checkpoint no longer validates → reuse fails closed (new approval scope).
    from saathi.application_harness.pipeline import step_fingerprint
    ops = {o.operation_id: o for o in SQ.operations()}
    step = GraphStep("A", "sqlite", "safe_mutation", _mk("t", "a.db"))
    plan = step.plan(StepContext(workspace="/tmp/ws", artifacts={}))
    fp2 = step_fingerprint(step, plan, ops["safe_mutation"], "/tmp/ws")
    fp4 = step_fingerprint(step, plan, replace(ops["safe_mutation"], risk=4), "/tmp/ws")
    assert fp2 != fp4


# ══ MISSION / SCHEDULER INTEGRATION ══════════════════════════════════════════
@live
def test_mission_launches_graph_through_pipeline_runner():
    from saathi.application_harness.mission import MissionEngine, MissionTemplate
    from saathi.application_harness.pipeline_graph import GraphPipelineRunner
    led = _ledger()
    runner = PipelineRunner(ledger=led, runs_root=tempfile.mkdtemp())
    graph_runner = GraphPipelineRunner(ledger=led, runner=runner)

    def build_graph(params):
        return _diamond(owner="ajay").steps      # A→(B,C)→D

    tmpl = MissionTemplate(template_id="graph_bundle", title="Graph bundle",
                           objective="parallel bundle", mission_type="one_time",
                           risk=0, approval_required=False, build_graph=build_graph)
    eng = MissionEngine(ledger=led, templates={"graph_bundle": tmpl},
                        pipeline_runner=runner, graph_runner=graph_runner)
    c = eng.create("graph_bundle", owner="ajay", params={}, mission_id="mg1")
    res = eng.launch("mg1", owner="ajay")
    assert res["ok"] and res["state"] == "completed"
    # the mission's pipeline IS a graph pipeline (branches recorded) — one engine
    g = led.inspect_graph(res["pipeline_id"], owner="ajay")
    assert g is not None and len(g["branches"]) == 2 and g["state"] == PIPELINE_SUCCEEDED
    # graph mission still delegates through the SAME PipelineRunner
    assert eng.graph_runner.runner is eng.runner
    # no duplicate mission occurrence
    assert eng.inspect("mg1", owner="ajay")["run_count"] == 1


# ══ CONTROL CENTER ═══════════════════════════════════════════════════════════
@live
def test_control_center_graph_cell_owner_safe():
    led = _ledger()
    _runner(led, runner=_fail_on("bee.db", 99)).run(_diamond("pgcc", owner="ajay"), now=100.0)
    health = led.graph_health("ajay")
    assert health["failed_branches"] >= 1
    # cross-owner sees nothing
    assert led.graph_health("mallory")["total_graphs"] == 0
    assert led.list_graphs("mallory") == []


# ══ DATABASE BACKUP / RESTORE ════════════════════════════════════════════════
@live
def test_graph_ledger_survives_backup_restore():
    import sqlite3
    led = _ledger()
    _runner(led).run(_diamond("pgbk", owner="ajay"), now=100.0)
    before = led.health()
    dst = os.path.join(tempfile.mkdtemp(), "restored.db")
    src = sqlite3.connect(str(led.db_path)); dstc = sqlite3.connect(dst)
    with dstc:
        src.backup(dstc)                      # WAL-safe online backup
    src.close(); dstc.close()
    restored = RunLedger(dst)
    h = restored.health()
    assert h["integrity"] == "ok" and h["ok"]
    assert h["graphs"] == before["graphs"] and h["branches"] == before["branches"]
    g = restored.inspect_graph("pgbk", owner="ajay")
    assert g["state"] == PIPELINE_SUCCEEDED and len(g["branches"]) == 2


# ══ TRADING GUARDIAN BOUNDARY (regression) ═══════════════════════════════════
def test_graph_layer_opens_no_trading_surface():
    import inspect
    from saathi.application_harness import pipeline_graph as PG
    src = inspect.getsource(PG).lower()
    # trading-specific tokens (avoid collisions with "ordering"/"order"=topo order)
    for banned in ("broker", "withdraw", "leverage", "rebalance", "place_order",
                   "trade_execution", "portfolio_", "exchange_execution"):
        assert banned not in src, f"graph layer must not reference {banned}"
