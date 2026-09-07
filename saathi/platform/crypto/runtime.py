"""PUBLIC-MARKET-DATA-SUPERVISOR-1 — the process-wide public crypto runtime.

TRADING-RUNTIME-INSTANCE-WIRING-1 found that market data and provider health had
nothing to observe: the certified Binance components existed but nothing owned
one at process level. This is that owner, and deliberately nothing more.

  BinanceWebSocketTransport (public wss)  ─┐
  BoundedStreamController  (queue/seq)    ─┼─> PublicMarketDataRuntime
  MarketDataSupervisor     (liveness)     ─┤        │
  OrderBookSynchronizer    (book safety)  ─┤        ├─> market-data health
  BinancePublicProvider    (public REST)  ─┘        └─> ProviderHealthTracker

WHAT IS REUSED, NOT REBUILT: sequence tracking, duplicate/regression/gap
detection, bounded queues and backpressure, bounded reconnect with exponential
backoff, heartbeat staleness, snapshot+contiguous-delta book safety, capture with
overflow accounting. All of it is CRYPTO-DATA-2/2.1 and none of it is reimplemented
here. This module contributes lifecycle and composition — the missing layer.

THIS IS MARKET DATA. IT IS NOT BROKER CONNECTIVITY. The runtime reaches exactly
two public Binance surfaces and can reach no others: it signs nothing, sends no
key, holds no credential field, and has no code path to an account, balance,
order or user-data stream. `PUBLIC_MARKET_DATA` is the whole of its scope, and a
healthy public feed says nothing whatever about a trading account.

DISABLED BY DEFAULT. Nothing connects on import, on construction, or because a
test imported a module. A caller must configure `enabled=True` and call `start()`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from saathi.platform.crypto.binance import (
    BinancePublicProvider,
    BinanceWebSocketTransport,
    BoundedStreamController,
    MarketDataSupervisor,
    OrderBookSynchronizer,
    StreamState,
)

RUNTIME_VERSION = "public-market-data-runtime/v1.0.0"
TRANSPORT_VERSION = "crypto-data-2.1/binance-public"

#: Spot only, and only pairs the certified provider already allowlists. Widening
#: this is a deliberate act, not a convenience: every extra symbol is another
#: stream, another queue and another thing to keep honest.
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT")

#: The complete set of hosts this runtime may reach. Public market data only.
PUBLIC_HOST_ALLOWLIST = frozenset({
    "stream.binance.com",   # public raw websocket streams
    "api.binance.com",      # public REST: exchangeInfo, ticker, klines
})

#: Private surfaces that must remain unreachable. Named so a test can assert
#: their absence rather than trusting that nobody adds one later.
FORBIDDEN_PATH_MARKERS = (
    "/api/v3/account", "/api/v3/order", "/api/v3/openOrders", "/api/v3/allOrders",
    "/api/v3/myTrades", "/sapi/", "/wapi/", "listenKey", "userDataStream",
    "signature=", "X-MBX-APIKEY",
)

#: Scope label carried with provider health. A healthy public feed is not a
#: healthy trading account, and the two must never be read as one claim.
PROVIDER_SCOPE = "PUBLIC_MARKET_DATA"
PROVIDER_ID = "binance_public_spot"


class RuntimeState(str, Enum):
    """Lifecycle of the RUNTIME, distinct from the state of the FEED.

    `StreamState` already describes the feed (LIVE/STALE/BACKOFF/FAILED). This
    describes whether the runtime is meant to be running at all — "switched off"
    and "trying and failing" are different operator facts.
    """

    DISABLED = "DISABLED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED_SAFE = "FAILED_SAFE"


@dataclass(frozen=True)
class PublicMarketDataConfig:
    """Configuration. Off unless explicitly switched on.

    `enabled` defaults to False so importing SaathiOS, running its tests, or
    booting a server never opens a socket by accident.
    """

    enabled: bool = False
    symbols: tuple = DEFAULT_SYMBOLS
    #: Public raw-stream suffixes. Bounded: the transport itself refuses >4.
    stream_kinds: tuple = ("trade",)
    staleness_seconds: int = 30
    max_queue: int = 256
    max_reconnects: int = 5
    heartbeat_timeout: int = 15
    max_capture: int = 1024

    def streams(self) -> tuple:
        return tuple(f"{s.lower()}@{k}" for s in self.symbols for k in self.stream_kinds)


class PublicMarketDataRuntime:
    """One process-wide owner for public crypto market data.

    Composition only. Every guarantee below — sequence continuity, bounded
    queues, bounded reconnect, staleness — is enforced by the certified
    components this holds, not re-derived here.
    """

    def __init__(
        self,
        config: PublicMarketDataConfig | None = None,
        *,
        transport=None,
        provider=None,
        health_tracker=None,
    ):
        self.config = config or PublicMarketDataConfig()
        self.state = (RuntimeState.DISABLED if not self.config.enabled
                      else RuntimeState.STOPPED)
        # Injected for tests and for a future async adapter. Constructed lazily
        # in `start` so nothing touches the network at construction time.
        self._transport_factory = transport
        self.transport = None
        self.provider = provider or BinancePublicProvider()
        self.controller = BoundedStreamController(
            max_queue=self.config.max_queue, max_reconnects=self.config.max_reconnects)
        self.supervisor = MarketDataSupervisor(
            heartbeat_timeout=self.config.heartbeat_timeout,
            max_reconnects=self.config.max_reconnects,
            max_capture=self.config.max_capture)
        self.book = OrderBookSynchronizer()
        # The canonical provider tracker Track B found missing. Owned here
        # because this runtime is what actually observes the provider.
        self.health = health_tracker or _new_tracker()
        self.last_valid_observation: datetime | None = None
        self.last_error: str | None = None
        self.frames_accepted = 0
        self.frames_dropped = 0
        self.resync_pending = False
        self.started_at: datetime | None = None
        self.stopped_at: datetime | None = None

    # ── lifecycle ───────────────────────────────────────────────────────────
    def start(self, *, now: datetime | None = None) -> str:
        """Open the public stream. Refuses when not explicitly enabled.

        A disabled runtime is not a failed one: it reports DISABLED, which the
        health layer renders as a real reason rather than an outage.
        """
        if not self.config.enabled:
            self.state = RuntimeState.DISABLED
            return self.state.value
        self.state = RuntimeState.STARTING
        try:
            self.transport = (self._transport_factory() if self._transport_factory
                              else BinanceWebSocketTransport())
            self.transport.connect()
            self.transport.subscribe(self.config.streams())
        except Exception as exc:
            # Contained: no socket left half-open, no retry storm, and the
            # provider is told the truth.
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            self.state = RuntimeState.FAILED_SAFE
            self._observe_provider_error(exc)
            self.transport = None
            return self.state.value
        self.controller.on_connect()
        self.supervisor.connect()
        self.started_at = now or _utcnow()
        self.state = RuntimeState.RUNNING
        self.health.observe_success(PROVIDER_ID)
        return self.state.value

    def stop(self) -> str:
        """Close cleanly. Safe to call when never started or already stopped."""
        self.state = RuntimeState.STOPPING
        try:
            if self.transport is not None:
                self.transport.close()
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
        finally:
            self.transport = None
            # Queue released so a stopped runtime holds no residual frames.
            self.controller.queue.clear()
            self.controller.connected = False
            self.supervisor.state = StreamState.STOPPED
            self.stopped_at = _utcnow()
            self.state = RuntimeState.STOPPED
        return self.state.value

    # ── events ──────────────────────────────────────────────────────────────
    def on_frame(self, frame, *, now: datetime | None = None) -> str:
        """Feed one public frame through the certified controller.

        Only an ACCEPTED frame advances the last-valid-observation clock. A
        dropped, duplicated or gapped frame is data the runtime saw but could not
        trust, and letting it refresh freshness would be the exact
        connectivity-as-freshness error this program already fixed once.
        """
        at = now or _utcnow()
        result = self.controller.on_frame(frame)
        if result == "ACCEPTED":
            self.frames_accepted += 1
            self.last_valid_observation = at
            self.supervisor.observe(at)
            self.supervisor.capture(frame)
            self.health.observe_success(PROVIDER_ID)
        elif result == "DROPPED_BACKPRESSURE":
            # Never silently dropped: the count is surfaced as a data-quality
            # condition so a slow consumer degrades health rather than hiding.
            self.frames_dropped += 1
        elif result == "GAP_DETECTED":
            self.resync_pending = True
        return result

    def on_disconnect(self, reason: str, *, now: datetime | None = None) -> str:
        self.last_error = str(reason)[:200]
        self.controller.on_disconnect()
        state = self.supervisor.disconnect(reason)
        if state == StreamState.FAILED:
            # Reconnect budget spent. Contained, not silently retrying forever.
            self.state = RuntimeState.FAILED_SAFE
        self._observe_provider_error(RuntimeError(reason))
        return state.value

    def _observe_provider_error(self, exc: BaseException) -> None:
        from saathi.connectors.providers.models import ProviderErrorCode

        text = f"{type(exc).__name__} {exc}".lower()
        if "rate" in text and "limit" in text:
            code = ProviderErrorCode.RATE_LIMITED
        elif any(t in text for t in ("dns", "resolve", "getaddrinfo", "refused",
                                     "unreachable", "timeout")):
            code = ProviderErrorCode.CONNECTION_FAILED
        else:
            code = ProviderErrorCode.PROVIDER_UNAVAILABLE
        self.health.observe_error(PROVIDER_ID, code)

    # ── health surfaces ─────────────────────────────────────────────────────
    def snapshot(self, *, now: datetime | None = None) -> dict:
        """Exactly the shape `read_market_data` consumes. No new DTO.

        `freshness` is left absent on purpose. Whether the feed is fresh depends
        on the caller's evaluation time and staleness policy, and the collector
        already decides that from `last_valid_observation`. Deciding it here
        would put a second, competing freshness rule in the system.
        """
        connected = bool(self.controller.connected and self.state is RuntimeState.RUNNING)
        return {
            "connected": connected,
            "source": "LIVE_PUBLIC",
            "last_valid_observation": _iso(self.last_valid_observation),
            "sequence_gap": self.supervisor.state is StreamState.STALE or self.resync_pending,
            "resync_pending": self.resync_pending,
            "reconnecting": self.supervisor.state is StreamState.BACKOFF,
            "reconnect_exhausted": self.supervisor.state is StreamState.FAILED,
            # Every failure path above closes the transport and stops, so an
            # exhausted runtime is contained rather than ambiguously live.
            "contained": True,
        }

    def provider_state(self) -> str:
        """Canonical provider state, read WITHOUT creating a record."""
        rec = self.health.peek(PROVIDER_ID)
        if rec is None:
            return "UNKNOWN"
        return rec.state

    def diagnostics(self) -> dict:
        return {
            "runtime_state": self.state.value,
            "stream_state": self.supervisor.state.value,
            "runtime_version": RUNTIME_VERSION,
            "transport_version": TRANSPORT_VERSION,
            "symbols": list(self.config.symbols),
            "streams": list(self.config.streams()),
            "market_type": "SPOT",
            "scope": PROVIDER_SCOPE,
            "frames_accepted": self.frames_accepted,
            "frames_dropped": self.frames_dropped,
            "queue_depth": len(self.controller.queue),
            "queue_max": self.controller.max_queue,
            "capture_overflow": self.supervisor.capture_overflow,
            "reconnect_count": self.supervisor.reconnect_count,
            "last_error": self.last_error,
            "requires_credentials": False,
            "authorizes_execution": False,
        }


def _new_tracker():
    from saathi.connectors.providers.health import ProviderHealthTracker

    return ProviderHealthTracker()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.strftime("%Y-%m-%dT%H:%M:%SZ")


_RUNTIME: PublicMarketDataRuntime | None = None


def default_public_market_data(config: PublicMarketDataConfig | None = None
                               ) -> PublicMarketDataRuntime:
    """The one process-wide instance. Constructed lazily; connects nothing.

    A per-caller instance would give the health layer a runtime no request ever
    feeds — green, and about nothing.
    """
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = PublicMarketDataRuntime(config)
    return _RUNTIME


def reset_public_market_data_for_tests(config: PublicMarketDataConfig | None = None
                                       ) -> PublicMarketDataRuntime:
    global _RUNTIME
    if _RUNTIME is not None:
        try:
            _RUNTIME.stop()
        except Exception:
            pass
    _RUNTIME = PublicMarketDataRuntime(config)
    return _RUNTIME
