"""M17.12 governed multi-harness pipeline — deterministic, sequential, fail-closed.

First LIVE exercise of chaining real application harnesses (sqlite → zip) into one
governed workflow. Every step runs through the SAME governed service
(run_harness_action) — the orchestrator only sequences, wires artifacts inside one
confined workspace, and records steps + a parent in the durable ledger. These
tests prove: a real chain succeeds and the second step consumes the first's
artifact; the first non-success halts the pipeline (later steps never run);
workspace confinement rejects escaping artifacts BEFORE execution; approval gates
are honoured; unknown/non-executable harnesses fail closed; records are
owner-scoped + owner-safe; and concurrent creation dedups.
"""
import multiprocessing as mp
import os
import tempfile
import zipfile
from dataclasses import replace

import pytest

from saathi.application_harness.run_ledger import (
    RunLedger, PIPELINE_SUCCEEDED, PIPELINE_FAILED, LedgerSecurityError,
)
from saathi.application_harness.pipeline import (
    PipelineRunner, PipelineSpec, PipelineStep, StepPlan, StepContext,
    default_resolver,
)
from saathi.application_harness.pilots import sqlite_harness as SQ, zip_archive as Z

HAS_SQLITE = SQ.available()["available"]
HAS_ZIP = Z.available()["available"]
live = pytest.mark.skipif(not (HAS_SQLITE and HAS_ZIP),
                          reason="sqlite3/zip required for live pipeline chain")


# ── fixtures / helpers ──────────────────────────────────────────────────────
def _ledger():
    return RunLedger(os.path.join(tempfile.mkdtemp(), "ledger.db"))


def _runs_root():
    return tempfile.mkdtemp()


def _mk_step(name="mk", table="t", produces="data.db"):
    def plan(ctx: StepContext) -> StepPlan:
        dbp = os.path.join(ctx.workspace, produces)
        return StepPlan(argv=SQ.build_mutation_argv(db_path=dbp, table=table),
                        produces=produces, verify_kind="sqlite_db", verify_target=dbp)
    return PipelineStep(name, "sqlite", "safe_mutation", plan)


def _pack_step(name="pack", src_step="mk", produces="bundle.zip"):
    def plan(ctx: StepContext) -> StepPlan:
        src = ctx.artifacts[src_step]
        out = os.path.join(ctx.workspace, produces)
        return StepPlan(argv=Z.build_pack_argv(output_path=out, input_paths=[src]),
                        produces=produces, verify_kind="zip", verify_target=out)
    return PipelineStep(name, "zip", "pack", plan)


def _run(spec, led=None, runs_root=None):
    led = led or _ledger()
    runner = PipelineRunner(ledger=led, runs_root=runs_root or _runs_root())
    return runner.run(spec), led, runner


# ── the headline: a real two-application chain, artifact wired end to end ────
@live
def test_live_sqlite_then_zip_pipeline_succeeds():
    rr = _runs_root()
    spec = PipelineSpec(name="sqlite-then-zip", owner="ajay",
                        steps=[_mk_step(), _pack_step()])
    res, led, _ = _run(spec, runs_root=rr)
    assert res["ok"] is True
    assert res["state"] == PIPELINE_SUCCEEDED
    assert res["steps_run"] == 2
    insp = led.inspect_pipeline(res["pipeline_id"], owner="ajay")
    assert insp["state"] == PIPELINE_SUCCEEDED
    assert [s["status"] for s in insp["steps"]] == ["success", "success"]
    assert [s["artifact"] for s in insp["steps"]] == ["data.db", "bundle.zip"]
    ws = os.path.join(rr, res["pipeline_id"])
    assert set(os.listdir(ws)) == {"data.db", "bundle.zip"}


@live
def test_pipeline_artifact_wiring_uses_prior_output():
    """The zip step must package the EXACT db the sqlite step produced."""
    rr = _runs_root()
    spec = PipelineSpec(name="wire", owner="ajay",
                        steps=[_mk_step(), _pack_step()])
    res, _, _ = _run(spec, runs_root=rr)
    bundle = os.path.join(rr, res["pipeline_id"], "bundle.zip")
    with zipfile.ZipFile(bundle) as z:
        # zip is packed with -j (junk paths) → flat basename of the wired artifact
        assert "data.db" in z.namelist()


# ── fail-closed: first non-success halts; later steps never run ─────────────
@live
def test_pipeline_fail_closed_short_circuits():
    def bad_pack(ctx):
        out = os.path.join(ctx.workspace, "b.zip")
        missing = os.path.join(ctx.workspace, "nope.db")   # never produced
        return StepPlan(argv=Z.build_pack_argv(output_path=out, input_paths=[missing]),
                        produces="b.zip", verify_kind="zip", verify_target=out)
    spec = PipelineSpec(name="fc", owner="ajay", steps=[
        _mk_step(),
        PipelineStep("bad", "zip", "pack", bad_pack),
        _mk_step("never", table="t2", produces="x.db"),
    ])
    res, led, _ = _run(spec)
    assert res["ok"] is False
    assert res["state"] == PIPELINE_FAILED
    assert res["failed_step"] == 1
    assert res["steps_run"] == 2                       # third step never ran
    insp = led.inspect_pipeline(res["pipeline_id"])
    assert [s["step_index"] for s in insp["steps"]] == [0, 1]   # no step 2 record
    assert insp["steps"][1]["status"] != "success"


# ── confinement: escaping paths rejected BEFORE execution ───────────────────
def test_pipeline_confinement_rejects_escaping_produces():
    def esc(ctx):
        dbp = os.path.join(ctx.workspace, "data.db")
        return StepPlan(argv=["sqlite3", dbp, "SELECT 1"], produces="../escape.db",
                        verify_kind="sqlite_db", verify_target=dbp)
    spec = PipelineSpec(name="esc", owner="ajay",
                        steps=[PipelineStep("esc", "sqlite", "safe_mutation", esc)])
    res, led, _ = _run(spec)
    assert res["ok"] is False
    assert res["failure_code"] == "PIPELINE_PATH_ESCAPE:produces"
    # the escaping file was NEVER created outside the workspace
    assert not os.path.exists("/tmp/escape.db")


def test_pipeline_confinement_rejects_absolute_produces():
    def esc(ctx):
        return StepPlan(argv=["sqlite3", "x"], produces="/etc/pwn.db")
    spec = PipelineSpec(name="abs", owner="ajay",
                        steps=[PipelineStep("esc", "sqlite", "safe_mutation", esc)])
    res, _, _ = _run(spec)
    assert res["ok"] is False and res["failure_code"] == "PIPELINE_PATH_ESCAPE:produces"


def test_pipeline_confinement_rejects_escaping_verify_target():
    def esc(ctx):
        dbp = os.path.join(ctx.workspace, "data.db")
        return StepPlan(argv=SQ.build_mutation_argv(db_path=dbp, table="t"),
                        produces="data.db", verify_kind="sqlite_db",
                        verify_target="/etc/passwd")
    spec = PipelineSpec(name="vt", owner="ajay",
                        steps=[PipelineStep("esc", "sqlite", "safe_mutation", esc)])
    res, _, _ = _run(spec)
    assert res["ok"] is False
    assert res["failure_code"] == "PIPELINE_PATH_ESCAPE:verify_target"


# ── unknown / non-executable harness fails closed ───────────────────────────
def test_pipeline_unknown_harness_operation_fails_closed():
    spec = PipelineSpec(name="unk", owner="ajay", steps=[
        PipelineStep("u", "does-not-exist", "nope", lambda c: StepPlan(argv=["x"]))])
    res, _, _ = _run(spec)
    assert res["ok"] is False
    assert res["failure_code"] == "PIPELINE_UNKNOWN_HARNESS_OPERATION"


def test_pipeline_non_executable_harness_fails_closed():
    from saathi.application_harness.models import (
        HarnessDefinition, HarnessOperation, TrustStatus)
    untrusted = HarnessDefinition(
        harness_id="x", display_name="x", application_name="x", version="1",
        trust_status=TrustStatus.EXTERNAL_UNTRUSTED.value)
    op = HarnessOperation("op", "x", "op", risk=0)

    def res_fn(h, o):
        return untrusted, op
    spec = PipelineSpec(name="ne", owner="ajay", steps=[
        PipelineStep("u", "x", "op", lambda c: StepPlan(argv=["x"]))])
    runner = PipelineRunner(ledger=_ledger(), resolver=res_fn, runs_root=_runs_root())
    res = runner.run(spec)
    assert res["ok"] is False
    assert res["failure_code"] == "PIPELINE_HARNESS_NOT_EXECUTABLE"


# ── approval gates honoured (no silent elevation) ───────────────────────────
@live
def test_pipeline_approval_gated_step_halts():
    """A step whose operation needs approval halts the pipeline when not approved;
    a later step must never run."""
    ops = {o.operation_id: o for o in SQ.operations()}
    gated = replace(ops["safe_mutation"], risk=3)          # force approval requirement

    def res_fn(h, o):
        defn, _ = default_resolver(h, o)
        return defn, gated

    def plan(ctx):
        dbp = os.path.join(ctx.workspace, "data.db")
        return StepPlan(argv=SQ.build_mutation_argv(db_path=dbp, table="t"),
                        produces="data.db")            # NOT approved
    spec = PipelineSpec(name="appr", owner="ajay", steps=[
        PipelineStep("gated", "sqlite", "safe_mutation", plan),
        _mk_step("never", table="t2", produces="x.db")])
    runner = PipelineRunner(ledger=_ledger(), resolver=res_fn, runs_root=_runs_root())
    res = runner.run(spec)
    assert res["ok"] is False
    assert res["failure_code"] == "approval_required"
    assert res["steps_run"] == 1                        # second step never ran


@live
def test_pipeline_approved_step_proceeds():
    ops = {o.operation_id: o for o in SQ.operations()}
    gated = replace(ops["safe_mutation"], risk=3)

    def res_fn(h, o):
        defn, _ = default_resolver(h, o)
        return defn, gated

    def plan(ctx):
        dbp = os.path.join(ctx.workspace, "data.db")
        return StepPlan(argv=SQ.build_mutation_argv(db_path=dbp, table="t"),
                        produces="data.db", verify_kind="sqlite_db",
                        verify_target=dbp, approved=True)   # explicit pre-approval
    spec = PipelineSpec(name="ok", owner="ajay", steps=[
        PipelineStep("gated", "sqlite", "safe_mutation", plan)])
    runner = PipelineRunner(ledger=_ledger(), resolver=res_fn, runs_root=_runs_root())
    res = runner.run(spec)
    assert res["ok"] is True and res["state"] == PIPELINE_SUCCEEDED


# ── shell-safety: content is data, never a shell string ─────────────────────
@live
def test_pipeline_argv_control_char_blocked_not_shelled():
    def evil(ctx):
        # a NUL byte in an argument is rejected by the adapter (argv-only, no shell)
        return StepPlan(argv=["sqlite3", "\x00; rm -rf /", "SELECT 1"])
    spec = PipelineSpec(name="evil", owner="ajay", steps=[
        PipelineStep("e", "sqlite", "safe_mutation", evil)])
    res, led, _ = _run(spec)
    assert res["ok"] is False
    insp = led.inspect_pipeline(res["pipeline_id"])
    assert insp["steps"][0]["status"] in ("blocked", "failed")


# ── owner scoping + owner-safe records ──────────────────────────────────────
@live
def test_pipeline_owner_scoped_inspect():
    spec = PipelineSpec(name="own", owner="ajay", steps=[_mk_step()])
    res, led, _ = _run(spec)
    assert led.inspect_pipeline(res["pipeline_id"], owner="ajay") is not None
    assert led.inspect_pipeline(res["pipeline_id"], owner="mallory") is None
    # list is owner-scoped
    assert led.list_pipelines("mallory") == []
    assert len(led.list_pipelines("ajay")) == 1


@live
def test_pipeline_records_are_owner_safe():
    import json
    spec = PipelineSpec(name="safe", owner="ajay", steps=[_mk_step(), _pack_step()])
    res, led, _ = _run(spec)
    blob = json.dumps(led.inspect_pipeline(res["pipeline_id"]))
    for leak in ("argv", "stdout", "stderr", "sqlite3", "SELECT", "INSERT", "output"):
        assert leak not in blob


# ── ledger invariants ───────────────────────────────────────────────────────
def test_pipeline_duplicate_id_rejected():
    led = _ledger()
    assert led.create_pipeline("p", owner="ajay", step_count=1)["created"] is True
    dup = led.create_pipeline("p", owner="ajay", step_count=1)
    assert dup["created"] is False and dup["reason"] == "duplicate_pipeline_id"


def test_pipeline_empty_owner_rejected():
    led = _ledger()
    with pytest.raises(LedgerSecurityError):
        led.create_pipeline("p", owner="", step_count=1)


def test_pipeline_terminal_immutable():
    led = _ledger()
    led.create_pipeline("p", owner="ajay", step_count=1)
    led.start_pipeline("p")
    assert led.complete_pipeline("p", state=PIPELINE_SUCCEEDED)["ok"] is True
    again = led.complete_pipeline("p", state=PIPELINE_FAILED)
    assert again["ok"] is False and "already_terminal" in again["reason"]


def test_pipeline_secret_shaped_name_rejected():
    led = _ledger()
    with pytest.raises(LedgerSecurityError):
        led.create_pipeline("p", owner="ajay",
                            name="api_key=sk-abcdefghijklmnopqrstuvwxyz012345")


def test_pipeline_health_and_list():
    led = _ledger()
    for i, st in enumerate([PIPELINE_SUCCEEDED, PIPELINE_FAILED, PIPELINE_SUCCEEDED]):
        pid = f"p{i}"
        led.create_pipeline(pid, owner="ajay", step_count=1)
        led.start_pipeline(pid)
        led.complete_pipeline(pid, state=st, failed_step=(0 if st == PIPELINE_FAILED else -1))
    h = led.pipeline_health("ajay")
    assert h["succeeded"] == 2 and h["failed"] == 1 and h["total"] == 3
    assert len(led.list_pipelines("ajay")) == 3


def test_pipeline_step_builder_error_fails_closed():
    def boom(ctx):
        raise ValueError("builder blew up")
    spec = PipelineSpec(name="boom", owner="ajay", steps=[
        PipelineStep("b", "sqlite", "safe_mutation", boom)])
    res, _, _ = _run(spec)
    assert res["ok"] is False
    assert res["failure_code"].startswith("PIPELINE_PLAN_ERROR")


# ── Control Center integration (owner-safe attention) ───────────────────────
def test_control_center_surfaces_failed_pipeline(monkeypatch):
    from saathi.application_harness import run_ledger as RL
    led = _ledger()
    led.create_pipeline("pf", owner="ajay", name="nightly", step_count=2)
    led.start_pipeline("pf")
    led.complete_pipeline("pf", state=PIPELINE_FAILED, failed_step=1,
                          failure_code="HARNESS_VERIFICATION_FAILED")
    monkeypatch.setattr(RL, "_default", led)
    monkeypatch.setattr(RL, "default_ledger", lambda: led)
    from saathi.control_center.aggregator import ControlCenterAggregator
    cc = ControlCenterAggregator(owner="ajay")
    ov = cc.overview()
    pipeline_items = [i for i in ov["requires_attention"]
                      if i.get("kind") == "harness_pipeline"]
    assert pipeline_items and "pf" in pipeline_items[0]["message"]
    # owner-safe: a different owner sees nothing
    cc2 = ControlCenterAggregator(owner="mallory")
    ov2 = cc2.overview()
    assert not [i for i in ov2["requires_attention"]
                if i.get("kind") == "harness_pipeline"]


# ── multi-process concurrency: duplicate create dedups to exactly one ───────
def _create_worker(db_path, pid, q):
    led = RunLedger(db_path)
    q.put(led.create_pipeline(pid, owner="ajay", step_count=1)["created"])


def test_concurrent_pipeline_create_dedups():
    db = os.path.join(tempfile.mkdtemp(), "l.db")
    RunLedger(db)                                      # materialize schema first
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    procs = [ctx.Process(target=_create_worker, args=(db, "shared", q)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(30)
    results = [q.get() for _ in range(4)]
    assert results.count(True) == 1                    # exactly one creator wins
    assert results.count(False) == 3
