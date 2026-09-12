"""Phase 4 — deterministic freshness classification.

Freshness is computed from the source publication time when available, measured
against ``now``. Retrieval time is preserved SEPARATELY (on the fact) and is
never used as a substitute for publication time. Freshness is never inferred
from page order or ranking.
"""
from __future__ import annotations

from enum import Enum


class Freshness(str, Enum):
    REALTIME = "REALTIME"            # < 1 minute
    NEAR_REALTIME = "NEAR_REALTIME"  # < 15 minutes
    TODAY = "TODAY"                  # < 24 hours
    RECENT = "RECENT"               # < 7 days
    STALE = "STALE"                 # >= 7 days
    UNKNOWN = "UNKNOWN"             # no publication time available


_MIN = 60.0
_HOUR = 3600.0
_DAY = 86_400.0

# Ordering for "meets requirement?" comparisons (fresher = smaller rank).
_ORDER = {
    Freshness.REALTIME: 0,
    Freshness.NEAR_REALTIME: 1,
    Freshness.TODAY: 2,
    Freshness.RECENT: 3,
    Freshness.STALE: 4,
    Freshness.UNKNOWN: 5,
}


def classify_freshness(publication_ts: float | None, *, now: float) -> Freshness:
    """Bucket by publication age. No publication time -> UNKNOWN (never guessed)."""
    if publication_ts is None:
        return Freshness.UNKNOWN
    try:
        age = float(now) - float(publication_ts)
    except (TypeError, ValueError):
        return Freshness.UNKNOWN
    if age < 0:
        # publication in the future -> untrustworthy timestamp, not "fresh"
        return Freshness.UNKNOWN
    if age < _MIN:
        return Freshness.REALTIME
    if age < 15 * _MIN:
        return Freshness.NEAR_REALTIME
    if age < _DAY:
        return Freshness.TODAY
    if age < 7 * _DAY:
        return Freshness.RECENT
    return Freshness.STALE


def meets_requirement(actual: Freshness, requirement: Freshness) -> bool:
    """True when ``actual`` is at least as fresh as ``requirement``.

    UNKNOWN never satisfies a concrete requirement (fail-closed).
    """
    if actual == Freshness.UNKNOWN:
        return requirement == Freshness.UNKNOWN
    return _ORDER[actual] <= _ORDER[requirement]
