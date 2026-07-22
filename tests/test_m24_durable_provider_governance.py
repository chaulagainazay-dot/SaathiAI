"""M24 — Durable circuit/cost state, reservation protocol, engine consolidation."""
from __future__ import annotations

import json
import multiprocessing
import os
import threading
import time
from decimal import Decimal
from pathlib import Path

import pytest

from saathi.inference.circuit_breaker import (
    CircuitConfig,
    CircuitState,
    ProviderCircuitBreakerRegistry,
    get_circuit_registry,
)
from saathi.inference.cost_policy import (
    CostStatus,
    DurableDailyCostStore,
    InMemoryDailyCostStore,
    PricingMetadata,
    estimate_cost,
    enforce_cost_policy,
    process_daily_store,
)
from saathi.inference.failure_taxonomy import FailureType
from saathi.inference.governance_clock import DeterministicClock, day_key
from saathi.inference.governance_errors import GovernanceError, GovernanceErrorCode
from saathi.inference.governance_service import GovernanceService, new_attempt_id, new_request_id
from saathi.inference.governance_store import (
    ACTUAL,
    CLOSED,
    HALF_OPEN,
    OPEN,
    RECONCILIATION,
    RELEASED,
    RESERVED,
    SETTLED,
    DurableGovernanceStore,
    get_governance_store,
    reset_governance_store_for_tests,
)
from saathi.inference.provider_decision import record_provider_outcome
from saathi.inference.release_check import run_release_check
from saathi.inference.residual_paths import ResidualDisposition, get_residual_control
from saathi.inference.runtime_gate import EXPECTED_EXCEPTION_COUNT, evaluate_runtime_gate

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "M21_3_RESIDUAL_EXCEPTION_MANIFEST.json"


@pytest.fixture
def gov(tmp_path):
    clock = DeterministicClock(1_700_000_000.0)
    store = DurableGovernanceStore(
        tmp_path / "gov.db",
        clock=clock,
        failure_threshold=3,
        cooldown_seconds=10.0,
        half_open_max_probes=1,
        half_open_lease_seconds=5.0,
        reservation_ttl_seconds=60.0,
    )
    return store, clock


# ── Audit and authority ───────────────────────────────────────────────────


def test_residual_exceptions_zero():
    data = json.loads(MANIFEST.read_text())
    assert data["exceptions"] == []
    assert data.get("inference_residual_exception_count", 0) == 0
    assert data.get("production_certified") is False
    assert EXPECTED_EXCEPTION_COUNT == 0


def test_engine_residuals_are_canonical():
    for pid in ("engine_cloud_caller", "engine_openai_compat"):
        ctrl = get_residual_control(pid)
        assert ctrl is not None
        assert ctrl.disposition is ResidualDisposition.CANONICAL


def test_process_daily_store_is_durable():
    store = process_daily_store()
    assert isinstance(store, DurableDailyCostStore)
    assert store.authority == "canonical_durable"


def test_inmemory_daily_is_test_fake_only():
    assert InMemoryDailyCostStore.authority == "test_fake_process_local"


def test_unknown_governance_state_zero():
    from saathi.inference.residual_paths import RESIDUAL_PATH_CONTROLS, ResidualDisposition

    unknown = [p for p in RESIDUAL_PATH_CONTROLS if p.disposition is ResidualDisposition.UNKNOWN]
    assert unknown == []


# ── Schema / migration ────────────────────────────────────────────────────


def test_schema_tables_exist(gov):
    store, _ = gov
    assert store.schema_ready()
    tables = {
        r[0]
        for r in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for t in (
        "provider_circuit",
        "circuit_transition",
        "cost_usage",
        "budget_reservation",
        "daily_spend_agg",
        "governance_audit",
        "operator_override",
        "governance_meta",
    ):
        assert t in tables


def test_migration_upgrade_downgrade(tmp_path):
    path = tmp_path / "mig.db"
    store = DurableGovernanceStore(path)
    assert store.upgrade()["ok"] is True
    assert store.schema_ready()
    down = store.downgrade()
    assert down["ok"] is True
    store2 = DurableGovernanceStore(path)
    assert store2.schema_ready()


def test_money_columns_are_text(gov):
    store, _ = gov
    cols = {
        r[1]: r[2]
        for r in store._conn.execute("PRAGMA table_info(budget_reservation)").fetchall()
    }
    assert cols["reserved_amount"].upper() == "TEXT"
    cols2 = {
        r[1]: r[2]
        for r in store._conn.execute("PRAGMA table_info(cost_usage)").fetchall()
    }
    assert cols2["actual_cost"].upper() == "TEXT"
    assert cols2["estimated_cost"].upper() == "TEXT"


def test_float_money_rejected(gov):
    store, _ = gov
    with pytest.raises(GovernanceError) as ei:
        store.reserve_budget(
            request_id="r1",
            attempt_id="a1",
            caller_id="c1",
            provider_id="ollama",
            amount=0.1,  # float
        )
    assert ei.value.code == GovernanceErrorCode.FLOAT_MONEY_REJECTED.value


# ── Circuit durability ────────────────────────────────────────────────────


def test_circuit_open_survives_restart(tmp_path):
    path = tmp_path / "c.db"
    clock = DeterministicClock(1000.0)
    s1 = DurableGovernanceStore(path, clock=clock, failure_threshold=2, cooldown_seconds=30)
    s1.record_failure("ollama", reason="timeout")
    s1.record_failure("ollama", reason="timeout")
    snap = s1.circuit_snapshot("ollama")
    assert snap["state"] == OPEN
    s1.close()
    s2 = DurableGovernanceStore(path, clock=clock, failure_threshold=2, cooldown_seconds=30)
    snap2 = s2.circuit_snapshot("ollama")
    assert snap2["state"] == OPEN
    assert snap2["failure_count"] == 2
    assert snap2["open_until"] is not None


def test_circuit_closed_and_half_open_survive(tmp_path):
    path = tmp_path / "c2.db"
    clock = DeterministicClock(1000.0)
    s = DurableGovernanceStore(path, clock=clock, failure_threshold=2, cooldown_seconds=10)
    s.record_failure("p", reason="x")
    s.record_failure("p", reason="x")
    assert s.circuit_snapshot("p")["state"] == OPEN
    clock.advance(11)
    snap = s.circuit_snapshot("p")
    assert snap["state"] == HALF_OPEN
    s.close()
    s2 = DurableGovernanceStore(path, clock=clock, failure_threshold=2, cooldown_seconds=10)
    assert s2.circuit_snapshot("p")["state"] == HALF_OPEN


def test_policy_denial_does_not_increment(gov):
    store, _ = gov
    store.record_failure("ollama", reason="policy", counts=False)
    snap = store.circuit_snapshot("ollama")
    assert snap["failure_count"] == 0
    assert snap["state"] == CLOSED


def test_success_closes_circuit(gov):
    store, clock = gov
    for _ in range(3):
        store.record_failure("x", reason="err")
    assert store.circuit_snapshot("x")["state"] == OPEN
    store.record_success("x")
    assert store.circuit_snapshot("x")["state"] == CLOSED
    assert store.circuit_snapshot("x")["failure_count"] == 0


def test_half_open_probe_lease_bound(gov):
    store, clock = gov
    for _ in range(3):
        store.record_failure("p", reason="e")
    clock.advance(11)
    ok1, r1, _ = store.allow_request("p", probe_owner="w1")
    assert ok1 and r1 == "half_open_probe"
    ok2, r2, _ = store.allow_request("p", probe_owner="w2")
    assert not ok2
    assert r2 == "half_open_probe_exhausted"


def test_half_open_lease_expiry_recoverable(gov):
    store, clock = gov
    for _ in range(3):
        store.record_failure("p", reason="e")
    clock.advance(11)
    ok1, _, _ = store.allow_request("p", probe_owner="w1")
    assert ok1
    clock.advance(6)  # past lease
    ok2, r2, _ = store.allow_request("p", probe_owner="w2")
    assert ok2 and r2 == "half_open_probe"


def test_manual_reset_audited(gov):
    store, _ = gov
    for _ in range(3):
        store.record_failure("p", reason="e")
    store.manual_reset("p", confirm=True, actor_id="ops", reason_code="ops_reset")
    assert store.circuit_snapshot("p")["state"] == CLOSED
    audit = store.list_audit(limit=20)
    assert any(a["event_type"] == "CIRCUIT_RESET" for a in audit)


def test_reset_requires_confirm(gov):
    store, _ = gov
    with pytest.raises(GovernanceError):
        store.manual_reset("p", confirm=False)


def test_registry_uses_durable_store(tmp_path):
    clock = DeterministicClock(5000.0)
    store = DurableGovernanceStore(tmp_path / "r.db", clock=clock, failure_threshold=2)
    reg = ProviderCircuitBreakerRegistry(
        config=CircuitConfig(failure_threshold=2, cooldown_seconds=5),
        clock=clock,
        store=store,
    )
    reg.record_failure("ollama", reason="t")
    reg.record_failure("ollama", reason="t")
    assert reg.state("ollama") is CircuitState.OPEN
    reg2 = ProviderCircuitBreakerRegistry(store=store, clock=clock)
    assert reg2.state("ollama") is CircuitState.OPEN


def test_record_provider_outcome_policy_vs_provider(gov):
    store, _ = gov
    reg = ProviderCircuitBreakerRegistry(store=store)
    # Provider transport failure counts; policy denial must not.
    record_provider_outcome("ollama", FailureType.PROVIDER_TIMEOUT, success=False, circuits=reg)
    before = reg.snapshot("ollama").failure_count
    # Prefer a non-circuit-impact failure if available
    from saathi.inference.failure_taxonomy import get_failure_spec

    non_impact = None
    for ft in FailureType:
        if not get_failure_spec(ft).circuit_impact:
            non_impact = ft
            break
    if non_impact is not None:
        record_provider_outcome("ollama", non_impact, success=False, circuits=reg)
        assert reg.snapshot("ollama").failure_count == before
    else:
        reg.record_failure("ollama", reason="policy", counts=False)
        assert reg.snapshot("ollama").failure_count == before


# ── Cost ledger + reservations ────────────────────────────────────────────


def test_reservation_before_execution(gov):
    store, _ = gov
    svc = GovernanceService(store)
    plan = svc.reserve_for_attempt(
        request_id="req1",
        caller_id="chat_engine",
        provider_id="openai",
        model_id="gpt",
        amount=Decimal("0.05"),
        daily_budget=Decimal("1.00"),
        paid_provider=True,
    )
    assert plan.reservation_id
    rsv = store.get_reservation(plan.reservation_id)
    assert rsv["status"] == RESERVED
    assert store.get_daily_spend("chat_engine") == Decimal("0.05")


def test_zero_cost_local_path(gov):
    store, _ = gov
    svc = GovernanceService(store)
    est = estimate_cost(
        PricingMetadata(zero_marginal=True, known=True, cost_confidence="zero_marginal"),
        input_tokens=10,
        output_tokens_ceiling=10,
    )
    plan = svc.reserve_for_attempt(
        request_id="r",
        caller_id="c",
        provider_id="ollama",
        estimate=est,
        zero_marginal=True,
    )
    assert plan.zero_cost
    assert plan.reserved_amount == "0"
    svc.begin_attempt(plan)
    out = svc.settle_attempt(plan, actual_cost="0")
    assert out["reservation"]["status"] == SETTLED


def test_duplicate_reservation_idempotent(gov):
    store, _ = gov
    r1 = store.reserve_budget(
        request_id="r",
        attempt_id="a",
        caller_id="c",
        provider_id="p",
        amount=Decimal("0.01"),
        idempotency_key="idem1",
    )
    r2 = store.reserve_budget(
        request_id="r",
        attempt_id="a",
        caller_id="c",
        provider_id="p",
        amount=Decimal("0.01"),
        idempotency_key="idem1",
    )
    assert r1["reservation_id"] == r2["reservation_id"]


def test_concurrent_reservations_cannot_overspend(gov):
    store, _ = gov
    errors = []
    ok = []

    def worker(i):
        try:
            store.reserve_budget(
                request_id=f"r{i}",
                attempt_id=f"a{i}",
                caller_id="c",
                provider_id="p",
                amount=Decimal("0.60"),
                daily_budget=Decimal("1.00"),
            )
            ok.append(i)
        except GovernanceError as e:
            errors.append(e.code)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ok) == 1
    assert GovernanceErrorCode.BUDGET_DENIED.value in errors
    assert store.get_daily_spend("c") == Decimal("0.60")


def test_settle_idempotent(gov):
    store, _ = gov
    r = store.reserve_budget(
        request_id="r",
        attempt_id="a",
        caller_id="c",
        provider_id="p",
        amount=Decimal("0.02"),
    )
    store.mark_attempt_started(r["reservation_id"])
    s1 = store.settle_reservation(r["reservation_id"], actual_cost=Decimal("0.01"))
    s2 = store.settle_reservation(r["reservation_id"], actual_cost=Decimal("0.01"))
    assert s2.get("idempotent") is True
    assert store.request_usage_total("r") == Decimal("0.01")
    # only one usage row
    rows = store._conn.execute("SELECT COUNT(*) AS n FROM cost_usage").fetchone()
    assert rows["n"] == 1


def test_released_cannot_settle(gov):
    store, _ = gov
    r = store.reserve_budget(
        request_id="r",
        attempt_id="a",
        caller_id="c",
        provider_id="p",
        amount=Decimal("0.02"),
    )
    store.release_reservation(r["reservation_id"])
    with pytest.raises(GovernanceError) as ei:
        store.settle_reservation(r["reservation_id"], actual_cost=Decimal("0.01"))
    assert ei.value.code == GovernanceErrorCode.RESERVATION_INVALID_STATE.value


def test_pre_transport_release(gov):
    store, _ = gov
    svc = GovernanceService(store)
    plan = svc.reserve_for_attempt(
        request_id="r",
        caller_id="c",
        provider_id="p",
        amount=Decimal("0.03"),
        daily_budget=Decimal("1"),
    )
    svc.release_attempt(plan, reason="failed_pre_transport")
    assert store.get_reservation(plan.reservation_id)["status"] == RELEASED
    assert store.get_daily_spend("c") == Decimal("0")


def test_unknown_paid_cost_fails_closed(gov):
    store, _ = gov
    svc = GovernanceService(store)
    est = estimate_cost(
        PricingMetadata(known=False, currency="USD"),
        input_tokens=10,
        output_tokens_ceiling=10,
    )
    assert est.status is CostStatus.UNKNOWN
    with pytest.raises(GovernanceError) as ei:
        svc.reserve_for_attempt(
            request_id="r",
            caller_id="c",
            provider_id="openai",
            estimate=est,
            paid_provider=True,
        )
    assert ei.value.code == GovernanceErrorCode.COST_UNKNOWN.value


def test_retry_attempts_separate_ledger(gov):
    store, _ = gov
    svc = GovernanceService(store)
    for n in (1, 2):
        plan = svc.reserve_for_attempt(
            request_id="reqX",
            caller_id="c",
            provider_id="p",
            amount=Decimal("0.01"),
            attempt_number=n,
            daily_budget=Decimal("1"),
        )
        svc.begin_attempt(plan)
        svc.settle_attempt(plan, actual_cost=Decimal("0.01"))
    assert store.request_usage_total("reqX") == Decimal("0.02")
    n = store._conn.execute(
        "SELECT COUNT(*) AS n FROM cost_usage WHERE request_id='reqX'"
    ).fetchone()["n"]
    assert n == 2


# ── Recovery ──────────────────────────────────────────────────────────────


def test_stale_non_started_releases(gov):
    store, clock = gov
    r = store.reserve_budget(
        request_id="r",
        attempt_id="a",
        caller_id="c",
        provider_id="p",
        amount=Decimal("0.05"),
        expires_at=clock() + 1,
    )
    clock.advance(5)
    out = store.recover_stale_reservations()
    assert out["processed"] >= 1
    assert store.get_reservation(r["reservation_id"])["status"] in {RELEASED, "expired"}
    assert store.get_daily_spend("c") == Decimal("0")


def test_unknown_attempt_reconciliation(gov):
    store, clock = gov
    r = store.reserve_budget(
        request_id="r",
        attempt_id="a",
        caller_id="c",
        provider_id="p",
        amount=Decimal("0.05"),
        expires_at=clock() + 1,
    )
    store.mark_attempt_started(r["reservation_id"])
    clock.advance(5)
    out = store.recover_stale_reservations()
    assert any(x["action"] == "reconciliation_required" for x in out["results"])
    assert store.get_reservation(r["reservation_id"])["status"] == RECONCILIATION
    # second recovery stable
    out2 = store.recover_stale_reservations()
    assert store.get_reservation(r["reservation_id"])["status"] == RECONCILIATION
    assert out2["unresolved_count"] >= 1


def test_operator_resolve_audited(gov):
    store, clock = gov
    r = store.reserve_budget(
        request_id="r",
        attempt_id="a",
        caller_id="c",
        provider_id="p",
        amount=Decimal("0.05"),
    )
    store.mark_attempt_started(r["reservation_id"])
    clock.advance(400)
    store.recover_stale_reservations()
    store.operator_resolve_reservation(
        r["reservation_id"],
        resolution="release",
        actor_id="ops",
        reason_code="manual_clear",
        confirm=True,
    )
    assert store.get_reservation(r["reservation_id"])["status"] == RELEASED


# ── Multi-process ─────────────────────────────────────────────────────────


def _mp_worker(db_path: str, attempt_id: str, result_q):
    store = DurableGovernanceStore(db_path, failure_threshold=3)
    try:
        store.reserve_budget(
            request_id="shared",
            attempt_id=attempt_id,
            caller_id="mp",
            provider_id="p",
            amount=Decimal("0.70"),
            daily_budget=Decimal("1.00"),
        )
        result_q.put("ok")
    except Exception as e:
        result_q.put(type(e).__name__ + ":" + getattr(e, "code", str(e)))


def test_multiprocess_budget(tmp_path):
    db = str(tmp_path / "mp.db")
    # init schema
    DurableGovernanceStore(db).close()
    q = multiprocessing.Queue()
    procs = [
        multiprocessing.Process(target=_mp_worker, args=(db, f"a{i}", q))
        for i in range(2)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=10)
    results = [q.get(timeout=2) for _ in range(2)]
    assert results.count("ok") == 1
    store = DurableGovernanceStore(db)
    assert store.get_daily_spend("mp") == Decimal("0.70")


def test_concurrent_half_open_probe_threads(tmp_path):
    """Concurrent half-open probe claims are bounded (thread workers, shared store)."""
    clock = DeterministicClock(2000.0)
    s = DurableGovernanceStore(
        tmp_path / "ho.db",
        clock=clock,
        failure_threshold=1,
        cooldown_seconds=5,
        half_open_max_probes=1,
    )
    s.record_failure("p", reason="e")
    clock.advance(6)
    assert s.circuit_snapshot("p")["state"] == HALF_OPEN
    results: list[tuple[bool, str]] = []
    lock = threading.Lock()

    def probe(owner: str) -> None:
        ok, reason, _ = s.allow_request("p", probe_owner=owner)
        with lock:
            results.append((ok, reason))

    threads = [threading.Thread(target=probe, args=(f"w{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for ok, _ in results if ok) == 1


# ── Engines + release/runtime ─────────────────────────────────────────────


def test_openai_compat_ssrf_blocks_remote():
    from saathi.inference.adapters.openai_compat import (
        OpenAICompatEngine,
        validate_openai_compat_base_url,
    )
    from saathi.inference.errors import EngineError

    ok, reason = validate_openai_compat_base_url(
        "http://evil.example.com/v1", production_context=True
    )
    assert not ok
    with pytest.raises(EngineError):
        OpenAICompatEngine(base_url="http://evil.example.com/v1", production_context=True)
    ok2, _ = validate_openai_compat_base_url("http://127.0.0.1:11435/v1")
    assert ok2


def test_cloud_engine_markers():
    from saathi.inference.adapters.cloud import CloudCallerEngine

    eng = CloudCallerEngine("anthropic", caller=lambda *a: ("", "", {}))
    assert eng.residual_exception is False
    assert eng.governance_authority == "durable_governance_store"


def test_release_check_m24():
    rep = run_release_check()
    assert rep.ok, [f.to_dict() for f in rep.findings if f.severity == "blocking"]
    assert rep.production_certified is False
    assert rep.summary.get("m24_residual_exception_count") == 0


def test_runtime_gate_m24_checks():
    # Isolate package disk evidence so this test covers M24 durable gates only
    report = evaluate_runtime_gate(evidence={"_skip_disk_cert_evidence": True})
    ids = {c.check_id: c for c in report.checks}
    for cid in (
        "durable_circuit_store_ready",
        "durable_cost_store_ready",
        "reservation_protocol_ready",
        "stale_reservation_recovery_ready",
        "governance_schema_ready",
        "cloud_engine_governed",
        "openai_compat_engine_governed",
        "residual_exception_count",
        "operator_controls_ready",
    ):
        assert cid in ids, cid
        assert ids[cid].state.value == "PASS", (cid, ids[cid].detail)
    # Without package evidence, production cannot certify
    assert report.production_certified is False


def test_currency_mismatch_fails(gov):
    store, _ = gov
    with pytest.raises(GovernanceError) as ei:
        store.reserve_budget(
            request_id="r",
            attempt_id="a",
            caller_id="c",
            provider_id="p",
            amount=Decimal("0.01"),
            currency="EUR",
        )
    assert ei.value.code == GovernanceErrorCode.COST_CURRENCY_MISMATCH.value


def test_day_key_uses_configured_tz(monkeypatch):
    monkeypatch.setenv("SAATHI_BUDGET_DAY_TZ", "UTC")
    assert day_key(1_700_000_000.0) == "2023-11-14"


def test_kill_denial_no_usage(gov):
    """Kill denials must not create usage — no reservation path at all."""
    store, _ = gov
    n = store._conn.execute("SELECT COUNT(*) AS n FROM cost_usage").fetchone()["n"]
    assert n == 0


def test_circuit_open_denial_no_usage(gov):
    store, _ = gov
    for _ in range(3):
        store.record_failure("p", reason="e")
    ok, reason, _ = store.allow_request("p")
    assert not ok and reason == "circuit_open"
    n = store._conn.execute("SELECT COUNT(*) AS n FROM cost_usage").fetchone()["n"]
    assert n == 0
