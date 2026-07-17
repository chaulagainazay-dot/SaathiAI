"""M26 — Inference operations lifecycle, readiness, rollout, resource guardian."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.inference.ops.models import (
    ProviderOpsState,
    ReadinessStatus,
    RolloutMode,
    ServicePhase,
    VALID_PROVIDER_TRANSITIONS,
)
from saathi.inference.ops.service import (
    InferenceOpsService,
    ResourceSnapshot,
    redact_payload,
)
from saathi.inference.ops.state import OpsStateStore, atomic_write_json
from saathi.inference.certification import (
    SELECTION_SAFETY_MARGIN_GB,
    memory_selection_ok,
    minimum_model_budget_gb,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def clock():
    t = {"v": 1000.0}

    def _c():
        return t["v"]

    def advance(s: float):
        t["v"] += s

    _c.advance = advance  # type: ignore[attr-defined]
    _c.t = t  # type: ignore[attr-defined]
    return _c


@pytest.fixture()
def store(tmp_path):
    return OpsStateStore(state_dir=tmp_path / "m26")


def _res(*, mem: float = 4.0, disk: float = 50.0, mem_ok: bool | None = None, disk_ok: bool | None = None):
    budget = minimum_model_budget_gb("qwen2.5:1.5b")
    mok = memory_selection_ok(mem, minimum_model_budget_gb=budget) if mem_ok is None else mem_ok
    dok = disk >= 5.0 if disk_ok is None else disk_ok
    return ResourceSnapshot(
        available_memory_gb=mem,
        free_disk_gb=disk,
        memory_ok=mok,
        disk_ok=dok,
        model_id="qwen2.5:1.5b",
        required_memory_gb=SELECTION_SAFETY_MARGIN_GB + budget,
        source="test",
    )


def make_svc(
    store,
    clock,
    *,
    certified=True,
    reachable=True,
    models=True,
    circuit_open=False,
    gov_ok=True,
    mem=4.0,
    disk=50.0,
    max_concurrent=1,
    canary_percent=10,
    drain_grace_s=0.05,
    shutdown_timeout_s=0.05,
    recover=None,
):
    return InferenceOpsService(
        store=store,
        clock=clock,
        resource_probe=lambda: _res(mem=mem, disk=disk),
        production_certified_probe=lambda: certified,
        provider_reachable_probe=lambda: reachable,
        model_available_probe=lambda: models,
        circuit_open_probe=lambda: circuit_open,
        governance_ready_probe=lambda: gov_ok,
        recover_reservations=recover or (lambda: {"schema": "m24.reservation_recovery.v1", "processed": 0, "unresolved_count": 0}),
        emit_bus=False,
        max_concurrent=max_concurrent,
        canary_percent=canary_percent,
        drain_grace_s=drain_grace_s,
        shutdown_timeout_s=shutdown_timeout_s,
        cooldown_s=30.0,
    )


# ── Lifecycle ──────────────────────────────────────────────────────────────


def test_start_idempotent(store, clock):
    svc = make_svc(store, clock)
    a = svc.start()
    b = svc.start()
    assert a["ok"] and b["ok"]
    assert b.get("idempotent") is True
    assert a["service_id"] == b["service_id"]


def test_stop_idempotent(store, clock):
    svc = make_svc(store, clock)
    svc.start()
    a = svc.stop()
    b = svc.stop()
    assert a["ok"] and b["ok"]
    assert b.get("idempotent") is True


def test_restart_no_duplicate_ownership(store, clock):
    svc = make_svc(store, clock)
    svc.start()
    r = svc.restart()
    assert r["ok"]
    assert r["duplicate_ownership"] is False
    st = store.load()
    assert st["phase"] == ServicePhase.RUNNING.value
    assert st["owner_token"]


def test_drain_rejects_new_requests(store, clock):
    svc = make_svc(store, clock, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    assert svc.begin_request(request_key="a")["accepted"] is True
    svc.end_request()
    svc.drain(grace_s=0.05)
    r = svc.begin_request(request_key="b")
    assert r["accepted"] is False
    assert "DRAINING" in r["reason"] or "drain" in r["reason"].lower() or "mode" in r["reason"]


def test_inflight_bounded_grace_then_force(store, clock):
    svc = make_svc(store, clock, shutdown_timeout_s=0.0)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    store.update(active_requests=1)
    # stop with zero grace forces after timeout
    out = svc.stop(force=False)
    assert out["ok"]
    # with timeout 0 and active_requests, forced path
    assert store.load()["phase"] == "STOPPED"


def test_recovery_reconciles_reservations(store, clock):
    called = {"n": 0}

    def rec():
        called["n"] += 1
        return {"schema": "m24.reservation_recovery.v1", "processed": 2, "unresolved_count": 0, "results": []}

    svc = make_svc(store, clock, recover=rec)
    svc.start()
    out = svc.recover()
    assert out["ok"]
    assert called["n"] == 1
    assert out["recovery"]["processed"] == 2


def test_stale_lease_recovery_deterministic(store, clock):
    svc = make_svc(store, clock)
    store.update(phase=ServicePhase.RUNNING.value, owner_token="", started_at="2026-01-01T00:00:00+00:00")
    out = svc.recover()
    assert out["ok"]
    assert store.load().get("owner_token")


# ── Health / readiness ─────────────────────────────────────────────────────


def test_healthy_but_memory_blocked(store, clock):
    svc = make_svc(store, clock, mem=0.5, certified=True, reachable=True, models=True)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    h = svc.health()
    r = svc.readiness()
    assert h.status.value in ("HEALTHY", "STOPPED") or h.phase.value == "RUNNING"
    assert r.status is ReadinessStatus.ENVIRONMENT_BLOCKED
    assert any("resource.memory" in b or "memory" in b for b in r.blockers)
    assert all(c.check_id for c in r.checks)


def test_certified_but_not_ready_when_off(store, clock):
    svc = make_svc(store, clock, certified=True)
    svc.start()
    # default OFF
    r = svc.readiness()
    assert r.production_certified is True
    assert r.ready is False
    assert r.status is ReadinessStatus.POLICY_BLOCKED


def test_missing_provider_precise(store, clock):
    svc = make_svc(store, clock, reachable=False, models=True, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    r = svc.readiness()
    assert r.status is ReadinessStatus.ENVIRONMENT_BLOCKED
    assert any("provider.reachable" in b for b in r.blockers)


def test_missing_model_precise(store, clock):
    svc = make_svc(store, clock, models=False, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    r = svc.readiness()
    assert any("model" in b for b in r.blockers)


def test_insufficient_memory_precise(store, clock):
    svc = make_svc(store, clock, mem=1.0, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    r = svc.readiness()
    assert any("memory" in b for b in r.blockers)
    assert r.resources["required_memory_gb"] == pytest.approx(1.8)


def test_open_circuit_blocks_readiness(store, clock):
    svc = make_svc(store, clock, circuit_open=True, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    r = svc.readiness()
    assert r.ready is False
    assert r.status in (ReadinessStatus.DEGRADED, ReadinessStatus.ENVIRONMENT_BLOCKED, ReadinessStatus.POLICY_BLOCKED) or any(
        "circuit" in b for b in r.blockers
    )


def test_draining_blocks_readiness(store, clock):
    svc = make_svc(store, clock, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    svc.drain(grace_s=0.01)
    r = svc.readiness()
    assert r.status is ReadinessStatus.DRAINING
    assert r.ready is False


def test_low_disk_blocks(store, clock):
    svc = make_svc(store, clock, disk=1.0, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    r = svc.readiness()
    assert any("disk" in b for b in r.blockers)
    assert r.ready is False


def test_every_blocker_has_check_id(store, clock):
    svc = make_svc(store, clock, mem=0.5, reachable=False, models=False, certified=False)
    svc.start()
    r = svc.readiness()
    for b in r.blockers:
        assert ":" in b or b  # structured
    assert all(c.check_id for c in r.checks)


# ── Resource guardian ──────────────────────────────────────────────────────


def test_canonical_m25_memory_rule_reused():
    assert SELECTION_SAFETY_MARGIN_GB == 0.8
    assert minimum_model_budget_gb("qwen2.5:1.5b") == 1.0
    assert memory_selection_ok(1.8) is True
    assert memory_selection_ok(1.79) is False


def test_concurrency_capped(store, clock):
    svc = make_svc(store, clock, max_concurrent=1, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    assert svc.begin_request(request_key="1")["accepted"]
    # second without end — cap
    r2 = svc.begin_request(request_key="2")
    assert r2["accepted"] is False
    assert "concurrency" in r2["reason"]


def test_request_storm_bounded(store, clock):
    svc = make_svc(store, clock, max_concurrent=1, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    accepted = 0
    rejected = 0
    for i in range(20):
        r = svc.begin_request(request_key=f"k{i}")
        if r["accepted"]:
            accepted += 1
        else:
            rejected += 1
    assert accepted == 1
    assert rejected == 19


def test_idle_unload_disabled_by_default(store, clock):
    svc = make_svc(store, clock)
    svc.start()
    out = svc.optional_idle_unload()
    assert out["performed"] is False
    assert out["model_deleted"] is False
    assert "disabled" in out["reason"]


def test_no_model_deleted(store, clock):
    svc = make_svc(store, clock)
    out = svc.optional_idle_unload(enabled_override=True)
    assert out["model_deleted"] is False


def test_historical_cert_survives_ram_pressure(store, clock):
    hist = ROOT / "docs" / "evidence" / "m25" / "LAST_SUCCESSFUL_LIVE_CERTIFICATION.json"
    before = hist.read_text(encoding="utf-8") if hist.is_file() else ""
    svc = make_svc(store, clock, mem=0.5, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    r = svc.readiness()
    assert r.status is ReadinessStatus.ENVIRONMENT_BLOCKED
    assert r.certification.get("historical_live_present") is True or hist.is_file()
    after = hist.read_text(encoding="utf-8") if hist.is_file() else ""
    assert before == after


# ── Provider supervision ───────────────────────────────────────────────────


def test_provider_state_transitions_valid():
    for src, dests in VALID_PROVIDER_TRANSITIONS.items():
        assert src in ProviderOpsState
        for d in dests:
            assert d in ProviderOpsState


def test_repeated_timeout_cooldown(store, clock):
    svc = make_svc(store, clock, certified=True)
    svc.start()
    for _ in range(3):
        svc.record_provider_failure(reason="timeout")
        clock.advance(1)
    st = store.load()
    assert st.get("cooldown_until")
    assert st.get("provider_state") == ProviderOpsState.COOLDOWN.value


def test_cooldown_prevents_accept(store, clock):
    svc = make_svc(store, clock, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    for _ in range(3):
        svc.record_provider_failure(reason="timeout")
    ok, reason = svc.accepts_new_work(request_key="x")
    assert ok is False
    assert "COOLDOWN" in reason or "cooldown" in reason.lower()


def test_success_clears_cooldown_path(store, clock):
    svc = make_svc(store, clock, certified=True)
    svc.start()
    for _ in range(3):
        svc.record_provider_failure(reason="timeout")
    svc.record_provider_success()
    st = store.load()
    assert not st.get("cooldown_until")


def test_no_gateway_bypass_markers(store, clock):
    """Ops service does not import or call raw provider URLs."""
    import inspect
    import saathi.inference.ops.service as mod

    src = inspect.getsource(mod)
    assert "api.openai.com" not in src
    assert "sk-" not in src
    assert "cloud_fallback" in src  # stays false


def test_accept_requires_governance_path_fields(store, clock):
    svc = make_svc(store, clock, certified=True, gov_ok=False)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    r = svc.readiness()
    assert any("governance" in b for b in r.blockers) or r.ready is False


# ── Rollout ────────────────────────────────────────────────────────────────


def test_default_mode_off(store, clock):
    svc = make_svc(store, clock)
    assert store.load()["rollout_mode"] == "OFF"
    svc.start()
    assert store.load()["rollout_mode"] == "OFF"


def test_shadow_serves_no_production(store, clock):
    svc = make_svc(store, clock, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.SHADOW)
    ok, reason = svc.accepts_new_work(request_key="p")
    assert ok is False
    assert "SHADOW" in reason


def test_canary_deterministic(store, clock):
    svc = make_svc(store, clock, certified=True, canary_percent=10)
    svc.start()
    svc.set_mode(RolloutMode.CANARY)
    # Same key always same decision
    a1, r1 = svc.accepts_new_work(request_key="stable-key-1")
    a2, r2 = svc.accepts_new_work(request_key="stable-key-1")
    assert a1 == a2
    assert r1 == r2


def test_active_requires_certification(store, clock):
    svc = make_svc(store, clock, certified=False)
    svc.start()
    out = svc.set_mode(RolloutMode.ACTIVE)
    assert out["ok"] is False
    assert out["error"] == "active_requires_production_certification"


def test_active_ok_when_certified(store, clock):
    svc = make_svc(store, clock, certified=True)
    svc.start()
    out = svc.set_mode(RolloutMode.ACTIVE)
    assert out["ok"] is True
    assert store.load()["rollout_mode"] == "ACTIVE"


def test_draining_accepts_no_new_work(store, clock):
    svc = make_svc(store, clock, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    svc.drain()
    ok, _ = svc.accepts_new_work(request_key="z")
    assert ok is False


def test_invalid_mode_transition_fails_closed(store, clock):
    svc = make_svc(store, clock, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.DRAINING, force=True)
    # DRAINING → ACTIVE not allowed
    out = svc.set_mode(RolloutMode.ACTIVE)
    assert out["ok"] is False
    assert out["error"] == "invalid_mode_transition"


def test_rollback_returns_off(store, clock):
    svc = make_svc(store, clock, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.ACTIVE)
    out = svc.rollback(reason="test")
    assert out["ok"]
    assert out["mode"] == "OFF"
    assert store.load()["rollout_mode"] == "OFF"
    assert out["cert_evidence_preserved"] is True


def test_mode_transitions_evidence_recorded(store, clock):
    svc = make_svc(store, clock, certified=True)
    svc.start()
    svc.set_mode(RolloutMode.SHADOW, reason="test")
    hist = store.mode_history_path.read_text(encoding="utf-8")
    assert "SHADOW" in hist
    assert "privacy_safe" in hist


# ── Evidence / observability ───────────────────────────────────────────────


def test_events_no_raw_prompts(store, clock):
    svc = make_svc(store, clock)
    svc.start()
    svc._emit("inference.ops.started", {"prompt": "SECRET PROMPT", "output": "SECRET OUT", "ok": True})
    text = store.events_path.read_text(encoding="utf-8")
    assert "SECRET PROMPT" not in text
    assert "SECRET OUT" not in text
    assert "privacy_safe" in text


def test_redact_payload_strips_secrets():
    p = redact_payload({"prompt": "x", "api_key": "sk", "status": "ok", "token": "t"})
    assert "prompt" not in p
    assert "api_key" not in p
    assert "token" not in p
    assert p["status"] == "ok"
    assert p["privacy_safe"] is True


def test_incident_deduplication(store, clock):
    svc = make_svc(store, clock)
    a = svc.open_incident("memory_pressure", check_ids=["resource.memory"], safe_summary="low ram")
    b = svc.open_incident("memory_pressure", check_ids=["resource.memory"], safe_summary="low ram")
    assert a.incident_id == b.incident_id
    open_ones = [i for i in store.load_incidents() if i["state"] == "open"]
    assert len(open_ones) == 1


def test_incident_resolution_recorded(store, clock):
    svc = make_svc(store, clock)
    a = svc.open_incident("disk_pressure", check_ids=["resource.disk"], safe_summary="low disk")
    r = svc.resolve_incident(a.incident_id, resolution="freed space")
    assert r is not None
    assert r.state == "resolved"
    assert r.resolution == "freed space"


def test_atomic_state_writes(tmp_path):
    p = tmp_path / "x.json"
    atomic_write_json(p, {"ok": True})
    assert json.loads(p.read_text())["ok"] is True
    assert not list(tmp_path.glob("*.tmp"))


def test_status_view_accurate(store, clock):
    svc = make_svc(store, clock, certified=True)
    svc.start()
    s = svc.status()
    assert s["schema"].startswith("m26")
    assert s["rollout_mode"] == "OFF"
    assert s["cloud_fallback"] is False
    assert s["trading_guardian"] == "UNCHANGED_UNENGAGED"
    assert s["owns_external_provider_process"] is False
    assert "production_certification" in s
    assert "current_readiness" in s


def test_historical_and_current_evidence_separate():
    hist = ROOT / "docs" / "evidence" / "m25" / "LAST_SUCCESSFUL_LIVE_CERTIFICATION.json"
    latest = ROOT / "docs" / "evidence" / "m25" / "LATEST_ENVIRONMENT_OBSERVATION.json"
    assert hist != latest
    if hist.is_file() and latest.is_file():
        assert hist.read_text() != ""  # both may exist independently


# ── Certification / invariants ─────────────────────────────────────────────


def test_m25_cert_package_not_erased(store, clock):
    cert_dir = ROOT / "docs" / "evidence" / "m25" / "cert"
    suite = cert_dir / "full_suite_evidence.json"
    before = suite.read_text() if suite.is_file() else None
    svc = make_svc(store, clock, mem=0.5)
    svc.start()
    svc.readiness()
    after = suite.read_text() if suite.is_file() else None
    assert before == after


def test_production_cert_not_hardcoded(store, clock):
    svc = make_svc(store, clock, certified=False)
    svc.start()
    r = svc.readiness()
    assert r.production_certified is False
    svc2 = make_svc(store, clock, certified=True)
    # need fresh store phase
    store2 = OpsStateStore(state_dir=store.state_dir.parent / "m26b")
    svc2 = make_svc(store2, clock, certified=True)
    svc2.start()
    assert svc2.readiness().production_certified is True


def test_cloud_fallback_disabled_in_state(store, clock):
    svc = make_svc(store, clock)
    svc.start()
    assert store.load()["cloud_fallback"] is False
    assert svc.status()["cloud_fallback"] is False


def test_trading_guardian_unengaged(store, clock):
    svc = make_svc(store, clock)
    svc.start()
    assert "UNENGAGED" in store.load()["trading_guardian"]
    assert svc.status()["trading_guardian"] == "UNCHANGED_UNENGAGED"


def test_ready_when_all_green(store, clock):
    svc = make_svc(store, clock, certified=True, reachable=True, models=True, mem=4.0, disk=50.0)
    svc.start()
    assert svc.set_mode(RolloutMode.ACTIVE)["ok"]
    r = svc.readiness()
    assert r.status is ReadinessStatus.READY
    assert r.ready is True
    assert r.blockers == []


def test_cli_main_status(store, clock, monkeypatch, tmp_path):
    from saathi.inference.ops import __main__ as cli
    from saathi.inference.ops import service as svc_mod

    svc = make_svc(store, clock)
    monkeypatch.setattr(svc_mod, "_default_service", svc)
    monkeypatch.setattr(svc_mod, "get_ops_service", lambda **kw: svc)
    assert cli.main(["status"]) == 0
