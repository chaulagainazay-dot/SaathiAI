"""PUBLIC-MARKET-DATA-ASYNC-READER-1 — the ingestion loop, and nothing else.

PUBLIC-MARKET-DATA-SUPERVISOR-1 left one gap: the runtime was driven by explicit
`on_frame` calls, so a real socket had nothing pulling from it. This is that
puller.

  BinanceWebSocketTransport.recv_json()  (sync, blocking, bounded by timeout)
      -> AsyncFrameReader          classify, never interpret
      -> PublicMarketDataRuntime.on_frame / on_disconnect
      -> the certified supervisor, sequence tracker and provider health

THE READER IS DATA PLUMBING, NOT MARKET AUTHORITY. It receives, classifies
framing, and dispatches. It creates no signal, parses no price into a decision,
and has no path to an order, an account or a policy.

SYNC TRANSPORT, ASYNC LOOP. The certified transport is blocking by design and is
NOT rewritten here. The reader awaits it in an executor thread, so one asyncio
task owns ingestion and stays cancellable. The blocked thread cannot be
interrupted directly — which is exactly why shutdown CLOSES THE TRANSPORT to
unblock it, and why the shutdown order below is load-bearing rather than
cosmetic.

ONE RECONNECT OWNER. `MarketDataSupervisor` already owns bounded reconnect: it
decides BACKOFF versus FAILED and computes the delay. The reader never decides to
retry — it reports the disconnect, asks what the supervisor decided, and obeys.
Two components each deciding to reconnect is how a reconnect storm starts.
"""
from __future__ import annotations

import asyncio
import contextlib
from enum import Enum

from saathi.platform.crypto.binance import StreamState

READER_VERSION = "public-market-data-reader/v1.0.0"

#: Public event types this reader will dispatch. Bounded on purpose: an event
#: the runtime cannot normalise is not evidence of a working feed.
SUPPORTED_EVENT_TYPES = frozenset({"trade", "depthUpdate"})

#: Subscribed by default. `depthUpdate` is understood but not requested unless
#: the runtime's config asks for it.
DEFAULT_EVENT_TYPES = frozenset({"trade"})


class FrameKind(str, Enum):
    """What a received frame turned out to be.

    Kept distinct because only ONE of these is evidence that market data is
    flowing, and collapsing them is how a subscription acknowledgement ends up
    looking like a live feed.
    """

    MARKET_EVENT = "MARKET_EVENT"
    #: Subscription acks, pongs, and anything else the protocol says rather than
    #: the market. Real traffic; not market data.
    CONTROL = "CONTROL"
    UNSUPPORTED_EVENT = "UNSUPPORTED_EVENT"
    MALFORMED = "MALFORMED"


class ReaderError(str, Enum):
    """Why the loop stopped or degraded. Never flattened to a generic ERROR."""

    NONE = "NONE"
    TRANSPORT_CLOSED = "TRANSPORT_CLOSED"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    DECODE_FAILED = "DECODE_FAILED"
    FRAME_TOO_LARGE = "FRAME_TOO_LARGE"
    CONSUMER_EXCEPTION = "CONSUMER_EXCEPTION"
    RECONNECT_EXHAUSTED = "RECONNECT_EXHAUSTED"
    CANCELLED = "CANCELLED"


def classify_frame(frame, *, supported: frozenset = SUPPORTED_EVENT_TYPES) -> tuple:
    """Decide what a frame is. Pure, and deliberately strict.

    Returns `(FrameKind, event_type_or_None)`. Anything that is not a dict
    carrying a supported `e` is not market data, and the caller must not let it
    touch the freshness clock.
    """
    if not isinstance(frame, dict):
        return FrameKind.MALFORMED, None
    event = frame.get("e")
    if event is None:
        # `{"result": null, "id": 1}` — a subscription acknowledgement. The
        # socket is healthy and no market data has arrived.
        if "result" in frame or "id" in frame or "ping" in frame or "pong" in frame:
            return FrameKind.CONTROL, None
        return FrameKind.MALFORMED, None
    if not isinstance(event, str):
        return FrameKind.MALFORMED, None
    if event not in supported:
        return FrameKind.UNSUPPORTED_EVENT, event
    return FrameKind.MARKET_EVENT, event


class AsyncFrameReader:
    """One bounded ingestion task for one runtime.

    Holds no queue of its own — the runtime's `BoundedStreamController` is the
    only buffer, so there is nowhere for an unbounded backlog to accumulate.
    """

    def __init__(self, runtime, *, event_types: frozenset | None = None,
                 max_idle_errors: int = 3):
        self.runtime = runtime
        self.event_types = frozenset(event_types or SUPPORTED_EVENT_TYPES)
        self.max_idle_errors = int(max_idle_errors)
        self._task: asyncio.Task | None = None
        self._stopping = False
        self.frames_seen = 0
        self.control_frames = 0
        self.unsupported_frames = 0
        self.malformed_frames = 0
        self.dispatched = 0
        self.last_error = ReaderError.NONE.value
        self.last_error_detail: str | None = None
        self.finished_cleanly = False

    # ── lifecycle ───────────────────────────────────────────────────────────
    @property
    def alive(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> asyncio.Task:
        """Start ingestion. Idempotent: a second call returns the SAME task.

        Two readers on one socket would interleave `recv` calls and shred the
        frame order the sequence tracker depends on.
        """
        if self._task is not None and not self._task.done():
            return self._task
        self._stopping = False
        self.finished_cleanly = False
        self._task = asyncio.get_running_loop().create_task(self._run())
        return self._task

    async def stop(self, *, timeout: float = 2.0) -> None:
        """Cancel the loop and wait for it to finish.

        The transport is closed by the RUNTIME, not here, and that close is what
        unblocks a thread parked in `recv`. Cancelling alone would leave the
        executor thread waiting on a socket nobody is going to feed.
        """
        self._stopping = True
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)

    # ── loop ────────────────────────────────────────────────────────────────
    async def _run(self) -> None:
        try:
            while not self._stopping:
                try:
                    frame = await self._recv()
                except asyncio.CancelledError:
                    # Never swallowed into reconnect logic: a cancel is a
                    # shutdown instruction, not a transport fault.
                    self.last_error = ReaderError.CANCELLED.value
                    raise
                except Exception as exc:
                    if not await self._handle_transport_error(exc):
                        return
                    continue

                if frame is _EOF:
                    # A socket that simply ends is NOT a quiet healthy idle.
                    if not await self._handle_transport_error(
                            EOFError("stream ended"), closed=True):
                        return
                    continue

                self.frames_seen += 1
                self._dispatch(frame)
        except asyncio.CancelledError:
            self.last_error = ReaderError.CANCELLED.value
            raise
        finally:
            self.finished_cleanly = True

    async def _recv(self):
        """Await the blocking transport without blocking the event loop."""
        transport = self.runtime.transport
        if transport is None:
            return _EOF
        recv = getattr(transport, "recv_json", None)
        if recv is None:
            return _EOF
        if asyncio.iscoroutinefunction(recv):
            return await recv()
        # The certified transport is synchronous; an executor keeps the loop
        # responsive and the task cancellable at this await point.
        return await asyncio.get_running_loop().run_in_executor(None, recv)

    def _dispatch(self, frame) -> None:
        """Route one frame. ONLY a market event may reach the runtime.

        This is the whole freshness rule in one place: control frames,
        unsupported events and malformed frames are counted and dropped here, so
        they can never reach `on_frame` and advance the observation clock.
        """
        kind, _event = classify_frame(frame, supported=self.event_types)
        if kind is FrameKind.CONTROL:
            self.control_frames += 1
            return
        if kind is FrameKind.UNSUPPORTED_EVENT:
            self.unsupported_frames += 1
            return
        if kind is FrameKind.MALFORMED:
            self.malformed_frames += 1
            self.last_error = ReaderError.DECODE_FAILED.value
            return
        try:
            self.runtime.on_frame(frame)
            self.dispatched += 1
        except Exception as exc:
            # A consumer that raises must be visible, not a silently dead task.
            self.last_error = ReaderError.CONSUMER_EXCEPTION.value
            self.last_error_detail = f"{type(exc).__name__}: {exc}"[:200]

    async def _handle_transport_error(self, exc: BaseException, *,
                                      closed: bool = False) -> bool:
        """Report the fault and do what the SUPERVISOR decided. Returns keep-going.

        The reader classifies the error and hands it over; whether to retry, and
        for how long, belongs to the supervisor's bounded reconnect budget. This
        function never invents a retry of its own.
        """
        detail = f"{type(exc).__name__}: {exc}"[:200]
        self.last_error_detail = detail
        text = detail.lower()
        if closed or isinstance(exc, EOFError):
            self.last_error = ReaderError.TRANSPORT_CLOSED.value
        elif "too large" in text:
            self.last_error = ReaderError.FRAME_TOO_LARGE.value
        elif isinstance(exc, (ValueError, TypeError)):
            self.last_error = ReaderError.DECODE_FAILED.value
        else:
            self.last_error = ReaderError.TRANSPORT_ERROR.value

        # A decode failure is a bad frame, not a dead socket: count it and read
        # on, or a single malformed message would tear down a healthy stream.
        if self.last_error in (ReaderError.DECODE_FAILED.value,
                               ReaderError.FRAME_TOO_LARGE.value):
            self.malformed_frames += 1
            if self.malformed_frames <= self.max_idle_errors:
                return True

        state = self.runtime.on_disconnect(detail)
        if state == StreamState.FAILED.value:
            self.last_error = ReaderError.RECONNECT_EXHAUSTED.value
            return False
        # The supervisor said BACKOFF and set the delay; the reader only waits.
        delay = float(self.runtime.supervisor.next_backoff())
        await asyncio.sleep(delay)
        return not self._stopping

    def diagnostics(self) -> dict:
        return {
            "reader_version": READER_VERSION,
            "alive": self.alive,
            "finished_cleanly": self.finished_cleanly,
            "frames_seen": self.frames_seen,
            "dispatched": self.dispatched,
            "control_frames": self.control_frames,
            "unsupported_frames": self.unsupported_frames,
            "malformed_frames": self.malformed_frames,
            "last_error": self.last_error,
            "last_error_detail": self.last_error_detail,
            "event_types": sorted(self.event_types),
            "authorizes_execution": False,
        }


class _Eof:
    __slots__ = ()


_EOF = _Eof()
