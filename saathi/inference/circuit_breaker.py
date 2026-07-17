"""M21.2 / M24 — Provider-scoped circuit breaker.

M24: authoritative state is the durable governance store (SQLite).
Process-local dicts are no longer production authority.

Public API preserved:
  CircuitState, CircuitConfig, CircuitSnapshot, ProviderCircuitBreakerRegistry,
  get_circuit_registry, record via registry methods.

Policy denials and invalid requests must not call record_failure.
Kill switch takes precedence over circuit state (evaluated by callers first).

States: CLOSED → OPEN (threshold) → HALF_OPEN (cooldown) → CLOSED (success)
        or HALF_OPEN → OPEN (failed probe).
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from saathi.inference.governance_clock import Clock as GovClock
from saathi.inference.governance_store import (
    DurableGovernanceStore,
    get_governance_store,
)

Clock = Callable[[], float]


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    DISABLED = "disabled"


def _default_clock() -> float:
    return get_governance_store().now()


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


def _snap_from_store(d: dict[str, Any]) -> CircuitSnapshot:
    st = CircuitState(d.get("state") or CircuitState.CLOSED.value)
    cfg = dict(d.get("config") or {})
    cfg.setdefault("process_local", False)
    cfg.setdefault("persistent", True)
    return CircuitSnapshot(
        provider_id=d["provider_id"],
        state=st,
        failure_count=int(d.get("failure_count") or 0),
        success_count=int(d.get("success_count") or 0),
        opened_at=d.get("opened_at"),
        last_failure_at=d.get("last_failure_at"),
        last_success_at=d.get("last_success_at"),
        last_transition_at=d.get("last_transition_at"),
        last_reason=d.get("last_reason") or "",
        config=cfg,
    )


class ProviderCircuitBreakerRegistry:
    """Provider-scoped circuit breakers backed by durable governance store.

    Optional ``store`` injection for tests. When ``enabled=False``, all
    requests are allowed (DISABLED semantics) without mutating durable state.
    """

    def __init__(
        self,
        *,
        config: Optional[CircuitConfig] = None,
        clock: Optional[Clock] = None,
        enabled: bool = True,
        store: Optional[DurableGovernanceStore] = None,
        use_global_store: bool = False,
    ) -> None:
        self._config = config or CircuitConfig()
        self._enabled = enabled
        self._clock = clock
        self._lock = threading.RLock()
        self._telemetry: list[dict[str, Any]] = []
        # Non-authoritative local hint only (never production source of truth)
        self._cache: dict[str, str] = {}
        self._use_global = use_global_store
        if store is not None:
            self._store = store
        elif use_global_store:
            self._store = None  # resolve via get_governance_store()
        else:
            # Private durable SQLite (in-memory) — still durable-semantics +
            # transactional; not process-dict authority. Used by unit tests /
            # isolated registries. Production global uses get_circuit_registry().
            self._store = DurableGovernanceStore(
                ":memory:",
                clock=clock,  # type: ignore[arg-type]
                failure_threshold=self._config.failure_threshold,
                cooldown_seconds=self._config.cooldown_seconds,
                half_open_max_probes=self._config.half_open_max_probes,
            )
        if self._store is not None:
            if clock is not None:
                self._store.set_clock(clock)  # type: ignore[arg-type]
            self._store.failure_threshold = self._config.failure_threshold
            self._store.cooldown_seconds = self._config.cooldown_seconds
            self._store.half_open_max_probes = self._config.half_open_max_probes

    def _gov(self) -> DurableGovernanceStore:
        if self._store is not None:
            if self._clock is not None:
                self._store.set_clock(self._clock)  # type: ignore[arg-type]
            self._store.failure_threshold = self._config.failure_threshold
            self._store.cooldown_seconds = self._config.cooldown_seconds
            self._store.half_open_max_probes = self._config.half_open_max_probes
            return self._store
        store = get_governance_store(clock=self._clock)  # type: ignore[arg-type]
        store.failure_threshold = self._config.failure_threshold
        store.cooldown_seconds = self._config.cooldown_seconds
        store.half_open_max_probes = self._config.half_open_max_probes
        return store

    def set_clock(self, clock: Clock) -> None:
        self._clock = clock
        if self._store is not None:
            self._store.set_clock(clock)  # type: ignore[arg-type]

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def _key(self, provider_id: str) -> str:
        return (provider_id or "").strip().lower() or "unknown"

    def _emit(self, event: str, provider_id: str, **extra: Any) -> None:
        row = {
            "schema": "m21.2.circuit_telemetry.v1",
            "event": event,
            "provider_id": provider_id,
            "ts": (self._clock or self._gov().now)(),
            "persistent": True,
        }
        for k, v in extra.items():
            if k in ("prompt", "output", "api_key", "token", "error_raw"):
                continue
            row[k] = v
        self._telemetry.append(row)
        if len(self._telemetry) > 200:
            self._telemetry = self._telemetry[-100:]

    def state(self, provider_id: str) -> CircuitState:
        if not self._enabled:
            return CircuitState.DISABLED
        snap = self._gov().circuit_snapshot(provider_id)
        st = CircuitState(snap["state"])
        self._cache[self._key(provider_id)] = st.value
        return st

    def is_open(self, provider_id: str) -> bool:
        st = self.state(provider_id)
        return st is CircuitState.OPEN

    def allow_request(self, provider_id: str) -> tuple[bool, str]:
        """Whether a provider attempt may proceed under circuit rules."""
        if not self._enabled:
            return True, "circuit_disabled"
        ok, reason, snap = self._gov().allow_request(provider_id)
        self._cache[self._key(provider_id)] = snap.get("state", "")
        return ok, reason

    def record_success(self, provider_id: str) -> CircuitSnapshot:
        d = self._gov().record_success(provider_id)
        self._emit("close", provider_id, reason="success", previous=d.get("state"))
        return _snap_from_store(d)

    def record_failure(
        self,
        provider_id: str,
        *,
        reason: str = "provider_failure",
        counts: bool = True,
    ) -> CircuitSnapshot:
        """Record a provider failure. Callers must not count policy denials."""
        d = self._gov().record_failure(provider_id, reason=reason, counts=counts)
        if counts and d.get("state") == CircuitState.OPEN.value:
            self._emit("open", provider_id, reason=reason, failure_count=d.get("failure_count"))
        return _snap_from_store(d)

    def manual_reset(self, provider_id: str) -> CircuitSnapshot:
        d = self._gov().manual_reset(
            provider_id, confirm=True, reason_code="manual_reset"
        )
        self._emit("manual_reset", provider_id)
        return _snap_from_store(d)

    def snapshot(self, provider_id: str) -> CircuitSnapshot:
        d = self._gov().circuit_snapshot(provider_id)
        return _snap_from_store(d)

    def all_snapshots(self) -> list[CircuitSnapshot]:
        return [_snap_from_store(d) for d in self._gov().all_circuit_snapshots()]

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
    store: Optional[DurableGovernanceStore] = None,
    db_path: str | Path | None = None,
) -> ProviderCircuitBreakerRegistry:
    """Global circuit registry — durable by default (M24)."""
    global _GLOBAL
    with _GLOBAL_LOCK:
        if reset or _GLOBAL is None:
            s = store
            if s is None and db_path is not None:
                from saathi.inference.governance_store import reset_governance_store_for_tests

                s = reset_governance_store_for_tests(db_path, clock=clock)  # type: ignore[arg-type]
            _GLOBAL = ProviderCircuitBreakerRegistry(
                config=config,
                clock=clock,
                store=s,
                use_global_store=(s is None),
            )
        elif clock is not None:
            _GLOBAL.set_clock(clock)
        return _GLOBAL
