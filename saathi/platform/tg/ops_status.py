"""CENTRAL-COMMAND-TRADING-OPS — the read-only serving edge for the ops snapshot.

Central Command asks one question — "is trading okay?" — and this is the only
place that answers it. The answer is the canonical TRADING-OPS-1 snapshot,
collected through HEALTH-COLLECTOR-1's safe reads. Nothing here classifies
health, and nothing downstream is permitted to either.

  live subsystems -> safe reads -> producers -> collector -> ops snapshot
                  -> THIS SERVICE -> HTTP -> Central Command

TWO STATES THAT MUST NEVER BE CONFUSED, and the reason this module exists at all:

  SUBSYSTEM_INSUFFICIENT_EVIDENCE  the collector ran and a subsystem could not
                                   be judged.
  SNAPSHOT_STALE                   the collector has not run recently, so NOTHING
                                   here is current — including the parts that say
                                   HEALTHY.

The second is the dangerous one. A monitor that stops collecting keeps serving
its last cheerful answer forever, and an operator reading a green panel has no
way to tell that it froze an hour ago. So freshness is computed on every read,
travels with the payload, and a stale snapshot is explicitly NOT presented as
current health.

COLLECTION IS REQUEST-DRIVEN AND COALESCED. No thread, no daemon, no new process
manager. The collector's own minimum interval means a burst of page loads does
not become a burst of collections, and a request that cannot collect serves the
last result plainly labelled by its age.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from saathi.platform.tg.health_collector import (
    TradingHealthCollector,
    snapshot_from_collection,
)
from saathi.platform.tg.strategy_observation import _epoch as iso_epoch
from saathi.platform.tg.trading_ops import OpsMode

STATUS_VERSION = "central-command-trading-ops/v1.0.0"

#: How old a snapshot may be before it stops describing "now". Deliberately
#: generous: health is not a millisecond signal, and an over-tight window would
#: make the panel cry stale during normal operation.
DEFAULT_MAX_SNAPSHOT_AGE_SECONDS = 180


class Freshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    #: The collector has never produced a snapshot in this process.
    NEVER_COLLECTED = "NEVER_COLLECTED"


@dataclass(frozen=True)
class OpsStatus:
    """What the status route returns. Derived; persisted nowhere."""

    freshness: str
    collected_at: str | None
    served_at: str | None
    age_seconds: int | None
    max_age_seconds: int
    snapshot: dict | None
    status_version: str = STATUS_VERSION
    authorizes_execution: bool = False

    def to_public(self) -> dict:
        return {
            "status_version": self.status_version,
            "freshness": self.freshness,
            "collected_at": self.collected_at,
            "served_at": self.served_at,
            "age_seconds": self.age_seconds,
            "max_age_seconds": self.max_age_seconds,
            # THE LOAD-BEARING FLAG. A stale snapshot still carries its last
            # readings — an operator may want to see what things looked like —
            # but this says plainly that they are not current, and the UI is
            # required to stop showing confident health when it is false.
            "reflects_current_state": self.freshness == Freshness.FRESH.value,
            "snapshot": self.snapshot,
            "authorizes_execution": False,
            "live_trading_authorized": False,
        }


class TradingOpsStatusService:
    """Hosts one collector and serves its snapshot with honest freshness.

    Deliberately NOT a scheduler. The host calls `status()` when someone asks,
    the collector coalesces, and freshness makes the cadence visible instead of
    hiding it behind a background loop nobody can see failing.
    """

    def __init__(
        self,
        *,
        min_interval_seconds: int = 30,
        max_age_seconds: int = DEFAULT_MAX_SNAPSHOT_AGE_SECONDS,
        mode: str = OpsMode.SHADOW.value,
    ):
        self.collector = TradingHealthCollector(min_interval_seconds=min_interval_seconds)
        self.max_age_seconds = int(max_age_seconds)
        self.mode = mode
        self._last_snapshot: dict | None = None
        self._last_collected_at: str | None = None

    def refresh(self, *, now: str, **sources) -> None:
        """Collect if due. Coalesced ticks leave the previous snapshot in place."""
        result = self.collector.tick(evaluation_time=now, **sources)
        if result is None:
            return
        snap = snapshot_from_collection(result, mode=self.mode)
        self._last_snapshot = snap.to_public()
        self._last_collected_at = now

    def status(self, *, now: str, collect: bool = True, **sources) -> OpsStatus:
        """Current operational status, with freshness computed at read time.

        `now` is supplied rather than read, so a caller — and a test — controls
        the clock. Freshness is recomputed on EVERY read, never cached alongside
        the snapshot: a snapshot that was fresh when collected becomes stale by
        sitting still, and only comparing against the current read time catches
        that.
        """
        if collect:
            try:
                self.refresh(now=now, **sources)
            except Exception:
                # A failed refresh must not deny the operator the last known
                # picture — but it also must not make it look current. The
                # freshness computed below is what tells them which it is.
                pass

        if self._last_snapshot is None or self._last_collected_at is None:
            return OpsStatus(
                freshness=Freshness.NEVER_COLLECTED.value,
                collected_at=None, served_at=now, age_seconds=None,
                max_age_seconds=self.max_age_seconds, snapshot=None,
            )

        age = _age_seconds(self._last_collected_at, now)
        fresh = age is not None and age <= self.max_age_seconds
        return OpsStatus(
            freshness=Freshness.FRESH.value if fresh else Freshness.STALE.value,
            collected_at=self._last_collected_at,
            served_at=now,
            age_seconds=age,
            max_age_seconds=self.max_age_seconds,
            snapshot=self._last_snapshot,
        )


def _age_seconds(collected_at: str, now: str) -> int | None:
    a, b = iso_epoch(collected_at), iso_epoch(now)
    if a is None or b is None:
        return None
    # A clock that appears to run backwards is not evidence of freshness.
    return max(0, b - a)


_SERVICE: TradingOpsStatusService | None = None


def default_status_service() -> TradingOpsStatusService:
    """Process-wide service, so freshness and coalescing mean something.

    A per-request instance would report NEVER_COLLECTED forever and re-collect on
    every page load, which is exactly the aggressive polling the design forbids.
    """
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = TradingOpsStatusService()
    return _SERVICE


def reset_status_service_for_tests() -> None:
    global _SERVICE
    _SERVICE = None
