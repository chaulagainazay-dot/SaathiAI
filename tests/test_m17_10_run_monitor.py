"""M17.10 harness run monitor + stuck-run alerting.

Covers happy path, dedup/replay idempotency, self-heal, terminal auto-resolve,
process_missing reconcile, owner scoping, admin-audited acknowledge + fail-closed,
multi-PROCESS concurrent sweep (no duplicate alerts), restart persistence, CLI
admin gating, Control Center attention contract, and M17.9 backward compatibility.
"""
import multiprocessing as mp
import os

import pytest

from saathi.application_harness import run_ledger as L
from saathi.application_harness import cli as CLI
from saathi.application_harness.run_monitor import HarnessRunMonitor

POSIX = os.name == "posix"
CTX = mp.get_context("spawn")


def _led(tmp_path):
    return L.RunLedger(tmp_path / "ledger.db")


def _running(led, rid="r", owner="ajay", pid=None):
    led.create_run(rid, owner=owner, harness_id="h", operation_id="op")
    led.claim(rid, pid=pid if pid is not None else os.getpid())
    led.mark_running(rid, pid=pid if pid is not None else os.getpid())
    return rid


def _make_stale(led, rid, hb=1):
    with led._conn() as c:
        c.execute("UPDATE run SET heartbeat_at=? WHERE run_id=?", (hb, rid))


# ── happy path: sweep raises a stuck-run alert ──────────────────────────────
def test_sweep_raises_heartbeat_stale_alert(tmp_path):
    led = _led(tmp_path); mon = HarnessRunMonitor(led)
    _running(led, "r", owner="ajay", pid=os.getpid()); _make_stale(led, "r")
    out = mon.sweep(now=1000, stale_sec=30, is_alive=lambda p: True)
    assert out["alerts_raised"] == [{"run_id": "r", "alert_class": "heartbeat_stale"}]
    alerts = led.open_alerts("ajay")
    assert len(alerts) == 1 and alerts[0]["severity"] == "medium"


def test_sweep_alerts_cancellation_stuck_high(tmp_path):
    led = _led(tmp_path); mon = HarnessRunMonitor(led)
    _running(led, "r", owner="ajay", pid=os.getpid())
    led.request_cancellation("r", requester="ajay")
    with led._conn() as c:
        c.execute("UPDATE run SET cancel_requested_at=1 WHERE run_id='r'")
    mon.sweep(now=1000, cancel_stuck_sec=60, is_alive=lambda p: True)
    a = led.open_alerts("ajay")[0]
    assert a["alert_class"] == "cancellation_stuck" and a["severity"] == "high"


# ── dedup / replay idempotency ──────────────────────────────────────────────
def test_repeated_sweep_does_not_duplicate_alert(tmp_path):
    led = _led(tmp_path); mon = HarnessRunMonitor(led)
    _running(led, "r", pid=os.getpid()); _make_stale(led, "r")
    mon.sweep(now=1000, stale_sec=30, is_alive=lambda p: True)
    second = mon.sweep(now=1001, stale_sec=30, is_alive=lambda p: True)
    assert second["alerts_raised"] == []
    assert len(led.open_alerts()) == 1
    # raise_alert itself is idempotent
    assert led.raise_alert("r", alert_class="heartbeat_stale")["raised"] is False


def test_raise_alert_rejects_unknown_class(tmp_path):
    led = _led(tmp_path); _running(led, "r")
    with pytest.raises(L.LedgerError):
        led.raise_alert("r", alert_class="not_a_class")


# ── self-heal: a run that recovers clears its alert ─────────────────────────
def test_self_heal_resolves_when_run_active_again(tmp_path):
    led = _led(tmp_path); mon = HarnessRunMonitor(led)
    _running(led, "r", pid=os.getpid()); _make_stale(led, "r")
    mon.sweep(now=1000, stale_sec=30, is_alive=lambda p: True)
    assert len(led.open_alerts()) == 1
    led.record_heartbeat("r")                       # run resumes
    fresh = led.inspect("r")["heartbeat_at"]
    out = mon.sweep(now=fresh + 1, stale_sec=30, is_alive=lambda p: True)
    assert out["open_alerts"] == 0 and led.open_alerts() == []


# ── terminal auto-resolve ───────────────────────────────────────────────────
def test_terminal_auto_resolves_open_alerts(tmp_path):
    led = _led(tmp_path); mon = HarnessRunMonitor(led)
    _running(led, "r", owner="ajay", pid=os.getpid()); _make_stale(led, "r")
    mon.sweep(now=1000, stale_sec=30, is_alive=lambda p: True)
    assert len(led.open_alerts()) == 1
    led.complete("r", state=L.SUCCEEDED)
    assert led.open_alerts() == []


def test_crash_reconcile_auto_resolves_alerts(tmp_path):
    led = _led(tmp_path); mon = HarnessRunMonitor(led)
    _running(led, "r", pid=os.getpid()); _make_stale(led, "r")
    mon.sweep(now=1000, stale_sec=30, is_alive=lambda p: True)
    assert len(led.open_alerts()) == 1
    led.reconcile_run("r", is_alive=lambda p: False)   # process died
    assert led.open_alerts() == []


# ── process_missing reconciled by the sweep (no lingering alert) ────────────
def test_sweep_reconciles_process_missing(tmp_path):
    led = _led(tmp_path); mon = HarnessRunMonitor(led)
    _running(led, "d", pid=999999999)
    out = mon.sweep(now=2000, is_alive=lambda p: p == os.getpid())
    assert out["recovered"] == ["d"]
    assert led.latest_state("d") == L.CRASH_RECOVERED
    assert led.open_alerts() == []


# ── owner scoping ───────────────────────────────────────────────────────────
def test_open_alerts_owner_scoped_and_safe(tmp_path):
    led = _led(tmp_path); mon = HarnessRunMonitor(led)
    _running(led, "mine", owner="ajay", pid=os.getpid()); _make_stale(led, "mine")
    _running(led, "theirs", owner="bob", pid=os.getpid()); _make_stale(led, "theirs")
    mon.sweep(now=1000, stale_sec=30, is_alive=lambda p: True)
    mine = led.open_alerts("ajay")
    assert [a["run_id"] for a in mine] == ["mine"]
    # owner-safe: no argv/output/secret fields
    assert set(mine[0]) == {"id", "run_id", "owner", "alert_class", "severity",
                            "status", "detail", "created_at", "acknowledged_at",
                            "acknowledged_by"}


# ── acknowledge: admin-audited, fail-closed ─────────────────────────────────
def test_acknowledge_alert_audited_and_fail_closed(tmp_path, monkeypatch):
    led = _led(tmp_path); mon = HarnessRunMonitor(led)
    seen = []
    from saathi.events import bus
    monkeypatch.setattr(bus, "publish_sync",
                        lambda name, payload=None: seen.append((name, payload)))
    _running(led, "r", owner="ajay", pid=os.getpid()); _make_stale(led, "r")
    mon.sweep(now=1000, stale_sec=30, is_alive=lambda p: True)
    aid = led.open_alerts("ajay")[0]["id"]
    assert led.acknowledge_alert(aid, operator="opuser")["ok"] is True
    assert any(n == "harness.run.alert_ack" for n, _ in seen)
    # acknowledged (not resolved) + audited actor recorded
    acked = led.open_alerts("ajay")[0]
    assert acked["status"] == "acknowledged" and acked["acknowledged_by"] == "admin:opuser"
    # fail closed: unknown + empty operator
    assert led.acknowledge_alert(999999, operator="x")["ok"] is False
    with pytest.raises(L.LedgerSecurityError):
        led.acknowledge_alert(aid, operator="")


# ── concurrent multi-process sweep: no duplicate alerts ─────────────────────
def _w_sweep(db, now):
    led = L.RunLedger(db)
    HarnessRunMonitor(led).sweep(now=now, stale_sec=30, is_alive=lambda p: True)


@pytest.mark.skipif(not POSIX, reason="POSIX multi-process")
def test_concurrent_sweeps_no_duplicate_alerts(tmp_path):
    db = str(tmp_path / "ledger.db")
    led = L.RunLedger(db)
    _running(led, "r", owner="ajay", pid=os.getpid()); _make_stale(led, "r")
    procs = [CTX.Process(target=_w_sweep, args=(db, 1000)) for _ in range(6)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(30)
    assert len(led.open_alerts()) == 1            # dedup held across processes
    assert led.health()["integrity"] == "ok"


# ── restart persistence ─────────────────────────────────────────────────────
def test_alerts_persist_across_restart(tmp_path):
    db = tmp_path / "ledger.db"
    led = L.RunLedger(db); mon = HarnessRunMonitor(led)
    _running(led, "r", owner="ajay", pid=os.getpid()); _make_stale(led, "r")
    mon.sweep(now=1000, stale_sec=30, is_alive=lambda p: True)
    led2 = L.RunLedger(db)                          # fresh object, same file
    assert len(led2.open_alerts("ajay")) == 1
    assert led2.health()["integrity"] == "ok"


# ── Control Center attention contract ───────────────────────────────────────
def test_control_center_attention_surfaces_alerts(tmp_path, monkeypatch):
    led = _led(tmp_path); mon = HarnessRunMonitor(led)
    monkeypatch.setattr(L, "_default", led, raising=False)
    _running(led, "r", owner="ajay", pid=os.getpid()); _make_stale(led, "r")
    mon.sweep(now=1000, stale_sec=30, is_alive=lambda p: True)
    from saathi.control_center.aggregator import ControlCenterAggregator
    agg = ControlCenterAggregator("ajay")
    cell = agg.harnesses()
    assert any(a["run_id"] == "r" for a in cell.value["run_alerts"])
    ov = agg.overview()
    harn_items = [i for i in ov["requires_attention"] if i["kind"] == "harness_run"]
    assert harn_items and harn_items[0]["link"] == "/control/harnesses"
    assert "argv" not in str(harn_items)           # owner-safe


# ── CLI admin gating ────────────────────────────────────────────────────────
def test_cli_monitor_commands_admin_gated(tmp_path, monkeypatch, capsys):
    led = _led(tmp_path)
    monkeypatch.setattr(L, "_default", led, raising=False)
    _running(led, "r", owner="ajay", pid=os.getpid()); _make_stale(led, "r")
    monkeypatch.delenv("SAATHI_HARNESS_ADMIN", raising=False)
    for argv in (["runs-monitor"], ["run-alerts"], ["alert-ack", "1"]):
        assert CLI.main(argv) == 3, argv           # gated, no caller identity trusted
    monkeypatch.setenv("SAATHI_HARNESS_ADMIN", "1")
    assert CLI.main(["runs-monitor"]) == 0
    capsys.readouterr()
    assert CLI.main(["run-alerts"]) == 0
    assert '"run_id": "r"' in capsys.readouterr().out
    aid = led.open_alerts()[0]["id"]
    assert CLI.main(["alert-ack", str(aid)]) == 0
    assert led.open_alerts()[0]["acknowledged_by"].startswith("admin:")


# ── backward compatibility: M17.9 health still ok ───────────────────────────
def test_m17_9_health_still_reports_ok(tmp_path):
    led = _led(tmp_path)
    _running(led, "r"); led.complete("r", state=L.SUCCEEDED)
    h = led.health()
    assert h["ok"] is True and h["open_alerts"] == 0
