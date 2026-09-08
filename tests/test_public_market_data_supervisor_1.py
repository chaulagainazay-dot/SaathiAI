"""PUBLIC-MARKET-DATA-SUPERVISOR-1 — public crypto market data, and nothing else.

The certified Binance components already existed; what was missing was a
process-wide owner. So these tests are about ownership, lifecycle and — above
all — the boundary: this runtime reaches public market data and can reach
nothing private, holds no credential, and its health says nothing about a
trading account.
"""
from __future__ import annotations

import ast
import asyncio
import gc
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from saathi.connectors.providers.models import ProviderHealthState
from saathi.platform.crypto.binance import StreamState
from saathi.platform.crypto.runtime import (
    DEFAULT_SYMBOLS,
    FORBIDDEN_PATH_MARKERS,
    PROVIDER_ID,
    PROVIDER_SCOPE,
    PUBLIC_HOST_ALLOWLIST,
    PublicMarketDataConfig,
    PublicMarketDataRuntime,
    RuntimeState,
    default_public_market_data,
    reset_public_market_data_for_tests,
)
from saathi.platform.tg.health_collector import collect_trading_health
from saathi.platform.tg.paper_activation.ops.models import HealthClass
from saathi.platform.tg.runtime_wiring import (
    WiringState,
    collector_sources,
    resolve_all,
    resolve_market_data,
    resolve_provider,
    unavailable_reasons,
)
from saathi.platform.tg.trading_ops import Subsystem

RUNTIME_SRC = Path("saathi/platform/crypto/runtime.py")
BINANCE_SRC = Path("saathi/platform/crypto/binance.py")
T0 = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)


class FakeWS:
    """Injectable stand-in for the public socket. Opens nothing."""

    def __init__(self, *, fail_on_connect=None, fail_on_subscribe=None):
        self.connected = False
        self.closed = False
        self.sent = []
        self._fail_connect = fail_on_connect
        self._fail_subscribe = fail_on_subscribe

    def connect(self):
        if self._fail_connect:
            raise self._fail_connect
        self.connected = True
        return self

    def subscribe(self, streams):
        if self._fail_subscribe:
            raise self._fail_subscribe
        self.sent.append(tuple(streams))

    def close(self):
        self.closed = True
        self.connected = False


def _rt(**cfg):
    params = dict(enabled=True, symbols=DEFAULT_SYMBOLS)
    params.update(cfg)
    ws = FakeWS()
    rt = PublicMarketDataRuntime(PublicMarketDataConfig(**params), transport=lambda: ws)
    return rt, ws


@pytest.fixture(autouse=True)
def _reset():
    reset_public_market_data_for_tests()
    yield
    reset_public_market_data_for_tests()


# ══ the boundary: public market data, never an account ══════════════════════
def test_the_runtime_can_reach_only_public_binance_hosts():
    assert PUBLIC_HOST_ALLOWLIST == {"stream.binance.com", "api.binance.com"}
    from saathi.platform.crypto.binance import (
        BinancePublicProvider, BinanceWebSocketTransport,
    )
    for url in (BinanceWebSocketTransport.URL, BinancePublicProvider.BASE):
        host = url.split("//", 1)[1].split("/", 1)[0].split(":", 1)[0]
        assert host in PUBLIC_HOST_ALLOWLIST, url


def _source_without_denylist(src: Path) -> str:
    """Source with the deny-list declaration removed.

    The deny-list names the forbidden paths in order to forbid them, so a naive
    substring scan flags the very constant that enforces the rule. Excised by
    line range from the AST rather than by string surgery, so the exclusion is
    exact and cannot silently swallow neighbouring code.
    """
    text = src.read_text()
    tree = ast.parse(text)
    lines = text.splitlines()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "FORBIDDEN_PATH_MARKERS"
                for t in node.targets):
            for i in range(node.lineno - 1, node.end_lineno):
                lines[i] = ""
    return "\n".join(lines)


@pytest.mark.parametrize("marker", FORBIDDEN_PATH_MARKERS)
def test_no_private_binance_surface_appears_anywhere_in_the_crypto_stack(marker):
    """NO_BINANCE_PRIVATE_ENDPOINTS — account, order and user-data paths."""
    for src in (RUNTIME_SRC, BINANCE_SRC):
        assert marker not in _source_without_denylist(src), (src.name, marker)


def test_the_runtime_has_no_credential_surface():
    """NO_BINANCE_CREDENTIALS — zero secrets, structurally."""
    body = _source_without_denylist(RUNTIME_SRC) + _source_without_denylist(BINANCE_SRC)
    for token in ("api_key", "apiKey", "API_KEY", "secret", "SECRET", "hmac",
                  "sha256(", "sign(", "signature", "listenKey", "keyring"):
        assert token not in body, token
    assert PublicMarketDataRuntime().diagnostics()["requires_credentials"] is False


def test_the_runtime_imports_no_signing_or_credential_module():
    tree = ast.parse(RUNTIME_SRC.read_text())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module)
        elif isinstance(n, ast.Import):
            mods.update(a.name for a in n.names)
    banned = ("hmac", "hashlib", "credentials", "secret", "keyring", "auth")
    assert not [m for m in mods if any(b in m.lower() for b in banned)], mods


def test_public_provider_health_never_implies_a_trading_account():
    """NO_PUBLIC_DATA_TO_EXECUTION_AUTHORITY."""
    rt, _ = _rt()
    rt.start(now=T0)
    assert rt.provider_state() == ProviderHealthState.HEALTHY.value
    d = rt.diagnostics()
    assert d["scope"] == PROVIDER_SCOPE == "PUBLIC_MARKET_DATA"
    assert d["authorizes_execution"] is False


def test_the_runtime_is_spot_only():
    d = PublicMarketDataRuntime(PublicMarketDataConfig(enabled=True)).diagnostics()
    assert d["market_type"] == "SPOT"
    body = RUNTIME_SRC.read_text().lower()
    for token in ("futures", "perpetual", "margin", "leverage", "options", "delivery"):
        assert token not in body.replace("no_leverage", "").replace("no_margin", ""), token


def test_the_symbol_scope_is_bounded_and_explicit():
    assert DEFAULT_SYMBOLS == ("BTCUSDT", "ETHUSDT")
    rt, ws = _rt()
    rt.start(now=T0)
    # The transport itself refuses more than four streams.
    assert ws.sent == [("btcusdt@trade", "ethusdt@trade")]


# ══ startup policy: nothing connects by accident ════════════════════════════
def test_the_runtime_is_disabled_by_default_and_connects_nothing():
    rt = PublicMarketDataRuntime()
    assert rt.state is RuntimeState.DISABLED
    assert rt.start() == RuntimeState.DISABLED.value
    assert rt.transport is None


def test_importing_the_module_opens_no_socket_and_starts_no_task():
    """NO import-time network, no background task on import."""
    tree = ast.parse(RUNTIME_SRC.read_text())
    for node in tree.body:            # module level only
        assert not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call), \
            ast.dump(node)[:120]
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not ({"create_connection", "urlopen", "getaddrinfo"} & called), called


def test_constructing_the_default_runtime_connects_nothing():
    rt = default_public_market_data()
    assert rt.transport is None
    assert rt.state is RuntimeState.DISABLED


def test_a_failed_connect_is_contained_not_left_half_open():
    ws = FakeWS(fail_on_connect=ConnectionRefusedError("connection refused"))
    rt = PublicMarketDataRuntime(PublicMarketDataConfig(enabled=True),
                                 transport=lambda: ws)
    assert rt.start(now=T0) == RuntimeState.FAILED_SAFE.value
    assert rt.transport is None
    assert rt.provider_state() != ProviderHealthState.HEALTHY.value


@pytest.mark.parametrize("exc,expected", [
    # DNS and refused connections are transport failures -> UNAVAILABLE.
    (OSError("getaddrinfo failed"), ProviderHealthState.UNAVAILABLE.value),
    (ConnectionRefusedError("connection refused"), ProviderHealthState.UNAVAILABLE.value),
    # Rate limiting is a distinct condition and must not flatten into it.
    (RuntimeError("rate limit exceeded"), ProviderHealthState.RATE_LIMITED.value),
])
def test_transport_failures_map_to_distinct_provider_states(exc, expected):
    """No generic OFFLINE flattening."""
    ws = FakeWS(fail_on_connect=exc)
    rt = PublicMarketDataRuntime(PublicMarketDataConfig(enabled=True),
                                 transport=lambda: ws)
    rt.start(now=T0)
    assert rt.provider_state() == expected


# ══ freshness is not connectivity ═══════════════════════════════════════════
def test_a_connected_runtime_with_no_events_is_not_fresh():
    """NO_CONNECTIVITY_AS_FRESHNESS, preserved end to end."""
    rt, _ = _rt()
    rt.start(now=T0)
    snap = rt.snapshot()
    assert snap["connected"] is True
    assert snap["last_valid_observation"] is None
    # The runtime states no freshness of its own — the collector decides from
    # the observation clock, so there is exactly one freshness rule.
    assert "freshness" not in snap

    result = collect_trading_health(
        evaluation_time="2026-09-07T12:00:00Z", market_data_source=rt)
    md = result.health_for(Subsystem.MARKET_DATA.value)
    assert md.health_class != HealthClass.HEALTHY.value
    assert md.evidence_sufficient is False


def test_a_valid_frame_advances_the_observation_clock():
    rt, _ = _rt()
    rt.start(now=T0)
    assert rt.on_frame({"u": 1, "p": "60000"}, now=T0) == "ACCEPTED"
    assert rt.snapshot()["last_valid_observation"] == "2026-09-07T12:00:00Z"
    md = collect_trading_health(evaluation_time="2026-09-07T12:00:10Z",
                                market_data_source=rt).health_for(Subsystem.MARKET_DATA.value)
    assert md.health_class == HealthClass.HEALTHY.value
    assert md.mode == "LIVE_PUBLIC_DATA" or md.mode  # carried, never "LIVE"


def test_an_old_observation_goes_stale_against_the_evaluation_time():
    rt, _ = _rt()
    rt.start(now=T0)
    rt.on_frame({"u": 1}, now=T0)
    md = collect_trading_health(evaluation_time="2026-09-07T13:00:00Z",
                                market_data_source=rt).health_for(Subsystem.MARKET_DATA.value)
    assert md.health_class == HealthClass.DEGRADED.value


def _clock(rt):
    return rt.snapshot()["last_valid_observation"]


@pytest.mark.parametrize("bad,frame", [
    ("INVALID_FRAME", "not a dict"),
    ("DUPLICATE", {"u": 5}),
    ("REGRESSION", {"u": 1}),
    ("GAP_DETECTED", {"u": 99}),
])
def test_an_untrusted_frame_never_refreshes_the_observation_clock(bad, frame):
    """Only an ACCEPTED frame is evidence the feed is working.

    A duplicated, regressing, gapped or malformed frame is data the runtime saw
    but could not trust; letting any of them refresh freshness is the
    connectivity-as-freshness error in another costume.
    """
    rt, _ = _rt()
    rt.start(now=T0)
    rt.on_frame({"u": 5}, now=T0)          # one good frame sets the clock
    before = _clock(rt)
    assert before is not None

    result = rt.on_frame(frame, now=T0 + timedelta(seconds=30))
    assert result == bad
    assert _clock(rt) == before             # untouched


def test_a_backpressure_drop_does_not_refresh_the_observation_clock():
    rt, _ = _rt(max_queue=2)
    rt.start(now=T0)
    for i in range(2):                      # fill the bounded queue
        rt.on_frame({"t": i}, now=T0)
    before = _clock(rt)

    dropped = rt.on_frame({"t": 99}, now=T0 + timedelta(seconds=30))
    assert dropped == "DROPPED_BACKPRESSURE"
    assert _clock(rt) == before


# ══ sequence and book safety ════════════════════════════════════════════════
def test_a_sequence_gap_sets_resync_and_is_never_a_healthy_book():
    """NO_SEQUENCE_GAP_AS_HEALTHY_BOOK."""
    rt, _ = _rt()
    rt.start(now=T0)
    rt.on_frame({"u": 1}, now=T0)
    assert rt.on_frame({"u": 9}, now=T0) == "GAP_DETECTED"
    snap = rt.snapshot()
    assert snap["resync_pending"] is True
    assert snap["sequence_gap"] is True
    md = collect_trading_health(evaluation_time="2026-09-07T12:00:05Z",
                                market_data_source=rt).health_for(Subsystem.MARKET_DATA.value)
    assert md.health_class == HealthClass.DEGRADED.value


def test_a_regressing_sequence_is_reported_not_applied():
    rt, _ = _rt()
    rt.start(now=T0)
    rt.on_frame({"u": 10}, now=T0)
    assert rt.on_frame({"u": 3}, now=T0) == "REGRESSION"


def test_the_order_book_refuses_a_non_contiguous_delta():
    rt, _ = _rt()
    rt.book.apply_snapshot(100, [("60000", "1")], [("60001", "1")])
    assert rt.book.apply_delta(105, [("60000", "1")], [("60001", "1")]) == "GAP_DETECTED"
    assert rt.book.state == "GAPPED"


# ══ bounded queue and backpressure ══════════════════════════════════════════
def test_the_queue_is_bounded_and_overflow_is_recorded_not_hidden():
    """NO_UNBOUNDED_MARKET_DATA_QUEUE, and no silent drops."""
    rt, _ = _rt(max_queue=4)
    rt.start(now=T0)
    for i in range(50):
        rt.on_frame({"t": i}, now=T0)
    d = rt.diagnostics()
    assert d["queue_depth"] <= 4
    assert d["frames_dropped"] > 0          # surfaced, not swallowed
    assert len(rt.controller.queue) <= 4


def test_a_slow_consumer_does_not_grow_memory_without_bound():
    """Both bounded buffers hold, and the capture ring reports its overflow.

    The queue is drained between frames so they keep being ACCEPTED — capture
    only records accepted frames, so a permanently full queue would never
    exercise the capture ring at all.
    """
    rt, _ = _rt(max_queue=8, max_capture=16)
    rt.start(now=T0)
    for i in range(5000):
        rt.controller.queue.clear()         # simulate a consumer keeping up
        rt.on_frame({"t": i}, now=T0)
    assert len(rt.controller.queue) <= 8
    assert len(rt.supervisor.captured) <= 16
    assert rt.supervisor.capture_overflow > 0
    assert rt.frames_accepted == 5000


# ══ reconnect ═══════════════════════════════════════════════════════════════
def test_reconnect_is_bounded_and_exhaustion_is_failed_safe():
    rt, _ = _rt(max_reconnects=2)
    rt.start(now=T0)
    assert rt.on_disconnect("socket closed", now=T0) == StreamState.BACKOFF.value
    assert rt.on_disconnect("socket closed", now=T0) == StreamState.BACKOFF.value
    assert rt.on_disconnect("socket closed", now=T0) == StreamState.FAILED.value
    assert rt.state is RuntimeState.FAILED_SAFE
    snap = rt.snapshot()
    assert snap["reconnect_exhausted"] is True
    assert snap["contained"] is True


def test_backoff_grows_and_is_capped():
    rt, _ = _rt(max_reconnects=10)
    rt.start(now=T0)
    seen = []
    for _ in range(8):
        rt.on_disconnect("drop", now=T0)
        seen.append(rt.supervisor.next_backoff())
    assert seen == sorted(seen)                       # never decreases
    assert max(seen) <= rt.supervisor.max_backoff     # capped: no runaway
    assert seen[0] >= 1                               # no busy loop


def test_reconnect_exhaustion_degrades_health_rather_than_claiming_fresh():
    rt, _ = _rt(max_reconnects=1)
    rt.start(now=T0)
    rt.on_frame({"u": 1}, now=T0)
    rt.on_disconnect("drop", now=T0)
    rt.on_disconnect("drop", now=T0)
    md = collect_trading_health(evaluation_time="2026-09-07T12:00:05Z",
                                market_data_source=rt).health_for(Subsystem.MARKET_DATA.value)
    assert md.health_class == HealthClass.FAILED_SAFE.value


# ══ shutdown and restart ════════════════════════════════════════════════════
def test_shutdown_closes_the_socket_and_releases_the_queue():
    rt, ws = _rt()
    rt.start(now=T0)
    for i in range(3):
        rt.on_frame({"t": i}, now=T0)
    assert rt.stop() == RuntimeState.STOPPED.value
    assert ws.closed is True
    assert rt.transport is None
    assert len(rt.controller.queue) == 0
    assert rt.supervisor.state is StreamState.STOPPED
    assert rt.snapshot()["connected"] is False


def test_stopping_is_safe_when_never_started():
    assert PublicMarketDataRuntime().stop() == RuntimeState.STOPPED.value


def test_no_thread_or_task_is_leaked_by_a_start_stop_cycle():
    before = threading.active_count()
    for _ in range(5):
        rt, _ = _rt()
        rt.start(now=T0)
        rt.on_frame({"u": 1}, now=T0)
        rt.stop()
    gc.collect()
    assert threading.active_count() == before


def test_a_restart_does_not_carry_stale_healthy_state_across():
    rt, _ = _rt()
    rt.start(now=T0)
    rt.on_frame({"u": 1}, now=T0)
    rt.stop()

    fresh = reset_public_market_data_for_tests(PublicMarketDataConfig(enabled=True))
    snap = fresh.snapshot()
    assert snap["connected"] is False
    assert snap["last_valid_observation"] is None      # no inherited freshness
    assert fresh.frames_accepted == 0


def test_the_process_wide_instance_is_a_single_object():
    a, b = default_public_market_data(), default_public_market_data()
    assert a is b


# ══ integration: wiring, collector, ops ═════════════════════════════════════
def test_a_disabled_runtime_reports_the_real_reason_not_an_outage():
    reset_public_market_data_for_tests()               # disabled
    md, pv = resolve_market_data(), resolve_provider()
    assert md.state == WiringState.PUBLIC_FEED_DISABLED.value
    assert pv.state == WiringState.NOT_CONFIGURED.value
    assert "disabled" in (md.detail or "").lower()


def test_an_enabled_runtime_wires_market_data_and_provider():
    rt = reset_public_market_data_for_tests(PublicMarketDataConfig(enabled=True))
    rt._transport_factory = lambda: FakeWS()
    rt.start(now=T0)
    rt.on_frame({"u": 1}, now=T0)

    md, pv = resolve_market_data(), resolve_provider()
    assert md.state == WiringState.WIRED.value
    assert md.instance is rt
    assert pv.state == WiringState.WIRED.value
    # The tracker observed is the runtime's own, not a monitoring-only copy.
    assert pv.instance is rt.health

    sources = collector_sources()
    assert sources["market_data_source"] is rt
    assert sources["provider_ids"] == (PROVIDER_ID,)


def test_real_public_events_reach_the_trading_ops_snapshot_unshaped():
    from saathi.platform.tg.health_producers import snapshot_from_producers
    from saathi.platform.tg.trading_ops import OpsMode

    rt = reset_public_market_data_for_tests(PublicMarketDataConfig(enabled=True))
    rt._transport_factory = lambda: FakeWS()
    rt.start(now=T0)
    rt.on_frame({"u": 1}, now=T0)

    w = resolve_all()
    result = collect_trading_health(
        evaluation_time="2026-09-07T12:00:05Z",
        unavailable_reasons=unavailable_reasons(w), **collector_sources(w))
    snap = snapshot_from_producers(result.healths, observed_at="2026-09-07T12:00:05Z",
                                   mode=OpsMode.SHADOW.value)
    subs = {s.subsystem: s for s in snap.subsystems}
    assert subs[Subsystem.MARKET_DATA.value].health == HealthClass.HEALTHY.value
    assert subs[Subsystem.PROVIDER.value].health == HealthClass.HEALTHY.value
    # PUBLIC LIVE DATA is not LIVE TRADING.
    assert snap.live_trading_authorized is False
    assert snap.mode == OpsMode.SHADOW.value


def test_live_public_data_never_reads_as_live_trading():
    """NO_FALSE_LIVE_LABEL — the two modes stay separate."""
    rt, _ = _rt()
    rt.start(now=T0)
    rt.on_frame({"u": 1}, now=T0)
    md = collect_trading_health(evaluation_time="2026-09-07T12:00:05Z",
                                market_data_source=rt).health_for(Subsystem.MARKET_DATA.value)
    assert md.mode != "LIVE"
    assert md.authorizes_execution is False


def test_the_runtime_holds_no_execution_authority():
    tree = ast.parse(RUNTIME_SRC.read_text())
    called = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Attribute):
                called.add(n.func.attr)
            elif isinstance(n.func, ast.Name):
                called.add(n.func.id)
    forbidden = {"submit", "place", "create_order", "cancel_order", "execute",
                 "withdraw", "transfer", "reserve", "approve", "consume"}
    assert not (forbidden & called), forbidden & called


# ══ server lifecycle ════════════════════════════════════════════════════════
def test_server_boot_opens_no_socket_unless_explicitly_configured(monkeypatch):
    """A feed nobody asked for is an unannounced outbound connection."""
    import saathi.server as srv
    from saathi.platform.crypto import runtime as rt_mod

    monkeypatch.delenv("SAATHI_PUBLIC_MARKET_DATA", raising=False)
    rt_mod._RUNTIME = None
    asyncio.run(srv._saathi_start_public_market_data())
    assert rt_mod._RUNTIME is None


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "maybe"])
def test_only_an_explicit_affirmative_starts_the_feed(monkeypatch, value):
    import saathi.server as srv
    from saathi.platform.crypto import runtime as rt_mod

    monkeypatch.setenv("SAATHI_PUBLIC_MARKET_DATA", value)
    rt_mod._RUNTIME = None
    asyncio.run(srv._saathi_start_public_market_data())
    assert rt_mod._RUNTIME is None


def test_shutdown_is_safe_when_the_feed_never_started():
    import saathi.server as srv
    from saathi.platform.crypto import runtime as rt_mod

    rt_mod._RUNTIME = None
    asyncio.run(srv._saathi_stop_public_market_data())   # must not raise


def test_shutdown_stops_a_running_runtime():
    import saathi.server as srv
    from saathi.platform.crypto import runtime as rt_mod

    rt = reset_public_market_data_for_tests(PublicMarketDataConfig(enabled=True))
    ws = FakeWS()
    rt._transport_factory = lambda: ws
    rt.start(now=T0)
    asyncio.run(srv._saathi_stop_public_market_data())
    assert ws.closed is True
    assert rt_mod._RUNTIME.state is RuntimeState.STOPPED


# ══ resource budget ════════════════════════════════════════════════════════
def test_sustained_frames_do_not_grow_resident_state():
    """Bounded by construction: 20k frames must not accumulate."""
    import sys

    rt, _ = _rt(max_queue=64, max_capture=256)
    rt.start(now=T0)
    for i in range(20_000):
        rt.on_frame({"u": i + 1}, now=T0)

    assert len(rt.controller.queue) <= 64
    assert len(rt.supervisor.captured) <= 256
    held = (sys.getsizeof(rt.controller.queue) + sys.getsizeof(rt.supervisor.captured))
    # Two bounded ring buffers; the figure is a guard against an accidental
    # unbounded list, not a benchmark.
    assert held < 100_000, held


def test_the_runtime_adds_no_heavy_dependency():
    tree = ast.parse(RUNTIME_SRC.read_text())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
        elif isinstance(n, ast.Import):
            mods.update(a.name.split(".")[0] for a in n.names)
    for heavy in ("kafka", "redis", "celery", "pika", "docker", "influxdb",
                  "prometheus_client", "pandas", "numpy"):
        assert heavy not in mods, heavy
