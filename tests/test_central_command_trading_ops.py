"""CENTRAL-COMMAND-TRADING-OPS — the read-only serving edge.

Central Command may render the canonical snapshot and nothing else. So the tests
here are about two things: that a status read changes NOTHING in the trading
subsystems, and that a stale snapshot can never be presented as current health.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from saathi.connectors.providers.health import ProviderHealthTracker
from saathi.platform.tg.kill_switch import KillSwitchStore
from saathi.platform.tg.ops_status import (
    DEFAULT_MAX_SNAPSHOT_AGE_SECONDS,
    Freshness,
    TradingOpsStatusService,
    reset_status_service_for_tests,
)
from saathi.platform.tg.paper_activation.approvals import ActivationApprovalCenter
from saathi.platform.tg.paper_activation.models import ActivationApprovalStatus
from saathi.platform.tg.paper_activation.ops.models import HealthClass
from saathi.platform.tg.service import TradingGuardianService
from saathi.platform.tg.trading_ops import OpsMode

SRC = Path("saathi/platform/tg/ops_status.py")
T0 = "2026-09-06T12:00:00Z"
T_LATER = "2026-09-06T12:00:30Z"
T_STALE = "2026-09-06T13:00:00Z"


@pytest.fixture(autouse=True)
def _reset():
    reset_status_service_for_tests()
    yield
    reset_status_service_for_tests()


def _sources(**over):
    tracker = ProviderHealthTracker()
    tracker.observe_success("binance.public")
    src = dict(
        market_data_source={"connected": True, "source": "GOVERNED_DATASET",
                            "last_valid_observation": "2026-09-06T11:59:30Z"},
        provider_tracker=tracker,
        guardian_service=TradingGuardianService(),
        kill_switch_store=KillSwitchStore(),
        approval_center=ActivationApprovalCenter(),
        gateway={"gateway_available": True},
    )
    src.update(over)
    return src


def _svc(**kw):
    params = dict(min_interval_seconds=0, mode=OpsMode.SHADOW.value)
    params.update(kw)
    return TradingOpsStatusService(**params)


# ══ freshness: the state that must never be confused with the others ════════
def test_a_snapshot_that_stops_being_collected_stops_being_current():
    """NO_STALE_SNAPSHOT_AS_CURRENT_HEALTH — the milestone's central safety claim.

    A monitor that stops collecting keeps serving its last cheerful answer
    forever. An operator reading green has no way to tell it froze an hour ago
    unless freshness is recomputed at READ time, which is what this pins.
    """
    svc = _svc()
    fresh = svc.status(now=T0, **_sources())
    assert fresh.freshness == Freshness.FRESH.value
    assert fresh.to_public()["reflects_current_state"] is True
    assert fresh.snapshot["overall_health"] == HealthClass.HEALTHY.value

    # The collector stops; only time moves.
    stale = svc.status(now=T_STALE, collect=False)
    assert stale.freshness == Freshness.STALE.value
    assert stale.to_public()["reflects_current_state"] is False
    assert stale.age_seconds == 3600
    # The last readings are still carried, but explicitly not as current.
    assert stale.snapshot["overall_health"] == HealthClass.HEALTHY.value


def test_freshness_is_recomputed_per_read_not_frozen_with_the_snapshot():
    svc = _svc()
    svc.status(now=T0, **_sources())
    assert svc.status(now=T_LATER, collect=False).freshness == Freshness.FRESH.value
    assert svc.status(now=T_STALE, collect=False).freshness == Freshness.STALE.value


def test_a_service_that_has_never_collected_says_so_rather_than_reporting_health():
    s = _svc().status(now=T0, collect=False)
    assert s.freshness == Freshness.NEVER_COLLECTED.value
    assert s.snapshot is None
    assert s.to_public()["reflects_current_state"] is False


def test_stale_and_insufficient_evidence_are_different_states():
    """The two must not collapse: one means the collector stopped, the other
    means it ran and a subsystem could not be judged."""
    svc = _svc()
    # Collector ran; approval and provider were never supplied.
    partial = svc.status(now=T0, guardian_service=TradingGuardianService(),
                         gateway={"gateway_available": True})
    assert partial.freshness == Freshness.FRESH.value
    subs = {s["subsystem"]: s for s in partial.snapshot["subsystems"]}
    assert subs["APPROVAL"]["health"] != HealthClass.HEALTHY.value

    stale = svc.status(now=T_STALE, collect=False)
    assert stale.freshness == Freshness.STALE.value


def test_a_backwards_clock_is_not_evidence_of_freshness():
    svc = _svc()
    svc.status(now=T_STALE, **_sources())
    earlier = svc.status(now=T0, collect=False)
    assert earlier.age_seconds == 0  # clamped, not negative
    assert earlier.freshness == Freshness.FRESH.value


def test_one_exploding_source_still_produces_a_genuinely_fresh_collection():
    """Fault isolation means a partial pass is still a pass.

    The collection really did happen now, so calling it stale would be its own
    lie. What must be true is that the broken subsystem stops claiming health
    while the rest keeps reporting.
    """
    class Exploding:
        def snapshot(self):
            raise RuntimeError("feed source exploded")

    svc = _svc()
    svc.status(now=T0, **_sources())
    after = svc.status(now=T_STALE, **_sources(market_data_source=Exploding()))

    assert after.freshness == Freshness.FRESH.value
    subs = {s["subsystem"]: s for s in after.snapshot["subsystems"]}
    assert subs["MARKET_DATA"]["health"] != HealthClass.HEALTHY.value
    assert subs["GUARDIAN"]["health"] == HealthClass.HEALTHY.value


def test_a_refresh_that_fails_outright_keeps_the_last_picture_and_lets_it_age():
    """The other half: when the pass cannot run at all, nothing is re-collected.

    The service must not raise at the operator, and must not stamp a new
    collection time it did not earn — so the previous snapshot simply grows old
    and freshness catches it.
    """
    svc = _svc()
    svc.status(now=T0, **_sources())

    # An argument the collector cannot accept: the pass raises before producing.
    after = svc.status(now=T_STALE, not_a_real_source=object())

    assert after.snapshot is not None
    assert after.collected_at == T0          # not restamped
    assert after.freshness == Freshness.STALE.value


# ══ zero mutation from a status read ════════════════════════════════════════
def test_a_status_read_does_not_expire_an_approval():
    """NO_APPROVAL_EXPIRY_FROM_STATUS_READ, against the real approval centre."""
    center = ActivationApprovalCenter()
    lapsed = center.request(strategy_slug="s", reason="r", operator_id="o",
                            operator_identity="human:o", expires_in_sec=-1)
    _svc().status(now="2030-01-01T00:00:00Z", **_sources(approval_center=center))
    assert lapsed.status is ActivationApprovalStatus.PENDING
    assert lapsed.decided_at is None
    assert lapsed.immutable is False


def test_a_status_read_does_not_consume_an_approval():
    center = ActivationApprovalCenter()
    ap = center.request(strategy_slug="s", reason="r", operator_id="o",
                        operator_identity="human:o")
    center.decide(ap.id, decision="approve", operator_id="o",
                  operator_identity="human:o", notes="ok")
    _svc().status(now=T0, **_sources(approval_center=center))
    assert ap.status is ActivationApprovalStatus.APPROVED
    assert ap.consumed_at is None


def test_a_status_read_does_not_create_a_provider():
    """NO_PROVIDER_CREATION_FROM_STATUS_READ — page loads must not grow the registry."""
    tracker = ProviderHealthTracker()
    tracker.observe_success("known")
    before = tracker.known_provider_ids()
    svc = _svc()
    for _ in range(5):   # five page loads
        svc.status(now=T0, provider_tracker=tracker,
                   provider_ids=["known", "never.seen"], **{
                       k: v for k, v in _sources().items() if k != "provider_tracker"})
    assert tracker.known_provider_ids() == before
    assert tracker.peek("never.seen") is None


def test_a_status_read_does_not_touch_the_kill_switch():
    store = KillSwitchStore()
    store.activate(scope="GLOBAL", reason="operator halt", activated_by="operator")
    before = [dict(x) for x in store.status()]
    _svc().status(now=T0, **_sources(kill_switch_store=store))
    assert [dict(x) for x in store.status()] == before
    assert store.is_blocked()["blocked"] is True


def test_the_status_service_holds_no_execution_or_mutation_authority():
    tree = ast.parse(SRC.read_text())
    called = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Attribute):
                called.add(n.func.attr)
            elif isinstance(n.func, ast.Name):
                called.add(n.func.id)
    forbidden = {
        "submit", "place", "execute", "cancel", "reserve", "consume", "approve",
        "decide", "revoke", "activate", "deactivate", "reconcile", "recover",
        "retry", "set_policy", "set_limit", "commit", "freeze", "force_state",
        "observe_success", "observe_error", "get", "list",
    }
    assert not (forbidden & called), forbidden & called


def test_the_status_payload_never_claims_authority():
    pub = _svc().status(now=T0, **_sources()).to_public()
    assert pub["authorizes_execution"] is False
    assert pub["live_trading_authorized"] is False


def test_no_credential_material_reaches_the_status_payload():
    import json

    blob = json.dumps(_svc().status(now=T0, **_sources()).to_public(), default=str).lower()
    for marker in ("api_key", "secret", "password", "bearer", "token=",
                   "authorization", "cookie"):
        assert marker not in blob, marker


def test_the_payload_exposes_no_filesystem_paths_or_tracebacks():
    import json

    class Exploding:
        def snapshot(self):
            raise RuntimeError("/Users/secretpath/thing.py exploded")

    svc = _svc()
    blob = json.dumps(svc.status(now=T0, **_sources(market_data_source=Exploding())
                                 ).to_public(), default=str)
    assert "/Users/" not in blob
    assert "Traceback" not in blob


# ══ presentation-relevant content ═══════════════════════════════════════════
def test_the_snapshot_carries_mode_and_never_implies_live():
    snap = _svc().status(now=T0, **_sources()).snapshot
    assert snap["mode"] == OpsMode.SHADOW.value
    assert snap["live_trading_authorized"] is False
    assert snap["mode"] != "LIVE"


def test_root_cause_convergence_reaches_the_serving_edge():
    from saathi.connectors.providers.models import ProviderHealthState

    tracker = ProviderHealthTracker()
    tracker.observe_success("binance.public")
    tracker.force_state("binance.public", ProviderHealthState.UNAVAILABLE)
    svc = _svc()
    s = svc.status(now=T0, **_sources(
        provider_tracker=tracker,
        market_data_source={"connected": True, "source": "GOVERNED_DATASET",
                            "last_valid_observation": "2026-09-06T10:00:00Z"},
    ))
    incidents = s.snapshot["incidents"]
    assert len(incidents) == 1
    assert incidents[0]["subsystem"] == "PROVIDER"
    assert {x["subsystem"] for x in incidents[0]["symptoms"]} == {"MARKET_DATA"}


def test_every_rendered_operator_action_names_its_authority():
    s = _svc().status(now=T0, **_sources(
        market_data_source={"connected": True, "source": "GOVERNED_DATASET",
                            "last_valid_observation": "2026-09-06T10:00:00Z"}))
    for a in s.snapshot["operator_actions_required"]:
        assert a["authority"] and a["authority"] != "UNKNOWN", a


def test_collection_is_coalesced_so_page_loads_do_not_become_a_polling_storm():
    svc = TradingOpsStatusService(min_interval_seconds=60, mode=OpsMode.SHADOW.value)
    src = _sources()
    svc.status(now=T0, **src)
    for _ in range(10):
        svc.status(now=T_LATER, **src)   # inside the interval
    assert svc.collector.runs == 1
    assert svc.collector.skipped == 10


def test_the_default_freshness_window_is_not_aggressive():
    assert DEFAULT_MAX_SNAPSHOT_AGE_SECONDS >= 60


# ══ the API route ═══════════════════════════════════════════════════════════
def test_the_status_route_is_registered_and_read_only():
    import saathi.platform.api as api

    route = next(r for r in api.router.routes
                 if getattr(r, "path", "").endswith("/tg/operations/trading-ops"))
    assert set(route.methods) == {"GET"}


def test_the_route_only_wires_subsystems_with_verified_safe_reads():
    """A fabricated stand-in would be worse than reporting nothing."""
    import saathi.platform.api as api

    sources = api._trading_ops_sources()
    assert set(sources) == {"guardian_service", "kill_switch_store"}
    assert "approval_center" not in sources
    assert "provider_tracker" not in sources
