"""PUBLIC-MARKET-DATA-ASYNC-READER-1 — bounded ingestion, honest freshness.

The reader is the piece that finally pulls from a real socket, which makes it the
piece most able to lie: a subscription acknowledgement, a pong or a dead task can
all make a feed look alive. Most of these tests exist to stop exactly that.
"""
from __future__ import annotations

import ast
import asyncio
import gc
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from saathi.connectors.providers.models import ProviderHealthState
from saathi.platform.crypto.binance import StreamState
from saathi.platform.crypto.reader import (
    DEFAULT_EVENT_TYPES,
    SUPPORTED_EVENT_TYPES,
    AsyncFrameReader,
    FrameKind,
    ReaderError,
    classify_frame,
)
from saathi.platform.crypto.runtime import (
    PublicMarketDataConfig,
    PublicMarketDataRuntime,
    RuntimeState,
)
from saathi.platform.tg.health_collector import collect_trading_health
from saathi.platform.tg.paper_activation.ops.models import HealthClass
from saathi.platform.tg.trading_ops import Subsystem

READER_SRC = Path("saathi/platform/crypto/reader.py")
T0 = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
TRADE = {"e": "trade", "E": 1, "s": "BTCUSDT", "p": "60000.00", "q": "0.5"}
ACK = {"result": None, "id": 1}


class ScriptedWS:
    """Deterministic transport. Scripted frames, exceptions, delays, EOF."""

    def __init__(self, script=(), *, hang=False, delay=0.0, hang_after=False):
        self.script = list(script)
        self.closed = False
        self.hang = hang
        # `hang_after` models a REAL socket: deliver the scripted frames, then
        # wait quietly for more. Without it the harness EOFs the instant the
        # script empties, so every assertion lands after a disconnect the test
        # never meant to exercise.
        self.hang_after = hang_after
        self.delay = delay
        self.recv_calls = 0
        self._closed_evt = threading.Event()

    def connect(self):
        return self

    def subscribe(self, streams):
        self.sent = tuple(streams)

    def recv_json(self):
        self.recv_calls += 1
        if self.hang:
            # Blocks until the transport is closed — the real socket's behaviour.
            self._closed_evt.wait(timeout=5)
            raise EOFError("stream ended")
        if self.delay:
            threading.Event().wait(self.delay)
        if not self.script:
            if self.hang_after:
                self._closed_evt.wait(timeout=5)
            raise EOFError("stream ended")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def close(self):
        self.closed = True
        self._closed_evt.set()


def _rt(script=(), *, max_reconnects=0, max_queue=256, base_backoff=None, **ws_kw):
    ws = ScriptedWS(script, **ws_kw)
    rt = PublicMarketDataRuntime(
        PublicMarketDataConfig(enabled=True, max_reconnects=max_reconnects,
                               max_queue=max_queue),
        transport=lambda: ws)
    if base_backoff is not None:
        rt.supervisor.base_backoff = base_backoff
    return rt, ws


async def _drain(rt, *, ticks=40):
    """Let the loop run until it settles."""
    for _ in range(ticks):
        await asyncio.sleep(0.005)
        if rt.reader is not None and not rt.reader.alive:
            return


# ══ classification: only market events are market data ══════════════════════
@pytest.mark.parametrize("frame,kind", [
    (TRADE, FrameKind.MARKET_EVENT),
    ({"e": "depthUpdate", "u": 5}, FrameKind.MARKET_EVENT),
    (ACK, FrameKind.CONTROL),
    ({"id": 9}, FrameKind.CONTROL),
    ({"ping": 1}, FrameKind.CONTROL),
    ({"e": "kline"}, FrameKind.UNSUPPORTED_EVENT),
    ({"e": "24hrTicker"}, FrameKind.UNSUPPORTED_EVENT),
    ("not json", FrameKind.MALFORMED),
    (None, FrameKind.MALFORMED),
    ([], FrameKind.MALFORMED),
    ({"x": 1}, FrameKind.MALFORMED),
    ({"e": 123}, FrameKind.MALFORMED),
])
def test_frames_are_classified_strictly(frame, kind):
    assert classify_frame(frame)[0] is kind


def test_the_default_subscription_scope_stays_bounded():
    assert DEFAULT_EVENT_TYPES == {"trade"}
    assert SUPPORTED_EVENT_TYPES == {"trade", "depthUpdate"}


# ══ freshness: what may and may not advance the clock ═══════════════════════
@pytest.mark.asyncio
async def test_only_an_accepted_market_event_advances_freshness():
    rt, _ = _rt([ACK, {"e": "kline"}, {"x": "junk"}, {"ping": 1}])
    await rt.start_async()
    await _drain(rt)
    # Four frames arrived and the socket is fine; none of them is market data.
    assert rt.reader.frames_seen >= 4
    assert rt.reader.dispatched == 0
    assert rt.snapshot()["last_valid_observation"] is None
    await rt.stop_async()


@pytest.mark.asyncio
async def test_a_subscription_ack_is_not_a_live_feed():
    """NO_CONTROL_FRAME_AS_FRESHNESS — the most plausible false-green."""
    rt, _ = _rt([ACK], hang_after=True)
    await rt.start_async()
    await _drain(rt)
    md = collect_trading_health(evaluation_time="2026-09-07T12:00:00Z",
                                market_data_source=rt
                                ).health_for(Subsystem.MARKET_DATA.value)
    assert md.health_class != HealthClass.HEALTHY.value
    assert md.evidence_sufficient is False
    await rt.stop_async()


@pytest.mark.asyncio
async def test_connecting_alone_is_not_freshness():
    """NO_SOCKET_CONNECT_AS_FRESHNESS."""
    rt, _ = _rt(hang=True)
    await rt.start_async()
    await asyncio.sleep(0.05)
    snap = rt.snapshot()
    assert snap["connected"] is True
    assert snap["last_valid_observation"] is None
    await rt.stop_async()


@pytest.mark.asyncio
async def test_a_real_trade_advances_freshness_and_reaches_health():
    rt, _ = _rt([TRADE], hang_after=True)
    await rt.start_async()
    await _drain(rt, ticks=20)
    assert rt.reader.dispatched == 1
    assert rt.snapshot()["last_valid_observation"] is not None
    assert rt.provider_state() == ProviderHealthState.HEALTHY.value
    await rt.stop_async()


@pytest.mark.asyncio
async def test_a_malformed_frame_is_counted_and_never_freshness():
    """NO_MALFORMED_FRAME_AS_FRESHNESS."""
    rt, _ = _rt([{"garbage": True}, "not-a-dict"])
    await rt.start_async()
    await _drain(rt)
    assert rt.reader.malformed_frames >= 1
    assert rt.snapshot()["last_valid_observation"] is None
    await rt.stop_async()


# ══ sequence safety is not bypassed ═════════════════════════════════════════
@pytest.mark.asyncio
async def test_the_reader_does_not_shortcut_the_sequence_tracker():
    """A depth gap must still degrade, arriving via the reader."""
    rt, _ = _rt([{"e": "depthUpdate", "u": 1}, {"e": "depthUpdate", "u": 99}],
                max_reconnects=0)
    reader = AsyncFrameReader(rt, event_types=SUPPORTED_EVENT_TYPES)
    rt.start()
    rt.reader = reader
    reader.start()
    await _drain(rt)
    snap = rt.snapshot()
    assert snap["resync_pending"] is True
    assert snap["sequence_gap"] is True
    await rt.stop_async()


@pytest.mark.asyncio
async def test_a_duplicate_event_does_not_advance_the_clock_again():
    rt, _ = _rt()
    rt.start()
    rt.on_frame({"e": "depthUpdate", "u": 5}, now=T0)
    before = rt.snapshot()["last_valid_observation"]
    assert rt.on_frame({"e": "depthUpdate", "u": 5}) == "DUPLICATE"
    assert rt.snapshot()["last_valid_observation"] == before
    rt.stop()


# ══ task ownership ══════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_start_creates_exactly_one_reader_task():
    rt, _ = _rt(hang=True)
    await rt.start_async()
    first = rt.reader._task
    assert rt.reader.alive
    # A second reader on one socket would interleave recv and shred frame order.
    assert rt.reader.start() is first
    await rt.stop_async()


@pytest.mark.asyncio
async def test_repeated_start_async_does_not_multiply_tasks():
    rt, _ = _rt(hang=True)
    before = len(asyncio.all_tasks())
    await rt.start_async()
    first = rt.reader._task
    await rt.start_async()
    await rt.start_async()
    # One reader, one task — not three orphans each holding an executor thread.
    assert rt.reader._task is first
    assert len(asyncio.all_tasks()) == before + 1
    await rt.stop_async()


@pytest.mark.asyncio
async def test_five_start_stop_cycles_leak_no_task_or_thread():
    tasks_before = len(asyncio.all_tasks())
    threads_before = threading.active_count()
    for _ in range(5):
        rt, ws = _rt([TRADE], hang=False)
        await rt.start_async()
        await _drain(rt, ticks=10)
        await rt.stop_async()
        assert ws.closed is True
    gc.collect()
    await asyncio.sleep(0.05)
    assert len(asyncio.all_tasks()) <= tasks_before + 1
    assert threading.active_count() <= threads_before + 4   # executor pool only


@pytest.mark.asyncio
async def test_a_clean_restart_creates_one_new_task():
    rt, _ = _rt(hang=True)
    await rt.start_async()
    first = rt.reader._task
    await rt.stop_async()
    assert first.done() or first.cancelled()

    rt2, _ = _rt(hang=True)
    await rt2.start_async()
    assert rt2.reader.alive
    assert rt2.reader._task is not first
    await rt2.stop_async()


def test_no_task_is_created_at_import_or_construction():
    tree = ast.parse(READER_SRC.read_text())
    for node in tree.body:
        assert not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)), \
            ast.dump(node)[:120]
    rt, _ = _rt()
    assert rt.reader is None                 # construction starts nothing


# ══ dead reader is not a healthy feed ═══════════════════════════════════════
@pytest.mark.asyncio
async def test_a_dead_reader_task_stops_the_feed_looking_connected():
    """NO_READER_TASK_DEATH_AS_HEALTHY.

    The socket can stay open while nothing reads it. Reporting that as connected
    is the same lie as treating connectivity as freshness.
    """
    rt, _ = _rt([TRADE])                     # script ends -> EOF -> reader exits
    await rt.start_async()
    await _drain(rt)
    assert rt.reader.alive is False
    assert rt.snapshot()["connected"] is False


@pytest.mark.asyncio
async def test_a_consumer_exception_is_recorded_not_silently_swallowed():
    rt, _ = _rt([TRADE, TRADE], hang_after=True)

    def boom(frame, **kw):
        raise RuntimeError("consumer blew up")

    await rt.start_async()
    rt.on_frame = boom
    await _drain(rt)
    assert rt.reader.last_error == ReaderError.CONSUMER_EXCEPTION.value
    assert "consumer blew up" in (rt.reader.last_error_detail or "")
    await rt.stop_async()


# ══ error classification ════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_eof_is_reported_as_a_closed_transport_not_a_quiet_idle():
    rt, _ = _rt([])
    await rt.start_async()
    await _drain(rt)
    assert rt.reader.last_error in (ReaderError.TRANSPORT_CLOSED.value,
                                    ReaderError.RECONNECT_EXHAUSTED.value)


@pytest.mark.asyncio
async def test_an_oversized_frame_is_classified_distinctly():
    rt, _ = _rt([ValueError("frame too large"), TRADE], max_reconnects=2, hang_after=True)
    await rt.start_async()
    await _drain(rt)
    assert rt.reader.last_error in (ReaderError.FRAME_TOO_LARGE.value,
                                    ReaderError.NONE.value)
    await rt.stop_async()


@pytest.mark.asyncio
async def test_a_transport_error_is_not_flattened_into_decode_failure():
    rt, _ = _rt([OSError("connection reset")], max_reconnects=0)
    await rt.start_async()
    await _drain(rt)
    assert rt.reader.last_error in (ReaderError.TRANSPORT_ERROR.value,
                                    ReaderError.RECONNECT_EXHAUSTED.value)


@pytest.mark.asyncio
async def test_one_bad_frame_does_not_tear_down_a_healthy_stream():
    """A single malformed message must not kill ingestion."""
    rt, _ = _rt([ValueError("bad json"), TRADE], max_reconnects=3, hang_after=True)
    await rt.start_async()
    await _drain(rt)
    assert rt.reader.dispatched == 1
    await rt.stop_async()


# ══ reconnect: one owner ════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_reconnect_exhaustion_stops_the_reader_and_is_failed_safe():
    rt, _ = _rt([OSError("drop"), OSError("drop"), OSError("drop")],
                max_reconnects=1, base_backoff=0)
    await rt.start_async()
    await _drain(rt, ticks=80)
    assert rt.reader.alive is False
    assert rt.reader.last_error == ReaderError.RECONNECT_EXHAUSTED.value
    assert rt.state is RuntimeState.FAILED_SAFE
    assert rt.snapshot()["contained"] is True


def test_the_reader_owns_no_reconnect_decision():
    """NO_DUPLICATE_RECONNECT_OWNER — the supervisor decides, the reader waits."""
    src = READER_SRC.read_text()
    # It may not reconnect, resubscribe or reopen the transport itself.
    for token in (".connect(", ".subscribe(", "create_connection", "reconnect_count ="):
        assert token not in src, token
    tree = ast.parse(src)
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "next_backoff" in called          # it asks
    assert "connect" not in called           # it never dials


# ══ cancellation and shutdown ═══════════════════════════════════════════════
@pytest.mark.asyncio
async def test_shutdown_while_blocked_in_recv_completes():
    """The executor thread is freed by CLOSING the transport, not by cancelling."""
    rt, ws = _rt(hang=True)
    await rt.start_async()
    await asyncio.sleep(0.05)
    await asyncio.wait_for(rt.stop_async(), timeout=4)
    assert ws.closed is True
    assert rt.state is RuntimeState.STOPPED


@pytest.mark.asyncio
async def test_shutdown_during_reconnect_backoff_completes():
    rt, ws = _rt([OSError("drop")] * 5, max_reconnects=5)
    await rt.start_async()
    await asyncio.sleep(0.02)
    await asyncio.wait_for(rt.stop_async(), timeout=4)
    assert ws.closed is True


@pytest.mark.asyncio
async def test_cancellation_is_not_swallowed_into_reconnect():
    rt, _ = _rt(hang=True)
    await rt.start_async()
    task = rt.reader._task
    await asyncio.sleep(0.02)
    await rt.stop_async()
    assert rt.reader is None or not rt.reader.alive
    assert task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_stop_is_safe_when_the_reader_never_started():
    rt, _ = _rt()
    assert await rt.stop_async() == RuntimeState.STOPPED.value


# ══ bounded buffers ═════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_the_reader_adds_no_queue_of_its_own():
    """NO_UNBOUNDED_READER_QUEUE — the controller is the only buffer."""
    src = READER_SRC.read_text()
    for token in ("deque(", "= []", "Queue(", "asyncio.Queue"):
        assert token not in src, token
    rt, _ = _rt([TRADE] * 500, max_queue=8)
    await rt.start_async()
    await _drain(rt, ticks=120)
    assert len(rt.controller.queue) <= 8
    await rt.stop_async()


@pytest.mark.asyncio
async def test_a_slow_consumer_keeps_memory_bounded_and_surfaces_overflow():
    rt, _ = _rt([{"e": "trade", "n": i} for i in range(400)], max_queue=4)
    await rt.start_async()
    await _drain(rt, ticks=150)
    assert len(rt.controller.queue) <= 4
    assert rt.frames_dropped > 0             # surfaced, not silent
    await rt.stop_async()


# ══ integration through the real health chain ═══════════════════════════════
@pytest.mark.asyncio
async def test_reader_events_reach_the_trading_ops_snapshot_unshaped():
    from saathi.platform.tg.health_producers import snapshot_from_producers
    from saathi.platform.tg.runtime_wiring import (
        collector_sources, resolve_all, unavailable_reasons,
    )
    from saathi.platform.tg.trading_ops import OpsMode
    from saathi.platform.crypto.runtime import reset_public_market_data_for_tests

    rt = reset_public_market_data_for_tests(PublicMarketDataConfig(enabled=True))
    ws = ScriptedWS([TRADE], hang_after=True)
    rt._transport_factory = lambda: ws
    await rt.start_async()
    await _drain(rt, ticks=20)

    w = resolve_all()
    result = collect_trading_health(
        evaluation_time=rt.snapshot()["last_valid_observation"],
        unavailable_reasons=unavailable_reasons(w), **collector_sources(w))
    snap = snapshot_from_producers(
        result.healths, observed_at=rt.snapshot()["last_valid_observation"],
        mode=OpsMode.SHADOW.value)
    subs = {s.subsystem: s for s in snap.subsystems}
    assert subs[Subsystem.PROVIDER.value].health == HealthClass.HEALTHY.value
    # LIVE_PUBLIC data with SHADOW execution never collapses into live trading.
    assert snap.mode == OpsMode.SHADOW.value
    assert snap.live_trading_authorized is False
    reset_public_market_data_for_tests()


# ══ authority and security ══════════════════════════════════════════════════
def test_the_reader_holds_no_execution_authority():
    tree = ast.parse(READER_SRC.read_text())
    called = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Attribute):
                called.add(n.func.attr)
            elif isinstance(n.func, ast.Name):
                called.add(n.func.id)
    forbidden = {"submit", "place", "create_order", "cancel_order", "execute",
                 "withdraw", "transfer", "reserve", "approve", "consume",
                 "set_policy", "set_limit"}
    assert not (forbidden & called), forbidden & called
    assert AsyncFrameReader(None).diagnostics()["authorizes_execution"] is False


def test_the_reader_reaches_no_private_surface_and_needs_no_credential():
    from saathi.platform.crypto.runtime import FORBIDDEN_PATH_MARKERS

    src = READER_SRC.read_text()
    for marker in FORBIDDEN_PATH_MARKERS:
        assert marker not in src, marker
    for token in ("api_key", "secret", "hmac", "signature", "keyring", "http"):
        assert token not in src.lower().replace("https://", ""), token


def test_the_reader_imports_nothing_heavy_or_networked():
    tree = ast.parse(READER_SRC.read_text())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
        elif isinstance(n, ast.Import):
            mods.update(a.name.split(".")[0] for a in n.names)
    for banned in ("requests", "httpx", "urllib", "socket", "websocket",
                   "kafka", "redis", "celery"):
        assert banned not in mods, banned


# ══ resource budget ═════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_sustained_ingestion_holds_memory_and_tasks_flat():
    """Target M2 / 8 GB: the loop must be cheap enough to run continuously."""
    import resource

    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    tasks_before = len(asyncio.all_tasks())

    rt, _ = _rt([{"e": "trade", "n": i} for i in range(3000)],
                max_queue=32, hang_after=True)
    await rt.start_async()
    await _drain(rt, ticks=400)

    assert len(rt.controller.queue) <= 32
    assert len(asyncio.all_tasks()) <= tasks_before + 1
    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Bounded ring buffers: 3k frames must not move resident memory materially.
    assert (rss_after - rss_before) < 200 * 1024 * 1024, (rss_before, rss_after)
    await rt.stop_async()


@pytest.mark.asyncio
async def test_shutdown_latency_is_bounded_even_while_blocked():
    import time

    rt, _ = _rt(hang=True)
    await rt.start_async()
    await asyncio.sleep(0.05)
    t0 = time.perf_counter()
    await rt.stop_async()
    assert (time.perf_counter() - t0) < 3.0


@pytest.mark.asyncio
async def test_repeated_cycles_do_not_accumulate_readers():
    from saathi.platform.crypto.runtime import reset_public_market_data_for_tests

    for _ in range(5):
        rt = reset_public_market_data_for_tests(PublicMarketDataConfig(enabled=True))
        rt._transport_factory = lambda: ScriptedWS([TRADE], hang_after=True)
        await rt.start_async()
        await _drain(rt, ticks=10)
        await rt.stop_async()
        assert rt.reader is None or not rt.reader.alive
    reset_public_market_data_for_tests()
