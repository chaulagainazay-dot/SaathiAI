"""M21.2 — Bounded provider-scoped circuit breaker.

Process-local by default (not durable across restarts — documented limitation).
Policy denials and invalid requests must not call record_failure.
Kill switch takes precedence over circuit state (evaluated by callers first).

States: CLOSED → OPEN (threshold) → HALF_OPEN (cooldown) → CLOSED (success)
        or HALF_OPEN → OPEN (failed probe).
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    DISABLED = "disabled"


Clock = Callable[[], float]


def _default_clock() -> float:
    return time.time()


@dataclass
class CircuitConfig:
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0
    half_open_max_probes: int = 1
    # Auth failures count toward circuit (documented) but are not soft-retried
    count_auth_failures: bool = True
    count_rate_limits: bool = True


@dataclass
class CircuitSnapshot:
    provider_id: str
    state: CircuitState
    failure_count: int
    success_count: int
    opened_at: Optional[float]
    last_failure_at: Optional[float]
    last_success_at: Optional[float]
    last_transition_at: Optional[float]
    last_reason: str
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d


@dataclass
class _Breaker:
    provider_id: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    opened_at: Optional[float] = None
    last_failure_at: Optional[float] = None
    last_success_at: Optional[float] = None
    last_transition_at: Optional[float] = None
    last_reason: str = ""
    half_open_probes: int = 0
    config: CircuitConfig = field(default_factory=CircuitConfig)


class ProviderCircuitBreakerRegistry:
    """Provider-scoped circuit breakers with injectable clock."""

    def __init__(
        self,
        *,
        config: Optional[CircuitConfig] = None,
        clock: Optional[Clock] = None,
        enabled: bool = True,
    ) -> None:
        self._config = config or CircuitConfig()
        self._clock = clock or _default_clock
        self._enabled = enabled
        self._lock = threading.RLock()
        self._breakers: dict[str, _Breaker] = {}
        self._telemetry: list[dict[str, Any]] = []

    def set_clock(self, clock: Clock) -> None:
        self._clock = clock

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def _key(self, provider_id: str) -> str:
        return (provider_id or "").strip().lower() or "unknown"

    def _get(self, provider_id: str) -> _Breaker:
        k = self._key(provider_id)
        if k not in self._breakers:
            self._breakers[k] = _Breaker(provider_id=k, config=self._config)
        return self._breakers[k]

    def _emit(self, event: str, provider_id: str, **extra: Any) -> None:
        # Privacy-safe: no prompts, secrets, raw errors
        row = {
            "schema": "m21.2.circuit_telemetry.v1",
            "event": event,
            "provider_id": provider_id,
            "ts": self._clock(),
        }
        for k, v in extra.items():
            if k in ("prompt", "output", "api_key", "token", "error_raw"):
                continue
            row[k] = v
        self._telemetry.append(row)
        if len(self._telemetry) > 200:
            self._telemetry = self._telemetry[-100:]

    def _maybe_half_open(self, b: _Breaker) -> None:
        if b.state is not CircuitState.OPEN:
            return
        if b.opened_at is None:
            return
        if (self._clock() - b.opened_at) >= b.config.cooldown_seconds:
            b.state = CircuitState.HALF_OPEN
            b.half_open_probes = 0
            b.last_transition_at = self._clock()
            b.last_reason = "cooldown_elapsed"
            self._emit("half_open", b.provider_id, reason="cooldown_elapsed")

    def state(self, provider_id: str) -> CircuitState:
        if not self._enabled:
            return CircuitState.DISABLED
        with self._lock:
            b = self._get(provider_id)
            self._maybe_half_open(b)
            return b.state

    def is_open(self, provider_id: str) -> bool:
        st = self.state(provider_id)
        return st is CircuitState.OPEN

    def allow_request(self, provider_id: str) -> tuple[bool, str]:
        """Whether a provider attempt may proceed under circuit rules."""
        if not self._enabled:
            return True, "circuit_disabled"
        with self._lock:
            b = self._get(provider_id)
            self._maybe_half_open(b)
            if b.state is CircuitState.CLOSED:
                return True, "closed"
            if b.state is CircuitState.OPEN:
                return False, "circuit_open"
            if b.state is CircuitState.HALF_OPEN:
                if b.half_open_probes >= b.config.half_open_max_probes:
                    return False, "half_open_probe_exhausted"
                b.half_open_probes += 1
                return True, "half_open_probe"
            return True, "disabled"

    def record_success(self, provider_id: str) -> CircuitSnapshot:
        with self._lock:
            b = self._get(provider_id)
            b.success_count += 1
            b.last_success_at = self._clock()
            b.failure_count = 0
            if b.state in {CircuitState.HALF_OPEN, CircuitState.OPEN, CircuitState.CLOSED}:
                prev = b.state
                b.state = CircuitState.CLOSED
                b.opened_at = None
                b.half_open_probes = 0
                b.last_transition_at = self._clock()
                b.last_reason = "success"
                if prev is not CircuitState.CLOSED:
                    self._emit("close", b.provider_id, reason="success", previous=prev.value)
            return self.snapshot(provider_id)

    def record_failure(
        self,
        provider_id: str,
        *,
        reason: str = "provider_failure",
        counts: bool = True,
    ) -> CircuitSnapshot:
        """Record a provider failure. Callers must not count policy denials."""
        with self._lock:
            b = self._get(provider_id)
            if not counts:
                b.last_reason = f"ignored:{reason}"
                return self.snapshot(provider_id)
            b.failure_count += 1
            b.last_failure_at = self._clock()
            b.last_reason = reason
            if b.state is CircuitState.HALF_OPEN:
                b.state = CircuitState.OPEN
                b.opened_at = self._clock()
                b.last_transition_at = self._clock()
                b.last_reason = f"half_open_failed:{reason}"
                self._emit("reopen", b.provider_id, reason=reason)
            elif b.failure_count >= b.config.failure_threshold:
                if b.state is not CircuitState.OPEN:
                    b.state = CircuitState.OPEN
                    b.opened_at = self._clock()
                    b.last_transition_at = self._clock()
                    self._emit(
                        "open",
                        b.provider_id,
                        reason=reason,
                        failure_count=b.failure_count,
                    )
            return self.snapshot(provider_id)

    def manual_reset(self, provider_id: str) -> CircuitSnapshot:
        with self._lock:
            b = self._get(provider_id)
            b.state = CircuitState.CLOSED
            b.failure_count = 0
            b.half_open_probes = 0
            b.opened_at = None
            b.last_transition_at = self._clock()
            b.last_reason = "manual_reset"
            self._emit("manual_reset", b.provider_id)
            return self.snapshot(provider_id)

    def snapshot(self, provider_id: str) -> CircuitSnapshot:
        with self._lock:
            b = self._get(provider_id)
            self._maybe_half_open(b)
            return CircuitSnapshot(
                provider_id=b.provider_id,
                state=b.state,
                failure_count=b.failure_count,
                success_count=b.success_count,
                opened_at=b.opened_at,
                last_failure_at=b.last_failure_at,
                last_success_at=b.last_success_at,
                last_transition_at=b.last_transition_at,
                last_reason=b.last_reason,
                config={
                    "failure_threshold": b.config.failure_threshold,
                    "cooldown_seconds": b.config.cooldown_seconds,
                    "half_open_max_probes": b.config.half_open_max_probes,
                    "process_local": True,
                    "persistent": False,
                },
            )

    def all_snapshots(self) -> list[CircuitSnapshot]:
        with self._lock:
            keys = sorted(self._breakers.keys()) or []
            # Also expose known empty for ollama if never touched
            return [self.snapshot(k) for k in keys]

    def drain_telemetry(self) -> list[dict[str, Any]]:
        with self._lock:
            out = list(self._telemetry)
            self._telemetry.clear()
            return out


_GLOBAL: Optional[ProviderCircuitBreakerRegistry] = None
_GLOBAL_LOCK = threading.Lock()


def get_circuit_registry(
    *,
    reset: bool = False,
    config: Optional[CircuitConfig] = None,
    clock: Optional[Clock] = None,
) -> ProviderCircuitBreakerRegistry:
    global _GLOBAL
    with _GLOBAL_LOCK:
        if reset or _GLOBAL is None:
            _GLOBAL = ProviderCircuitBreakerRegistry(config=config, clock=clock)
        elif clock is not None:
            _GLOBAL.set_clock(clock)
        return _GLOBAL
