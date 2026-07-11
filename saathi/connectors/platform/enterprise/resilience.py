"""M15.3 circuit breaker + layered rate limiter (deterministic, store-backed).

A circuit breaker scoped to connector/account/operation prevents runaway retries
and provider abuse. One failing account must not disable all accounts for the
same connector. Rate limiting is layered (user/connector/account/operation).
Both are deterministic and testable with an injectable clock.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    key: str
    failure_threshold: int = 5
    window_sec: float = 60.0
    cooldown_sec: float = 30.0
    failures: list = field(default_factory=list)   # timestamps
    opened_at: float = 0.0
    state: str = BreakerState.CLOSED.value

    def _now(self, clock) -> float:
        return clock() if clock else time.time()

    def allow(self, *, clock=None) -> bool:
        now = self._now(clock)
        if self.state == BreakerState.OPEN.value:
            if now - self.opened_at >= self.cooldown_sec:
                self.state = BreakerState.HALF_OPEN.value   # allow one probe
                return True
            return False
        return True

    def record(self, *, success: bool, clock=None) -> None:
        now = self._now(clock)
        if success:
            if self.state == BreakerState.HALF_OPEN.value:
                self.state = BreakerState.CLOSED.value
                self.failures.clear()
            return
        # prune failures outside the window
        self.failures = [t for t in self.failures if now - t <= self.window_sec]
        self.failures.append(now)
        if self.state == BreakerState.HALF_OPEN.value or \
                len(self.failures) >= self.failure_threshold:
            self.state = BreakerState.OPEN.value
            self.opened_at = now

    def reset(self) -> None:
        self.state = BreakerState.CLOSED.value
        self.failures.clear()
        self.opened_at = 0.0


class BreakerRegistry:
    """In-process breakers keyed by connector[:account[:operation]]. Scoped so a
    single account failure does not trip the whole connector."""
    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, *, connector_id: str, account_id: str = "", operation: str = "",
            **kw) -> CircuitBreaker:
        key = ":".join(x for x in (connector_id, account_id, operation) if x)
        if key not in self._breakers:
            self._breakers[key] = CircuitBreaker(key=key, **kw)
        return self._breakers[key]


@dataclass
class RateLimiter:
    """Token-window limiter layered by an arbitrary key. Deterministic."""
    limit: int = 60
    window_sec: float = 60.0
    _hits: dict = field(default_factory=dict)   # key -> [timestamps]

    def check(self, key: str, *, clock=None) -> dict:
        now = clock() if clock else time.time()
        hits = [t for t in self._hits.get(key, []) if now - t <= self.window_sec]
        remaining = self.limit - len(hits)
        allowed = remaining > 0
        if allowed:
            hits.append(now)
        self._hits[key] = hits
        reset_at = (min(hits) + self.window_sec) if hits else now + self.window_sec
        return {"allowed": allowed, "limit": self.limit,
                "remaining": max(0, self.limit - len(hits)),
                "reset_at": reset_at,
                "retry_after": max(0, reset_at - now) if not allowed else 0,
                "reason": None if allowed else "rate_limited"}

    def layered_check(self, *, user: str, connector: str, account: str,
                      operation: str, clock=None) -> dict:
        for scope, key in (("user", f"u:{user}"), ("connector", f"c:{connector}"),
                           ("account", f"a:{account}"), ("operation", f"o:{operation}")):
            r = self.check(key, clock=clock)
            if not r["allowed"]:
                r["scope"] = scope
                return r
        return {"allowed": True, "scope": None}
