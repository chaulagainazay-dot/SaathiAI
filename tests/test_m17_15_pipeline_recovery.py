"""M17.15 governed pipeline retry, resume, and checkpoints.

Deterministic (injected clock, no real sleeps). Proves: a verified step writes a
durable reusable checkpoint; recovery reuses ONLY a contiguous valid verified
prefix; the first invalid step and everything after it rerun; retry is category-
allowlisted and bounded; approval/owner/verification/tamper never auto-retry;
resume never implies approval; recovery claims are concurrency-safe; crash
reconciliation avoids duplicate execution; artifact tampering invalidates reuse;
and recovery runs through the SAME PipelineRunner + run_harness_action.
"""
import os
import tempfile

import pytest

from saathi.application_harness import service as SVC
from saathi.application_harness import run_ledger as L
from saathi.application_harness.run_ledger import (
    RunLedger, PIPELINE_FAILED, PIPELINE_SUCCEEDED,
    CHECKPOINT_VALID, RECOVERY_RECOVERED, RECOVERY_EXHAUSTED, RECOVERY_STOP_UNCERTAIN,
)
from saathi.application_harness.pipeline import (
    PipelineRunner, PipelineSpec, PipelineStep, StepPlan, StepContext,
    step_fingerprint, dependency_fingerprint, file_fingerprint, default_resolver,
)
from saathi.application_harness.pipeline_recovery import (
    PipelineRecovery, is_retryable, RETRYABLE_CATEGORIES,
)
from saathi.application_harness.pilots import sqlite_harness as SQ, zip_archive as Z

HAS_LIVE = SQ.available()["available"] and Z.available()["available"]
live = pytest.mark.skipif(not HAS_LIVE, reason="sqlite3/zip required")


# ── helpers ─────────────────────────────────────────────────────────────────
def _ledger():
    return RunLedger(os.path.join(tempfile.mkdtemp(), "l.db"))


def _mk(table="t", produces="data.db"):
    def plan(ctx):
        dbp = os.path.join(ctx.workspace, produces)
        return StepPlan(argv=SQ.build_mutation_argv(db_path=dbp, table=table),
                        produces=produces, verify_kind="sqlite_db", verify_target=dbp)
    return PipelineStep("build_db", "sqlite", "safe_mutation", plan)


def _pack(src="build_db", produces="bundle.zip"):
    def plan(ctx):
        s = ctx.artifacts[src]
        out = os.path.join(ctx.workspace, produces)
        return StepPlan(argv=Z.build_pack_argv(output_path=out, input_paths=[s]),
                        produces=produces, verify_kind="zip", verify_target=out)
    return PipelineStep("package", "zip", "pack", plan)


def _spec(pid="pl_t", steps=None):
    return PipelineSpec(name="p", owner="ajay", pipeline_id=pid,
                        steps=steps or [_mk(), _pack()])


def _flaky(fail_op, times, category="transient_lock"):
    st = {"n": 0}

    def runner(**kw):
        if kw["op"].operation_id == fail_op and st["n"] < times:
            st["n"] += 1
            return {"status": "failed", "error_code": category}
        return SVC.run_harness_action(**kw)
    return runner


def _runner(led, runner=None):
    return PipelineRunner(ledger=led, runner=runner, runs_root=tempfile.mkdtemp())


# ══ CHECKPOINT CREATION ══════════════════════════════════════════════════════
@live
def test_verified_step_creates_valid_checkpoint():
    led = _ledger()
    _runner(led, _flaky("pack", 1)).run(_spec("p1"))     # step0 ok, step1 fails
    cps = led.list_checkpoints("p1")
    assert len(cps) == 1 and cps[0]["step_index"] == 0
    assert cps[0]["status"] == CHECKPOINT_VALID and cps[0]["verification_result"]
    assert cps[0]["owner"] == "ajay" and cps[0]["artifact"] == "data.db"


@live
def test_failed_step_creates_no_checkpoint():
    led = _ledger()
    _runner(led, _flaky("pack", 1)).run(_spec("p2"))
    assert led.get_checkpoint("p2", step_index=1) is None    # the failed step


def test_step_fingerprint_stable_across_restart():
    step = _mk()
    ws = "/tmp/ws"
    plan = step.plan(StepContext(workspace=ws, artifacts={}))
    _, op = default_resolver("sqlite", "safe_mutation")
    a = step_fingerprint(step, plan, op, ws)
    b = step_fingerprint(step, plan, op, ws)
    assert a == b and len(a) == 24


# ══ CHECKPOINT VALIDATION ════════════════════════════════════════════════════
@live
def test_unchanged_prefix_reusable():
    led = _ledger()
    r = _runner(led, _flaky("pack", 1))
    r.run(_spec("p3"))
    rec = PipelineRecovery(ledger=led, runner=r)
    assert rec.reusable_prefix(_spec("p3"), "ajay")["prefix"] == 1


@live
def test_changed_step_definition_invalidates():
    led = _ledger()
    r = _runner(led, _flaky("pack", 1))
    r.run(_spec("p4"))
    # a spec whose step0 differs (different table → different argv → different fp)
    changed = _spec("p4", steps=[_mk(table="OTHER"), _pack()])
    pref = PipelineRecovery(ledger=led, runner=r).reusable_prefix(changed, "ajay")
    assert pref["prefix"] == 0 and pref["stop_reason"] == "step_definition_changed"


@live
def test_missing_artifact_invalidates():
    led = _ledger()
    r = _runner(led, _flaky("pack", 1))
    r.run(_spec("p5"))
    os.remove(os.path.join(r.runs_root, "p5", "data.db"))
    pref = PipelineRecovery(ledger=led, runner=r).reusable_prefix(_spec("p5"), "ajay")
    assert pref["prefix"] == 0 and pref["stop_reason"] == "missing_artifact"
    assert led.get_checkpoint("p5", step_index=0)["status"] == "missing_artifact"


@live
def test_modified_artifact_invalidates():
    led = _ledger()
    r = _runner(led, _flaky("pack", 1))
    r.run(_spec("p6"))
    with open(os.path.join(r.runs_root, "p6", "data.db"), "ab") as f:
        f.write(b"TAMPER")
    pref = PipelineRecovery(ledger=led, runner=r).reusable_prefix(_spec("p6"), "ajay")
    assert pref["prefix"] == 0 and pref["stop_reason"] == "artifact_integrity"


@live
def test_owner_mismatch_rejects_reuse():
    led = _ledger()
    r = _runner(led, _flaky("pack", 1))
    r.run(_spec("p7"))
    assert PipelineRecovery(ledger=led, runner=r).reusable_prefix(_spec("p7"), "mallory")["prefix"] == 0


@live
def test_invalidated_checkpoint_not_reused():
    led = _ledger()
    r = _runner(led, _flaky("pack", 1))
    r.run(_spec("p8"))
    led.invalidate_checkpoint("p8", step_index=0, reason="operator")
    assert PipelineRecovery(ledger=led, runner=r).reusable_prefix(_spec("p8"), "ajay")["prefix"] == 0


def test_path_escape_artifact_rejected():
    led = _ledger()
    led.create_pipeline("pe", owner="ajay", step_count=1); led.start_pipeline("pe")
    # forge a checkpoint whose artifact escapes the workspace
    led.upsert_checkpoint("cpx", pipeline_id="pe", owner="ajay", step_index=0,
                          step_name="build_db", artifact="../escape.db",
                          verify_kind="sqlite_db", verification_result=True)
    r = _runner(led)
    pref = PipelineRecovery(ledger=led, runner=r).reusable_prefix(_spec("pe"), "ajay")
    assert pref["prefix"] == 0            # escaping artifact never reused


# ══ RESUME ═══════════════════════════════════════════════════════════════════
@live
def test_resume_reuses_prefix_and_completes():
    led = _ledger()
    r = _runner(led, _flaky("pack", 1))
    r.run(_spec("r1"))
    res = PipelineRecovery(ledger=led, runner=r).resume(_spec("r1"), owner="ajay", now=100.0)
    assert res["ok"] and res["reused_steps"] == 1 and res["rerun_steps"] == 1
    assert res["resumed_from"] == "r1"
    assert led.inspect_pipeline("r1")["state"] == PIPELINE_SUCCEEDED
    assert led.get_recovery("r1")["state"] == RECOVERY_RECOVERED


@live
def test_resume_does_not_rerun_verified_step():
    led = _ledger()
    calls = {"mut": 0}
    real = SVC.run_harness_action
    st = {"n": 0}

    def counting(**kw):
        if kw["op"].operation_id == "safe_mutation":
            calls["mut"] += 1
        if kw["op"].operation_id == "pack" and st["n"] == 0:
            st["n"] = 1
            return {"status": "failed", "error_code": "transient_lock"}
        return real(**kw)
    r = _runner(led, counting)
    r.run(_spec("r2"))
    assert calls["mut"] == 1
    PipelineRecovery(ledger=led, runner=r).resume(_spec("r2"), owner="ajay", now=100.0)
    assert calls["mut"] == 1               # step0 NOT re-executed on resume


@live
def test_resume_starts_at_first_invalid_middle_step():
    led = _ledger()
    steps = [_mk(produces="data.db"), _pack(produces="b1.zip"),
             _pack(src="package", produces="b2.zip")]
    # rename second step name to avoid clash
    steps[2] = PipelineStep("package2", "zip", "pack",
                            lambda ctx: StepPlan(
                                argv=Z.build_pack_argv(
                                    output_path=os.path.join(ctx.workspace, "b2.zip"),
                                    input_paths=[ctx.artifacts["package"]]),
                                produces="b2.zip", verify_kind="zip",
                                verify_target=os.path.join(ctx.workspace, "b2.zip")))
    r = _runner(led, _flaky("pack", 99))     # both zip steps fail → only step0 checkpoints
    r.run(_spec("r3", steps=steps))
    # invalidate nothing extra; step0 valid, steps1-2 have no checkpoint
    pref = PipelineRecovery(ledger=led, runner=r).reusable_prefix(_spec("r3", steps=steps), "ajay")
    assert pref["prefix"] == 1              # contiguous prefix stops at first missing


@live
def test_full_restart_reruns_everything():
    led = _ledger()
    r = _runner(led, _flaky("pack", 1))
    r.run(_spec("r4"))
    res = PipelineRecovery(ledger=led, runner=r).resume(_spec("r4"), owner="ajay",
                                                        force_restart=True, now=100.0)
    assert res["ok"] and res["reused_steps"] == 0 and res["rerun_steps"] == 2


@live
def test_duplicate_resume_deduplicated():
    led = _ledger()
    r = _runner(led, _flaky("pack", 1))
    r.run(_spec("r5"))
    rec = PipelineRecovery(ledger=led, runner=r)
    # claim recovery so a concurrent resume cannot also run
    led.upsert_recovery("r5", owner="ajay", failure_category="transient_lock")
    assert led.claim_recovery("r5", worker="a", now=100.0)
    second = rec.resume(_spec("r5"), owner="ajay", now=101.0)
    assert not second["ok"] and second["reason"] == "recovery_claimed"


def test_resume_owner_mismatch_rejected():
    led = _ledger()
    led.create_pipeline("ro", owner="ajay", step_count=2); led.start_pipeline("ro")
    led.complete_pipeline("ro", state=PIPELINE_FAILED, failed_step=1, failure_code="x")
    r = _runner(led)
    assert PipelineRecovery(ledger=led, runner=r).resume(_spec("ro"), owner="mallory",
                                                         now=1.0)["reason"] == "owner_mismatch"


# ══ RETRY (category-allowlisted + bounded) ═══════════════════════════════════
def test_retry_eligibility_allowlist():
    assert is_retryable("transient_lock") and is_retryable("timeout")
    for bad in ("approval_required", "owner_mismatch", "HARNESS_VERIFICATION_FAILED",
                "PIPELINE_PATH_ESCAPE:produces", "cancelled", "", "unknown_thing"):
        assert not is_retryable(bad)


@live
def test_eligible_transient_retry_succeeds_after_backoff():
    led = _ledger()
    r = _runner(led, _flaky("pack", 1))
    r.run(_spec("t1"))
    res = PipelineRecovery(ledger=led, runner=r).retry(_spec("t1"), owner="ajay", now=100.0)
    assert res["ok"] and res["reused_steps"] == 1
    assert led.inspect_pipeline("t1")["state"] == PIPELINE_SUCCEEDED


@live
def test_retry_bounded_and_backoff_then_exhausted():
    led = _ledger()
    r = _runner(led, _flaky("pack", 99))    # always fails transiently
    r.run(_spec("t2"))
    rec = PipelineRecovery(ledger=led, runner=r)
    now = 0.0
    seen_backoff = False
    for _ in range(10):
        res = rec.retry(_spec("t2"), owner="ajay", now=now)
        if res.get("reason") == "backoff_wait":
            seen_backoff = True
            now = res["next_retry_at"]
            continue
        if res.get("reason") == "retry_exhausted" or res.get("recovery_state") == RECOVERY_EXHAUSTED:
            break
        now += 1
    assert seen_backoff
    assert led.get_recovery("t2")["state"] == RECOVERY_EXHAUSTED


@live
def test_non_retryable_failure_does_not_retry():
    led = _ledger()
    r = _runner(led, _flaky("pack", 1, category="HARNESS_VERIFICATION_FAILED"))
    r.run(_spec("t3"))
    res = PipelineRecovery(ledger=led, runner=r).retry(_spec("t3"), owner="ajay", now=100.0)
    assert not res["ok"] and res["reason"] == "not_retryable"
    assert led.inspect_pipeline("t3")["state"] == PIPELINE_FAILED    # untouched


@live
def test_approval_required_failure_does_not_retry():
    led = _ledger()

    def appr(**kw):
        if kw["op"].operation_id == "pack":
            return {"status": "approval_required"}
        return SVC.run_harness_action(**kw)
    r = _runner(led, appr)
    r.run(_spec("t4"))
    res = PipelineRecovery(ledger=led, runner=r).retry(_spec("t4"), owner="ajay", now=100.0)
    assert not res["ok"] and res["reason"] == "not_retryable"


def test_retry_owner_mismatch_rejected():
    led = _ledger()
    led.create_pipeline("tm", owner="ajay", step_count=1); led.start_pipeline("tm")
    led.complete_pipeline("tm", state=PIPELINE_FAILED, failed_step=0, failure_code="timeout")
    led.upsert_recovery("tm", owner="ajay", failure_category="timeout")
    r = _runner(led)
    assert PipelineRecovery(ledger=led, runner=r).retry(_spec("tm"), owner="mallory",
                                                        now=1.0)["reason"] == "owner_mismatch"


# ══ APPROVAL / RISK safety ═══════════════════════════════════════════════════
@live
def test_increased_risk_invalidates_checkpoint_reuse():
    """Risk is part of the step fingerprint, so raising a step's risk after it was
    checkpointed makes the checkpoint non-reusable (a new approval decision is
    required — resume never silently reuses under a stricter policy)."""
    from dataclasses import replace
    led = _ledger()
    r = _runner(led, _flaky("pack", 1))
    r.run(_spec("a1"))
    # rebuild resolver so step0's op carries a higher risk
    ops = {o.operation_id: o for o in SQ.operations()}
    stricter = replace(ops["safe_mutation"], risk=4)

    def res_fn(h, o):
        defn, orig = default_resolver(h, o)
        return defn, (stricter if o == "safe_mutation" else orig)
    rec = PipelineRecovery(ledger=led, runner=r, resolver=res_fn)
    assert rec.reusable_prefix(_spec("a1"), "ajay")["prefix"] == 0   # stricter → no reuse


@live
def test_resume_stops_closed_at_approval_required():
    led = _ledger()

    def appr(**kw):
        if kw["op"].operation_id == "pack":
            return {"status": "approval_required"}
        return SVC.run_harness_action(**kw)
    r = _runner(led, appr)
    r.run(_spec("a2"))
    res = PipelineRecovery(ledger=led, runner=r).resume(_spec("a2"), owner="ajay", now=100.0)
    assert not res["ok"]                     # resume did not elevate; step stays gated
    assert led.inspect_pipeline("a2")["state"] == PIPELINE_FAILED


# ══ CRASH RECOVERY / CONCURRENCY ═════════════════════════════════════════════
def test_active_recovery_lease_not_stealable_expired_reclaimable():
    led = _ledger()
    led.create_pipeline("c1", owner="ajay", step_count=1); led.start_pipeline("c1")
    led.complete_pipeline("c1", state=PIPELINE_FAILED, failed_step=0, failure_code="timeout")
    led.upsert_recovery("c1", owner="ajay", failure_category="timeout")
    assert led.claim_recovery("c1", worker="a", now=100.0, lease_sec=120)
    assert not led.claim_recovery("c1", worker="b", now=150.0, lease_sec=120)  # active
    stale = led.reclaim_stale_recovery(now=300.0, lease_sec=120)               # expired
    assert [s["pipeline_id"] for s in stale] == ["c1"]


@live
def test_reconcile_avoids_duplicate_execution():
    led = _ledger()
    r = _runner(led, _flaky("pack", 1))
    r.run(_spec("c2"))
    led.claim_recovery("c2", worker="dead", now=100.0, lease_sec=120) if led.get_recovery("c2") \
        else led.upsert_recovery("c2", owner="ajay", failure_category="transient_lock")
    led.claim_recovery("c2", worker="dead", now=100.0, lease_sec=120)
    missions_before = led.health()["missions"]
    rec = PipelineRecovery(ledger=led, runner=r).reconcile(now=300.0)   # lease expired
    assert "c2" in rec["reconciled"]
    # reconcile did NOT execute steps (pipeline stays failed, no new work)
    assert led.inspect_pipeline("c2")["state"] == PIPELINE_FAILED
    assert led.health()["missions"] == missions_before


@live
def test_uncertain_execution_fails_closed_stop_uncertain():
    led = _ledger()
    r = _runner(led, _flaky("pack", 1, category="HARNESS_VERIFICATION_FAILED"))
    r.run(_spec("c3"))
    assert led.get_recovery("c3")["state"] == RECOVERY_STOP_UNCERTAIN


# ══ RECOVERY runs through the SAME governed path ═════════════════════════════
def test_recovery_module_has_no_execution_shortcut():
    import inspect
    from saathi.application_harness import pipeline_recovery as PR
    body = inspect.getsource(PR).split('"""', 2)[-1]
    for forbidden in ("run_harness_action", "ApplicationHarnessAdapter", "subprocess",
                      "Popen", "os.system"):
        assert forbidden not in body, forbidden
    assert "execute_resume" in body       # only re-enters the PipelineRunner


def test_recovery_has_no_trading_surface():
    import inspect
    from saathi.application_harness import pipeline_recovery as PR
    src = inspect.getsource(PR)
    for forbidden in ("trading", "Trading", "withdraw", "leverage", "order", "broker"):
        assert forbidden not in src


# ══ MISSION / SCHEDULER integration ══════════════════════════════════════════
@live
def test_mission_pipeline_resume_no_duplicate_mission():
    """A mission's failed pipeline resumes in place; the mission keeps its single
    identity and the recovered pipeline links back to it."""
    from saathi.application_harness.mission import (
        MissionEngine, MissionTemplate, PipelineStep as PS)
    led = _ledger()
    st = {"n": 0}

    def flaky(**kw):
        if kw["op"].operation_id == "pack" and st["n"] == 0:
            st["n"] = 1
            return {"status": "failed", "error_code": "transient_lock"}
        return SVC.run_harness_action(**kw)
    runner = PipelineRunner(ledger=led, runner=flaky, runs_root=tempfile.mkdtemp())
    tmpl = MissionTemplate(template_id="db", title="db",
                           build_steps=lambda p: [_mk(), _pack()])
    eng = MissionEngine(ledger=led, templates={"db": tmpl}, pipeline_runner=runner)
    mid = eng.create("db", owner="ajay")["mission_id"]
    eng.launch(mid, owner="ajay")                       # pipeline fails transiently
    m = eng.inspect(mid, owner="ajay")
    pid = m["last_pipeline_id"]
    assert led.inspect_pipeline(pid)["state"] == PIPELINE_FAILED
    before = led.health()["missions"]
    spec = PipelineSpec(name="db", owner="ajay", pipeline_id=pid,
                        steps=[_mk(), _pack()], correlation_id=mid)
    res = PipelineRecovery(ledger=led, runner=runner).resume(spec, owner="ajay", now=100.0)
    assert res["ok"] and led.inspect_pipeline(pid)["state"] == PIPELINE_SUCCEEDED
    assert led.health()["missions"] == before           # NO duplicate mission


# ══ CONTROL CENTER (owner-safe) ══════════════════════════════════════════════
def _cc(monkeypatch, led, owner):
    from saathi.application_harness import run_ledger as RL
    monkeypatch.setattr(RL, "_default", led)
    monkeypatch.setattr(RL, "default_ledger", lambda: led)
    from saathi.control_center.aggregator import ControlCenterAggregator
    return ControlCenterAggregator(owner=owner).overview()


def test_control_center_recovery_attention_owner_safe(monkeypatch):
    led = _ledger()
    led.create_pipeline("cc", owner="ajay", step_count=2); led.start_pipeline("cc")
    led.complete_pipeline("cc", state=PIPELINE_FAILED, failed_step=1, failure_code="timeout")
    led.upsert_recovery("cc", owner="ajay", failure_category="timeout",
                        state=RECOVERY_EXHAUSTED)
    led.upsert_checkpoint("cp", pipeline_id="cc", owner="ajay", step_index=0,
                          artifact="data.db", verify_kind="sqlite_db", verification_result=True)
    led.invalidate_checkpoint("cc", step_index=0, reason="artifact_integrity",
                              status="missing_artifact")
    ov = _cc(monkeypatch, led, "ajay")
    kinds = {i["kind"] for i in ov["requires_attention"]}
    assert "pipeline_recovery" in kinds and "pipeline_checkpoint" in kinds
    ov2 = _cc(monkeypatch, led, "mallory")
    assert not [i for i in ov2["requires_attention"]
                if i["kind"] in ("pipeline_recovery", "pipeline_checkpoint")]


# ══ CLI ══════════════════════════════════════════════════════════════════════
def test_cli_recovery_health_always_available(capsys, monkeypatch, tmp_path):
    from saathi.application_harness import run_ledger as RL, cli
    led = RunLedger(str(tmp_path / "l.db"))
    monkeypatch.setattr(RL, "default_ledger", lambda: led)
    monkeypatch.delenv("SAATHI_HARNESS_ADMIN", raising=False)
    assert cli.main(["pipeline-recovery-health"]) == 0
    assert "invalid_checkpoints" in capsys.readouterr().out


def test_cli_resume_and_checkpoints_require_admin(monkeypatch, tmp_path):
    from saathi.application_harness import run_ledger as RL, cli
    monkeypatch.setattr(RL, "default_ledger", lambda: RunLedger(str(tmp_path / "l.db")))
    monkeypatch.delenv("SAATHI_HARNESS_ADMIN", raising=False)
    assert cli.main(["pipeline-resume", "x"]) == 3
    assert cli.main(["pipeline-checkpoints", "x"]) == 3


def test_cli_invalidate_checkpoint_audited_no_force_valid(capsys, monkeypatch, tmp_path):
    from saathi.application_harness import run_ledger as RL, cli
    led = RunLedger(str(tmp_path / "l.db"))
    led.create_pipeline("cli", owner="ajay", step_count=1); led.start_pipeline("cli")
    led.upsert_checkpoint("cp", pipeline_id="cli", owner="ajay", step_index=0,
                          artifact="data.db", verify_kind="sqlite_db", verification_result=True)
    monkeypatch.setattr(RL, "default_ledger", lambda: led)
    monkeypatch.setenv("SAATHI_HARNESS_ADMIN", "1")
    assert cli.main(["pipeline-invalidate-checkpoint", "cli", "0"]) == 0
    assert led.get_checkpoint("cli", step_index=0)["status"] != "valid"
    # there is NO "force valid" / "force success" command
    assert "pipeline-force-valid" not in " ".join(cli._LEDGER_CMDS)
    assert "force-success" not in " ".join(cli._LEDGER_CMDS)


# ══ DATABASE backup / restore ════════════════════════════════════════════════
def test_recovery_ledger_survives_backup_restore():
    import sqlite3
    d = tempfile.mkdtemp(); db = os.path.join(d, "l.db")
    led = RunLedger(db)
    led.create_pipeline("bk", owner="ajay", step_count=1); led.start_pipeline("bk")
    led.upsert_checkpoint("cp", pipeline_id="bk", owner="ajay", step_index=0,
                          artifact="data.db", verify_kind="sqlite_db", verification_result=True)
    led.upsert_recovery("bk", owner="ajay", failure_category="timeout")
    bak = os.path.join(d, "b.db")
    src = sqlite3.connect(db); dst = sqlite3.connect(bak)
    with dst:
        src.backup(dst)
    src.close(); dst.close()
    restored = RunLedger(bak)
    h = restored.health()
    assert h["ok"] and h["checkpoints"] == 1 and h["recoveries"] == 1
    assert restored.get_checkpoint("bk", step_index=0)["status"] == CHECKPOINT_VALID
