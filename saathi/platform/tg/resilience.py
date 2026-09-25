"""RESILIENCE-1 — deterministic degradation policy.

Every critical failure must degrade the same way every time. This is the single
table mapping a failure mode to its required response, so no code path can invent
an optimistic recovery under pressure.

Responses, worst to mildest:
  FAIL_CLOSED        — refuse new work; state is unsafe or unknown.
  RECONCILE_FIRST    — position/fill truth is ambiguous; reconcile before trading.
  HALT_NEW_ORDERS    — keep observing, stop originating new exposure.
  CONTINUE_DEGRADED  — safe to continue with reduced capability.

Two program invariants are structural here:
  * an UNKNOWN or ambiguous outcome NEVER auto-retries, and
  * no failure maps to "continue normally".
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FailureMode(str, Enum):
    PROVIDER_OUTAGE = "PROVIDER_OUTAGE"
    DNS_OUTAGE = "DNS_OUTAGE"
    WEBSOCKET_DISCONNECT = "WEBSOCKET_DISCONNECT"
    SCHEMA_DRIFT = "SCHEMA_DRIFT"
    STALE_MARKET_DATA = "STALE_MARKET_DATA"
    DB_RESTART = "DB_RESTART"
    DISK_PRESSURE = "DISK_PRESSURE"
    PROCESS_RESTART = "PROCESS_RESTART"
    DUPLICATE_EVENT = "DUPLICATE_EVENT"
    SEQUENCE_GAP = "SEQUENCE_GAP"
    OMS_AMBIGUITY = "OMS_AMBIGUITY"
    PARTIAL_WRITE = "PARTIAL_WRITE"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    KILL_SWITCH = "KILL_SWITCH"


class Response(str, Enum):
    FAIL_CLOSED = "FAIL_CLOSED"
    RECONCILE_FIRST = "RECONCILE_FIRST"
    HALT_NEW_ORDERS = "HALT_NEW_ORDERS"
    CONTINUE_DEGRADED = "CONTINUE_DEGRADED"


@dataclass(frozen=True)
class Degradation:
    failure: FailureMode
    response: Response
    auto_retry: bool
    detail: str

    @property
    def allows_new_orders(self) -> bool:
        return self.response == Response.CONTINUE_DEGRADED


# The policy table. Deliberately explicit: adding a failure mode without a decision
# is a KeyError at the boundary, not a silent "continue".
_POLICY: dict[FailureMode, tuple[Response, bool, str]] = {
    # Market data availability: we can still observe, but must not originate exposure
    # from a feed we cannot trust or refresh.
    FailureMode.PROVIDER_OUTAGE: (
        Response.HALT_NEW_ORDERS, False, "no trusted price source; stop originating exposure"),
    FailureMode.DNS_OUTAGE: (
        Response.HALT_NEW_ORDERS, False, "provider unreachable; environment-level blocker"),
    FailureMode.WEBSOCKET_DISCONNECT: (
        Response.HALT_NEW_ORDERS, False, "stream down; bounded reconnect, never auto-order"),
    FailureMode.STALE_MARKET_DATA: (
        Response.HALT_NEW_ORDERS, False, "data older than freshness policy"),
    FailureMode.SEQUENCE_GAP: (
        Response.HALT_NEW_ORDERS, False, "gap in stream; snapshot resync required"),

    # Truth is unknown: reconcile before anything else.
    FailureMode.OMS_AMBIGUITY: (
        Response.RECONCILE_FIRST, False, "order outcome UNKNOWN; never auto-retry"),
    FailureMode.RECONCILIATION_MISMATCH: (
        Response.RECONCILE_FIRST, False, "books and venue disagree; explicit resolution required"),
    FailureMode.PROCESS_RESTART: (
        Response.RECONCILE_FIRST, False, "restart never auto-executes prior intent"),

    # Storage / integrity: unsafe to write or trust state.
    FailureMode.SCHEMA_DRIFT: (
        Response.FAIL_CLOSED, False, "contract changed underneath us; refuse to guess"),
    FailureMode.PARTIAL_WRITE: (
        Response.FAIL_CLOSED, False, "durability broken; state may be torn"),
    FailureMode.DISK_PRESSURE: (
        Response.FAIL_CLOSED, False, "cannot guarantee durable evidence"),
    FailureMode.DB_RESTART: (
        Response.RECONCILE_FIRST, False, "reopen and verify state before trading"),

    # Explicit operator/safety control.
    FailureMode.KILL_SWITCH: (
        Response.FAIL_CLOSED, False, "operator halt; nothing proceeds"),

    # Benign and fully handled: idempotency already covers it.
    FailureMode.DUPLICATE_EVENT: (
        Response.CONTINUE_DEGRADED, False, "idempotent; duplicate ignored without effect"),
}


def degrade(failure: FailureMode) -> Degradation:
    """Deterministic response for a failure mode. Unknown modes fail closed."""
    if failure not in _POLICY:
        return Degradation(failure, Response.FAIL_CLOSED, False, "unmapped failure mode")
    response, auto_retry, detail = _POLICY[failure]
    return Degradation(failure, response, auto_retry, detail)


def worst(failures) -> Degradation:
    """Combine concurrent failures — the most restrictive response wins."""
    order = {
        Response.CONTINUE_DEGRADED: 0,
        Response.HALT_NEW_ORDERS: 1,
        Response.RECONCILE_FIRST: 2,
        Response.FAIL_CLOSED: 3,
    }
    decisions = [degrade(f) for f in failures]
    if not decisions:
        return Degradation(FailureMode.KILL_SWITCH, Response.CONTINUE_DEGRADED, False, "no failure")
    return max(decisions, key=lambda d: order[d.response])
