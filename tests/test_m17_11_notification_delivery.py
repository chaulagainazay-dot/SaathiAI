"""M17.11 scheduled monitoring + reliable alert delivery.

Core, retry, scheduler, concurrency (multi-PROCESS), security, and compatibility.
Injectable clock everywhere — no real sleeps. Fake/local transports only, no live
providers.
"""
import json
import multiprocessing as mp
import os

import pytest

from saathi.application_harness import run_ledger as L
from saathi.application_harness import cli as CLI
from saathi.application_harness import notify as N
from saathi.application_harness.run_monitor import HarnessRunMonitor
from saathi.application_harness.run_scheduler import MonitorScheduler, is_enabled
from saathi.application_harness.notify import (NotificationDispatcher, LocalFileTransport,
                                               DeliveryResult, DisabledTransport,
                                               UnconfiguredTransport, build_notification,
                                               fingerprint)

POSIX = os.name == "posix"
CTX = mp.get_context("spawn")


def _led(tmp_path):
    return L.RunLedger(tmp_path / "ledger.db")


def _stale_alert(led, rid="r", owner="ajay"):
    led.create_run(rid, owner=owner, harness_id="h", operation_id="op")
    led.claim(rid, pid=os.getpid()); led.mark_running(rid, pid=os.getpid())
    with led._conn() as c:
        c.execute("UPDATE run SET heartbeat_at=1 WHERE run_id=?", (rid,))
    HarnessRunMonitor(led).sweep(now=1000, stale_sec=30, is_alive=lambda p: True)
    return led.open_alerts(owner)[0]["id"]


class OkT:
    name = "local"
    def send(self, n): return DeliveryResult(ok=True)


class FailT:
    name = "local"
    def __init__(self, code="boom"): self.code = code
    def send(self, n): return DeliveryResult(ok=False, error_code=self.code)


class ExplodeT:
    name = "local"
    def send(self, n): raise RuntimeError("provider blew up: secret=abcd")


def _disp(led, transport=None, root=None):
    t = {"local": transport} if transport else None
    return NotificationDispatcher(led, transports=t, root=root)


# ── core ────────────────────────────────────────────────────────────────────
def test_alert_creates_one_delivery(tmp_path):
    led = _led(tmp_path); aid = _stale_alert(led)
    out = _disp(led, OkT()).enqueue(now=1000)
    assert len(out["created"]) == 1
    assert len(led.deliveries_for_alert(aid)) == 1


def test_repeated_enqueue_no_duplicate(tmp_path):
    led = _led(tmp_path); aid = _stale_alert(led)
    d = _disp(led, OkT())
    d.enqueue(now=1000); second = d.enqueue(now=1001)
    assert second["created"] == []
    assert len(led.deliveries_for_alert(aid)) == 1


def test_successful_local_delivery_writes_durable_evidence(tmp_path):
    led = _led(tmp_path); _stale_alert(led)
    root = tmp_path / "notif"
    out = _disp(led, LocalFileTransport(root), root=root).run_once(now=1000)
    assert len(out["delivered"]) == 1
    lines = (root / "local.jsonl").read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    # owner-safe payload: no argv/output/secret keys
    assert set(rec) >= {"idem", "alert_id", "run_id", "owner", "alert_class", "severity"}
    assert "argv" not in rec and "stdout" not in rec and "token" not in rec


def test_local_transport_idempotent(tmp_path):
    led = _led(tmp_path); aid = _stale_alert(led)
    t = LocalFileTransport(tmp_path / "n")
    note = build_notification(led.alert_by_id(aid))
    assert t.send(note).ok and t.send(note).idempotent is True
    assert len((tmp_path / "n" / "local.jsonl").read_text().splitlines()) == 1


def test_resolved_alert_suppresses_pending_delivery(tmp_path):
    led = _led(tmp_path); aid = _stale_alert(led)
    _disp(led, FailT()).run_once(now=1000)            # a pending/retry delivery exists
    led.complete("r", state=L.SUCCEEDED)               # terminal → resolve alert
    d = led.deliveries_for_alert(aid)[0]
    assert d["status"] == "suppressed"


def test_acknowledged_alert_suppresses_pending_delivery(tmp_path):
    led = _led(tmp_path); aid = _stale_alert(led)
    _disp(led, FailT()).run_once(now=1000)
    led.acknowledge_alert(aid, operator="op")
    assert led.deliveries_for_alert(aid)[0]["status"] == "suppressed"


def test_acknowledged_alert_creates_no_new_delivery(tmp_path):
    led = _led(tmp_path); aid = _stale_alert(led)
    led.acknowledge_alert(aid, operator="op")
    out = _disp(led, OkT()).enqueue(now=1000)
    assert out["created"] == []                        # ack → no new delivery


def test_changed_payload_fingerprint_is_new_version(tmp_path):
    led = _led(tmp_path); aid = _stale_alert(led)
    a = led.alert_by_id(aid)
    fp1 = fingerprint(a)
    a2 = dict(a); a2["severity"] = "critical"
    assert fingerprint(a2) != fp1                       # deterministic version change


def test_unknown_alert_class_fails_closed(tmp_path):
    led = _led(tmp_path)
    with pytest.raises(L.LedgerError):
        led.raise_alert("r", alert_class="bogus")


def test_disabled_transport_no_fake_success(tmp_path):
    led = _led(tmp_path); _stale_alert(led)
    out = _disp(led, DisabledTransport("local")).run_once(now=1000)
    assert out["delivered"] == [] and len(out["failed"]) == 1


def test_unconfigured_external_transport_fails_closed(tmp_path):
    led = _led(tmp_path)
    r = UnconfiguredTransport("telegram").send(
        N.AlertNotification(1, "r", "ajay", "heartbeat_stale", "medium", "fp", "m"))
    assert r.ok is False and r.error_code == "transport_unconfigured"


# ── retry ───────────────────────────────────────────────────────────────────
def test_first_failure_schedules_retry_deterministically(tmp_path):
    led = _led(tmp_path); aid = _stale_alert(led)
    _disp(led, FailT()).run_once(now=2000)
    d = led.deliveries_for_alert(aid)[0]
    assert d["status"] == "retry_wait"
    assert d["attempt_count"] == 1
    assert d["next_attempt_at"] == 2000 + L.RETRY_SCHEDULE[1]   # +60s, deterministic


def test_max_attempts_then_terminal_failed(tmp_path):
    led = _led(tmp_path); aid = _stale_alert(led)
    disp = _disp(led, FailT())
    disp.enqueue(now=3000)
    now = 3000
    for _ in range(L.MAX_DELIVERY_ATTEMPTS + 1):
        disp.dispatch_once(now=now)
        d = led.deliveries_for_alert(aid)[0]
        now = (d["next_attempt_at"] or now) + 1
        if d["status"] == "terminal_failed":
            break
    d = led.deliveries_for_alert(aid)[0]
    assert d["status"] == "terminal_failed"
    assert d["attempt_count"] == L.MAX_DELIVERY_ATTEMPTS


def test_delivered_is_never_retried(tmp_path):
    led = _led(tmp_path); aid = _stale_alert(led)
    disp = _disp(led, OkT())
    disp.run_once(now=1000)
    assert led.deliveries_for_alert(aid)[0]["status"] == "delivered"
    disp.dispatch_once(now=9999)                        # no-op for delivered
    assert led.deliveries_for_alert(aid)[0]["status"] == "delivered"


def test_admin_retry_of_terminal_failure(tmp_path):
    led = _led(tmp_path); aid = _stale_alert(led)
    disp = _disp(led, FailT())
    disp.enqueue(now=3000)
    now = 3000
    for _ in range(L.MAX_DELIVERY_ATTEMPTS + 1):
        disp.dispatch_once(now=now)
        d = led.deliveries_for_alert(aid)[0]; now = (d["next_attempt_at"] or now) + 1
        if d["status"] == "terminal_failed":
            break
    did = led.deliveries_for_alert(aid)[0]["id"]
    assert led.admin_retry_delivery(did, operator="op")["ok"] is True
    assert led.delivery(did)["status"] == "retry_wait"
    # fail closed: empty operator, and non-terminal target
    with pytest.raises(L.LedgerSecurityError):
        led.admin_retry_delivery(did, operator="")


def test_restart_resumes_retry_wait(tmp_path):
    db = tmp_path / "ledger.db"
    led = _led(tmp_path); aid = _stale_alert(led)
    _disp(led, FailT()).run_once(now=2000)
    led2 = L.RunLedger(db)                               # fresh object, same file
    d = led2.deliveries_for_alert(aid)[0]
    assert d["status"] == "retry_wait" and d["next_attempt_at"] == 2000 + 60


# ── scheduler ───────────────────────────────────────────────────────────────
def test_scheduler_registration_is_idempotent(tmp_path):
    sch = MonitorScheduler(_led(tmp_path))
    assert sch.register_once() is True
    assert sch.register_once() is False                 # duplicate prevented


def test_scheduler_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("SAATHI_HARNESS_MONITOR_ENABLED", raising=False)
    assert is_enabled() is False
    assert MonitorScheduler(_led(tmp_path)).start()["started"] is False


def test_scheduler_tick_emits_evidence_and_dispatches(tmp_path, monkeypatch):
    led = _led(tmp_path); _stale_alert(led)
    seen = []
    from saathi.events import bus
    monkeypatch.setattr(bus, "publish_sync", lambda name, payload=None: seen.append(name))
    sch = MonitorScheduler(led, dispatcher=_disp(led, LocalFileTransport(tmp_path / "n")))
    out = sch.tick(now=1000)
    assert "harness.monitor.sweep_started" in seen
    assert "harness.monitor.sweep_finished" in seen
    assert len(out["dispatch"]["delivered"]) == 1


def test_scheduler_overlap_is_skipped(tmp_path):
    sch = MonitorScheduler(_led(tmp_path))
    sch._tick_lock.acquire()                            # simulate an in-flight tick
    try:
        assert sch.tick(now=1)["skipped"] == "overlap"
    finally:
        sch._tick_lock.release()


def test_scheduler_sweep_failure_isolated_from_delivery(tmp_path, monkeypatch):
    led = _led(tmp_path)
    class BoomMon:
        def sweep(self, **k): raise RuntimeError("sweep boom")
    seen = []
    from saathi.events import bus
    monkeypatch.setattr(bus, "publish_sync", lambda name, payload=None: seen.append(name))
    sch = MonitorScheduler(led, monitor=BoomMon(), dispatcher=_disp(led, OkT()))
    out = sch.tick(now=1)
    assert "sweep_failed" in out and "harness.monitor.sweep_failed" in seen


# ── concurrency (multi-PROCESS) ─────────────────────────────────────────────
def _w_create(db, alert_id, q):
    led = L.RunLedger(db)
    q.put(led.create_delivery(alert_id, channel="local", payload_fingerprint="fp")["created"])


def _w_claim(db, did, q, barrier):
    barrier.wait()
    led = L.RunLedger(db)
    q.put(led.claim_delivery(did, worker=f"w{os.getpid()}", now=5000))


def _w_dispatch(db, root, q, barrier):
    barrier.wait()
    led = L.RunLedger(db)
    d = NotificationDispatcher(led, transports={"local": LocalFileTransport(root)})
    d.dispatch_once(now=5000)
    q.put("done")


@pytest.mark.skipif(not POSIX, reason="POSIX multi-process")
def test_concurrent_delivery_creation_dedups(tmp_path):
    db = str(tmp_path / "ledger.db"); led = L.RunLedger(db); aid = _stale_alert(led)
    q = CTX.Queue()
    ps = [CTX.Process(target=_w_create, args=(db, aid, q)) for _ in range(6)]
    for p in ps: p.start()
    for p in ps: p.join(30)
    res = [q.get(timeout=5) for _ in range(6)]
    assert res.count(True) == 1                         # exactly one row created
    assert len(led.deliveries_for_alert(aid)) == 1


@pytest.mark.skipif(not POSIX, reason="POSIX multi-process")
def test_concurrent_claim_single_winner(tmp_path):
    db = str(tmp_path / "ledger.db"); led = L.RunLedger(db); aid = _stale_alert(led)
    did = led.create_delivery(aid, channel="local", payload_fingerprint="fp", now=0)["delivery_id"]
    q = CTX.Queue(); barrier = CTX.Barrier(6)
    ps = [CTX.Process(target=_w_claim, args=(db, did, q, barrier)) for _ in range(6)]
    for p in ps: p.start()
    for p in ps: p.join(30)
    res = [q.get(timeout=5) for _ in range(6)]
    assert res.count(True) == 1                         # one claimant


@pytest.mark.skipif(not POSIX, reason="POSIX multi-process")
def test_concurrent_dispatch_single_delivery_line(tmp_path):
    db = str(tmp_path / "ledger.db"); led = L.RunLedger(db); aid = _stale_alert(led)
    led.create_delivery(aid, channel="local", payload_fingerprint=fingerprint(led.alert_by_id(aid)), now=0)
    root = str(tmp_path / "n"); q = CTX.Queue(); barrier = CTX.Barrier(5)
    ps = [CTX.Process(target=_w_dispatch, args=(db, root, q, barrier)) for _ in range(5)]
    for p in ps: p.start()
    for p in ps: p.join(30)
    [q.get(timeout=5) for _ in range(5)]
    assert led.deliveries_for_alert(aid)[0]["status"] == "delivered"
    lines = (tmp_path / "n" / "local.jsonl").read_text().splitlines()
    assert len(lines) == 1                              # transport idempotency held


def test_stale_claim_reclaimed(tmp_path):
    led = _led(tmp_path); aid = _stale_alert(led)
    did = led.create_delivery(aid, channel="local", payload_fingerprint="fp", now=0)["delivery_id"]
    assert led.claim_delivery(did, worker="w1", now=1000) is True   # now attempting
    # crash-after-claim: lease expires → reclaimed to retry_wait
    reclaimed = led.reclaim_stale_deliveries(now=1000 + 999, lease_sec=120)
    assert did in reclaimed and led.delivery(did)["status"] == "retry_wait"


def test_database_integrity_ok_with_deliveries(tmp_path):
    led = _led(tmp_path); _stale_alert(led)
    _disp(led, OkT()).run_once(now=1000)
    assert led.health()["integrity"] == "ok"


# ── security ────────────────────────────────────────────────────────────────
def test_open_deliveries_owner_scoped(tmp_path):
    led = _led(tmp_path)
    a1 = _stale_alert(led, "mine", "ajay"); _disp(led, FailT()).run_once(now=1000)
    a2 = _stale_alert(led, "theirs", "bob"); _disp(led, FailT()).run_once(now=1000)
    assert {d["owner"] for d in led.open_deliveries("ajay")} == {"ajay"}
    assert [d["alert_id"] for d in led.open_deliveries("ajay")] == [a1]


def test_admin_retry_forged_empty_identity_rejected(tmp_path):
    led = _led(tmp_path); aid = _stale_alert(led)
    did = led.create_delivery(aid, channel="local", payload_fingerprint="fp", now=0)["delivery_id"]
    with pytest.raises(L.LedgerSecurityError):
        led.admin_retry_delivery(did, operator="")


def test_error_summary_bounded_and_no_secret_dump(tmp_path):
    led = _led(tmp_path); aid = _stale_alert(led)
    _disp(led, ExplodeT()).run_once(now=1000)           # transport raises w/ 'secret='
    d = led.deliveries_for_alert(aid)[0]
    assert d["status"] == "retry_wait"
    assert d["last_error_code"] == "transport_exception"
    assert len(d["last_error_summary"]) <= 200          # bounded, never a full dump


def test_malicious_alert_content_is_data_not_executed(tmp_path):
    led = _led(tmp_path)
    led.create_run("r", owner="ajay"); led.claim("r", pid=os.getpid()); led.mark_running("r", pid=os.getpid())
    # detail carries shell/URL-looking content; it is stored/handled as inert data
    led.raise_alert("r", alert_class="heartbeat_stale",
                    detail="$(rm -rf /); http://evil/", owner="ajay")
    note = build_notification(led.open_alerts("ajay")[0])
    assert "rm -rf" not in note.message                 # message is templated, not eval'd


def test_cli_notification_commands_admin_gated(tmp_path, monkeypatch, capsys):
    led = _led(tmp_path); _stale_alert(led)
    monkeypatch.setattr(L, "_default", led, raising=False)
    monkeypatch.delenv("SAATHI_HARNESS_ADMIN", raising=False)
    for argv in (["notify-dispatch"], ["alert-deliveries"], ["retry-delivery", "1"],
                 ["monitor-schedule-status"]):
        assert CLI.main(argv) == 3, argv                # gated; no caller identity trusted
    monkeypatch.setenv("SAATHI_HARNESS_ADMIN", "1")
    assert CLI.main(["notify-dispatch"]) == 0
    capsys.readouterr()
    assert CLI.main(["alert-deliveries"]) == 0
    out = capsys.readouterr().out
    assert "alert_id" in out or "[]" in out


def test_cli_retry_delivery_audited_uses_os_identity(tmp_path, monkeypatch, capsys):
    led = _led(tmp_path); aid = _stale_alert(led)
    monkeypatch.setattr(L, "_default", led, raising=False)
    monkeypatch.setenv("SAATHI_HARNESS_ADMIN", "1")
    disp = _disp(led, FailT()); disp.enqueue(now=3000); now = 3000
    for _ in range(L.MAX_DELIVERY_ATTEMPTS + 1):
        disp.dispatch_once(now=now)
        d = led.deliveries_for_alert(aid)[0]; now = (d["next_attempt_at"] or now) + 1
        if d["status"] == "terminal_failed":
            break
    did = led.deliveries_for_alert(aid)[0]["id"]
    seen = []
    from saathi.events import bus
    monkeypatch.setattr(bus, "publish_sync", lambda name, payload=None: seen.append((name, payload)))
    assert CLI.main(["retry-delivery", str(did)]) == 0
    assert led.delivery(did)["status"] == "retry_wait"
    audit = [p for n, p in seen if n == "harness.notification.admin_retry"]
    assert audit and audit[0]["operator"] == CLI._operator_identity()


# ── Control Center integration ──────────────────────────────────────────────
def test_control_center_exposes_delivery_health(tmp_path, monkeypatch):
    led = _led(tmp_path); aid = _stale_alert(led)
    monkeypatch.setattr(L, "_default", led, raising=False)
    disp = _disp(led, FailT()); disp.enqueue(now=3000); now = 3000
    for _ in range(L.MAX_DELIVERY_ATTEMPTS + 1):
        disp.dispatch_once(now=now)
        d = led.deliveries_for_alert(aid)[0]; now = (d["next_attempt_at"] or now) + 1
        if d["status"] == "terminal_failed":
            break
    from saathi.control_center.aggregator import ControlCenterAggregator
    agg = ControlCenterAggregator("ajay")
    cell = agg.harnesses()
    assert "delivery_health" in cell.value
    assert cell.value["delivery_health"]["terminal_failed"] == 1
    ov = agg.overview()
    notif = [i for i in ov["requires_attention"] if i["kind"] == "harness_notification"]
    assert notif and notif[0]["severity"] == "high"
    assert "argv" not in str(notif) and "secret" not in str(notif).lower()


# ── compatibility ───────────────────────────────────────────────────────────
def test_m17_10_alert_flow_unchanged(tmp_path):
    led = _led(tmp_path); aid = _stale_alert(led)
    assert led.open_alerts("ajay")[0]["id"] == aid
    led.complete("r", state=L.SUCCEEDED)
    assert led.open_alerts("ajay") == []                # M17.10 self-resolve intact
