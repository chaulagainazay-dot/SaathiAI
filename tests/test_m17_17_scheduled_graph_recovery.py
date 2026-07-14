"""M17.17 governed scheduled graph mission scheduling + recovery integration.

Deterministic (injected clock, injected deterministic runners, bounded executor —
no real sleeps, no timing assertions). Proves the full chain settles EXACTLY ONCE
and creates NO duplicate work:

    schedule → occurrence → mission → graph pipeline → branches → join → recovery

and that graph terminal states propagate honestly into mission + occurrence state,
that a failed graph mission resumes through the EXISTING recovery interface (reusing
verified branch checkpoints, rerunning only the interrupted branch, running the join
once), that approval/owner/stop-uncertain fail closed, and that the integration
layer opens NO trading surface.
"""
import inspect
import os
import tempfile
import threading

import pytest

from saathi.application_harness import service as SVC
from saathi.application_harness.run_ledger import (
    RunLedger, PIPELINE_SUCCEEDED, PIPELINE_FAILED,
    MISSION_COMPLETED, MISSION_FAILED, MISSION_BLOCKED,
    OCC_SUCCEEDED, OCC_FAILED, OCC_BLOCKED, OCC_APPROVAL_REQUIRED, OCC_RETRY_WAIT,
    BRANCH_SUCCEEDED, BRANCH_APPROVAL_REQUIRED, BRANCH_STOP_UNCERTAIN,
)
from saathi.application_harness.pipeline import PipelineRunner
from saathi.application_harness.pipeline_graph import GraphPipelineRunner, GraphSpec
from saathi.application_harness.mission import MissionEngine, MissionTemplate
from saathi.application_harness.scheduler import MissionScheduler
from saathi.application_harness import scheduled_graph as SGMOD
from saathi.application_harness.scheduled_graph import (
    ScheduledGraphCoordinator, graph_mission_templates, register_graph_templates,
)
from saathi.application_harness.pilots import sqlite_harness as SQ, zip_archive as Z

HAS_LIVE = SQ.available()["available"] and Z.available()["available"]
live = pytest.mark.skipif(not HAS_LIVE, reason="sqlite3/zip required")

TEMPLATE = "graph_data_bundle"


# ── deterministic harness ────────────────────────────────────────────────────
def _build(injected=None, templates=None):
    led = RunLedger(os.path.join(tempfile.mkdtemp(), "l.db"))
    runs = tempfile.mkdtemp()
    runner = PipelineRunner(ledger=led, runner=injected, runs_root=runs)
    gr = GraphPipelineRunner(ledger=led, runner=runner)
    eng = MissionEngine(ledger=led, templates=(templates or {}),
                        pipeline_runner=runner, graph_runner=gr)
    sch = MissionScheduler(ledger=led, engine=eng)
    coord = ScheduledGraphCoordinator(ledger=led, engine=eng, scheduler=sch)
    return led, coord, sch, eng, runs


def _fail_on(produces, times, category="transient_lock"):
    """Injected runner: fail a specific produced-artifact step `times` times, then
    delegate to the real governed service. Deterministic (no sleeps)."""
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


def _status_on(produces, status, code):
    """Injected runner: return a fixed non-success status for a branch artifact
    (used to force approval_required / stop_uncertain), else delegate."""
    def r(**kw):
        if any(a.endswith("/" + produces) for a in kw["argv"]):
            return {"status": status, "error_code": code}
        return SVC.run_harness_action(**kw)
    return r


def _one_occurrence(sch, *, owner="ajay", now=100.0, template=TEMPLATE):
    r = sch.create_schedule(owner=owner, mission_template_id=template,
                            schedule_type="one_time", expression={"run_at": now + 10},
                            now=now)
    assert r["ok"], r
    gen = sch.create_due_occurrences(now=now + 20)
    assert len(gen["created"]) == 1
    return gen["created"][0], r["schedule_id"]


# ══ GRAPH-BACKED TEMPLATE SAFETY ═════════════════════════════════════════════
def test_graph_backed_template_registered():
    t = graph_mission_templates()
    assert TEMPLATE in t and t[TEMPLATE].build_graph is not None
    assert t[TEMPLATE].build_steps is None       # it is a GRAPH template, not sequential


def test_register_is_idempotent_and_additive():
    eng = MissionEngine(ledger=RunLedger(os.path.join(tempfile.mkdtemp(), "l.db")),
                        templates={})
    register_graph_templates(eng)
    register_graph_templates(eng)               # twice → no duplicate / no error
    assert TEMPLATE in eng.templates


def test_ordinary_sequential_template_unchanged():
    # the M17.13 default data_bundle sequential template is still a build_steps template
    eng = MissionEngine(ledger=RunLedger(os.path.join(tempfile.mkdtemp(), "l.db")))
    assert eng.templates["data_bundle"].build_steps is not None
    assert eng.templates["data_bundle"].build_graph is None


def test_schedule_cannot_supply_graph_definition():
    # a schedule binds a registered template id; it carries NO graph/steps field
    led, coord, sch, eng, _ = _build()
    import dataclasses
    fields = {f.name for f in dataclasses.fields(sch.create_schedule.__self__.__class__.__init__.__class__)} \
        if False else set()
    # create_schedule signature accepts only owner/template_id/type/expr/params — no graph
    sig = set(inspect.signature(sch.create_schedule).parameters)
    assert "graph" not in sig and "steps" not in sig and "dependencies" not in sig


def test_unknown_template_rejected():
    led, coord, sch, eng, _ = _build()
    r = sch.create_schedule(owner="ajay", mission_template_id="no_such_graph",
                            schedule_type="one_time", expression={"run_at": 200}, now=100)
    assert not r["ok"] and r["reason"] == "unknown_template"


# ══ SCHEDULED GRAPH LAUNCH (idempotent, layered) ═════════════════════════════
@live
def test_due_occurrence_launches_one_graph_mission():
    led, coord, sch, eng, _ = _build()
    oid, sid = _one_occurrence(sch)
    res = coord.dispatch(oid, now=120.0)
    assert res["ok"] and res["state"] == OCC_SUCCEEDED
    occ = led.inspect_occurrence(oid)
    m = eng.inspect(occ["mission_id"])
    assert m["state"] == MISSION_COMPLETED
    g = led.inspect_graph(m["last_pipeline_id"], owner="ajay")
    assert g["state"] == PIPELINE_SUCCEEDED and len(g["branches"]) == 2
    # durable link chain: schedule → occurrence → mission → graph pipeline
    assert occ["schedule_id"] == sid and m["correlation_id"] == oid


@live
def test_repeated_dispatch_creates_no_duplicate():
    led, coord, sch, eng, _ = _build()
    oid, _ = _one_occurrence(sch)
    coord.dispatch(oid, now=120.0)
    mid = led.inspect_occurrence(oid)["mission_id"]
    pid = eng.inspect(mid)["last_pipeline_id"]
    again = coord.dispatch(oid, now=130.0)          # terminal occurrence not re-run
    assert again["ok"] is False
    # exactly one mission, one run, one graph pipeline
    assert eng.inspect(mid)["run_count"] == 1
    assert len(led.pipelines_for_correlation(mid)) == 1
    assert eng.inspect(mid)["last_pipeline_id"] == pid


@live
def test_scheduler_does_not_call_graph_executor_or_recovery_directly():
    # the scheduler module imports MissionEngine but NOT the graph executor / recovery
    import saathi.application_harness.scheduler as SCH
    src = inspect.getsource(SCH)
    assert "GraphPipelineRunner" not in src
    assert "graph_runner.run(" not in src
    assert "PipelineRecovery(" not in src
    # fresh execution flows only through the MissionEngine
    assert "self.engine.launch(" in src


@live
def test_coordinator_fresh_launch_only_through_missionengine():
    # the coordinator never calls graph_runner.run (fresh execution); recovery goes
    # through engine.resume_graph_mission (the mission authority), not resume directly
    src = inspect.getsource(SGMOD)
    assert "graph_runner.run(" not in src
    assert "engine.resume_graph_mission(" in src


# ══ STATE PROPAGATION ════════════════════════════════════════════════════════
@live
def test_graph_success_completes_mission_and_occurrence():
    led, coord, sch, eng, _ = _build()
    oid, _ = _one_occurrence(sch)
    coord.dispatch(oid, now=120.0)
    assert led.inspect_occurrence(oid)["state"] == OCC_SUCCEEDED


@live
def test_graph_approval_required_propagates():
    led, coord, sch, eng, _ = _build(
        injected=_status_on("b.db", "blocked", "APPROVAL_REQUIRED"))
    oid, _ = _one_occurrence(sch)
    res = coord.dispatch(oid, now=120.0)
    assert res["state"] == OCC_APPROVAL_REQUIRED
    m = eng.inspect(led.inspect_occurrence(oid)["mission_id"])
    assert m["state"] == MISSION_BLOCKED and m["failure_code"] == "GRAPH_APPROVAL_REQUIRED"
    g = led.inspect_graph(m["last_pipeline_id"], owner="ajay")
    st = {b["branch_key"]: b["state"] for b in g["branches"]}
    assert BRANCH_APPROVAL_REQUIRED in st.values()
    # approval-required does NOT auto-retry and the join never ran
    assert g["state"] == PIPELINE_FAILED
    assert "join" not in {s["step_name"] for s in g["steps"] if s["status"] == "success"}


@live
def test_graph_stop_uncertain_fails_closed():
    led, coord, sch, eng, _ = _build(
        injected=_status_on("b.db", "failed", "VERIFICATION_UNCERTAIN"))
    oid, _ = _one_occurrence(sch)
    res = coord.dispatch(oid, now=120.0)
    assert res["state"] == OCC_BLOCKED           # fail closed (not success, not approval)
    m = eng.inspect(led.inspect_occurrence(oid)["mission_id"])
    assert m["state"] == MISSION_BLOCKED and m["failure_code"] == "GRAPH_STOP_UNCERTAIN"


@live
def test_retryable_failure_defers_not_settles_success():
    led, coord, sch, eng, _ = _build(injected=_fail_on("b.db", 1))
    oid, _ = _one_occurrence(sch)
    res = coord.dispatch(oid, now=120.0)
    assert res["state"] == OCC_RETRY_WAIT and res.get("recoverable")
    # NOT settled succeeded while recovery is pending
    assert led.inspect_occurrence(oid)["state"] == OCC_RETRY_WAIT


@live
def test_non_retryable_failure_is_terminal_not_deferred():
    led, coord, sch, eng, _ = _build(injected=_fail_on("b.db", 99, category="unknown"))
    oid, _ = _one_occurrence(sch)
    res = coord.dispatch(oid, now=120.0)
    assert res["state"] == OCC_FAILED            # no relaunch storm for a hard failure


# ══ RECOVERY / RESUME ════════════════════════════════════════════════════════
@live
def test_recover_reuses_checkpoint_and_reruns_only_interrupted_branch():
    led, coord, sch, eng, _ = _build(injected=_fail_on("b.db", 1))
    oid, _ = _one_occurrence(sch)
    coord.dispatch(oid, now=120.0)
    mid = led.inspect_occurrence(oid)["mission_id"]
    pid = eng.inspect(mid)["last_pipeline_id"]
    rr = coord.recover(oid, now=200.0)
    assert rr["state"] == OCC_SUCCEEDED
    assert rr["reused_steps"] == 2 and rr["rerun_steps"] == 2    # root+branch_a reused
    assert led.inspect_graph(pid, owner="ajay")["state"] == PIPELINE_SUCCEEDED
    assert led.inspect_occurrence(oid)["state"] == OCC_SUCCEEDED


@live
def test_recover_is_idempotent():
    led, coord, sch, eng, _ = _build(injected=_fail_on("b.db", 1))
    oid, _ = _one_occurrence(sch)
    coord.dispatch(oid, now=120.0)
    a = coord.recover(oid, now=200.0)
    b = coord.recover(oid, now=210.0)
    assert a["state"] == OCC_SUCCEEDED and b["state"] == OCC_SUCCEEDED
    assert b.get("idempotent") is True
    mid = led.inspect_occurrence(oid)["mission_id"]
    # one recovered mission, its graph is the SAME pipeline id (no second graph)
    rec_id = eng._recovered_mission_id(mid)
    assert eng.inspect(rec_id)["state"] == MISSION_COMPLETED
    assert eng.inspect(rec_id)["last_pipeline_id"] == eng.inspect(mid)["last_pipeline_id"]


@live
def test_original_failed_mission_stays_immutable_after_recovery():
    led, coord, sch, eng, _ = _build(injected=_fail_on("b.db", 1))
    oid, _ = _one_occurrence(sch)
    coord.dispatch(oid, now=120.0)
    mid = led.inspect_occurrence(oid)["mission_id"]
    coord.recover(oid, now=200.0)
    # the original failure is preserved (audit truth), recovery lives on a linked mission
    assert eng.inspect(mid)["state"] == MISSION_FAILED
    assert eng.inspect(mid)["failure_code"] == "transient_lock"


@live
def test_approval_required_does_not_auto_recover():
    led, coord, sch, eng, _ = _build(
        injected=_status_on("b.db", "blocked", "APPROVAL_REQUIRED"))
    oid, _ = _one_occurrence(sch)
    coord.dispatch(oid, now=120.0)
    mid = led.inspect_occurrence(oid)["mission_id"]
    r = eng.resume_graph_mission(mid, owner="ajay", now=200.0)
    assert r["ok"] is False and r["reason"] == "not_recoverable:blocked"


# ══ CRASH WINDOWS ════════════════════════════════════════════════════════════
@live
def test_crash_after_graph_terminal_before_mission_settlement():
    # simulate: mission RUNNING, graph already SUCCEEDED, finish_mission_run never ran
    led, coord, sch, eng, _ = _build()
    c = eng.create(TEMPLATE, owner="ajay", params={}, mission_id="mcrashF")
    eng.enqueue("mcrashF", owner="ajay")
    begun = led.begin_mission_run("mcrashF")             # mission → RUNNING
    assert begun["ok"]
    from saathi.application_harness.pipeline_graph import GraphSpec
    tmpl = eng.templates[TEMPLATE]
    gspec = GraphSpec(name="x", owner="ajay", steps=tmpl.build_graph({}),
                      concurrency_limit=2, correlation_id="mcrashF")
    g = eng.graph_runner.run(gspec, session_id="crash")
    assert g["ok"]                                        # graph terminal, mission still RUNNING
    assert eng.inspect("mcrashF")["state"] == "running"
    out = eng.reconcile_running_mission("mcrashF", owner="ajay")
    assert out["state"] == MISSION_COMPLETED and out["pipeline_id"] == g["pipeline_id"]


@live
def test_crash_after_mission_terminal_before_occurrence_settlement():
    # mission COMPLETED but occurrence still RUNNING (stale lease) → reconcile settles it
    led, coord, sch, eng, _ = _build()
    oid, _ = _one_occurrence(sch)
    # claim + create + link + run mission to completion, but do NOT finish the occurrence
    assert led.claim_occurrence(oid, worker="w", now=120.0, lease_sec=120.0)
    from saathi.application_harness.scheduler import _mission_id_for
    mid = _mission_id_for(oid)
    eng.create(TEMPLATE, owner="ajay", params={}, mission_id=mid, correlation_id=oid)
    led.link_occurrence_mission(oid, mission_id=mid, now=120.0)
    eng.launch(mid, owner="ajay")
    assert eng.inspect(mid)["state"] == MISSION_COMPLETED
    assert led.inspect_occurrence(oid)["state"] == "running"
    # lease expires → coordinator reconcile settles the occurrence from the mission
    out = coord.reconcile(now=120.0 + 1000.0)
    assert led.inspect_occurrence(oid)["state"] == OCC_SUCCEEDED


# ══ CONCURRENCY / DEDUP ══════════════════════════════════════════════════════
@live
def test_concurrent_dispatch_creates_one_mission_and_graph():
    led, coord, sch, eng, _ = _build()
    oid, _ = _one_occurrence(sch)
    results = {}
    barrier = threading.Barrier(2)

    def go(i):
        barrier.wait()
        results[i] = coord.dispatch(oid, now=120.0)

    ts = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    oks = [r for r in results.values() if r.get("ok")]
    assert len(oks) == 1                                  # exactly one dispatch won
    mid = led.inspect_occurrence(oid)["mission_id"]
    assert eng.inspect(mid)["run_count"] == 1
    assert len(led.pipelines_for_correlation(mid)) == 1


@live
def test_concurrent_recover_creates_one_resumed_graph():
    led, coord, sch, eng, _ = _build(injected=_fail_on("b.db", 1))
    oid, _ = _one_occurrence(sch)
    coord.dispatch(oid, now=120.0)
    results = {}
    barrier = threading.Barrier(2)

    def go(i):
        barrier.wait()
        results[i] = coord.recover(oid, now=200.0)

    ts = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert led.inspect_occurrence(oid)["state"] == OCC_SUCCEEDED
    mid = led.inspect_occurrence(oid)["mission_id"]
    rec_id = eng._recovered_mission_id(mid)
    # one recovered mission run, one resumed graph (same pid), one join
    assert eng.inspect(rec_id)["run_count"] == 1


# ══ OWNER SAFETY ═════════════════════════════════════════════════════════════
@live
def test_owner_mismatch_recover_fails_closed():
    led, coord, sch, eng, _ = _build(injected=_fail_on("b.db", 1))
    oid, _ = _one_occurrence(sch, owner="ajay")
    coord.dispatch(oid, now=120.0)
    mid = led.inspect_occurrence(oid)["mission_id"]
    # a foreign owner cannot resume the graph mission
    r = eng.resume_graph_mission(mid, owner="mallory", now=200.0)
    assert r["ok"] is False and r["reason"] == "owner_mismatch"


def test_health_is_owner_scoped():
    led, coord, sch, eng, _ = _build()
    h_foreign = coord.health("mallory")
    assert h_foreign["graphs"]["total_graphs"] == 0
    assert h_foreign["occurrences"]["total"] == 0


# ══ CONTROL CENTER ═══════════════════════════════════════════════════════════
@live
def test_control_center_attention_for_approval_and_owner_scope():
    led, coord, sch, eng, _ = _build(
        injected=_status_on("b.db", "blocked", "APPROVAL_REQUIRED"))
    oid, _ = _one_occurrence(sch)
    coord.dispatch(oid, now=120.0)
    h = coord.health("ajay")
    assert "approval_required_scheduled_graph" in h["attention"]
    assert h["occurrences"]["approval_required"] >= 1
    # cross-owner sees nothing
    assert coord.health("mallory")["occurrences"]["total"] == 0


# ══ TRUSTED EVENT GRAPH LAUNCH ═══════════════════════════════════════════════
@live
def test_trusted_event_launches_graph_mission_and_dedups():
    from saathi.application_harness.event_triggers import MissionEventTriggerService
    from saathi.application_harness import run_ledger as L
    led, coord, sch, eng, _ = _build()
    svc = MissionEventTriggerService(ledger=led, engine=eng)
    etype = sorted(L.TRUSTED_EVENT_TYPES)[0]
    reg = svc.register(owner="ajay", event_type=etype, mission_template_id=TEMPLATE)
    assert reg["ok"], reg
    r1 = svc.ingest_event(event_type=etype, source_event_id="evt-1", now=100.0)
    r2 = svc.ingest_event(event_type=etype, source_event_id="evt-1", now=101.0)
    assert len(r1["created"]) == 1 and len(r2["created"]) == 0    # deduped
    m = eng.inspect(r1["created"][0])
    assert m["state"] == MISSION_COMPLETED
    assert led.inspect_graph(m["last_pipeline_id"], owner="ajay")["state"] == PIPELINE_SUCCEEDED


@live
def test_event_cannot_override_owner_or_template():
    from saathi.application_harness.event_triggers import MissionEventTriggerService
    from saathi.application_harness import run_ledger as L
    led, coord, sch, eng, _ = _build()
    svc = MissionEventTriggerService(ledger=led, engine=eng)
    etype = sorted(L.TRUSTED_EVENT_TYPES)[0]
    svc.register(owner="ajay", event_type=etype, mission_template_id=TEMPLATE)
    # payload attempting to change owner/template is rejected (not applied)
    out = svc.ingest_event(event_type=etype, source_event_id="evt-2",
                           payload={"owner": "mallory", "template": "x"}, now=100.0)
    # created under the TRIGGER owner only, payload authority fields ignored/rejected
    for mid in out["created"]:
        assert eng.inspect(mid)["owner"] == "ajay"


# ══ MISSION / SCHEDULER REGRESSION ═══════════════════════════════════════════
@live
def test_ordinary_sequential_scheduled_mission_still_works():
    led, coord, sch, eng, _ = _build()
    r = sch.create_schedule(owner="ajay", mission_template_id="data_bundle",
                            schedule_type="one_time", expression={"run_at": 110}, now=100)
    assert r["ok"]
    gen = sch.create_due_occurrences(now=120)
    oid = gen["created"][0]
    res = sch.dispatch_occurrence(oid, now=120)          # plain M17.14 path unaffected
    assert res["ok"] and res["state"] == OCC_SUCCEEDED


def test_graph_recovery_flag_defaults_off_for_scheduler():
    # M17.14 dispatch signature stays backward compatible (graph_recovery defaults off)
    sig = inspect.signature(MissionScheduler.dispatch_occurrence)
    assert sig.parameters["graph_recovery"].default is False


# ══ TRADING GUARDIAN BOUNDARY ════════════════════════════════════════════════
def test_integration_module_opens_no_trading_surface():
    src = inspect.getsource(SGMOD).lower()
    for banned in ("broker", "withdraw", "leverage", "rebalance", "place_order",
                   "trade_execution", "portfolio_", "exchange_execution",
                   "order_submission", "fund_transfer"):
        assert banned not in src, banned


def test_engine_recovery_methods_open_no_trading_surface():
    from saathi.application_harness import mission as MOD
    src = inspect.getsource(MOD).lower()
    for banned in ("broker", "withdraw", "leverage", "rebalance", "place_order",
                   "exchange_execution", "fund_transfer"):
        assert banned not in src, banned
