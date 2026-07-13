"""M17.13 autonomous mission engine — Mission ABOVE the pipeline, fail-closed.

A Mission carries one business objective + validated parameters and delegates to
the SAME governed M17.12 pipeline (which delegates to run_harness_action). These
tests prove: parameters are strongly validated before execution; a mission
`completed` ONLY when its delegated pipeline succeeds; a pipeline failure drives
the mission to `failed` (no partial success); owner isolation on every op;
approval-required missions cannot be queued/run without explicit approval (no
silent elevation); retry is rejected for non-failed missions and clones a NEW
instance for failed ones; ledger + history records are owner-scoped + owner-safe;
state transitions fail closed and terminal states are immutable; and concurrent
creation dedups to exactly one.
"""
import multiprocessing as mp
import os
import tempfile

import pytest

from saathi.application_harness.run_ledger import (
    RunLedger, LedgerSecurityError,
    MISSION_DRAFT, MISSION_APPROVED, MISSION_QUEUED, MISSION_COMPLETED,
    MISSION_FAILED, MISSION_CANCELLED, MISSION_APPROVAL_REQUIRED,
)
from saathi.application_harness.mission import (
    MissionEngine, MissionTemplate, MissionParameter, MissionParameter as MP,
    PipelineStep, validate_params,
)
from saathi.application_harness.pipeline import StepContext, StepPlan
from saathi.application_harness.pilots import sqlite_harness as SQ, zip_archive as Z

HAS_SQLITE = SQ.available()["available"]
HAS_ZIP = Z.available()["available"]
live = pytest.mark.skipif(not (HAS_SQLITE and HAS_ZIP),
                          reason="sqlite3/zip required for live mission chain")


# ── helpers ─────────────────────────────────────────────────────────────────
def _ledger():
    return RunLedger(os.path.join(tempfile.mkdtemp(), "ledger.db"))


def _engine(templates=None):
    return MissionEngine(ledger=_ledger(), templates=templates,
                         runs_root=tempfile.mkdtemp())


def _live_template(*, approval_required=False, risk=0):
    """The real sqlite → zip business objective, as a template."""
    def _mk(ctx: StepContext) -> StepPlan:
        dbp = os.path.join(ctx.workspace, "data.db")
        return StepPlan(argv=SQ.build_mutation_argv(db_path=dbp, table="t"),
                        produces="data.db", verify_kind="sqlite_db", verify_target=dbp)

    def _pack(ctx: StepContext) -> StepPlan:
        src = ctx.artifacts["build_db"]
        out = os.path.join(ctx.workspace, "bundle.zip")
        return StepPlan(argv=Z.build_pack_argv(output_path=out, input_paths=[src]),
                        produces="bundle.zip", verify_kind="zip", verify_target=out)

    def build_steps(params):
        return [PipelineStep("build_db", "sqlite", "safe_mutation", _mk),
                PipelineStep("package", "zip", "pack", _pack)]

    return MissionTemplate(
        template_id="live", title="Live data bundle", objective="build+pack",
        mission_type="one_time", risk=risk, approval_required=approval_required,
        parameters=(MP("label", "str", required=False, default="daily"),),
        build_steps=build_steps)


def _failing_template():
    def _bad(ctx: StepContext) -> StepPlan:
        out = os.path.join(ctx.workspace, "b.zip")
        missing = os.path.join(ctx.workspace, "nope.db")   # never produced
        return StepPlan(argv=Z.build_pack_argv(output_path=out, input_paths=[missing]),
                        produces="b.zip", verify_kind="zip", verify_target=out)
    return MissionTemplate(
        template_id="fail", title="Failing mission", build_steps=lambda p: [
            PipelineStep("bad", "zip", "pack", _bad)])


# ── parameter validation (strongly typed, before execution) ─────────────────
def test_validate_params_coerces_and_defaults():
    params = (MP("date", "str"), MP("count", "int"), MP("ratio", "float"),
              MP("publish", "bool"), MP("level", "enum", choices=("a", "b")),
              MP("voice", "str", required=False, default="en"))
    v = validate_params(params, {"date": "2026-07-13", "count": "3",
                                 "ratio": "0.5", "publish": True, "level": "a"})
    assert v["ok"]
    assert v["values"] == {"date": "2026-07-13", "count": 3, "ratio": 0.5,
                           "publish": True, "level": "a", "voice": "en"}


def test_validate_params_rejects_missing_bad_type_bad_enum_and_unknown():
    params = (MP("count", "int"), MP("level", "enum", choices=("a", "b")))
    v = validate_params(params, {"count": "notint", "level": "z", "extra": 1})
    assert not v["ok"]
    assert any(e.startswith("bad_type:count") for e in v["errors"])
    assert any(e.startswith("bad_enum:level") for e in v["errors"])
    assert "unknown_parameter:extra" in v["errors"]
    v2 = validate_params(params, {})
    assert not v2["ok"] and "missing_required:count" in v2["errors"]


def test_bool_is_not_a_valid_int():
    assert not validate_params((MP("n", "int"),), {"n": True})["ok"]


def test_create_rejects_invalid_parameters_before_execution():
    eng = _engine({"live": _live_template()})
    # 'live' template only declares optional 'label' — unknown key is rejected
    res = eng.create("live", owner="ajay", params={"bogus": 1})
    assert res["ok"] is False and res["reason"] == "invalid_parameters"


# ── creation ────────────────────────────────────────────────────────────────
def test_create_unknown_template_fails_closed():
    assert _engine({}).create("nope", owner="ajay")["reason"] == "unknown_template"


def test_create_empty_owner_rejected():
    assert _engine({"live": _live_template()}).create("live", owner="")["reason"] == "empty_owner"


def test_create_makes_a_draft_mission():
    eng = _engine({"live": _live_template()})
    res = eng.create("live", owner="ajay")
    assert res["ok"] and res["state"] == MISSION_DRAFT
    m = eng.inspect(res["mission_id"], owner="ajay")
    assert m["state"] == MISSION_DRAFT and m["template"] == "live"
    assert m["params"] == {"label": "daily"}       # default applied + persisted


# ── the headline: a real objective delegated to the governed pipeline ───────
@live
def test_mission_completes_via_delegated_pipeline():
    eng = _engine({"live": _live_template()})
    mid = eng.create("live", owner="ajay")["mission_id"]
    res = eng.launch(mid, owner="ajay")
    assert res["ok"] and res["state"] == MISSION_COMPLETED
    assert res["pipeline_id"]
    m = eng.inspect(mid, owner="ajay")
    assert m["state"] == MISSION_COMPLETED
    assert m["run_count"] == 1
    assert m["last_pipeline_id"] == res["pipeline_id"]
    # the delegated pipeline is a REAL governed pipeline record in the same ledger
    p = eng.ledger.inspect_pipeline(res["pipeline_id"], owner="ajay")
    assert p is not None and [s["status"] for s in p["steps"]] == ["success", "success"]
    # history records the single successful attempt
    hist = eng.history(mid, owner="ajay")
    assert len(hist) == 1 and hist[0]["state"] == MISSION_COMPLETED
    assert hist[0]["pipeline_id"] == res["pipeline_id"]


@live
def test_mission_never_executes_tools_directly():
    """A mission holds NO adapter/argv; only the delegated pipeline does. The
    mission record is owner-safe (no argv/output/sql leaks)."""
    import json
    eng = _engine({"live": _live_template()})
    mid = eng.create("live", owner="ajay")["mission_id"]
    eng.launch(mid, owner="ajay")
    blob = json.dumps(eng.inspect(mid))
    for leak in ("argv", "stdout", "stderr", "sqlite3", "SELECT", "INSERT"):
        assert leak not in blob


# ── fail-closed: a pipeline failure fails the mission (no partial success) ───
@live
def test_pipeline_failure_fails_the_mission():
    eng = _engine({"fail": _failing_template()})
    mid = eng.create("fail", owner="ajay")["mission_id"]
    res = eng.launch(mid, owner="ajay")
    assert res["ok"] is False and res["state"] == MISSION_FAILED
    m = eng.inspect(mid, owner="ajay")
    assert m["state"] == MISSION_FAILED and m["failure_code"]


def test_template_that_raises_fails_closed():
    def boom(p):
        raise ValueError("builder blew up")
    tmpl = MissionTemplate(template_id="boom", title="boom", build_steps=boom)
    eng = _engine({"boom": tmpl})
    mid = eng.create("boom", owner="ajay")["mission_id"]
    res = eng.launch(mid, owner="ajay")
    assert res["ok"] is False and res["state"] == MISSION_FAILED
    assert res["failure_code"].startswith("MISSION_EXCEPTION")


def test_template_producing_no_steps_fails_closed():
    tmpl = MissionTemplate(template_id="empty", title="empty", build_steps=lambda p: [])
    eng = _engine({"empty": tmpl})
    mid = eng.create("empty", owner="ajay")["mission_id"]
    res = eng.launch(mid, owner="ajay")
    assert res["ok"] is False and res["state"] == MISSION_FAILED


# ── owner isolation ──────────────────────────────────────────────────────────
def test_owner_mismatch_is_rejected_everywhere():
    eng = _engine({"live": _live_template()})
    mid = eng.create("live", owner="ajay")["mission_id"]
    for call in (lambda: eng.run(mid, owner="mallory"),
                 lambda: eng.enqueue(mid, owner="mallory"),
                 lambda: eng.approve(mid, owner="mallory", approver="mallory"),
                 lambda: eng.cancel(mid, owner="mallory"),
                 lambda: eng.retry(mid, owner="mallory")):
        assert call()["reason"] == "owner_mismatch"
    assert eng.inspect(mid, owner="mallory") is None
    assert eng.list("mallory") == []


# ── approval gates honoured (no silent elevation) ───────────────────────────
def test_approval_required_mission_cannot_queue_without_approval():
    eng = _engine({"live": _live_template(approval_required=True)})
    mid = eng.create("live", owner="ajay")["mission_id"]
    eq = eng.enqueue(mid, owner="ajay")
    assert eq["ok"] is False and eq["reason"] == "approval_required"
    assert eng.inspect(mid, owner="ajay")["state"] == MISSION_APPROVAL_REQUIRED
    # run refuses too — not queued
    assert eng.run(mid, owner="ajay")["reason"].startswith("not_queued")


@live
def test_approval_required_mission_runs_after_approval():
    eng = _engine({"live": _live_template(approval_required=True)})
    mid = eng.create("live", owner="ajay")["mission_id"]
    eng.enqueue(mid, owner="ajay")                    # → approval_required
    assert eng.approve(mid, owner="ajay", approver="ceo")["ok"]
    assert eng.inspect(mid, owner="ajay")["state"] == MISSION_APPROVED
    res = eng.launch(mid, owner="ajay")               # enqueue(approved→queued)+run
    assert res["ok"] and res["state"] == MISSION_COMPLETED
    assert eng.inspect(mid, owner="ajay")["approved_by"] == "ceo"


def test_no_approval_mission_auto_approves_on_enqueue():
    eng = _engine({"live": _live_template(approval_required=False)})
    mid = eng.create("live", owner="ajay")["mission_id"]
    assert eng.enqueue(mid, owner="ajay")["ok"]
    assert eng.inspect(mid, owner="ajay")["state"] == MISSION_QUEUED


# ── state machine: fail-closed transitions + terminal immutability ──────────
def test_cannot_run_a_draft_mission():
    eng = _engine({"live": _live_template()})
    mid = eng.create("live", owner="ajay")["mission_id"]
    assert eng.run(mid, owner="ajay")["reason"].startswith("not_queued")


def test_terminal_mission_is_immutable():
    led = _ledger()
    led.create_mission("m", owner="ajay")
    assert led.cancel_mission("m")["ok"]
    assert led.approve_mission("m", approver="x")["ok"] is False
    assert led.enqueue_mission("m")["ok"] is False
    fin = led.finish_mission_run("m", attempt=1, state=MISSION_COMPLETED)
    assert fin["ok"] is False


def test_invalid_transition_rejected():
    led = _ledger()
    led.create_mission("m", owner="ajay")
    # draft → queued directly is NOT a valid transition (must go via approved)
    assert led.enqueue_mission("m")["ok"] is False
    assert led.begin_mission_run("m")["ok"] is False   # not queued


def test_begin_run_is_idempotent_guarded():
    led = _ledger()
    led.create_mission("m", owner="ajay")
    led.approve_mission("m", approver="auto")
    led.enqueue_mission("m")
    first = led.begin_mission_run("m")
    assert first["ok"] and first["attempt"] == 1
    # already running → cannot begin again (no double-run)
    assert led.begin_mission_run("m")["ok"] is False


# ── retry: rejected unless failed; clones a NEW instance ────────────────────
@live
def test_retry_rejected_for_completed_mission():
    eng = _engine({"live": _live_template()})
    mid = eng.create("live", owner="ajay")["mission_id"]
    eng.launch(mid, owner="ajay")
    r = eng.retry(mid, owner="ajay")
    assert r["ok"] is False and r["reason"].startswith("retry_rejected")


def test_retry_rejected_for_draft_mission():
    eng = _engine({"live": _live_template()})
    mid = eng.create("live", owner="ajay")["mission_id"]
    assert eng.retry(mid, owner="ajay")["reason"].startswith("retry_rejected")


@live
def test_retry_of_failed_mission_clones_new_instance():
    eng = _engine({"fail": _failing_template()})
    mid = eng.create("fail", owner="ajay")["mission_id"]
    eng.launch(mid, owner="ajay")
    assert eng.inspect(mid, owner="ajay")["state"] == MISSION_FAILED
    r = eng.retry(mid, owner="ajay")
    assert r["ok"] and r["mission_id"] != mid and r["retried_from"] == mid
    # original stays failed (immutable); the clone is a fresh draft
    assert eng.inspect(mid, owner="ajay")["state"] == MISSION_FAILED
    assert eng.inspect(r["mission_id"], owner="ajay")["state"] == MISSION_DRAFT


# ── ledger correctness: duplicate id, secret rejection, health, list ────────
def test_duplicate_mission_id_rejected():
    led = _ledger()
    assert led.create_mission("m", owner="ajay")["created"] is True
    dup = led.create_mission("m", owner="ajay")
    assert dup["created"] is False and dup["reason"] == "duplicate_mission_id"


def test_secret_shaped_params_rejected():
    led = _ledger()
    with pytest.raises(LedgerSecurityError):
        led.create_mission("m", owner="ajay",
                           params={"api_key": "sk-abcdefghijklmnopqrstuvwxyz012345"})


def test_mission_health_and_list_owner_scoped():
    led = _ledger()
    led.create_mission("a", owner="ajay")
    led.create_mission("b", owner="ajay")
    led.cancel_mission("b")
    led.create_mission("c", owner="mallory")
    h = led.mission_health("ajay")
    assert h["total"] == 2 and h["by_state"].get("cancelled") == 1
    assert {m["mission_id"] for m in led.list_missions("ajay")} == {"a", "b"}
    assert [m["mission_id"] for m in led.list_missions("mallory")] == ["c"]


def test_mission_count_in_ledger_health():
    led = _ledger()
    led.create_mission("m", owner="ajay")
    assert led.health()["missions"] == 1


# ── Control Center integration (owner-safe attention) ───────────────────────
def test_control_center_surfaces_failed_and_pending_missions(monkeypatch):
    from saathi.application_harness import run_ledger as RL
    led = _ledger()
    led.create_mission("mf", owner="ajay", title="nightly")
    led.approve_mission("mf", approver="auto"); led.enqueue_mission("mf")
    led.begin_mission_run("mf")
    led.finish_mission_run("mf", attempt=1, state=MISSION_FAILED,
                           failure_code="PIPELINE_FAILED")
    led.create_mission("mp", owner="ajay", title="review", approval_required=True)
    led.mark_mission_approval_required("mp")
    monkeypatch.setattr(RL, "_default", led)
    monkeypatch.setattr(RL, "default_ledger", lambda: led)
    from saathi.control_center.aggregator import ControlCenterAggregator
    ov = ControlCenterAggregator(owner="ajay").overview()
    items = [i for i in ov["requires_attention"] if i.get("kind") == "harness_mission"]
    msgs = " ".join(i["message"] for i in items)
    assert "mf" in msgs and "mp" in msgs
    # owner-safe: a different owner sees none
    ov2 = ControlCenterAggregator(owner="mallory").overview()
    assert not [i for i in ov2["requires_attention"] if i.get("kind") == "harness_mission"]


# ── CLI surface ─────────────────────────────────────────────────────────────
def test_cli_mission_health_is_always_available(capsys, monkeypatch, tmp_path):
    from saathi.application_harness import run_ledger as RL, cli
    led = RunLedger(str(tmp_path / "l.db"))
    led.create_mission("m", owner="ajay")
    monkeypatch.setattr(RL, "_default", led)
    monkeypatch.setattr(RL, "default_ledger", lambda: led)
    monkeypatch.delenv("SAATHI_HARNESS_ADMIN", raising=False)
    assert cli.main(["mission-health"]) == 0
    assert "total" in capsys.readouterr().out


def test_cli_missions_requires_admin(capsys, monkeypatch, tmp_path):
    from saathi.application_harness import run_ledger as RL, cli
    led = RunLedger(str(tmp_path / "l.db"))
    monkeypatch.setattr(RL, "default_ledger", lambda: led)
    monkeypatch.delenv("SAATHI_HARNESS_ADMIN", raising=False)
    assert cli.main(["missions"]) == 3          # admin gate


@live
def test_cli_mission_run_executes_and_inspect(capsys, monkeypatch, tmp_path):
    import json
    from saathi.application_harness import run_ledger as RL, cli
    led = RunLedger(str(tmp_path / "l.db"))
    monkeypatch.setattr(RL, "_default", led)
    monkeypatch.setattr(RL, "default_ledger", lambda: led)
    monkeypatch.setenv("SAATHI_HARNESS_ADMIN", "1")
    # CLI mission-run builds its own engine with the DEFAULT templates, so create
    # against the real shipped template (`data_bundle`), not a test-only one.
    eng = MissionEngine(ledger=led, runs_root=str(tmp_path / "runs"))
    mid = eng.create("data_bundle", owner="ajay")["mission_id"]
    assert cli.main(["mission-run", mid]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["state"] == MISSION_COMPLETED
    assert cli.main(["mission-inspect", mid]) == 0


# ── multi-process concurrency: duplicate create dedups to exactly one ───────
def _create_worker(db_path, mid, q):
    led = RunLedger(db_path)
    q.put(led.create_mission(mid, owner="ajay")["created"])


def test_concurrent_mission_create_dedups():
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
