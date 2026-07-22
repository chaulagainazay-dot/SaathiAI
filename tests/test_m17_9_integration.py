"""M17.9 integration — CLI, Control Center read model, and event-bus emission
over the durable run ledger. Wires the ledger to the canonical surfaces without a
second execution engine.
"""
import os

import pytest

from saathi.application_harness import run_ledger as L
from saathi.application_harness import cli as CLI


@pytest.fixture
def temp_ledger(tmp_path, monkeypatch):
    led = L.RunLedger(tmp_path / "ledger.db")
    monkeypatch.setattr(L, "_default", led, raising=False)
    return led


def _running(led, rid="r", owner="ajay"):
    led.create_run(rid, owner=owner, harness_id="h", operation_id="op")
    led.claim(rid, pid=os.getpid()); led.mark_running(rid, pid=os.getpid())
    return rid


# ── CLI security: ledger-health is open; everything else is admin-maintenance ─
def test_cli_ledger_health_is_open(temp_ledger, capsys, monkeypatch):
    monkeypatch.delenv("SAATHI_HARNESS_ADMIN", raising=False)
    _running(temp_ledger, "r", owner="ajay")
    assert CLI.main(["ledger-health"]) == 0
    out = capsys.readouterr().out
    assert '"integrity": "ok"' in out
    # aggregate only — no per-run owner data leaks through health
    assert "run_id" not in out


def test_cli_mutations_and_reads_require_admin_mode(temp_ledger, capsys, monkeypatch):
    monkeypatch.delenv("SAATHI_HARNESS_ADMIN", raising=False)
    _running(temp_ledger, "r", owner="ajay")
    # NO caller-supplied identity is trusted; without admin opt-in these are all
    # refused with a clear code (3), never silently authorized.
    for argv in (["runs"], ["run-inspect", "r"], ["run-transitions", "r"],
                 ["run-cancel", "r"], ["run-reconcile", "r"], ["runs-reconcile-stale"]):
        assert CLI.main(argv) == 3, argv
    assert temp_ledger.latest_state("r") == L.RUNNING     # nothing mutated


def test_cli_no_requester_or_owner_flag_is_trusted(temp_ledger, capsys, monkeypatch):
    # even if an attacker passes --requester/--owner, they are IGNORED (the OS
    # identity is the only actor) and still gated by admin mode.
    monkeypatch.delenv("SAATHI_HARNESS_ADMIN", raising=False)
    _running(temp_ledger, "r", owner="ajay")
    assert CLI.main(["run-cancel", "r", "--requester", "ajay"]) == 3
    assert CLI.main(["runs", "--owner", "ajay"]) == 3
    assert temp_ledger.latest_state("r") == L.RUNNING


def test_cli_admin_mode_reads_are_owner_safe(temp_ledger, capsys, monkeypatch):
    monkeypatch.setenv("SAATHI_HARNESS_ADMIN", "1")
    temp_ledger.create_run("r", owner="ajay", harness_id="h", operation_id="op",
                           idempotency_key="idem-SECRET", approval_id="appr-123")
    temp_ledger.claim("r", pid=os.getpid()); temp_ledger.mark_running("r", pid=os.getpid())
    assert CLI.main(["run-inspect", "r"]) == 0
    out = capsys.readouterr().out
    assert '"state": "running"' in out
    # approval material / idempotency keys / intent digests must NOT be exposed
    assert "idem-SECRET" not in out and "approval_id" not in out
    assert "intent_digest" not in out
    assert CLI.main(["runs"]) == 0
    assert "active_runs" in capsys.readouterr().out


def test_cli_admin_cancel_uses_os_identity_and_audits(temp_ledger, capsys, monkeypatch):
    monkeypatch.setenv("SAATHI_HARNESS_ADMIN", "1")
    seen = []
    from saathi.events import bus
    monkeypatch.setattr(bus, "publish_sync",
                        lambda name, payload=None: seen.append((name, payload)))
    _running(temp_ledger, "r", owner="ajay")
    assert CLI.main(["run-cancel", "r"]) == 0
    assert temp_ledger.latest_state("r") == L.CANCEL_REQ
    audit = [p for n, p in seen if n == "harness.run.admin_cancel"]
    assert audit and audit[0]["operator"] == CLI._operator_identity()
    # the actor recorded in the transition is the admin OS identity, not a flag
    actors = [t["actor"] for t in temp_ledger.transitions("r")]
    assert any(a.startswith("admin:") for a in actors)


def test_cli_reconcile_stale_admin_only(temp_ledger, capsys, monkeypatch):
    temp_ledger.create_run("d", owner="ajay")
    temp_ledger.claim("d", pid=999999999); temp_ledger.mark_running("d", pid=999999999)
    monkeypatch.delenv("SAATHI_HARNESS_ADMIN", raising=False)
    assert CLI.main(["runs-reconcile-stale"]) == 3          # gated
    assert temp_ledger.latest_state("d") == L.RUNNING
    monkeypatch.setenv("SAATHI_HARNESS_ADMIN", "1")
    assert CLI.main(["runs-reconcile-stale"]) == 0
    assert temp_ledger.latest_state("d") == L.CRASH_RECOVERED


# ── Control Center read model ────────────────────────────────────────────────
def test_control_center_shows_ledger(temp_ledger):
    _running(temp_ledger, "r", owner="ajay")
    from saathi.control_center.aggregator import ControlCenterAggregator
    cell = ControlCenterAggregator("ajay").harnesses()
    assert cell.status == "ok"
    rl = cell.value["run_ledger"]
    assert rl["active_count"] == 1
    row = rl["active_runs"][0]
    assert row["run_id"] == "r" and row["state"] == "running"
    # owner-safe: no argv / stdout / secret fields leak into the cell
    assert "argv" not in row and "stdout" not in row
    assert cell.value["ledger_health"]["ok"] is True


def test_control_center_scoped_to_owner(temp_ledger):
    _running(temp_ledger, "mine", owner="ajay")
    _running(temp_ledger, "theirs", owner="bob")
    from saathi.control_center.aggregator import ControlCenterAggregator
    rl = ControlCenterAggregator("ajay").harnesses().value["run_ledger"]
    assert [r["run_id"] for r in rl["active_runs"]] == ["mine"]


# ── event bus ────────────────────────────────────────────────────────────────
def test_event_bus_emits_on_lifecycle(temp_ledger, monkeypatch):
    seen = []
    from saathi.events import bus
    monkeypatch.setattr(bus, "publish_sync",
                        lambda name, payload=None: seen.append(name))
    _running(temp_ledger, "r", owner="ajay")
    temp_ledger.request_cancellation("r", requester="ajay")
    temp_ledger.complete("r", state=L.CANCELLED)
    assert "harness.run.created" in seen
    assert "harness.run.cancel_requested" in seen
    assert "harness.run.completed" in seen
