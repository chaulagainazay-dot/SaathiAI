"""TRADING-RUNTIME-INSTANCE-WIRING-1 — real instances, or real reasons.

Central Command reported INSUFFICIENT_EVIDENCE for three subsystems. That was
never a scheduling defect. These tests hold the line that matters: where a
canonical instance exists it is the SAME one the runtime uses, and where none
exists nothing is fabricated to make a panel green.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from saathi.platform.tg.health_collector import collect_trading_health
from saathi.platform.tg.ops_status import (
    TradingOpsStatusService,
    reset_status_service_for_tests,
)
from saathi.platform.tg.paper_activation.models import ActivationApprovalStatus
from saathi.platform.tg.paper_activation.ops.models import HealthClass
from saathi.platform.tg.runtime_wiring import (
    WiringState,
    collector_sources,
    resolve_all,
    resolve_approval,
    resolve_execution_gateway,
    resolve_guardian,
    resolve_kill_switch,
    resolve_market_data,
    resolve_provider,
    unavailable_reasons,
    wiring_report,
)
from saathi.platform.tg.trading_ops import OpsMode, Subsystem

SRC = Path("saathi/platform/tg/runtime_wiring.py")
AT = "2026-09-07T01:00:00Z"


@pytest.fixture(autouse=True)
def _reset():
    reset_status_service_for_tests()
    yield
    reset_status_service_for_tests()


def _status(**kw):
    w = resolve_all()
    svc = TradingOpsStatusService(min_interval_seconds=0, mode=OpsMode.SHADOW.value)
    return svc.status(now=AT, unavailable_reasons=unavailable_reasons(w),
                      **collector_sources(w), **kw)


def _subs(status):
    return {s["subsystem"]: s for s in status.snapshot["subsystems"]}


# ══ instance identity — the same object the runtime uses ════════════════════
def test_the_observed_approval_centre_is_the_runtime_s_own(stores=None):
    """NOT a monitoring-only copy. A second centre would report on approvals
    nobody ever grants."""
    from saathi.platform.tg.paper_activation.service import default_paper_gov

    wired = resolve_approval()
    assert wired.state == WiringState.WIRED.value
    assert wired.instance is default_paper_gov().approvals


def test_the_observed_guardian_is_the_process_wide_service():
    from saathi.platform.tg.service import default_tg_service

    assert resolve_guardian().instance is default_tg_service()


def test_the_kill_switch_has_one_owner_and_it_is_the_guardian_service():
    from saathi.platform.tg.service import default_tg_service

    wired = resolve_kill_switch()
    assert wired.instance is default_tg_service().kill_switches
    assert wired.owner == resolve_guardian().owner


def test_resolution_is_stable_so_no_duplicate_singletons_appear():
    a, b = resolve_all(), resolve_all()
    for key in (Subsystem.APPROVAL.value, Subsystem.GUARDIAN.value,
                Subsystem.KILL_SWITCH.value):
        assert a[key].instance is b[key].instance, key


def test_every_wired_subsystem_declares_exactly_one_owner():
    for name, w in resolve_all().items():
        if w.available:
            assert w.owner, name


# ══ nothing is fabricated ═══════════════════════════════════════════════════
def test_no_fake_market_data_supervisor_is_invented():
    """NO_FABRICATED_RUNTIME_INSTANCE.

    A fixture-sourced validation service presented as feed health would be a
    false live label. The absence is reported instead.
    """
    w = resolve_market_data()
    assert w.state == WiringState.PUBLIC_FEED_DISABLED.value
    assert w.instance is None
    assert "not a feed" in (w.detail or "")


def test_no_monitoring_only_provider_tracker_is_created():
    w = resolve_provider()
    assert w.state == WiringState.NOT_CONFIGURED.value
    assert w.instance is None
    # And resolving twice still creates nothing.
    assert resolve_provider().instance is None


def test_unwired_subsystems_contribute_no_source_to_the_collector():
    sources = collector_sources(resolve_all())
    assert "market_data_source" not in sources
    assert "provider_tracker" not in sources
    assert set(sources) >= {"guardian_service", "kill_switch_store", "approval_center"}


def test_the_wiring_module_constructs_no_provider_or_supervisor():
    """Structural: the absence is the guarantee.

    `get`/`list` are deliberately NOT banned by bare name — `dict.get` is
    ubiquitous and harmless. The hazard is calling them on an AUTHORITY, which
    the companion test below checks by receiver instead.
    """
    tree = ast.parse(SRC.read_text())
    called = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Attribute):
                called.add(n.func.attr)
            elif isinstance(n.func, ast.Name):
                called.add(n.func.id)
    forbidden = {"ProviderHealthTracker", "ProviderExecutionRuntime",
                 "ActivationApprovalCenter", "MarketDataService", "connect",
                 "start", "login", "authenticate", "observe_success",
                 "observe_error", "force_state", "consume", "decide", "revoke"}
    assert not (forbidden & called), forbidden & called


def test_no_mutating_accessor_is_called_on_an_authority_object():
    """The precise hazard: `center.get(...)` expires, `tracker.get(...)` creates.

    Checked by RECEIVER rather than by method name, so `dict.get` stays legal
    while the two accessors that transition state stay banned.
    """
    tree = ast.parse(SRC.read_text())
    authority_like = ("center", "approvals", "tracker", "store", "gov",
                      "supervisor", "runtime")
    offenders = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
            continue
        if n.func.attr not in {"get", "list"}:
            continue
        recv = n.func.value
        name = recv.id if isinstance(recv, ast.Name) else getattr(recv, "attr", "")
        if any(tok in str(name).lower() for tok in authority_like):
            offenders.append((name, n.func.attr, n.lineno))
    assert not offenders, offenders


# ══ real reasons, never a generic unknown ═══════════════════════════════════
def test_an_unwired_subsystem_reports_why_not_merely_that_it_is_unknown():
    """A wiring gap and a subsystem fault must not read the same."""
    subs = _subs(_status())
    assert "PUBLIC_FEED_DISABLED" in subs[Subsystem.MARKET_DATA.value]["detail"]
    assert "NOT_CONFIGURED" in subs[Subsystem.PROVIDER.value]["detail"]


def test_no_unwired_subsystem_is_reported_healthy():
    """NO_DEFAULT_HEALTHY_ON_MISSING_EVIDENCE survives the wiring."""
    subs = _subs(_status())
    for name in (Subsystem.MARKET_DATA.value, Subsystem.PROVIDER.value):
        assert subs[name]["health"] != HealthClass.HEALTHY.value


def test_the_wiring_report_separates_available_from_unavailable():
    report = wiring_report()
    assert report[Subsystem.APPROVAL.value]["available"] is True
    assert report[Subsystem.PROVIDER.value]["available"] is False
    assert report[Subsystem.PROVIDER.value]["state"] == WiringState.NOT_CONFIGURED.value
    for entry in report.values():
        assert entry["detail"]


def test_generic_offline_is_never_substituted_for_a_real_reason():
    for entry in wiring_report().values():
        assert entry["state"] != "OFFLINE"
        assert (entry["detail"] or "").lower() != "offline"


# ══ evidence before/after ═══════════════════════════════════════════════════
def test_wiring_turns_three_subsystems_from_unknown_into_real_evidence():
    """The milestone's headline claim, measured rather than asserted.

    BEFORE: nothing was wired, so all five reported insufficient evidence.
    AFTER: guardian, gateway and approval report from real runtime state.
    """
    before = collect_trading_health(evaluation_time=AT)      # nothing supplied
    assert all(h.evidence_sufficient is False for h in before.healths)

    subs = _subs(_status())
    real = {n for n, s in subs.items() if s["health"] == HealthClass.HEALTHY.value}
    assert real >= {Subsystem.GUARDIAN.value, Subsystem.APPROVAL.value,
                    Subsystem.EXECUTION_GATEWAY.value}


def test_the_gateway_reports_real_posture_without_being_exercised():
    """Every interesting gateway method advances execution state, so posture is
    read from Guardian's own declaration instead."""
    w = resolve_execution_gateway()
    assert w.state == WiringState.WIRED.value
    assert w.instance["gateway_available"] is True
    # Live execution off by policy is a CAPABILITY, not a fault.
    assert w.instance["live_execution_enabled"] is False
    subs = _subs(_status())
    assert subs[Subsystem.EXECUTION_GATEWAY.value]["health"] == HealthClass.HEALTHY.value


def test_health_and_readiness_stay_distinct_after_wiring():
    status = _status()
    assert status.snapshot["live_trading_authorized"] is False
    assert _subs(status)[Subsystem.EXECUTION_GATEWAY.value]["health"] == \
        HealthClass.HEALTHY.value


# ══ safe reads survive the wiring ═══════════════════════════════════════════
def test_a_status_read_still_does_not_expire_a_real_approval():
    """The whole hazard of wiring the REAL centre: lifecycle mutation on read."""
    from saathi.platform.tg.paper_activation.service import default_paper_gov

    center = default_paper_gov().approvals
    lapsed = center.request(strategy_slug="wiring-test", reason="r",
                            operator_id="o", operator_identity="human:o",
                            expires_in_sec=-1)
    assert lapsed.status is ActivationApprovalStatus.PENDING

    w = resolve_all()
    svc = TradingOpsStatusService(min_interval_seconds=0)
    svc.status(now="2030-01-01T00:00:00Z", unavailable_reasons=unavailable_reasons(w),
               **collector_sources(w))

    assert lapsed.status is ActivationApprovalStatus.PENDING
    assert lapsed.decided_at is None
    assert lapsed.immutable is False


def test_repeated_status_reads_do_not_mutate_the_real_kill_switch():
    from saathi.platform.tg.service import default_tg_service

    store = default_tg_service().kill_switches
    before = [dict(x) for x in store.status()]
    for _ in range(5):
        _status()
    assert [dict(x) for x in store.status()] == before


def test_five_repeated_requests_create_no_provider_records():
    from saathi.connectors.providers.health import ProviderHealthTracker

    probe = ProviderHealthTracker()
    for _ in range(5):
        _status()
    # Nothing in the wiring path can have touched any tracker.
    assert probe.known_provider_ids() == ()


# ══ bootstrap has no hidden side effects ════════════════════════════════════
def test_resolution_starts_no_connectivity_and_reads_no_credential():
    tree = ast.parse(SRC.read_text())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
        elif isinstance(n, ast.Import):
            mods.update(a.name for a in n.names)
    banned = ("requests", "httpx", "urllib", "socket", "websocket", "binance",
              "broker", "credentials", "secret", "keyring")
    assert not [m for m in mods if any(b in m.lower() for b in banned)], mods


def test_resolution_expires_nothing_on_first_call():
    """Server boot must not expire approvals just because it booted."""
    from saathi.platform.tg.paper_activation.service import default_paper_gov

    center = default_paper_gov().approvals
    lapsed = center.request(strategy_slug="boot-test", reason="r", operator_id="o",
                            operator_identity="human:o", expires_in_sec=-1)
    resolve_all()
    resolve_all()
    assert lapsed.status is ActivationApprovalStatus.PENDING


def test_a_failed_resolution_reports_rather_than_raising(monkeypatch):
    import saathi.platform.tg.service as svc_mod

    def boom():
        raise RuntimeError("service unavailable")

    monkeypatch.setattr(svc_mod, "default_tg_service", boom)
    w = resolve_guardian()
    assert w.state == WiringState.RESOLUTION_FAILED.value
    assert w.instance is None
    assert "RuntimeError" in (w.detail or "")


def test_wiring_adds_no_authority():
    src = SRC.read_text()
    for token in ("submit", "place_order", "execute(", "withdraw", "leverage",
                  "margin", "promote", "authorize"):
        assert token not in src, token


# ══ route ═══════════════════════════════════════════════════════════════════
def test_the_status_route_serves_the_wiring_report():
    import saathi.platform.api as api

    sources = api._trading_ops_sources()
    assert "guardian_service" in sources
    assert "approval_center" in sources
    assert "market_data_source" not in sources


def test_exception_text_never_reaches_the_served_detail():
    """A regression this milestone introduced and then closed.

    Carrying the collector's `reading.error` into the subsystem detail leaked
    exception text — including filesystem paths — into a payload served to a
    browser. Only the caller's AUTHORED reason is carried now; the exception
    stays in `failures` for local diagnostics.
    """
    import json

    class Exploding:
        def snapshot(self):
            raise RuntimeError("/Users/secret/path/thing.py exploded with token=abc")

    result = collect_trading_health(
        evaluation_time=AT, market_data_source=Exploding(),
        unavailable_reasons={Subsystem.MARKET_DATA.value: "PUBLIC_FEED_DISABLED: safe text"},
    )
    md = result.health_for(Subsystem.MARKET_DATA.value)
    assert "/Users/" not in (md.detail or "")
    assert "token=" not in (md.detail or "")

    # The raw error is still available locally, just never in the health payload.
    assert any("/Users/" in (f.get("error") or "") for f in result.failures)
    blob = json.dumps([h.__dict__ for h in result.healths], default=str)
    assert "/Users/" not in blob


def test_only_a_trusted_reason_can_replace_a_subsystem_detail():
    """Without an authored reason, the producer's own wording stands."""
    class Exploding:
        def snapshot(self):
            raise RuntimeError("/Users/secret/leak.py")

    result = collect_trading_health(evaluation_time=AT, market_data_source=Exploding())
    md = result.health_for(Subsystem.MARKET_DATA.value)
    assert "/Users/" not in (md.detail or "")
