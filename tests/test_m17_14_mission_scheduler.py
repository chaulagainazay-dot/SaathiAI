"""M17.14 governed mission scheduler + trusted event triggers.

Deterministic (injected clock, no real sleeps). Proves: schedules compute due times
deterministically and create exactly ONE occurrence per due time; each occurrence
creates at most ONE mission; dispatch happens ONLY through the MissionEngine (never
PipelineRunner/adapter directly); approvals are never inferred; ownership is
preserved end to end; lease claims are concurrency-safe; restart reconciliation
never duplicates work; trusted event triggers accept only allowlisted events and
dedup repeats; Control Center stays owner-safe.
"""
import multiprocessing as mp
import os
import tempfile
import threading

import pytest

from saathi.application_harness import run_ledger as L
from saathi.application_harness.run_ledger import RunLedger, LedgerSecurityError
from saathi.application_harness.mission import (
    MissionEngine, MissionTemplate, MissionParameter as MP, PipelineStep,
)
from saathi.application_harness.pipeline import StepContext, StepPlan
from saathi.application_harness.scheduler import (
    MissionScheduler, compute_next_due, validate_expression, validate_timezone,
    _dedup_key, _occurrence_id,
)
from saathi.application_harness.event_triggers import MissionEventTriggerService
from saathi.application_harness.pilots import sqlite_harness as SQ, zip_archive as Z

HAS_LIVE = SQ.available()["available"] and Z.available()["available"]
live = pytest.mark.skipif(not HAS_LIVE, reason="sqlite3/zip required for live chain")


# ── helpers ─────────────────────────────────────────────────────────────────
def _ledger():
    return RunLedger(os.path.join(tempfile.mkdtemp(), "ledger.db"))


def _live_template(*, approval_required=False):
    def _mk(ctx: StepContext) -> StepPlan:
        dbp = os.path.join(ctx.workspace, "data.db")
        return StepPlan(argv=SQ.build_mutation_argv(db_path=dbp, table="t"),
                        produces="data.db", verify_kind="sqlite_db", verify_target=dbp)

    def _pack(ctx: StepContext) -> StepPlan:
        src = ctx.artifacts["build_db"]
        out = os.path.join(ctx.workspace, "bundle.zip")
        return StepPlan(argv=Z.build_pack_argv(output_path=out, input_paths=[src]),
                        produces="bundle.zip", verify_kind="zip", verify_target=out)

    return MissionTemplate(
        template_id="live", title="Live bundle", approval_required=approval_required,
        parameters=(MP("label", "str", required=False, default="daily"),),
        build_steps=lambda p: [PipelineStep("build_db", "sqlite", "safe_mutation", _mk),
                               PipelineStep("package", "zip", "pack", _pack)])


def _fail_template():
    def _bad(ctx):
        out = os.path.join(ctx.workspace, "b.zip")
        missing = os.path.join(ctx.workspace, "nope.db")
        return StepPlan(argv=Z.build_pack_argv(output_path=out, input_paths=[missing]),
                        produces="b.zip", verify_kind="zip", verify_target=out)
    return MissionTemplate(template_id="fail", title="Fail",
                           build_steps=lambda p: [PipelineStep("bad", "zip", "pack", _bad)])


def _engine(led, templates=None):
    return MissionEngine(ledger=led, templates=templates or {"live": _live_template()},
                         runs_root=tempfile.mkdtemp())


def _scheduler(led=None, templates=None):
    led = led or _ledger()
    return MissionScheduler(ledger=led, engine=_engine(led, templates)), led


# ══ SCHEDULE VALIDATION ══════════════════════════════════════════════════════
def test_valid_schedules_of_each_type():
    sch, _ = _scheduler()
    for stype, expr in (("one_time", {"run_at": 5000.0}),
                        ("interval", {"interval_sec": 3600}),
                        ("daily", {"time": "06:00"}),
                        ("weekly", {"weekday": 0, "time": "06:00"})):
        r = sch.create_schedule(owner="ajay", mission_template_id="live",
                                schedule_type=stype, expression=expr, now=100.0)
        assert r["ok"], (stype, r)


def test_invalid_timezone_rejected():
    sch, _ = _scheduler()
    r = sch.create_schedule(owner="ajay", mission_template_id="live",
                            schedule_type="daily", timezone="Mars/Phobos",
                            expression={"time": "06:00"}, now=100.0)
    assert not r["ok"] and r["reason"] == "invalid_timezone"


def test_invalid_interval_and_time_and_weekday_rejected():
    assert validate_expression("interval", {"interval_sec": 0})["reason"] == "interval_too_small"
    assert validate_expression("daily", {"time": "99:99"})["reason"] == "invalid_time"
    assert validate_expression("weekly", {"time": "06:00", "weekday": 9})["reason"] == "invalid_weekday"
    assert validate_expression("one_time", {"run_at": -1})["reason"] == "invalid_run_at"


def test_invalid_template_rejected():
    sch, _ = _scheduler()
    r = sch.create_schedule(owner="ajay", mission_template_id="ghost",
                            schedule_type="interval", expression={"interval_sec": 60},
                            now=100.0)
    assert not r["ok"] and r["reason"] == "unknown_template"


def test_invalid_and_secret_params_rejected():
    tmpl = MissionTemplate(template_id="p", title="p", parameters=(MP("n", "int"),),
                           build_steps=lambda p: [])
    sch, led = _scheduler(templates={"p": tmpl})
    bad = sch.create_schedule(owner="ajay", mission_template_id="p",
                              schedule_type="interval", expression={"interval_sec": 60},
                              params={"n": "notint"}, now=100.0)
    assert not bad["ok"] and bad["reason"] == "invalid_parameters"
    with pytest.raises(LedgerSecurityError):
        led.create_schedule("x", owner="ajay", mission_template_id="p",
                            schedule_type="interval",
                            params={"api_key": "sk-abcdefghijklmnopqrstuvwxyz012345"})


def test_owner_mismatch_on_status_change_rejected():
    sch, _ = _scheduler()
    sid = sch.create_schedule(owner="ajay", mission_template_id="live",
                              schedule_type="interval", expression={"interval_sec": 60},
                              now=100.0)["schedule_id"]
    assert sch.pause(sid, owner="mallory")["reason"] == "owner_mismatch"


def test_empty_owner_schedule_rejected_at_ledger():
    with pytest.raises(LedgerSecurityError):
        _ledger().create_schedule("s", owner="", mission_template_id="live",
                                  schedule_type="interval")


# ══ DUE CALCULATION ══════════════════════════════════════════════════════════
def test_next_due_deterministic_interval():
    expr = {"interval_sec": 3600, "anchor": 0.0}
    assert compute_next_due("interval", expr, "UTC", 100.0) == 3600.0
    assert compute_next_due("interval", expr, "UTC", 3600.0) == 7200.0
    assert compute_next_due("interval", expr, "UTC", 7199.0) == 7200.0


def test_next_due_one_time_only_future():
    assert compute_next_due("one_time", {"run_at": 500.0}, "UTC", 100.0) == 500.0
    assert compute_next_due("one_time", {"run_at": 500.0}, "UTC", 500.0) is None


def test_next_due_daily_and_weekly_utc():
    # 2021-01-01 00:00:00 UTC = 1609459200
    base = 1609459200.0
    d = compute_next_due("daily", {"time": "06:00"}, "UTC", base)
    assert d == base + 6 * 3600
    # already past 06:00 → next day
    d2 = compute_next_due("daily", {"time": "06:00"}, "UTC", base + 7 * 3600)
    assert d2 == base + 24 * 3600 + 6 * 3600
    # weekly: 2021-01-01 was a Friday (weekday 4); ask for Monday (0)
    w = compute_next_due("weekly", {"weekday": 0, "time": "06:00"}, "UTC", base)
    assert w == base + 3 * 24 * 3600 + 6 * 3600      # next Monday 06:00


def test_dst_behaviour_documented_shift():
    """A daily local-time job keeps its WALL-CLOCK time across a DST change; its UTC
    epoch shifts by the offset. (US/Eastern spring-forward 2021-03-14.)"""
    tz = "America/New_York"
    before = 1615600800.0    # 2021-03-13 01:00 EST
    a = compute_next_due("daily", {"time": "12:00"}, tz, before)          # 12:00 EST
    b = compute_next_due("daily", {"time": "12:00"}, tz, a)              # 12:00 EDT next day
    # both are local noon; the UTC gap is 23h (spring forward), not 24h — deterministic
    assert round((b - a) / 3600) == 23


@live
def test_one_time_schedule_runs_exactly_once():
    sch, led = _scheduler()
    sid = sch.create_schedule(owner="ajay", mission_template_id="live",
                              schedule_type="one_time", expression={"run_at": 1000.0},
                              now=100.0)["schedule_id"]
    sch.sweep(now=2000.0)
    assert led.get_schedule(sid)["status"] == "completed"
    assert len(led.list_occurrences("ajay")) == 1
    # further sweeps never run it again
    sch.sweep(now=9999.0)
    assert len(led.list_occurrences("ajay")) == 1


def test_interval_produces_expected_due_times():
    sch, led = _scheduler()
    sch.create_schedule(owner="ajay", mission_template_id="live",
                        schedule_type="interval",
                        expression={"interval_sec": 100, "anchor": 0.0}, now=50.0)
    # only generate (don't dispatch) to inspect due grid
    sch.create_due_occurrences(now=350.0)
    dues = sorted(int(o["due_at"]) for o in led.list_occurrences("ajay"))
    assert dues == [100, 200, 300]


def test_paused_and_disabled_produce_nothing():
    sch, led = _scheduler()
    sid = sch.create_schedule(owner="ajay", mission_template_id="live",
                              schedule_type="interval", expression={"interval_sec": 100},
                              now=50.0)["schedule_id"]
    sch.pause(sid, owner="ajay")
    assert sch.create_due_occurrences(now=100000.0)["count"] == 0
    sch.resume(sid, owner="ajay"); sch.disable(sid, owner="ajay")
    assert sch.create_due_occurrences(now=100000.0)["count"] == 0
    assert led.list_occurrences("ajay") == []


def test_no_duplicate_occurrence_for_same_due_time():
    sch, led = _scheduler()
    sch.create_schedule(owner="ajay", mission_template_id="live",
                        schedule_type="one_time", expression={"run_at": 500.0},
                        now=100.0)
    sch.create_due_occurrences(now=600.0)
    sch.create_due_occurrences(now=600.0)      # idempotent
    assert len(led.list_occurrences("ajay")) == 1


# ══ CONCURRENCY ══════════════════════════════════════════════════════════════
def test_multithread_duplicate_occurrence_creation_one_winner():
    led = _ledger()
    key = _dedup_key("s", 100.0, 1)
    oid = _occurrence_id(key)
    results, lock = [], threading.Lock()

    def w():
        r = led.create_occurrence(oid, schedule_id="s", owner="ajay", due_at=100.0,
                                  dedup_key=key)
        with lock:
            results.append(r.get("created"))
    ts = [threading.Thread(target=w) for _ in range(8)]
    for t in ts: t.start()
    for t in ts: t.join(10)
    assert results.count(True) == 1 and results.count(False) == 7


def _occ_worker(db, key, oid, q):
    q.put(RunLedger(db).create_occurrence(oid, schedule_id="s", owner="ajay",
                                          due_at=100.0, dedup_key=key)["created"])


def test_multiprocess_duplicate_occurrence_creation_one_winner():
    db = os.path.join(tempfile.mkdtemp(), "l.db")
    RunLedger(db)
    key = _dedup_key("s", 100.0, 1); oid = _occurrence_id(key)
    ctx = mp.get_context("spawn"); q = ctx.Queue()
    procs = [ctx.Process(target=_occ_worker, args=(db, key, oid, q)) for _ in range(4)]
    for p in procs: p.start()
    for p in procs: p.join(30)
    res = [q.get() for _ in range(4)]
    assert res.count(True) == 1 and res.count(False) == 3


def test_exactly_one_claim_winner_and_active_lease_not_stealable():
    led = _ledger()
    led.create_occurrence("o", schedule_id="s", owner="ajay", due_at=1.0, dedup_key="k")
    assert led.claim_occurrence("o", worker="a", now=100.0, lease_sec=120) is True
    # second claim while lease active → refused (not stealable)
    assert led.claim_occurrence("o", worker="b", now=150.0, lease_sec=120) is False


def test_expired_lease_can_be_reclaimed():
    led = _ledger()
    led.create_occurrence("o", schedule_id="s", owner="ajay", due_at=1.0, dedup_key="k")
    led.claim_occurrence("o", worker="a", now=100.0, lease_sec=120)
    stale = led.reclaim_stale_occurrences(now=300.0, lease_sec=120)   # 100+120 < 300
    assert [s["occurrence_id"] for s in stale] == ["o"]


@live
def test_no_duplicate_mission_after_crash_window():
    """Deterministic mission id: re-dispatching the same occurrence never makes a
    second mission."""
    sch, led = _scheduler()
    sch.create_schedule(owner="ajay", mission_template_id="live",
                        schedule_type="one_time", expression={"run_at": 100.0}, now=10.0)
    sch.sweep(now=200.0)
    m1 = led.health()["missions"]
    # force a re-dispatch of the (already terminal) occurrence's mission id
    sch.sweep(now=200.0)
    assert led.health()["missions"] == m1 == 1


# ══ DISPATCH (delegates ONLY to MissionEngine) ═══════════════════════════════
def test_scheduler_module_has_no_execution_shortcut():
    """Static proof: the scheduler never references PipelineRunner, the adapter, the
    governed run entrypoint, or subprocess — it can only go through MissionEngine."""
    import inspect
    from saathi.application_harness import scheduler as S
    # strip the module docstring (its architecture diagram names PipelineRunner);
    # everything after the first triple-quoted block is real code.
    body = inspect.getsource(S).split('"""', 2)[-1]
    for forbidden in ("PipelineRunner", "run_harness_action", "ApplicationHarnessAdapter",
                      "subprocess", "os.system", "Popen"):
        assert forbidden not in body, forbidden
    assert "MissionEngine" in body and ".launch(" in body


@live
def test_dispatch_delegates_through_missionengine_to_pipeline():
    calls = {"launch": 0}
    led = _ledger()

    class SpyEngine(MissionEngine):
        def launch(self, *a, **k):
            calls["launch"] += 1
            return super().launch(*a, **k)
    eng = SpyEngine(ledger=led, templates={"live": _live_template()},
                    runs_root=tempfile.mkdtemp())
    sch = MissionScheduler(ledger=led, engine=eng)
    sch.create_schedule(owner="ajay", mission_template_id="live",
                        schedule_type="one_time", expression={"run_at": 100.0}, now=10.0)
    sch.sweep(now=200.0)
    assert calls["launch"] == 1                       # went through the engine
    occ = led.list_occurrences("ajay")[0]
    assert occ["state"] == "succeeded" and occ["mission_id"]
    # the mission delegated to a REAL governed pipeline (correlated to the occurrence)
    m = led.inspect_mission(occ["mission_id"])
    p = led.inspect_pipeline(m["last_pipeline_id"])
    assert p is not None and [s["status"] for s in p["steps"]] == ["success", "success"]


@live
def test_failed_mission_marks_occurrence_failed():
    sch, led = _scheduler(templates={"fail": _fail_template()})
    sch.create_schedule(owner="ajay", mission_template_id="fail",
                        schedule_type="one_time", expression={"run_at": 100.0}, now=10.0)
    sch.sweep(now=200.0)
    occ = led.list_occurrences("ajay")[0]
    assert occ["state"] == "failed" and occ["failure_category"] == "failed"


@live
def test_approval_required_scheduled_mission_stops_at_approval_required():
    sch, led = _scheduler(templates={"live": _live_template(approval_required=True)})
    sch.create_schedule(owner="ajay", mission_template_id="live",
                        schedule_type="one_time", expression={"run_at": 100.0}, now=10.0)
    sch.sweep(now=200.0)
    occ = led.list_occurrences("ajay")[0]
    assert occ["state"] == "approval_required"        # NEVER auto-approved
    m = led.inspect_mission(occ["mission_id"])
    assert m["state"] == "approval_required"


def test_owner_mismatch_executes_nothing():
    sch, led = _scheduler()
    sch.create_schedule(owner="ajay", mission_template_id="live", schedule_id="s",
                        schedule_type="one_time", expression={"run_at": 100.0}, now=10.0)
    # forge an occurrence owned by a different principal than its schedule
    led.create_occurrence("o", schedule_id="s", owner="mallory", due_at=100.0,
                          dedup_key="s:100:9")
    r = sch.dispatch_occurrence("o", now=200.0)
    assert r["state"] == "failed" and r["reason"] == "owner_mismatch"
    assert led.health()["missions"] == 0              # engine never invoked


def test_invalid_template_at_dispatch_executes_nothing():
    sch, led = _scheduler()
    sch.create_schedule(owner="ajay", mission_template_id="live", schedule_id="s",
                        schedule_type="one_time", expression={"run_at": 100.0}, now=10.0)
    # remove the template after scheduling → dispatch must fail closed
    sch.engine.templates.pop("live")
    led.create_occurrence("o", schedule_id="s", owner="ajay", due_at=100.0,
                          dedup_key="s:100:1")
    r = sch.dispatch_occurrence("o", now=200.0)
    assert r["state"] == "failed" and r["reason"] == "invalid_template"
    assert led.health()["missions"] == 0


# ══ RESTART & RECONCILIATION ═════════════════════════════════════════════════
def test_crash_before_claim_still_dispatchable():
    led = _ledger()
    led.create_occurrence("o", schedule_id="s", owner="ajay", due_at=1.0, dedup_key="k")
    assert [d["occurrence_id"] for d in led.pending_due_occurrences(now=100.0)] == ["o"]


@live
def test_crash_after_claim_no_mission_requeues():
    sch, led = _scheduler()
    sch.create_schedule(owner="ajay", mission_template_id="live", schedule_id="s",
                        schedule_type="one_time", expression={"run_at": 100.0}, now=10.0)
    led.create_occurrence("o", schedule_id="s", owner="ajay", due_at=100.0, dedup_key="s:100:1")
    led.claim_occurrence("o", worker="dead", now=100.0, lease_sec=120)   # crash, no mission
    rec = sch.reconcile(now=300.0)                     # lease expired
    assert "o" in rec["requeued"]
    assert led.inspect_occurrence("o")["state"] == "pending"


@live
def test_crash_after_mission_creation_reconciles_existing_mission():
    sch, led = _scheduler()
    sch.create_schedule(owner="ajay", mission_template_id="live", schedule_id="s",
                        schedule_type="one_time", expression={"run_at": 100.0}, now=10.0)
    from saathi.application_harness.scheduler import _mission_id_for
    led.create_occurrence("o", schedule_id="s", owner="ajay", due_at=100.0, dedup_key="s:100:1")
    led.claim_occurrence("o", worker="dead", now=100.0, lease_sec=120)
    mid = _mission_id_for("o")
    sch.engine.create("live", owner="ajay", mission_id=mid)   # mission created, then crash
    led.link_occurrence_mission("o", mission_id=mid, now=100.0)
    before = led.health()["missions"]
    rec = sch.reconcile(now=300.0)
    assert "o" in rec["reconciled"]
    assert led.inspect_occurrence("o")["state"] == "succeeded"
    assert led.health()["missions"] == before          # NO duplicate mission


@live
def test_crash_after_mission_completion_finalizes_occurrence():
    sch, led = _scheduler()
    sch.create_schedule(owner="ajay", mission_template_id="live", schedule_id="s",
                        schedule_type="one_time", expression={"run_at": 100.0}, now=10.0)
    from saathi.application_harness.scheduler import _mission_id_for
    led.create_occurrence("o", schedule_id="s", owner="ajay", due_at=100.0, dedup_key="s:100:1")
    led.claim_occurrence("o", worker="dead", now=100.0, lease_sec=120)
    mid = _mission_id_for("o")
    sch.engine.create("live", owner="ajay", mission_id=mid)
    sch.engine.launch(mid, owner="ajay")               # mission fully completed
    led.link_occurrence_mission("o", mission_id=mid, now=100.0)   # occurrence still running
    sch.reconcile(now=300.0)
    assert led.inspect_occurrence("o")["state"] == "succeeded"


def test_stale_lease_surfaced_in_health():
    led = _ledger()
    led.create_occurrence("o", schedule_id="s", owner="ajay", due_at=1.0, dedup_key="k")
    led.claim_occurrence("o", worker="a", now=100.0, lease_sec=120)
    assert led.occurrence_health("ajay", now=300.0)["stale_leases"] == 1


# ══ RETRIES (infrastructure only) ════════════════════════════════════════════
class _FlakyEngine(MissionEngine):
    """launch() raises the first `fail_times` calls (simulated infra failure)."""
    def __init__(self, *a, fail_times=0, **k):
        super().__init__(*a, **k)
        self._fail_times = fail_times
        self.launch_calls = 0

    def launch(self, *a, **k):
        self.launch_calls += 1
        if self.launch_calls <= self._fail_times:
            raise RuntimeError("transient db lock")
        return super().launch(*a, **k)


@live
def test_infra_failure_retries_with_deterministic_backoff_then_succeeds():
    led = _ledger()
    eng = _FlakyEngine(ledger=led, templates={"live": _live_template()},
                       runs_root=tempfile.mkdtemp(), fail_times=2)
    sch = MissionScheduler(ledger=led, engine=eng)
    sch.create_schedule(owner="ajay", mission_template_id="live", schedule_id="s",
                        schedule_type="one_time", expression={"run_at": 100.0}, now=10.0)
    led.create_occurrence("o", schedule_id="s", owner="ajay", due_at=100.0, dedup_key="s:100:1")
    # attempt 1 → retry_wait (backoff RETRY_SCHEDULE[1]=60)
    sch.dispatch_occurrence("o", now=200.0)
    o = led.inspect_occurrence("o")
    assert o["state"] == "retry_wait" and o["attempt_count"] == 1
    assert o["next_attempt_at"] == 200.0 + L.retry_delay(1)
    # attempt 2 (after backoff) → retry_wait again
    sch.dispatch_occurrence("o", now=o["next_attempt_at"])
    o = led.inspect_occurrence("o")
    assert o["state"] == "retry_wait" and o["attempt_count"] == 2
    # attempt 3 (launch now succeeds) → occurrence succeeded
    sch.dispatch_occurrence("o", now=o["next_attempt_at"])
    assert led.inspect_occurrence("o")["state"] == "succeeded"


def test_infra_retry_is_bounded_to_terminal_failure():
    led = _ledger()
    led.create_occurrence("o", schedule_id="s", owner="ajay", due_at=1.0, dedup_key="k")
    # drive retries to exhaustion deterministically; bounded to a terminal failure
    result = None
    for i in range(L.MAX_DELIVERY_ATTEMPTS + 2):
        result = led.occurrence_retry("o", reason="x", now=float(i))
        if result.get("terminal"):
            break
    assert result["state"] == L.OCC_FAILED
    assert led.inspect_occurrence("o")["failure_category"] == "infrastructure"


def test_no_retry_for_approval_owner_or_param_failures():
    """Mission-outcome / authority failures go straight to a terminal occurrence —
    they are NEVER placed on the infrastructure retry path."""
    sch, led = _scheduler()
    sch.create_schedule(owner="ajay", mission_template_id="live", schedule_id="s",
                        schedule_type="one_time", expression={"run_at": 100.0}, now=10.0)
    # owner mismatch → failed terminal, attempt_count stays 0 (no retry)
    led.create_occurrence("o", schedule_id="s", owner="mallory", due_at=100.0, dedup_key="s:100:1")
    sch.dispatch_occurrence("o", now=200.0)
    o = led.inspect_occurrence("o")
    assert o["state"] == "failed" and o["attempt_count"] == 0


# ══ EVENT TRIGGERS ═══════════════════════════════════════════════════════════
def _trigger_svc(led=None, templates=None):
    led = led or _ledger()
    eng = _engine(led, templates)
    return MissionEventTriggerService(ledger=led, engine=eng), led


@live
def test_allowlisted_event_creates_exactly_one_mission():
    ev, led = _trigger_svc()
    ev.register(owner="ajay", event_type="harness.mission.failed",
                mission_template_id="live")
    r = ev.ingest_event(event_type="harness.mission.failed", source_event_id="e1",
                        payload={"run_id": "x"}, now=10.0)
    assert len(r["created"]) == 1
    assert led.health()["missions"] == 1


def test_unknown_event_rejected():
    ev, led = _trigger_svc()
    r = ev.ingest_event(event_type="attacker.rce", source_event_id="e1", payload={}, now=10.0)
    assert not r["ok"] and r["reason"] == "untrusted_event_type"
    assert led.list_receipts() == []


@live
def test_duplicate_source_event_deduplicated():
    ev, led = _trigger_svc()
    ev.register(owner="ajay", event_type="harness.mission.failed",
                mission_template_id="live")
    ev.ingest_event(event_type="harness.mission.failed", source_event_id="e1",
                    payload={"run_id": "x"}, now=10.0)
    r2 = ev.ingest_event(event_type="harness.mission.failed", source_event_id="e1",
                         payload={"run_id": "x"}, now=11.0)
    assert r2["created"] == []
    assert led.health()["missions"] == 1              # exactly one


@live
def test_allowlisted_payload_mapping_and_static_binding():
    tmpl = MissionTemplate(template_id="live", title="L",
                           parameters=(MP("label", "str"), MP("run_id", "str", required=False, default="")),
                           build_steps=_live_template().build_steps)
    ev, led = _trigger_svc(templates={"live": tmpl})
    ev.register(owner="ajay", event_type="harness.mission.failed",
                mission_template_id="live", params={"label": "auto"},
                payload_map={"run_id": "run_id"})
    ev.ingest_event(event_type="harness.mission.failed", source_event_id="e1",
                    payload={"run_id": "abc"}, now=10.0)
    m = led.list_missions("ajay")[0]
    assert m["params"]["label"] == "auto" and m["params"]["run_id"] == "abc"


def test_unexpected_payload_field_rejected():
    ev, led = _trigger_svc()
    ev.register(owner="ajay", event_type="harness.mission.failed",
                mission_template_id="live")
    r = ev.ingest_event(event_type="harness.mission.failed", source_event_id="e1",
                        payload={"totally_unexpected": "x"}, now=10.0)
    assert r["created"] == [] and r["rejected"][0]["category"] == "unexpected_payload_field"


def test_owner_approval_risk_cannot_be_overridden_by_payload():
    # a trigger may not even MAP these fields
    ev, _ = _trigger_svc()
    for bad in ("owner", "approval_required", "risk"):
        r = ev.register(owner="ajay", event_type="harness.mission.failed",
                        mission_template_id="live", payload_map={bad: "x"})
        assert not r["ok"] and r["reason"].startswith("forbidden_mapping")


def test_secret_shaped_payload_rejected():
    ev, led = _trigger_svc()
    ev.register(owner="ajay", event_type="harness.mission.failed",
                mission_template_id="live")
    r = ev.ingest_event(event_type="harness.mission.failed", source_event_id="e1",
                        payload={"api_key": "sk-secret"}, now=10.0)
    assert r["rejected"][0]["category"] == "secret_shaped_payload"


def test_receipt_never_exposes_raw_payload():
    import json
    ev, led = _trigger_svc()
    ev.register(owner="ajay", event_type="harness.mission.failed",
                mission_template_id="live")
    ev.ingest_event(event_type="harness.mission.failed", source_event_id="e1",
                    payload={"run_id": "secret-value-xyz"}, now=10.0)
    blob = json.dumps(led.list_receipts("ajay"))
    assert "secret-value-xyz" not in blob


# ══ CONTROL CENTER (owner-safe) ══════════════════════════════════════════════
def _cc(monkeypatch, led, owner):
    from saathi.application_harness import run_ledger as RL
    monkeypatch.setattr(RL, "_default", led)
    monkeypatch.setattr(RL, "default_ledger", lambda: led)
    from saathi.control_center.aggregator import ControlCenterAggregator
    return ControlCenterAggregator(owner=owner).overview()


def test_control_center_scheduler_attention_and_owner_scope(monkeypatch):
    led = _ledger()
    led.create_schedule("s", owner="ajay", mission_template_id="live",
                        schedule_type="one_time")
    led.create_occurrence("of", schedule_id="s", owner="ajay", due_at=1.0, dedup_key="k1")
    led.finish_occurrence("of", state=L.OCC_FAILED, failure_category="failed")
    led.create_occurrence("oa", schedule_id="s", owner="ajay", due_at=2.0, dedup_key="k2")
    led.claim_occurrence("oa", worker="a", now=1.0, lease_sec=1)
    led.link_occurrence_mission("oa", mission_id="m", now=1.0)
    led.finish_occurrence("oa", state=L.OCC_APPROVAL_REQUIRED)
    ov = _cc(monkeypatch, led, "ajay")
    kinds = {i["kind"] for i in ov["requires_attention"]}
    assert "mission_occurrence" in kinds
    msgs = " ".join(i["message"] for i in ov["requires_attention"]
                    if i["kind"] == "mission_occurrence")
    assert "of" in msgs and "oa" in msgs
    # a different owner sees none of it
    ov2 = _cc(monkeypatch, led, "mallory")
    assert not [i for i in ov2["requires_attention"] if i["kind"] == "mission_occurrence"]


def test_control_center_stale_lease_attention(monkeypatch):
    led = _ledger()
    led.create_occurrence("o", schedule_id="s", owner="ajay", due_at=1.0, dedup_key="k")
    led.claim_occurrence("o", worker="a", now=1.0, lease_sec=1)   # lease long expired vs now
    ov = _cc(monkeypatch, led, "ajay")
    assert any("stale" in i["message"] for i in ov["requires_attention"]
               if i["kind"] == "mission_occurrence")


# ══ CLI ══════════════════════════════════════════════════════════════════════
def test_cli_scheduler_health_always_available(capsys, monkeypatch, tmp_path):
    from saathi.application_harness import run_ledger as RL, cli
    led = RunLedger(str(tmp_path / "l.db"))
    monkeypatch.setattr(RL, "default_ledger", lambda: led)
    monkeypatch.delenv("SAATHI_HARNESS_ADMIN", raising=False)
    assert cli.main(["scheduler-health"]) == 0
    assert "schedules" in capsys.readouterr().out


def test_cli_schedules_requires_admin(capsys, monkeypatch, tmp_path):
    from saathi.application_harness import run_ledger as RL, cli
    monkeypatch.setattr(RL, "default_ledger", lambda: RunLedger(str(tmp_path / "l.db")))
    monkeypatch.delenv("SAATHI_HARNESS_ADMIN", raising=False)
    assert cli.main(["schedules"]) == 3
    assert cli.main(["triggers"]) == 3


def test_cli_trigger_inspect_has_no_raw_payload(capsys, monkeypatch, tmp_path):
    from saathi.application_harness import run_ledger as RL, cli
    led = RunLedger(str(tmp_path / "l.db"))
    led.create_trigger("t", owner="ajay", event_type="harness.mission.failed",
                       mission_template_id="live")
    monkeypatch.setattr(RL, "default_ledger", lambda: led)
    monkeypatch.setenv("SAATHI_HARNESS_ADMIN", "1")
    assert cli.main(["trigger-inspect", "t"]) == 0
    out = capsys.readouterr().out
    assert "payload" not in out or "payload_map" in out    # only the allowlist map, not raw payloads


# ══ DATABASE backup / restore compatibility ═════════════════════════════════
def test_scheduler_ledger_survives_backup_restore():
    import shutil, sqlite3
    d = tempfile.mkdtemp()
    db = os.path.join(d, "l.db")
    led = RunLedger(db)
    led.create_schedule("s", owner="ajay", mission_template_id="live",
                        schedule_type="one_time", expression={"run_at": 1.0})
    led.create_occurrence("o", schedule_id="s", owner="ajay", due_at=1.0, dedup_key="k")
    # consistent online backup via sqlite's backup API
    bak = os.path.join(d, "backup.db")
    src = sqlite3.connect(db); dst = sqlite3.connect(bak)
    with dst:
        src.backup(dst)
    src.close(); dst.close()
    # restore = reopen the backup as a fresh ledger; integrity + rows preserved
    restored = RunLedger(bak)
    h = restored.health()
    assert h["ok"] and h["integrity"] == "ok"
    assert h["schedules"] == 1 and h["occurrences"] == 1
    assert restored.get_schedule("s")["owner"] == "ajay"
    assert restored.inspect_occurrence("o")["state"] == "pending"


# ══ REGRESSION guards (Trading Guardian stays unengaged) ═════════════════════
def test_scheduler_never_touches_trading_or_financial_surface():
    import inspect
    from saathi.application_harness import scheduler as S, event_triggers as E
    for mod in (S, E):
        src = inspect.getsource(mod)
        for forbidden in ("trading", "Trading", "withdraw", "leverage", "order",
                          "broker"):
            assert forbidden not in src
